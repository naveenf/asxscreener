"""
Triple Confirmation Trend Detector

Logic:
- Anchor: Fibonacci Structure Trend (50-bar)
- Confirmation: Pivot Point Supertrend
- Trigger: Ehlers Instantaneous Trend Crossover

Screening is performed on T-1 (previous day's close) to ensure stability.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional

from .indicators import TechnicalIndicators


class TripleTrendDetector:
    """Detect signals using Fibonacci, Supertrend, and Instant Trend alignment."""

    def __init__(
        self,
        fib_period: int = 50,
        st_factor: float = 3.0,
        it_alpha: float = 0.07,
        profit_target: float = 0.15,
        stop_loss: float = 0.10,
        time_limit: int = 90
    ):
        self.fib_period = fib_period
        self.st_factor = st_factor
        self.it_alpha = it_alpha
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.time_limit = time_limit

    def detect_entry_signal(self, df: pd.DataFrame) -> Dict:
        """
        Detect entry signal on T-1 data.
        
        Conditions:
        1. Fibonacci Trend is Bullish (Fib_Pos > 0)
        2. Supertrend is Bullish (PP_Trend == 1)
        3. Instant Trend Trigger crosses above IT_Trend (Bullish Trigger)
        """
        if len(df) < 3:
            return {'has_signal': False, 'reason': 'Insufficient data'}

        # Evaluation is on i-1 (yesterday)
        # In this backtester's context, df is sliced up to the 'current_date'
        # So iloc[-1] is actually the 'current' close (which we use as the T-1 signal)
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # Check required columns
        required = ['Fib_Pos', 'PP_Trend', 'IT_Trend', 'IT_Trigger', 'Close']
        if any(pd.isna(latest[col]) for col in required):
            return {'has_signal': False, 'reason': 'NaN values in indicators'}

        # 1. Fibonacci Anchor (Long term)
        fib_bullish = latest['Fib_Pos'] > 0

        # 2. Supertrend Confirmation (Mid term)
        st_bullish = latest['PP_Trend'] == 1

        # 3. Instant Trend Trigger (Short term)
        # Crossover: Trigger was below Trend, now is above
        it_crossover = (prev['IT_Trigger'] <= prev['IT_Trend']) and (latest['IT_Trigger'] > latest['IT_Trend'])

        # 4. Price Filter
        price_ok = latest['Close'] >= 1.0

        # All conditions must align
        has_signal = fib_bullish and st_bullish and it_crossover and price_ok

        return {
            'has_signal': has_signal,
            'fib_pos': int(latest['Fib_Pos']),
            'st_trend': int(latest['PP_Trend']),
            'it_trend': float(latest['IT_Trend']),
            'it_trigger': float(latest['IT_Trigger']),
            'close': float(latest['Close']),
            'date': latest.name
        }

    def calculate_score(self, signal_info: Dict, df: pd.DataFrame) -> float:
        """
        Calculate signal score.
        Higher score for signals where price is closer to the Supertrend line
        (better risk/reward).
        """
        if not signal_info.get('has_signal'):
            return 0.0

        score = 60.0 # Base score is high because triple confirmation is rare
        
        latest = df.iloc[-1]
        if 'PP_TrailingSL' in latest and not pd.isna(latest['PP_TrailingSL']):
            # Distance from stop loss (lower is better for entry)
            dist_pct = (latest['Close'] - latest['PP_TrailingSL']) / latest['Close']
            # Bonus of up to 20 points if within 5% of the stop
            dist_bonus = max(0, (0.05 - dist_pct) / 0.05 * 20.0)
            score += dist_bonus

        # Bonus for fresh Fibonacci trend
        if len(df) >= 5:
            if all(df['Fib_Pos'].iloc[-5:] > 0) and any(df['Fib_Pos'].iloc[-10:-5] <= 0):
                score += 10.0

        return min(score, 100.0)

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
            return {'has_exit': False}

        current = df.iloc[current_index]
        current_price = current['Close']

        # 1. Profit Target
        profit_pct = (current_price - entry_price) / entry_price
        profit_hit = profit_pct >= self.profit_target

        # 2. Hard Stop Loss (10%)
        stop_loss_hit = profit_pct <= -self.stop_loss

        # 3. Instant Trend Reversal (REMOVED for more room)
        it_reversal = False # current['IT_Trigger'] < current['IT_Trend']

        # 4. Supertrend Flip
        st_flip = current['PP_Trend'] == -1

        # 5. Time Limit
        time_limit_hit = False
        if entry_index is not None:
            bars_held = current_index - entry_index
            time_limit_hit = bars_held >= self.time_limit

        has_exit = profit_hit or stop_loss_hit or st_flip or time_limit_hit

        exit_reason = None
        if profit_hit: exit_reason = 'profit_target'
        elif stop_loss_hit: exit_reason = 'stop_loss'
        elif st_flip: exit_reason = 'supertrend_reversal'
        elif time_limit_hit: exit_reason = 'time_limit'

        return {
            'has_exit': has_exit,
            'exit_reason': exit_reason,
            'current_price': float(current_price),
            'profit_pct': float(profit_pct * 100),
            'date': current.name
        }

    def analyze_stock(self, df: pd.DataFrame, ticker: str, name: str = None) -> Optional[Dict]:
        """
        Analyze a stock and return signal if present.
        """
        signal_info = self.detect_entry_signal(df)

        if not signal_info['has_signal']:
            return None

        score = self.calculate_score(signal_info, df)
        latest = df.iloc[-1]
        
        above_sma = False
        if 'SMA200' in latest and not pd.isna(latest['SMA200']):
            above_sma = latest['Close'] > latest['SMA200']

        return {
            'ticker': ticker,
            'name': name or ticker,
            'signal': 'BUY',
            'strategy': 'trend_following',
            'score': round(score, 2),
            'current_price': round(signal_info['close'], 2),
            'indicators': {
                'Fib_Pos': int(signal_info['fib_pos']),
                'PP_Trend': int(signal_info['st_trend']),
                'IT_Trend': round(float(signal_info['it_trend']), 2),
                'IT_Trigger': round(float(signal_info['it_trigger']), 2),
                'SMA200': round(float(latest.get('SMA200', 0)), 2) if 'SMA200' in latest else None,
                'above_sma200': bool(above_sma)
            },
            'entry_conditions': {
                'fib_structure_bullish': bool(signal_info['fib_pos'] > 0),
                'supertrend_bullish': bool(signal_info['st_trend'] == 1),
                'it_trend_bullish': bool(latest['IT_Trigger'] > latest['IT_Trend'])
            },
            'timestamp': signal_info['date'].isoformat() if hasattr(signal_info['date'], 'isoformat') else str(signal_info['date'])
        }
