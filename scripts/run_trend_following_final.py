"""
Final full-scale backtest for Trend Following strategy.
"""

import sys
from pathlib import Path
import pandas as pd
import json

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'backend'))

from app.services.backtester import Backtester
from app.services.backtest_metrics import PerformanceMetrics
from app.services.signal_detector import SignalDetector
from app.services.indicators import TechnicalIndicators
from app.config import settings

def main():
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data' / 'raw'
    stock_list_path = project_root / 'data' / 'metadata' / 'stock_list.json'
    
    print("\n" + "="*70)
    print("FINAL FULL-SCALE TREND FOLLOWING BACKTEST")
    print("="*70)
    print(f"ADX Threshold: {settings.ADX_THRESHOLD}")
    print(f"Profit Target: {settings.PROFIT_TARGET}")
    print(f"ATR Filter: {settings.ATR_FILTER_ENABLED} ({settings.ATR_MIN_PCT}%)")
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
            adx_period=settings.ADX_PERIOD,
            sma_period=settings.SMA_PERIOD,
            atr_period=settings.ATR_PERIOD
        )
        df = df.dropna(subset=['ADX', 'DIPlus', 'DIMinus', 'SMA200'])
        if len(df) > 0: stock_data[ticker] = df

    # Initialize Detector
    detector = SignalDetector(
        adx_threshold=settings.ADX_THRESHOLD,
        profit_target=settings.PROFIT_TARGET,
        sma_period=settings.SMA_PERIOD,
        volume_filter_enabled=settings.VOLUME_FILTER_ENABLED,
        volume_multiplier=settings.VOLUME_MULTIPLIER,
        atr_filter_enabled=settings.ATR_FILTER_ENABLED,
        atr_min_pct=settings.ATR_MIN_PCT
    )

    # Initialize Backtester (Full Capacity)
    backtester = Backtester(
        detector=detector,
        start_date='2023-01-01',
        end_date='2024-12-31',
        initial_capital=100000.0,
        position_size_pct=0.05, 
        max_positions=20,        
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
