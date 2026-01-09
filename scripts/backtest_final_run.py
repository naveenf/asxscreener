"""
Final Strategy Backtester - Full Universe
Uses the Final Optimized logic:
- Entry: ADX > 35 & Rising, EMA Stack, EMA Slope, DI Jump > 10, Proximity < 0.15%
- Exit: Trailing EMA8, DI Reversal, Time Stop (12 bars)
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import sys

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.forex_detector import ForexDetector

# Configuration
CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
POSITION_SIZE = 1000.0
SPREAD_COST = 0.00015

def load_symbols():
    with open(CONFIG_PATH, 'r') as f:
        return [p['symbol'] for p in json.load(f)['pairs']]

def run_backtest(symbol, df):
    df = TechnicalIndicators.add_all_indicators(df)
    # Add EMA8 for exit
    df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()
    
    detector = ForexDetector(adx_threshold=35.0)
    
    trades = []
    position = None
    entry_price = 0.0
    entry_time = None
    entry_idx = 0
    initial_risk = 0.0
    
    for i in range(210, len(df)):
        window = df.iloc[i-220:i+1].copy()
        current = df.iloc[i]
        
        # --- EXIT LOGIC ---
        if position:
            exit_signal = False
            reason = ""
            final_price = current['Close']
            
            # 1. Trailing EMA8
            if position == 'BUY' and current['Low'] <= current['EMA8']:
                exit_signal = True
                reason = "EMA8 Stop"
                final_price = current['EMA8']
            elif position == 'SELL' and current['High'] >= current['EMA8']:
                exit_signal = True
                reason = "EMA8 Stop"
                final_price = current['EMA8']
            
            # 2. DI Reversal
            if not exit_signal:
                if position == 'BUY' and current['DIMinus'] > current['DIPlus']:
                    exit_signal = True
                    reason = "DI Reversal"
                elif position == 'SELL' and current['DIPlus'] > current['DIMinus']:
                    exit_signal = True
                    reason = "DI Reversal"
            
            # 3. Time Stop (12 bars)
            if not exit_signal and (i - entry_idx) >= 12:
                exit_signal = True
                reason = "Time Stop"
            
            if exit_signal:
                pnl = (final_price - entry_price) / entry_price if position == 'BUY' else (entry_price - final_price) / entry_price
                pnl -= SPREAD_COST
                reward = abs(final_price - entry_price)
                rr = reward / initial_risk if initial_risk > 0 else 0
                
                trades.append({
                    'pnl_amount': pnl * POSITION_SIZE,
                    'is_win': pnl > 0,
                    'rr': rr
                })
                position = None

        # --- ENTRY LOGIC ---
        if not position:
            analysis = detector.analyze(window, symbol, symbol, "Backtest")
            if analysis:
                position = analysis['signal']
                entry_price = current['Close']
                entry_time = current.name
                entry_idx = i
                # Calculate initial risk based on EMA13 at entry
                initial_risk = abs(entry_price - current['EMA13'])
                if initial_risk < entry_price * 0.0001:
                    initial_risk = entry_price * 0.001

    return trades

def main():
    symbols = load_symbols()
    all_results = []
    
    print(f"Running Final Optimized Backtest on {len(symbols)} symbols...")
    
    for symbol in symbols:
        data_path = PROJECT_ROOT / 'data' / 'forex_raw' / f"{symbol}.csv"
        if not data_path.exists(): continue
        
        try:
            df = pd.read_csv(data_path, header=[0, 1, 2], index_col=0)
            df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)
            
            trades = run_backtest(symbol, df)
            
            if trades:
                df_t = pd.DataFrame(trades)
                win_rate = (df_t['is_win'].sum() / len(df_t)) * 100
                net_profit = df_t['pnl_amount'].sum()
                avg_rr = df_t[df_t['is_win']]['rr'].mean()
                
                all_results.append({
                    'Symbol': symbol,
                    'Trades': len(df_t),
                    'WinRate': win_rate,
                    'Avg_Win_RR': avg_rr,
                    'Net': net_profit
                })
        except Exception as e:
            continue

    if not all_results:
        print("No trades generated with the current strict criteria.")
        return

    results_df = pd.DataFrame(all_results).sort_values(by='Net', ascending=False)
    
    print("\n" + "="*75)
    print(f"{ 'SYMBOL':<10} | {'TRADES':<6} | {'WIN%':<8} | {'AVG WIN RR':<10} | {'NET PROFIT':<10}")
    print("-" * 75)
    for _, row in results_df.iterrows():
        avg_rr_str = f"1:{row['Avg_Win_RR']:.2f}" if not np.isnan(row['Avg_Win_RR']) else "N/A"
        print(f"{row['Symbol']:<10} | {int(row['Trades']):<6} | {row['WinRate']:>6.1f}% | {avg_rr_str:<10} | ${row['Net']:>10.2f}")
    
    total_net = results_df['Net'].sum()
    print("-" * 75)
    print(f"{ 'TOTAL':<10} | {int(results_df['Trades'].sum()):<6} | {'-':<8} | {'-':<10} | ${total_net:>10.2f}")
    print("="*75)

if __name__ == "__main__":
    main()
