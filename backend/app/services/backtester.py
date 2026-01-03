"""
Backtesting engine for ASX Stock Screener trading strategy.

This module provides a realistic event-driven backtesting framework that simulates
trading the ADX/DI strategy on historical data, accounting for slippage, commissions,
and realistic position sizing.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from .signal_detector import SignalDetector
from .indicators import TechnicalIndicators


@dataclass
class Position:
    """Represents an open trading position."""

    ticker: str
    entry_date: datetime
    entry_price: float
    shares: int
    entry_indicators: Dict[str, float]  # ADX, DI+, DI- at entry
    score: float

    def unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized profit/loss."""
        return (current_price - self.entry_price) * self.shares

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L as percentage."""
        return ((current_price - self.entry_price) / self.entry_price) * 100

    def holding_days(self, current_date: datetime) -> int:
        """Calculate number of days position has been held."""
        return (current_date - self.entry_date).days

    def cost_basis(self) -> float:
        """Total cost of the position."""
        return self.entry_price * self.shares


@dataclass
class ClosedTrade:
    """Represents a completed trade."""

    ticker: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    holding_days: int
    exit_reason: str  # 'profit_target', 'trend_reversal', 'mean_reversion'
    entry_score: float
    # Trend following indicators (optional)
    entry_adx: Optional[float] = None
    entry_di_plus: Optional[float] = None
    entry_di_minus: Optional[float] = None
    # Mean reversion indicators (optional)
    entry_rsi: Optional[float] = None
    entry_bb_upper: Optional[float] = None
    entry_bb_middle: Optional[float] = None


class Backtester:
    """
    Event-driven backtesting engine.

    Simulates trading strategy on historical data with realistic assumptions:
    - Position sizing based on portfolio percentage
    - Slippage modeling (0.1% default)
    - Commission costs ($10 per trade default)
    - No lookahead bias (only uses data up to current date)
    - Concurrent position limits
    """

    def __init__(
        self,
        detector: SignalDetector,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000.0,
        position_size_pct: float = 0.20,  # 20% per position
        max_positions: int = 5,           # Max concurrent positions
        slippage_pct: float = 0.001,      # 0.1% slippage
        commission: float = 10.0,         # $10 per trade
    ):
        """
        Initialize backtester.

        Args:
            detector: SignalDetector instance with entry/exit logic
            start_date: Backtest start date (YYYY-MM-DD)
            end_date: Backtest end date (YYYY-MM-DD)
            initial_capital: Starting portfolio value
            position_size_pct: Percentage of capital per position
            max_positions: Maximum concurrent positions
            slippage_pct: Slippage as decimal (0.001 = 0.1%)
            commission: Commission per trade in dollars
        """
        self.detector = detector
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.max_positions = max_positions
        self.slippage_pct = slippage_pct
        self.commission = commission

        # State tracking
        self.current_capital = initial_capital
        self.open_positions: List[Position] = []
        self.closed_trades: List[ClosedTrade] = []
        self.equity_curve: List[Dict] = []

    def run(self, stock_data: Dict[str, pd.DataFrame]) -> 'BacktestResults':
        """
        Run backtest on historical data.

        Args:
            stock_data: Dict mapping ticker -> DataFrame with OHLC + indicators

        Returns:
            BacktestResults object with trades and performance metrics
        """
        print(f"Starting backtest from {self.start_date.date()} to {self.end_date.date()}")
        print(f"Initial capital: ${self.initial_capital:,.2f}")
        print(f"Position size: {self.position_size_pct * 100}% per position")
        print(f"Max positions: {self.max_positions}")
        print(f"Stocks to screen: {len(stock_data)}")

        # Create unified timeline from all stocks
        all_dates = self._create_timeline(stock_data)
        print(f"Trading days in backtest: {len(all_dates)}")

        # Event-driven simulation: process each date chronologically
        for i, current_date in enumerate(all_dates):
            if i % 50 == 0:
                print(f"Processing date {i+1}/{len(all_dates)}: {current_date.date()}")

            # Step 1: Check exits (process before entries to free up capital)
            self._check_exits(current_date, stock_data)

            # Step 2: Check entries (only if we have capacity)
            self._check_entries(current_date, stock_data)

            # Step 3: Update equity curve
            self._update_equity(current_date, stock_data)

        # Close any remaining positions at end date
        self._close_all_positions(self.end_date, stock_data)

        print(f"\nBacktest complete!")
        print(f"Total trades: {len(self.closed_trades)}")
        print(f"Final capital: ${self.current_capital:,.2f}")

        return BacktestResults(
            trades=self.closed_trades,
            equity_curve=pd.DataFrame(self.equity_curve),
            initial_capital=self.initial_capital,
            final_capital=self.current_capital
        )

    def _create_timeline(self, stock_data: Dict[str, pd.DataFrame]) -> List[pd.Timestamp]:
        """Create unified chronological timeline from all stocks."""
        all_dates = set()
        for df in stock_data.values():
            # Filter to backtest date range (use all dates, will filter in event loop)
            all_dates.update(df.index)

        # Filter to backtest date range (use date comparison to avoid timezone issues)
        start_date_only = self.start_date.date()
        end_date_only = self.end_date.date()
        all_dates = [d for d in all_dates if start_date_only <= d.date() <= end_date_only]

        return sorted(list(all_dates))

    def _check_exits(self, current_date: pd.Timestamp, stock_data: Dict[str, pd.DataFrame]):
        """
        Check all open positions for exit conditions.

        Exit triggers:
        1. Profit target reached (15%)
        2. Trend reversal (DI+ crosses below DI- at ANY point after entry)
        """
        for position in self.open_positions[:]:  # Iterate over copy to allow removal
            ticker = position.ticker

            if ticker not in stock_data:
                continue

            df = stock_data[ticker]

            # Check if this stock has data for current date
            if current_date not in df.index:
                continue

            # Get data up to current date (no lookahead)
            df_current = df.loc[:current_date]

            # CRITICAL FIX: Find entry_index in the dataframe
            entry_index = None
            try:
                # Get position of entry_date in df_current's index
                entry_index = df_current.index.get_loc(position.entry_date)
            except KeyError:
                # Entry date might not be in index (e.g., weekend, holiday)
                # Find nearest previous date
                mask = df_current.index <= position.entry_date
                if mask.any():
                    entry_dates = df_current.index[mask]
                    if len(entry_dates) > 0:
                        entry_index = len(entry_dates) - 1

            # Use detector's exit logic with entry_index
            exit_info = self.detector.detect_exit_signal(
                df_current,
                entry_price=position.entry_price,
                current_index=-1,  # Latest bar
                entry_index=entry_index  # NEW - pass entry position
            )

            if exit_info['has_exit']:
                # Close the position
                trade = self._close_position(
                    position,
                    current_date,
                    exit_info['current_price'],
                    exit_info['exit_reason']
                )
                self.closed_trades.append(trade)
                self.open_positions.remove(position)

    def _check_entries(self, current_date: pd.Timestamp, stock_data: Dict[str, pd.DataFrame]):
        """
        Scan all stocks for entry signals.

        Entry criteria:
        1. ADX > threshold AND DI+ > DI-
        2. Not already holding this stock
        3. Available capital for new position
        4. Under max_positions limit
        """
        if len(self.open_positions) >= self.max_positions:
            return  # No capacity for new positions

        # Collect all valid signals for this date
        signals = []

        for ticker, df in stock_data.items():
            # Check if this stock has data for current date
            if current_date not in df.index:
                continue

            # Skip if already holding this stock
            if any(p.ticker == ticker for p in self.open_positions):
                continue

            # Get data up to current date (no lookahead)
            df_current = df.loc[:current_date]

            # Check for entry signal
            signal_info = self.detector.detect_entry_signal(df_current)

            if signal_info['has_signal']:
                score = self.detector.calculate_score(signal_info, df_current)

                signals.append({
                    'ticker': ticker,
                    'score': score,
                    'price': signal_info['close'],
                    'signal_info': signal_info,
                    'df': df_current
                })

        # Sort signals by score (highest first) and take top signals
        signals.sort(key=lambda x: x['score'], reverse=True)

        # Open positions for top signals (up to capacity)
        slots_available = self.max_positions - len(self.open_positions)
        for signal in signals[:slots_available]:
            position = self._open_position(current_date, signal)
            if position:
                self.open_positions.append(position)

    def _open_position(self, date: pd.Timestamp, signal: Dict) -> Optional[Position]:
        """
        Open a new position.

        Args:
            date: Entry date
            signal: Signal info dict

        Returns:
            Position object if opened successfully, None otherwise
        """
        ticker = signal['ticker']
        price = signal['price']

        # Calculate position size
        shares = self._calculate_position_size(price)

        if shares == 0:
            return None  # Not enough capital

        # Calculate total cost with slippage and commission
        cost = self._execute_trade(price, shares, 'BUY')

        if cost > self.current_capital:
            return None  # Not enough capital

        # Deduct cost from capital
        self.current_capital -= cost

        # Create position with indicators
        # Support both trend following and mean reversion strategies
        entry_indicators = {}

        # Trend following indicators
        if 'adx' in signal['signal_info']:
            entry_indicators['ADX'] = signal['signal_info']['adx']
            entry_indicators['DIPlus'] = signal['signal_info']['di_plus']
            entry_indicators['DIMinus'] = signal['signal_info']['di_minus']

        # Mean reversion indicators
        if 'rsi' in signal['signal_info']:
            entry_indicators['RSI'] = signal['signal_info']['rsi']
            entry_indicators['BB_Upper'] = signal['signal_info']['bb_upper']
            entry_indicators['BB_Middle'] = signal['signal_info']['bb_middle']

        position = Position(
            ticker=ticker,
            entry_date=date,
            entry_price=price,
            shares=shares,
            entry_indicators=entry_indicators,
            score=signal['score']
        )

        return position

    def _close_position(
        self,
        position: Position,
        date: pd.Timestamp,
        exit_price: float,
        exit_reason: str
    ) -> ClosedTrade:
        """
        Close a position and record the trade.

        Args:
            position: Position to close
            date: Exit date
            exit_price: Exit price
            exit_reason: Reason for exit

        Returns:
            ClosedTrade object
        """
        # Calculate proceeds with slippage and commission
        proceeds = self._execute_trade(exit_price, position.shares, 'SELL')

        # Add proceeds to capital
        self.current_capital += proceeds

        # Calculate P&L
        cost = position.cost_basis()
        pnl = proceeds - cost
        pnl_pct = (pnl / cost) * 100

        # Create trade record
        # Support both trend following and mean reversion indicators
        trade = ClosedTrade(
            ticker=position.ticker,
            entry_date=position.entry_date,
            exit_date=date,
            entry_price=position.entry_price,
            exit_price=exit_price,
            shares=position.shares,
            pnl=pnl,
            pnl_pct=pnl_pct,
            holding_days=position.holding_days(date),
            exit_reason=exit_reason,
            entry_score=position.score,
            # Trend following indicators (optional)
            entry_adx=position.entry_indicators.get('ADX'),
            entry_di_plus=position.entry_indicators.get('DIPlus'),
            entry_di_minus=position.entry_indicators.get('DIMinus'),
            # Mean reversion indicators (optional)
            entry_rsi=position.entry_indicators.get('RSI'),
            entry_bb_upper=position.entry_indicators.get('BB_Upper'),
            entry_bb_middle=position.entry_indicators.get('BB_Middle')
        )

        return trade

    def _execute_trade(self, price: float, shares: int, side: str) -> float:
        """
        Calculate actual fill price with slippage and commission.

        Args:
            price: Market price
            shares: Number of shares
            side: 'BUY' or 'SELL'

        Returns:
            Total cost (BUY) or proceeds (SELL) including costs
        """
        slippage = price * self.slippage_pct

        if side == 'BUY':
            fill_price = price + slippage
            total_cost = (fill_price * shares) + self.commission
            return total_cost
        else:  # SELL
            fill_price = price - slippage
            total_proceeds = (fill_price * shares) - self.commission
            return total_proceeds

    def _calculate_position_size(self, price: float) -> int:
        """
        Calculate number of shares to buy based on position_size_pct.

        Args:
            price: Stock price

        Returns:
            Number of shares (integer)
        """
        available_capital = self.current_capital
        target_value = available_capital * self.position_size_pct

        # Account for slippage and commission
        fill_price = price * (1 + self.slippage_pct)
        shares = int((target_value - self.commission) / fill_price)

        # Ensure we have enough capital
        cost = self._execute_trade(price, shares, 'BUY')
        if cost > available_capital:
            # Reduce shares
            shares = int(available_capital / (fill_price + self.commission / shares))

        return max(shares, 0)

    def _update_equity(self, date: pd.Timestamp, stock_data: Dict[str, pd.DataFrame]):
        """Update equity curve with current portfolio value."""
        # Calculate positions value
        positions_value = 0.0
        for position in self.open_positions:
            if position.ticker in stock_data:
                df = stock_data[position.ticker]
                if date in df.index:
                    current_price = df.loc[date, 'Close']
                    positions_value += current_price * position.shares

        total_equity = self.current_capital + positions_value

        # Calculate drawdown
        if self.equity_curve:
            peak = max(e['portfolio_value'] for e in self.equity_curve)
        else:
            peak = self.initial_capital

        drawdown_pct = ((total_equity - peak) / peak) * 100 if peak > 0 else 0

        self.equity_curve.append({
            'date': date,
            'portfolio_value': total_equity,
            'cash': self.current_capital,
            'positions_value': positions_value,
            'drawdown_pct': drawdown_pct,
            'num_positions': len(self.open_positions)
        })

    def _close_all_positions(self, date: pd.Timestamp, stock_data: Dict[str, pd.DataFrame]):
        """Close all remaining positions at end of backtest."""
        print(f"DEBUG: Closing {len(self.open_positions)} positions at end of backtest")

        for position in self.open_positions[:]:
            ticker = position.ticker
            print(f"DEBUG: Attempting to close position in {ticker}")

            if ticker not in stock_data:
                print(f"DEBUG: {ticker} not in stock_data")
                continue

            df = stock_data[ticker]

            # Find the last available date for this stock (use date-only comparison)
            # Filter to dates <= end_date
            # Simple approach: compare date strings to avoid timezone complexities
            end_date_str = date.strftime('%Y-%m-%d')
            available_indices = []
            for idx in df.index:
                try:
                    idx_str = idx.strftime('%Y-%m-%d')
                    if idx_str <= end_date_str:
                        available_indices.append(idx)
                except:
                    pass
            available_dates = pd.Index(available_indices)

            if len(available_dates) > 0:
                last_date = available_dates[-1]  # Get last available date
                exit_price = df.loc[last_date, 'Close']
                trade = self._close_position(position, last_date, exit_price, 'end_of_backtest')
                self.closed_trades.append(trade)
                print(f"DEBUG: Closed {ticker} at ${exit_price:.2f}, P&L: ${trade.pnl:.2f}")
            else:
                print(f"DEBUG: No data available for {ticker} before {date}")

        print(f"DEBUG: After closing all, self.closed_trades has {len(self.closed_trades)} trades")

        # Clear all positions after closing
        self.open_positions.clear()


@dataclass
class BacktestResults:
    """Container for backtest results."""

    trades: List[ClosedTrade]
    equity_curve: pd.DataFrame
    initial_capital: float
    final_capital: float

    def total_return_pct(self) -> float:
        """Calculate total return percentage."""
        return ((self.final_capital - self.initial_capital) / self.initial_capital) * 100

    def num_trades(self) -> int:
        """Total number of trades."""
        return len(self.trades)
