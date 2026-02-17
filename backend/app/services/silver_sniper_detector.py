
import pandas as pd
import numpy as np
from typing import Dict, Optional
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class SilverSniperDetector(ForexStrategy):
    """
    Silver Sniper Strategy:
    - Base: 5m Squeeze Breakout
    - Confirmation 1: 15m Trend (DI+/DI- and ADX)
    - Confirmation 2: Entry within a recent 5m FVG (Fair Value Gap)
    """

    def __init__(self, squeeze_threshold: float = 1.6, adx_min: float = 18.0):
        self.squeeze_threshold = squeeze_threshold
        self.adx_min = adx_min

    def get_name(self) -> str:
        return "SilverSniper"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 3.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        df_5m = data.get('base')
        df_15m = data.get('htf')

        if df_5m is None or len(df_5m) < 100:
            return None

        # Extract params
        st_threshold = self.squeeze_threshold
        adx_limit = self.adx_min
        require_fvg = True
        fvg_boost = 0.0
        lookback = 48  # default 4 hours in 5m candles (was 96)

        if params:
            st_threshold = params.get('squeeze_threshold', st_threshold)
            adx_limit = params.get('adx_min', adx_limit)
            require_fvg = params.get('require_fvg', True)
            fvg_boost = params.get('fvg_score_boost', 0.0)
            if 'lookback_hours' in params:
                lookback = params.get('lookback_hours') * 12
        
        # Ensure indicators are added (especially FVG)
        if 'Bull_FVG' not in df_5m.columns:
            df_5m = TechnicalIndicators.add_all_indicators(df_5m)
        
        latest_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]

        # 1. 5m Squeeze Detection
        # Calculate recent min width (excluding current candle)
        min_width = df_5m['BB_Width'].iloc[-(lookback+1):-1].min()
        is_squeeze = latest_5m['BB_Width'] <= min_width * st_threshold
        
        if not is_squeeze:
            return None

        # 2. 5m Breakout Detection
        breakout_up = (latest_5m['Close'] > latest_5m['BB_Upper']) and (prev_5m['Close'] <= prev_5m['BB_Upper'])
        breakout_down = (latest_5m['Close'] < latest_5m['BB_Lower']) and (prev_5m['Close'] >= prev_5m['BB_Lower'])

        if not (breakout_up or breakout_down):
            return None

        # 3. 15m Trend Confirmation
        if df_15m is not None and len(df_15m) >= 20:
            if 'ADX' not in df_15m.columns:
                df_15m = TechnicalIndicators.calculate_adx(df_15m)
            
            latest_15m = df_15m.iloc[-1]
            
            if breakout_up:
                if latest_15m['DIPlus'] < latest_15m['DIMinus'] or latest_15m['ADX'] < adx_limit:
                    return None
            elif breakout_down:
                if latest_15m['DIMinus'] < latest_15m['DIPlus'] or latest_15m['ADX'] < adx_limit:
                    return None
        else:
            # If no 15m data, we can't confirm trend. Skip.
            return None

        # 4. FVG Mitigation Check
        # Check if there was an FVG in the last 5 candles
        recent_5m = df_5m.iloc[-6:-1]
        if breakout_up:
            has_recent_fvg = recent_5m['Bull_FVG'].any()
        else:
            has_recent_fvg = recent_5m['Bear_FVG'].any()
            
        if require_fvg and not has_recent_fvg:
            return None

        # 5. Scoring
        # If fvg_boost is 0, default to 10.0 if FVG is present
        effective_fvg_boost = fvg_boost if fvg_boost > 0 else 10.0
        score = 75.0 + (effective_fvg_boost if has_recent_fvg else 0.0)

        signal = "BUY" if breakout_up else "SELL"
        price = float(latest_5m['Close'])
        bb_middle = float(latest_5m['BB_Middle'])
        
        # Calculate initial SL
        stop_loss = bb_middle
        
        # HARDENING: Ensure minimum distance for SL (0.5%) + SPREAD PROTECTION
        # Use provided spread or default to 0.05% of price if missing
        padding = spread if spread > 0 else (price * 0.0005)
        
        min_dist = price * 0.005
        
        if signal == "BUY":
            stop_loss = min(stop_loss, price - min_dist)
            # Apply Spread Padding to prevent immediate wick-out
            stop_loss -= padding
        else: # SELL
            stop_loss = max(stop_loss, price + min_dist)
            stop_loss += padding
        
        risk = abs(price - stop_loss)
        if risk == 0: return None
        
        take_profit = price + (risk * target_rr if signal == "BUY" else -risk * target_rr)

        return {
            "signal": signal,
            "score": score,
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": latest_5m.name.isoformat() if hasattr(latest_5m.name, 'isoformat') else str(latest_5m.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX_15m": round(float(latest_15m['ADX']), 1),
                "BB_Width": round(float(latest_5m['BB_Width']), 4),
                "is_squeeze": True,
                "has_fvg": bool(has_recent_fvg)
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Standard exit: Price crosses back over the Middle Bollinger Band.
        """
        df = data.get('base')
        if df is None or len(df) < 20:
            return None
        
        if 'BB_Middle' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(df)
            
        latest = df.iloc[-1]
        close = float(latest['Close'])
        bb_middle = float(latest['BB_Middle'])
        
        exit_signal = False
        reason = None
        
        if direction == "BUY" and close < bb_middle:
            exit_signal = True
            reason = "Price crossed below BB Middle"
        elif direction == "SELL" and close > bb_middle:
            exit_signal = True
            reason = "Price crossed above BB Middle"
            
        if exit_signal:
            return {"exit_signal": True, "reason": reason}
        return None
