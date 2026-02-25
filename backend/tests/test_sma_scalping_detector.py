import pandas as pd
import pytest
from backend.app.services.sma_scalping_detector import SmaScalpingDetector
from backend.app.services.indicators import TechnicalIndicators

# Helper function to create a mock DataFrame with calculated indicators
def create_mock_dataframe(closes, highs, lows):
    data = {
        'Open': [1.0] * len(closes), # Open not critical for this strategy, can be dummy
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': [100] * len(closes), # Volume not critical for this strategy, can be dummy
    }
    # Generate valid 5-minute timestamps, ensuring enough history for indicators
    start_time = pd.to_datetime('2023-01-01 00:00:00')
    time_index = pd.date_range(start=start_time, periods=len(closes), freq='5min')
    
    df = pd.DataFrame(data, index=time_index)
    
    return df

@pytest.fixture
def detector():
    return SmaScalpingDetector(di_threshold=30.0, rr=5.0)

def test_buy_signal_conditions_met(detector):
    # Conditions for BUY: Close > SMA100, Close > SMA50, Close > SMA20, DI+ > 30
    # Create data for a strong, consistent uptrend
    base_price = 100.0
    num_candles = 150 # Enough candles for all SMAs and ADX (100 for SMA100, 14 for ADX)
    closes = [base_price + i * 0.1 for i in range(num_candles)] # Steady upward
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]

    # Ensure the last few candles show strong directional movement for DI+
    # A sharp increase at the end
    for i in range(10): # Last 10 candles have a stronger push
        closes[num_candles - 10 + i] += i * 0.5
        highs[num_candles - 10 + i] += i * 0.5 + 0.1
        lows[num_candles - 10 + i] += i * 0.5 - 0.1
    
    df_ohlcv = create_mock_dataframe(closes, highs, lows)
    data = {'base': df_ohlcv}

    signal = detector.analyze(data, "TEST_PAIR", spread=0.0001)
    
    assert signal is not None
    assert signal['signal'] == 'BUY'
    assert signal['strategy'] == 'SmaScalping'
    assert signal['price'] == closes[-1]
    assert signal['stop_loss'] < signal['price']
    assert signal['take_profit'] > signal['price']
    assert signal['take_profit'] - signal['price'] == pytest.approx((signal['price'] - signal['stop_loss']) * 5)

def test_sell_signal_conditions_met(detector):
    # Conditions for SELL: Close < SMA100, Close < SMA50, Close < SMA20, DI- > 30
    # Create data for a strong, consistent downtrend
    base_price = 200.0
    num_candles = 150
    closes = [base_price - i * 0.1 for i in range(num_candles)] # Steady downward
    highs = [c + 0.05 for c in closes]
    lows = [c - 0.05 for c in closes]

    # A sharp decrease at the end for strong directional movement for DI-
    for i in range(10): # Last 10 candles have a stronger push down
        closes[num_candles - 10 + i] -= i * 0.5
        highs[num_candles - 10 + i] -= i * 0.5 - 0.1
        lows[num_candles - 10 + i] -= i * 0.5 + 0.1
    
    df_ohlcv = create_mock_dataframe(closes, highs, lows)
    data = {'base': df_ohlcv}

    signal = detector.analyze(data, "TEST_PAIR", spread=0.0001)
    
    assert signal is not None
    assert signal['signal'] == 'SELL'
    assert signal['strategy'] == 'SmaScalping'
    assert signal['price'] == closes[-1]
    assert signal['stop_loss'] > signal['price']
    assert signal['take_profit'] < signal['price']
    assert signal['price'] - signal['take_profit'] == pytest.approx((signal['stop_loss'] - signal['price']) * 5)

def test_no_signal_conditions(detector):
    # Test 1: Price below SMAs, but DI- is low (choppy market) -> no SELL signal
    base_price = 150.0
    num_candles = 150
    closes_choppy = [base_price + (i % 5) * 0.1 - (i % 3) * 0.05 for i in range(num_candles)] # Choppy
    highs_choppy = [c + 0.1 for c in closes_choppy]
    lows_choppy = [c - 0.1 for c in closes_choppy]

    df_ohlcv_choppy = create_mock_dataframe(closes_choppy, highs_choppy, lows_choppy)
    data_choppy = {'base': df_ohlcv_choppy}
    signal_choppy = detector.analyze(data_choppy, "TEST_PAIR", spread=0.0001)
    assert signal_choppy is None

    # Test 2: Price above SMAs, but DI+ is low (choppy market) -> no BUY signal
    base_price = 150.0
    num_candles = 150
    closes_choppy_up = [base_price + (i % 5) * 0.1 - (i % 3) * 0.05 + 50 for i in range(num_candles)] # Choppy but generally higher
    highs_choppy_up = [c + 0.1 for c in closes_choppy_up]
    lows_choppy_up = [c - 0.1 for c in closes_choppy_up]
    
    df_ohlcv_choppy_up = create_mock_dataframe(closes_choppy_up, highs_choppy_up, lows_choppy_up)
    data_choppy_up = {'base': df_ohlcv_choppy_up}
    signal_choppy_up = detector.analyze(data_choppy_up, "TEST_PAIR", spread=0.0001)
    assert signal_choppy_up is None


def test_buy_exit_condition_met(detector):
    # Price crosses below SMA20
    closes = [100.0] * 19 + [100.5] + [99.0] # SMA20 will be ~100.025, close 99.0
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]

    df_ohlcv = create_mock_dataframe(closes, highs, lows)
    data = {'base': df_ohlcv}

    exit_signal = detector.check_exit(data, "BUY", entry_price=100.0)
    
    assert exit_signal is not None
    assert exit_signal['exit_signal'] is True
    assert "crossed below SMA20" in exit_signal['reason']

def test_buy_exit_condition_not_met(detector):
    # Price remains above SMA20
    closes = [100.0] * 19 + [99.5] + [100.0] # SMA20 will be ~99.975, close 100.0
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]

    df_ohlcv = create_mock_dataframe(closes, highs, lows)
    data = {'base': df_ohlcv}

    exit_signal = detector.check_exit(data, "BUY", entry_price=100.0)
    assert exit_signal is None

def test_sell_exit_condition_met(detector):
    # Price crosses above SMA20
    closes = [100.0] * 19 + [99.5] + [100.0] # SMA20 will be ~99.975, close 100.0
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]

    df_ohlcv = create_mock_dataframe(closes, highs, lows)
    data = {'base': df_ohlcv}

    exit_signal = detector.check_exit(data, "SELL", entry_price=100.0)
    
    assert exit_signal is not None
    assert exit_signal['exit_signal'] is True
    assert "crossed above SMA20" in exit_signal['reason']

def test_sell_exit_condition_not_met(detector):
    # Price remains below SMA20
    closes = [100.0] * 19 + [100.5] + [99.0] # SMA20 will be ~100.025, close 99.0
    highs = [c + 0.1 for c in closes]
    lows = [c - 0.1 for c in closes]

    df_ohlcv = create_mock_dataframe(closes, highs, lows)
    data = {'base': df_ohlcv}

    exit_signal = detector.check_exit(data, "SELL", entry_price=100.0)
    assert exit_signal is None
