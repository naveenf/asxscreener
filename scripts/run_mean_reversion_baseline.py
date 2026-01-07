"""
Script to run backtests on Mean Reversion strategy.
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app.services.backtester import Backtester
from app.services.backtest_metrics import PerformanceMetrics
from app.services.mean_reversion_detector import MeanReversionDetector
from app.services.indicators import TechnicalIndicators
from app.config import settings


def load_stock_data(
    data_dir: Path,
    tickers: list,
    min_required_bars: int = 250
) -> dict:
    """Load data for specific tickers."""
    print(f"Loading data for {len(tickers)} stocks...")
    stock_data = {}

    for ticker in tickers:
        csv_path = data_dir / f"{ticker}.csv"
        if not csv_path.exists():
            print(f"  - {ticker} not found")
            continue

        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        if len(df) < min_required_bars:
            print(f"  - {ticker} insufficient data")
            continue

        # Add indicators
        df = TechnicalIndicators.add_all_indicators(
            df,
            rsi_period=settings.RSI_PERIOD,
            bb_period=settings.BB_PERIOD,
            bb_std_dev=settings.BB_STD_DEV
        )
        df = df.dropna(subset=['RSI', 'BB_Upper', 'BB_Middle', 'BB_Lower'])
        
        if len(df) > 0:
            stock_data[ticker] = df

    return stock_data


def main():
    # Target 10 stocks for Phase 1
    target_tickers = [
        'CBA.AX', 'BHP.AX', 'RIO.AX', 'TLS.AX', 'NAB.AX', 
        'WBC.AX', 'ANZ.AX', 'MQG.AX', 'CSL.AX', 'WES.AX'
    ]

    # Setup paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data' / 'raw'
    output_dir = project_root / 'data' / 'backtest_results'

    # Settings
    start_date = '2023-01-01'
    end_date = '2024-12-31'
    initial_capital = 100000.0

    print("\n" + "="*70)
    print("PHASE 1: MEAN REVERSION BASELINE (OVERBOUGHT ENTRY)")
    print("="*70)

    # Load data
    stock_data = load_stock_data(data_dir, target_tickers)

    if not stock_data:
        print("ERROR: No stock data loaded.")
        return

    # Initialize Mean Reversion Detector with current (problematic) settings
    detector = MeanReversionDetector(
        rsi_threshold=settings.RSI_THRESHOLD, # 70
        profit_target=settings.MEAN_REVERSION_PROFIT_TARGET, # 0.07
        bb_period=settings.BB_PERIOD,
        bb_std_dev=settings.BB_STD_DEV
    )

    # Initialize backtester
    backtester = Backtester(
        detector=detector,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        position_size_pct=0.10, # 10% per stock
        max_positions=10,
        slippage_pct=0.001,
        commission=10.0
    )

    # Run
    results = backtester.run(stock_data)

    # Metrics
    metrics = PerformanceMetrics(
        trades=results.trades,
        equity_curve=results.equity_curve,
        initial_capital=initial_capital
    )

    metrics.print_summary()


if __name__ == '__main__':
    main()
