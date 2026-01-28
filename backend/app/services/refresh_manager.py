"""
Refresh Status Manager

Singleton service to track background refresh tasks for Stocks and Forex.
"""

from datetime import datetime
from typing import Optional
import threading

class RefreshStatusManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RefreshStatusManager, cls).__new__(cls)
            cls._instance.is_refreshing_stocks = False
            cls._instance.is_refreshing_forex = False
            cls._instance.last_stocks_refresh = None
            cls._instance.last_forex_refresh = None
            cls._instance.stocks_error = None
            cls._instance.forex_error = None
            cls._instance.forex_lock = threading.Lock()
            cls._instance.stocks_lock = threading.Lock()
        return cls._instance

    def start_stocks_refresh(self):
        self.is_refreshing_stocks = True
        self.stocks_error = None

    def complete_stocks_refresh(self, error: Optional[str] = None):
        self.is_refreshing_stocks = False
        if not error:
            self.last_stocks_refresh = datetime.now()
        self.stocks_error = error

    def start_forex_refresh(self):
        self.is_refreshing_forex = True
        self.forex_error = None

    def complete_forex_refresh(self, error: Optional[str] = None):
        self.is_refreshing_forex = False
        if not error:
            self.last_forex_refresh = datetime.now()
        self.forex_error = error

    def get_status(self):
        return {
            "stocks": {
                "in_progress": self.is_refreshing_stocks,
                "last_updated": self.last_stocks_refresh.isoformat() if self.last_stocks_refresh else None,
                "error": self.stocks_error
            },
            "forex": {
                "in_progress": self.is_refreshing_forex,
                "last_updated": self.last_forex_refresh.isoformat() if self.last_forex_refresh else None,
                "error": self.forex_error
            }
        }

# Global instance
refresh_manager = RefreshStatusManager()
