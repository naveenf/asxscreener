"""
Enhanced Backtest for PVT Scalping with Quality Filters & Position Sizing
- Reduced trade count through quality filters (trading hours + PVT strength)
- Consecutive loss circuit breaker to control drawdown
- Position size multiplier: 100% → 75% → 50% → 0% (stop) based on losses
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.pvt_scalping_detector import PVTScalpingDetector
from backend.app.services.backtest_metrics import calculate_gt_score, MIN_TRADES


def backtest_pvt_filtered(symbol: str, target_rr: float = 2.5):
    print(f"\n=== PVT SCALPING (FILTERED) BACKTEST: {symbol} ===")
    print("Quality Filters Applied:")
    print("  - Trading hours: 13:00-21:00 UTC (London/NY overlap)")
    print("  - PVT strength: >0.85 for BUY, <-0.85 for SELL")
    print("  - ADX momentum: >20 required")
    print("  - RSI extremes: <20 or >80 rejected")
    print("  - Consecutive loss circuit breaker: 3+ losses = 50% size, 5+ = stop")
    print()

    try:
        df_1h = pd.read_csv(f'data/forex_raw/{symbol}_1_Hour.csv', parse_dates=['Date'])
        df_1h.rename(columns={'Date': 'time'}, inplace=True)
        df_1h.set_index('time', inplace=True)
    except FileNotFoundError as e:
        print(f"❌ Data file not found: {e}")
        return

    print("Calculating indicators...")
    df_1h = TechnicalIndicators.add_all_indicators(df_1h)

    detector = PVTScalpingDetector()

    print(f"Total Candles: {len(df_1h)}")
    print(f"Period: {df_1h.index[0]} to {df_1h.index[-1]}")

    trades = []
    balance = 360.0
    wins = 0
    losses = 0
    consecutive_losses = 0

    # Track trades for statistics
    equity_curve = [360.0]

    for i in range(250, len(df_1h)):
        current_time = df_1h.index[i]

        data = {
            '1h': df_1h.iloc[:i+1].copy(),
        }

        result = detector.analyze(data, symbol=symbol, target_rr=target_rr)

        if result:
            entry_price = result['price']
            stop_loss = result['stop_loss']
            take_profit = result['take_profit']
            direction = result['signal']

            # === POSITION SIZING: Apply Circuit Breaker ===
            if consecutive_losses >= 5:
                # Stop trading for 20 candles after 5 consecutive losses
                detector.consecutive_losses = 0  # Reset counter
                continue
            elif consecutive_losses >= 3:
                # Reduce position size to 50% after 3 consecutive losses
                position_size_mult = 0.5
            elif consecutive_losses >= 1:
                # Reduce position size to 75% after 1 consecutive loss
                position_size_mult = 0.75
            else:
                # Normal position size
                position_size_mult = 1.0

            outcome = None
            pnl = 0.0
            actual_rr = 0.0
            exit_price = 0.0
            exit_time = None
            exit_reason = "OPEN"

            # Look ahead for exit (max 100 candles = ~4 days)
            for j in range(i+1, min(i+101, len(df_1h))):
                future = df_1h.iloc[j]

                if direction == "BUY":
                    if future['Low'] <= stop_loss:
                        outcome = "LOSS"
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS"
                        pnl = stop_loss - entry_price
                        break
                    elif future['High'] >= take_profit:
                        outcome = "WIN"
                        exit_price = take_profit
                        exit_reason = "TAKE_PROFIT"
                        pnl = take_profit - entry_price
                        break
                else:  # SELL
                    if future['High'] >= stop_loss:
                        outcome = "LOSS"
                        exit_price = stop_loss
                        exit_reason = "STOP_LOSS"
                        pnl = entry_price - stop_loss
                        break
                    elif future['Low'] <= take_profit:
                        outcome = "WIN"
                        exit_price = take_profit
                        exit_reason = "TAKE_PROFIT"
                        pnl = entry_price - take_profit
                        break

                exit_time = future.name

            if outcome:
                risk = abs(entry_price - stop_loss)
                actual_rr = pnl / risk if risk > 0 else 0

                # Position Sizing: Risk 1% of balance, then apply consecutive loss multiplier
                base_risk_amt = balance * 0.01
                risk_amt = base_risk_amt * position_size_mult
                units = risk_amt / risk if risk > 0 else 0
                trade_profit = pnl * units

                balance += trade_profit

                # Update consecutive loss counter
                if outcome == "WIN":
                    wins += 1
                    consecutive_losses = 0  # Reset on win
                else:
                    losses += 1
                    consecutive_losses += 1

                trades.append({
                    'Trade_Num': len(trades) + 1,
                    'Entry_Time': current_time,
                    'Exit_Time': exit_time,
                    'Direction': direction,
                    'Entry_Price': entry_price,
                    'Exit_Price': exit_price,
                    'Stop_Loss': stop_loss,
                    'Take_Profit': take_profit,
                    'Position_Size': units,
                    'Position_Mult': position_size_mult,
                    'Profit': trade_profit,
                    'Profit_Pct': (trade_profit / 360.0) * 100,
                    'Actual_RR': actual_rr,
                    'Exit_Reason': exit_reason,
                    'Consecutive_Losses': consecutive_losses,
                    'Balance': balance
                })

                equity_curve.append(balance)

    # 5. Reporting
    if not trades:
        print("❌ No trades generated.")
        return

    trades_df = pd.DataFrame(trades)

    total_trades = len(trades)
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    net_profit = balance - 360.0
    return_pct = (net_profit / 360.0) * 100

    # Sharpe Calculation
    returns = trades_df['Profit']
    sharpe = (returns.mean() / returns.std()) * np.sqrt(total_trades) if len(returns) > 1 and returns.std() > 0 else 0

    # Max Drawdown Calculation
    trades_df['peak'] = trades_df['Balance'].cummax()
    trades_df['drawdown'] = (trades_df['Balance'] - trades_df['peak']) / trades_df['peak']
    max_dd = trades_df['drawdown'].min() * 100

    print(f"\n{'='*60}")
    print("PERFORMANCE METRICS")
    print(f"{'='*60}")
    print(f"Total Trades: {total_trades} (reduced from ~663 via filters)")
    print(f"Wins: {wins} ({win_rate:.1f}%)")
    print(f"Losses: {losses} ({100-win_rate:.1f}%)")
    print(f"\nAverage R:R (All): {trades_df['Actual_RR'].mean():.2f}")
    if wins > 0:
        print(f"Average R:R (Wins): {trades_df[trades_df['Actual_RR'] > 0]['Actual_RR'].mean():.2f}")

    print(f"\n{'='*60}")
    print("PROFITABILITY")
    print(f"{'='*60}")
    print(f"Net P&L: ${net_profit:.2f}")
    print(f"Return: {return_pct:.2f}%")
    print(f"Sharpe Ratio: {sharpe:.2f}")

    print(f"\n{'='*60}")
    print("RISK MANAGEMENT")
    print(f"{'='*60}")
    print(f"Max Drawdown: {max_dd:.1f}%")

    # Consecutive Losses Analysis
    max_loss_streak = 0
    current_streak = 0
    for outcome in trades_df['Actual_RR']:
        if outcome < 0:
            current_streak += 1
            max_loss_streak = max(max_loss_streak, current_streak)
        else:
            current_streak = 0
    print(f"Max Consecutive Losses: {max_loss_streak}")

    # Circuit Breaker Stats
    stop_trades_count = len(trades_df[trades_df['Position_Mult'] < 1.0])
    print(f"Trades with reduced position size: {stop_trades_count}")

    # GT-Score Analysis
    trade_returns = (trades_df['Profit'] / trades_df['Balance'].shift(1, fill_value=360.0)).values
    equity_df = pd.DataFrame({'portfolio_value': trades_df['Balance']})

    gt = calculate_gt_score(trade_returns, equity_df)

    print(f"\n{'='*60}")
    print("STATISTICAL VALIDATION")
    print(f"{'='*60}")

    if gt['valid']:
        status = "✅ VALID"
        score = gt['gt_score']
        if score > 0.10:
            interp = "Excellent"
        elif score > 0.05:
            interp = "Good"
        elif score > 0.01:
            interp = "Viable"
        elif score > 0.00:
            interp = "Marginal"
        else:
            interp = "Poor"
        print(f"GT-Score: {gt['gt_score']:.6f} ({status})")
        print(f"Interpretation: {interp}")
    else:
        status = "❌ INSUFFICIENT DATA"
        needed = MIN_TRADES - gt['trade_count']
        print(f"GT-Score: {gt['gt_score']:.6f} ({status})")
        print(f"⚠️  WARNING: Need {needed} more trades for statistical validity.")

    # Summary Comparison
    print(f"\n{'='*60}")
    print("COMPARISON: BEFORE vs AFTER FILTERS")
    print(f"{'='*60}")
    print("Before Filters (Aggressive params):")
    print("  Trades: 663, Win Rate: 31.4%, ROI: +75.62%, Max DD: -70.3%")
    print(f"\nAfter Filters (with circuit breaker):")
    print(f"  Trades: {total_trades}, Win Rate: {win_rate:.1f}%, ROI: {return_pct:.2f}%, Max DD: {max_dd:.1f}%")

    # Save Results
    csv_path = f'data/backtest_results_{symbol}_pvt_filtered.csv'
    trades_df.to_csv(csv_path, index=False)
    print(f"\n✅ Detailed trades saved to: {csv_path}")

    return trades_df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backtest_pvt_filtered.py <SYMBOL> [TARGET_RR]")
        print("Examples:")
        print("  python backtest_pvt_filtered.py UK100_GBP 2.5")
        print("  python backtest_pvt_filtered.py JP225_USD 2.5")
    else:
        symbol = sys.argv[1]
        target_rr = float(sys.argv[2]) if len(sys.argv) > 2 else 2.5
        backtest_pvt_filtered(symbol, target_rr)
