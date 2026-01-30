import pandas as pd
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.squeeze_detector import SqueezeDetector
from backend.app.services.indicators import TechnicalIndicators

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'

# Assets to test (Excluding Sniper assets XAG, BCO, WHEAT)
TEST_ASSETS = [
    "XAU_USD", "NAS100_USD", "JP225_USD", "UK100_GBP",
    "USD_JPY", "AUD_USD", "USD_CHF", "XCU_USD"
]

def load_data_and_prep(symbol: str) -> Dict[str, pd.DataFrame]:
    data = {}
    files = {'1h': f"{symbol}_1_Hour.csv", '4h': f"{symbol}_4_Hour.csv"}
    for tf, fname in files.items():
        path = DATA_DIR / fname
        if path.exists():
            df = pd.read_csv(path)
            col = 'Date' if 'Date' in df.columns else 'Datetime'
            df[col] = pd.to_datetime(df[col], utc=True)
            df.set_index(col, inplace=True)
            df.sort_index(inplace=True)
            # CRITICAL: Calculate indicators ONCE
            df = TechnicalIndicators.add_all_indicators(df)
            data[tf] = df
    return data

def run_fast_test(symbol: str, data: Dict[str, pd.DataFrame], target_rr: float):
    df_base = data.get('1h')
    df_htf = data.get('4h')
    
    if df_base is None: return 0.0
    
    detector = SqueezeDetector()
    trades = []
    
    # Pre-calculated indicators are in df_base and df_htf
    for i in range(100, len(df_base)):
        current_time = df_base.index[i]
        
        # Detector still needs a slice, but analyze() will re-add indicators if not careful.
        # However, SqueezeDetector.analyze calls TechnicalIndicators.add_all_indicators(df)
        # which checks if columns exist before re-calculating (usually).
        # Let's trust the pre-calculated ones if possible.
        
        slice_base = df_base.iloc[i-50:i+1]
        
        htf_idx_list = df_htf.index.get_indexer([current_time], method='pad')
        htf_idx = htf_idx_list[0]
        if htf_idx < 20: continue
        slice_htf = df_htf.iloc[htf_idx-20:htf_idx+1]
        
        signal = detector.analyze({'base': slice_base, 'htf': slice_htf}, symbol, target_rr=target_rr)
        
        if signal:
            sl_p = signal['stop_loss']
            tp_p = signal['take_profit']
            pos = signal['signal']
            
            # Fast outcome check
            outcome = 0
            for j in range(i+1, len(df_base)):
                row = df_base.iloc[j]
                if pos == 'BUY':
                    if row['Low'] <= sl_p: outcome = -1; break
                    if row['High'] >= tp_p: outcome = 1; break
                else:
                    if row['High'] >= sl_p: outcome = -1; break
                    if row['Low'] <= tp_p: outcome = 1; break
            
            if outcome != 0:
                pnl = (target_rr if outcome == 1 else -1.0)
                pnl -= 0.1 # Cost
                trades.append(pnl)

    return sum(trades) if trades else 0.0

def main():
    print(f"{'Symbol':<12} | RR 1.5 Profit | RR 2.0 Profit | RR 3.0 Profit | BEST")
    print("-" * 75)
    
    for asset in TEST_ASSETS:
        data = load_data_and_prep(asset)
        if not data: continue
        
        results = {}
        for rr in [1.5, 2.0, 3.0]:
            pnl = run_fast_test(asset, data, rr)
            results[rr] = pnl
            
        best_rr = max(results, key=results.get)
        print(f"{asset:<12} | {results[1.5]:>12.1f} | {results[2.0]:>12.1f} | {results[3.0]:>12.1f} | {best_rr}")

if __name__ == "__main__":
    main()