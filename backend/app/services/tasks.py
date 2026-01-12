"""
Background Tasks Service

Contains logic for scheduled and manual background tasks.
"""

import logging
from datetime import datetime
from pathlib import Path

from ..config import settings
from .screener import StockScreener
from .market_data import update_all_stocks_data
from .insider_trades import InsiderTradesService
from .forex_screener import ForexScreener
from .notification import EmailService
from .refresh_manager import refresh_manager
from ..firebase_setup import db

logger = logging.getLogger(__name__)

def run_stock_refresh_task():
    """Logic for stock refresh."""
    try:
        if refresh_manager.is_refreshing_stocks:
            logger.warning("Stock refresh already in progress, skipping.")
            return

        refresh_manager.start_stocks_refresh()
        logger.info(f"Starting stock refresh task at {datetime.now()}")
        
        # Create screener
        screener = StockScreener(
            data_dir=settings.RAW_DATA_DIR,
            metadata_dir=settings.METADATA_DIR,
            output_dir=settings.PROCESSED_DATA_DIR
        )
        
        # 1. Update data from yfinance
        stocks = screener.load_stock_list()
        tickers = [s['ticker'] for s in stocks]
        
        # Smart Check: If it's after 18:00 but we already have today's data, we could potentially skip
        # but for simplicity and reliability, we'll run it as scheduled.
        
        logger.info(f"Updating data for {len(tickers)} tickers...")
        update_results = update_all_stocks_data(tickers, settings.RAW_DATA_DIR)
        success_count = sum(1 for r in update_results.values() if r)
        logger.info(f"Successfully updated {success_count}/{len(tickers)} CSV files")

        # 2. Run screener
        logger.info("Running screener...")
        results = screener.screen_all_stocks()
        screener.save_signals(results)
        
        # 3. Update Insider Trades
        logger.info("Updating insider trades...")
        insider_service = InsiderTradesService(settings.PROCESSED_DATA_DIR / 'insider_trades.json')
        insider_service.scrape_and_update()

        refresh_manager.complete_stocks_refresh()
        logger.info(f"Stock refresh task complete. Found {results['signals_count']} signals.")

    except Exception as e:
        logger.error(f"Stock refresh task failed: {e}")
        refresh_manager.complete_stocks_refresh(error=str(e))

def run_forex_refresh_task(mode: str = 'dynamic'):
    """Logic for forex refresh."""
    try:
        if refresh_manager.is_refreshing_forex:
            logger.warning("Forex refresh already in progress, skipping.")
            return

        refresh_manager.start_forex_refresh()
        logger.info(f"Starting forex refresh task ({mode}) at {datetime.now()}")
        
        results = ForexScreener.run_orchestrated_refresh(
            project_root=settings.PROJECT_ROOT,
            data_dir=settings.DATA_DIR / "forex_raw",
            config_path=settings.METADATA_DIR / "forex_pairs.json",
            output_path=settings.PROCESSED_DATA_DIR / "forex_signals.json",
            mode=mode
        )
        
        # --- Email Notification Logic ---
        all_signals = results.get('signals', [])
        diff = EmailService.filter_new_signals(all_signals)
        new_entries = diff['entries']
        exits = diff['exits']
        
        if new_entries or exits:
            # Fetch users who have opted in
            users_ref = db.collection('users')
            users = []
            for doc in users_ref.stream():
                user_data = doc.to_dict()
                email = user_data.get('email')
                if email and user_data.get('email_notifications', True): 
                    users.append(email)
            
            if users:
                if new_entries:
                    logger.info(f"Sending {len(new_entries)} new entries...")
                    EmailService.send_signal_alert(users, new_entries)
                
                if exits:
                    logger.info(f"Sending {len(exits)} trade exits...")
                    EmailService.send_exit_alert(users, exits)
            
            # Update state to current active signals
            EmailService.save_last_sent_signals(all_signals)

        refresh_manager.complete_forex_refresh()
        logger.info(f"Forex refresh task complete. Found {results.get('signals_count', 0)} signals.")

    except Exception as e:
        logger.error(f"Forex refresh task failed: {e}")
        refresh_manager.complete_forex_refresh(error=str(e))
