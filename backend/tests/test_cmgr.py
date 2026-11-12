"""Tests for compute_cmgr_pct: the constant monthly rate implied by a balance path."""

from datetime import date

import pytest

from backend.app.api.forex_portfolio import AVG_DAYS_PER_MONTH, compute_cmgr_pct


def _months_later(start: date, months: float) -> date:
    return date.fromordinal(start.toordinal() + round(months * AVG_DAYS_PER_MONTH))


START = date(2026, 3, 10)


def test_no_deposits_matches_plain_cagr_formula():
    end = _months_later(START, 12)
    months = (end - START).days / AVG_DAYS_PER_MONTH
    expected = (2 ** (1 / months) - 1) * 100

    assert compute_cmgr_pct(1000, 2000, START, end) == pytest.approx(expected, abs=1e-6)


def test_deposit_is_not_counted_as_growth():
    # The whole gain is the deposit itself, so the account earned nothing.
    end = _months_later(START, 8)
    deposits = [{"date": _months_later(START, 3), "amount": 1000.0}]

    assert compute_cmgr_pct(2503, 3503, START, end, deposits) == pytest.approx(0.0, abs=1e-6)


def test_rate_reproduces_ending_balance_when_compounded_with_deposit():
    end = _months_later(START, 8)
    deposit_date = _months_later(START, 3)
    deposits = [{"date": deposit_date, "amount": 1000.0}]

    rate = compute_cmgr_pct(2503, 5858, START, end, deposits) / 100

    months = (end - START).days / AVG_DAYS_PER_MONTH
    months_held = (end - deposit_date).days / AVG_DAYS_PER_MONTH
    rebuilt = 2503 * (1 + rate) ** months + 1000 * (1 + rate) ** months_held
    assert rebuilt == pytest.approx(5858, abs=0.01)


def test_earlier_deposit_implies_lower_rate_for_same_end_balance():
    # Money invested for longer had more time to earn the same profit.
    end = _months_later(START, 8)
    early = [{"date": _months_later(START, 1), "amount": 1000.0}]
    late = [{"date": _months_later(START, 7), "amount": 1000.0}]

    assert compute_cmgr_pct(2503, 5858, START, end, early) < compute_cmgr_pct(
        2503, 5858, START, end, late
    )


def test_withdrawal_is_added_back_rather_than_read_as_a_loss():
    # Flat account: the balance fell only because money was taken out.
    end = _months_later(START, 6)
    withdrawals = [{"date": _months_later(START, 3), "amount": -500.0}]

    assert compute_cmgr_pct(2000, 1500, START, end, withdrawals) == pytest.approx(0.0, abs=1e-6)


def test_losing_account_has_negative_rate():
    end = _months_later(START, 6)

    assert compute_cmgr_pct(2000, 1500, START, end) < 0


@pytest.mark.parametrize(
    "start_balance, end_balance",
    [(0, 1000), (-5, 1000), (None, 1000), (1000, 0), (1000, -1), (1000, None)],
)
def test_unusable_balances_return_none(start_balance, end_balance):
    end = _months_later(START, 6)

    assert compute_cmgr_pct(start_balance, end_balance, START, end) is None


def test_range_shorter_than_a_month_returns_none():
    # Scaling a few days of P&L up to a monthly rate would be noise.
    assert compute_cmgr_pct(1000, 1100, START, date(2026, 3, 20)) is None
