"""
OANDA Price & Trading Service

Fetches real-time price data and handles trade execution via OANDA API.
"""

import logging
import time
from functools import wraps
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.orders as orders
import oandapyV20.endpoints.trades as trades
from typing import Optional, Dict, Any, List, Callable
from ..config import settings

logger = logging.getLogger(__name__)

def retry_oanda(retries=3, delay=2):
    """Decorator to retry OANDA API calls on timeout or connection errors."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    # If it's a timeout or connection issue, retry
                    if "timed out" in str(e).lower() or "connection" in str(e).lower():
                        logger.warning(f"OANDA API {func.__name__} attempt {i+1} failed: {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        # For other errors (like 401, 404), don't retry
                        raise e
            logger.error(f"OANDA API {func.__name__} failed after {retries} retries.")
            return None
        return wrapper
    return decorator

class OandaPriceService:
    _api: Optional[API] = None

    @classmethod
    @retry_oanda(retries=2, delay=1)
    def list_all_accounts(cls) -> List[Dict[str, Any]]:
        """
        List all available Oanda accounts for this API token.
        Use this to find the account ID with your trades.
        """
        api = cls.get_api()
        if not api:
            return []

        try:
            import oandapyV20.endpoints.accounts as accounts_ep

            r = accounts_ep.AccountList()
            api.request(r)
            accounts_list = r.response.get('accounts', [])

            result = []
            for acc in accounts_list:
                result.append({
                    'account_id': acc.get('id'),
                    'alias': acc.get('alias'),
                    'currency': acc.get('currency'),
                    'balance': acc.get('balance'),
                    'type': acc.get('type')
                })

            logger.info(f"Found {len(result)} Oanda accounts:")
            for acc in result:
                logger.info(f"  Account: {acc['account_id']} | {acc['alias']} | Balance: {acc['balance']} {acc['currency']}")

            return result

        except Exception as e:
            logger.error(f"Error listing accounts: {e}")
            return []

    @classmethod
    def get_api(cls) -> Optional[API]:
        if cls._api:
            return cls._api
        
        token = settings.OANDA_ACCESS_TOKEN
        if not token:
            logger.warning("OANDA_ACCESS_TOKEN not set.")
            return None
            
        try:
            # Increased timeout from 10s to 20s
            cls._api = API(access_token=token, environment=settings.OANDA_ENV, request_params={"timeout": 20})
            return cls._api
        except Exception as e:
            logger.error(f"Error initializing OANDA API: {e}")
            return None

    @classmethod
    @retry_oanda(retries=3, delay=2)
    def get_current_price(cls, symbol: str) -> Optional[float]:
        """
        Get the latest Close price for a symbol (e.g. 'XAG_USD').
        Uses 5-second candles to get the most recent completed snapshot.
        """
        api = cls.get_api()
        if not api:
            return None

        params = {
            "count": 1,
            "granularity": "S5", # 5 second candles
            "price": "M" # Midpoint
        }
        
        r = instruments.InstrumentsCandles(instrument=symbol, params=params)
        api.request(r)
        candles = r.response.get('candles', [])
        
        if candles:
            return float(candles[0]['mid']['c'])
        return None

    @classmethod
    @retry_oanda(retries=3, delay=1)
    def get_current_spread(cls, symbol: str) -> Optional[float]:
        """
        Get the current spread (Ask - Bid) for a symbol.
        """
        api = cls.get_api()
        if not api:
            return None

        params = {
            "count": 1,
            "granularity": "S5",
            "price": "BA" # Bid/Ask
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=symbol, params=params)
            api.request(r)
            candles = r.response.get('candles', [])
            
            if candles:
                bid = float(candles[0]['bid']['c'])
                ask = float(candles[0]['ask']['c'])
                return ask - bid
        except Exception as e:
            logger.error(f"Error fetching spread for {symbol}: {e}")
        
        return None

    @classmethod
    @retry_oanda(retries=3, delay=1)
    def get_account_summary(cls) -> Optional[Dict[str, Any]]:
        """Fetch account balance, NAV, and margin info."""
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            return None
            
        r = accounts.AccountSummary(accountID=account_id)
        api.request(r)
        return r.response.get('account')

    @classmethod
    @retry_oanda(retries=3, delay=1)
    def get_instrument_details(cls, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch instrument details including marginRate and displayPrecision."""
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            return None
            
        r = accounts.AccountInstruments(accountID=account_id, params={"instruments": symbol})
        api.request(r)
        instruments_list = r.response.get('instruments', [])
        return instruments_list[0] if instruments_list else None

    @classmethod
    @retry_oanda(retries=2, delay=1)
    def get_open_trades(cls) -> List[str]:
        """Fetch list of symbols currently having open trades in Oanda."""
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            return []
            
        r = trades.OpenTrades(accountID=account_id)
        api.request(r)
        open_trades = r.response.get('trades', [])
        return [t.get('instrument') for t in open_trades]

    @classmethod
    def place_market_order(cls, symbol: str, units: float, stop_loss: float, take_profit: float) -> Optional[Dict[str, Any]]:
        """
        Place a Market Order with Stop Loss and Take Profit attached.
        Units: Positive for Buy, Negative for Sell (Can be fractional).
        NOTE: Retries are disabled for this method to prevent double-execution on timeouts.
        """
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            return None

        # Format SL/TP and Units based on instrument precision
        try:
            inst_info = cls.get_instrument_details(symbol)
        except Exception:
            inst_info = None
        
        # Fallback precision logic
        if inst_info:
            precision = int(inst_info.get('displayPrecision', 5))
            unit_precision = int(inst_info.get('tradeUnitsPrecision', 0))
        else:
            precision = 3 if "JPY" in symbol else 5
            unit_precision = 0
        
        sl_str = f"{stop_loss:.{precision}f}"
        tp_str = f"{take_profit:.{precision}f}"
        units_str = f"{units:.{unit_precision}f}"

        order_data = {
            "order": {
                "units": units_str,
                "instrument": symbol,
                "timeInForce": "FOK", # Fill or Kill
                "type": "MARKET",
                "positionFill": "DEFAULT",
                "stopLossOnFill": {
                    "price": sl_str,
                    "timeInForce": "GTC"
                },
                "takeProfitOnFill": {
                    "price": tp_str,
                    "timeInForce": "GTC"
                }
            }
        }
        
        logger.info(f"OANDA: Placing order for {symbol} ({units_str} units, SL: {sl_str}, TP: {tp_str})")
        r = orders.OrderCreate(accountID=account_id, data=order_data)
        api.request(r)
        
        # Check for rejection
        if 'orderRejectTransaction' in r.response:
            reason = r.response['orderRejectTransaction'].get('rejectReason', 'Unknown')
            logger.error(f"OANDA Order REJECTED for {symbol}: {reason}")
            return r.response
            
        return r.response

    @classmethod
    @retry_oanda(retries=2, delay=1)  # Lower retry count for closures
    def close_trade(cls, trade_id: str, units: str = "ALL") -> Optional[Dict[str, Any]]:
        """
        Close an open trade by trade ID.

        Args:
            trade_id: Oanda trade ID from orderFillTransaction
            units: "ALL" to close fully, or specific unit count for partial

        Returns:
            Response dict with orderFillTransaction or orderRejectTransaction
            None if API unavailable or network error
        """
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            logger.error("OANDA API or Account ID not available for trade close")
            return None

        data = {"units": units}

        logger.info(f"OANDA: Closing trade {trade_id} ({units} units)")
        r = trades.TradeClose(accountID=account_id, tradeID=trade_id, data=data)

        try:
            api.request(r)

            # Check for rejection
            if 'orderRejectTransaction' in r.response:
                reason = r.response['orderRejectTransaction'].get('rejectReason', 'Unknown')
                logger.error(f"OANDA Trade Close REJECTED for {trade_id}: {reason}")
                return r.response

            logger.info(f"OANDA: Trade {trade_id} closed successfully")
            return r.response

        except Exception as e:
            # Handle specific HTTP errors
            if "404" in str(e):
                logger.warning(f"Trade {trade_id} not found (already closed or invalid ID)")
            elif "401" in str(e):
                logger.error("OANDA authentication failed during trade close")
            else:
                logger.error(f"Unexpected error closing trade {trade_id}: {e}")
            return None

    @classmethod
    @retry_oanda(retries=2, delay=1)
    def get_trade_details(cls, trade_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch details of a specific trade by ID.
        Used to verify closure and get actual close price.
        Returns: Dict with trade details or None if not found
        """
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            return None

        try:
            r = trades.TradeDetails(accountID=account_id, tradeID=trade_id)
            api.request(r)
            trade_data = r.response.get('trade')

            if trade_data:
                logger.info(f"Trade {trade_id}: Status={trade_data.get('state')}, P&L={trade_data.get('unrealizedPL')}")

            return trade_data
        except Exception as e:
            logger.warning(f"Trade {trade_id} not found or error: {e}")
            return None

    @classmethod
    def get_closed_trades_by_id(cls, trade_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch details for specific trades by ID.
        Used to get exit prices and P&L for trades we know about.
        """
        closed_trades = []

        for trade_id in trade_ids:
            trade_data = cls.get_trade_details(trade_id)
            if trade_data:
                state = trade_data.get('state')

                # Extract closed trade data if trade is closed
                if state == 'CLOSED':
                    closed_trade = {
                        'trade_id': trade_id,
                        'symbol': trade_data.get('instrument'),
                        'entry_price': float(trade_data.get('initialPrice', 0)),
                        'exit_price': float(trade_data.get('closingTransaction', {}).get('price', 0)) if trade_data.get('closingTransaction') else None,
                        'pnl': float(trade_data.get('closingTransaction', {}).get('pl', 0)) if trade_data.get('closingTransaction') else 0,
                        'closed_at': trade_data.get('closingTransaction', {}).get('time') if trade_data.get('closingTransaction') else None,
                        'state': state
                    }
                    closed_trades.append(closed_trade)
                    logger.info(f"Found CLOSED trade {trade_id}: Exit={closed_trade['exit_price']}, P&L={closed_trade['pnl']}")

        return closed_trades

    @classmethod
    @retry_oanda(retries=2, delay=1)
    def get_all_trades_with_history(cls, from_time: Optional[str] = None, to_time: Optional[str] = None, instrument: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch ALL trades from Oanda: both OPEN (active) and CLOSED (completed).

        Args:
            from_time: ISO 8601 datetime string (e.g., "2026-02-17T00:00:00Z")
            to_time: ISO 8601 datetime string
            instrument: Filter by instrument (e.g., "XAG_USD")

        Returns:
            List of all trades (OPEN and CLOSED) with entry/exit prices and P&L
        """
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            logger.error("Oanda API or Account ID not configured")
            return []

        logger.info(f"Fetching trades for account: {account_id}")

        try:
            import oandapyV20.endpoints.transactions as transactions
            import oandapyV20.endpoints.trades as trades_api

            all_trades = []

            # ===== 1. FETCH OPEN TRADES (Active Positions) =====
            try:
                r_open = trades_api.OpenTrades(accountID=account_id)
                api.request(r_open)
                open_trades_list = r_open.response.get('trades', [])

                logger.info(f"OpenTrades Response Keys: {r_open.response.keys() if r_open.response else 'None'}")
                logger.info(f"Full OpenTrades Response: {r_open.response}")
                logger.info(f"Found {len(open_trades_list)} OPEN trades in Oanda")

                for trade in open_trades_list:
                    # Skip if wrong instrument
                    if instrument and trade.get('instrument') != instrument:
                        continue

                    trade_dict = {
                        'trade_id': trade.get('id'),
                        'symbol': trade.get('instrument'),
                        'direction': 'BUY' if int(trade.get('initialUnits', 0)) > 0 else 'SELL',
                        'entry_price': float(trade.get('price', 0)),
                        'exit_price': None,  # Still open
                        'units': abs(int(trade.get('initialUnits', 0))),
                        'pnl': float(trade.get('unrealizedPL', 0)),  # Unrealized P&L
                        'opened_at': trade.get('openTime'),
                        'closed_at': None,
                        'status': 'OPEN',
                        'reason': 'Still Active'
                    }
                    all_trades.append(trade_dict)

            except Exception as e:
                logger.warning(f"Error fetching open trades: {e}")

            # ===== 2. FETCH CLOSED TRADES (Historical) =====
            try:
                # First, try without time filters to see if ANY transactions exist
                params_all = {
                    "pageSize": 500
                }
                r_txn_all = transactions.TransactionList(accountID=account_id, params=params_all)
                api.request(r_txn_all)
                all_txns_count = r_txn_all.response.get('count', 0)
                logger.info(f"Total transactions in account (all time): {all_txns_count}")

                # Now try with date filters
                params = {
                    "pageSize": 500
                }
                if from_time:
                    params["from"] = from_time
                if to_time:
                    params["to"] = to_time

                r_txn = transactions.TransactionList(accountID=account_id, params=params)
                api.request(r_txn)

                all_transactions = r_txn.response.get('transactions', [])

                # Debug: Log response structure
                logger.info(f"TransactionList Response Keys: {r_txn.response.keys() if r_txn.response else 'None'}")
                logger.info(f"Response pageSize: {r_txn.response.get('pageSize')}")
                logger.info(f"Response lastTransactionID: {r_txn.response.get('lastTransactionID')}")

                # Debug: Log transaction types
                txn_types = set(t.get('type') for t in all_transactions)
                logger.info(f"Transaction types found: {txn_types}")
                logger.info(f"Total transactions: {len(all_transactions)}")
                if all_transactions:
                    logger.info(f"First transaction sample: {all_transactions[0]}")

                # Extract order fills and trade closures
                order_fills = {}

                for txn in all_transactions:
                    if txn.get('type') == 'ORDER_FILL':
                        opened = txn.get('tradeOpened')
                        if opened:
                            order_fills[opened.get('tradeID')] = txn

                logger.info(f"Found {len(order_fills)} order fills")

                # Extract closed trades
                for txn in all_transactions:
                    if txn.get('type') == 'TRADE_CLOSE':
                        trade_id = txn.get('tradeID')

                        # Skip if wrong instrument
                        if instrument and txn.get('instrument') != instrument:
                            continue

                        # Only include if within date range
                        entry_txn = order_fills.get(trade_id, {})

                        closed_trade = {
                            'trade_id': trade_id,
                            'symbol': txn.get('instrument'),
                            'direction': 'BUY' if float(txn.get('units', 0)) > 0 else 'SELL',
                            'entry_price': float(entry_txn.get('price', 0)),
                            'exit_price': float(txn.get('price', 0)),
                            'units': abs(float(txn.get('units', 0))),
                            'pnl': float(txn.get('pl', 0)),  # Realized P&L
                            'opened_at': entry_txn.get('time'),
                            'closed_at': txn.get('time'),
                            'status': 'CLOSED',
                            'reason': txn.get('reason', 'Manual Close')
                        }

                        all_trades.append(closed_trade)

                logger.info(f"Found {len([t for t in all_transactions if t.get('type') == 'TRADE_CLOSE'])} TRADE_CLOSE transactions")

            except Exception as e:
                logger.warning(f"Error fetching transaction history: {e}")

            logger.info(f"Fetched {len(all_trades)} total trades (OPEN + CLOSED) from Oanda")
            return all_trades

        except Exception as e:
            logger.error(f"Error fetching trades from Oanda: {e}")
            return []

