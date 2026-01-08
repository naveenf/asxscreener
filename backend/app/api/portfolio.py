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
from ..models.portfolio_schema import PortfolioItemCreate, PortfolioItemResponse, PortfolioItemSell, TaxSummaryResponse, TaxSummaryItem
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

def get_australian_fy(date_obj: date) -> str:
    """
    Get Australian Financial Year for a given date.
    FY ends on June 30.
    e.g., 2023-06-30 -> FY2022-23
          2023-07-01 -> FY2023-24
    """
    year = date_obj.year
    if date_obj.month > 6:
        # After June, it's the start of next FY
        return f"FY{year}-{str(year+1)[2:]}"
    else:
        # Before or in June, it's end of current FY
        return f"FY{year-1}-{str(year)[2:]}"

def calculate_metrics(item_data, current_price):
    """
    Calculate gain/loss and annualized return.
    Handles both OPEN (unrealized) and CLOSED (realized) positions.
    Returns a dict with all metrics including tax info.
    """
    quantity = item_data.get('quantity', 0)
    buy_price = item_data.get('buy_price', 0)
    brokerage = item_data.get('brokerage', 0.0) or 0.0
    status = item_data.get('status', 'OPEN')
    
    # Cost Basis = (Buy Price * Quantity) + Buy Brokerage
    cost_basis = (buy_price * quantity) + brokerage

    current_value = 0.0
    gain_loss = 0.0
    financial_year = None
    is_long_term = False
    holding_period_days = 0
    taxable_gain = None
    
    if status == 'CLOSED':
        # For closed items, use sell data
        sell_price = item_data.get('sell_price', 0)
        sell_brokerage = item_data.get('sell_brokerage', 0.0) or 0.0
        
        # Net Proceeds = (Sell Price * Quantity) - Sell Brokerage
        net_proceeds = (sell_price * quantity) - sell_brokerage
        
        current_value = net_proceeds # "Value" is what we got back
        gain_loss = net_proceeds - cost_basis
        
        # Use sell_date for time calculation
        end_date = item_data.get('sell_date')
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        if end_date:
            financial_year = get_australian_fy(end_date)
            
    else:
        # For OPEN items, use current price
        if not current_price:
            return {
                "current_value": None, "gain_loss": None, "gain_loss_percent": None, 
                "annualized_gain": None, "holding_period_days": None, "is_long_term": None,
                "financial_year": None, "taxable_gain": None
            }
            
        # Current Market Value = (Current Price * Quantity)
        current_value = current_price * quantity
        gain_loss = current_value - cost_basis
        end_date = datetime.utcnow().date()

    # Gain Loss Percent
    gain_loss_percent = (gain_loss / cost_basis * 100) if cost_basis > 0 else 0
    
    # Annualized Gain Calculation and Holding Period
    buy_date = item_data.get('buy_date')
    if isinstance(buy_date, str):
        buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
        
    if buy_date and end_date:
        holding_period_days = (end_date - buy_date).days
        is_long_term = holding_period_days >= 365 # 12 months rule
    
    annualized_gain = 0.0
    
    if cost_basis > 0 and current_value > 0:
        total_return_ratio = current_value / cost_basis
        
        days_held_calc = holding_period_days if holding_period_days > 0 else 1
            
        # Only calculate Annualized Gain (CAGR) if held for more than 1 year (365 days)
        if days_held_calc > 365:
            try:
                annualized_gain = (pow(total_return_ratio, (365.0 / days_held_calc)) - 1) * 100
            except Exception:
                annualized_gain = None
        else:
            annualized_gain = None

    # Calculate Taxable Gain for Closed positions
    if status == 'CLOSED':
        # CGT Event: If gain > 0 and held > 12 months, 50% discount applies
        # Note: Capital losses are just losses, no discount logic applied to reduce them, 
        # but they offset other gains. Here we just show the "assessable" amount.
        if gain_loss > 0 and is_long_term:
            taxable_gain = gain_loss * 0.5
        else:
            taxable_gain = gain_loss

    return {
        "current_value": current_value,
        "gain_loss": gain_loss,
        "gain_loss_percent": gain_loss_percent,
        "annualized_gain": annualized_gain,
        "holding_period_days": holding_period_days,
        "is_long_term": is_long_term,
        "financial_year": financial_year,
        "taxable_gain": taxable_gain
    }

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
                
            sell_date = data.get('sell_date')
            if isinstance(sell_date, str):
                sell_date = datetime.strptime(sell_date, "%Y-%m-%d").date()
            
            item = {
                'id': doc.id,
                'ticker': data.get('ticker'),
                'buy_date': buy_date,
                'buy_price': data.get('buy_price'),
                'quantity': data.get('quantity'),
                'brokerage': data.get('brokerage', 0.0),
                'strategy_type': data.get('strategy_type', 'triple_trend'),
                'notes': data.get('notes'),
                'status': data.get('status', 'OPEN'),
                'sell_date': sell_date,
                'sell_price': data.get('sell_price'),
                'sell_brokerage': data.get('sell_brokerage'),
                'realized_gain': data.get('realized_gain')
            }
            raw_items.append(item)
            if item['ticker'] and item['status'] == 'OPEN':
                tickers_to_fetch.append(item['ticker'])
        
        # Batch fetch current prices (only for OPEN positions)
        current_prices = get_current_prices(list(set(tickers_to_fetch)))
        
        # Enrichment items
        for item in raw_items:
            ticker = item['ticker']
            # For CLOSED items, current_price isn't needed for metrics, but nice to show "last known" or "current market"
            # We'll use current market price if available, else 0 or sell_price
            current_price = current_prices.get(ticker)
            
            metrics = calculate_metrics(item, current_price)
            
            # Calculate Trend Signal (Only for OPEN positions)
            trend_signal = "CLOSED"
            exit_reason = None
            
            if item['status'] == 'OPEN':
                trend_signal, exit_reason = calculate_trend_signal(
                    ticker, item['buy_price'], item['buy_date'], item['strategy_type']
                )
            elif item['status'] == 'CLOSED':
                trend_signal = "SOLD"
                exit_reason = "Position Closed"
            
            items.append(PortfolioItemResponse(
                id=item['id'],
                ticker=ticker,
                buy_date=item['buy_date'],
                buy_price=item['buy_price'],
                quantity=item['quantity'],
                brokerage=item['brokerage'],
                status=item['status'],
                sell_date=item['sell_date'],
                sell_price=item['sell_price'],
                sell_brokerage=item['sell_brokerage'],
                realized_gain=metrics['gain_loss'] if item['status'] == 'CLOSED' else None,
                financial_year=metrics['financial_year'],
                holding_period_days=metrics['holding_period_days'],
                is_long_term=metrics['is_long_term'],
                taxable_gain=metrics['taxable_gain'],
                strategy_type=item['strategy_type'],
                trend_signal=trend_signal,
                exit_reason=exit_reason,
                notes=item['notes'],
                current_price=current_price,
                current_value=metrics['current_value'],
                gain_loss=metrics['gain_loss'],
                gain_loss_percent=metrics['gain_loss_percent'],
                annualized_gain=metrics['annualized_gain']
            ))
            
        return items
    except Exception as e:
        print(f"Portfolio List Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch portfolio")

@router.get("/tax-summary", response_model=TaxSummaryResponse)
async def get_tax_summary(email: str = Depends(get_current_user_email)):
    """Get portfolio tax summary grouped by Financial Year."""
    try:
        portfolio_ref = db.collection('users').document(email).collection('portfolio')
        docs = portfolio_ref.where('status', '==', 'CLOSED').stream()
        
        all_items = []
        
        for doc in docs:
            data = doc.to_dict()
            buy_date = data.get('buy_date')
            if isinstance(buy_date, str):
                buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()
                
            sell_date = data.get('sell_date')
            if isinstance(sell_date, str):
                sell_date = datetime.strptime(sell_date, "%Y-%m-%d").date()
            
            # Use calculate_metrics to get tax fields
            metrics = calculate_metrics(data, current_price=None)
            
            item_response = PortfolioItemResponse(
                id=doc.id,
                ticker=data.get('ticker'),
                buy_date=buy_date,
                buy_price=data.get('buy_price'),
                quantity=data.get('quantity'),
                brokerage=data.get('brokerage', 0.0),
                status='CLOSED',
                sell_date=sell_date,
                sell_price=data.get('sell_price'),
                sell_brokerage=data.get('sell_brokerage'),
                realized_gain=metrics['gain_loss'],
                financial_year=metrics['financial_year'],
                holding_period_days=metrics['holding_period_days'],
                is_long_term=metrics['is_long_term'],
                taxable_gain=metrics['taxable_gain'],
                strategy_type=data.get('strategy_type', 'triple_trend'),
                trend_signal="SOLD",
                exit_reason="Position Closed",
                notes=data.get('notes'),
                current_price=None,
                current_value=metrics['current_value'],
                gain_loss=metrics['gain_loss'],
                gain_loss_percent=metrics['gain_loss_percent'],
                annualized_gain=metrics['annualized_gain']
            )
            all_items.append(item_response)
            
        # Group by Financial Year
        groups = {}
        for item in all_items:
            fy = item.financial_year or "Unknown"
            if fy not in groups:
                groups[fy] = {
                    'financial_year': fy,
                    'items': [],
                    'total_profit': 0.0,
                    'total_brokerage': 0.0,
                    'total_taxable_gain': 0.0
                }
            groups[fy]['items'].append(item)
            groups[fy]['total_profit'] += (item.gain_loss or 0.0)
            groups[fy]['total_brokerage'] += ((item.brokerage or 0.0) + (item.sell_brokerage or 0.0))
            groups[fy]['total_taxable_gain'] += (item.taxable_gain or 0.0)
            
        # Convert groups to list and sort by FY descending
        summary_list = [TaxSummaryItem(**g) for g in groups.values()]
        summary_list.sort(key=lambda x: x.financial_year, reverse=True)
        
        # Calculate Lifetime totals
        lifetime_profit = sum(g.total_profit for g in summary_list)
        lifetime_brokerage = sum(g.total_brokerage for g in summary_list)
        
        return TaxSummaryResponse(
            summary=summary_list,
            lifetime_profit=lifetime_profit,
            lifetime_brokerage=lifetime_brokerage
        )

    except Exception as e:
        print(f"Tax Summary Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch tax summary")

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
            'brokerage': item.brokerage or 0.0,
            'strategy_type': item.strategy_type or 'triple_trend',
            'notes': item.notes,
            'status': 'OPEN',
            'created_at': datetime.utcnow()
        }
        
        update_time, doc_ref = portfolio_ref.add(doc_data)
        
        # Calculate initial metrics
        item_dict = item.model_dump()
        item_dict['status'] = 'OPEN'
        
        metrics = calculate_metrics(item_dict, current_price)
        
        return PortfolioItemResponse(
            id=doc_ref.id,
            ticker=item.ticker,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            brokerage=item.brokerage,
            status='OPEN',
            strategy_type=item.strategy_type or 'triple_trend',
            notes=item.notes,
            current_price=current_price,
            current_value=metrics['current_value'],
            gain_loss=metrics['gain_loss'],
            gain_loss_percent=metrics['gain_loss_percent'],
            annualized_gain=metrics['annualized_gain'],
            holding_period_days=metrics['holding_period_days'],
            is_long_term=metrics['is_long_term'],
            financial_year=metrics['financial_year'],
            taxable_gain=metrics['taxable_gain']
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Add Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to add item")

@router.post("/{item_id}/sell", response_model=PortfolioItemResponse)
async def sell_portfolio_item(
    item_id: str,
    sell_data: PortfolioItemSell,
    email: str = Depends(get_current_user_email)
):
    """
    Sell a portfolio item (partial or full).
    If partial, creates a new CLOSED document for the sold portion and updates the original.
    If full, marks the original document as CLOSED.
    """
    try:
        portfolio_ref = db.collection('users').document(email).collection('portfolio')
        doc_ref = portfolio_ref.document(item_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Item not found")
            
        data = doc.to_dict()
        
        if data.get('status') == 'CLOSED':
            raise HTTPException(status_code=400, detail="Item is already closed")
            
        current_qty = data.get('quantity', 0)
        original_brokerage = data.get('brokerage', 0.0) or 0.0
        
        if sell_data.quantity > current_qty:
            raise HTTPException(status_code=400, detail="Sell quantity exceeds current holding")
            
        # Determine if Full or Partial Sell
        is_full_sell = (sell_data.quantity == current_qty)
        
        if is_full_sell:
            # Update existing doc to CLOSED
            update_data = {
                'status': 'CLOSED',
                'sell_date': sell_data.sell_date.isoformat(),
                'sell_price': sell_data.sell_price,
                'sell_brokerage': sell_data.brokerage,
                'updated_at': datetime.utcnow()
            }
            doc_ref.update(update_data)
            
            # Return updated object
            data.update(update_data)
            # Add implicit fields for response
            data['id'] = item_id
            
        else:
            # Partial Sell
            # 1. Calculate proportional buy brokerage for the sold portion
            # If we sell 30%, we attribute 30% of the original brokerage to this sale
            sell_ratio = sell_data.quantity / current_qty
            proportional_buy_brokerage = original_brokerage * sell_ratio
            remaining_buy_brokerage = original_brokerage - proportional_buy_brokerage
            
            # 2. Create NEW document for the Sold portion
            sold_doc_data = data.copy()
            sold_doc_data.update({
                'quantity': sell_data.quantity,
                'brokerage': proportional_buy_brokerage, # Adjusted buy cost
                'status': 'CLOSED',
                'sell_date': sell_data.sell_date.isoformat(),
                'sell_price': sell_data.sell_price,
                'sell_brokerage': sell_data.brokerage, # Fee for selling
                'created_at': datetime.utcnow(),
                'original_ref_id': item_id, # Optional: track origin
                'notes': f"Sold from original position. {data.get('notes', '')}"
            })
            # Remove updated_at if it exists from copy
            if 'updated_at' in sold_doc_data:
                del sold_doc_data['updated_at']
                
            portfolio_ref.add(sold_doc_data)
            
            # 3. Update ORIGINAL document (Remaining portion)
            remaining_qty = current_qty - sell_data.quantity
            update_data = {
                'quantity': remaining_qty,
                'brokerage': remaining_buy_brokerage,
                'updated_at': datetime.utcnow()
            }
            doc_ref.update(update_data)
            
            # Return updated original object
            data.update(update_data)
            data['id'] = item_id

        # Calculate metrics for response
        # Note: current_price isn't strictly needed for the response of a sell action, 
        # but we can fetch it if we want the 'current_value' to reflect the remaining part correctly.
        current_price = validate_and_get_price(data['ticker'])
        
        # fix dates
        if isinstance(data['buy_date'], str):
             data['buy_date'] = datetime.strptime(data['buy_date'], "%Y-%m-%d").date()
        if 'sell_date' in data and isinstance(data['sell_date'], str):
             data['sell_date'] = datetime.strptime(data['sell_date'], "%Y-%m-%d").date()

        metrics = calculate_metrics(data, current_price)
        
        return PortfolioItemResponse(
            id=data['id'],
            ticker=data['ticker'],
            buy_date=data['buy_date'],
            buy_price=data['buy_price'],
            quantity=data['quantity'],
            brokerage=data.get('brokerage'),
            status=data.get('status', 'OPEN'),
            sell_date=data.get('sell_date'),
            sell_price=data.get('sell_price'),
            sell_brokerage=data.get('sell_brokerage'),
            strategy_type=data.get('strategy_type'),
            trend_signal="HOLD", # simplified
            notes=data.get('notes'),
            current_price=current_price,
            current_value=metrics['current_value'],
            gain_loss=metrics['gain_loss'],
            gain_loss_percent=metrics['gain_loss_percent'],
            annualized_gain=metrics['annualized_gain'],
            holding_period_days=metrics['holding_period_days'],
            is_long_term=metrics['is_long_term'],
            financial_year=metrics['financial_year'],
            taxable_gain=metrics['taxable_gain']
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Sell Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to process sale")

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
            'brokerage': item.brokerage or 0.0,
            'strategy_type': item.strategy_type or 'triple_trend',
            'notes': item.notes,
            'updated_at': datetime.utcnow()
        }
        
        doc_ref.update(doc_data)
        
        item_dict = item.model_dump()
        metrics = calculate_metrics(item_dict, current_price)
        
        return PortfolioItemResponse(
            id=item_id,
            ticker=item.ticker,
            buy_date=item.buy_date,
            buy_price=item.buy_price,
            quantity=item.quantity,
            brokerage=item.brokerage,
            strategy_type=item.strategy_type or 'triple_trend',
            notes=item.notes,
            current_price=current_price,
            current_value=metrics['current_value'],
            gain_loss=metrics['gain_loss'],
            gain_loss_percent=metrics['gain_loss_percent'],
            annualized_gain=metrics['annualized_gain'],
            holding_period_days=metrics['holding_period_days'],
            is_long_term=metrics['is_long_term'],
            financial_year=metrics['financial_year'],
            taxable_gain=metrics['taxable_gain']
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Portfolio Update Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update item")
