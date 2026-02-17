"""
Comprehensive Sniper Backtest
Tests SilverSniper strategy on XAG and Sniper strategy on WHEAT/BCO
Outputs detailed per-trade metrics including actual R:R achieved
"""

import pandas as pd
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.silver_sniper_detector import SilverSniperDetector
from backend.app.services.sniper_detector import SniperDetector
from backend.app.services.commodity_sniper_detector import CommoditySniperDetector
from backend.app.services.indicators import TechnicalIndicators

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
OUTPUT_DIR = PROJECT_ROOT / 'data'
STARTING_BALANCE = 360.0
RISK_PCT = 2.0
LEVERAGE = 10.0
SPREAD_COST = 0.0006  # 0.06%


def load_asset_data(symbol: str, strategy_type: str) -> Optional[Dict[str, pd.DataFrame]]:
    """
    Load data for the specified symbol and strategy type.

    Args:
        symbol: Asset symbol (e.g., 'XAG_USD')
        strategy_type: 'SilverSniper' or 'Sniper'

    Returns:
        Dict with 'base' and 'htf' dataframes, or None if data missing
    """
    data = {}

    # Determine timeframes based on strategy
    if strategy_type in ['SilverSniper', 'CommoditySniper']:
        base_tf = '5_Min'
        htf_tf = '15_Min'
    else:  # Sniper
        base_tf = '15_Min'
        htf_tf = '1_Hour'

    # Load base timeframe
    base_path = DATA_DIR / f"{symbol}_{base_tf}.csv"
    if not base_path.exists():
        print(f"ERROR: Missing base timeframe data: {base_path}")
        return None

    df_base = pd.read_csv(base_path)
    date_col = 'Date' if 'Date' in df_base.columns else 'Datetime'
    df_base[date_col] = pd.to_datetime(df_base[date_col], utc=True)
    df_base.set_index(date_col, inplace=True)
    df_base.sort_index(inplace=True)
    df_base = TechnicalIndicators.add_all_indicators(df_base)
    data['base'] = df_base

    # Load HTF timeframe
    htf_path = DATA_DIR / f"{symbol}_{htf_tf}.csv"
    if not htf_path.exists():
        print(f"ERROR: Missing HTF data: {htf_path}")
        return None

    df_htf = pd.read_csv(htf_path)
    date_col = 'Date' if 'Date' in df_htf.columns else 'Datetime'
    df_htf[date_col] = pd.to_datetime(df_htf[date_col], utc=True)
    df_htf.set_index(date_col, inplace=True)
    df_htf.sort_index(inplace=True)
    df_htf = TechnicalIndicators.add_all_indicators(df_htf)
    data['htf'] = df_htf

    return data


def calculate_position_size(balance: float, entry_price: float, stop_loss: float, leverage: float) -> int:
    """
    Calculate position size based on risk management rules.

    Args:
        balance: Current account balance
        entry_price: Entry price
        stop_loss: Stop loss price
        leverage: Maximum leverage allowed

    Returns:
        Position size in units
    """
    risk_amount = balance * (RISK_PCT / 100.0)
    stop_distance = abs(entry_price - stop_loss)

    if stop_distance == 0:
        return 0

    # Calculate units based on risk
    units_by_risk = risk_amount / stop_distance

    # Calculate max units based on leverage
    max_units_by_leverage = (balance * leverage) / entry_price

    # Take minimum to respect both constraints
    units = min(units_by_risk, max_units_by_leverage)

    return int(units)


def simulate_trade(
    df_base: pd.DataFrame,
    entry_idx: int,
    signal: Dict,
    entry_price: float,
    stop_loss: float,
    take_profit: float
) -> Tuple[float, float, str, Optional[pd.Timestamp], float]:
    """
    Simulate a trade from entry to exit.

    Args:
        df_base: Base timeframe dataframe
        entry_idx: Index of entry candle
        signal: Signal dictionary
        entry_price: Entry price
        stop_loss: Stop loss price
        take_profit: Take profit price

    Returns:
        Tuple of (profit_per_unit, actual_rr, exit_reason, exit_time, exit_price)
    """
    direction = signal['signal']
    risk = abs(entry_price - stop_loss)

    # Iterate through subsequent candles
    for i in range(entry_idx + 1, len(df_base)):
        candle = df_base.iloc[i]

        if direction == 'BUY':
            # Check SL first (more conservative)
            if candle['Low'] <= stop_loss:
                profit_per_unit = stop_loss - entry_price  # Negative
                actual_rr = profit_per_unit / risk if risk > 0 else 0
                return profit_per_unit, actual_rr, "STOP_LOSS", candle.name, stop_loss

            # Check TP
            if candle['High'] >= take_profit:
                profit_per_unit = take_profit - entry_price
                actual_rr = profit_per_unit / risk if risk > 0 else 0
                return profit_per_unit, actual_rr, "TAKE_PROFIT", candle.name, take_profit

        else:  # SELL
            # Check SL first
            if candle['High'] >= stop_loss:
                profit_per_unit = entry_price - stop_loss  # Negative
                actual_rr = profit_per_unit / risk if risk > 0 else 0
                return profit_per_unit, actual_rr, "STOP_LOSS", candle.name, stop_loss

            # Check TP
            if candle['Low'] <= take_profit:
                profit_per_unit = entry_price - take_profit
                actual_rr = profit_per_unit / risk if risk > 0 else 0
                return profit_per_unit, actual_rr, "TAKE_PROFIT", candle.name, take_profit

    # Trade still open at end of data
    close_price = df_base.iloc[-1]['Close']
    profit_per_unit = (close_price - entry_price) if direction == 'BUY' else (entry_price - close_price)
    actual_rr = profit_per_unit / risk if risk > 0 else 0
    return profit_per_unit, actual_rr, "OPEN", None, close_price


def calculate_comprehensive_metrics(trades_df: pd.DataFrame, starting_balance: float) -> Dict:
    """
    Calculate comprehensive performance metrics from trades.

    Args:
        trades_df: DataFrame with all trade details
        starting_balance: Starting account balance

    Returns:
        Dictionary of metrics
    """
    if len(trades_df) == 0:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'wins': 0,
            'losses': 0
        }

    # Basic metrics
    wins = trades_df[trades_df['Exit_Reason'] == 'TAKE_PROFIT']
    losses = trades_df[trades_df['Exit_Reason'] == 'STOP_LOSS']

    total_trades = len(trades_df)
    num_wins = len(wins)
    num_losses = len(losses)
    win_rate = (num_wins / total_trades * 100) if total_trades > 0 else 0

    # R:R metrics
    avg_rr_wins = wins['Actual_RR'].mean() if len(wins) > 0 else 0
    avg_rr_losses = losses['Actual_RR'].mean() if len(losses) > 0 else 0
    avg_rr_all = trades_df['Actual_RR'].mean()

    # Profit metrics
    final_balance = trades_df.iloc[-1]['Balance_After'] if len(trades_df) > 0 else starting_balance
    total_pnl = final_balance - starting_balance
    return_pct = (total_pnl / starting_balance * 100) if starting_balance > 0 else 0

    # Win/Loss size
    avg_win = wins['PnL'].mean() if len(wins) > 0 else 0
    avg_loss = losses['PnL'].mean() if len(losses) > 0 else 0
    best_trade = trades_df['PnL'].max()
    worst_trade = trades_df['PnL'].min()

    # Risk metrics - Max Drawdown
    trades_df['Peak'] = trades_df['Balance_After'].cummax()
    trades_df['Drawdown'] = (trades_df['Balance_After'] - trades_df['Peak']) / trades_df['Peak'] * 100
    max_drawdown = trades_df['Drawdown'].min()

    # Consecutive losses
    consecutive_losses = 0
    max_consecutive_losses = 0
    for _, row in trades_df.iterrows():
        if row['Exit_Reason'] == 'STOP_LOSS':
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
        else:
            consecutive_losses = 0

    # Sharpe ratio (simplified - using trade returns)
    if len(trades_df) > 1:
        trade_returns = trades_df['PnL'] / starting_balance
        sharpe = (trade_returns.mean() / trade_returns.std()) * np.sqrt(len(trades_df)) if trade_returns.std() > 0 else 0
    else:
        sharpe = 0

    return {
        'total_trades': total_trades,
        'wins': num_wins,
        'losses': num_losses,
        'win_rate': win_rate,
        'avg_rr_wins': avg_rr_wins,
        'avg_rr_losses': avg_rr_losses,
        'avg_rr_all': avg_rr_all,
        'final_balance': final_balance,
        'total_pnl': total_pnl,
        'return_pct': return_pct,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'best_trade': best_trade,
        'worst_trade': worst_trade,
        'max_drawdown': max_drawdown,
        'max_consecutive_losses': max_consecutive_losses,
        'sharpe': sharpe
    }


def run_backtest(symbol: str, strategy_type: str, target_rr: float) -> Optional[Dict]:
    """
    Run backtest for a specific symbol and strategy.
    """
    print(f"\n{'='*60}")
    print(f"Running {strategy_type} backtest on {symbol}...")
    print(f"{'='*60}")

    # Load best strategies to get params
    import json
    with open('data/metadata/best_strategies.json', 'r') as f:
        best_strategies = json.load(f)
    
    asset_config = best_strategies.get(symbol, {})
    strat_params = {}
    if 'strategies' in asset_config:
        strat_params = next((s for s in asset_config['strategies'] if s['strategy'] == strategy_type), {}).get('params', {})
    elif asset_config.get('strategy') == strategy_type:
        strat_params = asset_config.get('params', {})

    # Load data
    data = load_asset_data(symbol, strategy_type)
    if data is None:
        return None

    df_base = data['base']
    df_htf = data['htf']

    # Initialize detector
    if strategy_type == 'SilverSniper':
        detector = SilverSniperDetector()
        min_lookback = 100
    elif strategy_type == 'CommoditySniper':
        detector = CommoditySniperDetector(
            squeeze_threshold=1.3,
            adx_min=20,
            require_fvg=False,
            cooldown_hours=0
        )
        min_lookback = 100
    else:  # Sniper
        detector = SniperDetector()
        min_lookback = 220

    # Initialize tracking
    balance = STARTING_BALANCE
    trades_list = []

    # Walk through base timeframe
    i = min_lookback
    while i < len(df_base):
        current_time = df_base.index[i]

        # Prepare data slices
        slice_base = df_base.iloc[max(0, i-min_lookback):i+1]

        # Align HTF data
        htf_idx_array = df_htf.index.get_indexer([current_time], method='pad')
        htf_idx = htf_idx_array[0]

        if htf_idx < 20:  # Need enough HTF data
            i += 1
            continue

        slice_htf = df_htf.iloc[max(0, htf_idx-50):htf_idx+1]

        # Check for signal
        data_slices = {'base': slice_base, 'htf': slice_htf}
        signal = detector.analyze(data_slices, symbol, target_rr=target_rr, spread=SPREAD_COST, params=strat_params)

        if signal:
            entry_price = signal['price']
            stop_loss = signal['stop_loss']
            take_profit = signal['take_profit']

            # Calculate position size
            units = calculate_position_size(balance, entry_price, stop_loss, LEVERAGE)

            if units >= 1:
                # Simulate trade
                profit_per_unit, actual_rr, exit_reason, exit_time, exit_price = simulate_trade(
                    df_base, i, signal, entry_price, stop_loss, take_profit
                )

                # Calculate P&L with spread cost
                gross_pnl = profit_per_unit * units
                spread_cost = entry_price * units * SPREAD_COST
                net_pnl = gross_pnl - spread_cost

                balance += net_pnl

                # Record trade
                intended_rr = target_rr if exit_reason == 'TAKE_PROFIT' else -1.0
                trade_record = {
                    'Trade_Num': len(trades_list) + 1,
                    'Entry_Time': current_time,
                    'Entry_Price': entry_price,
                    'Direction': signal['signal'],
                    'Stop_Loss': stop_loss,
                    'Take_Profit': take_profit,
                    'Intended_RR': intended_rr,
                    'Position_Size': units,
                    'Exit_Time': exit_time if exit_time else df_base.index[-1],
                    'Exit_Price': exit_price,
                    'Exit_Reason': exit_reason,
                    'PnL': net_pnl,
                    'Actual_RR': actual_rr,
                    'Balance_After': balance,
                    'Return_Pct': ((balance - STARTING_BALANCE) / STARTING_BALANCE * 100)
                }
                trades_list.append(trade_record)

                # Skip forward to exit time
                if exit_time:
                    try:
                        exit_idx = df_base.index.get_loc(exit_time)
                        i = exit_idx
                    except KeyError:
                        pass

        i += 1

    # Create trades DataFrame
    if not trades_list:
        print(f"No trades generated for {symbol}")
        return None

    trades_df = pd.DataFrame(trades_list)

    # Calculate metrics
    metrics = calculate_comprehensive_metrics(trades_df, STARTING_BALANCE)
    metrics['symbol'] = symbol
    metrics['strategy'] = strategy_type
    metrics['target_rr'] = target_rr

    # Save trades to CSV
    csv_path = OUTPUT_DIR / f"backtest_results_{symbol}.csv"
    trades_df.to_csv(csv_path, index=False)
    print(f"\nTrades saved to: {csv_path}")

    return {
        'metrics': metrics,
        'trades': trades_df
    }


def print_summary(result: Dict):
    """Print formatted summary of backtest results."""
    if result is None:
        return

    m = result['metrics']

    print(f"\n{'='*60}")
    print(f"=== {m['symbol']} ({m['strategy']}) ===")
    print(f"{'='*60}")

    print(f"\nTrade Summary:")
    print(f"  Total Trades: {m['total_trades']}")
    print(f"  Wins: {m['wins']} | Losses: {m['losses']}")
    print(f"  Win Rate: {m['win_rate']:.1f}%")

    print(f"\nR:R Analysis:")
    print(f"  Target R:R: {m['target_rr']:.1f}")
    print(f"  Average Actual R:R (Wins): {m['avg_rr_wins']:.2f}")
    print(f"  Average Actual R:R (Losses): {m['avg_rr_losses']:.2f}")
    print(f"  Average Actual R:R (All): {m['avg_rr_all']:.2f}")

    print(f"\nProfit Metrics:")
    print(f"  Starting Balance: ${STARTING_BALANCE:.2f}")
    print(f"  Final Balance: ${m['final_balance']:.2f}")
    print(f"  Total P&L: ${m['total_pnl']:.2f}")
    print(f"  Return: {m['return_pct']:.2f}%")

    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown: {m['max_drawdown']:.2f}%")
    print(f"  Max Consecutive Losses: {m['max_consecutive_losses']}")
    print(f"  Largest Loss: ${m['worst_trade']:.2f}")

    print(f"\nTrade Statistics:")
    print(f"  Average Win: ${m['avg_win']:.2f} ({m['avg_rr_wins']:.2f} R)")
    print(f"  Average Loss: ${m['avg_loss']:.2f} ({m['avg_rr_losses']:.2f} R)")
    print(f"  Best Trade: ${m['best_trade']:.2f}")
    print(f"  Worst Trade: ${m['worst_trade']:.2f}")
    print(f"  Sharpe Ratio: {m['sharpe']:.2f}")
    print()


def main():
    """Main execution function."""
    print("\n" + "="*60)
    print("SNIPER STRATEGY BACKTEST - COMPREHENSIVE ANALYSIS")
    print("="*60)
    print(f"Parameters:")
    print(f"  Starting Balance: ${STARTING_BALANCE}")
    print(f"  Risk per Trade: {RISK_PCT}%")
    print(f"  Leverage: {LEVERAGE}x")
    print(f"  Spread Cost: {SPREAD_COST*100:.2f}%")

    # Define test cases
    test_cases = [
        ('XAG_USD', 'SilverSniper', 3.0),
        ('WHEAT_USD', 'CommoditySniper', 3.0),  # Using optimized CommoditySniper
        ('BCO_USD', 'CommoditySniper', 3.0),    # Using optimized CommoditySniper
        ('AUD_USD', 'Sniper', 1.5)              # Forex major using Sniper strategy
    ]

    results = []

    # Run backtests
    for symbol, strategy, rr in test_cases:
        result = run_backtest(symbol, strategy, rr)
        if result:
            results.append(result)
            print_summary(result)

    # Print comparison table
    if results:
        print("\n" + "="*60)
        print("COMPARISON SUMMARY")
        print("="*60)
        print(f"{'Symbol':<12} | {'Strategy':<14} | {'Trades':<7} | {'Win %':<7} | {'Avg R:R':<8} | {'Return %':<10}")
        print("-"*80)

        for result in results:
            m = result['metrics']
            print(f"{m['symbol']:<12} | {m['strategy']:<14} | {m['total_trades']:<7} | {m['win_rate']:<7.1f} | {m['avg_rr_all']:<8.2f} | {m['return_pct']:<10.2f}")

    print("\n" + "="*60)
    print("Backtest Complete!")
    print("="*60)


if __name__ == "__main__":
    main()
