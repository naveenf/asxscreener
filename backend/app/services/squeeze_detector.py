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

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0) -> Optional[Dict]:
        df = data.get('base')
        df_htf = data.get('htf')
        
        if df is None or len(df) < 50: return None

        # Add indicators to base timeframe
        df = TechnicalIndicators.add_all_indicators(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # 1. Detect Squeeze Condition (Recent Low Volatility)
        # Calculate recent min width
        min_width_96 = df['BB_Width'].iloc[-96:].min()
        is_narrow = latest['BB_Width'] <= min_width_96 * 1.5
        
        # 2. Detect Breakout (Expansion)
        # Price breaking out of Bands (INITIAL CROSS ONLY)
        breakout_up = (latest['Close'] > latest['BB_Upper']) and (prev['Close'] <= prev['BB_Upper'])
        breakout_down = (latest['Close'] < latest['BB_Lower']) and (prev['Close'] >= prev['BB_Lower'])
        
        if not (breakout_up or breakout_down): return None
        
        # 3. HTF Confirmation (Energy Building)
        htf_confirmed = True
        if df_htf is not None and len(df_htf) > 20:
            df_htf = TechnicalIndicators.add_all_indicators(df_htf)
            latest_htf = df_htf.iloc[-1]
            if latest_htf['ADX'] > 40: 
                htf_confirmed = False 
        
        if not htf_confirmed: return None

        # 4. Volume Confirmation (Dynamic based on Asset Class)
        # Research Findings (2026-01-13):
        # - Gold/Forex: Requires Volume (Original 5-candle avg)
        # - Indices: Requires Volume (Faster 3-candle avg)
        # - Commodities (Oil, Copper, Ag): Volume filter hurts performance. Disabled.
        
        indices = ['NAS100_USD', 'JP225_USD', 'UK100_GBP']
        commodities_no_vol = ['BCO_USD', 'XCU_USD', 'CORN_USD', 'SOYBN_USD', 'WHEAT_USD']
        
        vol_confirmed = True
        
        if symbol in commodities_no_vol:
            # Disable volume filter for Commodities (except Precious Metals)
            pass
            
        elif 'Volume' in df.columns and latest['Volume'] > 0:
            if symbol in indices:
                # Indices: Use 3-candle average (more sensitive)
                # iloc[-4:-1] takes the 3 candles before current (-4, -3, -2)
                avg_vol = df['Volume'].iloc[-4:-1].mean()
            else:
                # Default (Gold/Forex): Use 5-candle average (more robust)
                # iloc[-6:-1] takes the 5 candles before current (-6, -5, -4, -3, -2)
                avg_vol = df['Volume'].iloc[-6:-1].mean()
                
            if avg_vol > 0 and latest['Volume'] < avg_vol * 1.2:
                vol_confirmed = False 
        
        if not vol_confirmed: return None

        signal = "BUY" if breakout_up else "SELL"
        price = float(latest['Close'])
        stop_loss = float(latest['BB_Middle'])
        
        # Calculate Take Profit based on R/R
        risk = abs(price - stop_loss)
        take_profit = price + (risk * target_rr if signal == "BUY" else -risk * target_rr)
        
        return {
            "signal": signal,
            "score": 80.0,
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX": round(float(latest.get('ADX', 0)), 1),
                "BB_Width": round(float(latest.get('BB_Width', 0)), 4),
                "vol_accel": 0.0,
                "di_momentum": 0.0,
                "DIPlus": 0.0,
                "DIMinus": 0.0,
                "is_power_volume": False,
                "is_power_momentum": False
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Exit if price crosses the Middle Bollinger Band (SMA 20).
        """
        df = data.get('base')
        if df is None or len(df) < 20: return None
        
        # Ensure indicators are present
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