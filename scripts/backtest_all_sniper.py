"""
Multi-Asset Sniper Backtest
Testing SilverSniper Strategy across all commodities/forex.
"""

import pandas as pd
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.silver_sniper_detector import SilverSniperDetector
from backend.app.services.indicators import TechnicalIndicators

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
SPREAD_COST = 0.0006 
STARTING_BALANCE = 360.0
RISK_PCT = 2.0
LEVERAGE = 10.0

def load_asset_data(symbol: str) -> Dict[str, pd.DataFrame]:
    data = {}
    files = {'5m': f"{symbol}_5_Min.csv", '15m': f"{symbol}_15_Min.csv"}
    for tf, fname in files.items():
        path = DATA_DIR / fname
        if path.exists():
            df = pd.read_csv(path)
            col = 'Date' if 'Date' in df.columns else 'Datetime'
            df[col] = pd.to_datetime(df[col], utc=True)
            df.set_index(col, inplace=True)
            df.sort_index(inplace=True)
            df = TechnicalIndicators.add_all_indicators(df)
            data[tf] = df
    return data

def calculate_units(balance, entry, sl, leverage):
    risk_amount = balance * (RISK_PCT / 100.0)
    stop_dist = abs(entry - sl)
    if stop_dist == 0: return 0
    
    units_by_risk = risk_amount / stop_dist
    max_units_by_lev = (balance * leverage) / entry
    
    return int(min(units_by_risk, max_units_by_lev))

def simulate_trade(df_base, entry_idx, position, entry_price, stop_loss, target_rr=3.0):
    risk = abs(entry_price - stop_loss)
    take_profit = entry_price + (risk * target_rr if position == 'BUY' else -risk * target_rr)
    
    for i in range(entry_idx + 1, len(df_base)):
        row = df_base.iloc[i]
        if position == 'BUY':
            if row['Low'] <= stop_loss: return -risk, "LOSS", row.name
            if row['High'] >= take_profit: return (take_profit - entry_price), "WIN", row.name
        else:
            if row['High'] >= stop_loss: return -risk, "LOSS", row.name
            if row['Low'] <= take_profit: return (entry_price - take_profit), "WIN", row.name
    return 0, "OPEN", None

def run_backtest(symbol: str):
    data = load_asset_data(symbol)
    df_5m = data.get('5m')
    df_15m = data.get('15m')
    
    if df_5m is None or df_15m is None: return None

    detector = SilverSniperDetector()
    balance = STARTING_BALANCE
    trades_log = []
    
    i = 100
    while i < len(df_5m):
        current_time = df_5m.index[i]
        slice_5m = df_5m.iloc[i-100:i+1]
        
        htf_idx_list = df_15m.index.get_indexer([current_time], method='pad')
        htf_idx = htf_idx_list[0]
        if htf_idx < 20: 
            i += 1
            continue
            
        slice_15m = df_15m.iloc[htf_idx-50:htf_idx+1]
        
        signal = detector.analyze({'5m': slice_5m, '15m': slice_15m}, symbol)
        
        if signal:
            entry_p = signal['price']
            sl_p = signal['stop_loss']
            units = calculate_units(balance, entry_p, sl_p, LEVERAGE)
            
            if units >= 1:
                profit_per_unit, result, exit_time = simulate_trade(df_5m, i, signal['signal'], entry_p, sl_p)
                
                if result != "OPEN":
                    trade_pnl = (profit_per_unit * units) - (entry_p * units * SPREAD_COST)
                    balance += trade_pnl
                    
                    trades_log.append(result)
                    
                    # Fast forward
                    exit_idx = df_5m.index.get_loc(exit_time)
                    i = exit_idx
            
        i += 1

    if not trades_log: return None
    
    wins = trades_log.count("WIN")
    win_rate = (wins / len(trades_log)) * 100
    total_return = ((balance - STARTING_BALANCE) / STARTING_BALANCE) * 100
    
    return {
        'Symbol': symbol,
        'Trades': len(trades_log),
        'Win Rate': f"{win_rate:.1f}%",
        'Return': f"{total_return:.2f}%",
        'Profit': round(balance - STARTING_BALANCE, 2)
    }

def main():
    # Identify all assets by checking for 5_Min files
    assets = []
    for f in os.listdir(DATA_DIR):
        if f.endswith("_5_Min.csv"):
            symbol = f.replace("_5_Min.csv", "")
            assets.append(symbol)
    
    print(f"Running Sniper Backtest on {len(assets)} assets...")
    print(f"{'Symbol':<12} | {'Trades':<6} | {'Win Rate':<8} | {'Return %':<10} | {'Profit $'}")
    print("-" * 60)
    
    results = []
    for asset in sorted(assets):
        res = run_backtest(asset)
        if res:
            results.append(res)
            print(f"{res['Symbol']:<12} | {res['Trades']:<6} | {res['Win Rate']:<8} | {res['Return']:<10} | ${res['Profit']}")
        else:
            print(f"{asset:<12} | 0      | N/A      | 0.00%      | $0.0")

if __name__ == "__main__":
    main()
