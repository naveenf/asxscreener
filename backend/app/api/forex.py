"""
Forex API Router

Endpoints for Forex and Commodity signals.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
import json
import asyncio
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from ..services.forex_screener import ForexScreener
from ..services.oanda_price import OandaPriceService
from ..config import settings
from ..services.refresh_manager import refresh_manager
from ..services.tasks import run_forex_refresh_task

router = APIRouter(prefix="/api/forex", tags=["forex"])

# Define paths
CONFIG_PATH = settings.METADATA_DIR / "forex_pairs.json"
FOREX_DATA_DIR = settings.DATA_DIR / "forex_raw"
OUTPUT_PATH = settings.PROCESSED_DATA_DIR / "forex_signals.json"

@router.get("/live-prices")
async def get_live_prices():
    """Bulk price + daily change for all active pairs — used by ticker tape."""
    with open(CONFIG_PATH, 'r') as f:
        config = json.load(f)

    pairs = config.get("pairs", [])

    def fetch_one(pair):
        data = OandaPriceService.get_price_and_change(pair["oanda_symbol"])
        if not data:
            return None
        return {
            "symbol": pair["oanda_symbol"],
            "name": pair["name"],
            "type": pair.get("type", "Forex"),
            **data
        }

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=len(pairs)) as executor:
        futures = [loop.run_in_executor(executor, fetch_one, pair) for pair in pairs]
        raw = await asyncio.gather(*futures)

    results = [r for r in raw if r is not None]
    return {"prices": results, "fetched_at": datetime.utcnow().isoformat() + "Z"}


@router.get("/price/{symbol}")
async def get_forex_price(symbol: str):
    """Get real-time price from OANDA."""
    price = OandaPriceService.get_current_price(symbol)
    if price is None:
        raise HTTPException(status_code=404, detail="Price unavailable")
    return {"symbol": symbol, "price": price}

@router.get("/signals")
async def get_forex_signals():
    """Get current forex and commodity signals."""
    if not OUTPUT_PATH.exists():
        return {"signals": [], "message": "No signals generated yet. Run refresh."}
    
    with open(OUTPUT_PATH, 'r') as f:
        return json.load(f)

@router.post("/refresh")
async def refresh_forex(background_tasks: BackgroundTasks, mode: str = 'sniper'):
    """
    Trigger background data refresh and re-run forex screener.

    Args:
        mode: 'sniper' (Elite 3 selection) or 'balanced' (all signals)
    """
    if refresh_manager.is_refreshing_forex:
        return {"status": "error", "message": "Forex refresh already in progress"}

    background_tasks.add_task(run_forex_refresh_task, mode)
    
    return {
        "status": "success",
        "message": "Forex refresh started in background"
    }