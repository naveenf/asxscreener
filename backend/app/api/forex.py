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
async def refresh_forex():
    """Trigger data refresh and re-run forex screener."""
    try:
        # 1. Download data (run the script using the same python executable)
        script_path = settings.PROJECT_ROOT / "scripts" / "download_forex.py"
        subprocess.run([sys.executable, str(script_path)], check=True)
        
        # 2. Run screener
        screener = ForexScreener(
            data_dir=FOREX_DATA_DIR,
            config_path=CONFIG_PATH,
            output_path=OUTPUT_PATH
        )
        results = screener.screen_all()
        
        return {
            "status": "success",
            "signals_count": results["signals_count"],
            "timestamp": results["generated_at"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

