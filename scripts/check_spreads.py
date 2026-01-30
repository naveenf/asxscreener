"""
OANDA Spread Diagnostic Script

Fetches current Bid/Ask prices for all active pairs to calculate 
the percentage spread impact.
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from app.services.oanda_price import OandaPriceService
from app.config import settings
import oandapyV20.endpoints.instruments as instruments

def check_spreads():
    api = OandaPriceService.get_api()
    if not api:
        print("❌ Error: OANDA API not initialized.")
        return

    # Assets to check (from your strategy map)
    assets = [
        "WHEAT_USD", "BCO_USD", 
        "XAG_USD", "XAU_USD", "NAS100_USD", "AUD_USD", "USD_JPY", "GBP_USD"
    ]

    print(f"{'Symbol':12} | {'Mid':10} | {'Spread %':10} | {'Risk Impact'}")
    print("-" * 55)

    for symbol in assets:
        params = {"count": 1, "granularity": "S5", "price": "BA"} # Fetch Bid/Ask
        try:
            r = instruments.InstrumentsCandles(instrument=symbol, params=params)
            api.request(r)
            candles = r.response.get('candles', [])
            
            if not candles:
                continue
                
            bid = float(candles[0]['ask']['c']) # Entry price for Sell (actually we buy at Ask)
            ask = float(candles[0]['ask']['c']) 
            
            # OandaBA response structure
            bid = float(candles[0]['bid']['c'])
            ask = float(candles[0]['ask']['c'])
            mid = (bid + ask) / 2
            
            spread_points = ask - bid
            spread_pct = (spread_points / mid) * 100
            
            # Risk Impact: How much of your 2% risk is eaten by the spread?
            # If spread is 0.5% and total risk is 2%, spread eats 25% of your SL room.
            risk_eaten = (spread_pct / 0.5) * 100 # Relative to a 0.5% SL

            status = "⚠️ HIGH" if spread_pct > 0.1 else "✅ LOW"
            if spread_pct > 0.3: status = "❌ EXTREME"

            print(f"{symbol:12} | {mid:10.4f} | {spread_pct:9.3f}% | {status}")
            
        except Exception as e:
            print(f"{symbol:12} | Error: {e}")

if __name__ == "__main__":
    check_spreads()
