"""
Tests for the local trade cache — avoids re-reading the entire closed-trades
history from Firestore on every analytics page load.

Covers only the pure/file-local logic (path naming, merge/dedupe, cursor
computation, corrupt-file recovery). The Firestore-fetching orchestration
function is not unit tested here — same precedent as get_financing_charges,
it needs a live Oanda/Firestore account to verify.
"""
from pathlib import Path

import pandas as pd
import pytest

from backend.app.services.trade_cache import (
    cache_path_for_email,
    compute_last_synced,
    dedupe_and_merge,
    load_cache,
    atomic_write_csv,
    frame_to_records,
)


# ── cache_path_for_email ─────────────────────────────────────────────────────
def test_cache_path_is_filename_safe(tmp_path):
    path = cache_path_for_email("naveenf.opt@gmail.com", tmp_path)
    assert "@" not in path.name
    assert path.suffix == ".csv"


def test_cache_path_is_stable_for_same_email(tmp_path):
    a = cache_path_for_email("user@example.com", tmp_path)
    b = cache_path_for_email("user@example.com", tmp_path)
    assert a == b


def test_cache_path_differs_for_different_emails(tmp_path):
    a = cache_path_for_email("alice@example.com", tmp_path)
    b = cache_path_for_email("bob@example.com", tmp_path)
    assert a != b


# ── compute_last_synced ──────────────────────────────────────────────────────
def test_last_synced_is_max_updated_at():
    df = pd.DataFrame({
        "_doc_id": ["a", "b"],
        "updated_at": pd.to_datetime(["2026-03-01T00:00:00Z", "2026-05-01T00:00:00Z"], utc=True),
    })
    assert compute_last_synced(df) == pd.Timestamp("2026-05-01T00:00:00Z")


def test_last_synced_is_none_for_empty_cache():
    df = pd.DataFrame({"_doc_id": [], "updated_at": pd.Series([], dtype="datetime64[ns, UTC]")})
    assert compute_last_synced(df) is None


def test_last_synced_is_none_when_updated_at_column_missing():
    df = pd.DataFrame({"_doc_id": ["a"], "symbol": ["XAU_USD"]})
    assert compute_last_synced(df) is None


# ── dedupe_and_merge ──────────────────────────────────────────────────────────
def test_merge_appends_new_trades():
    existing = pd.DataFrame({"_doc_id": ["a"], "pnl_aud": [10.0]})
    new = [{"_doc_id": "b", "pnl_aud": 20.0}]
    merged = dedupe_and_merge(existing, new)
    assert sorted(merged["_doc_id"].tolist()) == ["a", "b"]


def test_merge_overwrites_existing_trade_with_same_doc_id():
    """A trade already cached can be updated in Firestore later (e.g. close_type
    backfilled from UNKNOWN) — the cache must reflect the newer version, not
    keep two rows."""
    existing = pd.DataFrame({"_doc_id": ["a"], "close_type": ["UNKNOWN"]})
    new = [{"_doc_id": "a", "close_type": "SL"}]
    merged = dedupe_and_merge(existing, new)
    assert len(merged) == 1
    assert merged.iloc[0]["close_type"] == "SL"


def test_merge_with_no_updates_returns_existing_unchanged():
    existing = pd.DataFrame({"_doc_id": ["a"], "pnl_aud": [10.0]})
    merged = dedupe_and_merge(existing, [])
    assert len(merged) == 1
    assert merged.iloc[0]["pnl_aud"] == 10.0


def test_merge_into_empty_cache():
    existing = pd.DataFrame()
    new = [{"_doc_id": "a", "pnl_aud": 10.0}]
    merged = dedupe_and_merge(existing, new)
    assert len(merged) == 1


# ── load_cache / atomic_write_csv (real filesystem, no mocking) ─────────────
def test_load_cache_returns_empty_frame_when_file_missing(tmp_path):
    df = load_cache(tmp_path / "does_not_exist.csv")
    assert df.empty


def test_load_cache_returns_empty_frame_when_file_corrupt(tmp_path):
    path = tmp_path / "corrupt.csv"
    path.write_bytes(b"\x00\x01not,a,valid\ncsv\x02\x03file")
    df = load_cache(path)
    assert df.empty


def test_write_then_load_roundtrips_data(tmp_path):
    path = tmp_path / "trades.csv"
    original = pd.DataFrame({
        "_doc_id": ["a", "b"],
        "symbol": ["XAU_USD", "XAG_USD"],
        "pnl_aud": [10.5, -3.2],
        "updated_at": pd.to_datetime(["2026-03-01T00:00:00Z", "2026-05-01T00:00:00Z"], utc=True),
    })
    atomic_write_csv(original, path)
    loaded = load_cache(path)
    assert sorted(loaded["_doc_id"].tolist()) == ["a", "b"]
    assert loaded.set_index("_doc_id").loc["a", "pnl_aud"] == 10.5


def test_atomic_write_does_not_leave_temp_file_behind(tmp_path):
    path = tmp_path / "trades.csv"
    atomic_write_csv(pd.DataFrame({"_doc_id": ["a"]}), path)
    leftovers = [p for p in tmp_path.iterdir() if p.name != "trades.csv"]
    assert leftovers == []


# ── frame_to_records ──────────────────────────────────────────────────────────
def test_frame_to_records_converts_missing_values_to_none():
    """A field missing on some rows becomes NaN via pandas, not None — and
    downstream code does `if not sell_date_str: continue`, where NaN is
    truthy in Python and would slip through uncaught."""
    df = pd.DataFrame({"_doc_id": ["a", "b"], "close_type": ["SL", None]})
    records = frame_to_records(df)
    assert records[1]["close_type"] is None


def test_frame_to_records_on_empty_frame_returns_empty_list():
    assert frame_to_records(pd.DataFrame()) == []
