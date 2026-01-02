"""Quick test of indicator calculations."""

import sys
sys.path.insert(0, '/mnt/d/VSProjects/Stock Scanner/asx-screener/backend')

from app.services.indicators import load_and_calculate_indicators

# Test with CBA stock data
csv_path = '/mnt/d/VSProjects/Stock Scanner/asx-screener/data/raw/CBA.AX.csv'

print("Loading CBA.AX data and calculating indicators...")
df = load_and_calculate_indicators(csv_path)

print(f"\nDataFrame shape: {df.shape}")
print(f"Columns: {list(df.columns)}")

# Show last 5 rows with indicators
print("\nLast 5 rows with indicators:")
print(df[['Close', 'ADX', 'DIPlus', 'DIMinus', 'SMA200']].tail())

# Check for any NaN values in recent data
recent = df.tail(50)
print(f"\nNaN count in last 50 rows:")
print(recent[['ADX', 'DIPlus', 'DIMinus', 'SMA200']].isna().sum())

# Show a row where we have all indicators
valid_rows = df.dropna(subset=['ADX', 'DIPlus', 'DIMinus', 'SMA200'])
print(f"\nValid rows with all indicators: {len(valid_rows)}/{len(df)}")

if len(valid_rows) > 0:
    print("\nSample row with all indicators:")
    sample = valid_rows.tail(1)
    print(f"Date: {sample.index[0]}")
    print(f"Close: {sample['Close'].values[0]:.2f}")
    print(f"ADX: {sample['ADX'].values[0]:.2f}")
    print(f"DI+: {sample['DIPlus'].values[0]:.2f}")
    print(f"DI-: {sample['DIMinus'].values[0]:.2f}")
    print(f"SMA200: {sample['SMA200'].values[0]:.2f}")
