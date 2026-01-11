"""
One-time bulk download of maximum historical forex data.
Downloads 'max' period (up to 42 days of 15m data) for all forex pairs.
"""

import yfinance as yf
import pandas as pd
import json
import time
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'

DATA_DIR.mkdir(parents=True, exist_ok=True)

def load_forex_pairs():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)['pairs']

def download_max_data(symbol, name):
    """Download maximum available 15m data (up to 42 days)."""
    output_file = DATA_DIR / f"{symbol}.csv"

    print(f"[+] Downloading MAX 15m data for {name} ({symbol})...")

    try:
        # Download maximum available period
        # Yahoo Finance limits 15m data to last 60 days, max available is ~42 days
        df = yf.download(symbol, period="max", interval="15m", progress=False)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            print(f" [!] No data found for {symbol}")
            return False, 0

        # Handle MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Normalize timezone
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Save to CSV
        df.to_csv(output_file)

        rows = len(df)
        days = rows / 96  # 96 x 15m bars per day

        print(f" [✓] Downloaded {rows} rows (~{days:.1f} days) for {symbol}")
        return True, rows

    except Exception as e:
        print(f" [!] Error downloading {symbol}: {e}")
        return False, 0

def main():
    if not CONFIG_PATH.exists():
        print(f"Error: Config not found at {CONFIG_PATH}")
        return

    pairs = load_forex_pairs()
    success = 0
    total_rows = 0

    print("="*70)
    print("BULK DOWNLOAD: Maximum Historical Forex Data")
    print("="*70)
    print(f"Symbols: {len(pairs)}")
    print(f"Interval: 15m")
    print(f"Period: max (~42 days available)")
    print("="*70)

    for pair in pairs:
        ok, rows = download_max_data(pair['symbol'], pair['name'])
        if ok:
            success += 1
            total_rows += rows

        # Be nice to Yahoo API
        time.sleep(0.5)

    print("="*70)
    print(f"Finished: {success}/{len(pairs)} symbols downloaded")
    print(f"Total bars: {total_rows:,} (~{total_rows/96:.1f} instrument-days)")
    print("="*70)

if __name__ == "__main__":
    main()
