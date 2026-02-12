from typing import Dict, Optional
import pandas as pd
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy
from pathlib import Path
import json
import numpy as np

# Assuming PROJECT_ROOT is defined elsewhere or needs to be passed
# For now, we'll define it relative to this file for standalone testing
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

class NewBreakoutDetector(ForexStrategy):
    def __init__(self, adx_threshold: float = 25.0, ema_period: int = 34, rsi_period: int = 14, min_rr: float = 2.0, sr_lookback_candles: int = 40, atr_multiplier: float = 2.0):
        self.adx_threshold = adx_threshold
        self.ema_period = ema_period
        self.rsi_period = rsi_period
        self.min_rr = min_rr
        self.sr_lookback_candles = sr_lookback_candles # Default for S/R lookback
        self.atr_multiplier = atr_multiplier # Default for ATR-based SL/TP
        self.forex_caskets = self._load_forex_caskets()

    def get_name(self) -> str:
        return "NewBreakout"

    def _load_forex_caskets(self) -> Dict[str, list]:
        try:
            path = PROJECT_ROOT / 'data' / 'metadata' / 'forex_baskets.json'
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception:
            # Handle cases where file might not exist or is malformed
            return {"momentum": [], "steady": []}

    def get_casket(self, symbol: str) -> str:
        if symbol in self.forex_caskets.get('momentum', []): return 'momentum'
        if symbol in self.forex_caskets.get('steady', []): return 'steady'
        return 'unknown' # Default or a new category if needed

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        df_15m = data.get('base') # Base timeframe
        df_4h = data.get('htf')   # Higher timeframe (4-hour)

        if df_15m is None or len(df_15m) < max(self.ema_period, self.rsi_period, 20): # Ensure enough data for indicators
            return None
        if df_4h is None or len(df_4h) < max(self.ema_period, self.rsi_period, 20): # Ensure enough data for HTF indicators
            return None

        # Add all indicators to both dataframes
        df_15m = TechnicalIndicators.add_all_indicators(df_15m)
        df_4h = TechnicalIndicators.add_all_indicators(df_4h)

        latest_15m = df_15m.iloc[-1]
        prev_15m = df_15m.iloc[-2]
        latest_4h = df_4h.iloc[-1]
        prev_4h = df_4h.iloc[-2]

        # 1. Higher Timeframe (4H) Trend Filtering
        htf_trend = self._get_htf_trend(latest_4h)
        if htf_trend == "neutral":
            return None # No clear HTF trend, skip trade

        # 2. Breakout Entry Conditions (15M Timeframe)
        # Use sr_lookback_candles from __init__ or from params if provided
        current_sr_lookback_candles = params.get('sr_lookback_candles', self.sr_lookback_candles)
        
        # Identify recent high and low as potential S/R levels on 15m
        # Using shift(1) to avoid look-ahead bias on current candle's high/low
        recent_high = df_15m['High'].iloc[-current_sr_lookback_candles:-1].max()
        recent_low = df_15m['Low'].iloc[-current_sr_lookback_candles:-1].min()

        is_buy_signal = False
        is_sell_signal = False

        # Breakout confirmation: Close price breaks and stays above/below a recent S/R level
        # Also ensure previous candle didn't break it (to confirm NEW breakout)
        if htf_trend == "bullish" and latest_15m['Close'] > recent_high and prev_15m['Close'] <= recent_high:
            is_buy_signal = True
        elif htf_trend == "bearish" and latest_15m['Close'] < recent_low and prev_15m['Close'] >= recent_low:
            is_sell_signal = True

        if not (is_buy_signal or is_sell_signal):
            return None

        # Optional: Retest logic - for now, we enter on first confirmed breakout.
        # Retest can be incorporated as a separate filter or a parameter.

        # 3. Casket-Specific Logic
        casket = self.get_casket(symbol)
        score = 60.0 # Base score

        # Adjust score or parameters based on casket
        if casket == 'momentum':
            score += 10 # Bonus for momentum pairs
        elif casket == 'steady':
            score += 5 # Smaller bonus for steady

        price = float(latest_15m['Close'])
        signal_type = "BUY" if is_buy_signal else "SELL"

        # Define Stop Loss (SL) and Take Profit (TP)
        # Use atr_multiplier from __init__ or from params if provided
        current_atr_multiplier = params.get('atr_multiplier', self.atr_multiplier)
        current_atr = float(latest_15m['ATR'])

        if current_atr == 0: # Avoid division by zero
            return None

        risk = current_atr * current_atr_multiplier # Initial risk based on ATR

        # Apply spread padding to SL calculation
        padding = spread if spread > 0 else (price * 0.0005) # Default 0.05% of price

        if signal_type == "BUY":
            stop_loss = price - risk
            stop_loss -= padding # Adjust SL further down by spread
            take_profit = price + (risk * target_rr)
        else: # SELL
            stop_loss = price + risk
            stop_loss += padding # Adjust SL further up by spread
            take_profit = price - (risk * target_rr)

        # Basic validation for SL/TP (ensure TP > SL for buy, TP < SL for sell)
        if signal_type == "BUY" and (stop_loss >= price or take_profit <= price): return None
        if signal_type == "SELL" and (stop_loss <= price or take_profit >= price): return None


        return {
            "signal": signal_type,
            "score": score,
            "strategy": self.get_name(),
            "symbol": symbol,
            "casket": casket,
            "price": price,
            "timestamp": latest_15m.name.isoformat() if hasattr(latest_15m.name, 'isoformat') else str(latest_15m.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX_4h": round(float(latest_4h['ADX']), 2),
                "EMA34_4h": round(float(latest_4h['EMA34']), 5),
                "HTF_Trend": htf_trend,
                "ATR_15m": round(current_atr, 5)
            }
        }

    def _get_htf_trend(self, latest_4h_data: pd.Series) -> str:
        """Determine HTF trend based on EMA34, ADX, DI+/DI-."""
        if 'EMA34' not in latest_4h_data or 'ADX' not in latest_4h_data or 'DIPlus' not in latest_4h_data or 'DIMinus' not in latest_4h_data:
            return "neutral"

        if latest_4h_data['ADX'] > self.adx_threshold:
            if latest_4h_data['Close'] > latest_4h_data['EMA34'] and latest_4h_data['DIPlus'] > latest_4h_data['DIMinus']:
                return "bullish"
            elif latest_4h_data['Close'] < latest_4h_data['EMA34'] and latest_4h_data['DIMinus'] > latest_4h_data['DIPlus']:
                return "bearish"
        return "neutral"

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Default exit condition: simple MA cross or counter-signal.
        For breakout strategy, might use trailing stop or reversal signal.
        Placeholder for now.
        """
        df_15m = data.get('base')
        if df_15m is None or len(df_15m) < self.ema_period:
            return None

        # Ensure indicators are added for exit checks
        df_15m = TechnicalIndicators.add_all_indicators(df_15m)

        latest_15m = df_15m.iloc[-1]
        prev_15m = df_15m.iloc[-2]

        # Simple EMA crossover for exit (e.g., price crossing EMA9)
        # This will be refined based on strategy details
        if 'EMA9' not in latest_15m: # Fallback if EMA9 not added by add_all_indicators
            df_15m['EMA9'] = TechnicalIndicators.calculate_ema(df_15m, period=9)
            latest_15m = df_15m.iloc[-1]
            prev_15m = df_15m.iloc[-2] # Recalculate prev_15m after adding EMA9

        exit_signal = False
        reason = None

        if direction == "BUY":
            # Exit if price crosses below EMA9
            if latest_15m['Close'] < latest_15m['EMA9'] and prev_15m['Close'] >= prev_15m['EMA9']:
                exit_signal = True
                reason = f"Price ({latest_15m['Close']:.5f}) crossed below EMA9 ({latest_15m['EMA9']:.5f})"
        elif direction == "SELL":
            # Exit if price crosses above EMA9
            if latest_15m['Close'] > latest_15m['EMA9'] and prev_15m['Close'] <= prev_15m['EMA9']:
                exit_signal = True
                reason = f"Price ({latest_15m['Close']:.5f}) crossed above EMA9 ({latest_15m['EMA9']:.5f})"

        if exit_signal:
            return {
                "exit_signal": True,
                "reason": reason
            }
        return None
