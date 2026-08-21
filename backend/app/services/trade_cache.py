"""
Local per-user cache of ALL forex trades (any status), backed by a CSV file.

Why: several endpoints ran a plain Firestore .stream() over the whole trade
history on every call — analytics did it regardless of the date range
selected, trade-history did it regardless of status/date filters, and the
backfill-sell-prices / backfill-close-type maintenance endpoints re-scanned
every CLOSED trade just to find the handful still missing a field. Reads
scaled with total account history forever, not with what was actually
needed. That contributed to a Firestore 429 (quota exceeded) during heavy
use. This module fetches only trades updated since the last sync, merges
them into a local file, and lets every caller read from disk instead.

The cache deliberately holds ALL statuses, not just CLOSED — analytics,
trade-history and the backfill endpoints all read the same underlying
Firestore collection, just filtered differently. A per-status-filtered cache
per caller would each need its own delta cursor and could independently miss
trades outside their own filter; one shared full cache with client-side
filtering avoids that.

Cursor is `updated_at` (not `sell_date`) because a trade can be edited after
closing (e.g. close_type backfilled from UNKNOWN, or an OPEN trade closing)
— a sell_date cursor would miss that edit forever.

A missing or corrupt cache file is treated as "no cache" — the caller should
fall back to a full fetch, which self-heals the file on the next write.
"""
import logging
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def cache_path_for_email(email: str, cache_dir: Path) -> Path:
    """Deterministic, filename-safe path for one user's trade cache."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", email)
    return Path(cache_dir) / f"forex_trades_{safe}.csv"


def compute_last_synced(df: pd.DataFrame) -> Optional[pd.Timestamp]:
    """Max updated_at in the cache, or None if there's no usable cursor
    (empty cache, or the column is missing/corrupt)."""
    if df.empty or "updated_at" not in df.columns:
        return None
    ts = pd.to_datetime(df["updated_at"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return None
    return ts.max()


def dedupe_and_merge(existing: pd.DataFrame, new_records: List[dict]) -> pd.DataFrame:
    """Upsert new_records into existing by _doc_id. A record whose _doc_id is
    already present replaces the cached row (the trade was edited in
    Firestore); otherwise it's appended."""
    new_df = pd.DataFrame(new_records)
    if existing.empty:
        return new_df
    if new_df.empty:
        return existing
    combined = pd.concat([existing, new_df], ignore_index=True)
    # keep='last' so the freshly-fetched row wins over the cached one
    return combined.drop_duplicates(subset="_doc_id", keep="last").reset_index(drop=True)


def load_cache(path: Path) -> pd.DataFrame:
    """Read the cache CSV. Returns an empty DataFrame if the file is missing
    or unreadable — callers treat that as "no cache" and do a full refetch."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
        # pandas tolerates almost any bytes as "valid" CSV — a genuinely
        # corrupt/garbage file just produces nonsense columns rather than
        # raising. Require the one column every cache write always includes.
        if "_doc_id" not in df.columns:
            return pd.DataFrame()
        if "updated_at" in df.columns:
            df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True, errors="coerce")
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
        return df
    except Exception:
        return pd.DataFrame()


def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """Write via a temp file + rename so a crash mid-write can't corrupt the
    cache that's already on disk."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp_path, index=False)
    tmp_path.replace(path)


def frame_to_records(df: pd.DataFrame) -> List[dict]:
    """DataFrame.to_dict('records') leaves NaN for missing values, not None.
    Downstream trade-processing code does `if not sell_date_str: continue`,
    and NaN is truthy in Python, so a missing field would slip through
    uncaught instead of being skipped."""
    if df.empty:
        return []
    return df.astype(object).where(df.notna(), None).to_dict('records')


def get_forex_trades_cached(email: str, db, cache_dir: Path) -> List[dict]:
    """Return every trade (any status) for this user as plain dicts, reading
    from the local cache and only pulling the delta (or, if the cache is
    missing/corrupt, everything) from Firestore. Callers filter by status,
    symbol, date range etc. themselves on the returned list — see module
    docstring for why this cache isn't pre-filtered by status.

    Untested against a live Firestore instance in this environment — the
    pure merge/cursor/file logic above has full coverage; this function is
    a thin, largely un-branching wrapper around it plus the actual query,
    the one part that needs a real account to verify.
    """
    from google.cloud.firestore_v1.base_query import FieldFilter

    path = cache_path_for_email(email, cache_dir)
    cached = load_cache(path)
    last_synced = compute_last_synced(cached)

    portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
    query = portfolio_ref
    if last_synced is not None:
        query = query.where(filter=FieldFilter('updated_at', '>', last_synced.to_pydatetime()))

    new_records = []
    for doc in query.stream():
        record = doc.to_dict()
        record['_doc_id'] = doc.id
        new_records.append(record)

    logger.info(
        f"Trade cache [{email}]: {len(cached)} cached, "
        f"{len(new_records)} fetched ({'delta since ' + str(last_synced) if last_synced else 'full refetch'})"
    )

    merged = dedupe_and_merge(cached, new_records)
    if new_records:
        atomic_write_csv(merged, path)

    return frame_to_records(merged)
