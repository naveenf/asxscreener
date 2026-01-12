"""
API Routes

REST API endpoints for the stock screener.
"""

import json
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pathlib import Path
from datetime import datetime

from ..models.stock import SignalResponse, ScreenerStatus, SignalsListResponse
from ..config import settings
from ..services.screener import StockScreener
from ..services.market_data import update_all_stocks_data
from . import auth  # Import auth router
from . import portfolio  # Import portfolio router
from . import watchlist  # Import watchlist router
from . import analysis   # Import analysis router
from . import stocks     # Import stocks router
from . import insider_trades # Import insider trades router
from . import forex          # Import forex router
from . import forex_portfolio # Import forex portfolio router
from ..services.insider_trades import InsiderTradesService
from ..services.forex_screener import ForexScreener
from ..services.refresh_manager import refresh_manager
from ..services.tasks import run_stock_refresh_task

router = APIRouter()

# Include routers
router.include_router(auth.router)
router.include_router(portfolio.router)
router.include_router(watchlist.router)
router.include_router(analysis.router)
router.include_router(stocks.router)
router.include_router(insider_trades.router)
router.include_router(forex.router)
router.include_router(forex_portfolio.router)

@router.get("/api/status/refresh")
async def get_refresh_status():
    """Get the status of ongoing background refresh tasks."""
    return refresh_manager.get_status()


def load_signals() -> dict:
    """Load signals from JSON file."""
    signals_file = settings.PROCESSED_DATA_DIR / 'signals.json'

    if not signals_file.exists():
        raise HTTPException(status_code=404, detail="No signals found. Run screener first.")

    with open(signals_file, 'r') as f:
        return json.load(f)


@router.get("/api/signals", response_model=List[SignalResponse])
async def get_signals(
    min_score: Optional[float] = Query(0, ge=0, le=100, description="Minimum signal score"),
    sort_by: Optional[str] = Query("score", pattern="^(score|adx|ticker)$", description="Sort field")
):
    """
    Get current trading signals.

    - **min_score**: Minimum signal score (0-100)
    - **sort_by**: Sort field (score, adx, ticker)
    """
    data = load_signals()
    signals = data.get('signals', [])

    # Filter by minimum score
    if min_score > 0:
        signals = [s for s in signals if s.get('score', 0) >= min_score]

    # Sort signals
    if sort_by == 'score':
        signals.sort(key=lambda x: x.get('score', 0), reverse=True)
    elif sort_by == 'adx':
        signals.sort(key=lambda x: x.get('indicators', {}).get('ADX', 0), reverse=True)
    elif sort_by == 'ticker':
        signals.sort(key=lambda x: x.get('ticker', ''))

    return signals


@router.get("/api/stocks/{ticker}")
async def get_stock_detail(ticker: str):
    """
    Get detailed data for specific stock.

    - **ticker**: Stock ticker (e.g., CBA.AX)
    """
    data = load_signals()
    signals = data.get('signals', [])

    # Find signal for this ticker
    stock_signal = next((s for s in signals if s['ticker'] == ticker), None)

    if not stock_signal:
        raise HTTPException(
            status_code=404,
            detail=f"No signal found for {ticker}"
        )

    return stock_signal


@router.get("/api/status", response_model=ScreenerStatus)
async def get_status():
    """
    Get screener status.

    Returns information about the last screening run.
    """
    try:
        data = load_signals()

        return ScreenerStatus(
            last_updated=data.get('generated_at', 'Unknown'),
            total_stocks=data.get('total_stocks', 0),
            signals_count=data.get('signals_count', 0),
            status="ready"
        )

    except HTTPException:
        return ScreenerStatus(
            last_updated="Never",
            total_stocks=0,
            signals_count=0,
            status="no_data"
        )
    except Exception as e:
        return ScreenerStatus(
            last_updated="Error",
            total_stocks=0,
            signals_count=0,
            status="error"
        )


from fastapi import BackgroundTasks

@router.post("/api/refresh")
async def refresh_data(background_tasks: BackgroundTasks):
    """
    Trigger background data refresh and re-run screener.
    """
    if refresh_manager.is_refreshing_stocks:
        return {"status": "error", "message": "Refresh already in progress"}
    
    background_tasks.add_task(run_stock_refresh_task)
    
    return {
        "status": "success",
        "message": "Refresh started in background"
    }
