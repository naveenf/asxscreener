"""
Stock Screener Module

Orchestrates the screening process:
1. Load stock list
2. For each stock, load data and calculate indicators
3. Detect signals
4. Calculate scores
5. Generate output
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import sys

from .indicators import load_and_calculate_indicators, TechnicalIndicators
from .signal_detector import SignalDetector
from .mean_reversion_detector import MeanReversionDetector
from ..config import settings


class StockScreener:
    """Main screener orchestrator."""

    def __init__(
        self,
        data_dir: Path,
        metadata_dir: Path,
        output_dir: Path,
        adx_period: int = 14,
        sma_period: int = 200,
        adx_threshold: float = 30.0,
        enable_mean_reversion: bool = True
    ):
        """
        Initialize screener with dual strategy support.

        Args:
            data_dir: Directory with CSV files
            metadata_dir: Directory with stock_list.json
            output_dir: Directory for output files
            adx_period: ADX calculation period
            sma_period: SMA calculation period
            adx_threshold: ADX threshold for entry signals
            enable_mean_reversion: Enable mean reversion strategy
        """
        self.data_dir = Path(data_dir)
        self.metadata_dir = Path(metadata_dir)
        self.output_dir = Path(output_dir)
        self.adx_period = adx_period
        self.sma_period = sma_period
        self.adx_threshold = adx_threshold
        self.enable_mean_reversion = enable_mean_reversion

        # Initialize trend following detector
        self.trend_detector = SignalDetector(
            adx_threshold=settings.ADX_THRESHOLD,
            profit_target=settings.PROFIT_TARGET,
            sma_period=settings.SMA_PERIOD,
            volume_filter_enabled=settings.VOLUME_FILTER_ENABLED,
            volume_multiplier=settings.VOLUME_MULTIPLIER,
            atr_filter_enabled=settings.ATR_FILTER_ENABLED,
            atr_min_pct=settings.ATR_MIN_PCT
        )

        # Initialize mean reversion detector (if enabled)
        self.mean_rev_detector = None
        if enable_mean_reversion and settings.MEAN_REVERSION_ENABLED:
            self.mean_rev_detector = MeanReversionDetector(
                rsi_threshold=settings.RSI_THRESHOLD,
                profit_target=settings.MEAN_REVERSION_PROFIT_TARGET,
                bb_period=settings.BB_PERIOD,
                bb_std_dev=settings.BB_STD_DEV,
                rsi_period=settings.RSI_PERIOD,
                volume_filter_enabled=settings.VOLUME_FILTER_ENABLED,
                volume_multiplier=settings.VOLUME_MULTIPLIER
            )

    def load_stock_list(self) -> List[Dict]:
        """Load stock list from metadata."""
        stock_list_file = self.metadata_dir / 'stock_list.json'

        if not stock_list_file.exists():
            raise FileNotFoundError(f"Stock list not found: {stock_list_file}")

        with open(stock_list_file, 'r') as f:
            data = json.load(f)

        return data.get('stocks', [])

    def process_stock(self, stock: Dict) -> Dict:
        """
        Process a single stock with both strategies.

        Args:
            stock: Stock info dict with ticker, name, sector

        Returns:
            Dict with processing results (may contain multiple signals)
        """
        ticker = stock['ticker']
        name = stock.get('name', ticker)

        result = {
            'ticker': ticker,
            'name': name,
            'sector': stock.get('sector'),
            'success': False,
            'signals': [],  # Changed to list to support multiple strategies
            'error': None
        }

        try:
            # Load CSV and calculate ALL indicators (for both strategies)
            csv_path = self.data_dir / f"{ticker}.csv"

            if not csv_path.exists():
                result['error'] = 'CSV file not found'
                return result

            # Load raw data
            df = pd.read_csv(csv_path, parse_dates=['Date'], index_col='Date')

            # Add all indicators (ADX, SMA, ATR, RSI, BB)
            df = TechnicalIndicators.add_all_indicators(
                df,
                adx_period=settings.ADX_PERIOD,
                sma_period=settings.SMA_PERIOD,
                atr_period=settings.ATR_PERIOD,
                volume_period=settings.VOLUME_PERIOD,
                rsi_period=settings.RSI_PERIOD,
                bb_period=settings.BB_PERIOD,
                bb_std_dev=settings.BB_STD_DEV
            )

            if len(df) == 0:
                result['error'] = 'Empty data'
                return result

            # Run BOTH detectors
            signals = []

            # 1. Trend following strategy
            trend_signal = self.trend_detector.analyze_stock(df, ticker, name)
            if trend_signal:
                trend_signal['sector'] = stock.get('sector')
                trend_signal['strategy'] = 'trend_following'
                signals.append(trend_signal)

            # 2. Mean reversion strategy (if enabled)
            if self.mean_rev_detector:
                mr_signal = self.mean_rev_detector.analyze_stock(df, ticker, name)
                if mr_signal:
                    mr_signal['sector'] = stock.get('sector')
                    mr_signal['strategy'] = 'mean_reversion'
                    signals.append(mr_signal)

            result['signals'] = signals
            result['success'] = True

        except Exception as e:
            result['error'] = str(e)

        return result

    def screen_all_stocks(self) -> Dict:
        """
        Screen all stocks for signals using both strategies.

        Returns:
            Dict with signals and summary statistics
        """
        print("=" * 60)
        print("ASX Stock Screener - Dual Strategy")
        print("=" * 60)
        print(f"Strategies: Trend Following", end='')
        if self.mean_rev_detector:
            print(" + Mean Reversion")
        else:
            print()
        print(f"ADX Threshold: {self.adx_threshold}")
        print(f"RSI Threshold: {settings.RSI_THRESHOLD if self.mean_rev_detector else 'N/A'}")
        print("=" * 60)
        print()

        # Load stock list
        stocks = self.load_stock_list()
        print(f"Loaded {len(stocks)} stocks\n")

        # Process each stock
        all_signals = []
        errors = []
        processed = 0
        trend_count = 0
        mr_count = 0

        for stock in stocks:
            ticker = stock['ticker']
            print(f"Processing {ticker}...", end=' ')

            result = self.process_stock(stock)
            processed += 1

            if result['success']:
                if result['signals']:
                    # Add all signals from this stock
                    for signal in result['signals']:
                        all_signals.append(signal)
                        if signal.get('strategy') == 'trend_following':
                            trend_count += 1
                        elif signal.get('strategy') == 'mean_reversion':
                            mr_count += 1

                    # Show which strategies triggered
                    strategies = [s.get('strategy', 'unknown') for s in result['signals']]
                    scores = [s['score'] for s in result['signals']]
                    strategy_str = ', '.join([f"{s[:2].upper()}:{sc:.0f}" for s, sc in zip(strategies, scores)])
                    print(f"✓ SIGNALS ({strategy_str})")
                else:
                    print("✓ No signal")
            else:
                error_msg = result.get('error', 'Unknown error')
                errors.append({'ticker': ticker, 'error': error_msg})
                print(f"✗ Error: {error_msg}")

        # Sort ALL signals by score (highest first) - mixed strategies
        all_signals.sort(key=lambda x: x['score'], reverse=True)

        # Summary
        print()
        print("=" * 60)
        print(f"Screening complete")
        print(f"Processed: {processed}/{len(stocks)}")
        print(f"Total signals: {len(all_signals)}")
        print(f"  Trend Following: {trend_count}")
        print(f"  Mean Reversion: {mr_count}")
        if errors:
            print(f"Errors: {len(errors)}")
        print("=" * 60)

        return {
            'generated_at': datetime.now().isoformat(),
            'total_stocks': len(stocks),
            'signals_count': len(all_signals),
            'trend_following_count': trend_count,
            'mean_reversion_count': mr_count,
            'signals': all_signals,
            'errors': errors if errors else None
        }

    def save_signals(self, results: Dict, filename: str = 'signals.json'):
        """
        Save signals to JSON file.

        Args:
            results: Screening results
            filename: Output filename
        """
        output_path = self.output_dir / filename
        self.output_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nSignals saved to: {output_path}")

    def run(self):
        """Run the screener and save results."""
        results = self.screen_all_stocks()
        self.save_signals(results)

        # Print top signals
        if results['signals']:
            print(f"\n{'=' * 60}")
            print("Top Signals (All Strategies):")
            print(f"{'=' * 60}")
            for i, signal in enumerate(results['signals'][:10], 1):
                strategy = signal.get('strategy', 'unknown')
                strategy_badge = "📈" if strategy == 'trend_following' else "📉"

                print(f"\n{i}. {signal['ticker']} - {signal['name']} {strategy_badge}")
                print(f"   Strategy: {strategy.replace('_', ' ').title()}")
                print(f"   Score: {signal['score']:.1f}")
                print(f"   Price: ${signal['current_price']:.2f}")

                # Display strategy-specific indicators
                if strategy == 'trend_following':
                    print(f"   ADX: {signal['indicators']['ADX']:.1f}")
                    print(f"   DI+: {signal['indicators']['DIPlus']:.1f}")
                    print(f"   DI-: {signal['indicators']['DIMinus']:.1f}")
                    if signal['indicators'].get('above_sma200'):
                        print(f"   ✓ Above 200 SMA")
                elif strategy == 'mean_reversion':
                    print(f"   RSI: {signal['indicators']['RSI']:.1f}")
                    print(f"   BB Upper: ${signal['indicators']['BB_Upper']:.2f}")
                    print(f"   BB Distance: {signal['indicators']['BB_Distance_PCT']:.2f}%")

        return results


def main():
    """Command-line entry point."""
    # Project paths
    project_root = Path(__file__).parent.parent.parent.parent
    data_dir = project_root / 'data' / 'raw'
    metadata_dir = project_root / 'data' / 'metadata'
    output_dir = project_root / 'data' / 'processed'

    # Create and run screener
    screener = StockScreener(
        data_dir=data_dir,
        metadata_dir=metadata_dir,
        output_dir=output_dir,
        adx_period=14,
        sma_period=200,
        adx_threshold=30.0
    )

    screener.run()


if __name__ == '__main__':
    main()
