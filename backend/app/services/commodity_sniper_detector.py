"""
Commodity Sniper Strategy Detector
Optimized version of SilverSniper for commodity markets (WHEAT, BCO, etc.)

Key Adaptations:
- Time filters to avoid high-loss hours
- Optional FVG requirement (configurable)
- Cooldown period between trades
- Configurable squeeze and ADX thresholds
- No volume filters (proven harmful for commodities)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import timedelta
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy


class CommoditySniperDetector(ForexStrategy):
    """
    Commodity Sniper Strategy:
    - Base: 5m Squeeze Breakout
    - Confirmation 1: 15m Trend (DI+/DI- and ADX)
    - Confirmation 2: Optional FVG (Fair Value Gap) mitigation
    - Enhancement 1: Time filters (avoid high-loss hours)
    - Enhancement 2: Cooldown period (prevent overtrading)
    """

    # Time filters based on backtest analysis
    HIGH_LOSS_HOURS = {
        'WHEAT_USD': [8, 11, 15],  # 73% of losses occurred in these hours
        'BCO_USD': [8, 14, 15]     # 41% of losses occurred in these hours
    }

    def __init__(self,
                 squeeze_threshold: float = 1.3,
                 adx_min: float = 20.0,
                 require_fvg: bool = False,
                 cooldown_hours: int = 0):
        """
        Initialize Commodity Sniper detector.

        Args:
            squeeze_threshold: Multiplier for BB_Width minimum (1.2-1.5)
            adx_min: Minimum ADX for trend confirmation (20-25)
            require_fvg: Whether to require FVG mitigation (True/False)
            cooldown_hours: Hours to wait after exit before next trade (0-6)
        """
        self.squeeze_threshold = squeeze_threshold
        self.adx_min = adx_min
        self.require_fvg = require_fvg
        self.cooldown_hours = cooldown_hours
        self.last_exit_time = {}  # Track per symbol

    def get_name(self) -> str:
        return "CommoditySniper"

    def _check_time_filter(self, timestamp, symbol: str) -> bool:
        """
        Check if current time is in high-loss hours for this symbol.

        Returns:
            True if time is ALLOWED, False if BLOCKED
        """
        if symbol not in self.HIGH_LOSS_HOURS:
            return True  # No filter for this symbol

        entry_hour = timestamp.hour
        if entry_hour in self.HIGH_LOSS_HOURS[symbol]:
            return False  # Blocked hour

        return True  # Allowed

    def _check_cooldown(self, timestamp, symbol: str) -> bool:
        """
        Check if enough time has passed since last exit.

        Returns:
            True if cooldown period has passed, False if still in cooldown
        """
        if self.cooldown_hours == 0:
            return True  # No cooldown

        if symbol not in self.last_exit_time:
            return True  # No previous exit

        hours_since_exit = (timestamp - self.last_exit_time[symbol]).total_seconds() / 3600

        if hours_since_exit < self.cooldown_hours:
            return False  # Still in cooldown

        return True  # Cooldown passed

    def record_exit(self, timestamp, symbol: str):
        """
        Record exit time for cooldown tracking.
        Called externally after trade exit.
        """
        self.last_exit_time[symbol] = timestamp

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 3.0, spread: float = 0.0) -> Optional[Dict]:
        """
        Analyze market data for entry signals.

        Args:
            data: Dict with 'base' (5m) and 'htf' (15m) dataframes
            symbol: Asset symbol (e.g., 'WHEAT_USD')
            target_rr: Target risk:reward ratio
            spread: Spread cost as decimal (e.g., 0.0006 for 0.06%)

        Returns:
            Signal dict if conditions met, None otherwise
        """
        df_5m = data.get('base')
        df_15m = data.get('htf')

        if df_5m is None or len(df_5m) < 100:
            return None

        # Ensure indicators are added
        if 'Bull_FVG' not in df_5m.columns:
            df_5m = TechnicalIndicators.add_all_indicators(df_5m)

        latest_5m = df_5m.iloc[-1]
        prev_5m = df_5m.iloc[-2]
        current_time = latest_5m.name

        # FILTER 1: Time Filter (Block high-loss hours)
        if not self._check_time_filter(current_time, symbol):
            return None

        # FILTER 2: Cooldown Period
        if not self._check_cooldown(current_time, symbol):
            return None

        # FILTER 3: 5m Squeeze Detection
        # Calculate recent min width (excluding current candle)
        min_width_96 = df_5m['BB_Width'].iloc[-97:-1].min()
        is_squeeze = latest_5m['BB_Width'] <= min_width_96 * self.squeeze_threshold

        if not is_squeeze:
            return None

        # FILTER 4: 5m Breakout Detection
        breakout_up = (latest_5m['Close'] > latest_5m['BB_Upper']) and (prev_5m['Close'] <= prev_5m['BB_Upper'])
        breakout_down = (latest_5m['Close'] < latest_5m['BB_Lower']) and (prev_5m['Close'] >= prev_5m['BB_Lower'])

        if not (breakout_up or breakout_down):
            return None

        # FILTER 5: 15m HTF Trend Confirmation
        if df_15m is not None and len(df_15m) >= 20:
            if 'ADX' not in df_15m.columns:
                df_15m = TechnicalIndicators.calculate_adx(df_15m)

            latest_15m = df_15m.iloc[-1]

            if breakout_up:
                if latest_15m['DIPlus'] < latest_15m['DIMinus'] or latest_15m['ADX'] < self.adx_min:
                    return None
            elif breakout_down:
                if latest_15m['DIMinus'] < latest_15m['DIPlus'] or latest_15m['ADX'] < self.adx_min:
                    return None
        else:
            # If no 15m data, we can't confirm trend. Skip.
            return None

        # FILTER 6: FVG Mitigation Check (Optional)
        has_recent_fvg = True  # Default to True if not required
        if self.require_fvg:
            # Check if there was an FVG in the last 5 candles
            recent_5m = df_5m.iloc[-6:-1]
            if breakout_up:
                has_recent_fvg = recent_5m['Bull_FVG'].any()
            else:
                has_recent_fvg = recent_5m['Bear_FVG'].any()

            if not has_recent_fvg:
                return None

        # All filters passed - Generate signal
        signal = "BUY" if breakout_up else "SELL"
        price = float(latest_5m['Close'])
        bb_middle = float(latest_5m['BB_Middle'])

        # Calculate Stop Loss
        stop_loss = bb_middle

        # HARDENING: Ensure minimum distance for SL (0.5%) + SPREAD PROTECTION
        padding = spread if spread > 0 else (price * 0.0005)
        min_dist = price * 0.005

        if signal == "BUY":
            stop_loss = min(stop_loss, price - min_dist)
            stop_loss -= padding
        else:  # SELL
            stop_loss = max(stop_loss, price + min_dist)
            stop_loss += padding

        risk = abs(price - stop_loss)
        if risk == 0:
            return None

        take_profit = price + (risk * target_rr if signal == "BUY" else -risk * target_rr)

        return {
            "signal": signal,
            "score": 80.0,  # Base score for commodity signals
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": current_time.isoformat() if hasattr(current_time, 'isoformat') else str(current_time),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX_15m": round(float(latest_15m['ADX']), 1),
                "BB_Width": round(float(latest_5m['BB_Width']), 4),
                "is_squeeze": True,
                "has_fvg": has_recent_fvg,
                "squeeze_threshold": self.squeeze_threshold,
                "adx_min": self.adx_min
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
