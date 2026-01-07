"""
Signal Detection Module

Detects entry and exit signals based on ADX/DI strategy.
Implements scoring algorithm for ranking signals.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime

from .indicators import TechnicalIndicators


class SignalDetector:
    """Detect trading signals and calculate scores."""

    def __init__(
        self,
        adx_threshold: float = 30.0,
        profit_target: float = 0.15,  # 15%
        sma_period: int = 200,
        volume_filter_enabled: bool = False,
        volume_multiplier: float = 1.5,
        atr_filter_enabled: bool = False,
        atr_min_pct: float = 3.0
    ):
        """
        Initialize signal detector.

        Args:
            adx_threshold: ADX must be above this for entry (default 30)
            profit_target: Profit target as decimal (default 0.15 = 15%)
            sma_period: SMA period for scoring bonus (default 200)
            volume_filter_enabled: Enable volume filter (default False)
            volume_multiplier: Volume must be > this * SMA(20) (default 1.5)
            atr_filter_enabled: Enable ATR volatility filter (default False)
            atr_min_pct: Minimum ATR percentage (default 3.0%)
        """
        self.adx_threshold = adx_threshold
        self.profit_target = profit_target
        self.sma_period = sma_period
        self.sma_column = f'SMA{sma_period}'
        self.volume_filter_enabled = volume_filter_enabled
        self.volume_multiplier = volume_multiplier
        self.atr_filter_enabled = atr_filter_enabled
        self.atr_min_pct = atr_min_pct

    def detect_entry_signal(self, df: pd.DataFrame) -> Dict:
        """
        Detect current entry signal with improved trend logic.

        Entry conditions:
        1. ADX > threshold (default 25)
        2. DI+ > DI- (bullish trend)
        3. ADX is rising (ADX[-1] > ADX[-2]) - Momentum confirmation
        4. Price > BB_Middle (SMA20) - Short-term momentum
        """
        if len(df) < 2:
            return {'has_signal': False, 'reason': 'Insufficient data'}

        # Get latest rows
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Check if we have valid indicator values
        required = ['ADX', 'DIPlus', 'DIMinus', 'Close', 'BB_Middle']
        if any(pd.isna(latest[col]) for col in required):
            return {'has_signal': False, 'reason': 'Insufficient data for indicators'}

        # Check entry conditions
        adx_above_threshold = latest['ADX'] > self.adx_threshold
        di_plus_above_di_minus = latest['DIPlus'] > latest['DIMinus']
        adx_rising = latest['ADX'] > prev['ADX']
        above_sma20 = latest['Close'] > latest['BB_Middle']

        # Check for fresh crossover
        fresh_crossover = False
        if not pd.isna(prev['DIPlus']) and not pd.isna(prev['DIMinus']):
            was_below = prev['DIPlus'] <= prev['DIMinus']
            now_above = latest['DIPlus'] > latest['DIMinus']
            fresh_crossover = was_below and now_above

        # Apply volume filter
        volume_ok = self._check_volume(df)

        # Apply ATR filter
        atr_ok = self._check_atr(df)

        # All conditions must be met for entry signal
        has_signal = (
            adx_above_threshold and
            di_plus_above_di_minus and
            adx_rising and
            above_sma20 and
            volume_ok and
            atr_ok
        )

        return {
            'has_signal': has_signal,
            'adx': float(latest['ADX']),
            'di_plus': float(latest['DIPlus']),
            'di_minus': float(latest['DIMinus']),
            'close': float(latest['Close']),
            'adx_above_threshold': adx_above_threshold,
            'di_plus_above_di_minus': di_plus_above_di_minus,
            'adx_rising': adx_rising,
            'above_sma20': above_sma20,
            'fresh_crossover': fresh_crossover,
            'date': latest.name
        }

    def calculate_score(self, signal_info: Dict, df: pd.DataFrame) -> float:
        """
        Calculate improved signal score.
        """
        if not signal_info.get('has_signal'):
            return 0.0

        score = 40.0  # Base score

        # ADX strength (0-25 points)
        adx = signal_info['adx']
        if adx >= self.adx_threshold:
            adx_bonus = min((adx - self.adx_threshold) * 1.5, 25.0)
            score += adx_bonus

        # DI spread (0-15 points)
        di_spread = signal_info['di_plus'] - signal_info['di_minus']
        if di_spread > 0:
            spread_bonus = min(di_spread * 0.6, 15.0)
            score += spread_bonus

        # Trend alignment (SMA200) (+10 points)
        latest = df.iloc[-1]
        if self.sma_column in latest and not pd.isna(latest[self.sma_column]):
            if latest['Close'] > latest[self.sma_column]:
                score += 10.0

        # ADX Momentum (+5 points if rising strongly)
        if signal_info.get('adx_rising'):
            score += 5.0
            
        # Fresh crossover bonus (+5 points)
        if signal_info.get('fresh_crossover'):
            score += 5.0

        return min(score, 100.0)

    def _check_volume(self, df: pd.DataFrame) -> bool:
        """
        Check if current volume meets filter criteria.

        Volume filter logic:
        - Volume must be > volume_multiplier * Volume_SMA
        - Ensures institutional participation (not just retail noise)
        - Avoids isolated volume spikes (sustained above-average volume)

        Args:
            df: DataFrame with Volume and Volume_SMA columns

        Returns:
            True if volume filter passes (or disabled), False otherwise
        """
        if not self.volume_filter_enabled:
            return True  # Filter disabled, always pass

        if 'Volume' not in df.columns or 'Volume_SMA' not in df.columns:
            # Missing required data, pass to avoid false negatives
            return True

        latest = df.iloc[-1]

        # Check if volume data is valid
        if pd.isna(latest['Volume']) or pd.isna(latest['Volume_SMA']):
            return True  # Can't filter without data, pass

        # Volume must be above threshold
        volume_threshold = latest['Volume_SMA'] * self.volume_multiplier
        current_volume_ok = latest['Volume'] > volume_threshold

        # Check for isolated spike (volume spike without sustained increase)
        # Look back 2 bars to ensure it's not just a one-bar anomaly
        sustained_volume = True
        if len(df) >= 3:
            prev_bars = df.iloc[-3:-1]  # Last 2 bars before current
            if 'Volume_SMA' in prev_bars.columns:
                # At least one of the previous 2 bars should have elevated volume
                prev_volumes = prev_bars['Volume']
                prev_smas = prev_bars['Volume_SMA']
                elevated_count = sum(prev_volumes > prev_smas * self.volume_multiplier)
                sustained_volume = elevated_count >= 1

        return current_volume_ok and sustained_volume

    def _check_atr(self, df: pd.DataFrame) -> bool:
        """
        Check if current volatility (ATR) meets filter criteria.

        ATR filter logic:
        - ATR% must be > atr_min_pct (default 3.0%)
        - Ensures sufficient price movement to reach 15% profit target
        - Low ATR stocks (<3%) unlikely to move enough in reasonable timeframe
        - Too high ATR (>8%) indicates excessive volatility/risk

        Args:
            df: DataFrame with ATR_PCT column

        Returns:
            True if ATR filter passes (or disabled), False otherwise
        """
        if not self.atr_filter_enabled:
            return True  # Filter disabled, always pass

        if 'ATR_PCT' not in df.columns:
            # Missing ATR data, pass to avoid false negatives
            return True

        latest = df.iloc[-1]

        # Check if ATR data is valid
        if pd.isna(latest['ATR_PCT']):
            return True  # Can't filter without data, pass

        # ATR percentage must be above minimum threshold
        # This ensures the stock has enough volatility to reach profit targets
        return latest['ATR_PCT'] >= self.atr_min_pct

    def detect_exit_signal(
        self,
        df: pd.DataFrame,
        entry_price: float,
        current_index: Optional[int] = None,
        entry_index: Optional[int] = None
    ) -> Dict:
        """
        Detect exit signal for an existing position.

        Exit conditions:
        1. Price >= entry_price * (1 + profit_target) [15% profit]
        2. OR DI+ crosses below DI- at ANY point after entry [trend reversal]

        Args:
            df: DataFrame with indicators
            entry_price: Entry price for the position
            current_index: Index to check (default: latest)
            entry_index: Index where position was entered (for crossover detection)

        Returns:
            Dict with exit information
        """
        if current_index is None:
            current_index = len(df) - 1

        # CRITICAL FIX: Convert negative index to positive
        if current_index < 0:
            current_index = len(df) + current_index

        if current_index < 0 or current_index >= len(df):
            return {'has_exit': False, 'reason': 'Invalid index'}

        current = df.iloc[current_index]
        current_price = current['Close']

        # Check profit target
        profit_pct = (current_price - entry_price) / entry_price
        profit_target_hit = profit_pct >= self.profit_target

        # Check for DI+ crossing below DI- at ANY point after entry
        trend_reversal = False
        reversal_date = None

        if entry_index is not None and entry_index >= 0:
            # NEW LOGIC: Scan from entry to current for any crossunder
            # Use TechnicalIndicators.detect_crossunder helper
            df_slice = df.iloc[entry_index:current_index+1].copy()

            if len(df_slice) > 1:
                crossunders = TechnicalIndicators.detect_crossunder(
                    df_slice['DIPlus'],
                    df_slice['DIMinus']
                )

                # Check if any crossunder occurred
                if crossunders.any():
                    trend_reversal = True
                    # Find first crossunder date
                    crossunder_indices = crossunders[crossunders == True].index
                    if len(crossunder_indices) > 0:
                        reversal_date = crossunder_indices[0]
        else:
            # FALLBACK: Old logic if entry_index not provided (backward compatibility)
            if current_index > 0:
                prev = df.iloc[current_index - 1]
                if not (pd.isna(prev['DIPlus']) or pd.isna(prev['DIMinus']) or
                        pd.isna(current['DIPlus']) or pd.isna(current['DIMinus'])):
                    was_above = prev['DIPlus'] >= prev['DIMinus']
                    now_below = current['DIPlus'] < current['DIMinus']
                    trend_reversal = was_above and now_below

        has_exit = profit_target_hit or trend_reversal

        exit_reason = None
        if profit_target_hit:
            exit_reason = 'profit_target'
        elif trend_reversal:
            exit_reason = 'trend_reversal'

        return {
            'has_exit': has_exit,
            'exit_reason': exit_reason,
            'current_price': float(current_price),
            'profit_pct': float(profit_pct * 100),  # as percentage
            'profit_target_hit': profit_target_hit,
            'trend_reversal': trend_reversal,
            'reversal_date': reversal_date,  # NEW - for debugging
            'date': current.name
        }

    def analyze_stock(self, df: pd.DataFrame, ticker: str, name: str = None) -> Optional[Dict]:
        """
        Analyze a stock and return signal if present.

        Args:
            df: DataFrame with OHLC data and indicators
            ticker: Stock ticker
            name: Stock name (optional)

        Returns:
            Dict with complete signal analysis or None if no signal
        """
        signal_info = self.detect_entry_signal(df)

        if not signal_info['has_signal']:
            return None

        score = self.calculate_score(signal_info, df)

        latest = df.iloc[-1]
        above_sma = False
        if self.sma_column in latest and not pd.isna(latest[self.sma_column]):
            above_sma = latest['Close'] > latest[self.sma_column]

        return {
            'ticker': ticker,
            'name': name or ticker,
            'signal': 'BUY',
            'strategy': 'trend_following',
            'score': round(score, 2),
            'current_price': round(signal_info['close'], 2),
            'indicators': {
                'ADX': round(signal_info['adx'], 2),
                'DIPlus': round(signal_info['di_plus'], 2),
                'DIMinus': round(signal_info['di_minus'], 2),
                'SMA200': round(float(latest[self.sma_column]), 2) if self.sma_column in latest else None,
                'above_sma200': bool(above_sma)
            },
            'entry_conditions': {
                'adx_above_30': bool(signal_info['adx_above_threshold']),
                'di_plus_above_di_minus': bool(signal_info['di_plus_above_di_minus']),
                'fresh_crossover': bool(signal_info['fresh_crossover'])
            },
            'timestamp': signal_info['date'].isoformat() if hasattr(signal_info['date'], 'isoformat') else str(signal_info['date'])
        }
