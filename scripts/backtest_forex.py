"""
Forex Strategy Backtester - Phase 6 (Power Filters)

Refines the 15m Trend Strategy with:
1. Volume Acceleration (>1.5x avg)
2. DI Momentum (>5.0 point jump)
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.forex_detector import ForexDetector

# Configuration
TEST_SYMBOLS = ['NQ=F', 'GC=F']
POSITION_SIZE = 1000.0
SPREAD_COST = 0.00015

def run_backtest(symbol, df):
    print(f"\nBacktesting {symbol} with POWER FILTERS...")
    df = TechnicalIndicators.add_all_indicators(df)
    
    trades = []
    position = None
    entry_price = 0.0
    entry_time = None
    
    for i in range(210, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i-1]
        
        # --- EXIT LOGIC ---
        if position:
            exit_signal = False
            if position == 'BUY':
                if current['Low'] <= current['EMA13'] or current['DIMinus'] > current['DIPlus']:
                    exit_signal = True
            elif position == 'SELL':
                if current['High'] >= current['EMA13'] or current['DIPlus'] > current['DIMinus']:
                    exit_signal = True
            
            if exit_signal:
                pnl = (current['Close'] - entry_price) / entry_price if position == 'BUY' else (entry_price - current['Close']) / entry_price
                pnl -= SPREAD_COST
                trades.append({'pnl_amount': pnl * POSITION_SIZE})
                position = None

        # --- ENTRY LOGIC (With Power Filters) ---
        if not position:
            # 1. Base Logic (ADX > 30, DI Crossover, Price > EMA34)
            is_buy_base = (current['ADX'] > 30 and current['DIPlus'] > current['DIMinus'] and 
                           prev['DIPlus'] <= prev['DIMinus'] and current['Close'] > current['EMA34'])
            is_sell_base = (current['ADX'] > 30 and current['DIMinus'] > current['DIPlus'] and 
                            prev['DIMinus'] <= prev['DIPlus'] and current['Close'] < current['EMA34'])
            
            if is_buy_base or is_sell_base:
                # 2. Volume Acceleration Filter (>1.5x avg of prev 5)
                avg_vol = df['Volume'].iloc[i-5:i].mean()
                vol_accel = current['Volume'] > (avg_vol * 1.5)
                
                # 3. DI Momentum Filter (Leading DI must jump > 5 pts in last 2 bars)
                if is_buy_base:
                    di_jump = current['DIPlus'] - df['DIPlus'].iloc[i-2]
                else:
                    di_jump = current['DIMinus'] - df['DIMinus'].iloc[i-2]
                
                di_momentum = di_jump > 5.0
                
                # APPLY POWER FILTERS
                if vol_accel and di_momentum:
                    position = 'BUY' if is_buy_base else 'SELL'
                    entry_price = current['Close']
                    entry_time = current.name

    return trades

def print_stats(trades):
    if not trades:
        print("No trades executed.")
        return
    df_t = pd.DataFrame(trades)
    wins = df_t[df_t['pnl_amount'] > 0]
    losses = df_t[df_t['pnl_amount'] <= 0]
    pf = wins['pnl_amount'].sum() / abs(losses['pnl_amount'].sum()) if len(losses) > 0 else float('inf')
    print(f"Total Trades: {len(df_t)}")
    print(f"Win Rate:     {len(wins)/len(df_t)*100:.2f}%")
    print(f"Profit Factor: {pf:.2f}")
    print(f"Net Profit:    ${df_t['pnl_amount'].sum():.2f}")

def main():
    for symbol in TEST_SYMBOLS:
        data_dir = PROJECT_ROOT / 'data' / 'forex_raw'
        df = pd.read_csv(data_dir / f"{symbol}.csv", header=[0, 1, 2], index_col=0)
        df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        trades = run_backtest(symbol, df)
        print_stats(trades)

if __name__ == "__main__":
    main()