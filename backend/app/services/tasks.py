"""
Background Tasks Service

Contains logic for scheduled and manual background tasks.
"""

import logging
import threading
import uuid
from datetime import datetime, timezone, timedelta
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

# ---------------------------------------------------------------------------
# Profit-lock configs
# ---------------------------------------------------------------------------
# lock_at_r  : fire lock when trade unrealized P&L reaches this many R
# lock_to_r  : move SL to this many R from entry when lock fires
# cooldown_min: minutes to block new entries after a locked trade closes
# sl_precision: decimal places for Oanda SL price formatting
PAIR_LOCK_CONFIGS = {
    "XAG_USD": {"lock_at_r": 3.0, "lock_to_r": 2.0, "cooldown_min": 25,  "sl_precision": 3},
    "BCO_USD": {"lock_at_r": 2.0, "lock_to_r": 1.0, "cooldown_min": 90,  "sl_precision": 3},
}

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

        # --- Profit-Lock Check (cooldown gate + SL move for XAG, BCO) ---
        try:
            run_pair_lock_checks()
        except Exception as xag_e:
            logger.error(f"[{task_id}] Pair lock check failed (non-critical): {xag_e}", exc_info=True)

        # Re-filter signals after lock checks may have added pairs to blocked set
        if PRECLOSE_BLOCKED_PAIRS:
            filtered_signals = [s for s in all_signals if s.get('symbol') not in PRECLOSE_BLOCKED_PAIRS]
            newly_blocked = len(all_signals) - len(filtered_signals)
            if newly_blocked:
                logger.info(
                    f"[{task_id}] Post-lock-check block: filtered {newly_blocked} signal(s) "
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

            # --- Lock Cooldown Writer (fires after Oanda sync marks trades CLOSED) ---
            try:
                check_pair_lock_cooldowns()
            except Exception as xag_cool_e:
                logger.error(f"[{task_id}] Pair lock cooldown write failed (non-critical): {xag_cool_e}", exc_info=True)

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


def run_pair_lock_checks():
    """
    Profit-lock check for all pairs in PAIR_LOCK_CONFIGS.

    Runs before signal execution each refresh cycle:
      1. For each configured pair, reads config/lock_state_{symbol} from Firestore.
         If a cooldown is active (cooldown_until > now), adds the symbol to
         PRECLOSE_BLOCKED_PAIRS so no new entries are placed this cycle.
      2. Scans all OPEN trades for each pair where lock_fired is falsy.
         If a trade has reached lock_at_r unrealized profit, moves its Oanda SL
         to lock_to_r and flags the Firestore doc with lock_fired=True.
    """
    global PRECLOSE_BLOCKED_PAIRS

    auth_email = settings.AUTHORIZED_AUTO_TRADER_EMAIL
    if not auth_email:
        return

    for symbol, lock_cfg in PAIR_LOCK_CONFIGS.items():
        lock_at_r    = lock_cfg["lock_at_r"]
        lock_to_r    = lock_cfg["lock_to_r"]
        sl_precision = lock_cfg["sl_precision"]
        state_doc_id = f"lock_state_{symbol}"
        tag          = f"{symbol} lock"

        try:
            # --- Step 1: check cooldown ---
            try:
                lock_doc = db.collection("config").document(state_doc_id).get()
                if lock_doc.exists:
                    lock_data = lock_doc.to_dict() or {}
                    cooldown_until_str = lock_data.get("cooldown_until")
                    if cooldown_until_str:
                        cooldown_until = datetime.fromisoformat(cooldown_until_str)
                        if datetime.now(timezone.utc) < cooldown_until:
                            logger.info(
                                f"{tag}: cooldown active until {cooldown_until_str} — "
                                f"blocking {symbol} entries this cycle"
                            )
                            PRECLOSE_BLOCKED_PAIRS.add(symbol)
            except Exception:
                logger.error(f"{tag}: failed to read {state_doc_id} from Firestore", exc_info=True)

            # --- Step 2: scan open trades for lock threshold ---
            portfolio_ref = (
                db.collection("users")
                .document(auth_email)
                .collection("forex_portfolio")
            )

            try:
                open_docs = list(
                    portfolio_ref
                    .where(filter=firestore.FieldFilter("symbol", "==", symbol))
                    .where(filter=firestore.FieldFilter("status", "==", "OPEN"))
                    .stream()
                )
            except Exception:
                logger.error(f"{tag}: Firestore query for open trades failed", exc_info=True)
                continue

            current_price = None  # fetch once per symbol if needed

            for doc in open_docs:
                try:
                    data = doc.to_dict()

                    if data.get("lock_fired"):
                        continue

                    buy_price      = data.get("buy_price")
                    stop_loss      = data.get("stop_loss")
                    direction      = data.get("direction", "BUY")
                    oanda_trade_id = data.get("oanda_trade_id")

                    if buy_price is None or stop_loss is None or not oanda_trade_id:
                        logger.warning(f"{tag}: doc {doc.id} missing required fields — skipping")
                        continue

                    risk_distance = abs(float(buy_price) - float(stop_loss))
                    if risk_distance == 0:
                        logger.warning(f"{tag}: doc {doc.id} has zero risk_distance — skipping")
                        continue

                    if current_price is None:
                        current_price = OandaPriceService.get_current_price(symbol)
                    if current_price is None:
                        logger.warning(f"{tag}: could not fetch current price — skipping cycle")
                        break

                    if direction == "BUY":
                        r_current = (current_price - float(buy_price)) / risk_distance
                        lock_sl   = float(buy_price) + (1.0 + lock_to_r) * risk_distance
                    else:
                        r_current = (float(buy_price) - current_price) / risk_distance
                        lock_sl   = float(buy_price) - (1.0 + lock_to_r) * risk_distance

                    logger.info(
                        f"{tag}: trade {oanda_trade_id} — R={r_current:.2f}, "
                        f"entry={buy_price}, price={current_price}, rdist={risk_distance:.4f}"
                    )

                    if r_current >= lock_at_r:
                        logger.info(
                            f"{tag}: FIRING lock for trade {oanda_trade_id} "
                            f"(R={r_current:.2f} >= {lock_at_r}) — moving SL to "
                            f"{lock_sl:.{sl_precision}f} (+{lock_to_r}R)"
                        )

                        modify_result = OandaPriceService.modify_trade_sl(
                            oanda_trade_id, lock_sl, precision=sl_precision
                        )

                        if modify_result is None:
                            logger.error(
                                f"{tag}: modify_trade_sl returned None for {oanda_trade_id} "
                                f"— will retry next cycle"
                            )
                            continue

                        doc.reference.update({
                            "lock_fired":    True,
                            "lock_sl":       lock_sl,
                            "lock_fired_at": datetime.now(timezone.utc).isoformat(),
                            "updated_at":    datetime.now(timezone.utc),
                        })
                        logger.info(
                            f"{tag}: Firestore doc {doc.id} updated — "
                            f"lock_fired=True, lock_sl={lock_sl:.{sl_precision}f}"
                        )

                except Exception:
                    logger.error(f"{tag}: unexpected error processing doc {doc.id}", exc_info=True)

        except Exception:
            logger.error(f"{tag}: run_pair_lock_checks failed for {symbol}", exc_info=True)


def check_pair_lock_cooldowns():
    """
    Cooldown writer for all pairs in PAIR_LOCK_CONFIGS.

    Called after portfolio sync each refresh cycle. For each pair, finds trades that:
      - status == CLOSED
      - lock_fired == True
      - lock_cooldown_set is missing / False

    Writes a cooldown timestamp to config/lock_state_{symbol} and stamps the trade
    doc with lock_cooldown_set=True so it isn't processed again.
    """
    auth_email = settings.AUTHORIZED_AUTO_TRADER_EMAIL
    if not auth_email:
        return

    for symbol, lock_cfg in PAIR_LOCK_CONFIGS.items():
        cooldown_min = lock_cfg["cooldown_min"]
        state_doc_id = f"lock_state_{symbol}"
        tag          = f"{symbol} lock"

        try:
            portfolio_ref = (
                db.collection("users")
                .document(auth_email)
                .collection("forex_portfolio")
            )

            try:
                closed_locked_docs = list(
                    portfolio_ref
                    .where(filter=firestore.FieldFilter("symbol", "==", symbol))
                    .where(filter=firestore.FieldFilter("status", "==", "CLOSED"))
                    .where(filter=firestore.FieldFilter("lock_fired", "==", True))
                    .stream()
                )
            except Exception:
                logger.error(
                    f"{tag}: Firestore query for closed locked trades failed", exc_info=True
                )
                continue

            for doc in closed_locked_docs:
                try:
                    data = doc.to_dict()

                    if data.get("lock_cooldown_set"):
                        continue

                    cooldown_until     = datetime.now(timezone.utc) + timedelta(minutes=cooldown_min)
                    cooldown_until_str = cooldown_until.isoformat()

                    db.collection("config").document(state_doc_id).set(
                        {
                            "cooldown_until":     cooldown_until_str,
                            "reason":             "lock_sl_triggered",
                            "triggered_by_trade": doc.id,
                            "updated_at":         datetime.now(timezone.utc).isoformat(),
                        },
                        merge=True,
                    )

                    doc.reference.update({
                        "lock_cooldown_set": True,
                        "updated_at":        datetime.now(timezone.utc),
                    })

                    logger.info(
                        f"{tag}: cooldown written — no new {symbol} entries until "
                        f"{cooldown_until_str} (triggered by trade doc {doc.id})"
                    )

                except Exception:
                    logger.error(
                        f"{tag}: failed to write cooldown for doc {doc.id}", exc_info=True
                    )

        except Exception:
            logger.error(
                f"{tag}: check_pair_lock_cooldowns failed for {symbol}", exc_info=True
            )


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
