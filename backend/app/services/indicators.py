"""
Technical Indicators Module

Implements ADX, DI+, DI-, and SMA calculations.
ADX/DI implementation matches Pine Script logic exactly using Wilder's smoothing.
"""

import pandas as pd
import numpy as np
from typing import Optional


class TechnicalIndicators:
    """Calculate technical indicators for stock data."""

    @staticmethod
    def calculate_true_range(df: pd.DataFrame) -> pd.Series:
        """
        Calculate True Range.
        TR = max(high - low, abs(high - prev_close), abs(low - prev_close))
        """
        df = df.copy()
        df['prev_close'] = df['Close'].shift(1)

        tr1 = df['High'] - df['Low']
        tr2 = abs(df['High'] - df['prev_close'])
        tr3 = abs(df['Low'] - df['prev_close'])

        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return true_range

    @staticmethod
    def calculate_directional_movement(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        """
        Calculate Directional Movement Plus and Minus.

        Pine Script logic:
        DirectionalMovementPlus = high-nz(high[1]) > nz(low[1])-low ?
                                   max(high-nz(high[1]), 0): 0
        DirectionalMovementMinus = nz(low[1])-low > high-nz(high[1]) ?
                                    max(nz(low[1])-low, 0): 0

        Returns:
            tuple: (dm_plus, dm_minus)
        """
        df = df.copy()
        df['prev_high'] = df['High'].shift(1)
        df['prev_low'] = df['Low'].shift(1)

        df['high_diff'] = df['High'] - df['prev_high']
        df['low_diff'] = df['prev_low'] - df['Low']

        # DM+ = high_diff > low_diff ? max(high_diff, 0) : 0
        dm_plus = pd.Series(0.0, index=df.index)
        dm_plus[df['high_diff'] > df['low_diff']] = df.loc[
            df['high_diff'] > df['low_diff'], 'high_diff'
        ].clip(lower=0)

        # DM- = low_diff > high_diff ? max(low_diff, 0) : 0
        dm_minus = pd.Series(0.0, index=df.index)
        dm_minus[df['low_diff'] > df['high_diff']] = df.loc[
            df['low_diff'] > df['high_diff'], 'low_diff'
        ].clip(lower=0)

        return dm_plus, dm_minus

    @staticmethod
    def wilders_smoothing(series: pd.Series, period: int) -> pd.Series:
        """
        Apply Wilder's smoothing (modified EMA).

        Pine Script logic:
        SmoothedValue := nz(SmoothedValue[1]) - (nz(SmoothedValue[1])/len) + CurrentValue

        This is equivalent to EMA with alpha = 1/period and adjust=False.

        Args:
            series: Data series to smooth
            period: Smoothing period

        Returns:
            Smoothed series
        """
        return series.ewm(alpha=1/period, adjust=False).mean()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """
        Calculate ADX, DI+, and DI- indicators.

        Matches Pine Script implementation exactly:
        1. Calculate True Range
        2. Calculate Directional Movement (+ and -)
        3. Apply Wilder's smoothing to TR, DM+, DM-
        4. Calculate DI+ and DI-
        5. Calculate DX
        6. Calculate ADX (SMA of DX)

        Args:
            df: DataFrame with OHLC data (must have High, Low, Close columns)
            period: ADX period (default 14, matching Pine Script)

        Returns:
            DataFrame with added columns: ADX, DIPlus, DIMinus
        """
        result_df = df.copy()

        # Step 1: Calculate True Range
        tr = TechnicalIndicators.calculate_true_range(result_df)

        # Step 2: Calculate Directional Movement
        dm_plus, dm_minus = TechnicalIndicators.calculate_directional_movement(result_df)

        # Step 3: Apply Wilder's smoothing
        smoothed_tr = TechnicalIndicators.wilders_smoothing(tr, period)
        smoothed_dm_plus = TechnicalIndicators.wilders_smoothing(dm_plus, period)
        smoothed_dm_minus = TechnicalIndicators.wilders_smoothing(dm_minus, period)

        # Step 4: Calculate DI+ and DI-
        # DIPlus = SmoothedDirectionalMovementPlus / SmoothedTrueRange * 100
        # DIMinus = SmoothedDirectionalMovementMinus / SmoothedTrueRange * 100
        result_df['DIPlus'] = (smoothed_dm_plus / smoothed_tr) * 100
        result_df['DIMinus'] = (smoothed_dm_minus / smoothed_tr) * 100

        # Step 5: Calculate DX
        # DX = abs(DIPlus - DIMinus) / (DIPlus + DIMinus) * 100
        di_sum = result_df['DIPlus'] + result_df['DIMinus']
        di_diff = abs(result_df['DIPlus'] - result_df['DIMinus'])

        # Avoid division by zero
        dx = pd.Series(0.0, index=result_df.index)
        dx[di_sum != 0] = (di_diff[di_sum != 0] / di_sum[di_sum != 0]) * 100

        # Step 6: Calculate ADX (Simple Moving Average of DX)
        # ADX = sma(DX, len)
        result_df['ADX'] = dx.rolling(window=period).mean()

        return result_df

    @staticmethod
    def calculate_sma(df: pd.DataFrame, column: str = 'Close', period: int = 200) -> pd.Series:
        """
        Calculate Simple Moving Average.

        Args:
            df: DataFrame with price data
            column: Column to calculate SMA on (default 'Close')
            period: SMA period (default 200)

        Returns:
            Series with SMA values
        """
        return df[column].rolling(window=period).mean()

    @staticmethod
    def detect_crossover(series1: pd.Series, series2: pd.Series) -> pd.Series:
        """
        Detect when series1 crosses above series2.

        Returns:
            Boolean series: True where crossover occurred
        """
        # series1 was below series2 previously and is now above
        prev_below = series1.shift(1) <= series2.shift(1)
        now_above = series1 > series2
        return prev_below & now_above

    @staticmethod
    def detect_crossunder(series1: pd.Series, series2: pd.Series) -> pd.Series:
        """
        Detect when series1 crosses below series2.

        Returns:
            Boolean series: True where crossunder occurred
        """
        # series1 was above series2 previously and is now below
        prev_above = series1.shift(1) >= series2.shift(1)
        now_below = series1 < series2
        return prev_above & now_below

    @staticmethod
    def add_all_indicators(
        df: pd.DataFrame,
        adx_period: int = 14,
        sma_period: int = 200
    ) -> pd.DataFrame:
        """
        Add all indicators to DataFrame in one call.

        Args:
            df: DataFrame with OHLC data
            adx_period: Period for ADX calculation (default 14)
            sma_period: Period for SMA calculation (default 200)

        Returns:
            DataFrame with ADX, DIPlus, DIMinus, SMA200 columns added
        """
        # Add ADX indicators
        df = TechnicalIndicators.calculate_adx(df, period=adx_period)

        # Add SMA
        df[f'SMA{sma_period}'] = TechnicalIndicators.calculate_sma(
            df, column='Close', period=sma_period
        )

        return df


def load_and_calculate_indicators(
    csv_path: str,
    adx_period: int = 14,
    sma_period: int = 200
) -> pd.DataFrame:
    """
    Convenience function to load CSV and calculate all indicators.

    Args:
        csv_path: Path to CSV file
        adx_period: Period for ADX calculation
        sma_period: Period for SMA calculation

    Returns:
        DataFrame with all indicators calculated
    """
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    df = TechnicalIndicators.add_all_indicators(df, adx_period, sma_period)
    return df
