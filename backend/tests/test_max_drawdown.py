"""Tests for max-drawdown on the analytics summary.

The previous version divided the peak-to-trough fall by a FIXED starting
balance, so drawdowns inflated as the account grew — a $1,347 dip on a $7,800
account reported as -63% instead of -17%, and live figures were not comparable
with the backtest scripts (which all use (equity - peak) / peak).
"""
import pytest

from backend.app.api.forex_portfolio import compute_max_drawdown_pct


# ── the shape the old code got wrong ─────────────────────────────────────────
def test_peak_to_trough_is_measured_against_the_peak_not_the_start():
    """3000 -> 9000 -> 7000. The fall is 2000 from a 9000 peak = -22.2%.

    The old formula divided by the 3000 starting balance and reported -66.7%.
    """
    dd = compute_max_drawdown_pct([6000.0, -2000.0], starting_balance=3000.0)
    assert dd == pytest.approx(-22.22, abs=0.01)


def test_growth_alone_is_not_a_drawdown():
    """3000 -> 9000 with no fall is a gain, not a -200% anything."""
    assert compute_max_drawdown_pct([6000.0], starting_balance=3000.0) == 0.0


def test_later_drawdowns_are_not_inflated_by_a_small_starting_balance():
    """A 1347 dip near a 7800 peak is ~-17%, regardless of a 2142 start."""
    pnl = [5658.0, -1347.0]      # 2142 -> 7800 -> 6453
    dd = compute_max_drawdown_pct(pnl, starting_balance=2142.0)
    assert dd == pytest.approx(-17.27, abs=0.05)


# ── basics ───────────────────────────────────────────────────────────────────
def test_no_trades_is_zero():
    assert compute_max_drawdown_pct([], starting_balance=1000.0) == 0.0


def test_monotonic_gains_give_zero_drawdown():
    assert compute_max_drawdown_pct([100.0, 200.0, 50.0], starting_balance=1000.0) == 0.0


def test_immediate_loss_from_the_starting_balance_counts():
    """Starting balance is the first peak — a loss on trade 1 is a real drawdown."""
    dd = compute_max_drawdown_pct([-100.0], starting_balance=1000.0)
    assert dd == pytest.approx(-10.0, abs=0.01)


def test_worst_of_several_drawdowns_wins():
    # 1000 -> 900 (-10%) -> 1400 -> 980 (-30% from 1400)
    dd = compute_max_drawdown_pct([-100.0, 500.0, -420.0], starting_balance=1000.0)
    assert dd == pytest.approx(-30.0, abs=0.01)


def test_recovery_does_not_erase_the_recorded_drawdown():
    dd = compute_max_drawdown_pct([-500.0, 5000.0], starting_balance=1000.0)
    assert dd == pytest.approx(-50.0, abs=0.01)


def test_zero_or_missing_starting_balance_is_zero_not_a_crash():
    assert compute_max_drawdown_pct([-100.0], starting_balance=0) == 0.0
    assert compute_max_drawdown_pct([-100.0], starting_balance=None) == 0.0


# ── deposits ─────────────────────────────────────────────────────────────────
def test_deposit_is_not_counted_as_a_recovery():
    """1000 -> 500 (-50%). A 500 deposit restores equity but the account did
    NOT recover — the drawdown must stand at -50%."""
    dd = compute_max_drawdown_pct([-500.0], starting_balance=1000.0, deposits=[(0, 500.0)])
    assert dd == pytest.approx(-50.0, abs=0.01)


def test_deposit_raises_the_base_for_later_drawdowns():
    """After a 1000 deposit the account is 2000; a 200 loss is -10%, not -20%."""
    dd = compute_max_drawdown_pct(
        [0.0, -200.0], starting_balance=1000.0, deposits=[(0, 1000.0)]
    )
    assert dd == pytest.approx(-10.0, abs=0.01)


def test_multiple_deposits_accumulate():
    dd = compute_max_drawdown_pct(
        [0.0, 0.0, -300.0], starting_balance=1000.0,
        deposits=[(0, 1000.0), (1, 1000.0)],
    )
    assert dd == pytest.approx(-10.0, abs=0.01)


def test_no_deposits_argument_behaves_like_empty():
    pnl = [-100.0, 50.0]
    assert compute_max_drawdown_pct(pnl, 1000.0) == compute_max_drawdown_pct(pnl, 1000.0, deposits=[])


def test_deposit_before_any_trade_uses_index_minus_one():
    """The endpoint maps a pre-first-trade deposit to index -1; it must not
    silently attach to the last trade instead."""
    dd = compute_max_drawdown_pct([-200.0], starting_balance=1000.0, deposits=[(-1, 1000.0)])
    # deposit at -1 is never applied inside the loop, so base stays 1000 -> -20%
    assert dd == pytest.approx(-20.0, abs=0.01)
