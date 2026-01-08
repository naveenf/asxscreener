"""
Mean Reversion Signal Detection Module

Detects entry and exit signals based on mean reversion strategy:
- Entry: Price < Lower Bollinger Band AND RSI < 30 (oversold)
- Exit: Price returns to Middle BB OR 7% profit target

Rationale: Oversold stocks tend to revert to their mean, providing
short-term profit opportunities on the long side.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional

from .indicators import TechnicalIndicators


class MeanReversionDetector:
    """Detect mean reversion trading signals and calculate scores."""

    def __init__(
        self,
        rsi_threshold: float = 30.0,
        profit_target: float = 0.20,  
        stop_loss: float = 0.07,
        time_limit: int = 90,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
        rsi_period: int = 14,
        volume_filter_enabled: bool = False,
        volume_multiplier: float = 1.5
    ):
        """
        Initialize mean reversion detector.
        """
        self.rsi_threshold = rsi_threshold
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.time_limit = time_limit
        self.bb_period = bb_period
        self.bb_std_dev = bb_std_dev
        self.rsi_period = rsi_period
        self.volume_filter_enabled = volume_filter_enabled
        self.volume_multiplier = volume_multiplier

    def detect_entry_signal(self, df: pd.DataFrame) -> Dict:
        """
        Detect current entry signal.

        Entry conditions (ALL must be true):
        1. Price < Lower Bollinger Band (extreme oversold)
        2. RSI < 35 (momentum oversold)
        3. Price > SMA200 (Trade with primary trend)
        4. Price >= $1.00 (Avoid penny stocks)
        """
        if len(df) == 0:
            return {'has_signal': False, 'reason': 'No data'}

        # Get latest row
        latest = df.iloc[-1]

        # Check if we have valid indicator values
        required_cols = ['BB_Lower', 'BB_Middle', 'RSI', 'Close', 'SMA200']
        if any(pd.isna(latest[col]) for col in required_cols):
            return {'has_signal': False, 'reason': 'Insufficient data for indicators'}

        # Check entry conditions
        price_below_lower_bb = latest['Close'] < latest['BB_Lower']
        rsi_oversold = latest['RSI'] < self.rsi_threshold
        above_sma200 = latest['Close'] > latest['SMA200']
        price_ok = latest['Close'] >= 1.0  # Avoid stocks below $1

        # Calculate how far below lower band (as percentage)
        bb_distance_pct = ((latest['BB_Lower'] - latest['Close']) / latest['BB_Lower']) * 100

        # Check for volume confirmation (optional)
        volume_ok = self._check_volume(df)

        # ALL conditions must be met for entry signal
        has_signal = (
            price_below_lower_bb and
            rsi_oversold and
            above_sma200 and
            volume_ok and
            price_ok
        )

        return {
            'has_signal': has_signal,
            'rsi': float(latest['RSI']),
            'bb_upper': float(latest.get('BB_Upper', 0)),
            'bb_middle': float(latest['BB_Middle']),
            'bb_lower': float(latest['BB_Lower']),
            'close': float(latest['Close']),
            'bb_distance_pct': float(bb_distance_pct),
            'price_below_lower_bb': price_below_lower_bb,
            'rsi_oversold': rsi_oversold,
            'date': latest.name
        }

    def calculate_score(self, signal_info: Dict, df: pd.DataFrame) -> float:
        """
        Calculate signal score (0-100).
        Granular Scoring:
        - Up to 40 pts: RSI (40 pts if <= 30, 30 if <= 40, 20 if <= 50, 10 if <= 60)
        - Up to 30 pts: BB Position (30 pts if below Lower BB, 15 if below Middle BB)
        - 20 pts: Trend alignment (Price > SMA200)
        - Up to 10 pts: BB Distance bonus
        """
        latest = df.iloc[-1]
        score = 0.0

        # 1. RSI Component (Max 40)
        rsi = latest['RSI']
        if rsi <= self.rsi_threshold: # 30
            score += 40.0
        elif rsi <= 40:
            score += 30.0
        elif rsi <= 50:
            score += 20.0
        elif rsi <= 60:
            score += 10.0

        # 2. Bollinger Band Position (30)
        if latest['Close'] < latest['BB_Lower']:
            score += 30.0
        elif latest['Close'] < latest['BB_Middle']:
            score += 15.0

        # 3. Trend Alignment (20)
        if latest['Close'] > latest['SMA200']:
            score += 20.0

        # 4. BB Distance Bonus (Up to 10)
        # Only if below lower band
        bb_distance = ((latest['BB_Lower'] - latest['Close']) / latest['BB_Lower']) * 100
        if bb_distance > 0:
            score += min(bb_distance * 2, 10.0)

        return min(score, 100.0)

    def _check_volume(self, df: pd.DataFrame) -> bool:
        """
        Check if current volume meets filter criteria.
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
        Detect exit signal.
        """
        if current_index is None:
            current_index = len(df) - 1

        # Convert negative index to positive absolute index
        if current_index < 0:
            current_index = len(df) + current_index

        if current_index < 0 or current_index >= len(df):
            return {'has_exit': False, 'reason': 'Invalid index'}

        current = df.iloc[current_index]
        current_price = current['Close']

        # 1. Check profit target
        profit_pct = (current_price - entry_price) / entry_price
        profit_target_hit = profit_pct >= self.profit_target

        # 2. Check stop loss
        stop_loss_hit = profit_pct <= -self.stop_loss

        # 3. Check for mean reversion (price returned to middle band)
        mean_reversion = False
        if not pd.isna(current.get('BB_Middle', np.nan)):
            mean_reversion = current_price >= current['BB_Middle']

        # 4. Check time limit
        time_limit_hit = False
        if entry_index is not None:
            # How many bars since entry
            bars_held = current_index - entry_index
            time_limit_hit = bars_held >= self.time_limit

        has_exit = profit_target_hit or mean_reversion or stop_loss_hit or time_limit_hit

        exit_reason = None
        if profit_target_hit: exit_reason = 'profit_target'
        elif stop_loss_hit: exit_reason = 'stop_loss'
        elif mean_reversion: exit_reason = 'mean_reversion'
        elif time_limit_hit: exit_reason = 'time_limit'

        return {
            'has_exit': has_exit,
            'exit_reason': exit_reason,
            'current_price': float(current_price),
            'profit_pct': float(profit_pct * 100),
            'profit_target_hit': profit_target_hit,
            'stop_loss_hit': stop_loss_hit,
            'mean_reversion': mean_reversion,
            'time_limit_hit': time_limit_hit,
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
                'price_below_lower_bb': bool(signal_info['price_below_lower_bb']),
                'rsi_oversold': bool(signal_info['rsi_oversold'])
            },
            'timestamp': signal_info['date'].isoformat() if hasattr(signal_info['date'], 'isoformat') else str(signal_info['date'])
        }
