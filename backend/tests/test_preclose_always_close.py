"""Tests for the ALWAYS_CLOSE_PAIRS override in run_preclose_check.

The global holiday_close_enabled toggle defers ordinary pre-close flattening so
positions can be carried through a holiday. BCO_USD must close regardless: its
weekend gaps run 2.73 ATR at the median against a 1xATR stop floor, so a broker
stop cannot protect a position across the Sunday re-open.
"""
from backend.app.services.tasks import ALWAYS_CLOSE_PAIRS, pairs_to_close_now

ALL = {"BCO_USD", "XAU_USD", "EUR_USD"}


# ── toggle on: normal behaviour ──────────────────────────────────────────────
def test_toggle_on_closes_everything_in_the_window():
    assert pairs_to_close_now(ALL, holiday_close_enabled=True) == ALL


def test_toggle_on_with_empty_window_closes_nothing():
    assert pairs_to_close_now(set(), holiday_close_enabled=True) == set()


# ── toggle off: only the forced pairs close ──────────────────────────────────
def test_toggle_off_still_closes_bco():
    assert pairs_to_close_now(ALL, holiday_close_enabled=False) == {"BCO_USD"}


def test_toggle_off_defers_other_pairs():
    result = pairs_to_close_now(ALL, holiday_close_enabled=False)
    assert "XAU_USD" not in result
    assert "EUR_USD" not in result


def test_toggle_off_closes_nothing_when_bco_not_in_window():
    """BCO is only forced when it is actually in the close phase."""
    assert pairs_to_close_now({"XAU_USD", "EUR_USD"}, holiday_close_enabled=False) == set()


# ── config ───────────────────────────────────────────────────────────────────
def test_bco_is_the_only_forced_pair():
    """Guards against extending this on gap size alone — see the config comment."""
    assert ALWAYS_CLOSE_PAIRS == {"BCO_USD"}


def test_always_close_list_is_injectable_for_testing():
    assert pairs_to_close_now(ALL, holiday_close_enabled=False,
                              always_close_pairs={"XAU_USD"}) == {"XAU_USD"}


# ── the returned set must not alias the caller's ─────────────────────────────
def test_result_is_a_new_set():
    """run_preclose_check does `close_pairs - closing`; aliasing would corrupt it."""
    close_pairs = {"BCO_USD", "XAU_USD"}
    result = pairs_to_close_now(close_pairs, holiday_close_enabled=True)
    result.add("SENTINEL")
    assert "SENTINEL" not in close_pairs
