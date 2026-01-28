"""
Silver Dummy Trade Verification Script

Executes a 1-unit trade on Silver (XAG_USD) to verify OANDA and Firestore integration.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from app.services.oanda_price import OandaPriceService
from app.services.oanda_trade_service import OandaTradeService
from oandapyV20 import API
import oandapyV20.endpoints.trades as trades
from app.config import settings

def run_test():
    symbol = "XAG_USD"
    print(f"🚀 Starting dummy trade verification for {symbol}...")

    # 1. Get current price
    price = OandaPriceService.get_current_price(symbol)
    if not price:
        print("❌ Error: Could not fetch price.")
        return

    print(f"Current Price: {price}")

    # 2. Prepare dummy signal
    # SL 5% below, TP 5% above
    stop_loss = price * 0.95
    take_profit = price * 1.05
    
    dummy_signal = {
        "symbol": symbol,
        "signal": "BUY",
        "price": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "strategy": "VERIFICATION_TEST",
        "score": 100,
        "timeframe_used": "1m"
    }

    # 3. Execute Trade via OandaTradeService
    # We will call place_market_order directly to avoid ranking logic for this test
    # but still use the service logic for Firestore logging
    print(f"Placing 1-unit BUY order for {symbol}...")
    
    # We use 1 unit for minimal risk
    response = OandaPriceService.place_market_order(symbol, 1, stop_loss, take_profit)
    
    if response and 'orderFillTransaction' in response:
        fill = response['orderFillTransaction']
        exec_price = float(fill.get('price'))
        trade_id = fill.get('id')
        print(f"✅ OANDA Trade Executed: ID {trade_id} at {exec_price}")

        # Log to Firestore
        print("Logging to Firestore...")
        OandaTradeService._log_to_portfolio(settings.AUTHORIZED_AUTO_TRADER_EMAIL, dummy_signal, 1, exec_price, trade_id)
        print("✅ Firestore logging complete.")

        print("\n--- ACTION REQUIRED ---")
        print(f"1. Check your OANDA dashboard for Trade ID: {trade_id}")
        print(f"2. Check your Portfolio UI for {symbol} trade.")
        
        print("\nWaiting 15 seconds before closing the trade automatically...")
        time.sleep(15)

        # 4. Close the trade
        print(f"Closing trade {trade_id}...")
        api = OandaPriceService.get_api()
        r = trades.TradeClose(accountID=settings.OANDA_ACCOUNT_ID, tradeID=trade_id)
        try:
            api.request(r)
            print(f"✅ Trade {trade_id} closed successfully.")
        except Exception as e:
            print(f"❌ Failed to close trade: {e}")

    else:
        print(f"❌ Trade failed. Response: {response}")

if __name__ == "__main__":
    run_test()
