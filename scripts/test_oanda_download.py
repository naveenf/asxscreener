import os
import pandas as pd
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import sys
import json

def test_download():
    token = os.environ.get("OANDA_ACCESS_TOKEN")
    env = os.environ.get("OANDA_ENV", "live") # Default to live as requested
    
    if not token:
        print("Error: OANDA_ACCESS_TOKEN environment variable not set.")
        sys.exit(1)

    print(f"Environment: {env}")
    print(f"Attempting to download USD_JPY using token: {token[:4]}...{token[-4:]}")
    
    try:
        api = API(access_token=token, environment=env)
        
        # We want to see how much data we can get.
        # count: max is 5000 per request.
        # granularity: 'D' for Daily, 'H1' for Hourly, etc.
        # Let's try Daily first to see historical depth.
        params = {
            "count": 5000,
            "granularity": "D" 
        }
        
        instrument = "USD_JPY"
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        
        data = r.response['candles']
        print(f"Successfully downloaded {len(data)} candles.")
        
        if data:
            records = []
            for candle in data:
                if not candle['complete']: continue
                records.append({
                    "Date": candle['time'],
                    "Open": float(candle['mid']['o']),
                    "High": float(candle['mid']['h']),
                    "Low": float(candle['mid']['l']),
                    "Close": float(candle['mid']['c']),
                    "Volume": candle['volume']
                })
            df = pd.DataFrame(records)
            print(f"\nFirst Date: {df['Date'].iloc[0]}")
            print(f"Last Date: {df['Date'].iloc[-1]}")
            print(f"Total Rows: {len(df)}")
            
            # Save to a test file to verify content
            output_path = "data/forex_raw/USD_JPY_oanda_test.csv"
            os.makedirs("data/forex_raw", exist_ok=True)
            df.to_csv(output_path, index=False)
            print(f"\nSaved test data to {output_path}")
            
    except Exception as e:
        print(f"Error downloading data: {e}")

if __name__ == "__main__":
    test_download()
