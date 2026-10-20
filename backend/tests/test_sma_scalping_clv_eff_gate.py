"""Tests for SmaScalpingDetector's Filter 11 (clv_min) and Filter 12 (eff_ratio_min).

Filter 11 is the CLV (Close Location Value) — Williams' Accumulation/Distribution
close-location term, identical to the Money Flow Multiplier inside Chaikin Money
Flow — averaged over `clv_period` bars (3 by default). Filter 12 is the Kaufman
Efficiency Ratio (fractal efficiency, the core term of KAMA) over `eff_period`
bars (10 by default).

Both are OPTIONAL and default to 0.0, which means OFF — not "require >= 0.0".
Both are SIGNED BY TRADE DIRECTION, and both FAIL CLOSED on a NaN value, in the
same spirit as Filter 10 (htf_trend_align) — see test_sma_scalping_htf_gate.py.
The vectorised ports in scripts/backtest_htf_direction_filter.py,
backtest_xag_walkforward_retune.py and backtest_max_hold_sweep.py must stay in
lockstep with the formulas asserted here.
"""
import numpy as np
import pandas as pd
import pytest
from backend.app.services.sma_scalping_detector import SmaScalpingDetector


# ---------------------------------------------------------------------------
# Fixtures: guaranteed-signal base series with controllable intrabar shape.
# `clv_tail` sets the close location within the range for the last 3 bars:
#  +1.0 = close on the high, 0.0 = midpoint, -1.0 = close on the low.
# ---------------------------------------------------------------------------
def _uptrend_df(n=150, clv_tail=1.0, half_range=0.05, freq="15min",
                end_time=pd.Timestamp("2026-06-01 12:00")):
    closes = [100.0 + i * 0.1 for i in range(n)]
    for i in range(10):
        closes[n - 10 + i] += i * 0.5
    highs = [c + half_range for c in closes]
    lows = [c - half_range for c in closes]
    # clv = (2C - H - L) / (H - L); shifting H and L by -clv_tail*half_range
    # around the close puts the close at the requested location in range.
    for i in range(n - 3, n):
        highs[i] = closes[i] + half_range * (1.0 - clv_tail)
        lows[i] = closes[i] - half_range * (1.0 + clv_tail)
    idx = pd.date_range(end=end_time, periods=n, freq=freq)
    return pd.DataFrame({"Open": [1.0] * n, "High": highs, "Low": lows,
                         "Close": closes, "Volume": [100] * n}, index=idx)


def _downtrend_df(n=150, clv_tail=-1.0, half_range=0.05, freq="15min",
                  end_time=pd.Timestamp("2026-06-01 12:00")):
    closes = [200.0 - i * 0.1 for i in range(n)]
    for i in range(10):
        closes[n - 10 + i] -= i * 0.5
    highs = [c + half_range for c in closes]
    lows = [c - half_range for c in closes]
    for i in range(n - 3, n):
        highs[i] = closes[i] + half_range * (1.0 - clv_tail)
        lows[i] = closes[i] - half_range * (1.0 + clv_tail)
    idx = pd.date_range(end=end_time, periods=n, freq=freq)
    return pd.DataFrame({"Open": [1.0] * n, "High": highs, "Low": lows,
                         "Close": closes, "Volume": [100] * n}, index=idx)


def _detector():
    return SmaScalpingDetector(di_threshold=30.0, rr=5.0)


def _analyze(params, df):
    return _detector().analyze({"base": df}, "TEST_PAIR", spread=0.0001, params=params)


BASE_PARAMS = {"di_threshold": 30.0}


# ---------------------------------------------------------------------------
# Formula parity — hand-computed clv3 / eff10 on a small fixed frame
# ---------------------------------------------------------------------------
def _ref_clv(df, period=3):
    h, l, c = df["High"], df["Low"], df["Close"]
    return (((2 * c - h - l) / (h - l).replace(0, np.nan))
            .rolling(period).mean().iloc[-1])


def _ref_eff(df, period=10):
    c = df["Close"]
    path = c.diff().abs().rolling(period).sum().replace(0, np.nan)
    return (c.diff(period) / path).iloc[-1]


def test_clv_formula_matches_hand_computed_values():
    """clv = (2C - H - L)/(H - L); clv3 = mean of the last 3."""
    df = pd.DataFrame({
        "High":  [10.0, 12.0, 14.0],
        "Low":   [8.0, 10.0, 10.0],
        "Close": [10.0, 11.0, 11.0],
    })
    # bar0: (20-10-8)/2 = +1.0  (closed on the high)
    # bar1: (22-12-10)/2 = 0.0  (midpoint)
    # bar2: (22-14-10)/4 = -0.5
    per_bar = [1.0, 0.0, -0.5]
    assert _ref_clv(df) == pytest.approx(sum(per_bar) / 3.0)
    assert _ref_clv(df) == pytest.approx(0.16666666666666666)


def test_eff_ratio_formula_matches_hand_computed_values():
    """eff = (C[i] - C[i-n]) / sum(|C.diff()|) over the last n diffs."""
    closes = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    df = pd.DataFrame({"Close": closes})
    # net = 8 - 0 = 8; path = 1*5 + 1 + 1 + 1 + 1 + 1 = 10 -> 0.8
    assert _ref_eff(df, 10) == pytest.approx(0.8)


def test_detector_clv_boundary_equals_reference_formula():
    """The detector's own threshold boundary sits exactly at the reference
    clv3 value, which both proves parity and the >= boundary at once."""
    df = _uptrend_df(clv_tail=0.6)
    clv3 = float(_ref_clv(df))
    assert clv3 == pytest.approx(0.6)
    assert _analyze({**BASE_PARAMS, "clv_min": clv3}, df) is not None          # >= passes
    assert _analyze({**BASE_PARAMS, "clv_min": clv3 + 1e-9}, df) is None       # > blocks


def test_detector_eff_boundary_equals_reference_formula():
    df = _uptrend_df(clv_tail=1.0)
    eff10 = float(_ref_eff(df))
    assert np.isfinite(eff10)
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": eff10}, df) is not None
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": eff10 + 1e-9}, df) is None


# ---------------------------------------------------------------------------
# Inertness — a pair that does not configure these params is unaffected
# ---------------------------------------------------------------------------
def test_filters_inert_when_params_absent():
    """A frame whose closes sit on the LOW of range (clv3 = -1, the worst
    possible value) must still signal when the params are not configured."""
    df = _uptrend_df(clv_tail=-1.0)
    assert _analyze(BASE_PARAMS, df) is not None
    assert _analyze(None, df) is not None


def test_filters_inert_produces_identical_result_to_explicit_zero():
    df = _uptrend_df(clv_tail=-1.0)
    bare = _analyze(BASE_PARAMS, df)
    zeros = _analyze({**BASE_PARAMS, "clv_min": 0.0, "eff_ratio_min": 0.0}, df)
    assert bare is not None and zeros is not None
    assert bare == zeros


def test_zero_threshold_means_off_not_require_ge_zero():
    """clv3 here is -1.0, so "require clv3 >= 0.0" would block. 0.0 must mean
    the filter is OFF (same precedent as body_ratio_min / atr_ratio_min)."""
    df = _uptrend_df(clv_tail=-1.0)
    assert float(_ref_clv(df)) == pytest.approx(-1.0)
    assert _analyze({**BASE_PARAMS, "clv_min": 0.0}, df) is not None
    # and the filter does bite once it is actually switched on
    assert _analyze({**BASE_PARAMS, "clv_min": 0.1}, df) is None


def test_zero_eff_threshold_means_off():
    """A perfectly zig-zag path has eff10 ~ 0 for a BUY; 0.0 must not gate."""
    df = _uptrend_df(clv_tail=1.0)
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 0.0}, df) is not None


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------
def test_clv_fails_closed_on_zero_range_bar_in_window():
    """A High == Low bar anywhere in the 3-bar window makes clv3 NaN, which
    must BLOCK — never silently permit."""
    df = _uptrend_df(clv_tail=1.0)
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5}, df) is not None
    for offset in (1, 2, 3):                       # each of the 3 window bars
        flat = df.copy()
        i = len(flat) - offset
        flat.iloc[i, flat.columns.get_loc("High")] = flat["Close"].iloc[i]
        flat.iloc[i, flat.columns.get_loc("Low")] = flat["Close"].iloc[i]
        assert _analyze({**BASE_PARAMS, "clv_min": 0.5}, flat) is None, offset


def test_clv_zero_range_bar_outside_window_does_not_block():
    """The window is only clv_period bars deep — a flat bar before it is
    irrelevant, which guards against an over-broad NaN check."""
    df = _uptrend_df(clv_tail=1.0)
    i = len(df) - 5
    df.iloc[i, df.columns.get_loc("High")] = df["Close"].iloc[i]
    df.iloc[i, df.columns.get_loc("Low")] = df["Close"].iloc[i]
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5}, df) is not None


def test_eff_fails_closed_on_zero_path_length():
    """A flat close path over the eff_period window gives 0/0 -> NaN, which
    must block. (Flat closes also kill the SMA stack, so this is asserted on
    the filter quantity itself plus a non-signal outcome.)"""
    df = _uptrend_df(clv_tail=1.0)
    flat = df.copy()
    last = float(flat["Close"].iloc[-1])
    flat.iloc[-11:, flat.columns.get_loc("Close")] = last
    assert pd.isna(_ref_eff(flat))
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 0.3}, flat) is None


def test_eff_fails_closed_when_frame_too_short_for_eff_period():
    """eff_period + 1 closes are required. 150 bars is plenty for n=10 but not
    for an absurd period — the gate must block rather than pass."""
    df = _uptrend_df(clv_tail=1.0)
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 0.2, "eff_period": 10}, df) is not None
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 0.2, "eff_period": 400}, df) is None


def test_clv_fails_closed_when_frame_too_short_for_clv_period():
    df = _uptrend_df(clv_tail=1.0)
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5, "clv_period": 400}, df) is None


# ---------------------------------------------------------------------------
# Direction signing — both directions, both ways
# ---------------------------------------------------------------------------
def test_clv_buy_passes_and_mirrored_sell_fails_on_high_closes():
    """clv3 = +1 (closes on the high): the BUY gate passes; the mirrored SELL
    setup with the SAME +1 close location must be blocked, because a short is
    tested on -clv3 = -1."""
    up = _uptrend_df(clv_tail=1.0)
    down = _downtrend_df(clv_tail=1.0)          # closes on the HIGH of range
    assert float(_ref_clv(up)) == pytest.approx(1.0)
    assert float(_ref_clv(down)) == pytest.approx(1.0)

    buy = _analyze({**BASE_PARAMS, "clv_min": 0.5}, up)
    assert buy is not None and buy["signal"] == "BUY"
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5}, down) is None


def test_clv_sell_passes_and_mirrored_buy_fails_on_low_closes():
    """The mirror image: clv3 = -1 (closes on the low) passes for a SELL and
    blocks the BUY."""
    up = _uptrend_df(clv_tail=-1.0)
    down = _downtrend_df(clv_tail=-1.0)
    assert float(_ref_clv(down)) == pytest.approx(-1.0)

    sell = _analyze({**BASE_PARAMS, "clv_min": 0.5}, down)
    assert sell is not None and sell["signal"] == "SELL"
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5}, up) is None


def test_eff_buy_passes_and_sell_blocked_on_net_upward_path():
    """A strongly up-trending close path has eff10 > 0: the BUY passes. The
    SELL side of the same quantity is -eff10 < 0 and is blocked."""
    up = _uptrend_df(clv_tail=1.0)
    assert float(_ref_eff(up)) > 0.3
    buy = _analyze({**BASE_PARAMS, "eff_ratio_min": 0.3}, up)
    assert buy is not None and buy["signal"] == "BUY"


def test_eff_sell_passes_on_net_downward_path():
    down = _downtrend_df(clv_tail=-1.0)
    assert float(_ref_eff(down)) < -0.3          # signed POSITIVE for a short
    sell = _analyze({**BASE_PARAMS, "eff_ratio_min": 0.3}, down)
    assert sell is not None and sell["signal"] == "SELL"
    # a threshold above the magnitude blocks it, confirming the sign flip is
    # a comparison and not an absolute value
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 1.01}, down) is None


def _sell_with_net_up_path(n=150, rally=0.04, half_range=0.05,
                           end_time=pd.Timestamp("2026-06-01 12:00")):
    """A genuine SELL setup (price under the whole SMA stack, DI- dominant)
    whose LAST 10 closes nevertheless travel net UPWARD — a retracement rally
    inside a downtrend. eff10 is then +1.0, so the SELL gate (-eff10 = -1.0)
    must block it."""
    closes = [200.0 - i * 0.5 for i in range(n)]
    base = closes[n - 11]
    for k in range(10):
        closes[n - 10 + k] = base + (k + 1) * rally
    highs = [c + half_range for c in closes]
    lows = [c - half_range for c in closes]
    for i in range(n - 3, n):                      # closes on the LOW of range
        highs[i] = closes[i] + 2 * half_range
        lows[i] = closes[i]
    idx = pd.date_range(end=end_time, periods=n, freq="15min")
    return pd.DataFrame({"Open": [1.0] * n, "High": highs, "Low": lows,
                         "Close": closes, "Volume": [100] * n}, index=idx)


def test_eff_sell_blocked_when_path_is_net_up():
    """The SELL side must require net DOWNWARD displacement, not merely a
    large |eff10|. This frame produces a real ungated SELL whose 10-bar path
    is net UP (eff10 = +1.0); the gate must block it."""
    df = _sell_with_net_up_path()
    assert float(_ref_eff(df)) == pytest.approx(1.0)      # net path is UP
    ungated = _analyze(BASE_PARAMS, df)
    assert ungated is not None and ungated["signal"] == "SELL"
    # -eff10 = -1.0, below any positive threshold -> blocked
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 0.1}, df) is None
    # ... and an absolute-value implementation would WRONGLY let it through
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": 0.9}, df) is None


# ---------------------------------------------------------------------------
# Custom periods are honoured
# ---------------------------------------------------------------------------
def test_clv_period_is_honoured():
    """With clv_period=1 only the signal bar counts. Make the signal bar
    close on the high but the two before it on the low: period 1 passes,
    period 3 (the default) does not."""
    df = _uptrend_df(clv_tail=-1.0)
    i = len(df) - 1
    df.iloc[i, df.columns.get_loc("High")] = float(df["Close"].iloc[i])
    df.iloc[i, df.columns.get_loc("Low")] = float(df["Close"].iloc[i]) - 0.1
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5, "clv_period": 1}, df) is not None
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5, "clv_period": 3}, df) is None


def test_eff_period_is_honoured():
    """Put a retracement inside the 10-bar window but outside the 5-bar one:
    the 10-bar path lengthens (eff10 < 1) while eff5 stays a straight line."""
    df = _uptrend_df(clv_tail=1.0)
    i = len(df) - 8
    df.iloc[i, df.columns.get_loc("Close")] -= 2.0
    e5, e10 = float(_ref_eff(df, 5)), float(_ref_eff(df, 10))
    assert e5 == pytest.approx(1.0)
    assert e10 < 0.9
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": e5, "eff_period": 5}, df) is not None
    assert _analyze({**BASE_PARAMS, "eff_ratio_min": e5 + 1e-9, "eff_period": 5}, df) is None


# ---------------------------------------------------------------------------
# Both filters together
# ---------------------------------------------------------------------------
def test_both_filters_and_together():
    df = _uptrend_df(clv_tail=1.0)
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5, "eff_ratio_min": 0.3}, df) is not None
    assert _analyze({**BASE_PARAMS, "clv_min": 1.5, "eff_ratio_min": 0.3}, df) is None
    assert _analyze({**BASE_PARAMS, "clv_min": 0.5, "eff_ratio_min": 1.5}, df) is None


def test_constructor_defaults_leave_both_filters_off():
    d = SmaScalpingDetector()
    assert d.clv_min == 0.0 and d.eff_ratio_min == 0.0
    assert d.clv_period == 3 and d.eff_period == 10
