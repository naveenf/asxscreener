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
from ..services.insider_trades import InsiderTradesService

router = APIRouter()

# Include routers
router.include_router(auth.router)
router.include_router(portfolio.router)
router.include_router(watchlist.router)
router.include_router(analysis.router)
router.include_router(stocks.router)
router.include_router(insider_trades.router)
router.include_router(forex.router)


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


@router.post("/api/refresh")
async def refresh_data():
    """
    Trigger data refresh and re-run screener.

    This will:
    1. Download latest daily data for all stocks
    2. Re-calculate indicators for all stocks
    3. Detect new signals
    4. Update signals.json
    """
    try:
        print(f"Starting manual refresh at {datetime.now()}")
        # Create screener (new detectors are initialized inside StockScreener)
        screener = StockScreener(
            data_dir=settings.RAW_DATA_DIR,
            metadata_dir=settings.METADATA_DIR,
            output_dir=settings.PROCESSED_DATA_DIR
        )
        
        # 1. Update data from yfinance
        stocks = screener.load_stock_list()
        tickers = [s['ticker'] for s in stocks]
        print(f"Updating data for {len(tickers)} tickers...")
        update_results = update_all_stocks_data(tickers, settings.RAW_DATA_DIR)
        success_count = sum(1 for r in update_results.values() if r)
        print(f"Successfully updated {success_count}/{len(tickers)} CSV files")

        # 2. Run screener
        print("Running screener...")
        results = screener.screen_all_stocks()
        screener.save_signals(results)
        
        # 3. Update Insider Trades
        print("Updating insider trades...")
        insider_service = InsiderTradesService(settings.PROCESSED_DATA_DIR / 'insider_trades.json')
        insider_service.scrape_and_update()
        
        print(f"Refresh complete. Found {results['signals_count']} signals.")

        return {
            "status": "success",
            "message": "Data refreshed successfully",
            "signals_found": results['signals_count'],
            "timestamp": results['generated_at']
        }

    except Exception as e:
        print(f"Refresh failed: {e}")
        raise HTTPException(status_code=500, detail=f"Refresh failed: {str(e)}")


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
