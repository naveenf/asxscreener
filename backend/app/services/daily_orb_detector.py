
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime, time, timedelta
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class DailyORBDetector(ForexStrategy):
    """
    Daily Open Range Breakout (ORB) Strategy for Silver (XAG_USD):
    - Session: Sydney Open (19:00 UTC previous day / 10 AM AEDT)
    - Range: High/Low of the first 1-2 hours
    - Breakout: 15m candle close above/below the range
    - Confirmation: HTF (1H or 4H) trend alignment (ADX > 25, DI+/DI-)
    - Risk: 2x ATR Stop Loss
    """

    def __init__(self, orb_hours: float = 1.0, htf: str = '1h', adx_min_15m: float = 20.0, adx_min_htf: float = 25.0):
        self.orb_hours = orb_hours
        self.htf_key = htf
        self.adx_min_15m = adx_min_15m
        self.adx_min_htf = adx_min_htf

    def get_name(self) -> str:
        return f"DailyORB_{self.orb_hours}h"

    def _get_session_start(self, dt: datetime) -> datetime:
        """
        Get the 19:00 UTC session start for a given datetime.
        If current time is before 19:00, the session started at 19:00 the previous day.
        """
        # Sydney open is 19:00 UTC
        session_start = dt.replace(hour=19, minute=0, second=0, microsecond=0)
        if dt < session_start:
            session_start -= timedelta(days=1)
        return session_start

    def calculate_dor(self, df_15m: pd.DataFrame, session_start: datetime) -> Optional[Tuple[float, float]]:
        """
        Calculate Daily Open Range high/low for the session starting at session_start.
        """
        orb_end = session_start + timedelta(hours=self.orb_hours)
        
        # Filter candles within the ORB window
        mask = (df_15m.index >= session_start) & (df_15m.index < orb_end)
        orb_candles = df_15m.loc[mask]
        
        if len(orb_candles) < int(self.orb_hours * 4): # 4 candles per hour for 15m
            return None
            
        orb_high = orb_candles['High'].max()
        orb_low = orb_candles['Low'].min()
        
        return orb_high, orb_low

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.5, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        df_15m = data.get('15m')
        if df_15m is None:
            df_15m = data.get('base')

        df_htf = data.get(self.htf_key)
        if df_htf is None:
            df_htf = data.get('htf')

        if df_15m is None or len(df_15m) < 50:
            return None

        # Strategy specific params override
        if params:
            self.orb_hours = params.get('orb_hours', self.orb_hours)
            self.htf_key = params.get('htf', self.htf_key)

        latest_15m = df_15m.iloc[-1]
        prev_15m = df_15m.iloc[-2]
        prev2_15m = df_15m.iloc[-3] if len(df_15m) >= 3 else None
        current_time = latest_15m.name

        # 1. Sydney Session Detection
        session_start = self._get_session_start(current_time)
        orb_end = session_start + timedelta(hours=self.orb_hours)

        # If we are still within the ORB window, no signals
        if current_time <= orb_end:
            return None

        # 2. Daily Open Range Calculation
        dor = self.calculate_dor(df_15m, session_start)
        if not dor:
            return None
        orb_high, orb_low = dor

        # 3. Add indicators
        if 'ATR' not in df_15m.columns:
            df_15m = df_15m.copy()
            df_15m['ATR'] = TechnicalIndicators.calculate_atr(df_15m)
        if 'ADX' not in df_15m.columns:
            df_15m = TechnicalIndicators.calculate_adx(df_15m)
        if 'BB_Width' not in df_15m.columns:
            df_15m = TechnicalIndicators.add_all_indicators(df_15m)

        atr = float(df_15m.iloc[-1]['ATR'])
        latest_15m_ind = df_15m.iloc[-1]

        # 4. Squeeze Filter - Bollinger Bands width must be low (consolidation)
        # This reduces false breakouts by requiring prior consolidation
        bb_width = float(latest_15m_ind['BB_Width'])
        bb_high = float(latest_15m_ind.get('BB_Upper', orb_high))
        bb_low = float(latest_15m_ind.get('BB_Lower', orb_low))

        # Allow breakout only if BB is not too wide (squeeze condition) OR price just entering expansion
        # Using 1.5x the minimum BB width from recent 20 periods
        recent_bb_widths = df_15m['BB_Width'].iloc[-20:-1]
        min_bb_width = recent_bb_widths.min() if len(recent_bb_widths) > 0 else bb_width
        squeeze_threshold = 1.8  # was 1.3, increased to allow more entries

        is_squeeze = bb_width <= (min_bb_width * squeeze_threshold)

        # 5. Breakout Detection with Strength Requirement
        # Price must close beyond level by at least 0.5 ATR to confirm strength
        strength_threshold = 0.5 * atr

        breakout_up = (latest_15m['Close'] > orb_high + strength_threshold) and (prev_15m['Close'] <= orb_high)
        breakout_down = (latest_15m['Close'] < orb_low - strength_threshold) and (prev_15m['Close'] >= orb_low)

        if not (breakout_up or breakout_down):
            return None

        # 6. Momentum Confirmation on 15m (ADX > 18, increasing trend)
        if latest_15m_ind['ADX'] < 18:  # Lowered from 20 to catch more setups
            return None

        # Check if ADX is rising (momentum building)
        adx_rising = latest_15m_ind['ADX'] > prev_15m['ADX'] if 'ADX' in prev_15m and not pd.isna(prev_15m['ADX']) else True

        # 7. HTF Trend Confirmation (STRICT)
        if df_htf is None or len(df_htf) < 20:
            return None

        if 'ADX' not in df_htf.columns:
            df_htf = TechnicalIndicators.calculate_adx(df_htf)

        latest_htf = df_htf.iloc[-1]

        # Require clear directional alignment on HTF
        if breakout_up:
            # For BUY: DI+ significantly above DI-, ADX > 20
            di_diff = float(latest_htf['DIPlus']) - float(latest_htf['DIMinus'])
            if di_diff < 5.0 or latest_htf['ADX'] < 20.0:  # Require at least 5 point DI difference
                return None
        elif breakout_down:
            # For SELL: DI- significantly above DI+, ADX > 20
            di_diff = float(latest_htf['DIMinus']) - float(latest_htf['DIPlus'])
            if di_diff < 5.0 or latest_htf['ADX'] < 20.0:
                return None

        # 8. Risk Management - IMPROVED SL
        price = float(latest_15m['Close'])

        # Stop Loss: 1.5x ATR (tighter than 2x to reduce drawdown)
        sl_distance = 1.5 * atr + spread

        # Minimum SL distance: 0.3% of price (tighter than 0.5%)
        min_dist = price * 0.003
        sl_distance = max(sl_distance, min_dist)

        signal = "BUY" if breakout_up else "SELL"
        stop_loss = price - sl_distance if signal == "BUY" else price + sl_distance

        risk = abs(price - stop_loss)
        take_profit = price + (risk * target_rr if signal == "BUY" else -risk * target_rr)

        return {
            "signal": signal,
            "score": 85.0,
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": current_time.isoformat() if hasattr(current_time, 'isoformat') else str(current_time),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX_15m": round(float(latest_15m_ind['ADX']), 1),
                "ADX_htf": round(float(latest_htf['ADX']), 1),
                "DI_diff_htf": round(di_diff, 1),
                "orb_high": round(orb_high, 2),
                "orb_low": round(orb_low, 2),
                "squeeze_status": is_squeeze,
                "htf_used": self.htf_key
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Exit when HTF trend reverses or ADX drops significantly.
        """
        df_htf = data.get(self.htf_key)
        if df_htf is None:
            df_htf = data.get('htf')
            
        if df_htf is None or len(df_htf) < 5:
            return None
            
        if 'ADX' not in df_htf.columns:
            df_htf = TechnicalIndicators.calculate_adx(df_htf)
            
        latest_htf = df_htf.iloc[-1]
        
        exit_signal = False
        reason = None
        
        if direction == "BUY":
            if latest_htf['DIPlus'] < latest_htf['DIMinus']:
                exit_signal = True
                reason = "HTF Trend reversal (DI+ < DI-)"
            elif latest_htf['ADX'] < 20:
                exit_signal = True
                reason = "HTF Trend weakness (ADX < 20)"
        else: # SELL
            if latest_htf['DIMinus'] < latest_htf['DIPlus']:
                exit_signal = True
                reason = "HTF Trend reversal (DI- < DI+)"
            elif latest_htf['ADX'] < 20:
                exit_signal = True
                reason = "HTF Trend weakness (ADX < 20)"
                
        if exit_signal:
            return {"exit_signal": True, "reason": reason}
        return None
