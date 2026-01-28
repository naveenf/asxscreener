"""
OANDA Connectivity Diagnostic Script

Fetches account summary and verifies connectivity to the OANDA API.
"""

import os
import sys
from pathlib import Path

# Add backend to path so we can import app
sys.path.append(str(Path(__file__).parent.parent / "backend"))

from oandapyV20 import API
import oandapyV20.endpoints.accounts as accounts
import oandapyV20.endpoints.instruments as instruments
from app.config import settings

def test_connection():
    token = settings.OANDA_ACCESS_TOKEN
    account_id = settings.OANDA_ACCOUNT_ID
    env = settings.OANDA_ENV

    if not token or not account_id:
        print("❌ Error: OANDA_ACCESS_TOKEN or OANDA_ACCOUNT_ID not set in .env")
        return

    print(f"Connecting to OANDA ({env})...")
    api = API(access_token=token, environment=env)

    try:
        # 1. Fetch Account Summary
        print(f"\n--- Account Summary ({account_id}) ---")
        r = accounts.AccountSummary(accountID=account_id)
        api.request(r)
        summary = r.response.get('account', {})
        
        print(f"Balance:      {summary.get('balance')} {summary.get('currency')}")
        print(f"NAV:          {summary.get('NAV')} {summary.get('currency')}")
        print(f"Margin Used:  {summary.get('marginUsed')} {summary.get('currency')}")
        print(f"Margin Avail: {summary.get('marginAvailable')} {summary.get('currency')}")
        print(f"Open Trades:  {summary.get('openTradeCount')}")

        # 2. Check a few instruments
        print("\n--- Instrument Details ---")
        test_instruments = ["XAG_USD", "AUD_USD", "USD_JPY"]
        
        # We need to fetch instrument details to see margin rates (leverage)
        # The AccountInstruments endpoint returns all valid instruments for the account
        r = accounts.AccountInstruments(accountID=account_id, params={"instruments": ",".join(test_instruments)})
        api.request(r)
        
        instrument_list = r.response.get('instruments', [])
        for inst in instrument_list:
            name = inst.get('name')
            margin_rate = inst.get('marginRate')
            leverage = 1.0 / float(margin_rate) if margin_rate else "N/A"
            print(f"Symbol: {name:10} | Margin Rate: {margin_rate:8} | Max Leverage: {leverage:.0f}:1")

        print("\n✅ Connectivity test successful!")

    except Exception as e:
        print(f"\n❌ Connectivity test FAILED: {e}")

if __name__ == "__main__":
    test_connection()
