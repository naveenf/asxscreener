from abc import ABC, abstractmethod
from typing import Dict, Optional
import pandas as pd

class ForexStrategy(ABC):
    """
    Abstract Base Class for Forex Strategies supporting Multi-Timeframe (MTF) analysis.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Return the unique name of the strategy."""
        pass

    @abstractmethod
    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0) -> Optional[Dict]:
        """
        Analyze the given symbol using multi-timeframe data.

        Args:
            data: Dictionary containing dataframes for different timeframes.
                  Expected keys: '15m', '1h', '4h'.
                  DataFrames must have OHLCV columns and datetime index.
            symbol: The symbol being analyzed (e.g., 'EURUSD=X').
            target_rr: Target Reward-to-Risk ratio.

        Returns:
            Dictionary with signal details if a signal is found, else None.
            Required keys in return dict:
                - 'signal': 'BUY' or 'SELL'
                - 'score': float (0-100)
                - 'strategy': str (strategy name)
                - 'timestamp': datetime (entry time)
                - 'price': float (entry price)
                - 'stop_loss': float
                - 'take_profit': float (optional)
        """
        pass

    @abstractmethod
    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Check if an open position should be closed based on strategy rules.

        Args:
            data: Dictionary containing dataframes for different timeframes.
            direction: 'BUY' or 'SELL'.
            entry_price: The price at which the position was opened.

        Returns:
            Dictionary with exit details if exit condition met, else None.
            Required keys:
                - 'exit_signal': bool (True)
                - 'reason': str
        """
        pass
