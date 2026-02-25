from typing import Dict, Optional
import pandas as pd
from .strategy_interface import ForexStrategy
from .indicators import TechnicalIndicators

class SmaScalpingDetector(ForexStrategy):
    """
    5-minute scalping strategy using SMAs (20, 50, 100) and DMI.
    """
    def __init__(self, di_threshold: float = 35.0, rr: float = 5.0):
        self.di_threshold = di_threshold
        self.rr = rr

    def get_name(self) -> str:
        return "SmaScalping"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 5.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Analyze entry conditions.
        """
        df = data.get('base') # Assumes 'base' is the 5-min timeframe
        if df is None or len(df) < 101: # Need enough data for SMA 100
            return None

        # Read di_threshold from runtime params (allows per-asset JSON override)
        di_threshold = params.get('di_threshold', self.di_threshold) if params else self.di_threshold

        # -- Calculate Indicators --
        # Use add_all_indicators to ensure all necessary indicators are present
        # This will calculate ADX, SMA20, SMA50, SMA100, etc.
        # We need to ensure that the SMA periods we need are calculated by add_all_indicators.
        # Currently, add_all_indicators only calculates SMA200 by default.
        # So we either need to modify add_all_indicators or calculate specifically.
        # For this strategy, specific calculation is fine to keep it isolated.
        # Re-adding individual indicator calculations but using df_with_indicators variable.
        df_with_indicators = TechnicalIndicators.add_all_indicators(df)
        
        # Ensure our specific SMAs are present, add them if add_all_indicators didn't include them
        if 'SMA20' not in df_with_indicators.columns:
            df_with_indicators['SMA20'] = TechnicalIndicators.calculate_sma(df_with_indicators, period=20)
        if 'SMA50' not in df_with_indicators.columns:
            df_with_indicators['SMA50'] = TechnicalIndicators.calculate_sma(df_with_indicators, period=50)
        if 'SMA100' not in df_with_indicators.columns:
            df_with_indicators['SMA100'] = TechnicalIndicators.calculate_sma(df_with_indicators, period=100)

        latest = df_with_indicators.iloc[-1]

        
        # Ensure indicator values are present
        required_cols = ['SMA20', 'SMA50', 'SMA100', 'DIPlus', 'DIMinus', 'Low', 'High']
        if not all(col in latest.index and pd.notna(latest[col]) for col in required_cols):
            return None
            
        # -- Entry Conditions --
        is_buy_signal = (
            latest['Close'] > latest['SMA20'] and
            latest['Close'] > latest['SMA50'] and
            latest['Close'] > latest['SMA100'] and
            latest['DIPlus'] > di_threshold
        )

        is_sell_signal = (
            latest['Close'] < latest['SMA20'] and
            latest['Close'] < latest['SMA50'] and
            latest['Close'] < latest['SMA100'] and
            latest['DIMinus'] > di_threshold
        )

        if not (is_buy_signal or is_sell_signal):
            return None

        # -- SL/TP Calculation --
        price = float(latest['Close'])
        signal_type = "BUY" if is_buy_signal else "SELL"
        
        # Get last 2 candles before entry candle
        prev_candles = df_with_indicators.iloc[-3:-1]

        rr = target_rr if target_rr > 0 else self.rr
        if signal_type == "BUY":
            # SL is the lowest of the previous 2 candles + spread
            sl_price = prev_candles['Low'].min()
            stop_loss = sl_price - spread
            risk = price - stop_loss
            take_profit = price + (risk * rr)
        else: # SELL
            # SL is the highest of the previous 2 candles + spread
            sl_price = prev_candles['High'].max()
            stop_loss = sl_price + spread
            risk = stop_loss - price
            take_profit = price - (risk * rr)

        # Basic validation
        if risk <= 0:
            return None

        return {
            "signal": signal_type,
            "score": 75.0, # Base score
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "SMA20": round(float(latest['SMA20']), 5),
                "SMA50": round(float(latest['SMA50']), 5),
                "SMA100": round(float(latest['SMA100']), 5),
                "DIPlus": round(float(latest['DIPlus']), 2),
                "DIMinus": round(float(latest['DIMinus']), 2),
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Check exit conditions.
        Exit for BUY if price closes below SMA20.
        Exit for SELL if price closes above SMA20.
        """
        df = data.get('base')
        if df is None or len(df) < 21: # Need enough data for SMA20
            return None

        # -- Calculate Indicator --
        df_with_indicators = TechnicalIndicators.add_all_indicators(df)
        if 'SMA20' not in df_with_indicators.columns:
            df_with_indicators['SMA20'] = TechnicalIndicators.calculate_sma(df_with_indicators, period=20)
        
        latest = df_with_indicators.iloc[-1]
        
        if pd.isna(latest['SMA20']):
            return None

        exit_signal = False
        reason = None

        if direction == "BUY" and latest['Close'] < latest['SMA20']:
            exit_signal = True
            reason = f"Close ({latest['Close']:.5f}) crossed below SMA20 ({latest['SMA20']:.5f})"
        elif direction == "SELL" and latest['Close'] > latest['SMA20']:
            exit_signal = True
            reason = f"Close ({latest['Close']:.5f}) crossed above SMA20 ({latest['SMA20']:.5f})"

        if exit_signal:
            return {
                "exit_signal": True,
                "reason": reason
            }
        
        return None
