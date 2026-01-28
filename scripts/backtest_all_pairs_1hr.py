"""
Comprehensive Forex Backtest Suite (1HR - Squeeze Only)

Evaluates all forex pairs, commodities, and indices using the 1H timeframe.
Implements Squeeze strategy with Trailing Stop Loss.
"""

import pandas as pd
import numpy as np
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from tqdm import tqdm

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.squeeze_detector import SqueezeDetector

# Asset Class Configuration
ASSET_CONFIGS = {
    "Forex": {
        "spread": 0.00012, # 1.2 pips
        "is_pips": True
    },
    "Index": {
        "spread": 1.0,     # 1 point (NAS100, JP225)
        "is_pips": False
    },
    "Commodity": {
        "spread": 0.03,    # Default (Oil, etc.)
        "is_pips": False
    }
}

# Symbol-Specific Overrides
SYMBOL_SPREADS = {
    "XAU_USD": 0.40,   # Gold
    "XAG_USD": 0.02,   # Silver
    "XCU_USD": 0.002,  # Copper
    "CORN_USD": 0.01,  # Corn
    "WHEAT_USD": 0.01, # Wheat
    "SOYBN_USD": 0.01, # Soybeans
    "BCO_USD": 0.03,   # Brent Crude
}

def get_asset_config(symbol, symbol_type):
    config = ASSET_CONFIGS.get(symbol_type, ASSET_CONFIGS["Forex"]).copy()
    if symbol in SYMBOL_SPREADS:
        config["spread"] = SYMBOL_SPREADS[symbol]
        config["is_pips"] = False # Overrides are usually in points
    return config

# Data & Metadata Paths
DATA_DIR = PROJECT_ROOT / "data" / "forex_raw"
PAIRS_PATH = PROJECT_ROOT / "data" / "metadata" / "forex_pairs.json"
STRATEGY_MAP_PATH = PROJECT_ROOT / "data" / "metadata" / "best_strategies.json"

def load_metadata():
    """Load pairs and best strategies mapping."""
    with open(PAIRS_PATH, 'r') as f:
        pairs = json.load(f)['pairs']
    
    with open(STRATEGY_MAP_PATH, 'r') as f:
        strategy_map = json.load(f)
        
    return pairs, strategy_map

class BacktestEngine:
    def __init__(self, pairs, strategy_map):
        self.pairs = pairs
        self.strategy_map = strategy_map
        self.detector = SqueezeDetector()

    def run_backtest(self, symbol, asset_type):
        """Run backtest for a single symbol using 1H data."""
        filename = DATA_DIR / f"{symbol}_1_Hour.csv"
        if not filename.exists():
            return None

        df = pd.read_csv(filename)
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'], utc=True)
            df.set_index('Date', inplace=True)
        elif 'Datetime' in df.columns:
            df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
            df.set_index('Datetime', inplace=True)
        df.sort_index(inplace=True)

        # Add indicators (vectorized)
        df = TechnicalIndicators.add_all_indicators(df)
        
        config = get_asset_config(symbol, asset_type)
        spread = config["spread"]
        target_rr = self.strategy_map.get(symbol, {}).get("target_rr", 2.0)
        
        trades = []
        position = None # {type, entry_price, sl, tp, high_water_mark}

        # Squeeze logic requires some lookback, starting from 100
        for i in range(100, len(df)):
            current_bar = df.iloc[i]
            current_price = current_bar['Close']
            current_time = df.index[i]

            # --- EXIT LOGIC (Trailing SL & TP) ---
            if position:
                is_exit = False
                exit_reason = ""
                exit_price = current_price

                if position['type'] == 'BUY':
                    # Update High Water Mark
                    if current_price > position['high_water_mark']:
                        # Move SL up if price moved significantly (Trailing)
                        # Logic: Trail at 50% of the way to TP? 
                        # Or simple: SL follows at fixed distance once price > 1R
                        old_hwm = position['high_water_mark']
                        position['high_water_mark'] = current_price
                        
                        risk = position['entry_price'] - position['initial_sl']
                        if current_price > (position['entry_price'] + risk):
                            # Trailing SL: Keep SL at current_price - 1R
                            new_sl = current_price - risk
                            if new_sl > position['sl']:
                                position['sl'] = new_sl

                    # Check TP
                    if current_price >= position['tp']:
                        is_exit = True
                        exit_price = position['tp']
                        exit_reason = "TP"
                    # Check SL (Trailing)
                    elif current_price <= position['sl']:
                        is_exit = True
                        exit_price = position['sl']
                        exit_reason = "SL"
                
                else: # SELL
                    if current_price < position['high_water_mark']:
                        position['high_water_mark'] = current_price
                        risk = position['initial_sl'] - position['entry_price']
                        if current_price < (position['entry_price'] - risk):
                            new_sl = current_price + risk
                            if new_sl < position['sl']:
                                position['sl'] = new_sl

                    if current_price <= position['tp']:
                        is_exit = True
                        exit_price = position['tp']
                        exit_reason = "TP"
                    elif current_price >= position['sl']:
                        is_exit = True
                        exit_price = position['sl']
                        exit_reason = "SL"

                if is_exit:
                    pnl_raw = (exit_price - position['entry_price']) / position['entry_price'] if position['type'] == 'BUY' else \
                              (position['entry_price'] - exit_price) / position['entry_price']
                    
                    # Normalize spread to percentage
                    spread_pct = spread if config["is_pips"] else (spread / position['entry_price'])
                    pnl = pnl_raw - spread_pct
                    
                    trades.append({
                        "entry_time": position['entry_time'],
                        "exit_time": current_time,
                        "type": position['type'],
                        "entry_price": position['entry_price'],
                        "exit_price": exit_price,
                        "pnl": pnl,
                        "reason": exit_reason
                    })
                    position = None

            # --- ENTRY LOGIC ---
            if not position:
                # Prepare slice for detector (needs some history)
                # SqueezeDetector.analyze expects data['base']
                slice_df = df.iloc[i-50:i+1]
                result = self.detector.analyze({"base": slice_df}, symbol, target_rr=target_rr)
                
                if result and result.get('signal'):
                    entry_price = result['price']
                    sl = result['stop_loss']
                    tp = result['take_profit']
                    
                    position = {
                        "type": result['signal'],
                        "entry_price": entry_price,
                        "initial_sl": sl,
                        "sl": sl,
                        "tp": tp,
                        "entry_time": current_time,
                        "high_water_mark": entry_price
                    }

        return trades

    def run_full_universe(self):
        """Run backtest for all pairs and return results."""
        results = {}
        print(f"\n🚀 Running backtest for {len(self.pairs)} pairs...")
        
        for pair in tqdm(self.pairs, desc="Backtesting Pairs"):
            symbol = pair['symbol']
            asset_type = pair['type']
            
            trades = self.run_backtest(symbol, asset_type)
            if trades:
                results[symbol] = {
                    "name": pair['name'],
                    "type": asset_type,
                    "trades": trades
                }
            else:
                # Still record the attempt but with no trades
                results[symbol] = {
                    "name": pair['name'],
                    "type": asset_type,
                    "trades": [],
                    "error": "No data or no signals"
                }
                
        return results

    def summarize_results(self, results):
        """Calculate and print aggregate metrics."""
        summary = []
        
        for symbol, data in results.items():
            trades = data['trades']
            if not trades:
                continue
                
            df_t = pd.DataFrame(trades)
            wins = df_t[df_t['pnl'] > 0]
            losses = df_t[df_t['pnl'] <= 0]
            
            win_rate = len(wins) / len(df_t)
            total_pnl = df_t['pnl'].sum()
            
            gross_profit = wins['pnl'].sum()
            gross_loss = abs(losses['pnl'].sum())
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            
            summary.append({
                "symbol": symbol,
                "name": data['name'],
                "type": data['type'],
                "trades_count": len(df_t),
                "win_rate": win_rate,
                "net_profit_pct": total_pnl * 100,
                "profit_factor": profit_factor
            })
            
        return sorted(summary, key=lambda x: x['net_profit_pct'], reverse=True)

def log_config():
    print("=" * 60)
    print("BACKTEST CONFIGURATION")
    print("=" * 60)
    for asset, config in ASSET_CONFIGS.items():
        unit = "pips" if config["is_pips"] else "points"
        print(f"{asset:12}: Spread {config['spread']} {unit}")
    
    pairs, strategy_map = load_metadata()
    print(f"Loaded {len(pairs)} pairs and {len(strategy_map)} strategy mappings.")
    print("=" * 60)

if __name__ == "__main__":
    log_config()
    pairs, strategy_map = load_metadata()
    engine = BacktestEngine(pairs, strategy_map)
    
    results = engine.run_full_universe()
    summary = engine.summarize_results(results)
    
    print("\n" + "=" * 80)
    print(f"{'SYMBOL':12} | {'TRADES':6} | {'WIN %':8} | {'NET PNL':10} | {'PF':6}")
    print("-" * 80)
    for s in summary:
        print(f"{s['symbol']:12} | {s['trades_count']:6} | {s['win_rate']*100:7.2f}% | {s['net_profit_pct']:9.2f}% | {s['profit_factor']:6.2f}")
    print("=" * 80)
