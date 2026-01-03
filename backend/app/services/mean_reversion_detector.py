"""
Mean Reversion Signal Detection Module

Detects entry and exit signals based on mean reversion strategy:
- Entry: Price > Upper Bollinger Band AND RSI > 70 (overbought)
- Exit: Price returns to Middle BB OR 7% profit target

Rationale: Overbought stocks tend to revert to their mean, providing
short-term profit opportunities.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional

from .indicators import TechnicalIndicators


class MeanReversionDetector:
    """Detect mean reversion trading signals and calculate scores."""

    def __init__(
        self,
        rsi_threshold: float = 70.0,
        profit_target: float = 0.07,  # 7%
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
        rsi_period: int = 14,
        volume_filter_enabled: bool = False,
        volume_multiplier: float = 1.5
    ):
        """
        Initialize mean reversion detector.

        Args:
            rsi_threshold: RSI must be above this for entry (default 70)
            profit_target: Profit target as decimal (default 0.07 = 7%)
            bb_period: Bollinger Bands period (default 20)
            bb_std_dev: Bollinger Bands standard deviations (default 2.0)
            rsi_period: RSI calculation period (default 14)
            volume_filter_enabled: Enable volume filter (default False)
            volume_multiplier: Volume must be > this * SMA(20) (default 1.5)
        """
        self.rsi_threshold = rsi_threshold
        self.profit_target = profit_target
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev
        self.rsi_period = rsi_period
        self.volume_filter_enabled = volume_filter_enabled
        self.volume_multiplier = volume_multiplier

    def detect_entry_signal(self, df: pd.DataFrame) -> Dict:
        """
        Detect current entry signal.

        Entry conditions (ALL must be true):
        1. Price > Upper Bollinger Band (extreme overbought)
        2. RSI > 70 (momentum overbought)
        3. Optional: Volume confirmation

        Args:
            df: DataFrame with indicators (must have BB_Upper, RSI, Close)

        Returns:
            Dict with signal information
        """
        if len(df) == 0:
            return {'has_signal': False, 'reason': 'No data'}

        # Get latest row
        latest = df.iloc[-1]

        # Check if we have valid indicator values
        required_cols = ['BB_Upper', 'BB_Middle', 'RSI', 'Close']
        if any(pd.isna(latest[col]) for col in required_cols):
            return {'has_signal': False, 'reason': 'Insufficient data for indicators'}

        # Check entry conditions
        price_above_upper_bb = latest['Close'] > latest['BB_Upper']
        rsi_overbought = latest['RSI'] > self.rsi_threshold

        # Calculate how far above upper band (as percentage)
        bb_distance_pct = ((latest['Close'] - latest['BB_Upper']) / latest['BB_Upper']) * 100

        # Check for volume confirmation (optional)
        volume_ok = self._check_volume(df)

        # BOTH conditions must be met for entry signal
        has_signal = (
            price_above_upper_bb and
            rsi_overbought and
            volume_ok
        )

        return {
            'has_signal': has_signal,
            'rsi': float(latest['RSI']),
            'bb_upper': float(latest['BB_Upper']),
            'bb_middle': float(latest['BB_Middle']),
            'bb_lower': float(latest.get('BB_Lower', 0)),
            'close': float(latest['Close']),
            'bb_distance_pct': float(bb_distance_pct),
            'price_above_upper_bb': price_above_upper_bb,
            'rsi_overbought': rsi_overbought,
            'date': latest.name
        }

    def calculate_score(self, signal_info: Dict, df: pd.DataFrame) -> float:
        """
        Calculate signal score (0-100).

        Scoring algorithm:
        - Base score: 50
        - RSI extremeness: 0-20 (higher RSI = more extreme)
        - BB distance: 0-20 (further from band = more extreme)
        - Volume confirmation: +10
        - Trend alignment: +5 (price below SMA200 = counter-trend preferred)

        Args:
            signal_info: Signal information from detect_entry_signal()
            df: DataFrame with price and indicator data

        Returns:
            Score from 0-100
        """
        if not signal_info.get('has_signal'):
            return 0.0

        score = 50.0  # Base score

        # RSI extremeness bonus (0-20 points)
        # RSI from 70 to 100 gives 0 to 20 points
        rsi = signal_info['rsi']
        if rsi >= self.rsi_threshold:
            rsi_bonus = min((rsi - self.rsi_threshold) / 30 * 20, 20.0)
            score += rsi_bonus

        # BB distance bonus (0-20 points)
        # Further above upper band = more extreme
        bb_distance = signal_info['bb_distance_pct']
        if bb_distance > 0:
            distance_bonus = min(bb_distance * 2, 20.0)
            score += distance_bonus

        # Volume confirmation (+10 points)
        if self.volume_filter_enabled:
            latest = df.iloc[-1]
            if 'Volume' in latest and 'Volume_SMA' in latest:
                if not pd.isna(latest['Volume']) and not pd.isna(latest['Volume_SMA']):
                    if latest['Volume'] > latest['Volume_SMA'] * self.volume_multiplier:
                        score += 10.0

        # Counter-trend alignment (+5 points)
        # Mean reversion works better when counter to main trend
        latest = df.iloc[-1]
        if 'SMA200' in latest and not pd.isna(latest['SMA200']):
            if latest['Close'] < latest['SMA200']:  # Price below long-term MA
                score += 5.0

        return min(score, 100.0)

    def _check_volume(self, df: pd.DataFrame) -> bool:
        """
        Check if current volume meets filter criteria.

        Args:
            df: DataFrame with Volume and Volume_SMA columns

        Returns:
            True if volume filter passes (or disabled), False otherwise
        """
        if not self.volume_filter_enabled:
            return True  # Filter disabled, always pass

        if 'Volume' not in df.columns or 'Volume_SMA' not in df.columns:
            return True  # Missing data, pass

        latest = df.iloc[-1]

        if pd.isna(latest['Volume']) or pd.isna(latest['Volume_SMA']):
            return True  # Can't filter without data, pass

        # Volume must be above threshold
        return latest['Volume'] > latest['Volume_SMA'] * self.volume_multiplier

    def detect_exit_signal(
        self,
        df: pd.DataFrame,
        entry_price: float,
        current_index: Optional[int] = None,
        entry_index: Optional[int] = None
    ) -> Dict:
        """
        Detect exit signal for an existing position.

        Exit conditions (either triggers exit):
        1. Price returns to Middle Bollinger Band (mean reversion complete)
        2. 7% profit target reached

        Args:
            df: DataFrame with indicators
            entry_price: Entry price for the position
            current_index: Index to check (default: latest)
            entry_index: Index where position was entered (for reference)

        Returns:
            Dict with exit information
        """
        if current_index is None:
            current_index = len(df) - 1

        # Convert negative index to positive
        if current_index < 0:
            current_index = len(df) + current_index

        if current_index < 0 or current_index >= len(df):
            return {'has_exit': False, 'reason': 'Invalid index'}

        current = df.iloc[current_index]
        current_price = current['Close']

        # Check profit target
        profit_pct = (current_price - entry_price) / entry_price
        profit_target_hit = profit_pct >= self.profit_target

        # Check for mean reversion (price returned to middle band)
        mean_reversion = False
        if not pd.isna(current.get('BB_Middle', np.nan)):
            # Price has returned to or below middle band
            mean_reversion = current_price <= current['BB_Middle']

        has_exit = profit_target_hit or mean_reversion

        exit_reason = None
        if profit_target_hit:
            exit_reason = 'profit_target'
        elif mean_reversion:
            exit_reason = 'mean_reversion'

        return {
            'has_exit': has_exit,
            'exit_reason': exit_reason,
            'current_price': float(current_price),
            'profit_pct': float(profit_pct * 100),  # as percentage
            'profit_target_hit': profit_target_hit,
            'mean_reversion': mean_reversion,
            'bb_middle': float(current.get('BB_Middle', 0)),
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
        below_sma = False
        if 'SMA200' in latest and not pd.isna(latest['SMA200']):
            below_sma = latest['Close'] < latest['SMA200']

        return {
            'ticker': ticker,
            'name': name or ticker,
            'signal': 'BUY',
            'strategy': 'mean_reversion',
            'score': round(score, 2),
            'current_price': round(signal_info['close'], 2),
            'indicators': {
                'RSI': round(signal_info['rsi'], 2),
                'BB_Upper': round(signal_info['bb_upper'], 2),
                'BB_Middle': round(signal_info['bb_middle'], 2),
                'BB_Lower': round(signal_info['bb_lower'], 2),
                'BB_Distance_PCT': round(signal_info['bb_distance_pct'], 2),
                'SMA200': round(float(latest.get('SMA200', 0)), 2) if 'SMA200' in latest else None,
                'below_sma200': bool(below_sma)
            },
            'entry_conditions': {
                'price_above_upper_bb': bool(signal_info['price_above_upper_bb']),
                'rsi_overbought': bool(signal_info['rsi_overbought'])
            },
            'timestamp': signal_info['date'].isoformat() if hasattr(signal_info['date'], 'isoformat') else str(signal_info['date'])
        }
