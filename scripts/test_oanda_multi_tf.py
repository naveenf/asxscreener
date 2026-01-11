import os
import pandas as pd
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
import sys
from dotenv import load_dotenv

# Load env vars from backend/.env
load_dotenv("backend/.env")

def download_tf(api, instrument, granularity, label):
    print(f"\n--- Testing {label} ({granularity}) ---")
    params = {
        "count": 5000,
        "granularity": granularity
    }
    
    try:
        r = instruments.InstrumentsCandles(instrument=instrument, params=params)
        api.request(r)
        data = r.response['candles']
        
        if not data:
            print("No data received.")
            return

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
        print(f"Downloaded {len(df)} rows.")
        print(f"Start: {df['Date'].iloc[0]}")
        print(f"End:   {df['Date'].iloc[-1]}")
        
        # Calculate duration
        start_dt = pd.to_datetime(df['Date'].iloc[0])
        end_dt = pd.to_datetime(df['Date'].iloc[-1])
        duration = end_dt - start_dt
        print(f"Duration covered: {duration}")

        # Save to file
        filename = f"data/forex_raw/{instrument}_{label}.csv"
        os.makedirs("data/forex_raw", exist_ok=True)
        df.to_csv(filename, index=False)
        print(f"Saved to {filename}")

    except Exception as e:
        print(f"Error: {e}")

def main():
    token = os.environ.get("OANDA_ACCESS_TOKEN")
    env = os.environ.get("OANDA_ENV", "live")
    
    if not token:
        print("Error: OANDA credentials not found in environment.")
        return

    api = API(access_token=token, environment=env)
    instrument = "USD_JPY"

    # 1. 15 Minute
    download_tf(api, instrument, "M15", "15_Min")
    
    # 2. 1 Hour
    download_tf(api, instrument, "H1", "1_Hour")
    
    # 3. 4 Hour
    download_tf(api, instrument, "H4", "4_Hour")

if __name__ == "__main__":
    main()
