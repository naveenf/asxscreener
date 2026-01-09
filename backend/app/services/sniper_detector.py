"""
Sniper Strategy Detector
Implements Group-Based logic (Caskets) with MTF confirmation.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from .indicators import TechnicalIndicators

class SniperDetector:
    def __init__(self, adx_threshold: float = 30.0):
        self.adx_threshold = adx_threshold

    def get_casket(self, symbol: str) -> str:
        momentum = ['NQ=F', '^N225', 'USDJPY=X', 'GBPJPY=X', 'EURJPY=X', 'AUDJPY=X', 'CADJPY=X', 'CHFJPY=X', 'BTC-USD', 'LTC-USD']
        steady = ['EURUSD=X', 'GBPUSD=X', 'AUDUSD=X', 'NZDUSD=X', 'USDCHF=X', 'USDCAD=X', 'EURGBP=X', 'EURAUD=X', 'GBPAUD=X', 'AUDNZD=X', 'GC=F', 'SI=F', 'HG=F', '^FTSE']
        if symbol in momentum: return 'Momentum'
        if symbol in steady: return 'Steady'
        return 'Cyclical'

    def analyze(self, df_15m: pd.DataFrame, symbol: str) -> Optional[Dict]:
        if len(df_15m) < 220: return None
        
        # 1. Higher Timeframe (1H) Trend Filter
        df_1h = TechnicalIndicators.resample_to_1h(df_15m)
        df_1h = TechnicalIndicators.add_all_indicators(df_1h)
        if len(df_1h) < 2: return None
        
        latest_1h = df_1h.iloc[-1]
        htf_bull = latest_1h['Close'] > latest_1h['EMA34'] and latest_1h['ADX'] > 25
        htf_bear = latest_1h['Close'] < latest_1h['EMA34'] and latest_1h['ADX'] > 25
        
        if not (htf_bull or htf_bear): return None

        # 2. Execution Timeframe (15m)
        df_15m = TechnicalIndicators.add_all_indicators(df_15m)
        latest_15 = df_15m.iloc[-1]
        prev_15 = df_15m.iloc[-2]
        casket = self.get_casket(symbol)
        
        # Base Crossover Logic
        is_buy = htf_bull and latest_15['DIPlus'] > latest_15['DIMinus'] and prev_15['DIPlus'] <= prev_15['DIMinus']
        is_sell = htf_bear and latest_15['DIMinus'] > latest_15['DIPlus'] and prev_15['DIMinus'] <= prev_15['DIPlus']
        
        if not (is_buy or is_sell): return None

        # 3. Casket-Specific Filters (Dry Run - Proposed Logic)
        if casket == 'Momentum':
            # Focus: DI Jump and Volume Surge
            di_jump = (latest_15['DIPlus'] - df_15m['DIPlus'].iloc[-3]) if is_buy else (latest_15['DIMinus'] - df_15m['DIMinus'].iloc[-3])
            if di_jump < 7.0: return None
            
        elif casket == 'Steady':
            # Focus: EMA Proximity (Buying the low-risk start)
            dist_to_ema = abs(latest_15['Close'] - latest_15['EMA13']) / latest_15['Close']
            if dist_to_ema > 0.0020: return None
            
        elif casket == 'Cyclical':
            # Focus: BB Squeeze (Breakout from 24h low volatility)
            min_width_24h = df_15m['BB_Width'].iloc[-96:].min()
            if latest_15['BB_Width'] > min_width_24h * 1.5: pass # Breakout confirmed
            else: return None

        return {
            "symbol": symbol, "casket": casket,
            "signal": "BUY" if is_buy else "SELL",
            "price": float(latest_15['Close']),
            "timestamp": latest_15.name,
            "sl": float(latest_15['EMA13'])
        }
