"""
Background Tasks Service

Contains logic for scheduled and manual background tasks.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from .screener import StockScreener
from .market_data import update_all_stocks_data
from .insider_trades import InsiderTradesService
from .forex_screener import ForexScreener
from .oanda_trade_service import OandaTradeService
from .oanda_price import OandaPriceService
from .portfolio_monitor import PortfolioMonitor
from .notification import EmailService
from .refresh_manager import refresh_manager
from .market_close_schedule import get_all_preclose_pairs
from ..firebase_setup import db
from google.cloud import firestore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pre-close state
# ---------------------------------------------------------------------------
# Module-level set of pair symbols currently in the entry-block window.
# Written by run_preclose_check(), read by run_forex_refresh_task().
PRECLOSE_BLOCKED_PAIRS: set = set()

# Simple flag to prevent concurrent pre-close checks
_preclose_lock = threading.Lock()

def run_stock_refresh_task():
    """Logic for stock refresh."""
    task_id = str(uuid.uuid4())[:8]
    logger.info(f"[{task_id}] Starting stock refresh task at {datetime.now()}")
    
    # Acquire lock or skip if already running
    if not refresh_manager.stocks_lock.acquire(blocking=False):
        logger.warning(f"[{task_id}] Stock refresh already in progress (lock held), skipping.")
        return

    try:
        refresh_manager.start_stocks_refresh()
        
        # Create screener
        screener = StockScreener(
            data_dir=settings.RAW_DATA_DIR,
            metadata_dir=settings.METADATA_DIR,
            output_dir=settings.PROCESSED_DATA_DIR
        )
        
        # 1. Update data from yfinance
        stocks = screener.load_stock_list()
        tickers = [s['ticker'] for s in stocks]
        
        logger.info(f"[{task_id}] Updating data for {len(tickers)} tickers...")
        update_results = update_all_stocks_data(tickers, settings.RAW_DATA_DIR)
        success_count = sum(1 for r in update_results.values() if r)
        logger.info(f"[{task_id}] Successfully updated {success_count}/{len(tickers)} CSV files")

        # 2. Run screener
        logger.info(f"[{task_id}] Running screener...")
        results = screener.screen_all_stocks()
        screener.save_signals(results)
        
        # 3. Update Insider Trades
        logger.info(f"[{task_id}] Updating insider trades...")
        insider_service = InsiderTradesService(settings.PROCESSED_DATA_DIR / 'insider_trades.json')
        insider_service.scrape_and_update()

        refresh_manager.complete_stocks_refresh()
        logger.info(f"[{task_id}] Stock refresh task complete. Found {results['signals_count']} signals.")

    except Exception as e:
        logger.error(f"[{task_id}] Stock refresh task failed: {e}")
        refresh_manager.complete_stocks_refresh(error=str(e))
    finally:
        refresh_manager.stocks_lock.release()

def run_forex_refresh_task(mode: str = 'dynamic'):
    """Logic for forex refresh."""
    task_id = str(uuid.uuid4())[:8]
    logger.info(f"[{task_id}] Starting forex refresh task ({mode}) at {datetime.now()}")
    
    # Acquire lock or skip if already running
    if not refresh_manager.forex_lock.acquire(blocking=False):
        logger.warning(f"[{task_id}] Forex refresh already in progress (lock held), skipping ({mode}).")
        return

    try:
        refresh_manager.start_forex_refresh()

        # Fetch user override config from Firestore
        disabled_combos = set()
        direction_overrides = {}
        try:
            doc = db.collection("config").document("strategy_overrides").get()
            if doc.exists:
                overrides_data = doc.to_dict()
                disabled_combos = set(overrides_data.get("disabled", []))
                direction_overrides = overrides_data.get("direction_overrides", {})
                logger.info(f"[{task_id}] Loaded {len(disabled_combos)} disabled combos, {len(direction_overrides)} direction overrides from Firestore")
        except Exception as e:
            logger.warning(f"[{task_id}] Could not load strategy overrides, running all: {e}")

        # Snapshot current Oanda balance to Firestore for historical ROI tracking
        try:
            OandaPriceService.snapshot_balance_to_firestore()
        except Exception as be:
            logger.warning(f"[{task_id}] Balance snapshot failed (non-critical): {be}")

        logger.info(f"[{task_id}] Running orchestrator...")
        results = ForexScreener.run_orchestrated_refresh(
            project_root=settings.PROJECT_ROOT,
            data_dir=settings.DATA_DIR / "forex_raw",
            config_path=settings.METADATA_DIR / "forex_pairs.json",
            output_path=settings.PROCESSED_DATA_DIR / "forex_signals.json",
            mode=mode,
            disabled_combos=disabled_combos,
            direction_overrides=direction_overrides
        )
        logger.info(f"[{task_id}] Orchestrator finished.")
        
        # --- Auto-Trading Execution ---
        all_signals = results.get('signals', [])

        # Filter out signals for pairs currently in the pre-close block window
        if PRECLOSE_BLOCKED_PAIRS:
            filtered_signals = [s for s in all_signals if s.get('symbol') not in PRECLOSE_BLOCKED_PAIRS]
            blocked_count = len(all_signals) - len(filtered_signals)
            if blocked_count:
                logger.info(
                    f"[{task_id}] Pre-close block: filtered {blocked_count} signal(s) "
                    f"for {PRECLOSE_BLOCKED_PAIRS}"
                )
            all_signals = filtered_signals

        try:
            logger.info(f"[{task_id}] Attempting auto-trade execution for {len(all_signals)} signals...")
            OandaTradeService.execute_trades(all_signals)
        except Exception as te:
            logger.error(f"[{task_id}] Auto-trade execution failed: {te}")

        # --- Portfolio Exit Monitoring (New: For better exit reasons) ---
        portfolio_exits = []
        auth_email = settings.AUTHORIZED_AUTO_TRADER_EMAIL
        if auth_email:
            try:
                monitor = PortfolioMonitor()
                portfolio_exits = monitor.check_portfolio_exits(auth_email)
            except Exception as pe:
                logger.error(f"[{task_id}] Portfolio exit check failed: {pe}")

        # --- Email Notification Logic ---
        diff = EmailService.filter_new_signals(all_signals, results.get('all_prices', {}), portfolio_exits)
        new_entries = diff['entries']
        exits = diff['exits']
        
        if new_entries or exits:
            logger.info(f"[{task_id}] Fetching users for notification...")
            # Fetch users who have opted in
            users_ref = db.collection('users')
            users = []
            try:
                # Add timeout/safety log for firestore stream
                count = 0
                for doc in users_ref.stream():
                    count += 1
                    user_data = doc.to_dict()
                    email = user_data.get('email')
                    if email and user_data.get('email_notifications', True): 
                        users.append(email)
                logger.info(f"[{task_id}] Found {len(users)} users subscribed (scanned {count}).")
            except Exception as dbe:
                logger.error(f"[{task_id}] Firestore user fetch failed: {dbe}")
            
            if users:
                if new_entries:
                    logger.info(f"[{task_id}] Sending {len(new_entries)} new entries...")
                    EmailService.send_signal_alert(users, new_entries)
                    logger.info(f"[{task_id}] Entry emails sent.")
                
                if exits:
                    logger.info(f"[{task_id}] Sending {len(exits)} trade exits...")
                    EmailService.send_exit_alert(users, exits)
                    logger.info(f"[{task_id}] Exit emails sent.")
            
            # Update state to current active signals
            EmailService.save_last_sent_signals(all_signals)

        refresh_manager.complete_forex_refresh()
        logger.info(f"[{task_id}] Forex refresh task complete. Found {results.get('signals_count', 0)} signals.")

    except Exception as e:
        logger.error(f"[{task_id}] Forex refresh task failed: {e}")
        refresh_manager.complete_forex_refresh(error=str(e))
    finally:
        refresh_manager.forex_lock.release()


def run_preclose_check():
    """
    Scheduled job (every 5 minutes) that:
      1. Clears pairs from PRECLOSE_BLOCKED_PAIRS that are no longer in a
         pre-close window (market has re-opened or the window has not arrived).
      2. Identifies pairs newly entering the block/close window.
      3. For pairs in the 'close' phase, closes all open Oanda positions
         (unless keep_through_close=True on the trade document).
      4. Adds pairs in block/close phase to PRECLOSE_BLOCKED_PAIRS.
    """
    global PRECLOSE_BLOCKED_PAIRS

    if not _preclose_lock.acquire(blocking=False):
        logger.info("run_preclose_check: already running, skipping tick.")
        return

    try:
        now = datetime.now(timezone.utc)
        active_windows = get_all_preclose_pairs(now)

        # --- 1. Clear pairs no longer in a pre-close window ---
        pairs_to_remove = {p for p in PRECLOSE_BLOCKED_PAIRS if p not in active_windows}
        if pairs_to_remove:
            PRECLOSE_BLOCKED_PAIRS -= pairs_to_remove
            logger.info(f"Pre-close: cleared {pairs_to_remove} from block set (window ended).")

        if not active_windows:
            return  # Nothing to do

        logger.info(f"Pre-close: active windows → {active_windows}")

        # --- 2. Update block set ---
        PRECLOSE_BLOCKED_PAIRS.update(active_windows.keys())

        # --- 3. Close open positions for pairs in 'close' phase ---
        auth_email = settings.AUTHORIZED_AUTO_TRADER_EMAIL
        if not auth_email:
            logger.warning("run_preclose_check: AUTHORIZED_AUTO_TRADER_EMAIL not set, skipping close.")
            return

        close_pairs = {pair for pair, phase in active_windows.items() if phase == "close"}
        if not close_pairs:
            return  # Only in block phase — no closes yet

        for pair in close_pairs:
            _close_open_positions_for_pair(pair, auth_email, now)

    except Exception as e:
        logger.error(f"run_preclose_check: unexpected error: {e}", exc_info=True)
    finally:
        _preclose_lock.release()


def _close_open_positions_for_pair(pair: str, auth_email: str, now: datetime):
    """
    Fetch all OPEN Firestore trades for `pair` under `auth_email` and close
    each one via Oanda, unless keep_through_close=True.
    Updates Firestore on success.
    """
    try:
        portfolio_ref = (
            db.collection("users")
            .document(auth_email)
            .collection("forex_portfolio")
        )
        open_docs = list(
            portfolio_ref
            .where(filter=firestore.FieldFilter("status", "==", "OPEN"))
            .where(filter=firestore.FieldFilter("symbol", "==", pair))
            .stream()
        )
    except Exception as e:
        logger.error(f"Pre-close: Firestore query failed for {pair}: {e}")
        return

    if not open_docs:
        logger.info(f"Pre-close: no open trades for {pair} — no-op.")
        return

    today_str = now.strftime("%Y-%m-%d")

    for doc in open_docs:
        data = doc.to_dict()
        trade_id = data.get("oanda_trade_id")
        doc_id = doc.id

        # Respect keep_through_close flag
        if data.get("keep_through_close"):
            logger.info(
                f"Pre-close: skipping trade {trade_id or doc_id} ({pair}): "
                f"keep_through_close=True"
            )
            continue

        existing_notes = data.get("notes") or ""

        if not trade_id:
            logger.warning(
                f"Pre-close: trade doc {doc_id} ({pair}) has no oanda_trade_id — "
                f"updating Firestore only."
            )
            _update_firestore_closed(doc.reference, today_str, now, reason="pre_close (no Oanda ID)", existing_notes=existing_notes)
            continue

        # Attempt to close via Oanda.
        # close_trade() catches all exceptions internally (including 404) and returns None on
        # any failure, so the except branch would never fire — we handle None explicitly.
        result = OandaPriceService.close_trade(trade_id)
        if result is None:
            # Distinguish "already closed by TP/SL" (trade not found in Oanda) from a
            # genuine API failure (trade still shows as open).
            trade_details = OandaPriceService.get_trade_details(trade_id)
            if trade_details is None:
                # Not found in Oanda → already closed by TP/SL
                logger.info(
                    f"Pre-close: trade {trade_id} ({pair}) not found in Oanda (already closed) "
                    f"— updating Firestore."
                )
                _update_firestore_closed(doc.reference, today_str, now, reason="already closed via TP/SL", existing_notes=existing_notes)
            else:
                # Still open in Oanda — genuine API failure, skip Firestore update
                logger.error(
                    f"Pre-close: close_trade({trade_id}) failed for {pair} (trade still open in Oanda) — "
                    f"skipping Firestore update."
                )
            continue

        logger.info(f"Pre-close: closed Oanda trade {trade_id} for {pair}.")
        _update_firestore_closed(doc.reference, today_str, now, reason="pre_close", existing_notes=existing_notes)


def _update_firestore_closed(doc_ref, today_str: str, now: datetime, reason: str, existing_notes: str = ""):
    """Write CLOSED status and PRE_CLOSE metadata back to a Firestore trade document."""
    try:
        new_notes = f"{existing_notes} | Pre-close: {reason}".strip(" |")

        doc_ref.update({
            "status": "CLOSED",
            "sell_date": today_str,
            "close_type": "PRE_CLOSE",
            "notes": new_notes,
            "updated_at": now,
        })
        logger.info(f"Pre-close: Firestore doc {doc_ref.id} updated → CLOSED (reason: {reason})")
    except Exception as e:
        logger.error(f"Pre-close: failed to update Firestore doc {doc_ref.id}: {e}")
