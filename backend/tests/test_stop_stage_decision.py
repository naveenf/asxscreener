"""Tests for the stop-move stage decision used by run_pair_lock_checks.

Covers the two mechanisms in production:
  - profit lock  (XAG_USD, BCO_USD): late trigger, moves SL into profit
  - breakeven    (JP225_USD):        early trigger, moves SL to a small loss
"""
import pytest

from backend.app.services.tasks import decide_stop_move

XAG   = {"lock_at_r": 3.0, "lock_to_r": 2.0, "cooldown_min": 25, "sl_precision": 3}
BCO   = {"lock_at_r": 2.0, "lock_to_r": 1.0, "cooldown_min": 90, "sl_precision": 3}
JP225 = {"be_at_r": 0.25, "be_to_r": -0.1, "sl_precision": 1}
BOTH  = {"be_at_r": 0.25, "be_to_r": -0.1,
         "lock_at_r": 3.0, "lock_to_r": 2.0, "cooldown_min": 25, "sl_precision": 3}


# ── profit lock ──────────────────────────────────────────────────────────────
def test_lock_fires_when_r_reaches_threshold():
    assert decide_stop_move(XAG, r_current=3.0, be_fired=False, lock_fired=False) == ("lock", 2.0)


def test_lock_does_not_fire_below_threshold():
    assert decide_stop_move(XAG, r_current=2.99, be_fired=False, lock_fired=False) is None


def test_lock_does_not_refire_once_fired():
    assert decide_stop_move(XAG, r_current=5.0, be_fired=False, lock_fired=True) is None


def test_pair_without_breakeven_stage_ignores_small_r():
    """XAG must never move to breakeven — that was shown to destroy its edge."""
    assert decide_stop_move(XAG, r_current=0.5, be_fired=False, lock_fired=False) is None


def test_bco_lock_uses_its_own_levels():
    assert decide_stop_move(BCO, r_current=2.0, be_fired=False, lock_fired=False) == ("lock", 1.0)


# ── breakeven ────────────────────────────────────────────────────────────────
def test_breakeven_fires_at_trigger():
    assert decide_stop_move(JP225, r_current=0.25, be_fired=False, lock_fired=False) == ("be", -0.1)


def test_breakeven_does_not_fire_below_trigger():
    assert decide_stop_move(JP225, r_current=0.24, be_fired=False, lock_fired=False) is None


def test_breakeven_does_not_refire_once_fired():
    assert decide_stop_move(JP225, r_current=1.0, be_fired=True, lock_fired=False) is None


def test_breakeven_pair_never_returns_lock_stage():
    """JP225 has no profit lock configured; a big move must not invent one."""
    assert decide_stop_move(JP225, r_current=9.0, be_fired=True, lock_fired=False) is None


def test_negative_r_moves_nothing():
    assert decide_stop_move(JP225, r_current=-0.5, be_fired=False, lock_fired=False) is None


# ── both stages configured ───────────────────────────────────────────────────
def test_lock_takes_precedence_over_breakeven_on_a_big_jump():
    """A candle that gaps past both thresholds must go straight to the lock."""
    assert decide_stop_move(BOTH, r_current=3.5, be_fired=False, lock_fired=False) == ("lock", 2.0)


def test_breakeven_fires_first_when_only_it_is_reached():
    assert decide_stop_move(BOTH, r_current=0.5, be_fired=False, lock_fired=False) == ("be", -0.1)


def test_lock_still_fires_after_breakeven_already_fired():
    assert decide_stop_move(BOTH, r_current=3.0, be_fired=True, lock_fired=False) == ("lock", 2.0)
