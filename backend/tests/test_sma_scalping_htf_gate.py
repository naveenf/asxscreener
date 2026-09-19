"""Tests for SmaScalpingDetector's Filter 10 (htf_trend_align).

Covers the property that matters most for a live filter reading a second
timeframe: no lookahead. HTF rows are stored by OPEN time (download_forex.py
convention), so a bar only becomes usable once its own close (open + its
granularity) has passed — see the "Filter 10" comment in
sma_scalping_detector.py and scripts/backtest_htf_direction_filter.py's
htf_trend()/attach_htf(), which this mirrors.
"""
import pandas as pd
import pytest
from backend.app.services.sma_scalping_detector import SmaScalpingDetector


def _base_uptrend_df(end_time, n=150, freq="15min"):
    """Guaranteed-BUY-signal base series (mirrors test_sma_scalping_detector.py's
    uptrend fixture), ending exactly at `end_time`."""
    base_price = 100.0
    closes = [base_price + i * 0.1 for i in range(n)]
    for i in range(10):
        closes[n - 10 + i] += i * 0.5
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]
    idx = pd.date_range(end=end_time, periods=n, freq=freq)
    return pd.DataFrame({"Open": [1.0] * n, "High": highs, "Low": lows,
                          "Close": closes, "Volume": [100] * n}, index=idx)


def _base_downtrend_df(end_time, n=150, freq="15min"):
    """Guaranteed-SELL-signal base series, ending exactly at `end_time`."""
    base_price = 200.0
    closes = [base_price - i * 0.1 for i in range(n)]
    for i in range(10):
        closes[n - 10 + i] -= i * 0.5
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]
    idx = pd.date_range(end=end_time, periods=n, freq=freq)
    return pd.DataFrame({"Open": [1.0] * n, "High": highs, "Low": lows,
                          "Close": closes, "Volume": [100] * n}, index=idx)


def _htf_df(n_flat=50, last_two_closes=(110.0, 50.0), freq="4h", start="2023-06-01"):
    """n_flat flat bars at 100.0, then two more. Index -2 is the bar meant to
    represent the last one FULLY CLOSED as of the base candle under test;
    index -1 is still forming and must never be read."""
    n = n_flat + 2
    closes = [100.0] * n_flat + list(last_two_closes)
    idx = pd.date_range(start=start, periods=n, freq=freq)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                          "Close": closes, "Volume": [100] * n}, index=idx)


def _base_ending_after_htf_close(htf, hours_after_second_last_open=5):
    """A base candle whose own close lands `hours_after_second_last_open` hours
    after htf.index[-2] opened — comfortably past that bar's 4h close, but
    (with the default of 5h, against a 4h htf granularity) before htf.index[-1]
    (which opens 4h later and so closes 4h after that) has closed."""
    second_last_open = htf.index[-2]
    base_close = second_last_open + pd.Timedelta(hours=hours_after_second_last_open)
    return base_close - pd.Timedelta(minutes=15)


@pytest.fixture
def gated_detector():
    return SmaScalpingDetector(di_threshold=30.0, rr=5.0, htf_trend_align=True)


def test_htf_gate_allows_buy_and_ignores_still_forming_bar(gated_detector):
    """The last HTF bar (DOWN) hasn't closed yet; only the second-last (UP) has.
    If the gate read the still-forming bar instead, this BUY would be wrongly
    blocked."""
    htf = _htf_df(last_two_closes=(110.0, 50.0))
    base = _base_uptrend_df(end_time=_base_ending_after_htf_close(htf))

    signal = gated_detector.analyze({"base": base, "htf_trend": htf}, "TEST_PAIR", spread=0.0001)
    assert signal is not None
    assert signal["signal"] == "BUY"


def test_htf_gate_blocks_buy_when_htf_trend_down(gated_detector):
    htf = _htf_df(last_two_closes=(50.0, 110.0))  # last CLOSED bar is DOWN
    base = _base_uptrend_df(end_time=_base_ending_after_htf_close(htf))

    signal = gated_detector.analyze({"base": base, "htf_trend": htf}, "TEST_PAIR", spread=0.0001)
    assert signal is None


def test_htf_gate_blocks_sell_when_htf_trend_up(gated_detector):
    htf = _htf_df(last_two_closes=(110.0, 50.0))  # last CLOSED bar is UP
    base = _base_downtrend_df(end_time=_base_ending_after_htf_close(htf))

    signal = gated_detector.analyze({"base": base, "htf_trend": htf}, "TEST_PAIR", spread=0.0001)
    assert signal is None


def test_htf_gate_allows_sell_when_htf_trend_down(gated_detector):
    htf = _htf_df(last_two_closes=(50.0, 110.0))  # last CLOSED bar is DOWN
    base = _base_downtrend_df(end_time=_base_ending_after_htf_close(htf))

    signal = gated_detector.analyze({"base": base, "htf_trend": htf}, "TEST_PAIR", spread=0.0001)
    assert signal is not None
    assert signal["signal"] == "SELL"


def test_htf_gate_fails_closed_on_missing_htf_data(gated_detector):
    base = _base_uptrend_df(end_time=pd.Timestamp("2023-06-10"))
    signal = gated_detector.analyze({"base": base}, "TEST_PAIR", spread=0.0001)
    assert signal is None


def test_htf_gate_fails_closed_on_thin_htf_data(gated_detector):
    base = _base_uptrend_df(end_time=pd.Timestamp("2023-06-10"))
    thin_htf = _htf_df(n_flat=10, last_two_closes=(110.0, 50.0))  # well under the 51-row floor
    signal = gated_detector.analyze({"base": base, "htf_trend": thin_htf}, "TEST_PAIR", spread=0.0001)
    assert signal is None


def test_htf_gate_off_by_default_ignores_htf_data():
    """htf_trend_align defaults False, so a pair without it configured must be
    unaffected even if data['htf_trend'] happens to be populated."""
    detector = SmaScalpingDetector(di_threshold=30.0, rr=5.0)  # htf_trend_align not set
    htf = _htf_df(last_two_closes=(50.0, 110.0))  # would block this BUY if the gate were active
    base = _base_uptrend_df(end_time=_base_ending_after_htf_close(htf))

    signal = detector.analyze({"base": base, "htf_trend": htf}, "TEST_PAIR", spread=0.0001)
    assert signal is not None
    assert signal["signal"] == "BUY"
