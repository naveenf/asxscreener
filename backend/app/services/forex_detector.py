"""
Forex Signal Detection Module - Balanced Gold Standard
The "Sweet Spot" found through extensive backtesting.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, List
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class ForexDetector(ForexStrategy):
    def __init__(self, adx_threshold: float = 30.0, di_threshold: float = 20.0, sma_period: int = 200):
        self.adx_threshold = adx_threshold
        self.di_threshold = di_threshold
        self.sma_period = sma_period
        self.sma_column = f'SMA{sma_period}'

    def get_name(self) -> str:
        return "TrendFollowing"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        df = data.get('base')
        df_htf = data.get('htf')

        if df is None or len(df) < self.sma_period + 20: return None
        
        # Add indicators
        df = TechnicalIndicators.add_all_indicators(df, adx_period=14, sma_period=self.sma_period)

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

        # 6. HTF Bias (EMA Trend) - Optional Filter
        if df_htf is not None and len(df_htf) > 50:
            df_htf = TechnicalIndicators.add_all_indicators(df_htf)
            latest_htf = df_htf.iloc[-1]
            htf_bull = latest_htf['Close'] > latest_htf['EMA34']
            htf_bear = latest_htf['Close'] < latest_htf['EMA34']
            
            if is_bull and not htf_bull: return None
            if is_bear and not htf_bear: return None

        price = float(latest['Close'])
        stop_loss = float(latest['EMA34'])
        
        # Calculate TP
        risk = abs(price - stop_loss)
        signal_type = "BUY" if is_bull else "SELL"
        take_profit = price + (risk * target_rr if signal_type == "BUY" else -risk * target_rr)

        return {
            "signal": signal_type,
            "score": min(round(70.0 + min(di_jump, 20.0), 2), 100.0),
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX": round(float(latest['ADX']), 2),
                "di_momentum": round(di_jump, 2),
                "dist_ema": round(dist_to_ema * 100, 3),
                "vol_accel": 0.0,
                "DIPlus": float(latest['DIPlus']),
                "DIMinus": float(latest['DIMinus']),
                "is_power_volume": False,
                "is_power_momentum": di_jump > 5.0
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Exit if trend reverses (Price crosses EMA34).
        """
        df = data.get('base')
        if df is None or len(df) < 50: return None
        
        if 'EMA34' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(df, sma_period=self.sma_period)
            
        latest = df.iloc[-1]
        close = float(latest['Close'])
        ema34 = float(latest['EMA34'])
        
        exit_signal = False
        reason = None
        
        if direction == "BUY":
            if close < ema34:
                exit_signal = True
                reason = f"Price ({close:.4f}) crossed below EMA34 ({ema34:.4f})"
        elif direction == "SELL":
            if close > ema34:
                exit_signal = True
                reason = f"Price ({close:.4f}) crossed above EMA34 ({ema34:.4f})"
                
        if exit_signal:
            return {
                "exit_signal": True,
                "reason": reason
            }
        return None
