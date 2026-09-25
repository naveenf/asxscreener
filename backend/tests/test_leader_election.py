"""Tests for the pure leadership decision function.

Firestore I/O (acquire_or_renew_leadership, is_leader, release_leadership) is
not covered here — it needs a live or emulated Firestore client. This file
only tests decide_leadership(), the pure function that decides
claim/renew/defer given the current leader doc.
"""
from datetime import datetime, timedelta, timezone

from backend.app.services.leader_election import decide_leadership

NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
SELF = "pc-a-1234"
OTHER = "pc-b-5678"


def test_claims_when_no_doc_exists():
    assert decide_leadership(None, NOW, SELF) == "claim"


def test_claims_when_other_lease_expired():
    expired = {"leader_id": OTHER, "leased_until": NOW - timedelta(seconds=1)}
    assert decide_leadership(expired, NOW, SELF) == "claim"


def test_renews_own_valid_lease():
    mine = {"leader_id": SELF, "leased_until": NOW + timedelta(seconds=60)}
    assert decide_leadership(mine, NOW, SELF) == "renew"


def test_defers_to_other_valid_lease():
    theirs = {"leader_id": OTHER, "leased_until": NOW + timedelta(seconds=60)}
    assert decide_leadership(theirs, NOW, SELF) == "defer"


def test_claims_own_expired_lease_rather_than_defer():
    """Re-claiming our own expired lease is the same verb as a fresh claim —
    there is no meaningful distinction once it has lapsed."""
    mine_expired = {"leader_id": SELF, "leased_until": NOW - timedelta(seconds=1)}
    assert decide_leadership(mine_expired, NOW, SELF) == "claim"


def test_claims_when_leased_until_missing():
    """A malformed/legacy doc with no leased_until must not grant leadership
    by accident — treat it as unclaimed."""
    malformed = {"leader_id": OTHER}
    assert decide_leadership(malformed, NOW, SELF) == "claim"


def test_boundary_exactly_at_expiry_is_claimable():
    """leased_until == now is treated as expired (<=), so a lease can't be
    "valid" for zero duration — matches is_leader()'s strict `> now` check."""
    boundary = {"leader_id": OTHER, "leased_until": NOW}
    assert decide_leadership(boundary, NOW, SELF) == "claim"


def test_empty_dict_is_treated_as_no_lease():
    assert decide_leadership({}, NOW, SELF) == "claim"


def test_defers_when_leader_id_missing_but_lease_still_valid():
    """A doc with a valid, unexpired leased_until but no leader_id (e.g. a
    corrupted write) must not be claimed just because it matches nobody —
    that would let two processes both decide "no one owns this, I'll take
    it" and race. Defer and let it expire naturally instead."""
    orphaned = {"leased_until": NOW + timedelta(seconds=60)}
    assert decide_leadership(orphaned, NOW, SELF) == "defer"
