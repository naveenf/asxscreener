"""
OANDA Price Service

Fetches real-time price data from OANDA API.
"""

from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from typing import Optional
from ..config import settings

class OandaPriceService:
    _api: Optional[API] = None

    @classmethod
    def get_api(cls) -> Optional[API]:
        if cls._api:
            return cls._api
        
        token = settings.OANDA_ACCESS_TOKEN
        if not token:
            print("Warning: OANDA_ACCESS_TOKEN not set.")
            return None
            
        try:
            cls._api = API(access_token=token, environment=settings.OANDA_ENV)
            return cls._api
        except Exception as e:
            print(f"Error initializing OANDA API: {e}")
            return None

    @classmethod
    def get_current_price(cls, symbol: str) -> Optional[float]:
        """
        Get the latest Close price for a symbol (e.g. 'XAG_USD').
        Uses 5-second candles to get the most recent completed snapshot.
        """
        api = cls.get_api()
        if not api:
            return None

        # OANDA format check (just in case)
        # Assuming symbol is already in OANDA format like 'XAG_USD'
        
        params = {
            "count": 1,
            "granularity": "S5", # 5 second candles
            "price": "M" # Midpoint
        }
        
        try:
            r = instruments.InstrumentsCandles(instrument=symbol, params=params)
            api.request(r)
            candles = r.response.get('candles', [])
            
            if candles and candles[0]['complete']:
                return float(candles[0]['mid']['c'])
            elif candles:
                # Even if incomplete, it's the latest tick info
                return float(candles[0]['mid']['c'])
            return None
        except Exception as e:
            print(f"OANDA Price Fetch Error ({symbol}): {e}")
            return None
