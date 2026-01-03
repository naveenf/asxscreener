"""
Performance metrics calculator for backtest results.

This module provides comprehensive performance analysis including:
- Win rate, profit factor, expectancy
- Risk metrics (Sharpe ratio, max drawdown)
- Trade statistics and distributions
"""

from typing import List, Dict
import pandas as pd
import numpy as np

from .backtester import ClosedTrade


class PerformanceMetrics:
    """Calculate comprehensive trading performance metrics."""

    def __init__(self, trades: List[ClosedTrade], equity_curve: pd.DataFrame, initial_capital: float):
        """
        Initialize metrics calculator.

        Args:
            trades: List of closed trades
            equity_curve: DataFrame with portfolio value over time
            initial_capital: Starting capital
        """
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_capital = initial_capital

    def win_rate(self) -> float:
        """Calculate percentage of profitable trades."""
        if not self.trades:
            return 0.0

        winning_trades = [t for t in self.trades if t.pnl > 0]
        return (len(winning_trades) / len(self.trades)) * 100

    def loss_rate(self) -> float:
        """Calculate percentage of losing trades."""
        return 100 - self.win_rate()

    def total_trades(self) -> int:
        """Total number of trades."""
        return len(self.trades)

    def winning_trades(self) -> int:
        """Number of winning trades."""
        return len([t for t in self.trades if t.pnl > 0])

    def losing_trades(self) -> int:
        """Number of losing trades."""
        return len([t for t in self.trades if t.pnl < 0])

    def avg_profit_per_trade(self) -> float:
        """Average profit/loss across all trades."""
        if not self.trades:
            return 0.0

        return sum(t.pnl for t in self.trades) / len(self.trades)

    def avg_profit_per_win(self) -> float:
        """Average profit on winning trades."""
        winning_trades = [t for t in self.trades if t.pnl > 0]

        if not winning_trades:
            return 0.0

        return sum(t.pnl for t in winning_trades) / len(winning_trades)

    def avg_loss_per_loss(self) -> float:
        """Average loss on losing trades."""
        losing_trades = [t for t in self.trades if t.pnl < 0]

        if not losing_trades:
            return 0.0

        return sum(t.pnl for t in losing_trades) / len(losing_trades)

    def avg_holding_period(self) -> float:
        """Average holding period in days."""
        if not self.trades:
            return 0.0

        return sum(t.holding_days for t in self.trades) / len(self.trades)

    def max_drawdown(self) -> float:
        """
        Maximum peak-to-trough decline in portfolio value.

        Returns percentage drawdown (positive number).
        """
        if self.equity_curve.empty:
            return 0.0

        portfolio_values = self.equity_curve['portfolio_value']
        running_max = portfolio_values.expanding().max()
        drawdown = (portfolio_values - running_max) / running_max * 100

        return abs(drawdown.min())

    def profit_factor(self) -> float:
        """
        Ratio of gross profit to gross loss.

        > 1.5 is good for position trading
        > 2.0 is excellent
        """
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return gross_profit / gross_loss

    def sharpe_ratio(self, risk_free_rate: float = 0.03) -> float:
        """
        Risk-adjusted return metric.

        Annualized Sharpe ratio using daily returns.
        > 1.0 is acceptable, > 2.0 is excellent

        Args:
            risk_free_rate: Annual risk-free rate (default 3%)

        Returns:
            Annualized Sharpe ratio
        """
        if self.equity_curve.empty or len(self.equity_curve) < 2:
            return 0.0

        # Calculate daily returns
        returns = self.equity_curve['portfolio_value'].pct_change().dropna()

        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        # Daily risk-free rate
        daily_rf = risk_free_rate / 252

        # Excess returns
        excess_returns = returns.mean() - daily_rf

        # Annualized Sharpe
        sharpe = (excess_returns / returns.std()) * np.sqrt(252)

        return sharpe

    def expectancy(self) -> float:
        """
        Average $ expected per trade.

        Positive expectancy is essential for long-term profitability.

        Formula: (Win Rate * Avg Win) - (Loss Rate * Avg Loss)
        """
        if not self.trades:
            return 0.0

        win_rate = self.win_rate() / 100
        loss_rate = 1 - win_rate

        avg_win = self.avg_profit_per_win()
        avg_loss = abs(self.avg_loss_per_loss())

        return (win_rate * avg_win) - (loss_rate * avg_loss)

    def total_return(self) -> float:
        """Total return in dollars."""
        if self.equity_curve.empty:
            return 0.0

        final_value = self.equity_curve['portfolio_value'].iloc[-1]
        return final_value - self.initial_capital

    def total_return_pct(self) -> float:
        """Total return as percentage."""
        return (self.total_return() / self.initial_capital) * 100

    def best_trade(self) -> Dict:
        """Get best performing trade."""
        if not self.trades:
            return {}

        best = max(self.trades, key=lambda t: t.pnl_pct)

        return {
            'ticker': best.ticker,
            'entry_date': best.entry_date.strftime('%Y-%m-%d'),
            'exit_date': best.exit_date.strftime('%Y-%m-%d'),
            'pnl': best.pnl,
            'pnl_pct': best.pnl_pct,
            'holding_days': best.holding_days
        }

    def worst_trade(self) -> Dict:
        """Get worst performing trade."""
        if not self.trades:
            return {}

        worst = min(self.trades, key=lambda t: t.pnl_pct)

        return {
            'ticker': worst.ticker,
            'entry_date': worst.entry_date.strftime('%Y-%m-%d'),
            'exit_date': worst.exit_date.strftime('%Y-%m-%d'),
            'pnl': worst.pnl,
            'pnl_pct': worst.pnl_pct,
            'holding_days': worst.holding_days
        }

    def exit_reason_analysis(self) -> Dict:
        """Breakdown of exit reasons and their performance."""
        profit_target_trades = [t for t in self.trades if t.exit_reason == 'profit_target']
        reversal_trades = [t for t in self.trades if t.exit_reason == 'trend_reversal']
        end_backtest_trades = [t for t in self.trades if t.exit_reason == 'end_of_backtest']

        return {
            'profit_target': {
                'count': len(profit_target_trades),
                'avg_pnl': np.mean([t.pnl for t in profit_target_trades]) if profit_target_trades else 0,
                'avg_pnl_pct': np.mean([t.pnl_pct for t in profit_target_trades]) if profit_target_trades else 0,
                'avg_days': np.mean([t.holding_days for t in profit_target_trades]) if profit_target_trades else 0
            },
            'trend_reversal': {
                'count': len(reversal_trades),
                'avg_pnl': np.mean([t.pnl for t in reversal_trades]) if reversal_trades else 0,
                'avg_pnl_pct': np.mean([t.pnl_pct for t in reversal_trades]) if reversal_trades else 0,
                'avg_days': np.mean([t.holding_days for t in reversal_trades]) if reversal_trades else 0
            },
            'end_of_backtest': {
                'count': len(end_backtest_trades),
                'avg_pnl': np.mean([t.pnl for t in end_backtest_trades]) if end_backtest_trades else 0,
                'avg_pnl_pct': np.mean([t.pnl_pct for t in end_backtest_trades]) if end_backtest_trades else 0,
                'avg_days': np.mean([t.holding_days for t in end_backtest_trades]) if end_backtest_trades else 0
            }
        }

    def monthly_returns(self) -> pd.DataFrame:
        """Calculate monthly returns from equity curve."""
        if self.equity_curve.empty:
            return pd.DataFrame()

        df = self.equity_curve.copy()
        df['month'] = pd.to_datetime(df['date']).dt.to_period('M')

        # Get last day of each month
        monthly = df.groupby('month')['portfolio_value'].last()

        # Calculate returns
        monthly_returns = monthly.pct_change() * 100

        return monthly_returns.to_frame(name='return_pct')

    def trade_distribution(self) -> Dict:
        """Statistics on trade P&L distribution."""
        if not self.trades:
            return {}

        pnl_pcts = [t.pnl_pct for t in self.trades]

        return {
            'mean': np.mean(pnl_pcts),
            'median': np.median(pnl_pcts),
            'std': np.std(pnl_pcts),
            'min': np.min(pnl_pcts),
            'max': np.max(pnl_pcts),
            'percentile_25': np.percentile(pnl_pcts, 25),
            'percentile_75': np.percentile(pnl_pcts, 75)
        }

    def to_dict(self) -> Dict:
        """Export all metrics as dictionary for JSON serialization."""
        return {
            # Core metrics
            'total_trades': self.total_trades(),
            'winning_trades': self.winning_trades(),
            'losing_trades': self.losing_trades(),
            'win_rate_pct': round(self.win_rate(), 2),

            # Profitability metrics
            'total_return': round(self.total_return(), 2),
            'total_return_pct': round(self.total_return_pct(), 2),
            'profit_factor': round(self.profit_factor(), 2),
            'expectancy': round(self.expectancy(), 2),

            # Average metrics
            'avg_profit_per_trade': round(self.avg_profit_per_trade(), 2),
            'avg_profit_per_win': round(self.avg_profit_per_win(), 2),
            'avg_loss_per_loss': round(self.avg_loss_per_loss(), 2),
            'avg_holding_days': round(self.avg_holding_period(), 1),

            # Risk metrics
            'sharpe_ratio': round(self.sharpe_ratio(), 2),
            'max_drawdown_pct': round(self.max_drawdown(), 2),

            # Best/worst trades
            'best_trade': self.best_trade(),
            'worst_trade': self.worst_trade(),

            # Exit analysis
            'exit_reasons': self.exit_reason_analysis(),

            # Distribution stats
            'trade_distribution': self.trade_distribution()
        }

    def print_summary(self):
        """Print formatted summary of backtest results."""
        print("\n" + "="*60)
        print("BACKTEST PERFORMANCE SUMMARY")
        print("="*60)

        print(f"\nPORTFOLIO:")
        print(f"  Initial Capital:        ${self.initial_capital:,.2f}")
        print(f"  Final Capital:          ${self.equity_curve['portfolio_value'].iloc[-1]:,.2f}")
        print(f"  Total Return:           ${self.total_return():,.2f} ({self.total_return_pct():.2f}%)")

        print(f"\nTRADE STATISTICS:")
        print(f"  Total Trades:           {self.total_trades()}")
        print(f"  Winning Trades:         {self.winning_trades()}")
        print(f"  Losing Trades:          {self.losing_trades()}")
        print(f"  Win Rate:               {self.win_rate():.2f}%")

        print(f"\nPROFITABILITY:")
        print(f"  Avg Profit/Trade:       ${self.avg_profit_per_trade():.2f}")
        print(f"  Avg Profit/Win:         ${self.avg_profit_per_win():.2f}")
        print(f"  Avg Loss/Loss:          ${self.avg_loss_per_loss():.2f}")
        print(f"  Profit Factor:          {self.profit_factor():.2f}")
        print(f"  Expectancy:             ${self.expectancy():.2f}")

        print(f"\nRISK METRICS:")
        print(f"  Sharpe Ratio:           {self.sharpe_ratio():.2f}")
        print(f"  Max Drawdown:           {self.max_drawdown():.2f}%")

        print(f"\nTRADE DURATION:")
        print(f"  Avg Holding Period:     {self.avg_holding_period():.1f} days")

        print(f"\nBEST TRADE:")
        best = self.best_trade()
        if best:
            print(f"  {best['ticker']}: {best['pnl_pct']:.2f}% (${best['pnl']:.2f})")
            print(f"  {best['entry_date']} → {best['exit_date']} ({best['holding_days']} days)")

        print(f"\nWORST TRADE:")
        worst = self.worst_trade()
        if worst:
            print(f"  {worst['ticker']}: {worst['pnl_pct']:.2f}% (${worst['pnl']:.2f})")
            print(f"  {worst['entry_date']} → {worst['exit_date']} ({worst['holding_days']} days)")

        print(f"\nEXIT REASON BREAKDOWN:")
        exit_analysis = self.exit_reason_analysis()
        for reason, stats in exit_analysis.items():
            print(f"  {reason}:")
            print(f"    Count: {stats['count']}")
            print(f"    Avg P&L: ${stats['avg_pnl']:.2f} ({stats['avg_pnl_pct']:.2f}%)")
            print(f"    Avg Days: {stats['avg_days']:.1f}")

        print("\n" + "="*60)
