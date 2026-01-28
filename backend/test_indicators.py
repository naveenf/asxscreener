"""Quick test of indicator calculations."""

import sys
from pathlib import Path

# Add project root and backend to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / 'backend'))

from app.services.indicators import load_and_calculate_indicators

# Test with Gold data (since we optimized for it)
csv_path = PROJECT_ROOT / 'data' / 'forex_raw' / 'XAU_USD_1_Hour.csv'

print(f"Loading {csv_path.name} data and calculating indicators...")
if not csv_path.exists():
    print(f"Error: {csv_path} not found.")
    sys.exit(1)

df = load_and_calculate_indicators(str(csv_path))

print(f"\nDataFrame shape: {df.shape}")
print(f"Columns: {list(df.columns)}")

# Show last 5 rows with indicators
indicators = ['Close', 'ADX', 'DIPlus', 'DIMinus', 'BB_Width', 'KC_Upper', 'Momentum']
print("\nLast 5 rows with indicators:")
print(df[indicators].tail())

# Check for any NaN values in recent data
recent = df.tail(50)
print(f"\nNaN count in last 50 rows:")
print(recent[indicators[1:]].isna().sum())

# Show a row where we have all indicators
valid_rows = df.dropna(subset=['ADX', 'BB_Width', 'KC_Upper', 'Momentum'])
print(f"\nValid rows with all indicators: {len(valid_rows)}/{len(df)}")

if len(valid_rows) > 0:
    print("\nSample row with all indicators:")
    sample = valid_rows.tail(1)
    print(f"Date: {sample.index[0]}")
    for ind in indicators:
        print(f"{ind}: {sample[ind].values[0]:.4f}")