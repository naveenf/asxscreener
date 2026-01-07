"""
Pydantic Models

Data models for API requests and responses.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class IndicatorValues(BaseModel):
    """Indicator values for a stock - supports multiple strategies."""
    # Triple Trend Confirmation indicators
    Fib_Pos: Optional[int] = None
    PP_Trend: Optional[int] = None
    PP_TrailingSL: Optional[float] = None
    IT_Trend: Optional[float] = None
    IT_Trigger: Optional[float] = None
    SMA200: Optional[float] = None
    above_sma200: Optional[bool] = None

    # Mean reversion indicators
    RSI: Optional[float] = None
    BB_Upper: Optional[float] = None
    BB_Middle: Optional[float] = None
    BB_Lower: Optional[float] = None
    BB_Distance_PCT: Optional[float] = None
    below_sma200: Optional[bool] = None

    # Legacy (kept for safety)
    ADX: Optional[float] = None
    DIPlus: Optional[float] = None
    DIMinus: Optional[float] = None


class EntryConditions(BaseModel):
    """Entry condition checks - flexible for multiple strategies."""
    # Triple Trend conditions
    fib_structure_bullish: Optional[bool] = None
    supertrend_bullish: Optional[bool] = None
    it_trend_bullish: Optional[bool] = None

    # Mean reversion conditions
    rsi_oversold: Optional[bool] = None
    price_below_lower_bb: Optional[bool] = None
    above_sma200: Optional[bool] = None


class SignalResponse(BaseModel):
    """Signal response model - supports multiple strategies."""
    ticker: str
    name: str
    signal: str  # "BUY", "HOLD", "SELL"
    strategy: str  # "trend_following", "mean_reversion"
    score: float
    current_price: float
    indicators: IndicatorValues
    entry_conditions: EntryConditions
    timestamp: str
    sector: Optional[str] = None

    class Config:
        populate_by_name = True


class ScreenerStatus(BaseModel):
    """Screener status response."""
    last_updated: str
    total_stocks: int
    signals_count: int
    status: str  # "ready", "updating", "error"


class SignalsListResponse(BaseModel):
    """List of signals response."""
    generated_at: str
    total_stocks: int
    signals_count: int
    trend_following_count: Optional[int] = 0
    mean_reversion_count: Optional[int] = 0
    signals: List[SignalResponse]
