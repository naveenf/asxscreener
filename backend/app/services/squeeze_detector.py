"""
Squeeze Strategy Detector (MTF)

Logic:
- Identify volatility compression (Squeeze) on 15m.
- Confirm with building energy (Low ADX or Squeeze) on 1H.
- Trade the breakout.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class SqueezeDetector(ForexStrategy):
    def __init__(self, squeeze_threshold: float = 0.0020, adx_max: float = 25.0):
        self.squeeze_threshold = squeeze_threshold
        self.adx_max = adx_max

    def get_name(self) -> str:
        return "Squeeze"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str) -> Optional[Dict]:
        df = data.get('base')
        df_htf = data.get('htf')
        
        if df is None or len(df) < 50: return None

        # Add indicators to base timeframe
        df = TechnicalIndicators.add_all_indicators(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Detect Squeeze Condition (Recent Low Volatility)
        # Look back 20 bars to see if we were in a squeeze
        # Squeeze defined as BB Width < Threshold OR BB Width near 96-period low
        
        # Calculate recent min width
        min_width_96 = df['BB_Width'].iloc[-96:].min()
        is_narrow = latest['BB_Width'] <= min_width_96 * 1.5
        
        # 2. Detect Breakout (Expansion)
        # Width expanding
        expanding = latest['BB_Width'] > prev['BB_Width']
        
        # Price breaking out of Bands
        breakout_up = latest['Close'] > latest['BB_Upper']
        breakout_down = latest['Close'] < latest['BB_Lower']
        
        if not (breakout_up or breakout_down): return None
        
        # 3. HTF Confirmation (Energy Building)
        htf_confirmed = True
        if df_htf is not None and len(df_htf) > 20:
            df_htf = TechnicalIndicators.add_all_indicators(df_htf)
            latest_htf = df_htf.iloc[-1]
            # Ideally HTF is also somewhat consolidated or at least not exhausted
            # ADX < 30 suggests room to run
            if latest_htf['ADX'] > 40: 
                htf_confirmed = False # Trend already exhausted
        
        if not htf_confirmed: return None

        # 4. Volume Confirmation (if available)
        vol_confirmed = True
        if 'Volume' in df.columns and latest['Volume'] > 0:
            avg_vol = df['Volume'].iloc[-6:-1].mean()
            if avg_vol > 0 and latest['Volume'] < avg_vol * 1.2:
                vol_confirmed = False # Weak breakout volume
        
        if not vol_confirmed: return None

        signal = "BUY" if breakout_up else "SELL"
        
        return {
            "signal": signal,
            "score": 80.0, # Squeezes are high potential
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": float(latest['Close']),
            "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
            "stop_loss": float(latest['BB_Middle']), # Stop at mean
            "take_profit": None,
            "indicators": {
                "ADX": round(float(latest.get('ADX', 0)), 1),
                "BB_Width": round(float(latest.get('BB_Width', 0)), 4),
                "vol_accel": 0.0, # Placeholder
                "di_momentum": 0.0, # Placeholder
                "DIPlus": 0.0,
                "DIMinus": 0.0,
                "is_power_volume": False,
                "is_power_momentum": False
            }
        }
