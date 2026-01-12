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
    def calculate_ehlers_instant_trend(df: pd.DataFrame, alpha: float = 0.07) -> pd.DataFrame:
        """
        Calculate Ehler's Instantaneous Trend.
        A recursive filter that identifies short-term momentum triggers.
        """
        src = (df['High'] + df['Low']) / 2
        it = np.zeros(len(df))
        
        # Initial values
        for i in range(min(3, len(df))):
            it[i] = src.iloc[i]
            
        # Recursive calculation
        a2 = alpha * alpha
        for i in range(2, len(df)):
            it[i] = (alpha - a2 / 4.0) * src.iloc[i] + \
                    0.5 * a2 * src.iloc[i-1] - \
                    (alpha - 0.75 * a2) * src.iloc[i-2] + \
                    2 * (1 - alpha) * it[i-1] - \
                    (1 - alpha) * (1 - alpha) * it[i-2]
                    
        df = df.copy()
        df['IT_Trend'] = it
        # lag = 2.0*it - nz(it[2])
        df['IT_Trigger'] = 2.0 * df['IT_Trend'] - df['IT_Trend'].shift(2)
        return df

    @staticmethod
    def calculate_pivot_supertrend(df: pd.DataFrame, prd: int = 2, factor: float = 3.0, period: int = 10) -> pd.DataFrame:
        """
        Calculate Pivot Point Supertrend.
        Uses local pivots to establish a center line for ATR-based bands.
        """
        df = df.copy()
        
        # Calculate Pivot Highs and Lows
        df['ph'] = df['High'].rolling(window=prd*2+1, center=True).apply(lambda x: x.iloc[prd] if all(x.iloc[prd] >= i for i in x) else np.nan)
        df['pl'] = df['Low'].rolling(window=prd*2+1, center=True).apply(lambda x: x.iloc[prd] if all(x.iloc[prd] <= i for i in x) else np.nan)
        
        # Calculate Center Line
        center = np.nan
        centers = []
        for i in range(len(df)):
            last_pp = df['ph'].iloc[i] if not pd.isna(df['ph'].iloc[i]) else (df['pl'].iloc[i] if not pd.isna(df['pl'].iloc[i]) else np.nan)
            if not pd.isna(last_pp):
                if pd.isna(center):
                    center = last_pp
                else:
                    center = (center * 2 + last_pp) / 3.0
            centers.append(center)
        df['PP_Center'] = centers
        
        # Bands
        atr = TechnicalIndicators.calculate_atr(df, period)
        df['PP_Up'] = df['PP_Center'] - (factor * atr)
        df['PP_Dn'] = df['PP_Center'] + (factor * atr)
        
        # Trend tracking
        trend = 1
        t_up = np.zeros(len(df))
        t_dn = np.zeros(len(df))
        trends = []
        
        for i in range(1, len(df)):
            # TUp := close[1] > TUp[1] ? max(Up, TUp[1]) : Up
            t_up[i] = max(df['PP_Up'].iloc[i], t_up[i-1]) if df['Close'].iloc[i-1] > t_up[i-1] else df['PP_Up'].iloc[i]
            # TDown := close[1] < TDown[1] ? min(Dn, TDown[1]) : Dn
            t_dn[i] = min(df['PP_Dn'].iloc[i], t_dn[i-1]) if df['Close'].iloc[i-1] < t_dn[i-1] else df['PP_Dn'].iloc[i]
            
            # Trend := close > TDown[1] ? 1: close < TUp[1]? -1: nz(Trend[1], 1)
            if df['Close'].iloc[i] > t_dn[i-1]:
                trend = 1
            elif df['Close'].iloc[i] < t_up[i-1]:
                trend = -1
            trends.append(trend)
            
        df['PP_Trend'] = [1] + trends
        df['PP_TrailingSL'] = [t_up[i] if trends[i-1] == 1 else t_dn[i] for i in range(len(df))]
        return df

    @staticmethod
    def calculate_fibonacci_structure_trend(df: pd.DataFrame, period: int = 50, fib: float = 0.382) -> pd.DataFrame:
        """
        Calculate Fibonacci Structure Trend.
        Tracks high/low structure over a rolling window.
        """
        df = df.copy()
        hi = df['High'].rolling(window=period).max()
        lo = df['Low'].rolling(window=period).min()
        
        pos = 0
        poss = []
        retrace = 0.0
        retraces = []
        
        current_hi = df['High'].iloc[0]
        current_lo = df['Low'].iloc[0]
        
        for i in range(len(df)):
            if pos >= 0:
                if df['High'].iloc[i] > current_hi:
                    current_hi = df['High'].iloc[i]
                    retrace = current_hi - (current_hi - current_lo) * fib
                if df['High'].iloc[i] < retrace:
                    pos = -1
                    current_lo = df['Low'].iloc[i]
                    retrace = current_lo + (current_hi - current_lo) * fib
            else: # pos <= 0
                if df['Low'].iloc[i] < current_lo:
                    current_lo = df['Low'].iloc[i]
                    retrace = current_lo + (current_hi - current_lo) * fib
                if df['Low'].iloc[i] > retrace:
                    pos = 1
                    current_hi = df['High'].iloc[i]
                    retrace = current_hi - (current_hi - current_lo) * fib
            
            poss.append(pos)
            retraces.append(retrace)
            
        df['Fib_Pos'] = poss
        df['Fib_Retrace'] = retraces
        return df

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
    def calculate_bollinger_bands(
        df: pd.DataFrame,
        period: int = 20,
        std_dev: float = 2.0
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate Bollinger Bands.
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
    def calculate_ema(df: pd.DataFrame, column: str = 'Close', period: int = 14) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return df[column].ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_bb_width(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> pd.Series:
        """Calculate Bollinger Band Width (High - Low / Middle)."""
        middle, upper, lower = TechnicalIndicators.calculate_bollinger_bands(df, period, std_dev)
        return (upper - lower) / middle

    @staticmethod
    def resample_to_1h(df: pd.DataFrame) -> pd.DataFrame:
        """Resample 15m data to 1h for HTF filtering."""
        df_1h = df.resample('1h').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        return df_1h

    @staticmethod
    def add_all_indicators(
        df: pd.DataFrame,
        adx_period: int = 14,
        sma_period: int = 200,
        atr_period: int = 14,
        volume_period: int = 20,
        rsi_period: int = 14,
        bb_period: int = 20,
        bb_std_dev: float = 2.0,
        fib_period: int = 50,
        st_prd: int = 2,
        st_factor: float = 3.0,
        it_alpha: float = 0.07
    ) -> pd.DataFrame:
        """
        Add all indicators to DataFrame in one call.
        """
        # Add ADX indicators
        df = TechnicalIndicators.calculate_adx(df, period=adx_period)

        # Add SMA
        df[f'SMA{sma_period}'] = TechnicalIndicators.calculate_sma(
            df, column='Close', period=sma_period
        )

        # Add strategy-specific EMAs (5, 13, 34)
        df['EMA5'] = TechnicalIndicators.calculate_ema(df, period=5)
        df['EMA13'] = TechnicalIndicators.calculate_ema(df, period=13)
        df['EMA34'] = TechnicalIndicators.calculate_ema(df, period=34)

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
        df['BB_Width'] = TechnicalIndicators.calculate_bb_width(df)

        # Add Triple Trend Indicators
        df = TechnicalIndicators.calculate_fibonacci_structure_trend(df, period=fib_period)
        df = TechnicalIndicators.calculate_pivot_supertrend(df, prd=st_prd, factor=st_factor)
        df = TechnicalIndicators.calculate_ehlers_instant_trend(df, alpha=it_alpha)

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
    df = pd.read_csv(csv_path)
    if 'Date' in df.columns:
        df['Date'] = pd.to_datetime(df['Date'], utc=True)
        df.set_index('Date', inplace=True)
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
        df.index = df.index.floor('D')
    
    df.sort_index(inplace=True)
    df = TechnicalIndicators.add_all_indicators(df, adx_period, sma_period)
    return df
