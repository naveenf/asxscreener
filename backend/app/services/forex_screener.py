"""
Forex Screener Orchestrator

Manages the screening process for Forex and Commodities.
"""

import pandas as pd
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from .indicators import TechnicalIndicators
from .forex_detector import ForexDetector

class ForexScreener:
    def __init__(
        self,
        data_dir: Path,
        config_path: Path,
        output_path: Path
    ):
        self.data_dir = data_dir
        self.config_path = config_path
        self.output_path = output_path
        self.detector = ForexDetector()

    def load_pairs(self) -> List[Dict]:
        with open(self.config_path, 'r') as f:
            return json.load(f)['pairs']

    def screen_all(self) -> Dict:
        pairs = self.load_pairs()
        signals = []
        total_analyzed = 0

        for pair in pairs:
            symbol = pair['symbol']
            csv_path = self.data_dir / f"{symbol}.csv"

            if not csv_path.exists():
                continue

            try:
                # Load data - handle yfinance multi-row headers
                df = pd.read_csv(csv_path, header=[0, 1, 2], index_col=0)
                if df.empty:
                    continue
                
                # Flatten columns: ('Close', 'EURUSD=X', '...') -> 'Close'
                df.columns = df.columns.get_level_values(0)
                
                # Setup index
                df.index = pd.to_datetime(df.index)
                df.sort_index(inplace=True)

                # Add indicators
                df = TechnicalIndicators.add_all_indicators(df)
                
                # Analyze
                result = self.detector.analyze(
                    df, 
                    symbol, 
                    pair['name'], 
                    pair['type']
                )
                
                total_analyzed += 1
                if result:
                    print(f"Processing {symbol}... ✓ SIGNAL ({result['signal']} {result['score']})")
                    signals.append(result)
                else:
                    print(f"Processing {symbol}... ✓ No signal")

            except Exception as e:
                print(f"Processing {symbol}... ✗ Error: {e}")

        # Final results
        results = {
            "generated_at": datetime.now().isoformat(),
            "total_symbols": len(pairs),
            "analyzed_count": total_analyzed,
            "signals_count": len(signals),
            "signals": signals
        }

        # Save to file
        with open(self.output_path, 'w') as f:
            json.dump(results, f, indent=2)

        return results
