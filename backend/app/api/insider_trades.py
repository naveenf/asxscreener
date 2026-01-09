"""
Insider Trades API Routes
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict
from pathlib import Path

from ..config import settings
from ..services.insider_trades import InsiderTradesService

router = APIRouter(prefix="/api/insider-trades")

def get_service():
    storage_path = settings.PROCESSED_DATA_DIR / 'insider_trades.json'
    return InsiderTradesService(storage_path)

@router.get("")
async def get_insider_trades():
    """Get significant director trades grouped by ticker."""
    try:
        service = get_service()
        return service.get_grouped_trades()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh")
async def refresh_insider_trades():
    """Trigger manual scrape of director transactions."""
    try:
        service = get_service()
        result = service.scrape_and_update()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
