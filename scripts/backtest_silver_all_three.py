"""
90-Day Combined Silver Backtest for GT-Score Statistical Validation
Includes SilverMomentum strategy and enforces global 3-trade account limit.
"""

import pandas as pd
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import json
from datetime import datetime, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.silver_sniper_detector import SilverSniperDetector
from backend.app.services.daily_orb_detector import DailyORBDetector
from backend.app.services.silver_momentum_detector import SilverMomentumDetector
from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.backtest_metrics import calculate_gt_score, MIN_TRADES

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
OUTPUT_DIR = PROJECT_ROOT / 'data'
STARTING_BALANCE = 360.0
RISK_PCT = 2.0
SPREAD_COST = 0.0006  # 0.06%
SYMBOL = "XAG_USD"
MAX_ACCOUNT_TRADES = 3

def load_data():
    """Load all required timeframes for XAG_USD."""
    timeframes = ['5_Min', '15_Min', '1_Hour', '4_Hour']
    data = {}
    
    for tf in timeframes:
        path = DATA_DIR / f"{SYMBOL}_{tf}.csv"
        if not path.exists():
            print(f"ERROR: Missing {tf} data")
            return None
        
        df = pd.read_csv(path)
        date_col = 'Date' if 'Date' in df.columns else 'Datetime'
        df[date_col] = pd.to_datetime(df[date_col], utc=True)
        df.set_index(date_col, inplace=True)
        df.sort_index(inplace=True)
        
        # Pre-calculate indicators
        print(f"Calculating indicators for {tf}...", flush=True)
        if tf in ['5_Min', '15_Min', '1_Hour']:
            df = TechnicalIndicators.add_all_indicators(df)
        else: # 4H
            df = TechnicalIndicators.calculate_adx(df)
            df['EMA_50'] = TechnicalIndicators.calculate_ema(df, period=50)
            df['EMA_200'] = TechnicalIndicators.calculate_ema(df, period=200)
            
        data[tf] = df
    
    return data

def run_combined_backtest():
    print("\n" + "="*70)
    print("RUNNING 90-DAY COMBINED SILVER BACKTEST (3 STRATEGIES + 3-TRADE LIMIT)")
    print("="*70)
    print()
    
    data = load_data()
    if not data: 
        print("Failed to load data")
        return
    
    df_5m = data['5_Min']
    df_15m = data['15_Min']
    df_1h = data['1_Hour']
    df_4h = data['4_Hour']
    
    # Load params
    with open(PROJECT_ROOT / 'data' / 'metadata' / 'best_strategies.json', 'r') as f:
        best_strategies = json.load(f)
    
    silver_configs = best_strategies.get(SYMBOL, {}).get('strategies', [])
    orb_params = next((s for s in silver_configs if s['strategy'] == 'DailyORB'), {}).get('params', {})
    sniper_params = next((s for s in silver_configs if s['strategy'] == 'SilverSniper'), {}).get('params', {})
    momentum_params = next((s for s in silver_configs if s['strategy'] == 'SilverMomentum'), {}).get('params', {})
    
    orb_detector = DailyORBDetector()
    sniper_detector = SilverSniperDetector()
    momentum_detector = SilverMomentumDetector()
    
    # Determine 90-day window
    end_time = df_5m.index[-1]
    start_time = end_time - timedelta(days=90)
    
    print(f"Backtest Period: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")
    print()
    
    balance = STARTING_BALANCE
    trades = []
    active_trades = []
    
    # Use bfill to find the start index
    try:
        start_idx = df_5m.index.get_indexer([start_time], method='bfill')[0]
        if start_idx == -1: start_idx = 200
    except:
        start_idx = 200
        
    start_idx = max(start_idx, 200)
    end_idx = len(df_5m) - 1
    
    idx_5m = start_idx
    
    while idx_5m < end_idx:
        current_time = df_5m.index[idx_5m]
        candle_5m = df_5m.iloc[idx_5m]
        
        # 1. Update Active Trades
        remaining_trades = []
        for trade in active_trades:
            exit_reason = None
            exit_price = 0
            
            # Use 5m candle for tight SL/TP check
            if trade['direction'] == 'BUY':
                if candle_5m['Low'] <= trade['sl']:
                    exit_reason = 'STOP_LOSS'
                    exit_price = trade['sl']
                elif candle_5m['High'] >= trade['tp']:
                    exit_reason = 'TAKE_PROFIT'
                    exit_price = trade['tp']
            else: # SELL
                if candle_5m['High'] >= trade['sl']:
                    exit_reason = 'STOP_LOSS'
                    exit_price = trade['sl']
                elif candle_5m['Low'] <= trade['tp']:
                    exit_reason = 'TAKE_PROFIT'
                    exit_price = trade['tp']
            
            if exit_reason:
                profit_per_unit = (exit_price - trade['entry_price']) if trade['direction'] == 'BUY' else (trade['entry_price'] - exit_price)
                gross_pnl = profit_per_unit * trade['units']
                net_pnl = gross_pnl - (trade['entry_price'] * trade['units'] * SPREAD_COST)
                balance += net_pnl
                
                trades.append({
                    'Strategy': trade['strategy'],
                    'Entry_Time': trade['entry_time'],
                    'Exit_Time': current_time,
                    'Direction': trade['direction'],
                    'PnL': net_pnl,
                    'Balance': balance,
                    'Exit_Reason': exit_reason,
                    'PnL_Pct': (net_pnl / STARTING_BALANCE) * 100
                })
            else:
                remaining_trades.append(trade)
        
        active_trades = remaining_trades
        
        # 2. Check for New Signals if under account limit
        if len(active_trades) < MAX_ACCOUNT_TRADES:
            # Slices
            slice_5m = df_5m.iloc[max(0, idx_5m-100):idx_5m+1]
            idx_15m = df_15m.index.get_indexer([current_time], method='pad')[0]
            slice_15m = df_15m.iloc[max(0, idx_15m-50):idx_15m+1]
            
            # A. Sniper (5m)
            if not any(t['strategy'] == 'SilverSniper' for t in active_trades):
                res = sniper_detector.analyze({'base': slice_5m, 'htf': slice_15m}, SYMBOL, spread=SPREAD_COST, params=sniper_params)
                if res and len(active_trades) < MAX_ACCOUNT_TRADES:
                    risk = abs(res['price'] - res['stop_loss'])
                    units = (balance * (RISK_PCT/100.0)) / risk if risk > 0 else 0
                    if units > 0:
                        active_trades.append({'strategy': 'SilverSniper', 'direction': res['signal'], 'entry_price': res['price'], 'sl': res['stop_loss'], 'tp': res['take_profit'], 'entry_time': current_time, 'units': units})

            # B. DailyORB (15m boundary)
            if current_time in df_15m.index and len(active_trades) < MAX_ACCOUNT_TRADES:
                if not any(t['strategy'] == 'DailyORB' for t in active_trades):
                    idx_4h = df_4h.index.get_indexer([current_time], method='pad')[0]
                    slice_4h = df_4h.iloc[max(0, idx_4h-50):idx_4h+1]
                    res = orb_detector.analyze({'15m': slice_15m, '4h': slice_4h}, SYMBOL, spread=SPREAD_COST, params=orb_params)
                    if res and len(active_trades) < MAX_ACCOUNT_TRADES:
                        risk = abs(res['price'] - res['stop_loss'])
                        units = (balance * (RISK_PCT/100.0)) / risk if risk > 0 else 0
                        if units > 0:
                            active_trades.append({'strategy': 'DailyORB', 'direction': res['signal'], 'entry_price': res['price'], 'sl': res['stop_loss'], 'tp': res['take_profit'], 'entry_time': current_time, 'units': units})

            # C. SilverMomentum (1h boundary)
            if current_time in df_1h.index and len(active_trades) < MAX_ACCOUNT_TRADES:
                idx_1h = df_1h.index.get_indexer([current_time], method='pad')[0]
                slice_1h = df_1h.iloc[max(0, idx_1h-100):idx_1h+1]
                idx_4h = df_4h.index.get_indexer([current_time], method='pad')[0]
                slice_4h = df_4h.iloc[max(0, idx_4h-100):idx_4h+1]
                
                res = momentum_detector.analyze({'1h': slice_1h, '4h': slice_4h}, SYMBOL, spread=SPREAD_COST, params=momentum_params)
                if res and len(active_trades) < MAX_ACCOUNT_TRADES:
                    risk = abs(res['price'] - res['stop_loss'])
                    units = (balance * (RISK_PCT/100.0)) / risk if risk > 0 else 0
                    if units > 0:
                        active_trades.append({'strategy': 'SilverMomentum', 'direction': res['signal'], 'entry_price': res['price'], 'sl': res['stop_loss'], 'tp': res['take_profit'], 'entry_time': current_time, 'units': units})

        idx_5m += 1

    # Report
    if not trades:
        print("No trades executed.")
        return

    tdf = pd.DataFrame(trades)
    print("\n" + "="*70)
    print("BACKTEST RESULTS SUMMARY")
    print("="*70)
    print(f"Total Trades: {len(tdf)}")
    for strat in ['DailyORB', 'SilverSniper', 'SilverMomentum']:
        count = len(tdf[tdf['Strategy']==strat])
        print(f"  {strat}: {count}")
    
    wins = len(tdf[tdf['Exit_Reason']=='TAKE_PROFIT'])
    win_rate = (wins/len(tdf)*100) if len(tdf) > 0 else 0
    final_roi = (balance - STARTING_BALANCE) / STARTING_BALANCE * 100
    
    print(f"\nWin Rate: {win_rate:.1f}%")
    print(f"Final ROI: {final_roi:.2f}%")
    print(f"Ending Balance: ${balance:.2f}")
    
    # GT-Score
    returns = (tdf['PnL_Pct'].values / 100.0).tolist()
    gt_result = calculate_gt_score(returns, equity_curve=None)
    print(f"\nGT-Score: {gt_result['gt_score']:.6f}")
    print(f"Validity: {'✅ VALID' if gt_result['valid'] else '❌ INVALID'}")
    
    output_csv = OUTPUT_DIR / 'backtest_silver_all_three.csv'
    tdf.to_csv(output_csv, index=False)
    print(f"\n✓ Results saved to {output_csv}")

if __name__ == "__main__":
    run_combined_backtest()
