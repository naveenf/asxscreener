"""
Forex Portfolio Pydantic Schemas
"""

from pydantic import BaseModel
from datetime import date
from typing import Optional, List

class ForexPortfolioItemCreate(BaseModel):
    symbol: str  # OANDA Symbol (e.g., XAG_USD)
    direction: str = "BUY" # BUY (Long) or SELL (Short)
    buy_date: date
    buy_price: float  # Price in pair's currency
    quantity: float
    notes: Optional[str] = None
    strategy: Optional[str] = None
    timeframe: Optional[str] = None

class ForexPortfolioItemSell(BaseModel):
    quantity: float
    sell_price: float
    sell_date: date

class ForexPortfolioItemResponse(BaseModel):
    id: str
    symbol: str
    direction: str = "BUY"
    buy_date: date
    buy_price: float
    quantity: float
    status: str = "OPEN" # OPEN, CLOSED
    
    # Strategy Context
    strategy: Optional[str] = None
    timeframe: Optional[str] = None
    
    # Exit Signal
    exit_signal: bool = False
    exit_reason: Optional[str] = None
    
    # Sell details
    sell_date: Optional[date] = None
    sell_price: Optional[float] = None
    
    notes: Optional[str] = None
    
    # AUD Metrics (Calculated)
    current_price: Optional[float] = None # Native currency
    gain_loss_aud: Optional[float] = None
    gain_loss_percent: Optional[float] = None
    realized_gain_aud: Optional[float] = None

    class Config:
        from_attributes = True
