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

from .indicators import load_and_calculate_indicators
from .signal_detector import SignalDetector


class StockScreener:
    """Main screener orchestrator."""

    def __init__(
        self,
        data_dir: Path,
        metadata_dir: Path,
        output_dir: Path,
        adx_period: int = 14,
        sma_period: int = 200,
        adx_threshold: float = 30.0
    ):
        """
        Initialize screener.

        Args:
            data_dir: Directory with CSV files
            metadata_dir: Directory with stock_list.json
            output_dir: Directory for output files
            adx_period: ADX calculation period
            sma_period: SMA calculation period
            adx_threshold: ADX threshold for entry signals
        """
        self.data_dir = Path(data_dir)
        self.metadata_dir = Path(metadata_dir)
        self.output_dir = Path(output_dir)
        self.adx_period = adx_period
        self.sma_period = sma_period
        self.adx_threshold = adx_threshold

        # Initialize signal detector
        self.detector = SignalDetector(
            adx_threshold=adx_threshold,
            profit_target=0.15,
            sma_period=sma_period
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
        Process a single stock.

        Args:
            stock: Stock info dict with ticker, name, sector

        Returns:
            Dict with processing results
        """
        ticker = stock['ticker']
        name = stock.get('name', ticker)

        result = {
            'ticker': ticker,
            'name': name,
            'sector': stock.get('sector'),
            'success': False,
            'signal': None,
            'error': None
        }

        try:
            # Load CSV and calculate indicators
            csv_path = self.data_dir / f"{ticker}.csv"

            if not csv_path.exists():
                result['error'] = 'CSV file not found'
                return result

            df = load_and_calculate_indicators(
                str(csv_path),
                adx_period=self.adx_period,
                sma_period=self.sma_period
            )

            if len(df) == 0:
                result['error'] = 'Empty data'
                return result

            # Analyze for signals
            signal = self.detector.analyze_stock(df, ticker, name)

            if signal:
                # Add sector to signal
                signal['sector'] = stock.get('sector')
                result['signal'] = signal

            result['success'] = True

        except Exception as e:
            result['error'] = str(e)

        return result

    def screen_all_stocks(self) -> Dict:
        """
        Screen all stocks for signals.

        Returns:
            Dict with signals and summary statistics
        """
        print("=" * 60)
        print("ASX Stock Screener")
        print("=" * 60)
        print(f"ADX Threshold: {self.adx_threshold}")
        print(f"ADX Period: {self.adx_period}")
        print(f"SMA Period: {self.sma_period}")
        print("=" * 60)
        print()

        # Load stock list
        stocks = self.load_stock_list()
        print(f"Loaded {len(stocks)} stocks\n")

        # Process each stock
        signals = []
        errors = []
        processed = 0

        for stock in stocks:
            ticker = stock['ticker']
            print(f"Processing {ticker}...", end=' ')

            result = self.process_stock(stock)
            processed += 1

            if result['success']:
                if result['signal']:
                    signals.append(result['signal'])
                    score = result['signal']['score']
                    print(f"✓ SIGNAL (score: {score:.1f})")
                else:
                    print("✓ No signal")
            else:
                error_msg = result.get('error', 'Unknown error')
                errors.append({'ticker': ticker, 'error': error_msg})
                print(f"✗ Error: {error_msg}")

        # Sort signals by score (highest first)
        signals.sort(key=lambda x: x['score'], reverse=True)

        # Summary
        print()
        print("=" * 60)
        print(f"Screening complete")
        print(f"Processed: {processed}/{len(stocks)}")
        print(f"Signals found: {len(signals)}")
        if errors:
            print(f"Errors: {len(errors)}")
        print("=" * 60)

        return {
            'generated_at': datetime.now().isoformat(),
            'total_stocks': len(stocks),
            'signals_count': len(signals),
            'signals': signals,
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
            print("Top Signals:")
            print(f"{'=' * 60}")
            for i, signal in enumerate(results['signals'][:5], 1):
                print(f"\n{i}. {signal['ticker']} - {signal['name']}")
                print(f"   Score: {signal['score']:.1f}")
                print(f"   Price: ${signal['current_price']:.2f}")
                print(f"   ADX: {signal['indicators']['ADX']:.1f}")
                print(f"   DI+: {signal['indicators']['DIPlus']:.1f}")
                print(f"   DI-: {signal['indicators']['DIMinus']:.1f}")
                if signal['indicators']['above_sma200']:
                    print(f"   ✓ Above 200 SMA")

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
