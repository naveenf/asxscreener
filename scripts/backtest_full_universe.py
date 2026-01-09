"""
Full Universe Forex Backtester - Ultra Filter Edition
Tightens filters and SL to minimize noisy losses.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.forex_detector import ForexDetector

CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
POSITION_SIZE = 1000.0
SPREAD_COST = 0.00015

def run_backtest(symbol, df):
    df = TechnicalIndicators.add_all_indicators(df)
    # Add EMA8 for tighter trailing stop
    df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()
    
    detector = ForexDetector(adx_threshold=30.0)
    
    trades = []
    position = None
    entry_price = 0.0
    entry_time = None
    
    for i in range(210, len(df)):
        window = df.iloc[i-220:i+1].copy()
        current = df.iloc[i]
        
        # --- TIGHTER EXIT LOGIC ---
        if position:
            exit_signal = False
            if position == 'BUY':
                # Exit on EMA8 break OR DI reversal
                if current['Low'] <= current['EMA8'] or current['DIMinus'] > current['DIPlus']:
                    exit_signal = True
            elif position == 'SELL':
                if current['High'] >= current['EMA8'] or current['DIPlus'] > current['DIMinus']:
                    exit_signal = True
            
            if exit_signal:
                pnl = (current['Close'] - entry_price) / entry_price if position == 'BUY' else (entry_price - current['Close']) / entry_price
                pnl -= SPREAD_COST
                trades.append({'pnl_amount': pnl * POSITION_SIZE})
                position = None

        # --- ULTRA ENTRY LOGIC ---
        if not position:
            analysis = detector.analyze(window, symbol, symbol, "Backtest")
            if analysis:
                position = analysis['signal']
                entry_price = current['Close']
                entry_time = current.name

    return trades

def main():
    with open(CONFIG_PATH, 'r') as f:
        symbols = [p['symbol'] for p in json.load(f)['pairs']]
    
    all_results = []
    print(f"Starting Ultra Backtest...")
    
    for symbol in symbols:
        data_path = PROJECT_ROOT / 'data' / 'forex_raw' / f"{symbol}.csv"
        if not data_path.exists(): continue
        
        df = pd.read_csv(data_path, header=[0, 1, 2], index_col=0)
        df.columns = df.columns.get_level_values(0)
        df.index = pd.to_datetime(df.index)
        df.sort_index(inplace=True)
        
        trades = run_backtest(symbol, df)
        if trades:
            df_t = pd.DataFrame(trades)
            wins = df_t[df_t['pnl_amount'] > 0]
            losses = df_t[df_t['pnl_amount'] <= 0]
            pf = wins['pnl_amount'].sum() / abs(losses['pnl_amount'].sum()) if len(losses) > 0 else float('inf')
            all_results.append({
                'Symbol': symbol, 'Trades': len(df_t), 
                'WinRate': f"{len(wins)/len(df_t)*100:.1f}%", 
                'PF': round(pf, 2), 'Net': round(df_t['pnl_amount'].sum(), 2)
            })

    results_df = pd.DataFrame(all_results).sort_values(by='PF', ascending=False)
    print("\n" + "="*65)
    print(f"{'SYMBOL':<10} | {'TRADES':<6} | {'WIN%':<8} | {'PF':<5} | {'NET PROFIT':<10}")
    print("-" * 65)
    for _, row in results_df.iterrows():
        print(f"{row['Symbol']:<10} | {row['Trades']:<6} | {row['WinRate']:<8} | {row['PF']:<5} | ${row['Net']:<10}")
    print("="*65)