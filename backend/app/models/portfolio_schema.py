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
    notes: Optional[str] = None

class PortfolioItemResponse(BaseModel):
    id: str
    ticker: str
    buy_date: date
    buy_price: float
    quantity: float
    notes: Optional[str] = None
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    gain_loss: Optional[float] = None
    gain_loss_percent: Optional[float] = None
    annualized_gain: Optional[float] = None

    class Config:
        from_attributes = True