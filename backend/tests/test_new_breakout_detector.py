import pandas as pd
import pytest
from backend.app.services.new_breakout_detector import NewBreakoutDetector
from backend.app.services.indicators import TechnicalIndicators # To ensure indicators are calculated

# Dummy data for testing
@pytest.fixture
def dummy_data():
    # Create sample dataframes for 15m and 4h
    # Ensure enough data for indicator calculation (e.g., 200 bars for SMA200)
    # And for HTF alignment
    
    # 15m data
    data_15m = {
        'Date': pd.to_datetime(pd.date_range(start='2023-01-01', periods=250, freq='15min')),
        'Open': [i + 100 for i in range(250)],
        'High': [i + 101 for i in range(250)],
        'Low': [i + 99 for i in range(250)],
        'Close': [i + 100.5 for i in range(250)],
        'Volume': [1000 + i for i in range(250)]
    }
    df_15m = pd.DataFrame(data_15m).set_index('Date')
    df_15m = TechnicalIndicators.add_all_indicators(df_15m)

    # 4h data (aligned to 15m)
    data_4h = {
        'Date': pd.to_datetime(pd.date_range(start='2023-01-01', periods=20, freq='4H')),
        'Open': [i + 90 for i in range(20)],
        'High': [i + 92 for i in range(20)],
        'Low': [i + 88 for i in range(20)],
        'Close': [i + 90.5 for i in range(20)],
        'Volume': [5000 + i*10 for i in range(20)]
    }
    df_4h = pd.DataFrame(data_4h).set_index('Date')
    df_4h = TechnicalIndicators.add_all_indicators(df_4h)

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
    
    # Manually ensure no signal by setting conditions that won't trigger
    # In dummy_data, Close is generally rising, so a bullish trend.
    # We need to make sure the breakout condition isn't met or HTF isn't strong enough.
    
    # For a no-signal scenario, let's pass data where HTF is neutral or breakout isn't clear
    
    # Example: Create a scenario where ADX is too low for HTF trend
    dummy_data['htf']['ADX'].iloc[-1] = 10 # Force low ADX
    dummy_data['htf']['ADX'].iloc[-2] = 9 # Force low ADX

    result = detector.analyze(dummy_data, symbol, target_rr=2.0)
    assert result is None

def test_new_breakout_detector_analyze_buy_signal(dummy_data):
    # Adjust dummy data to generate a BUY signal
    df_15m = dummy_data['base']
    df_4h = dummy_data['htf']
    symbol = "TEST_PAIR"
    
    # Ensure strong bullish HTF trend
    df_4h['Close'].iloc[-1] = 1000 # High close
    df_4h['EMA34'].iloc[-1] = 900
    df_4h['ADX'].iloc[-1] = 30 # Strong ADX
    df_4h['DIPlus'].iloc[-1] = 40
    df_4h['DIMinus'].iloc[-1] = 20
    
    # Ensure 15m breakout
    # Create a recent high that can be broken
    sr_lookback = 20
    recent_high_idx = df_15m['High'].iloc[-sr_lookback:-1].idxmax()
    df_15m['High'].loc[recent_high_idx] = 150 # Some high within lookback

    # Current close breaks a recent high
    df_15m['Close'].iloc[-1] = df_15m['High'].iloc[-sr_lookback:-1].max() + 5
    df_15m['Close'].iloc[-2] = df_15m['High'].iloc[-sr_lookback:-1].max() - 1

    detector = NewBreakoutDetector(adx_threshold=25, sr_lookback_candles=sr_lookback)
    result = detector.analyze(dummy_data, symbol, target_rr=2.0)
    
    assert result is not None
    assert result['signal'] == "BUY"
    assert result['strategy'] == "NewBreakout"
    assert "stop_loss" in result
    assert "take_profit" in result
