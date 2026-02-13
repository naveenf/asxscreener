"""
Trade Closer Service

Handles automated closing of Oanda positions and syncing results to Firestore.
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

from ..firebase_setup import db
from ..config import settings
from .oanda_price import OandaPriceService

logger = logging.getLogger(__name__)

class TradeCloserService:
    AUDIT_LOG_PATH = settings.DATA_DIR / "processed" / "failed_closes.json"

    @classmethod
    def close_trade(cls, trade_id: str, symbol: str, reason: str) -> Dict[str, Any]:
        """
        Close an Oanda trade and return the result.
        
        Returns:
            Dict with success, close_price, pnl, actual_rr, error
        """
        result = {
            "success": False,
            "close_price": None,
            "pnl": 0.0,
            "actual_rr": 0.0,
            "error": None,
            "timestamp": datetime.utcnow().isoformat()
        }

        if not settings.AUTO_CLOSE_ENABLED:
            result["error"] = "Auto-close is disabled in settings"
            return result

        if settings.AUTO_CLOSE_DRY_RUN:
            logger.info(f"DRY RUN: Would close trade {trade_id} for {symbol} (Reason: {reason})")
            result["success"] = True
            result["error"] = "DRY RUN MODE"
            return result

        # 1. Idempotency Check
        if cls._is_already_attempted(trade_id):
            result["error"] = "Duplicate close attempt"
            return result

        # 2. Log Attempt
        cls._log_attempt(trade_id, symbol, reason)

        try:
            # 3. Call Oanda Price Service (Implementation in Task 2.1)
            # We expect OandaPriceService.close_trade to return Oanda response or None
            oanda_response = OandaPriceService.close_trade(trade_id)

            if oanda_response and 'orderFillTransaction' in oanda_response:
                fill = oanda_response['orderFillTransaction']
                result["success"] = True
                result["close_price"] = float(fill['price'])
                result["pnl"] = float(fill['pl'])
                
                # We'll need entry and SL to calculate R:R, which sync_firestore_position will handle
                logger.info(f"Successfully auto-closed trade {trade_id} at {result['close_price']} (PnL: {result['pnl']})")
            
            elif oanda_response and 'orderRejectTransaction' in oanda_response:
                reject = oanda_response['orderRejectTransaction']
                result["error"] = f"Trade close rejected: {reject.get('rejectReason', 'Unknown')}"
                cls._audit_failure(trade_id, symbol, reason, result["error"])
            
            else:
                # Handle 404 (already closed)
                trade_details = OandaPriceService.get_trade_details(trade_id)
                if not trade_details:
                    # Confirmed closed externally
                    result["success"] = True
                    result["error"] = "Already closed externally (SL/TP or manual)"
                    logger.info(f"Trade {trade_id} already closed externally")
                else:
                    result["error"] = "Failed to close trade via Oanda API (None response)"
                    cls._audit_failure(trade_id, symbol, reason, result["error"])

        except Exception as e:
            result["error"] = f"Exception during trade close: {str(e)}"
            logger.error(f"Error closing trade {trade_id}: {e}")
            cls._audit_failure(trade_id, symbol, reason, result["error"])

        return result

    @classmethod
    def sync_firestore_position(cls, user_email: str, doc_id: str, close_result: Dict[str, Any]):
        """Update Firestore with actual close data."""
        try:
            portfolio_ref = db.collection('users').document(user_email).collection('forex_portfolio')
            doc_ref = portfolio_ref.document(doc_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                logger.error(f"Firestore doc {doc_id} not found for user {user_email}")
                return

            item = doc.to_dict()
            
            update_data = {
                'status': 'CLOSED',
                'exit_signal': True,
                'exit_reason': item.get('exit_reason', '') + " (Auto-Closed)",
                'close_price': close_result.get('close_price'),
                'pnl': close_result.get('pnl', 0.0),
                'closed_at': datetime.utcnow(),
                'updated_at': datetime.utcnow(),
                'auto_closed': True
            }

            # Calculate actual R:R if possible
            entry = item.get('buy_price')
            sl = item.get('sl') or item.get('stop_loss')
            direction = item.get('direction', 'BUY')
            exit_price = close_result.get('close_price')

            if entry and sl and exit_price:
                actual_rr = cls.calculate_actual_rr(entry, exit_price, sl, direction)
                update_data['actual_rr'] = actual_rr

            doc_ref.update(update_data)
            logger.info(f"Synced Firestore position {doc_id} for user {user_email}")

        except Exception as e:
            logger.error(f"Error syncing Firestore for {doc_id}: {e}")

    @staticmethod
    def calculate_actual_rr(entry: float, exit_price: float, sl: float, direction: str) -> float:
        """Calculate achieved Risk:Reward ratio."""
        try:
            risk = abs(entry - sl)
            if risk == 0:
                return 0.0
            
            if direction.upper() == 'BUY':
                gain = exit_price - entry
            else:
                gain = entry - exit_price
                
            return round(gain / risk, 2)
        except Exception:
            return 0.0

    @classmethod
    def _is_already_attempted(cls, trade_id: str) -> bool:
        """Check if we've already tried to close this trade."""
        try:
            attempt_ref = db.collection('close_attempts').document(trade_id).get()
            return attempt_ref.exists
        except Exception:
            return False

    @classmethod
    def _log_attempt(cls, trade_id: str, symbol: str, reason: str):
        """Log the start of a close attempt to prevent double-execution."""
        try:
            db.collection('close_attempts').document(trade_id).set({
                'symbol': symbol,
                'reason': reason,
                'timestamp': datetime.utcnow(),
                'status': 'in_progress'
            })
        except Exception as e:
            logger.error(f"Error logging close attempt for {trade_id}: {e}")

    @classmethod
    def _audit_failure(cls, trade_id: str, symbol: str, reason: str, error: str):
        """Log failure to a JSON file for audit."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "trade_id": trade_id,
            "symbol": symbol,
            "exit_reason": reason,
            "error": error,
            "requires_manual_close": True
        }
        
        try:
            cls.AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            history = []
            if cls.AUDIT_LOG_PATH.exists():
                with open(cls.AUDIT_LOG_PATH, 'r') as f:
                    try:
                        history = json.load(f)
                    except json.JSONDecodeError:
                        history = []
            
            history.append(entry)
            
            with open(cls.AUDIT_LOG_PATH, 'w') as f:
                json.dump(history, f, indent=2)
                
        except Exception as e:
            logger.error(f"Critical: Failed to write audit log: {e}")
