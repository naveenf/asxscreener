"""
Portfolio Routes

CRUD operations for user portfolio items using Firestore.
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import List, Dict
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, date
import math
import pandas as pd

from ..firebase_setup import db
from ..models.portfolio_schema import PortfolioItemCreate, PortfolioItemResponse
from ..config import settings
from ..services.market_data import get_current_prices, validate_and_get_price, normalize_ticker
from ..services.indicators import TechnicalIndicators
from ..services.triple_trend_detector import TripleTrendDetector
from ..services.mean_reversion_detector import MeanReversionDetector

router = APIRouter(prefix="/api/portfolio")

def calculate_trend_signal(ticker: str, buy_price: float, buy_date: date, strategy_type: str) -> tuple[str, str]:
    """
    Calculate current trend/action for a stock in portfolio.
    Returns (signal, reason)
    """
    try:
        yf_ticker = normalize_ticker(ticker)
        csv_path = settings.RAW_DATA_DIR / f"{yf_ticker}.csv"
        
        if not csv_path.exists():
            return "HOLD", "No history data"
            
        df = pd.read_csv(csv_path, index_col='Date', parse_dates=True)
        if df.empty:
            return "HOLD", "Empty history"
            
        # Standardize index: timezone-naive and floored to midnight
        df.index = pd.to_datetime(df.index, utc=True)
        df.index = df.index.tz_localize(None)
        df.index = df.index.normalize()
            
        # Add indicators
        df = TechnicalIndicators.add_all_indicators(
            df,
            adx_period=settings.ADX_PERIOD,
            sma_period=settings.SMA_PERIOD,
            atr_period=settings.ATR_PERIOD,
            volume_period=settings.VOLUME_PERIOD,
            rsi_period=settings.RSI_PERIOD,
            bb_period=settings.BB_PERIOD,
            bb_std_dev=settings.BB_STD_DEV
        )
        
        # Instantiate correct detector
        if strategy_type == 'mean_reversion':
            detector = MeanReversionDetector(
                rsi_threshold=settings.RSI_THRESHOLD,
                profit_target=settings.MEAN_REVERSION_PROFIT_TARGET,
                bb_period=settings.BB_PERIOD,
                bb_std_dev=settings.BB_STD_DEV,
                rsi_period=settings.RSI_PERIOD,
                time_limit=settings.MEAN_REVERSION_TIME_LIMIT
            )
        else: # Default to triple_trend
            detector = TripleTrendDetector(
                profit_target=settings.PROFIT_TARGET,
                stop_loss=settings.TREND_FOLLOWING_STOP_LOSS,
                time_limit=settings.TREND_FOLLOWING_TIME_LIMIT
            )
            
        # Find entry index based on buy_date
        entry_idx = None
        target_date = pd.Timestamp(buy_date).replace(tzinfo=None).floor('D')
        if target_date in df.index:
            entry_idx = df.index.get_loc(target_date)
        else:
            # Find closest date after buy_date
            future_dates = df.index[df.index >= target_date]
            if not future_dates.empty:
                entry_idx = df.index.get_loc(future_dates[0])
        
        # 1. Check for EXIT signal first
        exit_info = detector.detect_exit_signal(df, buy_price, current_index=-1, entry_index=entry_idx)
        if exit_info.get('has_exit'):
            reason = exit_info.get('exit_reason', 'Unknown')
            return "EXIT", reason.replace('_', ' ').title()
            
        # 2. Check for fresh BUY signal (add to position)
        entry_info = detector.detect_entry_signal(df)
        if entry_info.get('has_signal'):
            return "BUY", "Fresh Signal"
            
        return "HOLD", "Strong Trend"
        
    except Exception as e:
        print(f"Error calculating trend for {ticker}: {e}")
        return "HOLD", "Error"

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
                'strategy_type': data.get('strategy_type', 'triple_trend'),
                'notes': data.get('notes')
            }
            raw_items.append(item)
            if item['ticker']:
                tickers_to_fetch.append(item['ticker'])
        
        # Batch fetch current prices
        current_prices = get_current_prices(list(set(tickers_to_fetch)))
        
        # Enrichment items
        for item in raw_items:
            ticker = item['ticker']
            current_price = current_prices.get(ticker)
            
            current_value, gain_loss, gain_loss_percent, annualized_gain = calculate_metrics(item, current_price)
            
            # Calculate Trend Signal
            trend_signal, exit_reason = calculate_trend_signal(
                ticker, item['buy_price'], item['buy_date'], item['strategy_type']
            )
            
            items.append(PortfolioItemResponse(
                id=item['id'],
                ticker=ticker,
                buy_date=item['buy_date'],
                buy_price=item['buy_price'],
                quantity=item['quantity'],
                strategy_type=item['strategy_type'],
                trend_signal=trend_signal,
                exit_reason=exit_reason,
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
            'strategy_type': item.strategy_type or 'triple_trend',
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
            strategy_type=item.strategy_type or 'triple_trend',
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
            'strategy_type': item.strategy_type or 'triple_trend',
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
            strategy_type=item.strategy_type or 'triple_trend',
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
