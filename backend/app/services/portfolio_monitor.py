"""
Portfolio Monitor Service

Monitors open portfolio positions for exit signals based on their strategy.
"""

import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
from google.cloud import firestore

from ..firebase_setup import db
from ..config import settings
from .squeeze_detector import SqueezeDetector
from .forex_detector import ForexDetector
from .notification import EmailService

class PortfolioMonitor:
    def __init__(self):
        self.strategies = {
            "Squeeze": SqueezeDetector(),
            "TrendFollowing": ForexDetector()
        }
        self.data_dir = settings.DATA_DIR / "forex_raw"

    def _load_data_mtf(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """Load 15m, 1h, 4h data for a symbol."""
        data = {}
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
                except Exception as e:
                    print(f"Error loading {fname}: {e}")
        return data

    def check_portfolio_exits(self, user_email: str) -> List[Dict]:
        """
        Check all open positions for a user and detect exit signals.
        Updates Firestore and sends email if new signal detected.
        """
        if not user_email:
            return []

        portfolio_ref = db.collection('users').document(user_email).collection('forex_portfolio')
        docs = portfolio_ref.where('status', '==', 'OPEN').stream()
        
        exits_found = []
        updates_made = 0
        
        for doc in docs:
            item = doc.to_dict()
            item_id = doc.id
            symbol = item.get('symbol')
            direction = item.get('direction', 'BUY')
            buy_price = item.get('buy_price', 0.0)
            
            # Default to Squeeze if unknown (Legacy Support)
            strategy_name = item.get('strategy') or "Squeeze"
            timeframe = item.get('timeframe') or "15m"
            
            strategy = self.strategies.get(strategy_name, self.strategies["Squeeze"])
            
            # Load Data
            raw_data = self._load_data_mtf(symbol)
            
            # Prepare Data Context based on Timeframe
            data = {}
            if timeframe == "1h":
                data['base'] = raw_data.get('1h')
                data['htf'] = raw_data.get('4h')
            else: # Default 15m
                data['base'] = raw_data.get('15m')
                data['htf'] = raw_data.get('1h')
                
            if data.get('base') is None:
                continue
                
            # Check Exit
            result = strategy.check_exit(data, direction, buy_price)
            
            if result and result.get('exit_signal'):
                reason = result.get('reason')
                
                # Check if this is a NEW exit signal
                if not item.get('exit_signal'):
                    print(f"🛑 Exit Signal Detected for {symbol} ({direction}): {reason}")
                    
                    # Update DB
                    portfolio_ref.document(item_id).update({
                        'exit_signal': True,
                        'exit_reason': reason,
                        'updated_at': datetime.utcnow()
                    })
                    
                    exits_found.append({
                        'symbol': symbol,
                        'signal': direction, # "Original Side"
                        'price': buy_price, # "Entry Price"
                        'exit_reason': reason
                    })
                    updates_made += 1
            elif item.get('exit_signal'): 
                # Signal disappeared (e.g. price moved back above BB Middle)
                # Option: Clear the signal? Or keep it sticky?
                # User preference: "You want the Exit Signal to persist in the DB once found... until cleared or re-checked"
                # If "re-checked" implies it can be cleared if condition false, then we should clear it.
                # However, the user said "mostly he will close... if the user ignores, it will remain in the db".
                # This suggests sticky behavior. I will NOT clear it automatically for now.
                pass

        # Send Email Alert for NEW exits
        if exits_found:
            print(f"Sending email for {len(exits_found)} new exit signals...")
            EmailService.send_exit_alert([user_email], exits_found)
            
        return exits_found
