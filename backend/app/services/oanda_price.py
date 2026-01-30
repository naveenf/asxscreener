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
    def place_market_order(cls, symbol: str, units: int, stop_loss: float, take_profit: float) -> Optional[Dict[str, Any]]:
        """
        Place a Market Order with Stop Loss and Take Profit attached.
        Units: Positive for Buy, Negative for Sell.
        NOTE: Retries are disabled for this method to prevent double-execution on timeouts.
        """
        api = cls.get_api()
        account_id = settings.OANDA_ACCOUNT_ID
        if not api or not account_id:
            return None

        # Format SL/TP based on instrument precision
        try:
            inst_info = cls.get_instrument_details(symbol)
        except Exception:
            inst_info = None
        
        # Fallback precision logic for safety
        if inst_info:
            precision = int(inst_info.get('displayPrecision', 5))
        else:
            precision = 3 if "JPY" in symbol else 5
        
        sl_str = f"{stop_loss:.{precision}f}"
        tp_str = f"{take_profit:.{precision}f}"

        order_data = {
            "order": {
                "units": str(units),
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
        
        logger.info(f"OANDA: Placing order for {symbol} ({units} units, SL: {sl_str}, TP: {tp_str})")
        r = orders.OrderCreate(accountID=account_id, data=order_data)
        api.request(r)
        
        # Check for rejection
        if 'orderRejectTransaction' in r.response:
            reason = r.response['orderRejectTransaction'].get('rejectReason', 'Unknown')
            logger.error(f"OANDA Order REJECTED for {symbol}: {reason}")
            return r.response
            
        return r.response

