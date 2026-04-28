"""
Forex Portfolio Routes
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Header, Query
from typing import List, Dict, Optional
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from datetime import datetime, date, timedelta, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 without tzdata installed
    from backports.zoneinfo import ZoneInfo
from pathlib import Path
import json
import pandas as pd
import logging

MELBOURNE_TZ = ZoneInfo('Australia/Melbourne')


def _utc_date_to_melbourne(sell_date_str: Optional[str], updated_at=None) -> Optional[datetime]:
    """Convert sell_date string (or updated_at timestamp) to Melbourne datetime."""
    mel_dt = None
    if updated_at:
        try:
            if hasattr(updated_at, 'tzinfo') and updated_at.tzinfo:
                mel_dt = updated_at.astimezone(MELBOURNE_TZ)
            else:
                utc_dt = updated_at.replace(tzinfo=timezone.utc)
                mel_dt = utc_dt.astimezone(MELBOURNE_TZ)
        except Exception:
            pass
    if mel_dt is None and sell_date_str:
        try:
            utc_dt = datetime.strptime(sell_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            mel_dt = utc_dt.astimezone(MELBOURNE_TZ)
        except Exception:
            pass
    return mel_dt


def _bucket_trade(mel_dt: Optional[datetime], period: str) -> Optional[str]:
    """Bucket a Melbourne datetime using 9am as trading day boundary."""
    if mel_dt is None:
        return None
    shifted = mel_dt - timedelta(hours=9)
    if period == 'daily':
        return shifted.strftime('%Y-%m-%d')
    elif period == 'weekly':
        return shifted.strftime('%G-W%V')
    elif period == 'monthly':
        return shifted.strftime('%Y-%m')
    elif period == 'yearly':
        return shifted.strftime('%Y')
    return shifted.strftime('%Y-%m')


def _compute_period_breakdown(trades: list, period: str) -> dict:
    """Return trades bucketed by period with per-pair sub-breakdown."""
    breakdown: dict = {}
    for t in trades:
        bucket = _bucket_trade(t.get('mel_dt'), period)
        if not bucket:
            continue
        if bucket not in breakdown:
            breakdown[bucket] = {'trades': 0, 'pnl': 0, 'wins': 0, 'by_pair': {}}
        breakdown[bucket]['trades'] += 1
        breakdown[bucket]['pnl'] += t['pnl_aud']
        if t['pnl_aud'] > 0:
            breakdown[bucket]['wins'] += 1
        pair_key = f"{t.get('symbol', 'Unknown')}::{t.get('strategy', 'Unknown')}"
        bp = breakdown[bucket]['by_pair']
        if pair_key not in bp:
            bp[pair_key] = {'trades': 0, 'pnl': 0, 'wins': 0}
        bp[pair_key]['trades'] += 1
        bp[pair_key]['pnl'] += t['pnl_aud']
        if t['pnl_aud'] > 0:
            bp[pair_key]['wins'] += 1
    for bucket in breakdown:
        n = breakdown[bucket]['trades']
        breakdown[bucket]['win_rate'] = (breakdown[bucket]['wins'] / n * 100) if n > 0 else 0
        for pk in breakdown[bucket]['by_pair']:
            pn = breakdown[bucket]['by_pair'][pk]['trades']
            breakdown[bucket]['by_pair'][pk]['win_rate'] = (
                breakdown[bucket]['by_pair'][pk]['wins'] / pn * 100
            ) if pn > 0 else 0
    return breakdown


def _load_backtest_reference() -> dict:
    """Load backtest benchmark data from JSON file."""
    try:
        from ..config import settings as _s
        path = Path(_s.DATA_DIR) / 'metadata' / 'backtest_reference.json'
        with open(path, 'r') as f:
            return json.load(f).get('pairs', {})
    except Exception:
        return {}


def _build_backtest_comparison(trades: list, backtest_ref: dict) -> dict:
    """Compare live trade stats vs backtest benchmarks per PAIR::Strategy."""
    live_stats: dict = {}
    for t in trades:
        pair_key = f"{t.get('symbol', 'Unknown')}::{t.get('strategy', 'Unknown')}"
        if pair_key not in live_stats:
            live_stats[pair_key] = {'trades': 0, 'wins': 0, 'pnl': 0, 'rr_sum': 0}
        live_stats[pair_key]['trades'] += 1
        live_stats[pair_key]['pnl'] += t['pnl_aud']
        live_stats[pair_key]['rr_sum'] += t.get('actual_rr') or 0
        if t['pnl_aud'] > 0:
            live_stats[pair_key]['wins'] += 1

    comparison: dict = {}
    for pair_key, bt in backtest_ref.items():
        live = live_stats.get(pair_key, {'trades': 0, 'wins': 0, 'pnl': 0, 'rr_sum': 0})
        n = live['trades']
        live_wr = (live['wins'] / n * 100) if n > 0 else 0
        comparison[pair_key] = {
            'live': {
                'trades': n,
                'win_rate_pct': round(live_wr, 1),
                'pnl': round(live['pnl'], 2),
                'avg_rr': round(live['rr_sum'] / n, 2) if n > 0 else 0,
            },
            'backtest': bt,
            'delta_win_rate': round(live_wr - bt['win_rate_pct'], 1) if n > 0 else None,
        }
    return comparison

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

def fetch_live_prices_for_open_trades(docs_data: List[dict]) -> dict:
    """Batch-fetch live Oanda prices for all unique OPEN trade symbols plus AUD_USD for conversion."""
    open_symbols = {d.get('symbol') for d in docs_data if d.get('status', 'OPEN') == 'OPEN' and d.get('symbol')}
    if not open_symbols:
        return {}
    # Always include AUD_USD and USD_JPY for P&L conversion (USD_JPY needed for JPY-quoted pairs)
    symbols_to_fetch = list(open_symbols | {'AUD_USD', 'USD_JPY'})
    try:
        prices = OandaPriceService.get_multiple_prices(symbols_to_fetch)
        return prices or {}
    except Exception as e:
        logger.warning(f"Could not fetch live Oanda prices: {e}")
        return {}


def calculate_forex_metrics(item_data: dict, signals: List[dict], live_prices: Optional[dict] = None) -> dict:
    """Calculate AUD metrics for a forex item."""
    symbol = item_data.get('symbol')
    direction = item_data.get('direction', 'BUY')
    buy_price = item_data.get('buy_price', 0)
    quantity = item_data.get('quantity', 0)
    status = item_data.get('status', 'OPEN')

    # Find current price: 1) screener signals cache, 2) CSV, 3) live Oanda prices
    current_price = None
    for s in signals:
        if s['symbol'] == symbol:
            current_price = s['price']
            break

    if current_price is None and status == 'OPEN':
        current_price = get_latest_price_from_csv(symbol)

    if current_price is None and status == 'OPEN' and live_prices:
        current_price = live_prices.get(symbol)

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
        elif live_prices and 'AUD_USD' in live_prices:
            aud_usd_rate = live_prices['AUD_USD']

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

    # For closed trades, use Oanda's authoritative AUD P&L (synced via realizedPL).
    # Recalculating from price × units introduces currency conversion errors for
    # non-USD quote pairs (e.g. GBP/JPY: JPY ÷ AUD/USD ≈ 150× inflation).
    if status == 'CLOSED' and item_data.get('pnl') is not None:
        gain_loss_aud = float(item_data['pnl'])
    else:
        # Conversion to AUD (open trades — live recalculation)
        quote_currency = symbol.split('_')[-1] if '_' in symbol else 'USD'
        gain_loss_aud = 0.0
        if quote_currency == 'AUD':
            gain_loss_aud = native_gain_loss
        elif quote_currency == 'USD':
            gain_loss_aud = native_gain_loss / aud_usd_rate if aud_usd_rate > 0 else 0
        elif quote_currency == 'JPY':
            # Convert JPY → AUD: native_gain_loss (JPY) * AUD_USD / USD_JPY
            usd_jpy = live_prices.get('USD_JPY') if live_prices else None
            if usd_jpy is None:
                usd_jpy = get_latest_price_from_csv('USD_JPY')
            if usd_jpy and usd_jpy > 0 and aud_usd_rate > 0:
                gain_loss_aud = native_gain_loss * aud_usd_rate / usd_jpy
            else:
                gain_loss_aud = native_gain_loss / aud_usd_rate  # fallback
        else:
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

        # Materialise docs so we can pre-fetch live prices in one batch call
        all_docs = [(doc.id, doc.to_dict()) for doc in docs]

        forex_data = get_forex_data()
        signals = forex_data.get('signals', [])

        # Batch-fetch live Oanda prices for all OPEN trade symbols
        live_prices = fetch_live_prices_for_open_trades([d for _, d in all_docs])

        items = []
        for doc_id, data in all_docs:
            # Apply date filters manually
            item_date_str = data.get('sell_date') if status == 'CLOSED' else data.get('buy_date')
            if not item_date_str:
                continue

            item_date = datetime.strptime(item_date_str, "%Y-%m-%d").date()

            if start_date and item_date < start_date:
                continue
            if end_date and item_date > end_date:
                continue

            metrics = calculate_forex_metrics(data, signals, live_prices)

            # Date handling
            buy_date = datetime.strptime(data.get('buy_date'), "%Y-%m-%d").date()
            sell_date = None
            if data.get('sell_date'):
                sell_date = datetime.strptime(data.get('sell_date'), "%Y-%m-%d").date()

            items.append(ForexPortfolioItemResponse(
                id=doc_id,
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
                realized_gain_aud=(data.get('pnl') if data.get('pnl') is not None else metrics['gain_loss_aud']) if data.get('status') == 'CLOSED' else None,
                actual_rr=data.get('actual_rr'),
                keep_through_close=data.get('keep_through_close'),
            ))

        # Sorting: default is newest-first (descending). Prefix '-' flips to ascending.
        reverse = True
        if sort_by.startswith('-'):
            sort_by = sort_by[1:]
            reverse = False
        
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
    end_date: Optional[date] = Query(None),
    period: Optional[str] = Query('monthly', description="Grouping period: daily | weekly | monthly | yearly")
):
    """
    Return comprehensive trade analytics with period breakdown and backtest comparison.
    """
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')

        # We only want CLOSED trades for analytics
        query = portfolio_ref.where('status', '==', 'CLOSED')
        docs = query.stream()

        forex_data = get_forex_data()
        signals = forex_data.get('signals', [])

        trades_list = []
        for doc in docs:
            data = doc.to_dict()

            sell_date_str = data.get('sell_date')
            if not sell_date_str:
                continue

            sell_date_obj = datetime.strptime(sell_date_str, "%Y-%m-%d").date()
            if start_date and sell_date_obj < start_date:
                continue
            if end_date and sell_date_obj > end_date:
                continue

            metrics = calculate_forex_metrics(data, signals)
            data['pnl_aud'] = metrics['gain_loss_aud']
            data['sell_date_dt'] = sell_date_obj
            # Enrich with Melbourne datetime for period bucketing
            data['mel_dt'] = _utc_date_to_melbourne(sell_date_str, data.get('updated_at'))
            trades_list.append(data)

        if not trades_list:
            return {
                "summary": {
                    "total_trades": 0, "total_profit_aud": 0, "total_loss_aud": 0,
                    "net_pnl_aud": 0, "net_pnl_percent": 0, "win_rate": 0,
                    "loss_rate": 0, "avg_winning_trade": 0, "avg_losing_trade": 0,
                    "best_trade": 0, "worst_trade": 0, "profit_factor": 0,
                    "current_balance_aud": 0, "starting_balance_aud": 0,
                    "deposits_in_period": [], "modified_dietz_denominator": 0,
                    "avg_rr": 0, "close_types": {}, "max_drawdown_pct": 0,
                    "win_days": 0, "loss_days": 0, "max_win_streak": 0, "max_loss_streak": 0
                },
                "by_strategy": {}, "by_month": {}, "daily_breakdown": {}, "equity_curve": [],
                "by_pair": {}, "period_breakdown": {}, "period_breakdowns": {}, "backtest_comparison": {}, "period": period
            }

        # 1. Summary Metrics
        winning_trades = [t for t in trades_list if t['pnl_aud'] > 0]
        losing_trades = [t for t in trades_list if t['pnl_aud'] <= 0]

        total_profit = sum(t['pnl_aud'] for t in winning_trades)
        total_loss = abs(sum(t['pnl_aud'] for t in losing_trades))
        net_pnl = total_profit - total_loss

        total_trades_count = len(trades_list)
        win_rate = (len(winning_trades) / total_trades_count * 100) if total_trades_count > 0 else 0

        roi_start = start_date.isoformat() if start_date else '2026-02-19'
        roi_end = end_date.isoformat() if end_date else date.today().isoformat()
        starting_balance_aud = 0
        try:
            snap = (
                db.collection('account_balance_history')
                .where('__name__', '<=', db.collection('account_balance_history').document(roi_start))
                .order_by('__name__', direction='DESCENDING')
                .limit(1)
                .get()
            )
            if snap:
                starting_balance_aud = float(snap[0].to_dict().get('balance_aud', 0))
        except Exception as e:
            logger.warning(f"Could not fetch balance snapshot for {roi_start}: {e}")

        oanda_summary = OandaPriceService.get_account_summary()
        current_balance_aud = float(oanda_summary.get('balance', 0)) if oanda_summary else 0

        if starting_balance_aud == 0 and current_balance_aud > 0:
            estimated = current_balance_aud - net_pnl
            if estimated > 0:
                starting_balance_aud = estimated
                logger.info(f"No balance snapshot for {roi_start}; using estimated starting balance ${estimated:.2f}")

        # Modified Dietz: weight each deposit by fraction of period remaining after it
        # denominator = starting_balance + Σ(deposit_i × (D - d_i) / D)
        # Fetch from roi_start+1 so deposits on the start date itself are excluded —
        # the daily balance snapshot already captures the post-deposit balance, so
        # including start-date transfers would double-count them in the denominator.
        period_start_dt = date.fromisoformat(roi_start)
        period_end_dt = date.fromisoformat(roi_end)
        transfers_from = (period_start_dt + timedelta(days=1)).isoformat()
        fund_transfers = OandaPriceService.get_fund_transfers(transfers_from, roi_end)
        total_days = max((period_end_dt - period_start_dt).days, 1)
        weighted_deposits = 0.0
        for tf in fund_transfers:
            days_elapsed = (tf["date"] - period_start_dt).days
            weight = (total_days - days_elapsed) / total_days
            weighted_deposits += tf["amount"] * weight
        modified_dietz_denominator = starting_balance_aud + weighted_deposits
        net_pnl_percent = (net_pnl / modified_dietz_denominator * 100) if modified_dietz_denominator > 0 else 0

        # Close type summary
        close_types: dict = {}
        for t in trades_list:
            ct = t.get('close_type') or 'UNKNOWN'
            close_types[ct] = close_types.get(ct, 0) + 1

        def _resolve_rr(t: dict):
            rr = t.get('actual_rr')
            if rr is not None:
                return rr
            entry = t.get('buy_price')
            sl = t.get('stop_loss')
            exit_price = t.get('sell_price')
            direction = t.get('direction', 'BUY')
            if entry and sl and exit_price:
                risk = abs(entry - sl)
                if risk > 0:
                    gain = exit_price - entry if direction.upper() == 'BUY' else entry - exit_price
                    return gain / risk
            return None  # exclude trades with incomplete data

        rr_values = [v for v in (_resolve_rr(t) for t in trades_list) if v is not None]
        avg_rr = sum(rr_values) / len(rr_values) if rr_values else 0

        summary = {
            "total_trades": total_trades_count,
            "total_profit_aud": total_profit,
            "total_loss_aud": -total_loss,
            "net_pnl_aud": net_pnl,
            "net_pnl_percent": net_pnl_percent,
            "current_balance_aud": current_balance_aud,
            "starting_balance_aud": starting_balance_aud,
            "deposits_in_period": [{"date": str(tf["date"]), "amount": tf["amount"]} for tf in fund_transfers],
            "modified_dietz_denominator": modified_dietz_denominator,
            "win_rate": win_rate,
            "loss_rate": 100 - win_rate,
            "avg_winning_trade": total_profit / len(winning_trades) if winning_trades else 0,
            "avg_losing_trade": -total_loss / len(losing_trades) if losing_trades else 0,
            "best_trade": max(t['pnl_aud'] for t in trades_list),
            "worst_trade": min(t['pnl_aud'] for t in trades_list),
            "profit_factor": total_profit / total_loss if total_loss > 0 else (total_profit if total_profit > 0 else 1),
            "avg_rr": round(avg_rr, 2),
            "close_types": close_types,
        }

        # 2. Group by Strategy
        by_strategy = {}
        strategies = set(t.get('strategy', 'Unknown') for t in trades_list)
        for strat in strategies:
            strat_trades = [t for t in trades_list if t.get('strategy', 'Unknown') == strat]
            strat_wins = [t for t in strat_trades if t['pnl_aud'] > 0]
            strat_pnl = sum(t['pnl_aud'] for t in strat_trades)
            by_strategy[strat] = {
                "trades": len(strat_trades),
                "win_rate": (len(strat_wins) / len(strat_trades) * 100) if strat_trades else 0,
                "pnl": strat_pnl,
                "avg_rr": sum(t.get('actual_rr') or 0 for t in strat_trades) / len(strat_trades) if strat_trades else 0
            }

        # 3. Group by Month
        by_month = {}
        for t in trades_list:
            month = t['sell_date_dt'].strftime("%Y-%m")
            if month not in by_month:
                by_month[month] = {"trades": 0, "pnl": 0, "wins": 0}
            by_month[month]["trades"] += 1
            by_month[month]["pnl"] += t['pnl_aud']
            if t['pnl_aud'] > 0:
                by_month[month]["wins"] += 1
        for month in by_month:
            by_month[month]["win_rate"] = by_month[month]["wins"] / by_month[month]["trades"] * 100

        # 4. Daily Breakdown
        daily_breakdown = {}
        for t in trades_list:
            day = t['sell_date_dt'].isoformat()
            if day not in daily_breakdown:
                daily_breakdown[day] = {"trades": 0, "pnl": 0}
            daily_breakdown[day]["trades"] += 1
            daily_breakdown[day]["pnl"] += t['pnl_aud']

        # 4b. Win/Loss day counts and max streaks (over trading days only)
        sorted_days = sorted(daily_breakdown.keys())
        win_days_count = sum(1 for d in sorted_days if daily_breakdown[d]['pnl'] > 0)
        loss_days_count = sum(1 for d in sorted_days if daily_breakdown[d]['pnl'] <= 0)
        max_win_streak = cur_win = 0
        max_loss_streak = cur_loss = 0
        for d in sorted_days:
            if daily_breakdown[d]['pnl'] > 0:
                cur_win += 1; cur_loss = 0
                if cur_win > max_win_streak: max_win_streak = cur_win
            else:
                cur_loss += 1; cur_win = 0
                if cur_loss > max_loss_streak: max_loss_streak = cur_loss
        summary['win_days'] = win_days_count
        summary['loss_days'] = loss_days_count
        summary['max_win_streak'] = max_win_streak
        summary['max_loss_streak'] = max_loss_streak

        # 5. Equity Curve + Max Drawdown
        sorted_trades = sorted(trades_list, key=lambda x: x['sell_date_dt'])
        equity_curve = []
        cumulative_pnl = 0
        peak = 0
        max_dd = 0

        if sorted_trades:
            first_date = sorted_trades[0]['sell_date_dt']
            equity_curve.append({"date": first_date.isoformat(), "cumulative_pnl": 0})

        for t in sorted_trades:
            cumulative_pnl += t['pnl_aud']
            equity_curve.append({
                "date": t['sell_date_dt'].isoformat(),
                "cumulative_pnl": cumulative_pnl
            })
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = (cumulative_pnl - peak) / starting_balance_aud * 100 if starting_balance_aud > 0 else 0
            if dd < max_dd:
                max_dd = dd

        summary['max_drawdown_pct'] = round(max_dd, 2)

        # 6. By Pair breakdown (PAIR::Strategy keyed)
        by_pair: dict = {}
        for t in trades_list:
            pair_key = f"{t.get('symbol', 'Unknown')}::{t.get('strategy', 'Unknown')}"
            if pair_key not in by_pair:
                by_pair[pair_key] = {'trades': 0, 'pnl': 0, 'wins': 0, 'close_types': {}, 'rr_sum': 0}
            by_pair[pair_key]['trades'] += 1
            by_pair[pair_key]['pnl'] += t['pnl_aud']
            by_pair[pair_key]['rr_sum'] += t.get('actual_rr') or 0
            if t['pnl_aud'] > 0:
                by_pair[pair_key]['wins'] += 1
            ct = t.get('close_type') or 'UNKNOWN'
            by_pair[pair_key]['close_types'][ct] = by_pair[pair_key]['close_types'].get(ct, 0) + 1
        for key in by_pair:
            n = by_pair[key]['trades']
            by_pair[key]['win_rate'] = (by_pair[key]['wins'] / n * 100) if n > 0 else 0
            by_pair[key]['avg_rr'] = round(by_pair[key]['rr_sum'] / n, 2) if n > 0 else 0
            del by_pair[key]['rr_sum']

        # 7. All period breakdowns (computed once, switched client-side)
        period_breakdowns = {
            'daily':   _compute_period_breakdown(trades_list, 'daily'),
            'weekly':  _compute_period_breakdown(trades_list, 'weekly'),
            'monthly': _compute_period_breakdown(trades_list, 'monthly'),
            'yearly':  _compute_period_breakdown(trades_list, 'yearly'),
        }
        period_breakdown = period_breakdowns.get(period or 'monthly', {})

        # 8. Backtest comparison
        backtest_ref = _load_backtest_reference()
        backtest_comparison = _build_backtest_comparison(trades_list, backtest_ref)

        return {
            "summary": summary,
            "by_strategy": by_strategy,
            "by_month": by_month,
            "daily_breakdown": daily_breakdown,
            "equity_curve": equity_curve,
            "by_pair": by_pair,
            "period_breakdown": period_breakdown,
            "period_breakdowns": period_breakdowns,
            "backtest_comparison": backtest_comparison,
            "period": period
        }
    except Exception as e:
        logger.error(f"Forex Portfolio Analytics Error: {e}", exc_info=True)
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
    NOTE: Always uses all-time data (no date filter). Add start_date/end_date params
    to this endpoint and pass them through if per-period filtering is needed.
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

        all_docs_data = [doc.to_dict() | {'_id': doc.id} for doc in docs]
        live_prices = fetch_live_prices_for_open_trades(all_docs_data)

        items = []
        for data in all_docs_data:
            metrics = calculate_forex_metrics(data, signals, live_prices)

            # Date handling
            buy_date = data.get('buy_date')
            if isinstance(buy_date, str):
                buy_date = datetime.strptime(buy_date, "%Y-%m-%d").date()

            sell_date = data.get('sell_date')
            if isinstance(sell_date, str):
                sell_date = datetime.strptime(sell_date, "%Y-%m-%d").date()

            items.append(ForexPortfolioItemResponse(
                id=data.get('_id', ''),
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
                realized_gain_aud=(data.get('pnl') if data.get('pnl') is not None else metrics['gain_loss_aud']) if data.get('status') == 'CLOSED' else None,
                actual_rr=data.get('actual_rr'),
                keep_through_close=data.get('keep_through_close'),
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
                # Parse sell_date to YYYY-MM-DD (strip time component)
                closed_at_raw = closed_trade.get('closed_at') or ''
                try:
                    sell_date_str = datetime.fromisoformat(
                        closed_at_raw.replace('Z', '+00:00')
                    ).strftime("%Y-%m-%d")
                except Exception:
                    sell_date_str = datetime.utcnow().strftime("%Y-%m-%d")

                exit_price = closed_trade.get('exit_price')
                entry = data.get('buy_price')
                sl = data.get('stop_loss')
                direction = data.get('direction', 'BUY')
                actual_rr = None
                if entry and sl and exit_price:
                    risk = abs(entry - sl)
                    if risk > 0:
                        gain = exit_price - entry if direction.upper() == 'BUY' else entry - exit_price
                        actual_rr = round(gain / risk, 2)

                doc.reference.update({
                    'status': 'CLOSED',
                    'sell_price': exit_price,
                    'sell_date': sell_date_str,
                    'pnl': closed_trade.get('pnl'),
                    'closed_by': 'OandaSync',
                    'actual_rr': actual_rr,
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


@router.post("/backfill-sell-prices", description="Backfill missing sell_price for CLOSED trades that have oanda_trade_id")
async def backfill_sell_prices(
    email: str = Depends(get_current_user_email)
):
    """
    One-time backfill: fetch actual exit prices from Oanda for CLOSED Firestore trades
    that are missing sell_price (e.g. trades that were closed before the sync fix).
    """
    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
        closed_docs = list(portfolio_ref.where('status', '==', 'CLOSED').stream())

        SYNC_START = date(2026, 2, 19)
        backfilled = 0
        skipped = 0

        for doc in closed_docs:
            data = doc.to_dict()

            # Only process trades opened on or after the sync feature launch date
            buy_date_str = data.get('buy_date') or ''
            try:
                trade_open_date = datetime.strptime(buy_date_str, "%Y-%m-%d").date()
            except ValueError:
                trade_open_date = None

            if trade_open_date is None or trade_open_date < SYNC_START:
                skipped += 1
                continue

            if data.get('sell_price'):
                skipped += 1
                continue

            trade_id = data.get('oanda_trade_id')
            if not trade_id:
                skipped += 1
                continue

            closed_trades = OandaPriceService.get_closed_trades_by_id([trade_id])
            if not closed_trades:
                skipped += 1
                continue

            ct = closed_trades[0]
            exit_price = ct.get('exit_price')
            if not exit_price:
                skipped += 1
                continue

            closed_at_raw = ct.get('closed_at') or ''
            try:
                sell_date_str = datetime.fromisoformat(
                    closed_at_raw.replace('Z', '+00:00')
                ).strftime("%Y-%m-%d")
            except Exception:
                sell_date_str = data.get('sell_date') or datetime.utcnow().strftime("%Y-%m-%d")

            doc.reference.update({
                'sell_price': exit_price,
                'sell_date': sell_date_str,
                'pnl': ct.get('pnl', 0.0),
                'updated_at': datetime.utcnow()
            })
            backfilled += 1
            logger.info(f"Backfilled trade {trade_id}: sell_price={exit_price}")

        return {
            "status": "success",
            "backfilled": backfilled,
            "skipped": skipped,
            "message": f"Backfilled {backfilled} trades, skipped {skipped}"
        }

    except Exception as e:
        logger.error(f"Error backfilling sell prices: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to backfill: {str(e)}")


@router.patch("/trades/{trade_id}/keep-through-close")
async def set_keep_through_close(
    trade_id: str,
    body: dict = Body(...),
    email: str = Depends(get_current_user_email),
):
    """
    Toggle the keep_through_close flag on an open trade.
    Admin only. When True, the pre-close job will skip closing this position.

    Body: { "keep_through_close": true | false }
    """
    if email != settings.AUTHORIZED_AUTO_TRADER_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    keep = body.get("keep_through_close")
    if not isinstance(keep, bool):
        raise HTTPException(status_code=422, detail="keep_through_close must be a boolean")

    try:
        doc_ref = (
            db.collection("users")
            .document(email)
            .collection("forex_portfolio")
            .document(trade_id)
        )
        doc = doc_ref.get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Trade not found")

        doc_ref.update({
            "keep_through_close": keep,
            "updated_at": datetime.now(timezone.utc),
        })
        logger.info(f"keep_through_close={keep} set on trade {trade_id} by {email}")
        return {"success": True, "trade_id": trade_id, "keep_through_close": keep}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting keep_through_close on {trade_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update trade")


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


@router.post("/backfill-close-type", description="Backfill close_type for CLOSED trades missing that field (admin only)")
async def backfill_close_type(
    email: str = Depends(get_current_user_email)
):
    """
    Iterate CLOSED trades with oanda_trade_id but no close_type, fetch from Oanda,
    and write back to Firestore. Rate-limited to 1 call/second to respect Oanda limits.
    """
    import asyncio

    ADMIN_EMAIL = settings.AUTHORIZED_AUTO_TRADER_EMAIL
    if email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin only")

    try:
        portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
        closed_docs = list(portfolio_ref.where('status', '==', 'CLOSED').stream())

        updated = 0
        skipped = 0

        for doc in closed_docs:
            data = doc.to_dict()
            if data.get('close_type'):
                skipped += 1
                continue
            trade_id = data.get('oanda_trade_id')
            if not trade_id:
                skipped += 1
                continue

            close_type = OandaPriceService.get_trade_close_type(trade_id)
            doc.reference.update({'close_type': close_type, 'updated_at': datetime.utcnow()})
            updated += 1
            logger.info(f"Backfilled close_type={close_type} for trade {trade_id}")

            await asyncio.sleep(1)  # 1 call/sec rate limit — non-blocking

        return {
            "status": "success",
            "updated": updated,
            "skipped": skipped,
            "message": f"Backfilled close_type for {updated} trades, skipped {skipped}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error backfilling close_type: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to backfill: {str(e)}")
