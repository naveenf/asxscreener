"""
Watchlist Routes

CRUD operations for user watchlist items using Firestore.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import List
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, timezone

from ..firebase_setup import db
from ..models.watchlist_schema import WatchlistItemCreate, WatchlistItemResponse
from ..config import settings
from ..services.market_data import get_current_prices, validate_and_get_price

router = APIRouter(prefix="/api/watchlist")

async def get_current_user_email(authorization: str = Header(...)) -> str:
    """
    Dependency to get user email from Google ID token.
    Expects 'Authorization: Bearer <token>'
    """
    try:
        token = authorization.replace("Bearer ", "")
        id_info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
        return email
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def calculate_metrics(item_data, current_price):
    """Calculate watchlist metrics."""
    if not current_price:
        return None, None, None
        
    added_price = item_data['added_price']
    
    change_absolute = current_price - added_price
    change_percent = (change_absolute / added_price * 100) if added_price > 0 else 0
    
    added_at = item_data['added_at']
    # Ensure added_at is offset-aware or offset-naive consistently
    if added_at.tzinfo is None:
        added_at = added_at.replace(tzinfo=timezone.utc)
        
    days_in_watchlist = (datetime.now(timezone.utc) - added_at).days
    
    return change_absolute, change_percent, days_in_watchlist

@router.get("", response_model=List[WatchlistItemResponse])
async def list_watchlist(email: str = Depends(get_current_user_email)):
    """Get all items in user's watchlist."""
    try:
        watchlist_ref = db.collection('users').document(email).collection('watchlist')
        docs = watchlist_ref.stream()
        
        items = []
        tickers_to_fetch = []
        raw_items = []

        for doc in docs:
            data = doc.to_dict()
            
            # Handle timestamps from Firestore
            added_at = data.get('added_at')
            # If it's a Firestore timestamp, it might need conversion, or if it's stored as ISO string
            if isinstance(added_at, str):
                added_at = datetime.fromisoformat(added_at)
            
            item = {
                'id': doc.id,
                'ticker': data.get('ticker'),
                'added_at': added_at,
                'added_price': data.get('added_price'),
                'notes': data.get('notes')
            }
            raw_items.append(item)
            if item['ticker']:
                tickers_to_fetch.append(item['ticker'])
        
        # Batch fetch current prices
        current_prices = get_current_prices(list(set(tickers_to_fetch)))
        
        # Enrich items
        for item in raw_items:
            ticker = item['ticker']
            current_price = current_prices.get(ticker)
            
            change_absolute, change_percent, days_in_watchlist = calculate_metrics(item, current_price)
            
            items.append(WatchlistItemResponse(
                id=item['id'],
                ticker=ticker,
                added_at=item['added_at'],
                added_price=item['added_price'],
                notes=item['notes'],
                current_price=current_price,
                change_absolute=change_absolute,
                change_percent=change_percent,
                days_in_watchlist=days_in_watchlist
            ))
            
        return items
    except Exception as e:
        print(f"Watchlist List Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch watchlist")

@router.post("", response_model=WatchlistItemResponse)
async def add_to_watchlist(
    item: WatchlistItemCreate,
    email: str = Depends(get_current_user_email)
):
    """Add a new stock to watchlist."""
    try:
        current_price = validate_and_get_price(item.ticker)
        
        # Use current price as added_price if not provided
        added_price = item.added_price if item.added_price is not None else current_price
        
        watchlist_ref = db.collection('users').document(email).collection('watchlist')
        
        # Check if already exists? Maybe allow duplicates? Usually watchlist is unique per ticker.
        # Let's check for existence to prevent duplicates
        existing = watchlist_ref.where('ticker', '==', item.ticker).limit(1).get()
        if existing:
             raise HTTPException(status_code=400, detail="Stock already in watchlist")

        added_at = datetime.now(timezone.utc)
        
        doc_data = {
            'ticker': item.ticker,
            'added_at': added_at.isoformat(),
            'added_price': added_price,
            'notes': item.notes
        }
        
        update_time, doc_ref = watchlist_ref.add(doc_data)
        
        item_dict = {
            'ticker': item.ticker,
            'added_at': added_at,
            'added_price': added_price,
            'notes': item.notes
        }
        
        change_absolute, change_percent, days_in_watchlist = calculate_metrics(item_dict, current_price)
        
        return WatchlistItemResponse(
            id=doc_ref.id,
            ticker=item.ticker,
            added_at=added_at,
            added_price=added_price,
            notes=item.notes,
            current_price=current_price,
            change_absolute=change_absolute,
            change_percent=change_percent,
            days_in_watchlist=days_in_watchlist
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Watchlist Add Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add to watchlist")

@router.delete("/{item_id}")
async def remove_from_watchlist(
    item_id: str,
    email: str = Depends(get_current_user_email)
):
    """Remove a stock from watchlist."""
    try:
        doc_ref = db.collection('users').document(email).collection('watchlist').document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        doc_ref.delete()
        return {"message": "Item removed"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Watchlist Delete Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete item")
