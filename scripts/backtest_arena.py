"""
Forex Backtest Arena (MTF)

Systematically tests all strategies against all pairs using Multi-Timeframe data.
Generates 'best_strategies.json' for the live screener.
"""

import pandas as pd
import numpy as np
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from tqdm import tqdm

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
METADATA_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
OUTPUT_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'best_strategies.json'
SPREAD_COST = 0.00015  # Average spread cost

class BacktestArena:
    def __init__(self):
        self.strategies: List[ForexStrategy] = [
            SniperDetector(),
            TripleTrendDetector(),
            ForexDetector(),
            SqueezeDetector()
        ]
        self.pairs = self._load_pairs()

    def _load_pairs(self) -> List[Dict]:
        with open(METADATA_PATH, 'r') as f:
            return json.load(f)['pairs']

    def _load_data(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """
        Load 15m, 1h, and 4h data for a symbol.
        Returns a dict of DataFrames.
        """
        data = {}
        # Filename patterns based on ls output: {Symbol}_15_Min.csv, etc.
        patterns = {
            '15m': f"{symbol}_15_Min.csv",
            '1h': f"{symbol}_1_Hour.csv",
            '4h': f"{symbol}_4_Hour.csv"
        }

        for tf, filename in patterns.items():
            path = DATA_DIR / filename
            if not path.exists():
                # Try fallback for some symbols that might be named differently
                # e.g. replacing =X might be needed sometimes, but based on ls output it seems exact
                continue
            
            try:
                # Load CSV
                df = pd.read_csv(path)
                
                # Standardize columns (Open, High, Low, Close, Volume, Date/Datetime)
                # Oanda download script likely saves index as 'Date' or 'Datetime' column
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'], utc=True)
                    df.set_index('Date', inplace=True)
                elif 'Datetime' in df.columns:
                    df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True)
                    df.set_index('Datetime', inplace=True)
                
                # Ensure sort
                df.sort_index(inplace=True)
                
                data[tf] = df
            except Exception as e:
                print(f"Error loading {filename}: {e}")

        return data

    def run_backtest(self, strategy: ForexStrategy, data: Dict[str, pd.DataFrame], symbol: str) -> Dict:
        """
        Run a backtest for a specific strategy on a specific pair.
        """
        df_15m = data.get('15m')
        if df_15m is None or len(df_15m) < 100:
            return {'score': -100, 'trades': 0, 'win_rate': 0, 'profit_factor': 0}

        # Optimization: Pre-calculate indicators for strategies that support it?
        # No, because strategies might rely on different indicators.
        # But we can limit the data passed to analyze() to avoid copying huge frames.
        
        trades = []
        position = None # 'BUY' or 'SELL'
        entry_price = 0.0
        stop_loss = 0.0
        
        # Reduced lookback for speed
        start_idx = max(50, len(df_15m) - 200) 
        
        # We process in chunks to avoid slicing overhead if possible, 
        # but for simplicity/correctness we stick to slicing but fewer bars.
        
        for i in range(start_idx, len(df_15m)):
            current_time = df_15m.index[i]
            
            # --- EXIT LOGIC (Fast path) ---
            if position:
                current_price = df_15m['Close'].iloc[i]
                
                # 1. Stop Loss
                hit_stop = (position == 'BUY' and current_price <= stop_loss) or \
                           (position == 'SELL' and current_price >= stop_loss)
                
                # 2. Profit Target (2R)
                risk = abs(entry_price - stop_loss)
                target = entry_price + (risk * 2 if position == 'BUY' else -risk * 2)
                hit_target = (position == 'BUY' and current_price >= target) or \
                             (position == 'SELL' and current_price <= target)
                
                if hit_stop or hit_target:
                    exit_price = stop_loss if hit_stop else target
                    pnl = (exit_price - entry_price) / entry_price if position == 'BUY' else \
                          (entry_price - exit_price) / entry_price
                    pnl -= SPREAD_COST
                    trades.append(pnl)
                    position = None
                    continue

            # --- ENTRY LOGIC ---
            # Prepare slice
            slice_data = {}
            # We only need enough history for indicators (e.g. 100 bars)
            start_window = max(0, i - 100)
            slice_data['15m'] = df_15m.iloc[start_window:i+1]
            
            for tf in ['1h', '4h']:
                if tf in data:
                    # Filter for closed candles
                    htf = data[tf]
                    mask = htf.index < current_time
                    # Only take last 50 bars of HTF to save memory/copy
                    relevant_htf = htf[mask]
                    if len(relevant_htf) > 50:
                        slice_data[tf] = relevant_htf.iloc[-50:]
                    else:
                        slice_data[tf] = relevant_htf

            if not position:
                try:
                    signal = strategy.analyze(slice_data, symbol)
                    
                    if signal and signal.get('signal'):
                        position = signal['signal']
                        entry_price = signal['price']
                        # Use strategy stop loss or default to 0.5%
                        stop_loss = signal.get('stop_loss', 
                            entry_price * (0.995 if position == 'BUY' else 1.005))
                except Exception:
                    pass # Skip errors in strategy calc

        # Compile stats
        if not trades:
             return {'score': 0, 'trades': 0, 'win_rate': 0, 'profit_factor': 0}

        wins = [t for t in trades if t > 0]
        losses = [t for t in trades if t <= 0]
        
        win_rate = len(wins) / len(trades)
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10 if gross_profit > 0 else 0)
        
        score = (win_rate * 100) + (min(profit_factor, 5) * 20)
        if len(trades) < 3:
            score -= 50
            
        return {
            'score': score,
            'trades': len(trades),
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'net_profit': sum(trades)
        }

    def run(self):
        print(f"🏟️  Entering the Arena...")
        print(f"strategies: {[s.get_name() for s in self.strategies]}")
        print(f"pairs: {len(self.pairs)}")
        
        results = {}
        
        for pair in tqdm(self.pairs, desc="Analyzing Pairs"):
            symbol = pair['symbol']
            data = self._load_data(symbol)
            
            if '15m' not in data:
                continue
                
            pair_results = []
            
            for strategy in self.strategies:
                stats = self.run_backtest(strategy, data, symbol)
                pair_results.append({
                    'strategy': strategy.get_name(),
                    'score': stats['score'],
                    'details': stats
                })
            
            # Find best strategy
            best = max(pair_results, key=lambda x: x['score'])
            
            # Only assign if score is positive (beating random/loss)
            if best['score'] > 20: 
                results[symbol] = best['strategy']
                # print(f"  {symbol}: {best['strategy']} (Score: {best['score']:.1f})")
            else:
                # Fallback to standard
                results[symbol] = "TrendFollowing"

        # Save to file
        with open(OUTPUT_PATH, 'w') as f:
            json.dump(results, f, indent=2)
            
        print(f"\n🏆 Arena Closed. Best strategies saved to {OUTPUT_PATH}")
        return results

if __name__ == "__main__":
    arena = BacktestArena()
    arena.run()
