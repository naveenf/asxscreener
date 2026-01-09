import yfinance as yf
import pandas as pd
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'

DATA_DIR.mkdir(parents=True, exist_ok=True)

def load_forex_pairs():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)['pairs']

def is_data_stale(file_path):
    if not os.path.exists(file_path):
        return True
    
    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
    # If file is older than 15 minutes, it's stale
    return datetime.now() - file_time > timedelta(minutes=15)

def download_forex_data(symbol, name):
    output_file = DATA_DIR / f"{symbol}.csv"
    
    if not is_data_stale(output_file):
        print(f"[-] Data for {name} ({symbol}) is still fresh. Skipping.")
        return True

    print(f"[+] Downloading 15m data for {name} ({symbol})...")
    try:
        # yfinance 15m data is limited to 60 days
        df = yf.download(symbol, period="60d", interval="15m", progress=False)
        
        if df is None or df.empty:
            print(f" [!] No data found for {symbol}")
            return False
            
        df.to_csv(output_file)
        return True
    except Exception as e:
        print(f" [!] Error downloading {symbol}: {e}")
        return False

def main():
    if not CONFIG_PATH.exists():
        print(f"Error: Config not found at {CONFIG_PATH}")
        return

    pairs = load_forex_pairs()
    success = 0
    
    print(f"Starting Forex/Commodity data download ({len(pairs)} symbols)")
    print(f"Target interval: 15m | Refresh threshold: 15m")
    
    for pair in pairs:
        if download_forex_data(pair['symbol'], pair['name']):
            success += 1
        # Small delay to be nice to Yahoo
        time.sleep(0.5)
        
    print(f"\nFinished. Successfully updated {success}/{len(pairs)} symbols.")

if __name__ == "__main__":
    main()