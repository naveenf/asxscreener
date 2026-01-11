"""
Sniper Ranking System - "Elite 3" Global Signal Selection

This module implements the composite scoring and global ranking system
for the Trend Sniper strategy. It analyzes all signals across 42 instruments
and selects only the top 3 highest-quality setups per screening cycle.

Composite Score Formula:
    FINAL_SCORE = (HTF_Score × 0.5) + (Volume_Accel × 0.3) + (DI_Jump × 0.2)

Where:
    - HTF_Score = Higher Timeframe trend strength (1H ADX + EMA slope)
    - Volume_Accel = Current volume vs 5-bar average (institutional participation)
    - DI_Jump = Directional momentum acceleration (explosive moves)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional


class SniperRanker:
    """
    Ranks forex/commodity signals to select Elite 3 per day.

    Philosophy: Quality over quantity. Only the strongest multi-timeframe
    setups with institutional volume and explosive momentum make the cut.
    """

    def __init__(self):
        # Weighting for composite score
        self.htf_weight = 0.5    # Higher timeframe alignment (most important)
        self.volume_weight = 0.3  # Institutional participation
        self.di_weight = 0.2      # Momentum acceleration

    def calculate_htf_score(self, df_1h: pd.DataFrame) -> float:
        """
        Calculate Higher Timeframe (1H) trend strength score.

        Components:
        1. ADX strength: (ADX - 25) → Range 0-15+ points
        2. EMA34 slope: (current - 5 bars ago) / price × 1000 → Range -5 to +5 points

        Args:
            df_1h: 1-hour dataframe with indicators calculated

        Returns:
            HTF score (typically 0-20 range, higher = stronger trend)
        """
        if len(df_1h) < 6:
            return 0.0

        latest = df_1h.iloc[-1]
        prev5 = df_1h.iloc[-6]

        # Component 1: ADX strength (above threshold of 25)
        adx_score = max(0, float(latest['ADX']) - 25.0)

        # Component 2: EMA34 slope (positive slope = uptrend, negative = downtrend)
        # Normalize by price to make comparable across instruments
        ema34_delta = float(latest['EMA34']) - float(prev5['EMA34'])
        ema34_slope = (ema34_delta / float(latest['EMA34'])) * 1000
        ema34_score = abs(ema34_slope)  # Take absolute value (strong trend either direction)

        htf_score = adx_score + ema34_score

        return round(htf_score, 2)

    def calculate_volume_accel(self, df_15m: pd.DataFrame) -> float:
        """
        Calculate volume acceleration (current vs 5-bar average).

        High volume acceleration indicates institutional participation
        and increased probability of sustained move.

        Args:
            df_15m: 15-minute dataframe with Volume column

        Returns:
            Volume acceleration ratio (1.0 = average, 2.0 = 2x average, etc.)
        """
        if len(df_15m) < 6:
            return 1.0

        latest_volume = float(df_15m['Volume'].iloc[-1])
        avg_volume_5 = float(df_15m['Volume'].iloc[-6:-1].mean())

        if avg_volume_5 == 0 or pd.isna(avg_volume_5):
            return 1.0  # Forex pairs often have no volume data

        volume_accel = latest_volume / avg_volume_5

        return round(volume_accel, 2)

    def calculate_di_jump(self, signal: Dict, df_15m: pd.DataFrame) -> float:
        """
        Calculate DI momentum jump (already computed in signal).

        This measures the explosive acceleration in directional movement,
        indicating a strong breakout or momentum surge.

        Args:
            signal: Signal dict from SniperDetector (contains DI jump if available)
            df_15m: 15-minute dataframe for fallback calculation

        Returns:
            DI jump value (typically 5.0 - 15.0 for valid signals)
        """
        # First try to get from signal metadata (if detector already calculated it)
        if 'di_jump' in signal:
            return float(signal['di_jump'])

        # Fallback: Calculate from DataFrame
        if len(df_15m) < 3:
            return 0.0

        latest = df_15m.iloc[-1]
        prev2 = df_15m.iloc[-3]

        if signal.get('signal') == 'BUY':
            di_jump = float(latest['DIPlus']) - float(prev2['DIPlus'])
        else:
            di_jump = float(latest['DIMinus']) - float(prev2['DIMinus'])

        return round(di_jump, 2)

    def calculate_composite_score(
        self,
        signal: Dict,
        df_15m: pd.DataFrame,
        df_1h: pd.DataFrame
    ) -> Dict:
        """
        Calculate weighted composite score for a single signal.

        Formula:
            FINAL_SCORE = (HTF × 0.5) + (Volume × 0.3) + (DI × 0.2)

        Args:
            signal: Signal dict from SniperDetector
            df_15m: 15-minute dataframe for volume/DI calculations
            df_1h: 1-hour dataframe for HTF score

        Returns:
            Dict with breakdown: {
                'final_score': float,
                'htf_score': float,
                'volume_accel': float,
                'di_jump': float
            }
        """
        # Calculate components
        htf_score = self.calculate_htf_score(df_1h)
        volume_accel = self.calculate_volume_accel(df_15m)
        di_jump = self.calculate_di_jump(signal, df_15m)

        # Apply weighting
        final_score = (
            (htf_score * self.htf_weight) +
            (volume_accel * self.volume_weight) +
            (di_jump * self.di_weight)
        )

        return {
            'final_score': round(final_score, 2),
            'htf_score': htf_score,
            'volume_accel': volume_accel,
            'di_jump': di_jump
        }

    def rank_signals(self, signals_with_scores: List[Dict], top_n: int = 3) -> List[Dict]:
        """
        Rank all signals by composite score and return top N.

        Args:
            signals_with_scores: List of signal dicts (each must have 'composite_score' key)
            top_n: Number of top signals to return (default 3)

        Returns:
            List of top N signals sorted by score (descending)
        """
        if not signals_with_scores:
            return []

        # Sort by final_score (descending)
        sorted_signals = sorted(
            signals_with_scores,
            key=lambda s: s['composite_score']['final_score'],
            reverse=True
        )

        # Add rank to top N signals
        elite_signals = []
        for rank, signal in enumerate(sorted_signals[:top_n], start=1):
            signal['rank'] = rank
            signal['is_elite'] = True
            elite_signals.append(signal)

        return elite_signals

    def format_elite_output(
        self,
        elite_signals: List[Dict],
        total_analyzed: int,
        total_signals_found: int
    ) -> Dict:
        """
        Format Elite 3 signals for API response.

        Args:
            elite_signals: List of top 3 ranked signals
            total_analyzed: Total number of symbols analyzed
            total_signals_found: Total signals before ranking

        Returns:
            Formatted dict matching API spec
        """
        import datetime

        # Format each signal for output
        formatted_signals = []
        for signal in elite_signals:
            composite = signal.get('composite_score', {})

            formatted = {
                'rank': signal.get('rank', 0),
                'symbol': signal['symbol'],
                'name': signal.get('name', signal['symbol']),
                'casket': signal.get('casket', 'Unknown'),
                'signal': signal['signal'],
                'score': composite.get('final_score', 0),
                'breakdown': {
                    'htf_score': composite.get('htf_score', 0),
                    'volume_accel': composite.get('volume_accel', 0),
                    'di_jump': composite.get('di_jump', 0)
                },
                'price': signal['price'],
                'sl': signal.get('sl', signal['price'] * 0.99),  # Fallback: 1% below entry
                'risk_reward_potential': '1:3+',  # Standard Sniper target
                'timestamp': signal.get('timestamp', datetime.datetime.now().isoformat())
            }
            formatted_signals.append(formatted)

        return {
            'generated_at': datetime.datetime.now().isoformat(),
            'mode': 'sniper',
            'elite_signals': formatted_signals,
            'total_analyzed': total_analyzed,
            'signals_found': total_signals_found,
            'top_n_selected': len(elite_signals)
        }
