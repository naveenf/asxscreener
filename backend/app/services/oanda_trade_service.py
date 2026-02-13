"""
OANDA Trade Service (Hardened)

Handles risk management, unit calculation, and trade orchestration.
"""

import logging
from typing import List, Dict, Optional, Any
from .oanda_price import OandaPriceService
from ..config import settings
from ..firebase_setup import db
from google.cloud import firestore
from datetime import datetime

logger = logging.getLogger(__name__)

class OandaTradeService:
    @staticmethod
    def calculate_units(symbol: str, entry_price: float, stop_loss: float, balance_aud: float, margin_avail_aud: float) -> int:
        """
        Calculate position units based on 2% risk of AUD balance.
        Formula: Units = (Risk_AUD) / (Risk_per_Unit_AUD)
        """
        try:
            risk_pct = 0.02
            risk_amount_aud = balance_aud * risk_pct
            
            # Risk per unit in Quote currency
            risk_per_unit_quote = abs(entry_price - stop_loss)
            if risk_per_unit_quote == 0:
                return 0

            # Convert Risk per unit to AUD
            quote_currency = symbol.split('_')[-1]
            
            if quote_currency == 'AUD':
                quote_to_aud = 1.0
            else:
                # Try AUD_<Quote> or <Quote>_AUD
                quote_to_aud = None
                
                # Check AUD_<Quote>
                pair_name = f"AUD_{quote_currency}"
                rate = OandaPriceService.get_current_price(pair_name)
                if rate:
                    quote_to_aud = 1.0 / rate
                else:
                    # Check <Quote>_AUD
                    pair_name = f"{quote_currency}_AUD"
                    rate = OandaPriceService.get_current_price(pair_name)
                    if rate:
                        quote_to_aud = rate

                if quote_to_aud is None:
                    logger.error(f"FAIL-SAFE: Could not fetch conversion rate for {quote_currency} to AUD. Aborting trade for {symbol}.")
                    return 0

            risk_per_unit_aud = risk_per_unit_quote * quote_to_aud
            
            # Fetch precision for units (some accounts allow fractional units for indices/commodities)
            inst_info = OandaPriceService.get_instrument_details(symbol)
            unit_precision = 0
            if inst_info:
                unit_precision = int(inst_info.get('tradeUnitsPrecision', 0))

            units = round(risk_amount_aud / risk_per_unit_aud, unit_precision)
            
            # --- MINIMUM UNIT INJECTION (For Small Accounts) ---
            if units == 0:
                # Calculate the smallest possible unit (e.g., 1 or 0.01)
                min_unit = round(10**(-unit_precision), unit_precision) if unit_precision > 0 else 1
                
                # Check if 1 min_unit is at least within "Extreme Risk" (e.g. 10% of balance)
                # and verify we have the margin for it.
                min_unit_risk_pct = (min_unit * risk_per_unit_aud) / balance_aud
                if min_unit_risk_pct <= 0.10: # Max 10% risk for smallest unit
                    units = min_unit
                    logger.info(f"RISK OVERRIDE [{symbol}]: Risk-based units were 0, allowing minimum unit {units} (Risk: {min_unit_risk_pct*100:.1f}%)")
                else:
                    logger.warning(f"RISK BLOCK [{symbol}]: Min unit {min_unit} risk ({min_unit_risk_pct*100:.1f}%) exceeds absolute safety limit (10%)")
                    return 0

            logger.info(f"RISK CALC [{symbol}]: Risk Amount: {risk_amount_aud:.2f} AUD | Risk/Unit: {risk_per_unit_aud:.4f} AUD | Units: {units} (Precision: {unit_precision})")

            # --- Margin Requirement Check ---
            if inst_info:
                margin_rate = float(inst_info.get('marginRate', 0.1))
                # Required margin in AUD = Units * EntryPrice * QuoteToAUD * MarginRate
                required_margin = units * entry_price * quote_to_aud * margin_rate
                
                # Safety: Don't use more than 50% of REMAINING available margin for a single trade
                margin_limit = margin_avail_aud * 0.5
                
                if units > 0 and required_margin > margin_limit:
                    units = round(margin_limit / (entry_price * quote_to_aud * margin_rate), unit_precision)
                    logger.info(f"Units capped by available margin for {symbol}: {units} (Required: {required_margin:.2f} > Limit: {margin_limit:.2f})")
                
                # FINAL VALIDATION: If we are taking high risk (>5%), log a warning
                actual_risk_pct = (units * risk_per_unit_aud) / balance_aud
                if actual_risk_pct > 0.05:
                    logger.warning(f"⚠️ HIGH RISK TRADE [{symbol}]: This trade risks {actual_risk_pct*100:.1f}% of your account.")

            return units

        except Exception as e:
            logger.error(f"Error calculating units for {symbol}: {e}")
            return 0

    @classmethod
    def execute_trades(cls, signals: List[Dict[str, Any]]):
        """
        Orchestrate trade execution for authorized users.
        """
        # 1. Authorization & Environment Check
        auth_email = settings.AUTHORIZED_AUTO_TRADER_EMAIL
        if not auth_email:
            logger.info("Auto-trading skipped: No authorized email configured.")
            return

        # 2. Filter & Rank Signals
        valid_signals = [s for s in signals if s.get('stop_loss') and s.get('take_profit')]
        if not valid_signals:
            return

        # Sort by score descending (Higher score = higher priority)
        valid_signals.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        # 3. Get Account Info (Source of Truth for Balance & Margin)
        summary = OandaPriceService.get_account_summary()
        if not summary:
            logger.error("Could not fetch Oanda account summary. Aborting auto-trade execution.")
            return

        balance = float(summary.get('balance', 0))
        margin_avail = float(summary.get('marginAvailable', 0))
        open_trades_count = int(summary.get('openTradeCount', 0))

        if open_trades_count >= settings.MAX_CONCURRENT_TRADES:
            logger.info(f"Max concurrent trades reached ({open_trades_count}). Skipping new entries.")
            return

        # 4. Source of Truth for Existing Positions
        # Check Oanda directly to prevent duplicates if Firestore failed last time
        oanda_open_symbols = OandaPriceService.get_open_trades()
        
        # Also check Firestore for local tracking and sync if needed
        try:
            portfolio_ref = db.collection('users').document(auth_email).collection('forex_portfolio')
            open_docs = list(portfolio_ref.where(filter=firestore.FieldFilter('status', '==', 'OPEN')).stream())
            
            for doc in open_docs:
                data = doc.to_dict()
                symbol = data.get('symbol')
                if symbol not in oanda_open_symbols:
                    # Sync: Oanda says it's closed, but Firestore says it's open
                    logger.info(f"SYNC: {symbol} found open in Firestore but not in Oanda. Marking as CLOSED.")
                    doc.reference.update({
                        'status': 'CLOSED',
                        'sell_price': 0,
                        'sell_date': datetime.utcnow().strftime("%Y-%m-%d"),
                        'notes': (data.get('notes', '') or '') + " | Auto-closed: Not found in Oanda open trades."
                    })
        except Exception as e:
            logger.error(f"Error fetching/syncing Firestore portfolio: {e}")

        # Absolute Truth: Use Oanda for "already open" check
        existing_symbols = list(oanda_open_symbols)

        # 5. Execute top N signals
        executed_count = 0
        limit = settings.MAX_CONCURRENT_TRADES - len(oanda_open_symbols)
        
        for signal in valid_signals:
            if executed_count >= limit:
                break
                
            symbol = signal['symbol']
            if symbol in existing_symbols:
                logger.info(f"Skipping {symbol}: Trade already open in Oanda.")
                continue

            # Calculate Units with margin awareness
            entry_price = signal['price']
            stop_loss = signal['stop_loss']
            take_profit = signal['take_profit']
            direction = signal['signal']
            
            units = cls.calculate_units(symbol, entry_price, stop_loss, balance, margin_avail)
            if units <= 0:
                logger.warning(f"Calculated 0 units for {symbol}. Insufficient risk/margin.")
                continue

            # Adjust units for direction
            oanda_units = units if direction == 'BUY' else -units

            logger.info(f"EXECUTION: {direction} {symbol} ({units} units) | Risk 2% | Balance: {balance:.2f} AUD")
            
            # Place Order
            response = OandaPriceService.place_market_order(symbol, oanda_units, stop_loss, take_profit)
            
            if response and 'orderFillTransaction' in response:
                fill = response['orderFillTransaction']
                exec_price = float(fill.get('price'))
                trade_id = fill.get('id')
                
                logger.info(f"SUCCESS: {symbol} Trade ID {trade_id} filled at {exec_price}")
                
                # Add to Firestore Portfolio (Local Sync)
                cls._log_to_portfolio(auth_email, signal, units, exec_price, trade_id)
                executed_count += 1
                existing_symbols.append(symbol)
            else:
                logger.error(f"FAILURE: Order placement for {symbol} failed.")

    @staticmethod
    def _log_to_portfolio(email: str, signal: Dict, units: int, exec_price: float, trade_id: str):
        """Add the executed trade to the user's Firestore portfolio."""
        try:
            portfolio_ref = db.collection('users').document(email).collection('forex_portfolio')
            
            doc_data = {
                'symbol': signal['symbol'],
                'direction': signal['signal'],
                'buy_date': datetime.utcnow().strftime("%Y-%m-%d"),
                'buy_price': exec_price,
                'quantity': units,
                'notes': f"Auto-traded via Bot. Strategy: {signal.get('strategy')}. Oanda ID: {trade_id}",
                'strategy': signal.get('strategy', 'Unknown'),
                'timeframe': signal.get('timeframe_used', 'Unknown'),
                'status': 'OPEN',
                'oanda_trade_id': trade_id,
                'stop_loss': signal.get('stop_loss'),
                'take_profit': signal.get('take_profit'),
                'created_at': datetime.utcnow()
            }
            
            portfolio_ref.add(doc_data)
            logger.info(f"SYNC: Logged trade {trade_id} to Firestore for {email}")
        except Exception as e:
            logger.error(f"DATABASE ERROR: Failed to log trade {trade_id} to Firestore: {e}")