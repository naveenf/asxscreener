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
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range (ATR) using Wilder's smoothing.

        ATR measures volatility by considering the true range of price movement.
        Essential for position trading to ensure sufficient price movement potential.

        Args:
            df: DataFrame with OHLC data
            period: ATR period (default 14, Wilder's standard)

        Returns:
            Series with ATR values
        """
        # Calculate True Range (already have this method)
        tr = TechnicalIndicators.calculate_true_range(df)

        # Apply Wilder's smoothing (EMA with alpha = 1/period)
        atr = tr.ewm(alpha=1/period, adjust=False).mean()

        return atr

    @staticmethod
    def calculate_atr_percent(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate ATR as percentage of price.

        More useful for cross-stock comparison and filtering.

        Args:
            df: DataFrame with OHLC data
            period: ATR period (default 14)

        Returns:
            Series with ATR percentage values
        """
        atr = TechnicalIndicators.calculate_atr(df, period)
        atr_pct = (atr / df['Close']) * 100
        return atr_pct

    @staticmethod
    def calculate_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.Series:
        """
        Calculate Volume Simple Moving Average.

        Used to identify above-average volume periods which indicate
        institutional participation and more sustainable trends.

        Args:
            df: DataFrame with Volume column
            period: Volume SMA period (default 20)

        Returns:
            Series with Volume SMA values
        """
        if 'Volume' not in df.columns:
            raise ValueError("DataFrame must contain 'Volume' column")

        return df['Volume'].rolling(window=period).mean()

    @staticmethod
    def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI).

        RSI measures the magnitude of recent price changes to evaluate
        overbought or oversold conditions. Values range from 0-100.
        - RSI > 70: Overbought (potential reversal down)
        - RSI < 30: Oversold (potential reversal up)

        Uses Wilder's smoothing method (same as ADX) for consistency.

        Args:
            df: DataFrame with Close column
            period: RSI period (default 14)

        Returns:
            Series with RSI values (0-100)
        """
        if 'Close' not in df.columns:
            raise ValueError("DataFrame must contain 'Close' column")

        # Calculate price changes
        delta = df['Close'].diff()

        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # Use Wilder's smoothing (EMA with alpha=1/period)
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_bollinger_bands(
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands.

        Bollinger Bands consist of:
        - Middle Band: Simple Moving Average (SMA)
        - Upper Band: Middle Band + (std_dev * standard deviation)
        - Lower Band: Middle Band - (std_dev * standard deviation)

        Price touching or exceeding bands indicates overbought/oversold conditions.

        Args:
            df: DataFrame with Close column
            period: Period for middle band SMA (default 20)
            std_dev: Number of standard deviations (default 2.0)

        Returns:
            Tuple of (middle_band, upper_band, lower_band) Series
        """
        if 'Close' not in df.columns:
            raise ValueError("DataFrame must contain 'Close' column")

        # Middle band is SMA
        middle_band = df['Close'].rolling(window=period).mean()

        # Standard deviation
        rolling_std = df['Close'].rolling(window=period).std()

        # Upper and lower bands
        upper_band = middle_band + (rolling_std * std_dev)
        lower_band = middle_band - (rolling_std * std_dev)

        return middle_band, upper_band, lower_band

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
        sma_period: int = 200,
        atr_period: int = 14,
        volume_period: int = 20,
        rsi_period: int = 14,
        bb_period: int = 20,
        bb_std_dev: float = 2.0
    ) -> pd.DataFrame:
        """
        Add all indicators to DataFrame in one call.

        Args:
            df: DataFrame with OHLC data
            adx_period: Period for ADX calculation (default 14)
            sma_period: Period for SMA calculation (default 200)
            atr_period: Period for ATR calculation (default 14)
            volume_period: Period for Volume SMA calculation (default 20)
            rsi_period: Period for RSI calculation (default 14)
            bb_period: Period for Bollinger Bands (default 20)
            bb_std_dev: Standard deviations for Bollinger Bands (default 2.0)

        Returns:
            DataFrame with all technical indicators added
        """
        # Add ADX indicators
        df = TechnicalIndicators.calculate_adx(df, period=adx_period)

        # Add SMA
        df[f'SMA{sma_period}'] = TechnicalIndicators.calculate_sma(
            df, column='Close', period=sma_period
        )

        # Add ATR indicators
        df['ATR'] = TechnicalIndicators.calculate_atr(df, period=atr_period)
        df['ATR_PCT'] = TechnicalIndicators.calculate_atr_percent(df, period=atr_period)

        # Add Volume SMA
        df['Volume_SMA'] = TechnicalIndicators.calculate_volume_sma(df, period=volume_period)

        # Add RSI
        df['RSI'] = TechnicalIndicators.calculate_rsi(df, period=rsi_period)

        # Add Bollinger Bands
        bb_middle, bb_upper, bb_lower = TechnicalIndicators.calculate_bollinger_bands(
            df, period=bb_period, std_dev=bb_std_dev
        )
        df['BB_Middle'] = bb_middle
        df['BB_Upper'] = bb_upper
        df['BB_Lower'] = bb_lower

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
