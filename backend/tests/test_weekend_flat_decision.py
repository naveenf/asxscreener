"""Tests for the weekend-flat window used by run_weekend_flat_checks.

BCO_USD is flattened and blocked from Friday 19:00 UTC until the market
reopens, so no position carries the Sunday re-open gap. 19:00 UTC is chosen to
sit clear of the close in both DST regimes (close is 21:00 UTC under EDT,
22:00 UTC under EST), so these tests pin the behaviour either side of that hour
as well as across the whole weekend.
"""
from datetime import datetime, timezone

from backend.app.services.tasks import should_flatten_for_weekend

BCO = {"friday_utc_hour": 19}


def utc(y, m, d, h):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


# ── Friday cutoff ────────────────────────────────────────────────────────────
def test_friday_before_cutoff_stays_open():
    # 2026-08-21 is a Friday
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 21, 18)) is False


def test_friday_at_cutoff_flattens():
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 21, 19)) is True


def test_friday_after_cutoff_flattens():
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 21, 23)) is True


def test_friday_cutoff_clears_the_close_in_both_dst_regimes():
    """Close is 21:00 UTC under EDT and 22:00 UTC under EST; 19:00 precedes both."""
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 21, 20)) is True   # EDT, 1h pre-close
    assert should_flatten_for_weekend(BCO, utc(2026, 1, 16, 21)) is True   # EST, 1h pre-close


# ── weekend body ─────────────────────────────────────────────────────────────
def test_saturday_is_blocked():
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 22, 12)) is True


def test_sunday_is_blocked_through_the_reopen_hour():
    """FX reopens 22:00-23:00 UTC Sunday; stay blocked rather than enter the gap."""
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 23, 23)) is True


# ── weekdays ─────────────────────────────────────────────────────────────────
def test_monday_trades_normally():
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 24, 0)) is False


def test_midweek_late_hour_is_not_a_weekend():
    """Thursday 23:00 is past the Friday cutoff hour but is not the weekend."""
    assert should_flatten_for_weekend(BCO, utc(2026, 8, 20, 23)) is False


# ── pairs without the config ─────────────────────────────────────────────────
def test_pair_without_config_is_never_flattened():
    assert should_flatten_for_weekend(None, utc(2026, 8, 22, 12)) is False
    assert should_flatten_for_weekend({}, utc(2026, 8, 22, 12)) is False
