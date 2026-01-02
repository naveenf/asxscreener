"""
Pydantic Models

Data models for API requests and responses.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class IndicatorValues(BaseModel):
    """Indicator values for a stock."""
    ADX: float
    DIPlus: float = Field(..., alias="DIPlus")
    DIMinus: float = Field(..., alias="DIMinus")
    SMA200: Optional[float] = None
    above_sma200: bool


class EntryConditions(BaseModel):
    """Entry condition checks."""
    adx_above_30: bool
    di_plus_above_di_minus: bool
    fresh_crossover: bool


class SignalResponse(BaseModel):
    """Signal response model."""
    ticker: str
    name: str
    signal: str  # "BUY", "HOLD", "SELL"
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
    signals: List[SignalResponse]
