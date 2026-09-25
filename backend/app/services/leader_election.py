"""
Leader Election Service

When this app runs on more than one machine against the same Oanda account
and Firestore project, only ONE instance may ever place an order, close a
position, or move a stop. This module elects that instance via a single
Firestore doc (config/leader_election) holding a renewable lease, so the
active/standby role is decided centrally rather than relying on any
in-process lock — threading.Lock (see refresh_manager.py) only protects a
process against itself, not against a second machine.

Standby instances keep running normally otherwise (screening, serving the
UI); they simply skip every trade-mutating call.

Usage: call acquire_or_renew_leadership() near the start of each scheduled
task (run_forex_refresh_task, run_preclose_check, run_max_hold_close_check)
to renew the lease and learn the current verdict. If meaningful time may
have passed since then (e.g. after the ~60s screener run in
run_forex_refresh_task), call is_leader() again immediately before the
mutating action — a lease can expire mid-cycle, and a stale in-process
belief must never be trusted on its own.

Fails CLOSED: any Firestore error is treated as "not leader" — never assume
leadership when the source of truth can't be reached.
"""
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from ..config import settings
from ..firebase_setup import db

logger = logging.getLogger(__name__)

_LEADER_COLLECTION = "config"
_LEADER_DOC_ID = "leader_election"

# Stable for the life of this process. Prefixed with an optional human label
# (settings.INSTANCE_LABEL) so logs/UI can show something meaningful instead
# of just a hostname.
_label = settings.INSTANCE_LABEL.strip()
INSTANCE_ID = f"{_label + '-' if _label else ''}{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"


def decide_leadership(current_doc, now: datetime, self_id: str) -> str:
    """Pure decision: what this process should do given the current leader doc.

    current_doc is the Firestore doc's to_dict() (or None if it doesn't
    exist). Returns:
      "claim"  — no one holds a valid lease (missing doc, missing
                 leased_until, or leased_until <= now) — includes re-claiming
                 our own expired lease, which is the same verb as a fresh claim.
      "renew"  — we already hold a still-valid lease.
      "defer"  — someone else holds a still-valid lease.

    A lease is valid strictly up to and including leased_until; at or past
    that instant it is expired (leased_until <= now => "claim"), matching
    is_leader()'s strict `leased_until > now` check for a currently-valid one.
    """
    if not current_doc:
        return "claim"

    leader_id = current_doc.get("leader_id")
    leased_until = current_doc.get("leased_until")

    if leased_until is None or leased_until <= now:
        return "claim"
    if leader_id == self_id:
        return "renew"
    return "defer"


def _leader_doc_ref():
    return db.collection(_LEADER_COLLECTION).document(_LEADER_DOC_ID)


@firestore.transactional
def _acquire_txn(transaction, doc_ref, self_id: str, lease_seconds: int) -> bool:
    now = datetime.now(timezone.utc)
    snapshot = doc_ref.get(transaction=transaction)
    current = snapshot.to_dict() if snapshot.exists else None

    verdict = decide_leadership(current, now, self_id)
    if verdict == "defer":
        return False

    transaction.set(doc_ref, {
        "leader_id": self_id,
        "leased_until": now + timedelta(seconds=lease_seconds),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    return True


def acquire_or_renew_leadership(lease_seconds: int = None) -> bool:
    """Attempt to become, or remain, leader. Safe to call from every scheduled
    task — first-claim and renewal go through the same atomic transaction, so
    two instances racing after an expired lease can't both win.

    Returns True iff this process is the leader immediately after the call.
    """
    lease_seconds = lease_seconds if lease_seconds is not None else settings.LEADER_LEASE_SECONDS
    doc_ref = _leader_doc_ref()
    try:
        transaction = db.transaction()
        won = _acquire_txn(transaction, doc_ref, INSTANCE_ID, lease_seconds)
        if won:
            logger.debug(f"Leader election: {INSTANCE_ID} holds the lease.")
        else:
            logger.info(f"Leader election: {INSTANCE_ID} is standby this cycle.")
        return won
    except Exception as e:
        logger.error(f"Leader election: acquire/renew failed for {INSTANCE_ID}: {e}")
        return False  # fail closed


def is_leader() -> bool:
    """Cheap read-only re-check for use immediately before a mutating action,
    in case meaningful time passed since the last acquire_or_renew_leadership()
    call and the lease has since expired or moved to another instance.
    """
    try:
        snapshot = _leader_doc_ref().get()
        if not snapshot.exists:
            return False
        data = snapshot.to_dict()
        leased_until = data.get("leased_until")
        return (
            data.get("leader_id") == INSTANCE_ID
            and leased_until is not None
            and leased_until > datetime.now(timezone.utc)
        )
    except Exception as e:
        logger.error(f"Leader election: is_leader check failed for {INSTANCE_ID}: {e}")
        return False  # fail closed


@firestore.transactional
def _release_txn(transaction, doc_ref, self_id: str):
    snapshot = doc_ref.get(transaction=transaction)
    if not snapshot.exists:
        return
    if snapshot.to_dict().get("leader_id") != self_id:
        return  # someone else already took over — don't clobber their claim
    transaction.set(doc_ref, {
        "leader_id": self_id,
        "leased_until": datetime.now(timezone.utc),
        "updated_at": firestore.SERVER_TIMESTAMP,
    })


def release_leadership():
    """Best-effort: give up leadership immediately (e.g. on clean shutdown) so
    the standby doesn't have to wait out the full lease to take over. Never
    raises — a failed release just means the lease expires normally."""
    doc_ref = _leader_doc_ref()
    try:
        transaction = db.transaction()
        _release_txn(transaction, doc_ref, INSTANCE_ID)
        logger.info(f"Leader election: {INSTANCE_ID} released leadership.")
    except Exception as e:
        logger.warning(f"Leader election: release failed for {INSTANCE_ID}: {e}")
