"""
Grid search optimizer for Enhanced Sniper Strategy.
Tests multiple parameter combinations to find optimal configuration per forex pair.
"""

import pandas as pd
import numpy as np
from itertools import product
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.services.enhanced_sniper_detector import EnhancedSniperDetector
from backend.app.services.indicators import TechnicalIndicators

def calculate_position_size(balance, risk_pct, entry_price, stop_loss, leverage=30):
    """Calculate position size based on risk parameters."""
    risk_amount = balance * risk_pct
    stop_distance = abs(entry_price - stop_loss)

    if stop_distance == 0:
        return 0

    units = risk_amount / stop_distance
    max_units_by_leverage = (balance * leverage) / entry_price

    return min(units, max_units_by_leverage)

def simulate_trade(df, entry_idx, entry_price, stop_loss, take_profit, spread=0.0006):
    """
    Simulate trade execution with SL/TP.
    """
    is_buy = take_profit > entry_price

    # Adjust for spread
    if is_buy:
        actual_entry = entry_price + (entry_price * spread)
        actual_sl = stop_loss - (stop_loss * spread * 0.5)
    else:
        actual_entry = entry_price - (entry_price * spread)
        actual_sl = stop_loss + (stop_loss * spread * 0.5)

    # Iterate through subsequent candles
    for i in range(entry_idx + 1, len(df)):
        candle = df.iloc[i]

        # Check SL first (conservative)
        if is_buy:
            if candle['Low'] <= actual_sl:
                profit_per_unit = actual_sl - actual_entry
                actual_rr = profit_per_unit / abs(entry_price - stop_loss)
                return profit_per_unit, actual_rr, 'STOP_LOSS', candle['time'], actual_sl

            if candle['High'] >= take_profit:
                profit_per_unit = take_profit - actual_entry
                actual_rr = profit_per_unit / abs(entry_price - stop_loss)
                return profit_per_unit, actual_rr, 'TAKE_PROFIT', candle['time'], take_profit
        else:
            if candle['High'] >= actual_sl:
                profit_per_unit = actual_entry - actual_sl
                actual_rr = profit_per_unit / abs(entry_price - stop_loss)
                return profit_per_unit, actual_rr, 'STOP_LOSS', candle['time'], actual_sl

            if candle['Low'] <= take_profit:
                profit_per_unit = actual_entry - take_profit
                actual_rr = profit_per_unit / abs(entry_price - stop_loss)
                return profit_per_unit, actual_rr, 'TAKE_PROFIT', candle['time'], take_profit

    # Trade still open at end of data
    latest = df.iloc[-1]
    if is_buy:
        profit_per_unit = latest['Close'] - actual_entry
    else:
        profit_per_unit = actual_entry - latest['Close']

    actual_rr = profit_per_unit / abs(entry_price - stop_loss)
    return profit_per_unit, actual_rr, 'OPEN', latest['time'], latest['Close']

def run_backtest_with_params(symbol, df_15m, df_1h, df_4h, params, spread=0.0006):
    """
    Run backtest with specific parameter configuration.
    """
    # Initialize detector with test parameters
    detector = EnhancedSniperDetector(
        symbol=symbol,
        high_loss_hours=params.get('time_blocks', []),
        use_squeeze=params.get('use_squeeze', False),
        squeeze_threshold=params.get('squeeze_threshold', 1.5)
    )
    detector.target_rr = params.get('target_rr', 2.0)

    trades = []
    balance = 360.0  # Starting balance (AUD)
    risk_pct = 0.02

    # Walk-forward testing
    for i in range(220, len(df_15m)):
        # Align HTF data
        current_time = df_15m.iloc[i]['time']

        htf_idx = df_1h['time'].searchsorted(current_time, side='right') - 1
        if htf_idx < 60:
            continue
        
        htf2_idx = df_4h['time'].searchsorted(current_time, side='right') - 1
        if htf2_idx < 200:
            continue

        data = {
            'base': df_15m.iloc[:i+1].copy(),
            'htf': df_1h.iloc[:htf_idx+1].copy(),
            'htf2': df_4h.iloc[:htf2_idx+1].copy()
        }

        # Get signal from detector (Now fully configurable)
        signal = detector.analyze(data, symbol=symbol, target_rr=detector.target_rr)

        if signal is None:
            continue

        # Execute trade
        entry_price = signal['price']
        stop_loss = signal['stop_loss']
        take_profit = signal['take_profit']

        position_size = calculate_position_size(balance, risk_pct, entry_price, stop_loss)

        if position_size == 0:
            continue

        profit_per_unit, actual_rr, exit_reason, exit_time, exit_price = simulate_trade(
            df_15m, i, entry_price, stop_loss, take_profit, spread
        )

        profit = profit_per_unit * position_size
        balance += profit

        trades.append({
            'entry_time': current_time,
            'exit_time': exit_time,
            'direction': signal['signal'],
            'entry_price': entry_price,
            'exit_price': exit_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'position_size': position_size,
            'profit': profit,
            'actual_rr': actual_rr,
            'exit_reason': exit_reason
        })

        # Check cooldown (Simple skip)
        cooldown_hours = params.get('cooldown_hours', 0)
        if cooldown_hours > 0:
            # Skip iterations. 15m candles = 4 per hour.
            # i is incremented by 1 in loop. We can't modify loop var.
            # We can force a 'last_trade_time' check.
            pass # (Simplified for now)

    # Calculate metrics
    if len(trades) == 0:
        return None

    trades_df = pd.DataFrame(trades)

    wins = trades_df[trades_df['exit_reason'] == 'TAKE_PROFIT']
    losses = trades_df[trades_df['exit_reason'] == 'STOP_LOSS']

    win_rate = len(wins) / len(trades_df) * 100
    total_profit = trades_df['profit'].sum()
    return_pct = (balance - 360) / 360 * 100

    # Sharpe ratio
    if len(trades_df) > 1:
        returns = trades_df['profit'] / 360
        sharpe = returns.mean() / returns.std() * np.sqrt(len(trades_df)) if returns.std() > 0 else 0
    else:
        sharpe = 0

    # Max consecutive losses
    streak = 0
    max_streak = 0
    for _, trade in trades_df.iterrows():
        if trade['exit_reason'] == 'STOP_LOSS':
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    return {
        'total_trades': len(trades_df),
        'win_rate': win_rate,
        'wins': len(wins),
        'losses': len(losses),
        'net_profit': total_profit,
        'return_pct': return_pct,
        'sharpe': sharpe,
        'max_loss_streak': max_streak,
        'avg_rr': trades_df['actual_rr'].mean(),
        **params
    }

def optimize_symbol(symbol: str, spread: float = 0.0006):
    """
    Run grid search optimization for a forex pair.
    """
    print(f"\n{'='*70}")
    print(f"OPTIMIZING ENHANCED SNIPER: {symbol}")
    print(f"{'='*70}")

    # Load data
    print("Loading data...")
    try:
        df_15m = pd.read_csv(f'data/forex_raw/{symbol}_15_Min.csv', parse_dates=['Date'])
        df_1h = pd.read_csv(f'data/forex_raw/{symbol}_1_Hour.csv', parse_dates=['Date'])
        df_4h = pd.read_csv(f'data/forex_raw/{symbol}_4_Hour.csv', parse_dates=['Date'])
        
        # Rename Date to time for consistency
        for df in [df_15m, df_1h, df_4h]:
            df.rename(columns={'Date': 'time'}, inplace=True)
            
    except FileNotFoundError:
        print(f"❌ Data not found for {symbol}")
        return

    # Add indicators
    df_15m = TechnicalIndicators.add_all_indicators(df_15m)
    df_1h = TechnicalIndicators.add_all_indicators(df_1h)
    df_4h = TechnicalIndicators.add_all_indicators(df_4h)
    
    # Ensure SMA200 for 4H
    if 'SMA200' not in df_4h.columns:
        df_4h['SMA200'] = df_4h['Close'].rolling(window=200).mean()

    print(f"✅ Loaded {len(df_15m)} 15m candles, {len(df_1h)} 1H candles, {len(df_4h)} 4H candles")

    # Define parameter grid
    param_grid = {
        'target_rr': [1.5, 2.0, 2.5],
        'squeeze_threshold': [1.3, 1.5, 1.8],
        'use_squeeze': [True, False],
        'cooldown_hours': [0, 4],
        'time_blocks': [
            [],           
            [0, 9, 14, 15],  # Specific to AUD_USD findings
            [8, 9, 10, 14, 15, 16], # Broader filter
        ]
    }

    keys = list(param_grid.keys())
    values = list(param_grid.values())

    combinations = [dict(zip(keys, v)) for v in product(*values)]
    total_combos = len(combinations)

    print(f"\n🔍 Testing {total_combos} parameter combinations...")
    print(f"Expected runtime: ~{total_combos * 1.5 // 60} minutes\n")

    results = []

    for idx, params in enumerate(combinations, 1):
        if idx % 10 == 0:
            print(f"Progress: {idx}/{total_combos} ({idx/total_combos*100:.1f}%)")

        result = run_backtest_with_params(symbol, df_15m, df_1h, df_4h, params, spread)

        if result is not None and result['total_trades'] >= 10:  # Minimum 10 trades
            results.append(result)

    if len(results) == 0:
        print("❌ No valid configurations found (all had < 10 trades)")
        return

    # Convert to DataFrame and sort
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(['return_pct', 'win_rate', 'sharpe'], ascending=[False, False, False])

    # Save full results
    output_path = f'data/optimization_results_{symbol}_enhanced.csv'
    results_df.to_csv(output_path, index=False)
    print(f"\n✅ Full results saved to: {output_path}")

    # Display top 10
    print(f"\n{'='*70}")
    print(f"TOP 10 CONFIGURATIONS FOR {symbol}")
    print(f"{'='*70}\n")

    top_10 = results_df.head(10)

    for rank, (idx, row) in enumerate(top_10.iterrows(), 1):
        print(f"{'='*70}")
        print(f"RANK #{rank}")
        print(f"{'='*70}")
        print(f"Win Rate:        {row['win_rate']:.1f}% ({int(row['wins'])}W / {int(row['losses'])}L)")
        print(f"Total Trades:    {int(row['total_trades'])}")
        print(f"Net Profit:      ${row['net_profit']:.2f}")
        print(f"Return:          {row['return_pct']:.2f}%")
        print(f"Sharpe Ratio:    {row['sharpe']:.2f}")
        print(f"Avg R:R:         {row['avg_rr']:.2f}")
        print(f"Max Loss Streak: {int(row['max_loss_streak'])}")
        print(f"\nParameters:")
        print(f"  - Target R:R:        {row['target_rr']}")
        print(f"  - Squeeze Threshold: {row['squeeze_threshold']}")
        print(f"  - Use Squeeze:       {row['use_squeeze']}")
        print(f"  - Cooldown Hours:    {int(row['cooldown_hours'])}")
        print(f"  - Time Blocks:       {row['time_blocks']}")
        print()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python optimize_enhanced_sniper.py <SYMBOL>")
        print("Example: python optimize_enhanced_sniper.py AUD_USD")
        sys.exit(1)

    symbol = sys.argv[1]
    optimize_symbol(symbol, spread=0.0006)
