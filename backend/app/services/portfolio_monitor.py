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
from .new_breakout_detector import NewBreakoutDetector
from .daily_orb_detector import DailyORBDetector
from .heiken_ashi_detector import HeikenAshiDetector
from .enhanced_sniper_detector import EnhancedSniperDetector
from .silver_sniper_detector import SilverSniperDetector
from .commodity_sniper_detector import CommoditySniperDetector
from .triple_trend_detector import TripleTrendDetector
from .sniper_detector import SniperDetector
from .notification import EmailService
from .trade_closer import TradeCloserService
from .oanda_price import OandaPriceService

class PortfolioMonitor:
    def __init__(self):
        self.strategies = {
            "Squeeze": SqueezeDetector(),
            "TrendFollowing": ForexDetector(),
            "NewBreakout": NewBreakoutDetector(),
            "DailyORB": DailyORBDetector(),
            "HeikenAshi": HeikenAshiDetector(),
            "EnhancedSniper": EnhancedSniperDetector(),
            "SilverSniper": SilverSniperDetector(),
            "CommoditySniper": CommoditySniperDetector(),
            "TripleTrend": TripleTrendDetector(),
            "Sniper": SniperDetector()
        }
        self.data_dir = settings.DATA_DIR / "forex_raw"

    def _load_data_mtf(self, symbol: str, timeframes: List[str]) -> Dict[str, pd.DataFrame]:
        """Load specified timeframes (5m, 15m, 1h, 4h) data for a symbol."""
        data = {}
        files_map = {
            '5m': f"{symbol}_5_Min.csv",
            '15m': f"{symbol}_15_Min.csv",
            '1h': f"{symbol}_1_Hour.csv",
            '4h': f"{symbol}_4_Hour.csv"
        }
        
        for tf in timeframes:
            fname = files_map.get(tf)
            if not fname: continue
            
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
        Also syncs closed trades from Oanda back to Firestore.
        Updates Firestore and sends email if new signal detected.
        """
        if not user_email:
            return []

        # FIRST: Sync any closed trades from Oanda to Firestore
        self._sync_oanda_closed_trades(user_email)

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
            
            # Map strategy to base timeframe
            timeframe_map = {
                "SilverSniper": "5m",
                "CommoditySniper": "5m",
                "DailyORB": "15m",
                "NewBreakout": "15m",
                "EnhancedSniper": "15m",
                "HeikenAshi": "15m",
                "TripleTrend": "15m",
                "Sniper": "15m",
                "Squeeze": "15m",
                "TrendFollowing": "15m"
            }
            
            base_tf = timeframe_map.get(strategy_name, timeframe or "15m")
            
            # Determine required timeframes
            if base_tf == "5m":
                req_tfs = ["5m", "15m"]
            elif base_tf == "1h":
                req_tfs = ["1h", "4h"]
            else: # 15m
                req_tfs = ["15m", "1h"]

            # Load only required data
            raw_data = self._load_data_mtf(symbol, req_tfs)
            
            # Prepare Data Context based on Timeframe
            data = {}
            if base_tf == "5m":
                data['base'] = raw_data.get('5m')
                data['htf'] = raw_data.get('15m')
            elif base_tf == "1h":
                data['base'] = raw_data.get('1h')
                data['htf'] = raw_data.get('4h')
            else: # 15m (default)
                data['base'] = raw_data.get('15m')
                data['htf'] = raw_data.get('1h')
                
            if data.get('base') is None:
                continue
                
            # Check Exit
            result = strategy.check_exit(data, direction, buy_price)
            
            if result and result.get('exit_signal'):
                reason = result.get('reason')
                
                # Check if this is a NEW exit signal (not already flagged)
                if not item.get('exit_signal'):
                    print(f"🛑 Exit Signal Detected for {symbol} ({direction}): {reason}")
                    
                    # Attempt Oanda trade close
                    trade_id = item.get('oanda_trade_id')
                    if trade_id:
                        close_result = TradeCloserService.close_trade(
                            trade_id=trade_id,
                            symbol=symbol,
                            reason=reason
                        )

                        if close_result['success']:
                            # Update Firestore with actual close data
                            TradeCloserService.sync_firestore_position(
                                user_email, item_id, close_result
                            )
                            exits_found.append({
                                'symbol': symbol,
                                'signal': direction,
                                'price': buy_price,
                                'exit_price': close_result.get('close_price'),
                                'pnl': close_result.get('pnl'),
                                'actual_rr': close_result.get('actual_rr'),
                                'exit_reason': reason,
                                'auto_closed': True
                            })
                        else:
                            # Flag for manual review
                            portfolio_ref.document(item_id).update({
                                'exit_signal': True,
                                'exit_reason': reason + " | AUTO-CLOSE FAILED",
                                'requires_manual_close': True,
                                'close_failure_reason': close_result.get('error'),
                                'updated_at': datetime.utcnow()
                            })
                            
                            exits_found.append({
                                'symbol': symbol,
                                'signal': direction,
                                'price': buy_price,
                                'exit_reason': reason,
                                'requires_manual_close': True
                            })
                    else:
                        # No Oanda trade ID (manual entry or legacy) - just flag in DB
                        portfolio_ref.document(item_id).update({
                            'exit_signal': True,
                            'exit_reason': reason,
                            'updated_at': datetime.utcnow()
                        })
                        
                        exits_found.append({
                            'symbol': symbol,
                            'signal': direction,
                            'price': buy_price,
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

    def _sync_oanda_closed_trades(self, user_email: str):
        """
        Sync closed trades from Oanda API back to Firestore.
        This keeps Firestore in sync with actual Oanda account.
        """
        try:
            portfolio_ref = db.collection('users').document(user_email).collection('forex_portfolio')

            # Get all OPEN trades from Firestore
            open_docs = list(portfolio_ref.where('status', '==', 'OPEN').stream())

            if not open_docs:
                return

            synced_count = 0

            for doc in open_docs:
                data = doc.to_dict()
                trade_id = data.get('oanda_trade_id')

                if not trade_id:
                    continue

                # Check if trade is closed in Oanda
                closed_trades = OandaPriceService.get_closed_trades_by_id([trade_id])

                if closed_trades:
                    closed_trade = closed_trades[0]

                    # Update Firestore with exit data
                    doc.reference.update({
                        'status': 'CLOSED',
                        'sell_price': closed_trade.get('exit_price'),
                        'sell_date': closed_trade.get('closed_at'),
                        'pnl': closed_trade.get('pnl'),
                        'closed_by': 'OandaSync',
                        'updated_at': datetime.utcnow()
                    })

                    synced_count += 1
                    print(f"✅ Synced trade {trade_id}: Exit={closed_trade.get('exit_price')}, P&L={closed_trade.get('pnl')}")

            if synced_count > 0:
                print(f"📊 Synced {synced_count} closed trades from Oanda to Firestore")

        except Exception as e:
            print(f"⚠️ Error syncing Oanda trades: {e}")
