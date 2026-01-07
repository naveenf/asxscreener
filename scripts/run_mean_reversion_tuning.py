"""
Script to run multiple Mean Reversion parameter sets to find optimal settings.
"""

import sys
from pathlib import Path
import pandas as pd
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app.services.backtester import Backtester
from app.services.backtest_metrics import PerformanceMetrics
from app.services.mean_reversion_detector import MeanReversionDetector
from app.services.indicators import TechnicalIndicators
from app.config import settings

def load_stock_data(data_dir: Path, tickers: list, rsi_period=14, bb_period=20, bb_std_dev=2.0):
    stock_data = {}
    for ticker in tickers:
        csv_path = data_dir / f"{ticker}.csv"
        if not csv_path.exists(): continue
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if len(df) < 250: continue
        
        df = TechnicalIndicators.add_all_indicators(
            df, rsi_period=rsi_period, bb_period=bb_period, bb_std_dev=bb_std_dev
        )
        df = df.dropna(subset=['RSI', 'BB_Upper', 'BB_Middle', 'BB_Lower'])
        if len(df) > 0: stock_data[ticker] = df
    return stock_data

def run_test(name, rsi_thresh, bb_p, bb_std, stock_data_cached=None):
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data' / 'raw'
    target_tickers = ['CBA.AX', 'BHP.AX', 'RIO.AX', 'TLS.AX', 'NAB.AX', 'WBC.AX', 'ANZ.AX', 'MQG.AX', 'CSL.AX', 'WES.AX']
    
    # We need to recalculate indicators if BB_period changed
    if stock_data_cached is None:
        stock_data = load_stock_data(data_dir, target_tickers, bb_period=bb_p, bb_std_dev=bb_std)
    else:
        stock_data = stock_data_cached

    detector = MeanReversionDetector(
        rsi_threshold=rsi_thresh,
        profit_target=0.10,
        bb_period=bb_p,
        bb_std_dev=bb_std
    )

    backtester = Backtester(
        detector=detector,
        start_date='2023-01-01',
        end_date='2024-12-31',
        initial_capital=100000.0,
        position_size_pct=0.10,
        max_positions=10
    )

    results = backtester.run(stock_data)
    metrics = PerformanceMetrics(results.trades, results.equity_curve, 100000.0)
    
    return {
        'name': name,
        'rsi': rsi_thresh,
        'bb_p': bb_p,
        'return_pct': metrics.total_return_pct,
        'win_rate': metrics.win_rate,
        'trades': len(results.trades),
        'profit_factor': metrics.profit_factor
    }

def main():
    print("Starting Parameter Tuning...")
    
    # Test cases: (Name, RSI, BB_Period, BB_Std)
    configs = [
        ("Baseline (P2)", 30, 20, 2.0),
        ("More Sensitive RSI", 35, 20, 2.0),
        ("Faster Bands", 30, 14, 2.0),
        ("Combined (Sensi+Fast)", 35, 14, 2.0),
        ("Aggressive Bands", 35, 20, 1.5)
    ]

    summary = []
    # Cache data for same BB settings to speed up
    cache_20_2 = load_stock_data(Path('data/raw'), ['CBA.AX', 'BHP.AX', 'RIO.AX', 'TLS.AX', 'NAB.AX', 'WBC.AX', 'ANZ.AX', 'MQG.AX', 'CSL.AX', 'WES.AX'], bb_period=20, bb_std_dev=2.0)
    cache_14_2 = load_stock_data(Path('data/raw'), ['CBA.AX', 'BHP.AX', 'RIO.AX', 'TLS.AX', 'NAB.AX', 'WBC.AX', 'ANZ.AX', 'MQG.AX', 'CSL.AX', 'WES.AX'], bb_period=14, bb_std_dev=2.0)
    cache_20_15 = load_stock_data(Path('data/raw'), ['CBA.AX', 'BHP.AX', 'RIO.AX', 'TLS.AX', 'NAB.AX', 'WBC.AX', 'ANZ.AX', 'MQG.AX', 'CSL.AX', 'WES.AX'], bb_period=20, bb_std_dev=1.5)

    for name, rsi, bb_p, bb_std in configs:
        print(f"\nTesting: {name}")
        cache = None
        if bb_p == 20 and bb_std == 2.0: cache = cache_20_2
        elif bb_p == 14 and bb_std == 2.0: cache = cache_14_2
        elif bb_p == 20 and bb_std == 1.5: cache = cache_20_15
        
        res = run_test(name, rsi, bb_p, bb_std, cache)
        summary.append(res)

    print("\n" + "="*80)
    print(f"{ 'Configuration':<25} | {'RSI':<4} | {'BB':<4} | {'Trades':<6} | {'Win%':<6} | {'Return':<8}")
    print("-"*80)
    for s in summary:
        print(f"{s['name']:<25} | {s['rsi']:<4} | {s['bb_p']:<4} | {s['trades']:<6} | {s['win_rate']():<6.1f} | {s['return_pct']():<8.2f}%")
    print("="*80)

if __name__ == '__main__':
    main()
