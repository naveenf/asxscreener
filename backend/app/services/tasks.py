"""
Background Tasks Service

Contains logic for scheduled and manual background tasks.
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path

from ..config import settings
from .screener import StockScreener
from .market_data import update_all_stocks_data
from .insider_trades import InsiderTradesService
from .forex_screener import ForexScreener
from .oanda_trade_service import OandaTradeService
from .notification import EmailService
from .refresh_manager import refresh_manager
from ..firebase_setup import db

logger = logging.getLogger(__name__)

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
        
        logger.info(f"[{task_id}] Running orchestrator...")
        results = ForexScreener.run_orchestrated_refresh(
            project_root=settings.PROJECT_ROOT,
            data_dir=settings.DATA_DIR / "forex_raw",
            config_path=settings.METADATA_DIR / "forex_pairs.json",
            output_path=settings.PROCESSED_DATA_DIR / "forex_signals.json",
            mode=mode
        )
        logger.info(f"[{task_id}] Orchestrator finished.")
        
        # --- Auto-Trading Execution ---
        all_signals = results.get('signals', [])
        try:
            logger.info(f"[{task_id}] Attempting auto-trade execution for {len(all_signals)} signals...")
            OandaTradeService.execute_trades(all_signals)
        except Exception as te:
            logger.error(f"[{task_id}] Auto-trade execution failed: {te}")

        # --- Email Notification Logic ---
        diff = EmailService.filter_new_signals(all_signals)
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
