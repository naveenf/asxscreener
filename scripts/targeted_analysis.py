"""
Targeted Analysis Script

Specific backtest to answer user query:
1. Efficacy of algos on major pairs.
2. Profitability %.
3. Viability of 1:3 Risk:Reward.
4. Frequency check (Target: 2-4 trades/day).
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.strategy_interface import ForexStrategy
from backend.app.services.sniper_detector import SniperDetector
from backend.app.services.triple_trend_detector import TripleTrendDetector
from backend.app.services.forex_detector import ForexDetector
from backend.app.services.squeeze_detector import SqueezeDetector

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
SPREAD_COST = 0.00015
TARGET_RR = 3.0  # Testing the user's requested 1:3 ratio
SELECTED_PAIRS = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'GC=F', 'BTC-USD']

def load_mtf_data(symbol: str) -> Dict[str, pd.DataFrame]:
    data = {}
    files = {
        '15m': f"{symbol}_15_Min.csv",
        '1h': f"{symbol}_1_Hour.csv",
        '4h': f"{symbol}_4_Hour.csv"
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

def run_simulation(strategy: ForexStrategy, data: Dict[str, pd.DataFrame], symbol: str):
    df_15m = data.get('15m')
    if df_15m is None or len(df_15m) < 200:
        return None

    trades = []
    position = None
    entry_price = 0.0
    stop_loss = 0.0
    
    # Analyze last 1000 bars (or max available) to get a good sample
    start_idx = max(50, len(df_15m) - 1000)
    
    # Calculate days in sample for frequency
    start_date = df_15m.index[start_idx]
    end_date = df_15m.index[-1]
    days = (end_date - start_date).days
    if days < 1: days = 1

    for i in range(start_idx, len(df_15m)):
        current_time = df_15m.index[i]
        
        # --- EXIT LOGIC ---
        if position:
            current_price = df_15m['Close'].iloc[i]
            
            # Stop Loss
            hit_stop = (position == 'BUY' and current_price <= stop_loss) or \
                       (position == 'SELL' and current_price >= stop_loss)
            
            # Profit Target (1:3 RR)
            risk = abs(entry_price - stop_loss)
            target = entry_price + (risk * TARGET_RR if position == 'BUY' else -risk * TARGET_RR)
            hit_target = (position == 'BUY' and current_price >= target) or \
                         (position == 'SELL' and current_price <= target)
            
            if hit_stop or hit_target:
                exit_price = stop_loss if hit_stop else target
                # Calculate % PnL
                pnl_pct = (exit_price - entry_price) / entry_price if position == 'BUY' else \
                          (entry_price - exit_price) / entry_price
                
                # Apply spread approximation
                pnl_pct -= SPREAD_COST
                
                trades.append({
                    'pnl': pnl_pct,
                    'result': 'WIN' if pnl_pct > 0 else 'LOSS',
                    'rr': TARGET_RR if hit_target else -1.0
                })
                position = None
                continue

        # --- ENTRY LOGIC ---
        if not position:
            # Prepare slice
            slice_data = {}
            start_window = max(0, i - 100)
            slice_data['15m'] = df_15m.iloc[start_window:i+1]
            
            for tf in ['1h', '4h']:
                if tf in data:
                    htf = data[tf]
                    # Filter for closed candles
                    mask = htf.index < current_time
                    relevant_htf = htf[mask]
                    if len(relevant_htf) > 50:
                        slice_data[tf] = relevant_htf.iloc[-50:]
                    else:
                        slice_data[tf] = relevant_htf

            try:
                signal = strategy.analyze(slice_data, symbol)
                if signal and signal.get('signal'):
                    position = signal['signal']
                    entry_price = signal['price']
                    # Use strategy stop or tight default
                    stop_loss = signal.get('stop_loss', entry_price * (0.995 if position == 'BUY' else 1.005))
            except Exception:
                pass

    if not trades:
        return None

    # Stats
    df_trades = pd.DataFrame(trades)
    wins = df_trades[df_trades['pnl'] > 0]
    total_trades = len(df_trades)
    win_rate = len(wins) / total_trades * 100
    
    # Assume $1000 per trade
    equity = 1000.0
    for pnl in df_trades['pnl']:
        equity *= (1 + pnl * 10) # 10x leverage simulation for meaningful %
        
    net_profit_pct = (equity - 1000.0) / 1000.0 * 100
    
    return {
        'total_trades': total_trades,
        'trades_per_day': round(total_trades / days, 1),
        'win_rate': round(win_rate, 1),
        'net_profit_pct_leveraged': round(net_profit_pct, 1),
        'days': days
    }

def main():
    strategies = [
        SniperDetector(),
        TripleTrendDetector(),
        ForexDetector(),
        SqueezeDetector()
    ]
    
    print(f"\n🔬 TARGETED ANALYSIS (Risk:Reward = 1:{TARGET_RR})")
    print("=" * 80)
    print(f"{ 'Pair':<10} | { 'Strategy':<15} | { 'Trades':<6} | { 'Freq/Day':<8} | { 'Win%':<6} | { 'Profit% (10x)':<12}")
    print("-" * 80)

    for symbol in SELECTED_PAIRS:
        data = load_mtf_data(symbol)
        if '15m' not in data:
            print(f"{symbol:<10} | NO DATA")
            continue
            
        for strat in strategies:
            res = run_simulation(strat, data, symbol)
            if res:
                # Highlight if matches user criteria (approx)
                freq_ok = 0.5 <= res['trades_per_day'] <= 5.0
                profitable = res['net_profit_pct_leveraged'] > 0
                
                marker = "✨" if (freq_ok and profitable) else "  "
                
                print(f"{symbol:<10} | {strat.get_name():<15} | {res['total_trades']:<6} | {res['trades_per_day']:<8} | {res['win_rate']:<6} | {res['net_profit_pct_leveraged']:<12} {marker}")
    
    print("=" * 80)
    print("Note: Profit% assumes 10x leverage. Freq/Day is avg over available data.")

if __name__ == "__main__":
    main()
