"""
NAS100 Highest RR Finder - Debug Version
"""

import pandas as pd
import numpy as np
from pathlib import Path
import sys

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.forex_detector import ForexDetector

def load_data(symbol):
    data_dir = PROJECT_ROOT / 'data' / 'forex_raw'
    csv_path = data_dir / f"{symbol}.csv"
    if not csv_path.exists(): return None
    df = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0)
    df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index)
    df.sort_index(inplace=True)
    return df

def analyze_max_rr(symbol, df):
    print(f"Analyzing {symbol} ({len(df)} rows)...")
    df = TechnicalIndicators.add_all_indicators(df)
    detector = ForexDetector(adx_threshold=20.0)
    
    trades = []
    position = None
    entry_price = 0.0
    entry_time = None
    initial_risk = 0.0
    
    print("Starting loop...")
    for i in range(210, len(df)):
        window = df.iloc[i-220:i+1].copy()
        current = df.iloc[i]
        
        if position:
            exit_signal = False
            final_price = current['Close']
            
            if position == 'BUY':
                if current['Low'] <= current['EMA13']:
                    exit_signal = True
                    final_price = current['EMA13']
                elif current['DIMinus'] > current['DIPlus']:
                    exit_signal = True
            elif position == 'SELL':
                if current['High'] >= current['EMA13']:
                    exit_signal = True
                    final_price = current['EMA13']
                elif current['DIPlus'] > current['DIMinus']:
                    exit_signal = True
            
            if exit_signal:
                reward = abs(final_price - entry_price)
                is_win = (final_price > entry_price and position == 'BUY') or (final_price < entry_price and position == 'SELL')
                rr = reward / initial_risk if initial_risk > 0 else 0
                
                trades.append({
                    'symbol': symbol, 'type': position, 'entry_time': entry_time, 'rr': rr,
                    'pnl_pct': (reward / entry_price) if is_win else -(reward / entry_price)
                })
                position = None

        if not position:
            analysis = detector.analyze(window, symbol, symbol, "Backtest")
            if analysis:
                position = analysis['signal']
                entry_price = current['Close']
                entry_time = current.name
                initial_risk = abs(entry_price - current['EMA13'])
                if initial_risk < entry_price * 0.0001: initial_risk = entry_price * 0.001

    print(f"Loop finished. Total trades found: {len(trades)}")
    if not trades: return

    df_trades = pd.DataFrame(trades)
    df_wins = df_trades[df_trades['pnl_pct'] > 0].sort_values(by='rr', ascending=False)
    
    print("\nTop 5 Captured Gains (Risk/Reward):")
    print("-" * 60)
    for idx, row in df_wins.head(5).iterrows():
        print(f"Time: {row['entry_time']} | Type: {row['type']} | RR: 1:{row['rr']:.2f} | Gain: {row['pnl_pct']*100:.2f}%")
    print("-" * 60)

def main():
    df = load_data('NQ=F')
    if df is not None:
        analyze_max_rr('NQ=F', df)

if __name__ == "__main__":
    main()
