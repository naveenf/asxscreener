"""
Forex Signal Detection Module - Balanced Gold Standard
The "Sweet Spot" found through extensive backtesting.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from .indicators import TechnicalIndicators

class ForexDetector:
    def __init__(self, adx_threshold: float = 30.0, di_threshold: float = 20.0, sma_period: int = 200):
        self.adx_threshold = adx_threshold
        self.di_threshold = di_threshold
        self.sma_period = sma_period
        self.sma_column = f'SMA{sma_period}'

    def analyze(self, df: pd.DataFrame, symbol: str, name: str, pair_type: str) -> Optional[Dict]:
        if len(df) < self.sma_period + 20: return None
        latest = df.iloc[-1]
        prev1 = df.iloc[-2]
        prev2 = df.iloc[-3]
        
        # 1. EMA Stack Filter (Price > 13 > 34)
        is_bull = latest['Close'] > latest['EMA13'] > latest['EMA34']
        is_bear = latest['Close'] < latest['EMA13'] < latest['EMA34']
        if not (is_bull or is_bear): return None

        # 2. EMA34 Slope (Underlying Trend Confirmation)
        ema34_prev5 = df['EMA34'].iloc[-6]
        if is_bull and latest['EMA34'] <= ema34_prev5: return None
        if is_bear and latest['EMA34'] >= ema34_prev5: return None

        # 3. ADX Filter: Above 30 and RISING
        if latest['ADX'] <= self.adx_threshold or latest['ADX'] <= prev1['ADX']: return None

        # 4. Balanced DI Momentum (Jump > 5.0)
        di_jump = (latest['DIPlus'] - prev2['DIPlus']) if is_bull else (latest['DIMinus'] - prev2['DIMinus'])
        if di_jump < 5.0: return None

        # 5. Balanced Proximity (Within 0.30%)
        dist_to_ema = abs(latest['Close'] - latest['EMA13']) / latest['Close']
        if dist_to_ema > 0.0030: return None

        return {
            "symbol": symbol, "name": name, "type": pair_type,
            "signal": "BUY" if is_bull else "SELL",
            "score": round(70.0 + min(di_jump, 20.0), 2),
            "price": round(float(latest['Close']), 5),
            "is_power_signal": True,
            "indicators": {
                "ADX": round(float(latest['ADX']), 2),
                "di_momentum": round(di_jump, 2),
                "dist_ema": round(dist_to_ema * 100, 3)
            },
            "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name)
        }
