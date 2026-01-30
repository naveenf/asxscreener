"""
Winners Detailed Analysis
Extracts indicator and volume values for the top RR trades.
"""

import pandas as pd
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators

def analyze_win(symbol, timestamp, label):
    data_dir = PROJECT_ROOT / 'data' / 'forex_raw'
    csv_path = data_dir / f"{symbol}_15_Min.csv"
    
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return

    try:
        df = pd.read_csv(csv_path)
        col = 'Date' if 'Date' in df.columns else 'Datetime'
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
            df.set_index(col, inplace=True)
        df.sort_index(inplace=True)
        
        df = TechnicalIndicators.add_all_indicators(df)
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")
        return
    
    # Target timestamp
    ts = pd.to_datetime(timestamp)
    if ts not in df.index:
        # Find closest
        ts = df.index[df.index.get_indexer([ts], method='nearest')[0]]
    
    idx = df.index.get_loc(ts)
    # Get 5 bars before and 2 after
    window = df.iloc[idx-5 : idx+3]
    
    print(f"\n--- Analysis for {label} ({ts}) ---")
    print(f"{ 'Time':<20} | {'Close':<10} | {'ADX':<6} | {'DI+':<6} | {'DI-':<6} | {'Volume':<10}")
    print("-" * 75)
    for t, row in window.iterrows():
        mark = ">> ENTRY <<" if t == ts else ""
        print(f"{str(t.time()):<20} | {row['Close']:<10.2f} | {row['ADX']:<6.1f} | {row['DIPlus']:<6.1f} | {row['DIMinus']:<6.1f} | {row['Volume']:<10.0f} {mark}")

def main():
    # NAS100 Winners
    analyze_win('NAS100_USD', '2025-11-06 14:00:00+00:00', "8.7 RR SELL")
    analyze_win('NAS100_USD', '2026-01-06 01:15:00+00:00', "3.2 RR BUY")
    analyze_win('NAS100_USD', '2025-11-03 08:45:00+00:00', "2.2 RR BUY")

if __name__ == "__main__":
    main()
