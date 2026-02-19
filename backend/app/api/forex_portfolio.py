"""
Forex Portfolio Routes
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from typing import List, Dict, Optional
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, date
import json
import pandas as pd
import logging

from ..firebase_setup import db
from ..models.forex_portfolio_schema import ForexPortfolioItemCreate, ForexPortfolioItemResponse, ForexPortfolioItemSell
from ..config import settings
from ..services.portfolio_monitor import PortfolioMonitor
from ..services.oanda_price import OandaPriceService

logger = logging.getLogger(__name__)
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
        # For other quote currencies (JPY, GBP, etc.), ideally need cross-rate pairs
        # JPY: Need AUD_JPY or JPY_AUD rate
        # GBP: Need AUD_GBP or GBP_AUD rate
        # For now, use AUD_USD as approximation (not accurate but prevents 0 values)
        # TODO: Add support for more cross-rate pairs in signals
        gain_loss_aud = native_gain_loss / aud_usd_rate if aud_usd_rate > 0 else 0

    cost_basis_native = (buy_price * quantity)
    gain_loss_percent = (native_gain_loss / cost_basis_native * 100) if cost_basis_native > 0 else 0
    
    return {
        "current_price": current_price,
        "gain_loss_aud": gain_loss_aud,
        "gain_loss_percent": gain_loss_percent
    }

@router.get("/history", response_model=List[ForexPortfolioItemResponse])
async def get_trade_history(
    email: str = Depends(get_current_user_email),
    start_date: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    status: Optional[str] = Query(None, description="Filter by status: OPEN, CLOSED, or None for all trades"),
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g., XAG_USD)"),
    strategy: Optional[str] = Query(None, description="Filter by strategy (e.g., DailyORB)"),
    sort_by: Optional[str] = Query("sell_date", description="Sort field")
):
    """
    Get trade history with filtering.
    Default: Returns ALL trades (both OPEN and CLOSED).

    Parameters:
    - status: Use 'OPEN' to show only open trades, 'CLOSED' for closed only, or leave blank for all
    - start_date, end_date: Filter by date range
    - symbol: Filter by specific symbol
    - strategy: Filter by specific strategy
    """
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')

        # Build query - only filter by status if explicitly specified (not None)
        query = portfolio_ref
        if status:
            query = query.where('status', '==', status)
        if symbol:
            query = query.where('symbol', '==', symbol)
        if strategy:
            query = query.where('strategy', '==', strategy)
            
        docs = query.stream()
        
        forex_data = get_forex_data()
        signals = forex_data.get('signals', [])
        
        items = []
        for doc in docs:
            data = doc.to_dict()
            
            # Apply date filters manually (Firestore doesn't support complex inequality on different fields easily with this structure)
            # sell_date is stored as ISO string in 'sell_date' field for CLOSED trades
            # buy_date is stored as ISO string in 'buy_date' field
            
            item_date_str = data.get('sell_date') if status == 'CLOSED' else data.get('buy_date')
            if not item_date_str:
                continue
                
            item_date = datetime.strptime(item_date_str, "%Y-%m-%d").date()
            
            if start_date and item_date < start_date:
                continue
            if end_date and item_date > end_date:
                continue
                
            metrics = calculate_forex_metrics(data, signals)
            
            # Date handling
            buy_date = datetime.strptime(data.get('buy_date'), "%Y-%m-%d").date()
            sell_date = None
            if data.get('sell_date'):
                sell_date = datetime.strptime(data.get('sell_date'), "%Y-%m-%d").date()

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
                realized_gain_aud=metrics['gain_loss_aud'] if data.get('status') == 'CLOSED' else None,
                actual_rr=data.get('actual_rr')
            ))
            
        # Sorting
        reverse = True
        if sort_by.startswith('-'):
            sort_by = sort_by[1:]
            reverse = False # Wait, usually '-' means descending. 
            # If default is descending, then '-' would be ascending? No.
        
        # Let's use standard convention: default ascending, but for trades we usually want newest first.
        # Plan says default sort_by="sell_date".
        
        def sort_key(x):
            val = getattr(x, sort_by, None)
            if val is None:
                return datetime.min.date() if 'date' in sort_by else 0
            return val

        items.sort(key=sort_key, reverse=reverse)
            
        return items
    except Exception as e:
        print(f"Forex Portfolio History Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch trade history")

@router.get("/analytics")
async def get_trade_analytics(
    email: str = Depends(get_current_user_email),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None)
):
    """
    Return comprehensive trade analytics.
    """
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
        
        # We only want CLOSED trades for analytics
        query = portfolio_ref.where('status', '==', 'CLOSED')
        docs = query.stream()
        
        forex_data = get_forex_data()
        signals = forex_data.get('signals', [])
        
        trades = []
        for doc in docs:
            data = doc.to_dict()
            
            # Date filter
            sell_date_str = data.get('sell_date')
            if not sell_date_str:
                continue
            
            sell_date = datetime.strptime(sell_date_str, "%Y-%m-%d").date()
            if start_date and sell_date < start_date:
                continue
            if end_date and sell_date > end_date:
                continue
                
            metrics = calculate_forex_metrics(data, signals)
            data['pnl_aud'] = metrics['gain_loss_aud']
            data['sell_date_dt'] = sell_date
            trades.append(data)
            
        if not trades:
            return {
                "summary": {
                    "total_trades": 0, "total_profit_aud": 0, "total_loss_aud": 0,
                    "net_pnl_aud": 0, "net_pnl_percent": 0, "win_rate": 0,
                    "loss_rate": 0, "avg_winning_trade": 0, "avg_losing_trade": 0,
                    "best_trade": 0, "worst_trade": 0, "profit_factor": 0
                },
                "by_strategy": {}, "by_month": {}, "daily_breakdown": {}, "equity_curve": []
            }
            
        # 1. Summary Metrics
        winning_trades = [t for t in trades if t['pnl_aud'] > 0]
        losing_trades = [t for t in trades if t['pnl_aud'] <= 0]
        
        total_profit = sum(t['pnl_aud'] for t in winning_trades)
        total_loss = abs(sum(t['pnl_aud'] for t in losing_trades))
        net_pnl = total_profit - total_loss
        
        total_trades_count = len(trades)
        win_rate = (len(winning_trades) / total_trades_count * 100) if total_trades_count > 0 else 0
        
        # Calculate net_pnl_percent (using sum of costs)
        total_cost = sum(t['buy_price'] * t['quantity'] for t in trades)
        net_pnl_percent = (net_pnl / total_cost * 100) if total_cost > 0 else 0
        
        summary = {
            "total_trades": total_trades_count,
            "total_profit_aud": total_profit,
            "total_loss_aud": -total_loss,
            "net_pnl_aud": net_pnl,
            "net_pnl_percent": net_pnl_percent,
            "win_rate": win_rate,
            "loss_rate": 100 - win_rate,
            "avg_winning_trade": total_profit / len(winning_trades) if winning_trades else 0,
            "avg_losing_trade": -total_loss / len(losing_trades) if losing_trades else 0,
            "best_trade": max(t['pnl_aud'] for t in trades),
            "worst_trade": min(t['pnl_aud'] for t in trades),
            "profit_factor": total_profit / total_loss if total_loss > 0 else (total_profit if total_profit > 0 else 1)
        }
        
        # 2. Group by Strategy
        by_strategy = {}
        strategies = set(t.get('strategy', 'Unknown') for t in trades)
        for strat in strategies:
            strat_trades = [t for t in trades if t.get('strategy', 'Unknown') == strat]
            strat_wins = [t for t in strat_trades if t['pnl_aud'] > 0]
            strat_pnl = sum(t['pnl_aud'] for t in strat_trades)
            
            by_strategy[strat] = {
                "trades": len(strat_trades),
                "win_rate": (len(strat_wins) / len(strat_trades) * 100) if strat_trades else 0,
                "pnl": strat_pnl,
                "avg_rr": sum(t.get('actual_rr', 0) for t in strat_trades) / len(strat_trades) if strat_trades else 0
            }
            
        # 3. Group by Month
        by_month = {}
        for t in trades:
            month = t['sell_date_dt'].strftime("%Y-%m")
            if month not in by_month:
                by_month[month] = {"trades": 0, "pnl": 0, "wins": 0}
            
            by_month[month]["trades"] += 1
            by_month[month]["pnl"] += t['pnl_aud']
            if t['pnl_aud'] > 0:
                by_month[month]["wins"] += 1
                
        for month in by_month:
            by_month[month]["win_rate"] = (by_month[month]["wins"] / by_month[month]["trades"] * 100)
            
        # 4. Daily Breakdown
        daily_breakdown = {}
        for t in trades:
            day = t['sell_date_dt'].isoformat()
            if day not in daily_breakdown:
                daily_breakdown[day] = {"trades": 0, "pnl": 0}
            daily_breakdown[day]["trades"] += 1
            daily_breakdown[day]["pnl"] += t['pnl_aud']
            
        # 5. Equity Curve
        sorted_trades = sorted(trades, key=lambda x: x['sell_date_dt'])
        equity_curve = []
        cumulative_pnl = 0
        
        # Initial point
        if sorted_trades:
            first_date = sorted_trades[0]['sell_date_dt']
            equity_curve.append({"date": first_date.isoformat(), "cumulative_pnl": 0})
            
        for t in sorted_trades:
            cumulative_pnl += t['pnl_aud']
            equity_curve.append({
                "date": t['sell_date_dt'].isoformat(),
                "cumulative_pnl": cumulative_pnl
            })
            
        return {
            "summary": summary,
            "by_strategy": by_strategy,
            "by_month": by_month,
            "daily_breakdown": daily_breakdown,
            "equity_curve": equity_curve
        }
    except Exception as e:
        print(f"Forex Portfolio Analytics Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate analytics")

@router.get("/oanda-accounts", description="List all available Oanda accounts")
async def list_oanda_accounts(
    email: str = Depends(get_current_user_email)
):
    """
    List all Oanda accounts available with this API token.
    Use this to find the account ID that has your trades.
    """
    try:
        accounts = OandaPriceService.list_all_accounts()
        return {
            "accounts": accounts,
            "count": len(accounts),
            "message": "Use one of these account IDs in OANDA_ACCOUNT_ID setting"
        }
    except Exception as e:
        logger.error(f"Error listing Oanda accounts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list accounts: {str(e)}")

@router.get("/oanda-trades", description="Fetch closed trades directly from Oanda (source of truth)")
async def get_oanda_closed_trades(
    email: str = Depends(get_current_user_email),
    start_date: Optional[date] = Query(None, description="Filter from date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter to date (YYYY-MM-DD)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g., XAG_USD)")
):
    """
    Fetch closed trades directly from Oanda transactions.

    This is the SOURCE OF TRUTH for trade data.
    Returns all closed positions with actual entry/exit prices and P&L.

    This endpoint requires:
    - OANDA_ACCESS_TOKEN to be configured
    - OANDA_ACCOUNT_ID to be configured
    """
    try:
        # Convert dates to ISO 8601 format for Oanda API
        from_time = None
        to_time = None

        if start_date:
            from_time = f"{start_date}T00:00:00Z"
        if end_date:
            to_time = f"{end_date}T23:59:59Z"

        # Fetch from Oanda (both OPEN and CLOSED trades)
        oanda_trades = OandaPriceService.get_all_trades_with_history(
            from_time=from_time,
            to_time=to_time,
            instrument=symbol
        )

        # Transform to response format
        result = []
        for trade in oanda_trades:
            # Calculate metrics
            units = trade.get('units', 0)
            entry = trade.get('entry_price', 0)
            exit_price = trade.get('exit_price')
            pnl_aud = trade.get('pnl', 0)
            status = trade.get('status', 'CLOSED')

            # Parse dates
            try:
                opened_at = datetime.fromisoformat(trade.get('opened_at', '').replace('Z', '+00:00')).date() if trade.get('opened_at') else None
            except:
                opened_at = None

            try:
                closed_at = datetime.fromisoformat(trade.get('closed_at', '').replace('Z', '+00:00')).date() if trade.get('closed_at') else None
            except:
                closed_at = None

            # R:R calculation requires stop loss price which Oanda sync doesn't provide
            # True R:R = abs(exit - entry) / abs(entry - stop_loss)
            # Without stop_loss, we cannot calculate accurate R:R, so we omit it
            actual_rr = None

            # Calculate percentage
            gain_loss_percent = 0
            if entry > 0 and units > 0:
                if status == 'CLOSED' and exit_price:
                    gain_loss_percent = round(((exit_price - entry) / entry * 100), 2)
                elif status == 'OPEN':
                    # For open trades, calculate from unrealized P&L
                    gain_loss_percent = round((pnl_aud / (entry * units) * 100), 2) if entry > 0 and units > 0 else 0

            result.append({
                "id": trade.get('trade_id'),
                "symbol": trade.get('symbol'),
                "direction": trade.get('direction'),
                "buy_price": entry,
                "sell_price": exit_price if exit_price else None,
                "quantity": units,
                "status": status,
                "buy_date": opened_at,
                "sell_date": closed_at if status == 'CLOSED' else None,
                "realized_gain_aud": round(pnl_aud, 2) if status == 'CLOSED' else None,  # Only for closed trades
                "current_price": exit_price if exit_price else None,  # For open trades, show last known price
                "gain_loss_aud": round(pnl_aud, 2),  # P&L (unrealized for OPEN, realized for CLOSED)
                "gain_loss_percent": gain_loss_percent,
                "actual_rr": actual_rr,
                "strategy": "OandaSync",  # Marked as synced from Oanda
                "notes": f"[{status}] Synced from Oanda | {trade.get('reason', 'Active')}"
            })

        return result

    except Exception as e:
        logger.error(f"Error fetching Oanda trades: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch trades from Oanda: {str(e)}")

@router.get("/strategy-comparison")
async def get_strategy_comparison(
    email: str = Depends(get_current_user_email)
):
    """
    Compare performance across all strategies.
    Returns ranking: ROI, win rate, total trades.
    """
    try:
        analytics = await get_trade_analytics(email)
        by_strategy = analytics.get("by_strategy", {})
        
        # Sort by PNL descending
        sorted_strategies = dict(sorted(
            by_strategy.items(), 
            key=lambda item: item[1]['pnl'], 
            reverse=True
        ))
        
        return sorted_strategies
    except Exception as e:
        print(f"Forex Strategy Comparison Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to compare strategies")

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
                realized_gain_aud=metrics['gain_loss_aud'] if data.get('status') == 'CLOSED' else None,
                actual_rr=data.get('actual_rr')  # R:R from Firestore if available
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

@router.post("/sync-oanda-closes", description="Sync closed trades from Oanda back to Firestore")
async def sync_oanda_closes(
    email: str = Depends(get_current_user_email)
):
    """
    Check for trades that were closed in Oanda (via SL/TP) and update Firestore.
    This syncs exit prices and P&L back to Firestore.
    """
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')

        # Get all OPEN trades from Firestore
        open_docs = list(portfolio_ref.where('status', '==', 'OPEN').stream())

        if not open_docs:
            return {"status": "success", "synced": 0, "message": "No open trades to sync"}

        synced_count = 0

        for doc in open_docs:
            data = doc.to_dict()
            trade_id = data.get('oanda_trade_id')

            if not trade_id:
                continue

            # Check if trade is closed in Oanda
            closed_trades = OandaPriceService.get_closed_trades_by_id([trade_id])

            if closed_trades:
                closed_trade = closed_trades[0]

                # Update Firestore with exit data
                doc.reference.update({
                    'status': 'CLOSED',
                    'sell_price': closed_trade.get('exit_price'),
                    'sell_date': closed_trade.get('closed_at'),
                    'pnl': closed_trade.get('pnl'),
                    'closed_by': 'OandaSync',
                    'updated_at': datetime.utcnow()
                })

                synced_count += 1
                logger.info(f"Synced trade {trade_id}: Exit={closed_trade.get('exit_price')}, P&L={closed_trade.get('pnl')}")

        return {
            "status": "success",
            "synced": synced_count,
            "message": f"Synced {synced_count} closed trades from Oanda"
        }

    except Exception as e:
        logger.error(f"Error syncing Oanda closes: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync: {str(e)}")

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
