"""
Sniper Strategy Dry Run Backtester
Simulates Trailing SL and Break-even logic per casket.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.sniper_detector import SniperDetector

CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
POSITION_SIZE = 1000.0
SPREAD_COST = 0.00015

def run_backtest(symbol, df_all):
    detector = SniperDetector()
    trades = []
    position = None
    entry_price = 0.0
    sl_price = 0.0
    initial_risk = 0.0
    is_breakeven = False
    
    df_all = TechnicalIndicators.add_all_indicators(df_all)
    df_all['EMA8'] = df_all['Close'].ewm(span=8, adjust=False).mean()
    
    for i in range(220, len(df_all)):
        current = df_all.iloc[i]
        
        if position:
            exit_signal = False
            final_price = current['Close']
            reward = (current['Close'] - entry_price) if position == 'BUY' else (entry_price - current['Close'])
            current_rr = reward / initial_risk if initial_risk > 0 else 0
            
            if not is_breakeven and current_rr >= 1.5:
                sl_price = entry_price
                is_breakeven = True
            
            if current_rr >= 2.0:
                if position == 'BUY': sl_price = max(sl_price, current['EMA8'])
                else: sl_price = min(sl_price, current['EMA8'])
            
            if position == 'BUY' and current['Low'] <= sl_price:
                exit_signal = True
                final_price = sl_price
            elif position == 'SELL' and current['High'] >= sl_price:
                exit_signal = True
                final_price = sl_price
            
            if exit_signal:
                pnl = (final_price - entry_price) / entry_price if position == 'BUY' else (entry_price - final_price) / entry_price
                trades.append({'pnl': pnl - SPREAD_COST, 'casket': detector.get_casket(symbol)})
                position = None

        if not position:
            window = df_all.iloc[i-220:i+1]
            analysis = detector.analyze(window, symbol)
            if analysis:
                position = analysis['signal']
                entry_price = analysis['price']
                sl_price = analysis['sl']
                initial_risk = abs(entry_price - sl_price)
                if initial_risk < entry_price * 0.0001: initial_risk = entry_price * 0.001
                is_breakeven = False

    return trades

def main():
    with open(CONFIG_PATH, 'r') as f:
        symbols = [p['symbol'] for p in json.load(f)['pairs']]
    
    all_trades = []
    print("Running Sniper Dry Run (Grouping Strategy)...")
    
    for symbol in symbols:
        data_path = PROJECT_ROOT / 'data' / 'forex_raw' / f"{symbol}.csv"
        if not data_path.exists(): continue
        try:
            df = pd.read_csv(data_path, header=[0, 1, 2], index_col=0)
            df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)
            trades = run_backtest(symbol, df)
            all_trades.extend(trades)
        except: continue

    if not all_trades:
        print("No trades generated.")
        return

    df_res = pd.DataFrame(all_trades)
    print("\n" + "="*60)
    print(f"{ 'CASKET':<12} | {'TRADES':<6} | {'WIN%':<8} | {'PF':<5} | {'NET Profit'}")
        total_net = df_res['pnl'].sum() * POSITION_SIZE
        print("-" * 60)
        print(f"{'TOTAL':<12} | {len(df_res):<6} | -        | -     | ${total_net:>10.2f}")
        print("="*60)