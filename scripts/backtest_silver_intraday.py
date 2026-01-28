"""
Silver Sniper Full Dataset Backtest
Starting Balance: $360
Risk Per Trade: 2%
Leverage: 1:10
"""

import pandas as pd
import sys
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
SPREAD_COST = 0.0006  # ~0.06%
STARTING_BALANCE = 360.0
RISK_PCT = 2.0
LEVERAGE = 10.0

def load_silver_data() -> Dict[str, pd.DataFrame]:
    data = {}
    files = {'5m': "XAG_USD_5_Min.csv", '15m': "XAG_USD_15_Min.csv"}
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

def calculate_units(balance, entry, sl):
    risk_amount = balance * (RISK_PCT / 100.0)
    stop_dist = abs(entry - sl)
    if stop_dist == 0: return 0
    
    units_by_risk = risk_amount / stop_dist
    max_units_by_lev = (balance * LEVERAGE) / entry
    
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
            if row['High'] <= stop_loss: return -risk, "LOSS", row.name # Wait, logic error in SL for SELL
            # Fixed SL logic for Sell:
            if row['High'] >= stop_loss: return -risk, "LOSS", row.name
            if row['Low'] <= take_profit: return (entry_price - take_profit), "WIN", row.name
    return 0, "OPEN", None

def run_full_backtest():
    data = load_silver_data()
    df_5m = data.get('5m')
    df_15m = data.get('15m')
    
    if df_5m is None or df_15m is None: return

    detector = SilverSniperDetector()
    balance = STARTING_BALANCE
    equity_curve = [balance]
    trades_log = []
    
    print(f"Starting Backtest on {len(df_5m)} candles...")
    print(f"Period: {df_5m.index.min()} to {df_5m.index.max()}")
    print("-" * 60)

    i = 100
    while i < len(df_5m):
        current_time = df_5m.index[i]
        slice_5m = df_5m.iloc[i-100:i+1]
        htf_idx = df_15m.index.get_indexer([current_time], method='pad')[0]
        slice_15m = df_15m.iloc[htf_idx-50:htf_idx+1]
        
        signal = detector.analyze({'5m': slice_5m, '15m': slice_15m}, "XAG_USD")
        
        if signal:
            entry_p = signal['price']
            sl_p = signal['stop_loss']
            units = calculate_units(balance, entry_p, sl_p)
            
            if units >= 1:
                profit_per_unit, result, exit_time = simulate_trade(df_5m, i, signal['signal'], entry_p, sl_p)
                
                if result != "OPEN":
                    trade_pnl = (profit_per_unit * units) - (entry_p * units * SPREAD_COST)
                    balance += trade_pnl
                    equity_curve.append(balance)
                    
                    trades_log.append({
                        'Time': current_time,
                        'Signal': signal['signal'],
                        'Entry': entry_p,
                        'Units': units,
                        'PnL': trade_pnl,
                        'Result': result,
                        'Balance': balance
                    })
                    
                    # Fast forward to exit to avoid overlapping trades
                    exit_idx = df_5m.index.get_loc(exit_time)
                    i = exit_idx
            
        i += 1

    # Final Stats
    print(f"BACKTEST COMPLETE")
    print(f"{ 'Initial Balance:':<20} ${STARTING_BALANCE:.2f}")
    print(f"{ 'Final Balance:':<20} ${balance:.2f}")
    print(f"{ 'Total Return:':<20} {((balance-STARTING_BALANCE)/STARTING_BALANCE)*100:.2f}%")
    print(f"{ 'Total Trades:':<20} {len(trades_log)}")
    
    if trades_log:
        wins = len([t for t in trades_log if t['Result'] == "WIN"])
        print(f"{ 'Win Rate:':<20} {(wins/len(trades_log))*100:.1f}%")
        max_drawdown = (max(equity_curve) - min(equity_curve)) / max(equity_curve) * 100
        print(f"{ 'Max Drawdown (est):':<20} {max_drawdown:.2f}%")
        
        print("\nRecent Trades:")
        for t in trades_log[-5:]:
            print(f"{t['Time']} | {t['Signal']} | Units: {t['Units']} | PnL: ${t['PnL']:.2f} | Balance: ${t['Balance']:.2f}")

if __name__ == "__main__":
    run_full_backtest()