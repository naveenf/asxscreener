"""
Portfolio Pydantic Schemas
"""

from pydantic import BaseModel
from datetime import date
from typing import Optional, List

class PortfolioItemCreate(BaseModel):
    ticker: str
    buy_date: date
    buy_price: float
    quantity: float
    brokerage: Optional[float] = 0.0
    strategy_type: Optional[str] = "triple_trend" # Default to triple_trend
    notes: Optional[str] = None

class PortfolioItemSell(BaseModel):
    quantity: float
    sell_price: float
    sell_date: date
    brokerage: Optional[float] = 0.0

class PortfolioItemResponse(BaseModel):
    id: str
    ticker: str
    buy_date: date
    buy_price: float
    quantity: float
    brokerage: Optional[float] = 0.0
    status: Optional[str] = "OPEN" # OPEN, CLOSED
    
    # Sell details (optional, for closed/sold items)
    sell_date: Optional[date] = None
    sell_price: Optional[float] = None
    sell_brokerage: Optional[float] = None
    realized_gain: Optional[float] = None
    
    # Tax fields
    financial_year: Optional[str] = None
    holding_period_days: Optional[int] = None
    is_long_term: Optional[bool] = None # > 12 months
    taxable_gain: Optional[float] = None # After CGT discount if applicable

    strategy_type: Optional[str] = "triple_trend"
    trend_signal: Optional[str] = "HOLD" # BUY, HOLD, EXIT
    exit_reason: Optional[str] = None
    notes: Optional[str] = None
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_percent: Optional[float] = None
    annualized_gain: Optional[float] = None

    class Config:
        from_attributes = True

class TaxSummaryItem(BaseModel):
    financial_year: str
    total_profit: float
    total_brokerage: float
    total_taxable_gain: float
    items: List[PortfolioItemResponse]

class TaxSummaryResponse(BaseModel):
    summary: List[TaxSummaryItem]
    lifetime_profit: float
    lifetime_brokerage: float