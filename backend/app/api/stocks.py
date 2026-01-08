"""
Stocks API Routes

Endpoints for stock discovery and metadata.
"""

from fastapi import APIRouter, Query
from typing import List, Dict
import json
from ..config import settings

router = APIRouter(prefix="/api/stocks")

@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1)):
    """
    Search for stocks by ticker or name from the local stock list.
    """
    q = q.upper()
    results = []
    
    metadata_file = settings.METADATA_DIR / 'stock_list.json'
    if not metadata_file.exists():
        return []

    try:
        with open(metadata_file, 'r') as f:
            data = json.load(f)
            stocks = data.get('stocks', [])
            
            # 1. Exact ticker matches
            exact_ticker = [s for s in stocks if s['ticker'].upper() == q or s['ticker'].upper().split('.')[0] == q]
            results.extend(exact_ticker)
            
            # 2. Ticker starts with (if not already added)
            ticker_starts = [s for s in stocks if s['ticker'].upper().startswith(q) and s not in results]
            results.extend(ticker_starts)
            
            # 3. Name matches
            name_matches = [s for s in stocks if q in s['name'].upper() and s not in results]
            results.extend(name_matches)
            
            # Limit results
            return results[:10]
            
    except Exception as e:
        print(f"Error searching stocks: {e}")
        return []
