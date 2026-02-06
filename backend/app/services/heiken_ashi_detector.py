"""
Heiken Ashi Bollinger Band Swing Strategy Detector - Hardened Version

Logic:
- Uses Heiken Ashi candles for noise filtering.
- Uses Bollinger Bands calculated on Heiken Ashi Close prices.
- Trend filter: SMA 200 (Standard Close).
- HTF Filter: 4H SMA 200 alignment.
- Momentum Filter: ADX > 25.
- Freshness Filter: HA BB Cross within last 3 bars.
- Entry (BUY): 
    - Heiken Ashi Close > Heiken Ashi Middle BB.
    - Heiken Ashi Candle is Green (HA_Close > HA_Open).
    - Standard Close > SMA 200.
- Stop Loss: Minimum Low of previous 3 regular candles.
- Exit: HA Close crosses below HA Middle BB (Trend Trail).
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class HeikenAshiDetector(ForexStrategy):
    def __init__(self, bb_period: int = 20, bb_std: float = 2.0, sma_period: int = 200, adx_min: float = 22.0, freshness_window: int = 4):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.sma_period = sma_period
        self.adx_min = adx_min
        self.freshness_window = freshness_window

    def get_name(self) -> str:
        return "HeikenAshi"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 3.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        df = data.get('base')
        df_htf = data.get('htf')
        
        if df is None or len(df) < self.sma_period + 20:
            return None

        # 1. HTF Filter (4H Trend Alignment)
        htf_trend = 0 # 1 for bullish, -1 for bearish, 0 for neutral/none
        if df_htf is not None and len(df_htf) > self.sma_period:
            # Ensure HTF has indicators
            if f'SMA{self.sma_period}' not in df_htf.columns:
                df_htf = TechnicalIndicators.add_all_indicators(df_htf, sma_period=self.sma_period)
            
            latest_htf = df_htf.iloc[-1]
            if latest_htf['Close'] > latest_htf[f'SMA{self.sma_period}']:
                htf_trend = 1
            elif latest_htf['Close'] < latest_htf[f'SMA{self.sma_period}']:
                htf_trend = -1
        
        # Add standard indicators to base
        df = TechnicalIndicators.add_all_indicators(df, sma_period=self.sma_period)
        
        # 2. ADX Filter
        if df['ADX'].iloc[-1] < self.adx_min:
            return None

        # Calculate Heiken Ashi
        ha_df = TechnicalIndicators.calculate_heiken_ashi(df)
        
        # Calculate BB on HA prices
        bb_mid, bb_upper, bb_lower = TechnicalIndicators.calculate_ha_bollinger_bands(
            ha_df, period=self.bb_period, std_dev=self.bb_std
        )
        
        ha_df['HA_BB_Middle'] = bb_mid
        
        # 3. Freshness Filter: HA BB Cross within last N bars
        ha_df['is_above'] = ha_df['HA_Close'] > ha_df['HA_BB_Middle']
        ha_df['cross_up'] = (ha_df['is_above']) & (~ha_df['is_above'].shift(1, fill_value=False))
        ha_df['cross_down'] = (~ha_df['is_above']) & (ha_df['is_above'].shift(1, fill_value=True))
        
        recent_cross_up = ha_df['cross_up'].iloc[-self.freshness_window:].any()
        recent_cross_down = ha_df['cross_down'].iloc[-self.freshness_window:].any()

        latest = ha_df.iloc[-1]
        sma_col = f'SMA{self.sma_period}'
        
        # BUY Rules
        is_green = latest['HA_Close'] > latest['HA_Open']
        above_bb_mid = latest['HA_Close'] > latest['HA_BB_Middle']
        above_sma = latest['Close'] > latest[sma_col]
        
        if is_green and above_bb_mid and above_sma and recent_cross_up and htf_trend >= 0:
            price = float(latest['Close'])
            stop_loss = float(df['Low'].iloc[-3:].min())
            
            if price - stop_loss < spread:
                stop_loss = price - (spread * 2)
            
            risk = abs(price - stop_loss)
            take_profit = price + (risk * target_rr)
            
            return {
                "signal": "BUY",
                "score": 85.0,
                "strategy": self.get_name(),
                "symbol": symbol,
                "price": price,
                "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "indicators": {
                    "HA_Close": round(float(latest['HA_Close']), 2),
                    "HA_BB_Middle": round(float(latest['HA_BB_Middle']), 2),
                    "ADX": round(float(df['ADX'].iloc[-1]), 1),
                    "is_green": True
                }
            }
            
        # SELL Rules
        is_red = latest['HA_Close'] < latest['HA_Open']
        below_bb_mid = latest['HA_Close'] < latest['HA_BB_Middle']
        below_sma = latest['Close'] < latest[sma_col]
        
        if is_red and below_bb_mid and below_sma and recent_cross_down and htf_trend <= 0:
            price = float(latest['Close'])
            stop_loss = float(df['High'].iloc[-3:].max())
            
            if stop_loss - price < spread:
                stop_loss = price + (spread * 2)
            
            risk = abs(stop_loss - price)
            take_profit = price - (risk * target_rr)
            
            return {
                "signal": "SELL",
                "score": 85.0,
                "strategy": self.get_name(),
                "symbol": symbol,
                "price": price,
                "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "indicators": {
                    "HA_Close": round(float(latest['HA_Close']), 2),
                    "HA_BB_Middle": round(float(latest['HA_BB_Middle']), 2),
                    "ADX": round(float(df['ADX'].iloc[-1]), 1),
                    "is_green": False
                }
            }
            
        return None

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        df = data.get('base')
        if df is None or len(df) < 20:
            return None

        # Calculate HA
        ha_df = TechnicalIndicators.calculate_heiken_ashi(df)
        
        # Calculate BB on HA
        bb_mid, _, _ = TechnicalIndicators.calculate_ha_bollinger_bands(ha_df, period=self.bb_period)
        ha_df['HA_BB_Middle'] = bb_mid
        
        latest = ha_df.iloc[-1]
        
        exit_signal = False
        reason = ""
        
        if direction == "BUY":
            # HA Close crosses below HA Middle BB
            if latest['HA_Close'] < latest['HA_BB_Middle']:
                exit_signal = True
                reason = "HA Close crossed below HA Middle BB"
        
        elif direction == "SELL":
            # HA Close crosses above HA Middle BB
            if latest['HA_Close'] > latest['HA_BB_Middle']:
                exit_signal = True
                reason = "HA Close crossed above HA Middle BB"
                
        if exit_signal:
            return {
                "exit_signal": True,
                "reason": reason
            }
            
        return None