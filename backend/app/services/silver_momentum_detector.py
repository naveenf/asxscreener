import pandas as pd
import numpy as np
from typing import Dict, Optional
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class SilverMomentumDetector(ForexStrategy):
    """
    Silver Momentum Strategy (1H MACD + 4H Trend Filter)
    - Entry: MACD histogram crosses zero
    - Confirmation: 4H trend alignment, RSI not extreme, Price vs EMA34
    - Time Filter: Configurable (default 13:00-17:00 UTC - London-NY overlap)
    - Exit: MACD signal cross or 4H trend reversal
    """

    def __init__(self, macd_fast=12, macd_slow=26, macd_signal=9, 
                 atr_sl_multiplier=2.0, rsi_threshold=70,
                 session_start=13, session_end=17):
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.atr_sl_multiplier = atr_sl_multiplier
        self.rsi_threshold = rsi_threshold
        self.session_start = session_start
        self.session_end = session_end

    def get_name(self) -> str:
        return "SilverMomentum"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.5, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Analyze for MACD momentum signals on 1H + 4H confirmation.
        """
        # Extract params from config
        if params:
            self.macd_fast = params.get('macd_fast', self.macd_fast)
            self.macd_slow = params.get('macd_slow', self.macd_slow)
            self.macd_signal = params.get('macd_signal', self.macd_signal)
            self.atr_sl_multiplier = params.get('atr_sl_multiplier', self.atr_sl_multiplier)
            self.rsi_threshold = params.get('rsi_threshold', self.rsi_threshold)
            self.session_start = params.get('session_start', self.session_start)
            self.session_end = params.get('session_end', self.session_end)

        # Get data (Backtest uses '1h'/'4h', Real-time might use 'base'/'htf')
        df_1h = data.get('1h')
        if df_1h is None:
            df_1h = data.get('base')
            
        df_4h = data.get('4h')
        if df_4h is None:
            df_4h = data.get('htf')

        if df_1h is None or len(df_1h) < 50:
            return None

        # Ensure indicators are calculated
        if 'MACD' not in df_1h.columns:
            df_1h = TechnicalIndicators.calculate_macd(df_1h, self.macd_fast, self.macd_slow, self.macd_signal)
        if 'RSI' not in df_1h.columns:
            df_1h['RSI'] = TechnicalIndicators.calculate_rsi(df_1h)
        if 'ATR' not in df_1h.columns:
            df_1h['ATR'] = TechnicalIndicators.calculate_atr(df_1h)
        if 'EMA_34' not in df_1h.columns:
            df_1h['EMA_34'] = TechnicalIndicators.calculate_ema(df_1h, period=34)

        latest_1h = df_1h.iloc[-1]
        prev_1h = df_1h.iloc[-2]
        current_time = latest_1h.name

        # Time Filter: 13:00-17:00 UTC (London-NY overlap)
        # Note: In backtesting, the index is datetime objects
        hour_utc = current_time.hour
        if hour_utc < self.session_start or hour_utc >= self.session_end:
            return None

        # 1. MACD Histogram Cross Detection
        macd_hist_current = float(latest_1h['MACD_Hist'])
        macd_hist_prev = float(prev_1h['MACD_Hist'])

        cross_above = (macd_hist_prev <= 0 and macd_hist_current > 0)
        cross_below = (macd_hist_prev >= 0 and macd_hist_current < 0)

        if not (cross_above or cross_below):
            return None

        # 2. 4H Trend Confirmation
        if df_4h is None or len(df_4h) < 50:
            return None

        if 'EMA_50' not in df_4h.columns:
            df_4h['EMA_50'] = TechnicalIndicators.calculate_ema(df_4h, period=50)
        if 'EMA_200' not in df_4h.columns:
            df_4h['EMA_200'] = TechnicalIndicators.calculate_ema(df_4h, period=200)

        latest_4h = df_4h.iloc[-1]
        ema50_4h = float(latest_4h['EMA_50'])
        ema200_4h = float(latest_4h['EMA_200'])

        trend_up = ema50_4h > ema200_4h
        trend_down = ema50_4h < ema200_4h

        # 3. Match signal direction with trend
        if cross_above and not trend_up:
            return None
        if cross_below and not trend_down:
            return None

        # 4. RSI Filter (avoid extreme overbought/oversold)
        rsi = float(latest_1h['RSI'])
        if cross_above and rsi > self.rsi_threshold:
            return None
        if cross_below and rsi < (100 - self.rsi_threshold):
            return None

        # 5. Price Position Filter (EMA34)
        price = float(latest_1h['Close'])
        ema34 = float(latest_1h['EMA_34'])

        if cross_above and price < ema34:
            return None
        if cross_below and price > ema34:
            return None

        # 6. Calculate Risk Management
        atr = float(latest_1h['ATR'])
        sl_distance = self.atr_sl_multiplier * atr + spread
        
        # Minimum SL distance: 0.5% of price
        min_dist = price * 0.005
        sl_distance = max(sl_distance, min_dist)

        signal = "BUY" if cross_above else "SELL"
        stop_loss = price - sl_distance if signal == "BUY" else price + sl_distance
        
        risk = abs(price - stop_loss)
        take_profit = price + (risk * target_rr if signal == "BUY" else -risk * target_rr)

        return {
            "signal": signal,
            "score": 80.0,
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": current_time.isoformat() if hasattr(current_time, 'isoformat') else str(current_time),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "MACD_Hist": round(macd_hist_current, 6),
                "RSI_1H": round(rsi, 2),
                "EMA50_4H": round(ema50_4h, 4),
                "EMA200_4H": round(ema200_4h, 4),
                "Trend_4H": "UP" if trend_up else "DOWN"
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Exit when:
        1. MACD signal line crosses MACD line (momentum reversal)
        2. 4H trend reverses (EMA50 crosses EMA200)
        """
        df_1h = data.get('1h')
        if df_1h is None:
            df_1h = data.get('base')
            
        df_4h = data.get('4h')
        if df_4h is None:
            df_4h = data.get('htf')

        if df_1h is None or len(df_1h) < 5:
            return None

        if 'MACD' not in df_1h.columns:
            df_1h = TechnicalIndicators.calculate_macd(df_1h, self.macd_fast, self.macd_slow, self.macd_signal)

        latest_1h = df_1h.iloc[-1]
        prev_1h = df_1h.iloc[-2]

        macd = float(latest_1h['MACD'])
        macd_signal = float(latest_1h['MACD_Signal'])
        macd_prev = float(prev_1h['MACD'])
        macd_signal_prev = float(prev_1h['MACD_Signal'])

        # Exit 1: MACD Signal Cross
        # BUY Exit: MACD crosses below MACD_Signal
        if direction == "BUY":
            if macd_prev > macd_signal_prev and macd < macd_signal:
                return {"exit_signal": True, "reason": "MACD bearish cross"}
        else: # SELL Exit: MACD crosses above MACD_Signal
            if macd_prev < macd_signal_prev and macd > macd_signal:
                return {"exit_signal": True, "reason": "MACD bullish cross"}

        # Exit 2: 4H Trend Reversal
        if df_4h is not None and len(df_4h) >= 2:
            if 'EMA_50' not in df_4h.columns:
                df_4h['EMA_50'] = TechnicalIndicators.calculate_ema(df_4h, period=50)
            if 'EMA_200' not in df_4h.columns:
                df_4h['EMA_200'] = TechnicalIndicators.calculate_ema(df_4h, period=200)

            latest_4h = df_4h.iloc[-1]
            prev_4h = df_4h.iloc[-2]

            ema50 = float(latest_4h['EMA_50'])
            ema200 = float(latest_4h['EMA_200'])
            ema50_prev = float(prev_4h['EMA_50'])
            ema200_prev = float(prev_4h['EMA_200'])

            if direction == "BUY":
                if ema50_prev > ema200_prev and ema50 < ema200:
                    return {"exit_signal": True, "reason": "4H trend reversal (bearish)"}
            else:
                if ema50_prev < ema200_prev and ema50 > ema200:
                    return {"exit_signal": True, "reason": "4H trend reversal (bullish)"}

        return None
