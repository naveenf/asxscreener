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
from .silver_sniper_detector import SilverSniperDetector
from .commodity_sniper_detector import CommoditySniperDetector
from .heiken_ashi_detector import HeikenAshiDetector
from .enhanced_sniper_detector import EnhancedSniperDetector
from .daily_orb_detector import DailyORBDetector

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
            "EnhancedSniper": EnhancedSniperDetector(),
            "TripleTrend": TripleTrendDetector(),
            "TrendFollowing": ForexDetector(),
            "Squeeze": SqueezeDetector(),
            "SilverSniper": SilverSniperDetector(),
            "DailyORB": DailyORBDetector(),
            "CommoditySniper": CommoditySniperDetector(),
            "HeikenAshi": HeikenAshiDetector()
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
            '5m': f"{symbol}_5_Min.csv",
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
        mode: str = 'dynamic'
    ):
        """Orchestrate full download and screening cycle."""
        # 1. Download fresh data
        script_path = project_root / "scripts" / "download_forex.py"
        print(f"Starting data download via subprocess: {script_path}")
        
        try:
            # Add timeout (e.g., 5 minutes) to prevent hanging forever
            subprocess.run([sys.executable, str(script_path)], check=True, timeout=300)
            print("Data download subprocess completed successfully.")
        except subprocess.TimeoutExpired:
            print("❌ Data download subprocess TIMED OUT after 300s. Proceeding with existing data.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Data download subprocess FAILED: {e}")
        except Exception as e:
            print(f"❌ Data download subprocess encountered unexpected error: {e}")

        # 2. Run screener
        screener = ForexScreener(
            data_dir=data_dir,
            config_path=config_path,
            output_path=output_path
        )
        return screener.screen_all(mode=mode)

    def load_pairs(self) -> List[Dict]:
        with open(self.config_path, 'r') as f:
            return json.load(f)['pairs']

    def screen_all(self, mode: str = 'dynamic') -> Dict:
        """
        Screen assets. 
        If mode='sniper', only screen assets that use Sniper or SilverSniper strategy.
        """
        pairs = self.load_pairs()
        all_signals = []
        all_prices = {} # Symbol -> Current Price
        
        # Load existing signals to avoid wiping out the others during a sniper-only run
        if mode == 'sniper' and self.output_path.exists():
            try:
                with open(self.output_path, 'r') as f:
                    old_results = json.load(f)
                    all_signals = old_results.get('signals', [])
                    all_prices = old_results.get('all_prices', {})
            except Exception:
                all_signals = []

        total_analyzed = 0

        # ACTIVE DEPLOYMENT FILTER
        # Only these assets are approved for live trading.
        # Others are commented out/skipped until further optimization.
        DEPLOYED_PAIRS = [
            "XAU_USD",   # Gold
            "XAG_USD",   # Silver
            "BCO_USD",   # Brent Crude Oil
            "WHEAT_USD", # Wheat
            "JP225_USD", # Nikkei 225
            "AUD_USD"    # Aussie Dollar
        ]

        print(f"\n🚀 Starting Dynamic Forex Screener ({len(pairs)} pairs loaded, Active: {len(DEPLOYED_PAIRS)}, mode={mode})")
        print(f"Strategy Map Loaded: {len(self.strategy_map)} entries")

        for pair in pairs:
            symbol = pair['symbol']

            # DEPLOYMENT CHECK: Skip if not in approved list
            if symbol not in DEPLOYED_PAIRS:
                # print(f"Skipping {symbol} - Not in active deployment list.")
                continue
            
            # Determine Strategy and Timeframe from Config
            # Support both single strategy (legacy) and multiple strategies (new)
            config = self.strategy_map.get(symbol, {"strategy": "TrendFollowing", "timeframe": "15m", "target_rr": 2.0})

            # Check if config has multiple strategies or single
            strategies_to_run = []
            if "strategies" in config:
                # Multiple strategies for this asset
                strategies_to_run = config["strategies"]
            else:
                # Legacy single strategy format
                strategies_to_run = [config]

            # Load Data once for all strategies
            raw_data = self._load_data_mtf(symbol)
            if not raw_data:
                continue

            # Record current price for exit tracking
            for tf_key, df in raw_data.items():
                if df is not None and 'Close' in df.columns and len(df) > 0:
                    all_prices[symbol] = float(df['Close'].iloc[-1])
                    break

            # Run all strategies for this symbol
            for strategy_config in strategies_to_run:
                strategy_name = strategy_config.get("strategy", "TrendFollowing")
                base_tf = strategy_config.get("timeframe", "15m")
                target_rr = strategy_config.get("target_rr", 2.0)
                params_dict = strategy_config.get("params", {})

                # FILTER: If sniper mode, skip non-sniper assets
                if mode == 'sniper' and strategy_name not in ['Sniper', 'SilverSniper', 'CommoditySniper', 'EnhancedSniper', 'DailyORB']:
                    continue

                # Map timeframes for the detector
                # 5m  -> base=5m,  htf=15m
                # 15m -> base=15m, htf=1h
                # 1h  -> base=1h,  htf=4h
                data = {}
                if base_tf == "1h":
                    data['base'] = raw_data.get('1h')
                    data['htf'] = raw_data.get('4h')
                elif base_tf == "5m":
                    data['base'] = raw_data.get('5m')
                    data['htf'] = raw_data.get('15m')
                    data['htf2'] = raw_data.get('1h') # Added for 3-TF sniper
                else: # 15m
                    data['base'] = raw_data.get('15m')
                    data['htf'] = raw_data.get('1h')
                    data['htf2'] = raw_data.get('4h') # Added for 3-TF sniper

                if data['base'] is None:
                    continue

                strategy = self.strategies.get(strategy_name, self.strategies["TrendFollowing"])

                try:
                    # Fetch Spread if in Sniper mode (Critical for Wheat/Commodities SL)
                    spread = 0.0
                    if mode == 'sniper':
                        from .oanda_price import OandaPriceService
                        spread = OandaPriceService.get_current_spread(symbol) or 0.0
                        if spread > 0:
                            print(f"   Debug: {symbol} Spread = {spread:.5f}")

                    # Analyze
                    result = strategy.analyze(data, symbol, target_rr=target_rr, spread=spread, params=params_dict)
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
                    print(f"Processing {symbol}... ✗ Error in {strategy_name}: {e}")

        # Rank all signals by score
        all_signals.sort(key=lambda x: x['score'], reverse=True)

        results = {
            "generated_at": datetime.now().isoformat(),
            "mode": "dynamic_mtf",
            "total_symbols": len(pairs),
            "analyzed_count": total_analyzed if mode != 'sniper' else len(all_signals),
            "signals_count": len(all_signals),
            "signals": all_signals,
            "all_prices": all_prices
        }
        
        # Save to file
        with open(self.output_path, 'w') as f:
            json.dump(results, f, indent=2)
            
        print(f"\n📊 Analysis Complete: {len(all_signals)} signals found")
        if all_signals:
            print(f"Top Signal: {all_signals[0]['symbol']} ({all_signals[0]['strategy']}) - Score: {all_signals[0]['score']}")

        return results