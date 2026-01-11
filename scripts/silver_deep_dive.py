"""
Silver (SI=F) Max Potential Analysis

Simulates a "Let it Run" strategy:
1. Enter on Squeeze Breakout.
2. Initial Stop = Middle Band (SMA20).
3. If Profit >= 1.5R -> Move Stop to +1.0R (Lock Profit).
4. After locking, Trail Stop using EMA13 to capture big trends.
"""

import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.squeeze_detector import SqueezeDetector
from backend.app.services.indicators import TechnicalIndicators

# Configuration
FILE_PATH = PROJECT_ROOT / 'data' / 'forex_raw' / 'SI=F_15_Min.csv'
SPREAD_COST = 0.00015

def run_deep_dive():
    if not FILE_PATH.exists():
        print("Data file not found.")
        return

    # Load Data
    df = pd.read_csv(FILE_PATH)
    col = 'Date' if 'Date' in df.columns else 'Datetime'
    df[col] = pd.to_datetime(df[col], utc=True)
    df.set_index(col, inplace=True)
    df.sort_index(inplace=True)

    # Add Indicators
    df = TechnicalIndicators.add_all_indicators(df)

    detector = SqueezeDetector()
    trades = []
    
    position = None # 'BUY' or 'SELL'
    entry_price = 0.0
    initial_risk = 0.0
    stop_loss = 0.0
    is_locked = False # Have we moved SL to +1R?
    
    highest_r_global = 0.0
    best_trade_date = None

    # Analyze last 1000 bars
    start_idx = max(100, len(df) - 1000)
    
    for i in range(start_idx, len(df)):
        current = df.iloc[i]
        current_time = df.index[i]
        
        # --- EXIT / MANAGEMENT ---
        if position:
            # Calculate current R-Multiple
            if position == 'BUY':
                current_profit = current['High'] - entry_price
                current_r = current_profit / initial_risk
                
                # Logic: Lock 1R at 1.5R
                if not is_locked and current_r >= 1.5:
                    is_locked = True
                    stop_loss = entry_price + (initial_risk * 1.0)
                
                # Logic: Trail with EMA13 after locking to let it run
                if is_locked:
                    # Trail stop up, never down
                    stop_loss = max(stop_loss, current['EMA13'])
                
                # Check Exit (Low hit stop)
                if current['Low'] <= stop_loss:
                    exit_price = stop_loss
                    pnl_r = (exit_price - entry_price) / initial_risk
                    trades.append(pnl_r)
                    
                    if pnl_r > highest_r_global:
                        highest_r_global = pnl_r
                        best_trade_date = current_time
                        
                    position = None
                    continue
                    
            elif position == 'SELL':
                current_profit = entry_price - current['Low']
                current_r = current_profit / initial_risk
                
                if not is_locked and current_r >= 1.5:
                    is_locked = True
                    stop_loss = entry_price - (initial_risk * 1.0)
                
                if is_locked:
                    stop_loss = min(stop_loss, current['EMA13'])
                
                if current['High'] >= stop_loss:
                    exit_price = stop_loss
                    pnl_r = (entry_price - exit_price) / initial_risk
                    trades.append(pnl_r)
                    
                    if pnl_r > highest_r_global:
                        highest_r_global = pnl_r
                        best_trade_date = current_time

                    position = None
                    continue

        # --- ENTRY ---
        if not position:
            # Slice for detector
            slice_df = df.iloc[:i+1] # No HTF needed for raw signal check in this test
            data = {'15m': slice_df} 
            
            try:
                signal = detector.analyze(data, "SI=F")
                if signal:
                    position = signal['signal']
                    entry_price = signal['price']
                    # Initial Stop is Middle Band (SMA20)
                    initial_stop = df['BB_Middle'].iloc[i]
                    initial_risk = abs(entry_price - initial_stop)
                    
                    # Safety: Min risk to avoid div/0
                    if initial_risk < entry_price * 0.0005:
                        initial_risk = entry_price * 0.0005
                        
                    stop_loss = initial_stop
                    is_locked = False
            except:
                pass

    # Stats
    wins = [r for r in trades if r > 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    total_r = sum(trades)
    
    print("\n🥈 SILVER (15m) 'LET IT RUN' ANALYSIS")
    print("=" * 60)
    print(f"Strategy: Lock 1R at 1.5R, then Trail EMA13")
    print("-" * 60)
    print(f"Total Trades:       {len(trades)}")
    print(f"Win Rate:           {len(wins)/len(trades)*100:.1f}%")
    print(f"Avg Win (R):        {avg_win:.2f} R")
    print(f"Total Net Reward:   {total_r:.2f} R")
    print("=" * 60)
    print(f"🚀 HIGHEST R ACHIEVED:  {highest_r_global:.2f} R")
    print(f"📅 Date of Best Trade:  {best_trade_date}")
    print("=" * 60)
    
    # Distribution
    r5 = len([r for r in trades if r >= 5])
    r10 = len([r for r in trades if r >= 10])
    print(f"Trades > 5R:        {r5}")
    print(f"Trades > 10R:       {r10}")

if __name__ == "__main__":
    run_deep_dive()
