"""
Final full-scale backtest for Mean Reversion strategy.
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

def main():
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data' / 'raw'
    stock_list_path = project_root / 'data' / 'metadata' / 'stock_list.json'
    
    print("\n" + "="*70)
    print("FINAL FULL-SCALE MEAN REVERSION BACKTEST")
    print("="*70)
    print(f"RSI Threshold: {settings.RSI_THRESHOLD}")
    print(f"Profit Target: {settings.MEAN_REVERSION_PROFIT_TARGET}")
    print("="*70)

    # Load full stock list
    with open(stock_list_path) as f:
        stocks = json.load(f)['stocks']
    
    tickers = [s['ticker'] for s in stocks]
    
    print(f"Loading data for {len(tickers)} stocks...")
    stock_data = {}
    for ticker in tickers:
        csv_path = data_dir / f"{ticker}.csv"
        if not csv_path.exists(): continue
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if len(df) < 250: continue
        
        df = TechnicalIndicators.add_all_indicators(
            df, 
            rsi_period=settings.RSI_PERIOD, 
            bb_period=settings.BB_PERIOD, 
            bb_std_dev=settings.BB_STD_DEV
        )
        df = df.dropna(subset=['RSI', 'BB_Upper', 'BB_Middle', 'BB_Lower'])
        if len(df) > 0: stock_data[ticker] = df

    # Initialize Detector
    detector = MeanReversionDetector(
        rsi_threshold=settings.RSI_THRESHOLD,
        profit_target=settings.MEAN_REVERSION_PROFIT_TARGET,
        stop_loss=settings.MEAN_REVERSION_STOP_LOSS,
        time_limit=settings.MEAN_REVERSION_TIME_LIMIT,
        bb_period=settings.BB_PERIOD,
        bb_std_dev=settings.BB_STD_DEV
    )

    # Initialize Backtester
    backtester = Backtester(
        detector=detector,
        start_date='2023-01-01',
        end_date='2024-12-31',
        initial_capital=100000.0,
        max_positions=10,
        position_size_pct=0.10, # 10% per trade
        slippage_pct=0.001,
        commission=10.0
    )

    # Run
    results = backtester.run(stock_data)

    # Metrics
    metrics = PerformanceMetrics(results.trades, results.equity_curve, 100000.0)
    metrics.print_summary()

if __name__ == '__main__':
    main()
