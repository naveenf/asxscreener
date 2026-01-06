"""
Portfolio Routes

CRUD operations for user portfolio items using Firestore.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import List, Dict
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime
import yfinance as yf
import pandas as pd
import math

from ..firebase_setup import db
from ..models.portfolio_schema import PortfolioItemCreate, PortfolioItemResponse
from ..config import settings

router = APIRouter(prefix="/api/portfolio")

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

def normalize_ticker(ticker: str) -> str:
    """Ensure ticker has .AX suffix for ASX stocks."""
    ticker = ticker.upper().strip()
    if not ticker.endswith(".AX"):
        return f"{ticker}.AX"
    return ticker

def get_current_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Fetch current prices for a list of tickers using yfinance.
    Returns a dict {ticker_input: current_price}
    """
    if not tickers:
        return {}
    
    # Map input ticker to yfinance ticker
    ticker_map = {t: normalize_ticker(t) for t in tickers}
    yf_tickers = list(ticker_map.values())
    
    try:
        # Fetch data for all tickers
        # Use grouping='ticker' to ensure consistent structure for single/multi tickers
        data = yf.download(yf_tickers, period="1d", progress=False, group_by='ticker')
        
        prices = {}
        
        if data.empty:
            return prices

        for original_ticker, yf_ticker in ticker_map.items():
            try:
                # Handle DataFrame structure variations based on number of tickers
                if len(yf_tickers) == 1:
                    # If single ticker, data columns are 'Open', 'High', 'Low', 'Close', ...
                    # Or it might be multi-index depending on yfinance version.
                    # With group_by='ticker', accessing the ticker column might be needed if multi-index.
                    # But if 1 ticker, it often just gives the OHLCV cols directly or under the ticker level.
                    # Let's try to access safe check.
                    
                    if isinstance(data.columns, pd.MultiIndex):
                        # data[yf_ticker]['Close']
                        last_price = data[yf_ticker]['Close'].iloc[-1]
                    else:
                        last_price = data['Close'].iloc[-1]
                else:
                    # Multi-ticker: data[yf_ticker]['Close']
                    last_price = data[yf_ticker]['Close'].iloc[-1]
                
                prices[original_ticker] = float(last_price)
            except Exception:
                # Price not found for this ticker
                continue
                
        return prices
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return {}

def validate_and_get_price(ticker: str) -> float:
    """
    Check if ticker is valid and return current price.
    Raises HTTPException if invalid.
    """
    yf_ticker = normalize_ticker(ticker)
    try:
        t = yf.Ticker(yf_ticker)
        # Try fast_info first
        price = t.fast_info.last_price
        if price is not None:
            return float(price)
        
        # Fallback to history
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
            
        raise Exception("No data found")
    except Exception:
         raise HTTPException(status_code=400, detail=f"Invalid ticker symbol: {ticker}")

def calculate_metrics(item_data, current_price):
    """Calculate gain/loss and annualized return."""
    if not current_price:
        return None, None, None, None
        
    quantity = item_data['quantity']
    buy_price = item_data['buy_price']
    
    # Simple Metrics
    current_value = current_price * quantity
    cost_basis = buy_price * quantity
    gain_loss = current_value - cost_basis
    gain_loss_percent = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
    
    # Annualized Gain Calculation
    # CAGR = (End Value / Start Value) ^ (365 / Days) - 1
    # If held for less than a year, simple return is often used, or we just show the extrapolated annual rate.
    # To avoid huge numbers for very short durations (e.g. 1 day 1% = huge annual), 
    # we can cap it or just return it raw.
    # Let's return raw but handle the 'days=0' case.
    
    buy_date = item_data['buy_date']
    if isinstance(buy_date, str):
        # Should be date object by now usually, but safe check
        buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
        
    days_held = (datetime.utcnow().date() - buy_date).days
    
    annualized_gain = 0.0
    
    if cost_basis > 0:
        total_return_ratio = current_value / cost_basis
        
        if days_held < 1:
            days_held = 1 # Avoid division by zero
            
        # Only calculate Annualized Gain (CAGR) if held for more than 1 year (365 days)
        # Short-term annualized compounding produces unrealistic numbers (e.g. 50 billion %)
        if days_held > 365:
            try:
                annualized_gain = (pow(total_return_ratio, (365.0 / days_held)) - 1) * 100
            except Exception:
                annualized_gain = None
        else:
            annualized_gain = None

    return current_value, gain_loss, gain_loss_percent, annualized_gain

@router.get("", response_model=List[PortfolioItemResponse])
async def list_portfolio(email: str = Depends(get_current_user_email)):
    """Get all items in user's portfolio with current market data."""
    try:
        portfolio_ref = db.collection('users').document(email).collection('portfolio')
        docs = portfolio_ref.stream()
        
        items = []
        tickers_to_fetch = []
        raw_items = []

        for doc in docs:
            data = doc.to_dict()
            buy_date = data.get('buy_date')
            if isinstance(buy_date, str):
                buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
            
            item = {
                'id': doc.id,
                'ticker': data.get('ticker'),
                'buy_date': buy_date,
                'buy_price': data.get('buy_price'),
                'quantity': data.get('quantity'),
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
            
            current_value, gain_loss, gain_loss_percent, annualized_gain = calculate_metrics(item, current_price)
            
            items.append(PortfolioItemResponse(
                id=item['id'],
                ticker=ticker,
                buy_date=item['buy_date'],
                buy_price=item['buy_price'],
                quantity=item['quantity'],
                notes=item['notes'],
                current_price=current_price,
                current_value=current_value,
                gain_loss=gain_loss,
                gain_loss_percent=gain_loss_percent,
                annualized_gain=annualized_gain
            ))
            
        return items
    except Exception as e:
        print(f"Portfolio List Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch portfolio")

@router.post("", response_model=PortfolioItemResponse)
async def add_to_portfolio(
    item: PortfolioItemCreate,
    email: str = Depends(get_current_user_email)
):
    """Add a new stock to portfolio in Firestore."""
    try:
        # Validate ticker and get price
        current_price = validate_and_get_price(item.ticker)
        
        portfolio_ref = db.collection('users').document(email).collection('portfolio')
        
        doc_data = {
            'ticker': item.ticker,
            'buy_date': item.buy_date.isoformat(),
            'buy_price': item.buy_price,
            'quantity': item.quantity,
            'notes': item.notes,
            'created_at': datetime.utcnow()
        }
        
        update_time, doc_ref = portfolio_ref.add(doc_data)
        
        # Calculate initial metrics (pass dict that looks like item)
        item_dict = item.model_dump() # Pydantic v2
        # fix buy_date to be date object if it isn't
        
        current_value, gain_loss, gain_loss_percent, annualized_gain = calculate_metrics(item_dict, current_price)
        
        return PortfolioItemResponse(
            id=doc_ref.id,
            ticker=item.ticker,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            notes=item.notes,
            current_price=current_price,
            current_value=current_value,
            gain_loss=gain_loss,
            gain_loss_percent=gain_loss_percent,
            annualized_gain=annualized_gain
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Add Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add item")

@router.delete("/{item_id}")
async def remove_from_portfolio(
    item_id: str,
    email: str = Depends(get_current_user_email)
):
    """Remove a stock from portfolio in Firestore."""
    try:
        doc_ref = db.collection('users').document(email).collection('portfolio').document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        doc_ref.delete()
        return {"message": "Item removed"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Delete Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete item")

@router.put("/{item_id}", response_model=PortfolioItemResponse)
async def update_portfolio_item(
    item_id: str,
    item: PortfolioItemCreate,
    email: str = Depends(get_current_user_email)
):
    """Update a portfolio item in Firestore."""
    try:
        current_price = validate_and_get_price(item.ticker)
        
        doc_ref = db.collection('users').document(email).collection('portfolio').document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        doc_data = {
            'ticker': item.ticker,
            'buy_date': item.buy_date.isoformat(),
            'buy_price': item.buy_price,
            'quantity': item.quantity,
            'notes': item.notes,
            'updated_at': datetime.utcnow()
        }
        
        doc_ref.update(doc_data)
        
        item_dict = item.model_dump()
        current_value, gain_loss, gain_loss_percent, annualized_gain = calculate_metrics(item_dict, current_price)
        
        return PortfolioItemResponse(
            id=item_id,
            ticker=item.ticker,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            notes=item.notes,
            current_price=current_price,
            current_value=current_value,
            gain_loss=gain_loss,
            gain_loss_percent=gain_loss_percent,
            annualized_gain=annualized_gain
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Update Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update item")