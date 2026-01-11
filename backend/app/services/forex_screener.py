"""
Forex Screener Orchestrator

Manages the screening process for Forex and Commodities using
Dynamic Strategy Selection based on Backtest Arena results.
"""

import pandas as pd
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy
from .forex_detector import ForexDetector
from .sniper_detector import SniperDetector
from .triple_trend_detector import TripleTrendDetector
from .squeeze_detector import SqueezeDetector

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

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
        
        # Initialize Strategies
        self.strategies: Dict[str, ForexStrategy] = {
            "Sniper": SniperDetector(),
            "TripleTrend": TripleTrendDetector(),
            "TrendFollowing": ForexDetector(),
            "Squeeze": SqueezeDetector()
        }
        
        # Load Strategy Map
        self.strategy_map = self._load_strategy_map()

    def _load_strategy_map(self) -> Dict[str, str]:
        path = PROJECT_ROOT / 'data' / 'metadata' / 'best_strategies.json'
        if path.exists():
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        print("⚠️ No best_strategies.json found. Defaulting to TrendFollowing.")
        return {}

    def _load_data_mtf(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """Load 15m, 1h, 4h data."""
        data = {}
        # Try both Oanda format (from download_forex.py) and yfinance (fallback)
        # Assuming download_forex.py creates {symbol}_15_Min.csv etc.
        
        files = {
            '15m': f"{symbol}_15_Min.csv",
            '1h': f"{symbol}_1_Hour.csv",
            '4h': f"{symbol}_4_Hour.csv"
        }
        
        for tf, fname in files.items():
            path = self.data_dir / fname
            if path.exists():
                try:
                    df = pd.read_csv(path)
                    col = 'Date' if 'Date' in df.columns else 'Datetime'
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], utc=True)
                        df.set_index(col, inplace=True)
                        df.sort_index(inplace=True)
                        data[tf] = df
                except Exception:
                    pass
        
        return data

    @staticmethod
    def run_orchestrated_refresh(
        project_root: Path,
        data_dir: Path,
        config_path: Path,
        output_path: Path,
        mode: str = 'dynamic' # Deprecated param kept for compatibility
    ):
        """Orchestrate full download and screening cycle."""
        # 1. Download fresh data
        script_path = project_root / "scripts" / "download_forex.py"
        subprocess.run([sys.executable, str(script_path)], check=True)

        # 2. Run screener
        screener = ForexScreener(
            data_dir=data_dir,
            config_path=config_path,
            output_path=output_path
        )
        return screener.screen_all()

    def load_pairs(self) -> List[Dict]:
        with open(self.config_path, 'r') as f:
            return json.load(f)['pairs']

    def screen_all(self) -> Dict:
        pairs = self.load_pairs()
        all_signals = []
        total_analyzed = 0

        print(f"\n🚀 Starting Dynamic Forex Screener ({len(pairs)} pairs)")
        print(f"Strategy Map Loaded: {len(self.strategy_map)} entries")

        for pair in pairs:
            symbol = pair['symbol']
            
            # Load Data
            raw_data = self._load_data_mtf(symbol)
            if not raw_data:
                continue

            # Determine Strategy and Timeframe from Config
            config = self.strategy_map.get(symbol, {"strategy": "TrendFollowing", "timeframe": "15m", "target_rr": 2.0})
            strategy_name = config.get("strategy", "TrendFollowing")
            base_tf = config.get("timeframe", "15m")
            target_rr = config.get("target_rr", 2.0)
            
            # Map timeframes for the detector
            # 15m -> base=15m, htf=1h
            # 1h  -> base=1h,  htf=4h
            data = {}
            if base_tf == "1h":
                data['base'] = raw_data.get('1h')
                data['htf'] = raw_data.get('4h')
            else:
                data['base'] = raw_data.get('15m')
                data['htf'] = raw_data.get('1h')

            if data['base'] is None:
                continue

            strategy = self.strategies.get(strategy_name, self.strategies["TrendFollowing"])
            
            try:
                # Analyze
                result = strategy.analyze(data, symbol, target_rr=target_rr)
                total_analyzed += 1

                if result and result.get('signal'):
                    # Add pair metadata
                    result['name'] = pair.get('name', symbol)
                    result['type'] = pair.get('type', 'Unknown')
                    result['timeframe_used'] = base_tf
                    
                    print(f"Processing {symbol}... ✓ {result['signal']} ({strategy_name})")
                    all_signals.append(result)
                else:
                    print(f"Processing {symbol}... ✓ No signal ({strategy_name})")

            except Exception as e:
                print(f"Processing {symbol}... ✗ Error: {e}")

        # Rank all signals by score
        all_signals.sort(key=lambda x: x['score'], reverse=True)

        results = {
            "generated_at": datetime.now().isoformat(),
            "mode": "dynamic_mtf",
            "total_symbols": len(pairs),
            "analyzed_count": total_analyzed,
            "signals_count": len(all_signals),
            "signals": all_signals
        }
        
        # Save to file
        with open(self.output_path, 'w') as f:
            json.dump(results, f, indent=2)
            
        print(f"\n📊 Analysis Complete: {len(all_signals)} signals found")
        if all_signals:
            print(f"Top Signal: {all_signals[0]['symbol']} ({all_signals[0]['strategy']}) - Score: {all_signals[0]['score']}")

        return results