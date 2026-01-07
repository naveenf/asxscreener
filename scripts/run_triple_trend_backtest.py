"""
Full-scale backtest for Triple Confirmation Trend strategy.
"""

import sys
from pathlib import Path
import pandas as pd
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app.services.backtester import Backtester
from app.services.backtest_metrics import PerformanceMetrics
from app.services.triple_trend_detector import TripleTrendDetector
from app.services.indicators import TechnicalIndicators
from app.config import settings

def main():
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data' / 'raw'
    stock_list_path = project_root / 'data' / 'metadata' / 'stock_list.json'
    
    print("\n" + "="*70)
    print("TRIPLE TREND CONFIRMATION BACKTEST")
    print("="*70)
    print("Indicators: Fibonacci (50), PP Supertrend, Ehlers IT")
    print("Screening: T-1 (Yesterday's Close)")
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
        # Fibonacci(50) + Supertrend(10) + IT(3) -> need at least 100 bars for stability
        if len(df) < 100: continue
        
        # Add all indicators
        df = TechnicalIndicators.add_all_indicators(df)
        
        # Drop initial NaNs
        df = df.dropna(subset=['Fib_Pos', 'PP_Trend', 'IT_Trend'])
        if len(df) > 0: stock_data[ticker] = df

    # Initialize Detector
    detector = TripleTrendDetector(
        fib_period=50,
        st_factor=3.0,
        it_alpha=0.07,
        profit_target=0.15,
        stop_loss=settings.TREND_FOLLOWING_STOP_LOSS,
        time_limit=settings.TREND_FOLLOWING_TIME_LIMIT
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
