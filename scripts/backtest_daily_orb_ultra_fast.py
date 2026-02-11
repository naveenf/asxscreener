"""
Ultra-Fast Daily ORB Backtest (Smart Sampling)
Only tests Sydney session hours to avoid wasted iterations
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.services.daily_orb_detector import DailyORBDetector

def run_smart_backtest(symbol: str = "XAG_USD"):
    print(f"\n=== DAILY ORB BACKTEST (ULTRA-FAST/SMART) ===\n")

    # Load data
    print("Loading data...", flush=True)
    df_15m = pd.read_csv(f'data/forex_raw/{symbol}_15_Min.csv', parse_dates=['Date'])
    df_15m.rename(columns={'Date': 'time'}, inplace=True)
    df_15m.set_index('time', inplace=True)

    df_1h = pd.read_csv(f'data/forex_raw/{symbol}_1_Hour.csv', parse_dates=['Date'])
    df_1h.rename(columns={'Date': 'time'}, inplace=True)
    df_1h.set_index('time', inplace=True)

    df_4h = pd.read_csv(f'data/forex_raw/{symbol}_4_Hour.csv', parse_dates=['Date'])
    df_4h.rename(columns={'Date': 'time'}, inplace=True)
    df_4h.set_index('time', inplace=True)

    print(f"✓ Data loaded: {len(df_15m)} 15m rows\n", flush=True)

    # Test 3 key configs
    configs = [
        (1.5, '1h', 2.5),
        (1.5, '4h', 2.5),
        (2.0, '4h', 2.5),
    ]

    all_results = []

    for orb_h, htf_name, target_rr in configs:
        print(f"Testing: ORB {orb_h}h | HTF {htf_name} | RR {target_rr}", end=" | ", flush=True)

        df_htf = df_1h if htf_name == '1h' else df_4h
        detector = DailyORBDetector(orb_hours=orb_h, htf=htf_name, adx_min_htf=20.0)

        trades = []
        balance = 360.0
        wins = 0

        # Smart iteration: only check 15m candles that might have Sydney session signals
        # Sydney session: 19:00-23:00 UTC (and next day start)
        sydney_hours = set([19, 20, 21, 22, 23, 0, 1, 2, 3])

        start_idx = 200
        for i in range(start_idx, len(df_15m)):
            current_hour = df_15m.index[i].hour

            # Skip candles outside Sydney session window (+ some buffer)
            if current_hour not in sydney_hours:
                continue

            current_time = df_15m.index[i]
            htf_slice = df_htf[df_htf.index <= current_time]

            if len(htf_slice) < 20:
                continue

            base_slice = df_15m.iloc[:i+1]
            data = {'15m': base_slice, htf_name: htf_slice}

            result = detector.analyze(data, symbol, target_rr=target_rr, spread=0.0006)

            if result:
                entry_price = result['price']
                stop_loss = result['stop_loss']
                take_profit = result['take_profit']
                direction = result['signal']

                # Find exit (lookahead 100 candles = 25h)
                outcome = None
                pnl = 0.0
                exit_price = 0.0
                exit_time = None
                exit_reason = "OPEN"

                for j in range(i+1, min(i+101, len(df_15m))):
                    future = df_15m.iloc[j]

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

                    exit_time = df_15m.index[j]

                if outcome:
                    risk = abs(entry_price - stop_loss)
                    risk_amt = balance * 0.02
                    units = risk_amt / risk if risk > 0 else 0
                    trade_profit = pnl * units

                    balance += trade_profit
                    if outcome == "WIN":
                        wins += 1

                    trades.append({
                        'Entry_Time': current_time,
                        'Entry_Price': entry_price,
                        'Exit_Price': exit_price,
                        'Stop_Loss': stop_loss,
                        'Take_Profit': take_profit,
                        'Direction': direction,
                        'PnL': trade_profit,
                        'RR': pnl / risk if risk > 0 else 0,
                        'Exit_Reason': exit_reason,
                        'Balance': balance
                    })

        # Calculate metrics
        if not trades:
            print(f"NO TRADES FOUND", flush=True)
            continue

        trades_df = pd.DataFrame(trades)
        total_trades = len(trades)
        win_rate = (wins / total_trades) * 100
        net_profit = balance - 360.0
        return_pct = (net_profit / 360.0) * 100
        avg_rr = trades_df['RR'].mean()
        returns = trades_df['PnL'] / 360.0
        sharpe = (returns.mean() / returns.std()) * np.sqrt(total_trades) if returns.std() > 0 else 0

        # Max drawdown
        trades_df['peak'] = trades_df['Balance'].cummax()
        max_dd = ((trades_df['Balance'] - trades_df['peak']) / trades_df['peak'].max() * 100).min()

        result_row = {
            'ORB_Hours': orb_h,
            'HTF': htf_name,
            'RR_Target': target_rr,
            'Total_Trades': total_trades,
            'Wins': wins,
            'Win_Rate': win_rate,
            'Net_Profit': net_profit,
            'ROI': return_pct,
            'Avg_RR': avg_rr,
            'Sharpe': sharpe,
            'Max_DD': max_dd
        }

        all_results.append(result_row)

        print(f"Trades:{total_trades:2d} | WR:{win_rate:5.1f}% | ROI:{return_pct:6.2f}% | Sharpe:{sharpe:5.2f} | DD:{max_dd:6.1f}%", flush=True)

        # Save trade log
        trades_df.to_csv(f'data/backtest_orb_opt_{orb_h}h_{htf_name}_rr{target_rr}.csv', index=False)

    # Summary
    if all_results:
        summary_df = pd.DataFrame(all_results)
        summary_df.to_csv('data/optimization_results_orb_optimized_XAG_USD.csv', index=False)

        print(f"\n{'='*120}")
        print("SUMMARY - OPTIMIZED DAILY ORB STRATEGY")
        print(f"{'='*120}")
        print(summary_df.to_string(index=False))

        # Viability check
        print(f"\n{'='*120}")
        print("VIABILITY ASSESSMENT")
        print(f"{'='*120}")
        for idx, row in summary_df.iterrows():
            status = "✓ VIABLE" if (row['Win_Rate'] >= 42 and row['ROI'] >= 8.0) else "⚠ MARGINAL" if (row['Win_Rate'] >= 38 and row['ROI'] >= 5.0) else "❌ POOR"
            print(f"{row['ORB_Hours']}h ORB + {row['HTF']} HTF: {status} (WR {row['Win_Rate']:.1f}%, ROI {row['ROI']:.2f}%)")

if __name__ == "__main__":
    run_smart_backtest()
