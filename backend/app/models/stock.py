"""
Pydantic Models

Data models for API requests and responses.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class IndicatorValues(BaseModel):
    """Indicator values for a stock - supports multiple strategies."""
    # Trend following indicators (optional)
    ADX: Optional[float] = None
    DIPlus: Optional[float] = Field(None, alias="DIPlus")
    DIMinus: Optional[float] = Field(None, alias="DIMinus")
    SMA200: Optional[float] = None
    above_sma200: Optional[bool] = None

    # Mean reversion indicators (optional)
    RSI: Optional[float] = None
    BB_Upper: Optional[float] = None
    BB_Middle: Optional[float] = None
    BB_Lower: Optional[float] = None
    BB_Distance_PCT: Optional[float] = None
    below_sma200: Optional[bool] = None


class EntryConditions(BaseModel):
    """Entry condition checks - flexible for multiple strategies."""
    # Trend following conditions
    adx_above_30: Optional[bool] = None
    di_plus_above_di_minus: Optional[bool] = None
    fresh_crossover: Optional[bool] = None

    # Mean reversion conditions
    price_above_upper_bb: Optional[bool] = None
    rsi_overbought: Optional[bool] = None


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
