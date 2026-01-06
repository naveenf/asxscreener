"""
Watchlist Pydantic Schemas
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class WatchlistItemCreate(BaseModel):
    ticker: str
    added_price: Optional[float] = None
    notes: Optional[str] = None

class WatchlistItemResponse(BaseModel):
    id: str
    ticker: str
    added_at: datetime
    added_price: float
    current_price: Optional[float] = None
    change_absolute: Optional[float] = None
    change_percent: Optional[float] = None
    days_in_watchlist: int
    notes: Optional[str] = None

    class Config:
        from_attributes = True
