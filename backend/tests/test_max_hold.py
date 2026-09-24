"""Tests for the max-hold time stop (decide_max_hold_close / max_hold_days_for).

A SmaScalping entry is built from 15m structure but nothing bounded how long the
resulting trade could run — XAU_USD has a measured 132-day hold, and because
oanda_trade_service enforces one position per pair, such a trade locks the pair
out for its whole duration.

The decision function must fail CLOSED in the safe direction: anything it cannot
establish the age of is left alone rather than force-closed. The timezone cases
are load-bearing — _log_to_portfolio writes created_at with datetime.utcnow(),
which is NAIVE, while the Firestore client hands the field back timezone-AWARE.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.services.tasks import (
    PAIR_MAX_HOLD_DAYS,
    _update_firestore_closed,
    classify_close_outcome,
    decide_max_hold_close,
    extract_close_fill,
    max_hold_days_for,
)

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)


# ── the basic threshold ──────────────────────────────────────────────────────
def test_trade_younger_than_cap_is_left_open():
    assert decide_max_hold_close(NOW - timedelta(days=6, hours=23), NOW, 7) is False


def test_trade_exactly_at_cap_closes():
    """Boundary is inclusive — at exactly 7 days the trade is closed."""
    assert decide_max_hold_close(NOW - timedelta(days=7), NOW, 7) is True


def test_trade_older_than_cap_closes():
    assert decide_max_hold_close(NOW - timedelta(days=132), NOW, 7) is True


def test_brand_new_trade_is_left_open():
    assert decide_max_hold_close(NOW, NOW, 7) is False


# ── timezone handling: naive created_at vs aware now ─────────────────────────
def test_naive_entry_time_is_treated_as_utc():
    """_log_to_portfolio writes datetime.utcnow() — naive. Must not raise."""
    naive_entry = datetime(2026, 9, 10, 12, 0)          # 14 days before NOW
    assert decide_max_hold_close(naive_entry, NOW, 7) is True


def test_naive_entry_time_below_cap_is_left_open():
    naive_entry = datetime(2026, 9, 23, 12, 0)          # 1 day before NOW
    assert decide_max_hold_close(naive_entry, NOW, 7) is False


def test_naive_now_is_treated_as_utc():
    aware_entry = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    naive_now = datetime(2026, 9, 24, 12, 0)
    assert decide_max_hold_close(aware_entry, naive_now, 7) is True


def test_mixed_awareness_never_raises_typeerror():
    """The naive/aware mix is the one that would blow up at runtime.

    Both orderings must return a bool rather than raise. The reversed ordering
    puts the entry AFTER now, so the future-entry guard returns False — that is
    the correct answer, not a comparison failure.
    """
    naive = datetime(2026, 9, 1, 12, 0)
    aware = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
    assert decide_max_hold_close(naive, aware, 7) is True
    assert decide_max_hold_close(aware, naive, 7) is False


def test_non_utc_timezone_is_compared_correctly():
    """An aware timestamp in another zone must not be shifted twice."""
    tz = timezone(timedelta(hours=10))
    entry = datetime(2026, 9, 24, 12, 0, tzinfo=tz)      # = 02:00 UTC, 10h ago
    assert decide_max_hold_close(entry, NOW, 7) is False


# ── fail-closed: unknown or nonsensical age is never force-closed ────────────
def test_missing_created_at_is_never_closed():
    """183 legacy docs predate the signal_* fields; treat unknown age as safe."""
    assert decide_max_hold_close(None, NOW, 7) is False


def test_missing_now_is_never_closed():
    assert decide_max_hold_close(NOW - timedelta(days=99), None, 7) is False


def test_non_datetime_created_at_is_never_closed():
    """A string/Timestamp-like value must not be coerced or crash the job."""
    assert decide_max_hold_close("2026-09-01", NOW, 7) is False
    assert decide_max_hold_close(1758700000, NOW, 7) is False


def test_future_entry_time_is_never_closed():
    """Clock skew must not instantly close a fresh trade."""
    assert decide_max_hold_close(NOW + timedelta(days=1), NOW, 7) is False


# ── the cap value itself disables cleanly ────────────────────────────────────
def test_none_cap_disables():
    assert decide_max_hold_close(NOW - timedelta(days=500), NOW, None) is False


def test_zero_cap_disables():
    """0 means 'off', not 'close everything immediately'."""
    assert decide_max_hold_close(NOW - timedelta(days=500), NOW, 0) is False


def test_negative_cap_disables():
    assert decide_max_hold_close(NOW - timedelta(days=500), NOW, -1) is False


# ── per-pair lookup ──────────────────────────────────────────────────────────
def test_uncapped_pair_returns_none():
    assert max_hold_days_for("EUR_USD", configs={"XAU_USD": 7}) is None


def test_capped_pair_returns_its_value():
    assert max_hold_days_for("XAU_USD", configs={"XAU_USD": 7}) == 7


def test_lookup_defaults_to_module_config():
    assert max_hold_days_for("XAU_USD") == 7


@pytest.mark.parametrize("pair", ["XAU_USD", "XAG_USD", "NAS100_USD", "BCO_USD", "JP225_USD"])
def test_all_active_pairs_are_capped_at_seven_days(pair):
    """7d was the expectancy-neutral cell (XAU paired dR +0.005R, t=0.18).
    3d and 5d scored higher on ROI but had negative paired estimates — if this
    is ever retuned, re-read the config comment before picking a shorter cap."""
    assert PAIR_MAX_HOLD_DAYS[pair] == 7


def test_disabled_pairs_are_not_capped():
    """EUR_USD / USD_JPY / UK100_GBP are off at runtime; no cap entry for them."""
    for pair in ("EUR_USD", "USD_JPY", "UK100_GBP"):
        assert pair not in PAIR_MAX_HOLD_DAYS


# ─────────────────────────────────────────────────────────────────────────────
# classify_close_outcome — the branch that decides whether a LIVE position gets
# marked CLOSED. Getting this wrong hides a real position from the stop-move
# stages and from ALWAYS_CLOSE_PAIRS weekend flattening, so it fails closed.
# ─────────────────────────────────────────────────────────────────────────────
def test_successful_close_is_closed():
    assert classify_close_outcome({"orderFillTransaction": {"pl": "12.5"}}, None) == "closed"


def test_rejection_is_rejected_not_closed():
    result = {"orderRejectTransaction": {"rejectReason": "MARKET_HALTED"}}
    assert classify_close_outcome(result, None) == "rejected"


def test_rejection_wins_over_a_fill_in_the_same_response():
    result = {"orderRejectTransaction": {"rejectReason": "X"}, "orderFillTransaction": {}}
    assert classify_close_outcome(result, None) == "rejected"


def test_none_result_with_closed_details_is_already_closed():
    """404 from close_trade + state CLOSED = the trade hit TP/SL first."""
    assert classify_close_outcome(None, {"state": "CLOSED"}) == "already_closed"


def test_none_result_with_open_details_is_still_open():
    assert classify_close_outcome(None, {"state": "OPEN"}) == "still_open"


def test_none_result_with_unknown_details_is_still_open():
    """A dict with no state is not positive confirmation of closure."""
    assert classify_close_outcome(None, {}) == "still_open"


def test_both_none_is_indeterminate_never_already_closed():
    """THE dangerous case: get_trade_details also returns None on API failure,
    so None must never be read as 'already closed' — that would mark a LIVE
    position CLOSED and hide it from every job that queries status == OPEN."""
    assert classify_close_outcome(None, None) == "indeterminate"


@pytest.mark.parametrize("outcome", ["rejected", "still_open", "indeterminate"])
def test_non_confirmed_outcomes_are_not_treated_as_closed(outcome):
    """Guard: only 'closed' and 'already_closed' may ever write CLOSED."""
    assert outcome not in ("closed", "already_closed")


# ─────────────────────────────────────────────────────────────────────────────
# extract_close_fill — without these a max-hold close books a $0 P&L trade,
# because _sync_oanda_closed_trades only repairs docs whose status is OPEN.
# ─────────────────────────────────────────────────────────────────────────────
def test_fill_read_from_trades_closed():
    result = {"orderFillTransaction": {
        "price": "1.0", "pl": "9.9",
        "tradesClosed": [{"price": "4321.5", "realizedPL": "123.45"}]}}
    assert extract_close_fill(result) == (4321.5, 123.45)


def test_fill_falls_back_to_top_level_when_no_trades_closed():
    result = {"orderFillTransaction": {"price": "4321.5", "pl": "123.45"}}
    assert extract_close_fill(result) == (4321.5, 123.45)


def test_fill_falls_back_to_trade_details():
    details = {"averageClosePrice": "99.5", "realizedPL": "-12.0"}
    assert extract_close_fill(None, details) == (99.5, -12.0)


def test_fill_returns_none_when_nothing_available():
    assert extract_close_fill(None, None) == (None, None)
    assert extract_close_fill({}, {}) == (None, None)


def test_fill_tolerates_unparseable_values():
    """Must degrade to None rather than raise inside the close loop."""
    result = {"orderFillTransaction": {"price": "not-a-number", "pl": None}}
    assert extract_close_fill(result) == (None, None)


def test_negative_pnl_is_preserved():
    result = {"orderFillTransaction": {"tradesClosed": [{"price": "10", "realizedPL": "-50.25"}]}}
    assert extract_close_fill(result) == (10.0, -50.25)


def test_zero_pnl_is_preserved_not_dropped():
    """0.0 is a real P&L; it must not be confused with 'missing'."""
    result = {"orderFillTransaction": {"tradesClosed": [{"price": "10", "realizedPL": "0"}]}}
    assert extract_close_fill(result) == (10.0, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# _update_firestore_closed — the write payload itself
# ─────────────────────────────────────────────────────────────────────────────
class _FakeDocRef:
    def __init__(self):
        self.id = "doc123"
        self.payload = None

    def update(self, payload):
        self.payload = payload


def test_write_always_sets_updated_at():
    """The delta-sync invariant: a doc written without updated_at is skipped by
    where('updated_at','>',cursor) permanently. See test_trade_doc_updated_at."""
    ref = _FakeDocRef()
    _update_firestore_closed(ref, "2026-09-24", NOW, reason="x")
    assert "updated_at" in ref.payload
    assert isinstance(ref.payload["updated_at"], datetime)


def test_updated_at_is_stamped_at_write_time_not_job_start():
    """A job that retries Oanda for minutes must not back-date its write below
    a cursor another writer has already advanced past."""
    ref = _FakeDocRef()
    stale = datetime(2020, 1, 1, tzinfo=timezone.utc)
    _update_firestore_closed(ref, "2026-09-24", stale, reason="x")
    assert ref.payload["updated_at"] > stale


def test_defaults_preserve_preclose_behaviour():
    """Backward compatibility for the three existing call sites."""
    ref = _FakeDocRef()
    _update_firestore_closed(ref, "2026-09-24", NOW, reason="pre_close", existing_notes="n")
    assert ref.payload["close_type"] == "PRE_CLOSE"
    assert ref.payload["notes"] == "n | Pre-close: pre_close"
    assert ref.payload["status"] == "CLOSED"


def test_max_hold_close_type_and_extra_fields_propagate():
    ref = _FakeDocRef()
    _update_firestore_closed(ref, "2026-09-24", NOW, reason="held ≥ 7d",
                             close_type="MAX_HOLD", label="Max-hold",
                             extra_fields={"sell_price": 4321.5, "pnl": 12.0,
                                           "closed_by": "MaxHold"})
    assert ref.payload["close_type"] == "MAX_HOLD"
    assert ref.payload["sell_price"] == 4321.5
    assert ref.payload["pnl"] == 12.0
    assert ref.payload["closed_by"] == "MaxHold"
    assert "Max-hold" in ref.payload["notes"]


def test_extra_fields_cannot_drop_updated_at():
    ref = _FakeDocRef()
    _update_firestore_closed(ref, "2026-09-24", NOW, reason="x",
                             extra_fields={"sell_price": 1.0})
    assert "updated_at" in ref.payload


# ─────────────────────────────────────────────────────────────────────────────
# Firestore datetime subclass (DatetimeWithNanoseconds) — the isinstance gate
# in decide_max_hold_close depends on this being a datetime subclass.
# ─────────────────────────────────────────────────────────────────────────────
class _DatetimeWithNanoseconds(datetime):
    """Stand-in for google.api_core.datetime_helpers.DatetimeWithNanoseconds."""


def test_firestore_datetime_subclass_is_accepted():
    entry = _DatetimeWithNanoseconds(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    assert decide_max_hold_close(entry, NOW, 7) is True


def test_firestore_datetime_subclass_naive_is_accepted():
    entry = _DatetimeWithNanoseconds(2026, 9, 1, 12, 0)
    assert decide_max_hold_close(entry, NOW, 7) is True
