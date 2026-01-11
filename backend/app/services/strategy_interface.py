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
    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str) -> Optional[Dict]:
        """
        Analyze the given symbol using multi-timeframe data.

        Args:
            data: Dictionary containing dataframes for different timeframes.
                  Expected keys: '15m', '1h', '4h'.
                  DataFrames must have OHLCV columns and datetime index.
            symbol: The symbol being analyzed (e.g., 'EURUSD=X').

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
