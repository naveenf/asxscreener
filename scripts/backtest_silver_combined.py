
import pandas as pd
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.silver_sniper_detector import SilverSniperDetector
from backend.app.services.daily_orb_detector import DailyORBDetector
from backend.app.services.indicators import TechnicalIndicators

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
OUTPUT_DIR = PROJECT_ROOT / 'data'
STARTING_BALANCE = 360.0
RISK_PCT = 2.0
LEVERAGE = 10.0
SPREAD_COST = 0.0006  # 0.06%
SYMBOL = "XAG_USD"

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
        print(f"Calculating indicators for {tf}...")
        if tf == '5_Min':
            df = TechnicalIndicators.add_all_indicators(df)
        elif tf == '15_Min':
            df = TechnicalIndicators.add_all_indicators(df)
        else: # 1H, 4H
            df = TechnicalIndicators.calculate_adx(df)
            
        data[tf] = df
    
    return data

def run_combined_backtest():
    print("\n" + "="*60)
    print("RUNNING COMBINED SILVER BACKTEST (Shared Capital)")
    print("="*60)
    
    data = load_data()
    if not data: return
    
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
    
    orb_detector = DailyORBDetector()
    sniper_detector = SilverSniperDetector()
    
    balance = STARTING_BALANCE
    trades = []
    active_trades = [] # List of {direction, entry_price, sl, tp, strategy, entry_time, units}
    
    # Use 15m as the master clock since both strategies can trigger on it (Sniper uses 5m but we can sync)
    # Actually, iterate through all 5m candles to be precise
    
    start_time = max(df_5m.index[200], df_15m.index[200])
    end_time = min(df_5m.index[-1], df_15m.index[-1])
    
    current_time = start_time
    
    # To speed up, we'll iterate through 5m candles
    idx_5m = df_5m.index.get_loc(start_time)
    
    print(f"Simulating from {start_time} to {end_time}...")
    
    while idx_5m < len(df_5m):
        current_time = df_5m.index[idx_5m]
        if current_time > end_time: break
        
        candle_5m = df_5m.iloc[idx_5m]
        
        # 1. Update Active Trades
        remaining_trades = []
        for trade in active_trades:
            exit_reason = None
            exit_price = 0
            
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
                # Close trade
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
                    'Exit_Reason': exit_reason
                })
            else:
                remaining_trades.append(trade)
        
        active_trades = remaining_trades
        
        # 2. Check for New Signals
        # SilverSniper (5m)
        slice_5m = df_5m.iloc[max(0, idx_5m-100):idx_5m+1]
        htf_idx = df_15m.index.get_indexer([current_time], method='pad')[0]
        slice_15m = df_15m.iloc[max(0, htf_idx-50):htf_idx+1]
        
        # Sniper Analysis
        res_sniper = sniper_detector.analyze({'base': slice_5m, 'htf': slice_15m}, SYMBOL, spread=SPREAD_COST, params=sniper_params)
        
        if res_sniper:
            # Check if already in a Sniper trade
            if not any(t['strategy'] == 'SilverSniper' for t in active_trades):
                risk = abs(res_sniper['price'] - res_sniper['stop_loss'])
                units = (balance * (RISK_PCT/100.0)) / risk if risk > 0 else 0
                if units > 0:
                    active_trades.append({
                        'strategy': 'SilverSniper',
                        'direction': res_sniper['signal'],
                        'entry_price': res_sniper['price'],
                        'sl': res_sniper['stop_loss'],
                        'tp': res_sniper['take_profit'],
                        'entry_time': current_time,
                        'units': units
                    })

        # DailyORB (15m) - Only check if current_time is a 15m candle boundary
        if current_time in df_15m.index:
            # ORB Analysis
            htf4_idx = df_4h.index.get_indexer([current_time], method='pad')[0]
            slice_4h = df_4h.iloc[max(0, htf4_idx-50):htf4_idx+1]
            
            res_orb = orb_detector.analyze({'base': slice_15m, 'htf': slice_4h}, SYMBOL, spread=SPREAD_COST, params=orb_params)
            if res_orb:
                # Check if already in an ORB trade
                if not any(t['strategy'] == 'DailyORB' for t in active_trades):
                    risk = abs(res_orb['price'] - res_orb['stop_loss'])
                    units = (balance * (RISK_PCT/100.0)) / risk if risk > 0 else 0
                    if units > 0:
                        active_trades.append({
                            'strategy': 'DailyORB',
                            'direction': res_orb['signal'],
                            'entry_price': res_orb['price'],
                            'sl': res_orb['stop_loss'],
                            'tp': res_orb['take_profit'],
                            'entry_time': current_time,
                            'units': units
                        })

        idx_5m += 1

    # Report
    if not trades:
        print("No trades executed.")
        return

    tdf = pd.DataFrame(trades)
    print("\n" + "="*60)
    print("COMBINED BACKTEST RESULTS")
    print("="*60)
    print(f"Total Trades: {len(tdf)}")
    print(f"  DailyORB: {len(tdf[tdf['Strategy']=='DailyORB'])}")
    print(f"  SilverSniper: {len(tdf[tdf['Strategy']=='SilverSniper'])}")
    
    wins = len(tdf[tdf['Exit_Reason']=='TAKE_PROFIT'])
    print(f"Win Rate: {(wins/len(tdf)*100):.1f}%")
    
    final_roi = (balance - STARTING_BALANCE) / STARTING_BALANCE * 100
    print(f"Final ROI: {final_roi:.2f}%")
    
    # Calculate Sharpe
    tdf['Returns'] = tdf['PnL'] / STARTING_BALANCE
    sharpe = (tdf['Returns'].mean() / tdf['Returns'].std()) * np.sqrt(len(tdf)) if tdf['Returns'].std() > 0 else 0
    print(f"Sharpe Ratio: {sharpe:.2f}")

if __name__ == "__main__":
    run_combined_backtest()
