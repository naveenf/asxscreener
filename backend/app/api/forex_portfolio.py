"""
Forex Portfolio Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from typing import List, Dict, Optional
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, date
import json
import pandas as pd

from ..firebase_setup import db
from ..models.forex_portfolio_schema import ForexPortfolioItemCreate, ForexPortfolioItemResponse, ForexPortfolioItemSell
from ..config import settings
from ..services.portfolio_monitor import PortfolioMonitor

router = APIRouter(prefix="/api/forex-portfolio")

async def get_current_user_email(authorization: str = Header(...)) -> str:
    """Dependency to get user email from Google ID token."""
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

def get_forex_data() -> dict:
    """Load latest forex signals and rates."""
    path = settings.PROCESSED_DATA_DIR / 'forex_signals.json'
    if not path.exists():
        return {"signals": []}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {"signals": []}

def get_latest_price_from_csv(symbol: str) -> Optional[float]:
    """Fallback to get latest price from raw CSV data."""
    try:
        # Check for 15m file first
        path = settings.DATA_DIR / "forex_raw" / f"{symbol}_15_Min.csv"
        if not path.exists():
            return None
        
        # Read last line
        df = pd.read_csv(path)
        if not df.empty:
            # Use 'Close' price
            return float(df['Close'].iloc[-1])
    except Exception as e:
        print(f"Error reading CSV price for {symbol}: {e}")
    return None

def calculate_forex_metrics(item_data: dict, signals: List[dict]) -> dict:
    """Calculate AUD metrics for a forex item."""
    symbol = item_data.get('symbol')
    direction = item_data.get('direction', 'BUY')
    buy_price = item_data.get('buy_price', 0)
    quantity = item_data.get('quantity', 0)
    status = item_data.get('status', 'OPEN')
    
    # Find current price
    current_price = None
    for s in signals:
        if s['symbol'] == symbol:
            current_price = s['price']
            break
            
    if current_price is None and status == 'OPEN':
        current_price = get_latest_price_from_csv(symbol)

    # Find conversion rate to AUD
    # Most pairs are XXX_USD. So we need AUD_USD to convert USD profit to AUD.
    aud_usd_rate = 1.0
    for s in signals:
        if s['symbol'] == 'AUD_USD':
            aud_usd_rate = s['price']
            break
    
    if aud_usd_rate == 1.0:
        csv_rate = get_latest_price_from_csv('AUD_USD')
        if csv_rate:
            aud_usd_rate = csv_rate

    # Gain/Loss in native currency
    native_gain_loss = 0.0
    price_to_use = 0.0
    
    if status == 'CLOSED':
        price_to_use = item_data.get('sell_price', 0)
    elif current_price is not None:
        price_to_use = current_price
    
    if price_to_use > 0:
        if direction == 'BUY':
            native_gain_loss = (price_to_use - buy_price) * quantity
        else: # SELL (Short)
            native_gain_loss = (buy_price - price_to_use) * quantity

    # Conversion to AUD
    quote_currency = symbol.split('_')[-1] if '_' in symbol else 'USD'
    
    gain_loss_aud = 0.0
    if quote_currency == 'AUD':
        gain_loss_aud = native_gain_loss
    elif quote_currency == 'USD':
        gain_loss_aud = native_gain_loss / aud_usd_rate if aud_usd_rate > 0 else 0
    else:
        # Fallback for other quote currencies like JPY, GBP etc.
        # For simplicity, treat as USD if not AUD, or add more cross rates later
        gain_loss_aud = native_gain_loss / aud_usd_rate if aud_usd_rate > 0 else 0

    cost_basis_native = (buy_price * quantity)
    gain_loss_percent = (native_gain_loss / cost_basis_native * 100) if cost_basis_native > 0 else 0
    
    return {
        "current_price": current_price,
        "gain_loss_aud": gain_loss_aud,
        "gain_loss_percent": gain_loss_percent
    }

@router.get("", response_model=List[ForexPortfolioItemResponse])
async def list_forex_portfolio(email: str = Depends(get_current_user_email)):
    """Get all items in user's forex portfolio."""
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
        docs = portfolio_ref.stream()
        
        forex_data = get_forex_data()
        signals = forex_data.get('signals', [])
        
        items = []
        for doc in docs:
            data = doc.to_dict()
            metrics = calculate_forex_metrics(data, signals)
            
            # Date handling
            buy_date = data.get('buy_date')
            if isinstance(buy_date, str):
                buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
            
            sell_date = data.get('sell_date')
            if isinstance(sell_date, str):
                sell_date = datetime.strptime(sell_date, "%Y-%m-%d").date()

            items.append(ForexPortfolioItemResponse(
                id=doc.id,
                symbol=data.get('symbol'),
                direction=data.get('direction', 'BUY'),
                buy_date=buy_date,
                buy_price=data.get('buy_price'),
                quantity=data.get('quantity'),
                status=data.get('status', 'OPEN'),
                sell_date=sell_date,
                sell_price=data.get('sell_price'),
                notes=data.get('notes'),
                strategy=data.get('strategy'),
                timeframe=data.get('timeframe'),
                exit_signal=data.get('exit_signal', False),
                exit_reason=data.get('exit_reason'),
                current_price=metrics['current_price'],
                gain_loss_aud=metrics['gain_loss_aud'] if data.get('status') == 'OPEN' else None,
                gain_loss_percent=metrics['gain_loss_percent'],
                realized_gain_aud=metrics['gain_loss_aud'] if data.get('status') == 'CLOSED' else None
            ))
            
        return items
    except Exception as e:
        print(f"Forex Portfolio List Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch forex portfolio")

@router.post("", response_model=ForexPortfolioItemResponse)
async def add_forex_item(
    item: ForexPortfolioItemCreate,
    email: str = Depends(get_current_user_email)
):
    """Add a new forex trade to portfolio."""
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
        
        doc_data = {
            'symbol': item.symbol,
            'direction': item.direction,
            'buy_date': item.buy_date.isoformat(),
            'buy_price': item.buy_price,
            'quantity': item.quantity,
            'notes': item.notes,
            'strategy': item.strategy,
            'timeframe': item.timeframe,
            'status': 'OPEN',
            'created_at': datetime.utcnow()
        }
        
        _, doc_ref = portfolio_ref.add(doc_data)
        
        return ForexPortfolioItemResponse(
            id=doc_ref.id,
            symbol=item.symbol,
            direction=item.direction,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            status='OPEN',
            notes=item.notes,
            strategy=item.strategy,
            timeframe=item.timeframe
        )
    except Exception as e:
        print(f"Forex Portfolio Add Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add item")

@router.post("/{item_id}/sell", response_model=ForexPortfolioItemResponse)
async def sell_forex_item(
    item_id: str,
    sell_data: ForexPortfolioItemSell,
    email: str = Depends(get_current_user_email)
):
    """Close a forex position."""
    try:
        doc_ref = db.collection('users').document(email).collection('forex_portfolio').document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        data = doc.to_dict()
        if data.get('status') == 'CLOSED':
            raise HTTPException(status_code=400, detail="Position already closed")
            
        update_data = {
            'status': 'CLOSED',
            'sell_date': sell_data.sell_date.isoformat(),
            'sell_price': sell_data.sell_price,
            'updated_at': datetime.utcnow()
        }
        doc_ref.update(update_data)
        
        # Merge for response
        data.update(update_data)
        data['id'] = item_id
        
        # Calculate final metrics
        forex_data = get_forex_data()
        metrics = calculate_forex_metrics(data, forex_data.get('signals', []))
        
        return ForexPortfolioItemResponse(
            id=item_id,
            symbol=data['symbol'],
            buy_date=datetime.strptime(data['buy_date'], "%Y-%m-%d").date(),
            buy_price=data['buy_price'],
            quantity=data['quantity'],
            status='CLOSED',
            sell_date=sell_data.sell_date,
            sell_price=sell_data.sell_price,
            realized_gain_aud=metrics['gain_loss_aud'],
            gain_loss_percent=metrics['gain_loss_percent']
        )
    except Exception as e:
        print(f"Forex Portfolio Sell Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to close position")

@router.delete("/{item_id}")
async def delete_forex_item(
    item_id: str,
    email: str = Depends(get_current_user_email)
):
    """Delete a forex portfolio item."""
    try:
        doc_ref = db.collection('users').document(email).collection('forex_portfolio').document(item_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail="Item not found")
        doc_ref.delete()
        return {"message": "Item deleted"}
    except Exception as e:
        print(f"Forex Portfolio Delete Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete item")

@router.put("/{item_id}", response_model=ForexPortfolioItemResponse)
async def update_forex_item(
    item_id: str,
    item: ForexPortfolioItemCreate,
    email: str = Depends(get_current_user_email)
):
    """Update an existing forex portfolio item."""
    try:
        doc_ref = db.collection('users').document(email).collection('forex_portfolio').document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        doc_data = {
            'symbol': item.symbol,
            'direction': item.direction,
            'buy_date': item.buy_date.isoformat(),
            'buy_price': item.buy_price,
            'quantity': item.quantity,
            'notes': item.notes,
            'strategy': item.strategy,
            'timeframe': item.timeframe,
            'updated_at': datetime.utcnow()
        }
        
        doc_ref.update(doc_data)
        
        # Calculate metrics for response
        forex_data = get_forex_data()
        metrics = calculate_forex_metrics(doc_data, forex_data.get('signals', []))
        
        return ForexPortfolioItemResponse(
            id=item_id,
            symbol=item.symbol,
            direction=item.direction,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            status=doc.to_dict().get('status', 'OPEN'),
            notes=item.notes,
            strategy=item.strategy,
            timeframe=item.timeframe,
            current_price=metrics['current_price'],
            gain_loss_aud=metrics['gain_loss_aud'],
            gain_loss_percent=metrics['gain_loss_percent']
        )
    except Exception as e:
        print(f"Forex Portfolio Update Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update item")

@router.post("/check-exits")
async def check_portfolio_exits(email: str = Depends(get_current_user_email)):
    """
    Trigger an exit check for all open positions in the user's portfolio.
    Returns list of detected exit signals.
    """
    try:
        monitor = PortfolioMonitor()
        exits = monitor.check_portfolio_exits(email)
        return {"status": "success", "exits_found": len(exits), "details": exits}
    except Exception as e:
        print(f"Portfolio Exit Check Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to check exits")
