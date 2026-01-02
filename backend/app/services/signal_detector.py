"""
Signal Detection Module

Detects entry and exit signals based on ADX/DI strategy.
Implements scoring algorithm for ranking signals.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from datetime import datetime


class SignalDetector:
    """Detect trading signals and calculate scores."""

    def __init__(
        self,
        adx_threshold: float = 30.0,
        profit_target: float = 0.15,  # 15%
        sma_period: int = 200
    ):
        """
        Initialize signal detector.

        Args:
            adx_threshold: ADX must be above this for entry (default 30)
            profit_target: Profit target as decimal (default 0.15 = 15%)
            sma_period: SMA period for scoring bonus (default 200)
        """
        self.adx_threshold = adx_threshold
        self.profit_target = profit_target
        self.sma_period = sma_period
        self.sma_column = f'SMA{sma_period}'

    def detect_entry_signal(self, df: pd.DataFrame) -> Dict:
        """
        Detect current entry signal.

        Entry conditions:
        1. ADX > 30
        2. DI+ > DI- (bullish trend)

        Args:
            df: DataFrame with indicators (must have ADX, DIPlus, DIMinus)

        Returns:
            Dict with signal information
        """
        if len(df) == 0:
            return {'has_signal': False, 'reason': 'No data'}

        # Get latest row
        latest = df.iloc[-1]

        # Check if we have valid indicator values
        if pd.isna(latest['ADX']) or pd.isna(latest['DIPlus']) or pd.isna(latest['DIMinus']):
            return {'has_signal': False, 'reason': 'Insufficient data for indicators'}

        # Check entry conditions
        adx_above_threshold = latest['ADX'] > self.adx_threshold
        di_plus_above_di_minus = latest['DIPlus'] > latest['DIMinus']

        # Check for fresh crossover (DI+ just crossed above DI-)
        fresh_crossover = False
        if len(df) >= 2:
            prev = df.iloc[-2]
            if not pd.isna(prev['DIPlus']) and not pd.isna(prev['DIMinus']):
                was_below = prev['DIPlus'] <= prev['DIMinus']
                now_above = latest['DIPlus'] > latest['DIMinus']
                fresh_crossover = was_below and now_above

        has_signal = adx_above_threshold and di_plus_above_di_minus

        return {
            'has_signal': has_signal,
            'adx': float(latest['ADX']),
            'di_plus': float(latest['DIPlus']),
            'di_minus': float(latest['DIMinus']),
            'close': float(latest['Close']),
            'adx_above_threshold': adx_above_threshold,
            'di_plus_above_di_minus': di_plus_above_di_minus,
            'fresh_crossover': fresh_crossover,
            'date': latest.name
        }

    def calculate_score(self, signal_info: Dict, df: pd.DataFrame) -> float:
        """
        Calculate signal score (0-100).

        Scoring algorithm:
        - Base score: 50
        - ADX strength bonus: 0-25 (higher ADX = stronger trend)
        - DI spread bonus: 0-15 (bigger difference = clearer signal)
        - Above SMA200 bonus: +10
        - Fresh crossover bonus: +5

        Args:
            signal_info: Signal information from detect_entry_signal()
            df: DataFrame with price and indicator data

        Returns:
            Score from 0-100
        """
        if not signal_info.get('has_signal'):
            return 0.0

        score = 50.0  # Base score

        # ADX strength bonus (0-25 points)
        # ADX from 30 to 50+ gives 0 to 25 points
        adx = signal_info['adx']
        if adx >= self.adx_threshold:
            adx_bonus = min((adx - self.adx_threshold) * 1.25, 25.0)
            score += adx_bonus

        # DI spread bonus (0-15 points)
        # Bigger spread between DI+ and DI- = clearer trend
        di_spread = signal_info['di_plus'] - signal_info['di_minus']
        if di_spread > 0:
            spread_bonus = min(di_spread * 0.5, 15.0)
            score += spread_bonus

        # Above SMA200 bonus (+10 points)
        latest = df.iloc[-1]
        if self.sma_column in latest and not pd.isna(latest[self.sma_column]):
            if latest['Close'] > latest[self.sma_column]:
                score += 10.0

        # Fresh crossover bonus (+5 points)
        if signal_info.get('fresh_crossover'):
            score += 5.0

        return min(score, 100.0)

    def detect_exit_signal(
        self,
        df: pd.DataFrame,
        entry_price: float,
        current_index: Optional[int] = None
    ) -> Dict:
        """
        Detect exit signal for an existing position.

        Exit conditions:
        1. Price >= entry_price * (1 + profit_target) [15% profit]
        2. OR DI+ crosses below DI- [trend reversal]

        Args:
            df: DataFrame with indicators
            entry_price: Entry price for the position
            current_index: Index to check (default: latest)

        Returns:
            Dict with exit information
        """
        if current_index is None:
            current_index = len(df) - 1

        if current_index < 0 or current_index >= len(df):
            return {'has_exit': False, 'reason': 'Invalid index'}

        current = df.iloc[current_index]
        current_price = current['Close']

        # Check profit target
        profit_pct = (current_price - entry_price) / entry_price
        profit_target_hit = profit_pct >= self.profit_target

        # Check for DI+ crossing below DI- (trend reversal)
        trend_reversal = False
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
