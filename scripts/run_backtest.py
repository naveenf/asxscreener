"""
CLI script to run backtests on ASX stock screener strategy.

Usage:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --start-date 2023-01-01 --end-date 2024-12-31
    python scripts/run_backtest.py --single-stock CBA.AX
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
from app.services.signal_detector import SignalDetector
from app.services.indicators import TechnicalIndicators
from app.config import Settings


def load_stock_data(
    data_dir: Path,
    stock_list_path: Path,
    start_date: str,
    end_date: str,
    single_stock: str = None,
    min_required_bars: int = 250
) -> dict:
    """
    Load and prepare stock data for backtesting.

    Args:
        data_dir: Path to data/raw directory
        stock_list_path: Path to stock_list.json
        start_date: Backtest start date
        end_date: Backtest end date
        single_stock: Optional ticker to backtest single stock
        min_required_bars: Minimum bars required for indicators

    Returns:
        Dict mapping ticker -> DataFrame with indicators
    """
    print("Loading stock data...")

    # Load stock list
    with open(stock_list_path) as f:
        stock_data_json = json.load(f)

    stocks = stock_data_json['stocks']

    # Filter to single stock if specified
    if single_stock:
        stocks = [s for s in stocks if s['ticker'] == single_stock]
        if not stocks:
            raise ValueError(f"Stock {single_stock} not found in stock list")

    stock_data = {}
    skipped = []

    for stock in stocks:
        ticker = stock['ticker']
        csv_path = data_dir / f"{ticker}.csv"

        if not csv_path.exists():
            skipped.append(f"{ticker} (file not found)")
            continue

        # Load CSV
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)

        # Check if we have sufficient data (we'll filter by date in backtester)
        if len(df) < min_required_bars:
            skipped.append(f"{ticker} (only {len(df)} bars)")
            continue

        # Calculate all indicators
        df = TechnicalIndicators.add_all_indicators(df)

        # Drop rows with NaN indicators (first ~200 rows for SMA200)
        df = df.dropna(subset=['ADX', 'DIPlus', 'DIMinus', 'SMA200'])

        if len(df) > 0:
            stock_data[ticker] = df

    print(f"Loaded {len(stock_data)} stocks")
    if skipped:
        print(f"Skipped {len(skipped)} stocks:")
        for s in skipped[:10]:  # Show first 10
            print(f"  - {s}")
        if len(skipped) > 10:
            print(f"  ... and {len(skipped) - 10} more")

    return stock_data


def save_results(results, metrics, output_dir: Path, run_id: str):
    """
    Save backtest results to files.

    Args:
        results: BacktestResults object
        metrics: PerformanceMetrics object
        output_dir: Output directory path
        run_id: Unique run identifier
    """
    # Create output directories
    trades_dir = output_dir / 'trades'
    metrics_dir = output_dir / 'metrics'
    equity_dir = output_dir / 'equity'

    trades_dir.mkdir(parents=True, exist_ok=True)
    metrics_dir.mkdir(parents=True, exist_ok=True)
    equity_dir.mkdir(parents=True, exist_ok=True)

    # Save trades
    trades_data = []
    for trade in results.trades:
        trades_data.append({
            'ticker': trade.ticker,
            'entry_date': trade.entry_date.strftime('%Y-%m-%d'),
            'exit_date': trade.exit_date.strftime('%Y-%m-%d'),
            'entry_price': round(trade.entry_price, 2),
            'exit_price': round(trade.exit_price, 2),
            'shares': trade.shares,
            'pnl': round(trade.pnl, 2),
            'pnl_pct': round(trade.pnl_pct, 2),
            'holding_days': trade.holding_days,
            'exit_reason': trade.exit_reason,
            'entry_score': round(trade.entry_score, 2),
            'entry_adx': round(trade.entry_adx, 2),
            'entry_di_plus': round(trade.entry_di_plus, 2),
            'entry_di_minus': round(trade.entry_di_minus, 2)
        })

    trades_file = trades_dir / f'{run_id}.json'
    with open(trades_file, 'w') as f:
        json.dump(trades_data, f, indent=2)

    print(f"Saved trades to: {trades_file}")

    # Save metrics
    metrics_data = metrics.to_dict()
    metrics_file = metrics_dir / f'{run_id}.json'

    with open(metrics_file, 'w') as f:
        json.dump(metrics_data, f, indent=2)

    print(f"Saved metrics to: {metrics_file}")

    # Save equity curve
    equity_file = equity_dir / f'{run_id}.csv'
    equity_df = results.equity_curve.copy()
    equity_df['date'] = equity_df['date'].dt.strftime('%Y-%m-%d')
    equity_df.to_csv(equity_file, index=False)

    print(f"Saved equity curve to: {equity_file}")


def main():
    """Main backtest runner."""
    import argparse

    parser = argparse.ArgumentParser(description='Run backtest on ASX stock screener strategy')
    parser.add_argument('--start-date', default='2023-01-01', help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', default='2024-12-31', help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--single-stock', help='Test single stock (e.g., CBA.AX)')
    parser.add_argument('--initial-capital', type=float, default=100000.0, help='Initial capital')
    parser.add_argument('--position-size-pct', type=float, default=0.20, help='Position size as % of capital')
    parser.add_argument('--max-positions', type=int, default=5, help='Max concurrent positions')
    parser.add_argument('--adx-threshold', type=float, default=30.0, help='ADX threshold for entry')
    parser.add_argument('--profit-target', type=float, default=0.15, help='Profit target (0.15 = 15%)')

    args = parser.parse_args()

    # Setup paths
    project_root = Path(__file__).parent.parent
    data_dir = project_root / 'data' / 'raw'
    stock_list_path = project_root / 'data' / 'metadata' / 'stock_list.json'
    output_dir = project_root / 'data' / 'backtest_results'

    # Generate run ID
    run_id = f"backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("\n" + "="*70)
    print("ASX STOCK SCREENER - BACKTEST")
    print("="*70)
    print(f"Run ID: {run_id}")
    print(f"Date Range: {args.start_date} to {args.end_date}")
    print(f"Initial Capital: ${args.initial_capital:,.2f}")
    print(f"Position Size: {args.position_size_pct * 100}% per position")
    print(f"Max Positions: {args.max_positions}")
    print(f"ADX Threshold: {args.adx_threshold}")
    print(f"Profit Target: {args.profit_target * 100}%")
    print("="*70 + "\n")

    # Load stock data
    stock_data = load_stock_data(
        data_dir=data_dir,
        stock_list_path=stock_list_path,
        start_date=args.start_date,
        end_date=args.end_date,
        single_stock=args.single_stock
    )

    if not stock_data:
        print("ERROR: No valid stock data loaded. Exiting.")
        return

    # Initialize signal detector with filter settings from config
    settings = Settings()
    detector = SignalDetector(
        adx_threshold=args.adx_threshold,
        profit_target=args.profit_target,
        sma_period=200,
        volume_filter_enabled=settings.VOLUME_FILTER_ENABLED,
        volume_multiplier=settings.VOLUME_MULTIPLIER,
        atr_filter_enabled=settings.ATR_FILTER_ENABLED,
        atr_min_pct=settings.ATR_MIN_PCT
    )

    # Initialize backtester
    backtester = Backtester(
        detector=detector,
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.initial_capital,
        position_size_pct=args.position_size_pct,
        max_positions=args.max_positions,
        slippage_pct=0.001,  # 0.1%
        commission=10.0      # $10
    )

    # Run backtest
    print("\nRunning backtest...")
    results = backtester.run(stock_data)

    # Calculate metrics
    print("\nCalculating performance metrics...")
    metrics = PerformanceMetrics(
        trades=results.trades,
        equity_curve=results.equity_curve,
        initial_capital=args.initial_capital
    )

    # Print summary
    metrics.print_summary()

    # Save results
    print("\nSaving results...")
    save_results(results, metrics, output_dir, run_id)

    print("\n" + "="*70)
    print("BACKTEST COMPLETE")
    print("="*70)
    print(f"\nResults saved to: {output_dir}")
    print(f"Run ID: {run_id}\n")


if __name__ == '__main__':
    main()
