import pandas as pd
import pytest
from datetime import datetime, timedelta
from backend.app.services.new_breakout_detector import NewBreakoutDetector
from backend.app.services.indicators import TechnicalIndicators # To ensure indicators are calculated

# Dummy data for testing
@pytest.fixture
def dummy_data():
    # Timestamps must end at "now" so the candle freshness check (10-min limit) passes
    now = pd.Timestamp.now().floor('min')
    end_15m = now
    start_15m = end_15m - pd.Timedelta(minutes=15 * 249)
    end_4h = now
    start_4h = end_4h - pd.Timedelta(hours=4 * 49)  # 50 candles, need >= 34 for EMA34

    # 15m data - create a series of closes that can show breakout
    data_15m = {
        'Date': pd.date_range(start=start_15m, end=end_15m, periods=250),
        'Open': [100 + i*0.05 for i in range(250)],
        'High': [100.1 + i*0.05 for i in range(250)],
        'Low': [99.9 + i*0.05 for i in range(250)],
        'Close': [100 + i*0.05 for i in range(250)],
        'Volume': [1000 + i for i in range(250)]
    }
    df_15m = pd.DataFrame(data_15m).set_index('Date')

    # 4h data - strongly bullish trend to guarantee ADX, DI+, EMA conditions are met
    # Need >= 34 candles: max(ema_period=34, rsi_period=14, 20) = 34
    data_4h = {
        'Date': pd.date_range(start=start_4h, end=end_4h, periods=50),
        'Open': [100 + i*10 for i in range(50)],
        'High': [102 + i*10 for i in range(50)],
        'Low': [98 + i*10 for i in range(50)],
        'Close': [101 + i*10 for i in range(50)],
        'Volume': [5000 + i*10 for i in range(50)]
    }
    df_4h = pd.DataFrame(data_4h).set_index('Date')

    return {
        'base': df_15m,
        'htf': df_4h
    }

def test_new_breakout_detector_get_name():
    detector = NewBreakoutDetector()
    assert detector.get_name() == "NewBreakout"

def test_new_breakout_detector_analyze_no_signal(dummy_data):
    detector = NewBreakoutDetector(adx_threshold=50) # Set high ADX to reduce signals
    symbol = "TEST_PAIR"
    
    df_15m = dummy_data['base'].copy() # Work on a copy
    df_4h = dummy_data['htf'].copy()   # Work on a copy

    # Add all indicators to both dataframes within the test context
    df_15m = TechnicalIndicators.add_all_indicators(df_15m)
    df_4h = TechnicalIndicators.add_all_indicators(df_4h)
    
    # Example: Create a scenario where ADX is too low for HTF trend
    df_4h.loc[df_4h.index[-1], 'ADX'] = 10 # Force low ADX
    df_4h.loc[df_4h.index[-2], 'ADX'] = 9 # Force low ADX

    # Pass the modified dataframes to the detector
    modified_dummy_data = {'base': df_15m, 'htf': df_4h}
    result = detector.analyze(modified_dummy_data, symbol, target_rr=2.0)
    assert result is None

def test_new_breakout_detector_analyze_buy_signal(dummy_data):
    symbol = "TEST_PAIR"
    sr_lookback = 20

    # Timestamps must end at "now" so the candle freshness check (10-min limit) passes
    now = pd.Timestamp.now().floor('min')

    # --- Setup df_4h for a clear bullish trend ---
    # Need >= 34 candles: max(ema_period=34, rsi_period=14, 20) = 34
    num_candles_4h = 50
    closes_4h = [100.0 + i * 5 for i in range(num_candles_4h)]
    highs_4h = [c + 2 for c in closes_4h]
    lows_4h = [c - 2 for c in closes_4h]
    end_4h = now
    start_4h = end_4h - pd.Timedelta(hours=4 * (num_candles_4h - 1))
    df_4h_raw = pd.DataFrame({
        'Date': pd.date_range(start=start_4h, end=end_4h, periods=num_candles_4h),
        'Open': [c - 1 for c in closes_4h],
        'High': highs_4h,
        'Low': lows_4h,
        'Close': closes_4h,
        'Volume': [1000] * num_candles_4h
    }).set_index('Date')
    df_4h = TechnicalIndicators.add_all_indicators(df_4h_raw.copy()) # Process with indicators

    # --- Setup df_15m for a clear breakout ---
    num_candles_15m = 250
    closes_15m_base = [100.0] * (num_candles_15m - 2)
    highs_15m_base = [c + 0.1 for c in closes_15m_base]
    lows_15m_base = [c - 0.1 for c in closes_15m_base]

    recent_high_val = 105.0 # Define a specific recent high to break
    # Place a high value before the last few candles to be the "recent_high"
    highs_15m_base[-sr_lookback + 5] = recent_high_val + 0.5 # Ensure a high point exists

    # Ensure previous candle was below or at recent_high, and current breaks it
    prev_close = recent_high_val - 0.1
    current_close = recent_high_val + 1.0

    closes_15m = closes_15m_base + [prev_close, current_close]
    highs_15m = [c + 0.1 for c in closes_15m]
    lows_15m = [c - 0.1 for c in closes_15m]

    end_15m = now
    start_15m = end_15m - pd.Timedelta(minutes=15 * (len(closes_15m) - 1))
    df_15m_raw = pd.DataFrame({
        'Date': pd.date_range(start=start_15m, end=end_15m, periods=len(closes_15m)),
        'Open': [c - 0.05 for c in closes_15m],
        'High': highs_15m,
        'Low': lows_15m,
        'Close': closes_15m,
        'Volume': [1000] * len(closes_15m)
    }).set_index('Date')
    df_15m = TechnicalIndicators.add_all_indicators(df_15m_raw.copy()) # Process with indicators

    # Manually ensure the last two closes reflect the breakout over the *calculated* recent high
    # We find the recent_high from the processed dataframe, then ensure the last two closes break it.
    calculated_recent_high = df_15m['High'].iloc[-sr_lookback:-1].max()
    df_15m.loc[df_15m.index[-1], 'Close'] = calculated_recent_high + 1.0
    df_15m.loc[df_15m.index[-2], 'Close'] = calculated_recent_high - 0.1

    detector = NewBreakoutDetector(adx_threshold=25, sr_lookback_candles=sr_lookback)
    modified_dummy_data = {'base': df_15m, 'htf': df_4h}
    result = detector.analyze(modified_dummy_data, symbol, target_rr=2.0)
    
    assert result is not None
    assert result['signal'] == "BUY"
    assert result['strategy'] == "NewBreakout"
    assert "stop_loss" in result
    assert "take_profit" in result
