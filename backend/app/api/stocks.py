"""
Stocks API Routes

Endpoints for stock discovery and metadata.
"""

from fastapi import APIRouter, Query
from typing import List, Dict
import json
from ..config import settings
from ..firebase_setup import db

router = APIRouter(prefix="/api/stocks")

@router.get("/search")
async def search_stocks(q: str = Query(..., min_length=1)):
    """
    Search for stocks by ticker or name.
    1. Local stock list (ASX300)
    2. User Portfolios
    3. Potential ticker match (if not in list)
    """
    q = q.upper().strip()
    results = []
    
    # 1. Load Local stock list
    metadata_file = settings.METADATA_DIR / 'stock_list.json'
    local_stocks = []
    if metadata_file.exists():
        try:
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                local_stocks = data.get('stocks', [])
        except Exception as e:
            print(f"Error loading stock list: {e}")

    # Exact ticker match in local list
    exact_ticker = [s for s in local_stocks if s['ticker'].upper() == q or s['ticker'].upper().split('.')[0] == q]
    results.extend(exact_ticker)
    
    # 2. Check User Portfolios for custom tickers
    try:
        # Collection group query for all portfolios
        portfolio_docs = db.collection_group('portfolio').stream()
        portfolio_tickers = set()
        for doc in portfolio_docs:
            item = doc.to_dict()
            t = item.get('ticker', '').upper().strip()
            if t and q in t and t not in [r['ticker'] for r in results]:
                # Construct a result if it's not already in results
                results.append({
                    "ticker": t,
                    "name": f"Portfolio Stock: {t}",
                    "sector": "Portfolio"
                })
    except Exception as e:
        print(f"Error searching portfolio stocks: {e}")

    # 3. Fuzzy matches in local list
    ticker_starts = [s for s in local_stocks if s['ticker'].upper().startswith(q) and s not in results]
    results.extend(ticker_starts)
    
    name_matches = [s for s in local_stocks if q in s['name'].upper() and s not in results]
    results.extend(name_matches)

    # 4. Fallback: If it looks like a ticker (3-4 chars) but not found, suggest it
    if len(q) >= 3 and len(q) <= 5 and not any(r['ticker'].split('.')[0] == q for r in results):
        results.append({
            "ticker": f"{q}.AX",
            "name": f"Analyze '{q}.AX'",
            "sector": "New Search"
        })
            
    # Limit results
    return results[:10]
