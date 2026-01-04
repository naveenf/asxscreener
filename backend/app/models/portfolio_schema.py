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

    class Config:
        from_attributes = True
