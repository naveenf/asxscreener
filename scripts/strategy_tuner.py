"""
Strategy Parameter Tuner - Final Precision Edition
Adding Entry-to-EMA proximity and Time-based exits.

"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators

def run_sim(symbol, df, adx_min, di_min_jump):
    df = TechnicalIndicators.add_all_indicators(df)
    df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()
    
    trades = []
    position = None
    entry_price = 0.0
    entry_idx = 0
    
    for i in range(210, len(df)):
        current = df.iloc[i]
        prev1 = df.iloc[i-1]
        prev2 = df.iloc[i-2]
        
        if position:
            exit_signal = False
            # 1. Trailing EMA8 Stop
            if position == 'BUY':
                if current['Low'] <= current['EMA8']: exit_signal = True
            elif position == 'SELL':
                if current['High'] >= current['EMA8']: exit_signal = True
            
            # 2. DI Reversal
            if position == 'BUY' and current['DIMinus'] > current['DIPlus']: exit_signal = True
            elif position == 'SELL' and current['DIPlus'] > current['DIMinus']: exit_signal = True
            
            # 3. Time Stop (12 bars = 3 hours)
            if i - entry_idx > 12: exit_signal = True
            
            if exit_signal:
                pnl = (current['Close'] - entry_price) / entry_price if position == 'BUY' else (entry_price - current['Close']) / entry_price
                trades.append(pnl - 0.00015)
                position = None

        if not position:
            is_bull = current['Close'] > current['EMA13'] > current['EMA34']
            is_bear = current['Close'] < current['EMA13'] < current['EMA34']
            
            if is_bull or is_bear:
                if current['ADX'] > adx_min and current['ADX'] > prev1['ADX'] > prev2['ADX']:
                    di_jump = (current['DIPlus'] - prev2['DIPlus']) if is_bull else (current['DIMinus'] - prev2['DIMinus'])
                    
                    # Entry Proximity Check (Price must be close to the EMA to ensure fresh move)
                    dist_to_ema = abs(current['Close'] - current['EMA13']) / current['Close']
                    
                    if di_jump > di_min_jump and dist_to_ema < 0.001: # Within 0.1%
                        position = 'BUY' if is_bull else 'SELL'
                        entry_price = current['Close']
                        entry_idx = i
    return trades

def main():
    data_dir = PROJECT_ROOT / 'data' / 'forex_raw'
    files = list(data_dir.glob('*.csv'))
    results = []
    for adx_t in [30, 35, 40]:
        for di_j in [8, 10, 12]:
            print(f"Testing ADX>{{adx_t}}, DI_Jump>{{di_j}}...")
            t_net, t_count = 0, 0
            for f in files:
                try:
                    df = pd.read_csv(f, header=[0, 1, 2], index_col=0)
                    df.columns = df.columns.get_level_values(0)
                    df.index = pd.to_datetime(df.index)
                    df.sort_index(inplace=True)
                    trades = run_sim(f.stem, df, adx_t, di_j)
                    t_net += sum(trades) * 1000
                    t_count += len(trades)
                except: continue
            results.append({'ADX': adx_t, 'DI_Jump': di_j, 'Net': round(t_net, 2), 'Trades': t_count})
    print("\n" + "="*40)
    print(pd.DataFrame(results).sort_values(by='Net', ascending=False))

if __name__ == "__main__":
    main()