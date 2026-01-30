import os
import pandas as pd
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from dotenv import load_dotenv
from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent
# Try root first, then backend/
if (PROJECT_ROOT / ".env").exists():
    load_dotenv(PROJECT_ROOT / ".env")
else:
    load_dotenv(PROJECT_ROOT / "backend" / ".env")

# Config
DATA_DIR = PROJECT_ROOT / "data" / "forex_raw"
CONFIG_PATH = PROJECT_ROOT / "data" / "metadata" / "forex_pairs.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# OANDA Limits
MAX_CANDLES = 5000

def retry_request(retries=3, delay=5):
    """Decorator to retry OANDA API calls on network-related errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_err = None
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    err_msg = str(e).lower()
                    # Retry on connection, DNS (name resolution), or SSL errors
                    if any(x in err_msg for x in ["connection", "name resolution", "ssl", "timeout", "remote end"]):
                        print(f"  [Retry] Attempt {i+1} failed: {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        # For auth or logic errors, don't retry
                        break
            print(f"  [Error] Failed after {retries} attempts: {last_err}")
            return []
        return wrapper
    return decorator

def get_oanda_api():
    token = os.environ.get("OANDA_ACCESS_TOKEN")
    env = os.environ.get("OANDA_ENV", "live")
    if not token:
        print("Error: OANDA_ACCESS_TOKEN not found.")
        return None
    # Use a longer timeout for the downloader
    return API(access_token=token, environment=env, request_params={"timeout": 30})

def load_pairs():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)['pairs']

@retry_request(retries=4, delay=5)
def fetch_candles(api, instrument, granularity, start_time=None, count=5000):
    """
    Fetch candles from OANDA.
    """
    params = {
        "granularity": granularity,
        "alignmentTimezone": "America/New_York" # Standardize
    }

    if start_time:
        from_str = start_time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        params["from"] = from_str
        params["count"] = count 
    else:
        params["count"] = count

    r = instruments.InstrumentsCandles(instrument=instrument, params=params)
    api.request(r)
    return r.response.get('candles', [])

def parse_candles(candles):
    records = []
    for c in candles:
        if not c['complete']: continue
        records.append({
            "Date": c['time'],
            "Open": float(c['mid']['o']),
            "High": float(c['mid']['h']),
            "Low": float(c['mid']['l']),
            "Close": float(c['mid']['c']),
            "Volume": int(c['volume'])
        })
    return records

def update_dataset(api, symbol, oanda_symbol, granularity, label):
    """
    Update the CSV dataset for a specific timeframe.
    file_name: e.g. "EUR_USD_15_Min.csv"
    """
    # Map granularity to file suffix
    if granularity == "M15":
        suffix = "15_Min"
    elif granularity == "H1":
        suffix = "1_Hour"
    elif granularity == "H4":
        suffix = "4_Hour"
    elif granularity == "M3":
        suffix = "3_Min"
    elif granularity == "M5":
        suffix = "5_Min"
    else:
        suffix = granularity

    filename = DATA_DIR / f"{symbol}_{suffix}.csv"
    
    # 1. Determine start time
    start_time = None
    existing_df = None
    
    if filename.exists():
        try:
            existing_df = pd.read_csv(filename)
            existing_df['Date'] = pd.to_datetime(existing_df['Date'])
            last_date = existing_df['Date'].max()
            # Start from the last date
            start_time = last_date
            print(f"  [{label}] Found existing data. Last: {last_date}. Appending...")
        except Exception as e:
            print(f"  [{label}] Error reading existing file: {e}. Starting fresh.")
    
    # 2. Fetch Data
    candles = fetch_candles(api, oanda_symbol, granularity, start_time)
    
    if not candles:
        print(f"  [{label}] No new data received.")
        return

    new_records = parse_candles(candles)
    if not new_records:
        print(f"  [{label}] No complete candles returned.")
        return

    new_df = pd.DataFrame(new_records)
    new_df['Date'] = pd.to_datetime(new_df['Date'])

    # 3. Merge and Save
    if existing_df is not None:
        # Concatenate
        combined_df = pd.concat([existing_df, new_df])
        # Drop duplicates based on Date
        combined_df = combined_df.drop_duplicates(subset=['Date'], keep='last')
        combined_df = combined_df.sort_values('Date')
        
        # Optional: Limit file size (e.g. keep last 20k rows)
        if len(combined_df) > 20000:
             combined_df = combined_df.tail(20000)
             
        combined_df.to_csv(filename, index=False)
        print(f"  [{label}] Updated. New rows: {len(new_df)}. Total: {len(combined_df)}")
    else:
        new_df.to_csv(filename, index=False)
        print(f"  [{label}] Created fresh. Total: {len(new_df)}")


def main():
    api = get_oanda_api()
    if not api:
        sys.exit(1)

    pairs = load_pairs()
    now = datetime.now()
    
    # Logic for update schedule
    # Cron logic: 
    # M15: Every run (assuming script runs every 15m)
    # H1, H4: Always attempt update. 
    # Why? 
    # 1. It makes the script idempotent and robust to missed runs or startup delays.
    # 2. OANDA API just returns empty or existing candles if no new 'completed' candle exists.
    # 3. We filter for 'complete' candles and duplicates, so there's no harm in polling.
    
    print(f"Starting Forex Update at {now.strftime('%H:%M')}")
    print(f"Plan: M15=Yes | H1=Yes | H4=Yes (Polling for completed candles)")

    for pair in pairs:
        symbol = pair['symbol'] # e.g. EURUSD=X (keep for file naming)
        oanda_symbol = pair.get('oanda_symbol') # e.g. EUR_USD
        
        if not oanda_symbol:
            print(f"Skipping {symbol} (No OANDA mapping)")
            continue
            
        print(f"Processing {pair['name']} ({oanda_symbol})...")
        
        # M15 Update
        update_dataset(api, symbol, oanda_symbol, "M15", "15_Min")
        
        # H1 Update
        update_dataset(api, symbol, oanda_symbol, "H1", "1_Hour")
            
        # H4 Update
        update_dataset(api, symbol, oanda_symbol, "H4", "4_Hour")

        # Intraday M5 for all assets
        update_dataset(api, symbol, oanda_symbol, "M5", "5_Min")

        # Special Case: Silver (XAG_USD) Intraday M3
        if symbol == "XAG_USD":
            print(f"  [Intraday] Fetching M3 for Silver...")
            update_dataset(api, symbol, oanda_symbol, "M3", "3_Min")
            
        # Rate limit kindness
        time.sleep(0.2)

if __name__ == "__main__":
    main()
