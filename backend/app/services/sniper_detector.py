"""
Sniper Strategy Detector
Implements Group-Based logic (Caskets) with MTF confirmation.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
from typing import Dict, Optional
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

class SniperDetector(ForexStrategy):
    def __init__(self, adx_threshold: float = 30.0):
        self.adx_threshold = adx_threshold
        self.caskets = self._load_caskets()

    def get_name(self) -> str:
        return "Sniper"

    def _load_caskets(self) -> Dict[str, list]:
        try:
            path = PROJECT_ROOT / 'data' / 'metadata' / 'forex_baskets.json'
            if path.exists():
                with open(path, 'r') as f:
                    return json.load(f)
            return {}
        except Exception:
            return {}

    def get_casket(self, symbol: str) -> str:
        if symbol in self.caskets.get('momentum', []): return 'Momentum'
        if symbol in self.caskets.get('steady', []): return 'Steady'
        return 'Cyclical'

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        df_15m = data.get('base')
        df_1h = data.get('htf')
        
        if df_15m is None or len(df_15m) < 220: return None
        if df_1h is None or len(df_1h) < 2: return None
        
        # 1. Higher Timeframe (HTF) Trend Filter
        df_1h = TechnicalIndicators.add_all_indicators(df_1h)
        
        latest_1h = df_1h.iloc[-1]
        htf_bull = latest_1h['Close'] > latest_1h['EMA34'] and latest_1h['ADX'] > 25
        htf_bear = latest_1h['Close'] < latest_1h['EMA34'] and latest_1h['ADX'] > 25
        
        if not (htf_bull or htf_bear): return None

        # 2. Execution Timeframe
        df_15m = TechnicalIndicators.add_all_indicators(df_15m)
        latest_15 = df_15m.iloc[-1]
        prev_15 = df_15m.iloc[-2]
        casket = self.get_casket(symbol)
        
        # Base Crossover Logic
        is_buy = htf_bull and latest_15['DIPlus'] > latest_15['DIMinus'] and prev_15['DIPlus'] <= prev_15['DIMinus']
        is_sell = htf_bear and latest_15['DIMinus'] > latest_15['DIPlus'] and prev_15['DIMinus'] <= prev_15['DIPlus']
        
        if not (is_buy or is_sell): return None

        # 3. Casket-Specific Filters
        score = 60.0 # Base score for signal
        
        di_jump = 0.0
        vol_accel = 0.0

        if casket == 'Momentum':
            # Filter 1: DI Momentum Jump
            di_jump = (latest_15['DIPlus'] - df_15m['DIPlus'].iloc[-3]) if is_buy else (latest_15['DIMinus'] - df_15m['DIMinus'].iloc[-3])
            if di_jump < 7.0: return None
            score += min(di_jump, 20.0)

            # Filter 2: Volume Surge
            avg_vol_5 = df_15m['Volume'].iloc[-6:-1].mean()
            if avg_vol_5 > 0:  
                vol_accel = latest_15['Volume'] / avg_vol_5
                if vol_accel < 2.0:
                    return None
                score += 10.0
            
        elif casket == 'Steady':
            # Filter 1: EMA Proximity
            dist_to_15m_ema = abs(latest_15['Close'] - latest_15['EMA13']) / latest_15['Close']
            if dist_to_15m_ema > 0.0020: return None
            score += (0.0020 - dist_to_15m_ema) * 10000

            # Filter 2: HTF EMA Pullback
            dist_to_1h_ema = abs(latest_1h['Close'] - latest_1h['EMA13']) / latest_1h['Close']
            if dist_to_1h_ema > 0.0080:
                return None
            
        elif casket == 'Cyclical':
            # Focus: BB Squeeze
            min_width_24h = df_15m['BB_Width'].iloc[-96:].min()
            if latest_15['BB_Width'] > min_width_24h * 1.5: 
                score += 20.0
            else: return None

        price = float(latest_15['Close'])
        bb_middle = float(latest_15['BB_Middle'])
        
        # Calculate initial SL based on BB_Middle (Standard for Sniper Strategy)
        stop_loss = bb_middle
        signal_type = "BUY" if is_buy else "SELL"
        
        # SPREAD / PADDING CONFIGURATION
        # User requirement: "SL should be BB_Middle + spread"
        # Use provided spread or default to 0.05% of price if missing/zero
        padding = spread if spread > 0 else (price * 0.0005)

        # HARDENING: Ensure minimum distance for SL (0.5% for commodities/forex)
        min_dist = price * 0.005
        
        if signal_type == "BUY":
            # SL below price
            stop_loss = min(stop_loss, price - min_dist)
            # Apply Spread padding (Lower the SL by the spread amount)
            stop_loss -= padding
        else: # SELL
            # SL above price
            stop_loss = max(stop_loss, price + min_dist)
            # Apply Spread padding (Raise the SL by the spread amount)
            stop_loss += padding

        # Calculate TP
        risk = abs(price - stop_loss)
        take_profit = price + (risk * target_rr if signal_type == "BUY" else -risk * target_rr)

        return {
            "signal": signal_type,
            "score": min(round(score, 1), 100.0),
            "strategy": self.get_name(),
            "symbol": symbol,
            "casket": casket,
            "price": price,
            "timestamp": latest_15.name.isoformat() if hasattr(latest_15.name, 'isoformat') else str(latest_15.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX": round(float(latest_15['ADX']), 2),
                "di_momentum": round(di_jump, 2),
                "vol_accel": round(vol_accel, 2),
                "DIPlus": float(latest_15['DIPlus']),
                "DIMinus": float(latest_15['DIMinus']),
                "is_power_volume": vol_accel > 2.0,
                "is_power_momentum": di_jump > 7.0
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Exit if price crosses BB_Middle (SMA 20) (Trailing Stop).
        """
        df = data.get('base')
        if df is None or len(df) < 50: return None
        
        if 'BB_Middle' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(df)
            
        latest = df.iloc[-1]
        close = float(latest['Close'])
        bb_middle = float(latest['BB_Middle'])
        
        exit_signal = False
        reason = None
        
        if direction == "BUY":
            if close < bb_middle:
                exit_signal = True
                reason = f"Price ({close:.4f}) crossed below BB Middle ({bb_middle:.4f})"
        elif direction == "SELL":
            if close > bb_middle:
                exit_signal = True
                reason = f"Price ({close:.4f}) crossed above BB Middle ({bb_middle:.4f})"
                
        if exit_signal:
            return {
                "exit_signal": True,
                "reason": reason
            }
        return None
