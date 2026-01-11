"""
Forex API Router

Endpoints for Forex and Commodity signals.
"""

from fastapi import APIRouter, HTTPException
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

from ..services.forex_screener import ForexScreener
from ..config import settings

router = APIRouter(prefix="/api/forex", tags=["forex"])

# Define paths
CONFIG_PATH = settings.METADATA_DIR / "forex_pairs.json"
FOREX_DATA_DIR = settings.DATA_DIR / "forex_raw"
OUTPUT_PATH = settings.PROCESSED_DATA_DIR / "forex_signals.json"

@router.get("/signals")
async def get_forex_signals():
    """Get current forex and commodity signals."""
    if not OUTPUT_PATH.exists():
        return {"signals": [], "message": "No signals generated yet. Run refresh."}
    
    with open(OUTPUT_PATH, 'r') as f:
        return json.load(f)

@router.post("/refresh")
async def refresh_forex(mode: str = 'sniper'):
    """
    Trigger data refresh and re-run forex screener.

    Args:
        mode: 'sniper' (Elite 3 selection) or 'balanced' (all signals)
    """
    try:
        results = ForexScreener.run_orchestrated_refresh(
            project_root=settings.PROJECT_ROOT,
            data_dir=FOREX_DATA_DIR,
            config_path=CONFIG_PATH,
            output_path=OUTPUT_PATH,
            mode=mode
        )

        # Format response based on mode
        if mode == 'sniper':
            return {
                "status": "success",
                "mode": "sniper",
                "elite_signals_count": results.get("top_n_selected", 0),
                "total_signals_found": results.get("signals_found", 0),
                "total_analyzed": results.get("total_analyzed", 0),
                "timestamp": results["generated_at"]
            }
        else:
            return {
                "status": "success",
                "mode": "balanced",
                "signals_count": results.get("signals_count", 0),
                "timestamp": results["generated_at"]
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

