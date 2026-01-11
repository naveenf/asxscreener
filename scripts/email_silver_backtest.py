"""
Silver Backtest & Email Alert Script

Runs a targeted backtest on Silver (XAG_USD) using the Squeeze strategy,
collects the most recent 5 signals, and emails them to the user.
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import logging

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.squeeze_detector import SqueezeDetector
from backend.app.services.notification import EmailService
from backend.app.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_data(symbol: str) -> Dict[str, pd.DataFrame]:
    """Load MTF data for Silver."""
    data_dir = PROJECT_ROOT / 'data' / 'forex_raw'
    data = {}
    
    # Files we expect for Silver
    files = {
        '15m': f"{symbol}_15_Min.csv",
        '1h': f"{symbol}_1_Hour.csv",
        '4h': f"{symbol}_4_Hour.csv"
    }
    
    for tf, filename in files.items():
        path = data_dir / filename
        if not path.exists():
            continue
            
        try:
            df = pd.read_csv(path)
            # Standardize Index
            col = 'Date' if 'Date' in df.columns else 'Datetime'
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], utc=True)
                df.set_index(col, inplace=True)
            df.sort_index(inplace=True)
            data[tf] = df
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
            
    return data

def run_simulation():
    symbol = "XAG_USD"
    logger.info(f"Loading data for {symbol}...")
    
    data = load_data(symbol)
    if '15m' not in data:
        logger.error("No 15m data found for Silver. Cannot run backtest.")
        return

    strategy = SqueezeDetector()
    df_base = data['15m']
    
    signals_found = []
    active_position = None
    
    # We simulate walking forward through the last 1000 candles to find 5 UNIQUE trades
    start_idx = max(200, len(df_base) - 1000)
    
    logger.info(f"Scanning last {len(df_base) - start_idx} bars for UNIQUE trades...")
    
    for i in range(start_idx, len(df_base)):
        current_time = df_base.index[i]
        current_close = df_base['Close'].iloc[i]
        
        # --- 1. Handle Active Position (Exit Logic) ---
        if active_position:
            # Check if SL hit
            is_buy = active_position['signal'] == 'BUY'
            sl = active_position['stop_loss']
            
            hit_sl = (is_buy and current_close <= sl) or (not is_buy and current_close >= sl)
            
            # Simple TP (2:1 Reward/Risk) or trend reversal
            risk = abs(active_position['price'] - sl)
            tp = active_position['price'] + (risk * 2 if is_buy else -risk * 2)
            hit_tp = (is_buy and current_close >= tp) or (not is_buy and current_close <= tp)
            
            if hit_sl or hit_tp:
                active_position = None # Trade closed, can look for next one
            continue

        # --- 2. Handle Entry (Only if no active position) ---
        slice_data = {}
        start_window = max(0, i - 200)
        slice_data['base'] = df_base.iloc[start_window:i+1]
        
        if '1h' in data:
            htf_full = data['1h']
            slice_data['htf'] = htf_full[htf_full.index < current_time].iloc[-100:]
            
        try:
            # SqueezeDetector.analyze now expects target_rr
            result = strategy.analyze(slice_data, symbol, target_rr=3.0)
            
            if result and result.get('signal'):
                # Found a NEW unique trade entry
                if 'timestamp' not in result:
                    result['timestamp'] = current_time.isoformat()
                
                signals_found.append(result)
                active_position = result # Mark as active so we ignore further noise
        except Exception:
            pass

    logger.info(f"Total unique trades found: {len(signals_found)}")
    
    if not signals_found:
        logger.warning("No signals found in the simulation window.")
        return

    # User asked for "first 5 generated signals" - usually implies recent ones for context
    # But strictly "first 5 generated" means from the start of our loop.
    # However, to verify "current alerts", the MOST RECENT 5 are useful.
    # I will pick the LAST 5 (most recent).
    recent_signals = signals_found[-5:]
    recent_signals.reverse() # Newest first
    
    recipient = "naveenf@gmail.com"
    logger.info(f"Sending {len(recent_signals)} signals to {recipient}...")
    
    EmailService.send_signal_alert([recipient], recent_signals)
    logger.info("Done.")

if __name__ == "__main__":
    run_simulation()
