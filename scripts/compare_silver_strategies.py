
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from typing import Dict, List, Optional
from tqdm import tqdm

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.sniper_detector import SniperDetector
from backend.app.services.silver_sniper_detector import SilverSniperDetector

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
SYMBOL = 'XAG_USD'
SPREAD = 0.025 # Approx spread for Silver
TARGET_RR = 3.0

def load_data(symbol: str) -> Dict[str, pd.DataFrame]:
    data = {}
    files = {
        '5m': f"{symbol}_5_Min.csv",
        '15m': f"{symbol}_15_Min.csv",
        '1h': f"{symbol}_1_Hour.csv"
    }
    
    for tf, fname in files.items():
        path = DATA_DIR / fname
        if path.exists():
            try:
                df = pd.read_csv(path)
                # Standardize
                col = 'Date' if 'Date' in df.columns else 'Datetime'
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], utc=True)
                    df.set_index(col, inplace=True)
                    df.sort_index(inplace=True)
                    data[tf] = df
            except Exception as e:
                print(f"Error loading {fname}: {e}")
    return data

def run_backtest(strategy, data: Dict[str, pd.DataFrame], symbol: str):
    df_base = data.get('5m') # Driver
    if df_base is None:
        print("No 5m data found.")
        return {}

    trades = []
    position = None # 'BUY' or 'SELL'
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    
    equity = 10000.0
    equity_curve = [equity]
    
    # Simulation Loop
    # Need enough lookback for indicators (e.g. 200 bars) 
    start_idx = 200 
    
    print(f"Running {strategy.get_name()} on {len(df_base)} bars...")

    for i in tqdm(range(start_idx, len(df_base))):
        current_bar = df_base.iloc[i]
        current_time = df_base.index[i]
        
        # --- CHECK EXIT ---
        if position:
            # Check Low/High for SL/TP
            # Being conservative: Assume Worst Case (Stop hit first if both triggered in same candle) 
            
            low = current_bar['Low']
            high = current_bar['High']
            
            exit_price = None
            pnl = 0.0
            
            if position == 'BUY':
                if low <= stop_loss:
                    exit_price = stop_loss
                elif high >= take_profit:
                    exit_price = take_profit
            elif position == 'SELL':
                if high >= stop_loss:
                    exit_price = stop_loss
                elif low <= take_profit:
                    exit_price = take_profit
            
            if exit_price:
                if position == 'BUY':
                    pnl = (exit_price - entry_price) * 5000 # 5000 oz contract size? Just using raw price diff for now
                    # Normalized PnL (R-multiples)
                    r_pnl = (exit_price - entry_price) / abs(entry_price - stop_loss)
                else:
                    pnl = (entry_price - exit_price) * 5000
                    r_pnl = (entry_price - exit_price) / abs(entry_price - stop_loss)
                
                trades.append({
                    'entry_time': entry_time,
                    'exit_time': current_time,
                    'type': position,
                    'entry': entry_price,
                    'exit': exit_price,
                    'pnl': r_pnl # Recording R-multiples
                })
                
                position = None
                continue

        # --- CHECK ENTRY ---
        if not position:
            # Prepare Data Slice (Base + HTF)
            # Strategy expects 'base' (5m) and 'htf' (15m)
            
            # Base slice
            base_slice = df_base.iloc[max(0, i-100):i+1]
            
            # HTF slice (15m)
            # Find 15m candle corresponding to current time
            df_htf = data.get('15m')
            if df_htf is not None:
                htf_mask = df_htf.index <= current_time
                htf_slice = df_htf[htf_mask].iloc[-50:] # Last 50 candles
            else:
                htf_slice = None
                
            input_data = {
                'base': base_slice,
                'htf': htf_slice
            }
            
            try:
                # Use strategy analyze with spread
                signal = strategy.analyze(input_data, symbol, target_rr=TARGET_RR, spread=SPREAD)
                
                if signal:
                    position = signal['signal']
                    entry_price = float(current_bar['Close']) # Enter at Close of signal candle
                    stop_loss = signal['stop_loss']
                    take_profit = signal['take_profit']
                    entry_time = current_time
            except Exception as e:
                # print(f"Error: {e}")
                pass

    return trades

def analyze_results(name, trades):
    if not trades:
        print(f"--- {name} Results ---")
        print("No trades generated.")
        return

    df = pd.DataFrame(trades)
    total_trades = len(df)
    wins = df[df['pnl'] > 0]
    losses = df[df['pnl'] <= 0]
    
    win_rate = len(wins) / total_trades * 100
    avg_win = wins['pnl'].mean() if not wins.empty else 0
    avg_loss = losses['pnl'].mean() if not losses.empty else 0
    total_r = df['pnl'].sum()
    
    print(f"--- {name} Results ---")
    print(f"Total Trades: {total_trades}")
    print(f"Win Rate:     {win_rate:.2f}%")
    print(f"Total Return: {total_r:.2f} R")
    print(f"Avg Win:      {avg_win:.2f} R")
    print(f"Avg Loss:     {avg_loss:.2f} R")
    print("-" * 30)

if __name__ == "__main__":
    print(f"Loading data for {SYMBOL}...")
    data = load_data(SYMBOL)
    
    if '5m' not in data:
        print("Error: 5m data missing.")
        sys.exit(1)
        
    # 1. Test Sniper (New Config)
    # Note: Sniper uses 'casket' logic. XAG_USD defaults to 'Steady'
    # Check forex_baskets.json for classification.
    # We need to make sure 'XAG_USD' is recognized correctly. 
    
    sniper = SniperDetector()
    print("\nTesting Sniper Strategy...")
    trades_sniper = run_backtest(sniper, data, SYMBOL)
    analyze_results("Sniper", trades_sniper)
    
    # 2. Test SilverSniper (Old Config)
    silver_sniper = SilverSniperDetector()
    print("\nTesting SilverSniper Strategy...")
    trades_silver = run_backtest(silver_sniper, data, SYMBOL)
    analyze_results("SilverSniper", trades_silver)
