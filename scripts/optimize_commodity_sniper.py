"""
CommoditySniper Parameter Optimization
Grid search to find optimal parameters for WHEAT and BCO

Tests combinations of:
- squeeze_threshold: 1.2, 1.3, 1.5
- adx_min: 20, 22, 25
- require_fvg: False, True
- target_rr: 2.5, 3.0
- cooldown_hours: 0, 4

Total: 72 combinations per asset
"""

import pandas as pd
import sys
from pathlib import Path
from typing import Dict, List
import numpy as np
from itertools import product

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.commodity_sniper_detector import CommoditySniperDetector
from backend.app.services.indicators import TechnicalIndicators

# Configuration
DATA_DIR = PROJECT_ROOT / 'data' / 'forex_raw'
STARTING_BALANCE = 360.0
RISK_PCT = 2.0
LEVERAGE = 10.0
SPREAD_COST = 0.0006


def load_data(symbol: str) -> Dict[str, pd.DataFrame]:
    """Load 5m and 15m data for symbol."""
    data = {}

    for tf_name, tf_str in [('base', '5_Min'), ('htf', '15_Min')]:
        path = DATA_DIR / f"{symbol}_{tf_str}.csv"
        if not path.exists():
            return None

        df = pd.read_csv(path)
        date_col = 'Date' if 'Date' in df.columns else 'Datetime'
        df[date_col] = pd.to_datetime(df[date_col], utc=True)
        df.set_index(date_col, inplace=True)
        df.sort_index(inplace=True)
        df = TechnicalIndicators.add_all_indicators(df)
        data[tf_name] = df

    return data


def calculate_position_size(balance: float, entry: float, sl: float) -> int:
    """Calculate position size based on 2% risk."""
    risk_amount = balance * (RISK_PCT / 100.0)
    stop_distance = abs(entry - sl)
    if stop_distance == 0:
        return 0

    units_by_risk = risk_amount / stop_distance
    max_units = (balance * LEVERAGE) / entry
    return int(min(units_by_risk, max_units))


def simulate_trade(df, entry_idx, signal, entry_price, stop_loss, take_profit):
    """Simulate trade to SL or TP."""
    direction = signal['signal']
    risk = abs(entry_price - stop_loss)

    for i in range(entry_idx + 1, len(df)):
        candle = df.iloc[i]

        if direction == 'BUY':
            if candle['Low'] <= stop_loss:
                return stop_loss - entry_price, -1.0, "LOSS", candle.name
            if candle['High'] >= take_profit:
                return take_profit - entry_price, (take_profit - entry_price) / risk, "WIN", candle.name
        else:  # SELL
            if candle['High'] >= stop_loss:
                return entry_price - stop_loss, -1.0, "LOSS", candle.name
            if candle['Low'] <= take_profit:
                return entry_price - take_profit, (entry_price - take_profit) / risk, "WIN", candle.name

    # Still open at end
    close = df.iloc[-1]['Close']
    ppu = (close - entry_price) if direction == 'BUY' else (entry_price - close)
    return ppu, ppu / risk if risk > 0 else 0, "OPEN", None


def backtest_config(symbol: str, data: Dict, params: Dict) -> Dict:
    """Run backtest with specific parameter configuration."""
    detector = CommoditySniperDetector(
        squeeze_threshold=params['squeeze_threshold'],
        adx_min=params['adx_min'],
        require_fvg=params['require_fvg'],
        cooldown_hours=params['cooldown_hours']
    )

    df_base = data['base']
    df_htf = data['htf']
    balance = STARTING_BALANCE
    trades = []

    i = 100
    while i < len(df_base):
        current_time = df_base.index[i]
        slice_base = df_base.iloc[max(0, i-100):i+1]

        # Align HTF
        htf_idx = df_htf.index.get_indexer([current_time], method='pad')[0]
        if htf_idx < 20:
            i += 1
            continue

        slice_htf = df_htf.iloc[max(0, htf_idx-50):htf_idx+1]

        # Check for signal
        signal = detector.analyze(
            {'base': slice_base, 'htf': slice_htf},
            symbol,
            target_rr=params['target_rr'],
            spread=SPREAD_COST
        )

        if signal:
            entry_price = signal['price']
            stop_loss = signal['stop_loss']
            take_profit = signal['take_profit']
            units = calculate_position_size(balance, entry_price, stop_loss)

            if units >= 1:
                ppu, actual_rr, result, exit_time = simulate_trade(
                    df_base, i, signal, entry_price, stop_loss, take_profit
                )

                if result != "OPEN":
                    gross_pnl = ppu * units
                    spread_cost = entry_price * units * SPREAD_COST
                    net_pnl = gross_pnl - spread_cost
                    balance += net_pnl

                    trades.append({
                        'result': result,
                        'pnl': net_pnl,
                        'rr': actual_rr
                    })

                    # Record exit for cooldown
                    if exit_time:
                        detector.record_exit(exit_time, symbol)
                        try:
                            i = df_base.index.get_loc(exit_time)
                        except KeyError:
                            pass

        i += 1

    # Calculate metrics
    if not trades:
        return {
            'total_trades': 0,
            'win_rate': 0,
            'net_profit': 0,
            'return_pct': 0,
            'max_loss_streak': 0,
            'sharpe': 0
        }

    wins = [t for t in trades if t['result'] == 'WIN']
    losses = [t for t in trades if t['result'] == 'LOSS']

    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    net_profit = balance - STARTING_BALANCE
    return_pct = (net_profit / STARTING_BALANCE * 100)

    # Max loss streak
    streak = 0
    max_streak = 0
    for t in trades:
        if t['result'] == 'LOSS':
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    # Sharpe (simplified)
    if len(trades) > 1:
        returns = [t['pnl'] / STARTING_BALANCE for t in trades]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(len(trades)) if np.std(returns) > 0 else 0
    else:
        sharpe = 0

    return {
        'total_trades': len(trades),
        'win_rate': win_rate,
        'net_profit': net_profit,
        'return_pct': return_pct,
        'max_loss_streak': max_streak,
        'sharpe': sharpe
    }


def optimize_asset(symbol: str) -> pd.DataFrame:
    """Run grid search for a single asset."""
    print(f"\n{'='*80}")
    print(f"Optimizing {symbol}...")
    print(f"{'='*80}")

    # Load data once
    data = load_data(symbol)
    if not data:
        print(f"ERROR: Could not load data for {symbol}")
        return None

    # Parameter grid
    param_grid = {
        'squeeze_threshold': [1.2, 1.3, 1.5],
        'adx_min': [20, 22, 25],
        'require_fvg': [False, True],
        'target_rr': [2.5, 3.0],
        'cooldown_hours': [0, 4]
    }

    # Generate all combinations
    keys = param_grid.keys()
    values = param_grid.values()
    combinations = [dict(zip(keys, v)) for v in product(*values)]

    print(f"Testing {len(combinations)} parameter combinations...")

    results = []
    for i, params in enumerate(combinations, 1):
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(combinations)}")

        metrics = backtest_config(symbol, data, params)

        results.append({
            **params,
            **metrics
        })

    # Convert to DataFrame and sort by profitability
    df = pd.DataFrame(results)

    # Filter: Must have at least 5 trades
    df = df[df['total_trades'] >= 5]

    if len(df) == 0:
        print(f"WARNING: No configurations produced >= 5 trades for {symbol}")
        return pd.DataFrame()

    # Sort by net_profit (primary), then win_rate
    df = df.sort_values(['net_profit', 'win_rate'], ascending=[False, False])

    return df


def main():
    """Run optimization for both assets."""
    print("\n" + "="*80)
    print("COMMODITYSNIPER PARAMETER OPTIMIZATION")
    print("="*80)
    print(f"Testing 72 parameter combinations per asset")
    print(f"Optimization Metrics:")
    print(f"  1. Win Rate >= 40%")
    print(f"  2. Net Profit > $30")
    print(f"  3. Max Loss Streak <= 5")
    print(f"  4. Total Trades >= 5 (quality threshold)")

    assets = ['WHEAT_USD', 'BCO_USD']
    best_configs = {}

    for symbol in assets:
        results_df = optimize_asset(symbol)

        if results_df is None or len(results_df) == 0:
            print(f"\nNo valid configurations found for {symbol}")
            continue

        # Show top 10 configurations
        print(f"\n{'='*80}")
        print(f"TOP 10 CONFIGURATIONS FOR {symbol}")
        print(f"{'='*80}")

        # Select columns to display
        display_cols = ['squeeze_threshold', 'adx_min', 'require_fvg', 'target_rr', 'cooldown_hours',
                        'total_trades', 'win_rate', 'net_profit', 'return_pct', 'max_loss_streak', 'sharpe']

        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 200)
        print(results_df[display_cols].head(10).to_string(index=False))

        # Save full results
        output_path = PROJECT_ROOT / 'data' / f'optimization_results_{symbol}.csv'
        results_df.to_csv(output_path, index=False)
        print(f"\nFull results saved to: {output_path}")

        # Store best config
        best = results_df.iloc[0]
        best_configs[symbol] = best.to_dict()

    # Print final recommendations
    print("\n" + "="*80)
    print("RECOMMENDED CONFIGURATIONS")
    print("="*80)

    for symbol, config in best_configs.items():
        print(f"\n{symbol}:")
        print(f"  squeeze_threshold: {config['squeeze_threshold']}")
        print(f"  adx_min: {config['adx_min']}")
        print(f"  require_fvg: {config['require_fvg']}")
        print(f"  target_rr: {config['target_rr']}")
        print(f"  cooldown_hours: {config['cooldown_hours']}")
        print(f"\n  Expected Performance:")
        print(f"    Trades: {config['total_trades']}")
        print(f"    Win Rate: {config['win_rate']:.1f}%")
        print(f"    Net Profit: ${config['net_profit']:.2f}")
        print(f"    Return: {config['return_pct']:.2f}%")
        print(f"    Max Loss Streak: {config['max_loss_streak']}")
        print(f"    Sharpe Ratio: {config['sharpe']:.2f}")

    print("\n" + "="*80)
    print("Optimization Complete!")
    print("="*80)


if __name__ == "__main__":
    main()
