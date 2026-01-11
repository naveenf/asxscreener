"""
Squeeze Strategy Multi-Timeframe Analysis

Running Squeeze Detector on the Final Portfolio.
Mapping YFinance file names to Oanda display names.
"""

import pandas as pd
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.squeeze_detector import SqueezeDetector

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
SPREAD_COST = 0.00015

# Asset Configuration: (YFinance_Key, Target_RR)
ASSET_CONFIG = {
    "XAG_USD":    ("SI=F", 3.0),
    "NAS100_USD": ("NQ=F", 3.0),
    "BCO_USD":    ("BZ=F", 3.0),
    "XCU_USD":    ("HG=F", 3.0),
    "USD_JPY":    ("USDJPY=X", 1.5),  # Forex -> 1.5
    "XAU_USD":    ("GC=F", 3.0),
    "LTC_USD":    ("LTC-USD", 3.0),
    "UK100_GBP":  ("^FTSE", 3.0),
    "JP225_USD":  ("^N225", 3.0),
    "WHEAT_USD":  ("ZW=F", 3.0),
    "SUGAR_USD":  ("SB=F", 3.0),
    "CORN_USD":   ("ZC=F", 3.0),
    "SOYBN_USD":  ("ZS=F", 3.0),
    "AUD_USD":    ("AUDUSD=X", 1.5),  # Forex -> 1.5
    "USD_CHF":    ("USDCHF=X", 1.5)   # Forex -> 1.5
}

def load_data(yf_symbol: str) -> Dict[str, pd.DataFrame]:
    data = {}
    files = {
        '15m': f"{yf_symbol}_15_Min.csv",
        '1h': f"{yf_symbol}_1_Hour.csv",
        '4h': f"{yf_symbol}_4_Hour.csv"
    }
    for tf, fname in files.items():
        path = DATA_DIR / fname
        if path.exists():
            try:
                df = pd.read_csv(path)
                col = 'Date' if 'Date' in df.columns else 'Datetime'
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True)
                    df.set_index(col, inplace=True)
                    df.sort_index(inplace=True)
                    data[tf] = df
            except Exception:
                pass
    return data

def run_test(symbol_display: str, base_tf: str, confirm_tf: str, data: Dict[str, pd.DataFrame], target_rr: float):
    df_base = data.get(base_tf)
    df_conf = data.get(confirm_tf)
    
    if df_base is None:
        return None

    detector = SqueezeDetector()
    trades = []
    position = None
    entry_price = 0.0
    stop_loss = 0.0
    
    # Analyze last 500 bars
    start_idx = max(50, len(df_base) - 500)
    
    for i in range(start_idx, len(df_base)):
        current_time = df_base.index[i]
        current_price = df_base['Close'].iloc[i]

        # --- EXIT ---
        if position:
            hit_stop = (position == 'BUY' and current_price <= stop_loss) or \
                       (position == 'SELL' and current_price >= stop_loss)
            
            risk = abs(entry_price - stop_loss)
            target = entry_price + (risk * target_rr if position == 'BUY' else -risk * target_rr)
            
            hit_target = (position == 'BUY' and current_price >= target) or \
                         (position == 'SELL' and current_price <= target)

            if hit_stop or hit_target:
                pnl = (stop_loss - entry_price) / entry_price if hit_stop else (target - entry_price) / entry_price
                if position == 'SELL': pnl = -pnl
                
                pnl -= SPREAD_COST
                trades.append(pnl)
                position = None
                continue

        # --- ENTRY ---
        if not position:
            slice_base = df_base.iloc[:i+1]
            simulated_data = {'15m': slice_base}
            
            if df_conf is not None:
                mask = df_conf.index < current_time
                slice_conf = df_conf[mask]
                if not slice_conf.empty:
                    simulated_data['1h'] = slice_conf

            try:
                signal = detector.analyze(simulated_data, symbol_display)
                if signal:
                    position = signal['signal']
                    entry_price = signal['price']
                    stop_loss = signal['stop_loss']
            except:
                pass

    if not trades:
        return {'count': 0, 'win_rate': 0.0, 'profit': 0.0}

    wins = len([t for t in trades if t > 0])
    total = len(trades)
    
    # 10x Leverage Profit simulation
    equity = 1000.0
    for t in trades:
        equity *= (1 + t * 10)
        
    return {
        'count': total,
        'win_rate': (wins/total)*100,
        'profit': ((equity - 1000)/1000)*100
    }

def main():
    print(f"\n⚡ SQUEEZE STRATEGY: 15m vs 1h (Mixed RR)")
    print("=" * 110)
    print(f"{ 'Asset':<12} | {'TF':<5} | {'Trades':<6} | {'Win Rate':<8} | {'Net Profit':<12} | {'Target RR':<12} | {'Status'}")
    print("-" * 110)

    for oanda_name, (yf_file_key, rr) in ASSET_CONFIG.items():
        data = load_data(yf_file_key)
        
        setups = [('15m', '1h'), ('1h', '4h')]
        
        has_data = False
        for base, conf in setups:
            res = run_test(oanda_name, base, conf, data, rr)
            
            if res:
                has_data = True
                status = "✅" if res['profit'] > 0 else "❌"
                if res['count'] < 3: status = "⚠️ (Low Data)"
                if res['profit'] > 50: status += " 🚀"
                
                print(f"{oanda_name:<12} | {base:<5} | {res['count']:<6} | {res['win_rate']:<6.1f}%  | {res['profit']:<12.1f}% | 1 : {rr:<3.1f}      | {status}")
        
        if not has_data:
             print(f"{oanda_name:<12} | NO DATA FOUND (Check YF Key: {yf_file_key})")
        
        print("-" * 110)

if __name__ == "__main__":
    main()