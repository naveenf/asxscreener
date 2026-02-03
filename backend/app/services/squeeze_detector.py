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
    # Asset-specific time filters (hours to avoid trading in UTC)
    ASSET_TIME_FILTERS = {
        'USD_JPY': [8, 20],      # Forex: Avoid major news hours
        'AUD_USD': [0, 8, 20],   # Add Sydney open (00:00 UTC)
        'USD_CHF': [8, 20],      # Most whipsaw-prone
        'NAS100_USD': [8, 13, 14, 20],   # Indices: Market open volatility
        'UK100_GBP': [8, 13, 14, 20],
        'XCU_USD': [8, 13, 14, 20]
    }

    # Cooldown period in hours to prevent overtrading
    COOLDOWN_HOURS = 2

    # Asset-specific FVG requirements (Phase 2 Enhancement)
    FVG_REQUIRED = {
        'WHEAT_USD': True,    # Proven effective
        'NAS100_USD': False,   # Indices benefit from FVG - Disabled to increase frequency
        'UK100_GBP': False,
        'BCO_USD': False,     # Optional
        'XCU_USD': False,     # Test both
        'USD_JPY': False,     # Forex - optional
        'AUD_USD': False,
        'USD_CHF': False
    }

    def __init__(self, squeeze_threshold: float = 0.0020, adx_max: float = 25.0):
        self.squeeze_threshold = squeeze_threshold
        self.adx_max = adx_max
        self.last_signal_time = {}  # Track last signal time per symbol

    def get_name(self) -> str:
        return "Squeeze"

    def _is_valid_trade_time(self, timestamp, symbol: str) -> bool:
        """
        Filter out high-volatility news hours to prevent whipsaws.
        Returns False if current hour should be avoided for this symbol.
        """
        excluded_hours = self.ASSET_TIME_FILTERS.get(symbol, [])
        if not excluded_hours:
            return True  # No time filter for this symbol

        hour = timestamp.hour
        return hour not in excluded_hours

    def _check_cooldown(self, symbol: str, current_time) -> bool:
        """
        Prevent trades within cooldown period to reduce overtrading.
        Returns False if we're still in cooldown period.
        """
        if symbol not in self.last_signal_time:
            return True  # No previous signal, cooldown doesn't apply

        time_diff = current_time - self.last_signal_time[symbol]
        hours_since = time_diff.total_seconds() / 3600

        return hours_since >= self.COOLDOWN_HOURS

    def _calculate_dynamic_rr(self, df: pd.DataFrame, symbol: str, default_rr: float) -> float:
        """
        Calculate dynamic Risk:Reward ratio based on volatility (Phase 2 Enhancement).

        Higher volatility assets can achieve bigger moves, so we use higher R:R.
        Lower volatility assets need more conservative targets.

        Returns:
            float: Adjusted R:R ratio (1.5 to 2.5)
        """
        latest = df.iloc[-1]

        # Use ATR if available, otherwise use default
        if 'ATR' not in df.columns or pd.isna(latest['ATR']):
            return default_rr

        atr = float(latest['ATR'])
        price = float(latest['Close'])

        if price == 0:
            return default_rr

        # Calculate volatility ratio (ATR as percentage of price)
        volatility_ratio = atr / price

        # Asset-specific baseline adjustments
        # Forex: Lower baseline (1.5-2.0)
        # Indices: Medium baseline (2.0-2.5)
        # Commodities: Higher baseline (2.5-3.0)
        forex_pairs = ['USD_JPY', 'AUD_USD', 'USD_CHF', 'EUR_USD', 'GBP_USD']
        indices = ['NAS100_USD', 'JP225_USD', 'UK100_GBP', 'XCU_USD']

        if symbol in forex_pairs:
            # Forex: 1.5-2.0 R:R
            if volatility_ratio > 0.015:  # 1.5%+ daily range
                return 2.0
            else:
                return 1.5
        elif symbol in indices:
            # Indices: 2.0-2.5 R:R
            if volatility_ratio > 0.02:  # 2%+ daily range
                return 2.5
            else:
                return 2.0
        else:
            # Commodities and others: 2.5-3.0 R:R
            if volatility_ratio > 0.02:  # 2%+ daily range
                return 3.0
            elif volatility_ratio > 0.01:  # 1-2% daily range
                return 2.5
            else:
                return 2.0

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0, spread: float = 0.0) -> Optional[Dict]:
        df = data.get('base')
        df_htf = data.get('htf')
        
        if df is None or len(df) < 50: return None

        # Add indicators to base timeframe
        df = TechnicalIndicators.add_all_indicators(df)
        df = df.copy() # Ensure we work on a copy to avoid SettingWithCopyWarning
        
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Time filter check (Phase 1 Optimization)
        if not self._is_valid_trade_time(latest.name, symbol):
            return None

        # Cooldown check (Phase 1 Optimization)
        if not self._check_cooldown(symbol, latest.name):
            return None

        # 1. Detect Squeeze Condition (TTM Squeeze Style)
        # Squeeze = BB inside Keltner Channel
        df['is_sqz'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])
        
        # We want to see a squeeze in the last 5 candles
        had_squeeze = df['is_sqz'].iloc[-6:-1].any()
        
        # 2. Detect Breakout (Expansion)
        # Price breaking out of Bands (INITIAL CROSS ONLY)
        breakout_up = (latest['Close'] > latest['BB_Upper']) and (prev['Close'] <= prev['BB_Upper'])
        breakout_down = (latest['Close'] < latest['BB_Lower']) and (prev['Close'] >= prev['BB_Lower'])
        
        if not (breakout_up or breakout_down): return None
        if not had_squeeze: return None

        # 3. Momentum Confirmation
        # Ensure momentum is positive for BUYS and negative for SELLS
        mom_confirmed = False
        if breakout_up and latest['Momentum'] > 0:
            mom_confirmed = True
        elif breakout_down and latest['Momentum'] < 0:
            mom_confirmed = True
            
        if not mom_confirmed: return None
        
        # 4. HTF Confirmation
        htf_confirmed = True
        if df_htf is not None and len(df_htf) > 20:
            df_htf = TechnicalIndicators.add_all_indicators(df_htf)
            latest_htf = df_htf.iloc[-1]
            # HTF Trend alignment: ADX > 23 (relaxed from 25)
            if latest_htf['ADX'] < 23:
                htf_confirmed = False
            elif breakout_up and latest_htf['DIPlus'] < latest_htf['DIMinus']:
                htf_confirmed = False
            elif breakout_down and latest_htf['DIMinus'] < latest_htf['DIPlus']:
                htf_confirmed = False
        
        if not htf_confirmed: return None

        # 5. Volume Confirmation (Dynamic based on Asset Class)
        # Research Findings (2026-01-13):
        # - Gold/Forex: Requires Volume (Original 5-candle avg)
        # - Indices: Requires Volume (Faster 3-candle avg)
        # - Commodities (Oil, Copper, Ag): Volume filter hurts performance. Disabled.
        
        indices = ['NAS100_USD', 'JP225_USD', 'UK100_GBP']
        commodities_no_vol = ['BCO_USD', 'XCU_USD', 'WHEAT_USD']
        
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

        # 6. Fair Value Gap (FVG) Confirmation (Phase 2 Enhancement)
        # Only required for specific assets (indices, some commodities)
        if self.FVG_REQUIRED.get(symbol, False):
            # Check if current candle has or is near an FVG
            if 'Bull_FVG' not in df.columns or 'Bear_FVG' not in df.columns:
                # FVG columns should exist from add_all_indicators, but safeguard
                pass
            else:
                fvg_confirmed = False
                if breakout_up:
                    # For bullish breakout, check for bullish FVG
                    # Check current candle or previous 2 candles
                    fvg_confirmed = df['Bull_FVG'].iloc[-3:].any()
                elif breakout_down:
                    # For bearish breakout, check for bearish FVG
                    fvg_confirmed = df['Bear_FVG'].iloc[-3:].any()

                if not fvg_confirmed:
                    return None

        signal = "BUY" if breakout_up else "SELL"
        price = float(latest['Close'])
        stop_loss = float(latest['BB_Middle'])

        # Calculate dynamic R:R based on volatility (Phase 2 Enhancement)
        dynamic_rr = self._calculate_dynamic_rr(df, symbol, target_rr)

        # Calculate Take Profit based on dynamic R/R
        risk = abs(price - stop_loss)
        take_profit = price + (risk * dynamic_rr if signal == "BUY" else -risk * dynamic_rr)

        # Update last signal time for cooldown tracking
        self.last_signal_time[symbol] = latest.name

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