"""
Backtest Engine for Enhanced Sniper Strategy
Supports 15m Base + 1H HTF + 4H HTF analysis.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.enhanced_sniper_detector import EnhancedSniperDetector

def backtest_enhanced_sniper(symbol: str, target_rr: float = 2.0):
    print(f"\n=== ENHANCED SNIPER BACKTEST: {symbol} ===")
    
    # 1. Load Data
    try:
        df_15m = pd.read_csv(f'data/forex_raw/{symbol}_15_Min.csv', parse_dates=['Date'])
        df_1h = pd.read_csv(f'data/forex_raw/{symbol}_1_Hour.csv', parse_dates=['Date'])
        df_4h = pd.read_csv(f'data/forex_raw/{symbol}_4_Hour.csv', parse_dates=['Date'])
        
        # Rename Date to time for consistency
        for df in [df_15m, df_1h, df_4h]:
            df.rename(columns={'Date': 'time'}, inplace=True)
            
    except FileNotFoundError as e:
        print(f"❌ Data file not found: {e}")
        return

    # 2. Add Indicators
    print("Calculating indicators...")
    df_15m = TechnicalIndicators.add_all_indicators(df_15m)
    df_1h = TechnicalIndicators.add_all_indicators(df_1h)
    df_4h = TechnicalIndicators.add_all_indicators(df_4h)
    
    # Calculate SMA200 for 4H if missing (critical for trend filter)
    if 'SMA200' not in df_4h.columns:
        df_4h['SMA200'] = df_4h['Close'].rolling(window=200).mean()

    # 3. Initialize Detector
    detector = EnhancedSniperDetector(symbol=symbol)
    detector.target_rr = target_rr
    
    print(f"Strategy: {detector.name} (15m base, 1H + 4H HTF)")
    print(f"Target R:R: {target_rr}")
    print(f"Period: {df_15m.iloc[0]['time']} to {df_15m.iloc[-1]['time']}")

    trades = []
    balance = 360.0  # Starting Balance
    wins = 0
    losses = 0
    
    # 4. Simulation Loop
    # Start after warm-up period (220 bars)
    for i in range(220, len(df_15m)):
        current_time = df_15m.iloc[i]['time']
        
        # Align HTF Data
        # Find 1H candle index
        htf_idx = df_1h['time'].searchsorted(current_time, side='right') - 1
        if htf_idx < 60: continue
        
        # Find 4H candle index
        htf2_idx = df_4h['time'].searchsorted(current_time, side='right') - 1
        if htf2_idx < 200: continue
        
        # Slice data to simulate real-time
        data = {
            'base': df_15m.iloc[:i+1].copy(),
            'htf': df_1h.iloc[:htf_idx+1].copy(),
            'htf2': df_4h.iloc[:htf2_idx+1].copy()
        }
        
        # Detect Signal
        # Updated to call analyze() instead of detect()
        result = detector.analyze(data, symbol=symbol, target_rr=target_rr)
        
        if result:
            entry_price = result['price']
            stop_loss = result['stop_loss']
            take_profit = result['take_profit']
            direction = result['signal']
            
            # Simulate Trade Outcome
            outcome = None
            pnl = 0.0
            actual_rr = 0.0
            exit_price = 0.0
            exit_time = None
            exit_reason = "OPEN"
            
            # Look ahead for exit
            for j in range(i+1, len(df_15m)):
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
                else: # SELL
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
                
                exit_time = future['time']

            if outcome:
                risk = abs(entry_price - stop_loss)
                actual_rr = pnl / risk if risk > 0 else 0
                
                # Position Sizing (Risk 2% of Balance)
                risk_amt = balance * 0.02
                units = risk_amt / risk if risk > 0 else 0
                trade_profit = pnl * units
                
                balance += trade_profit
                if outcome == "WIN": wins += 1
                else: losses += 1
                
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
                    'Profit': trade_profit,
                    'Profit_Pct': (trade_profit / 360.0) * 100, # ROI based on starting balance
                    'Actual_RR': actual_rr,
                    'Exit_Reason': exit_reason,
                    'Balance': balance
                })
                
    # 5. Reporting
    if not trades:
        print("❌ No trades generated.")
        return

    trades_df = pd.DataFrame(trades)
    
    total_trades = len(trades)
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    net_profit = balance - 360.0
    return_pct = (net_profit / 360.0) * 100
    
    # Sharpe Calc
    returns = trades_df['Profit']
    sharpe = (returns.mean() / returns.std()) * np.sqrt(total_trades) if len(returns) > 1 and returns.std() > 0 else 0
    
    # Max Drawdown
    trades_df['peak'] = trades_df['Balance'].cummax()
    trades_df['drawdown'] = (trades_df['Balance'] - trades_df['peak']) / trades_df['peak']
    max_dd = trades_df['drawdown'].min() * 100

    print(f"\nTotal Trades: {total_trades}")
    print(f"Wins: {wins} ({win_rate:.1f}%)")
    print(f"Losses: {losses} ({100-win_rate:.1f}%)")
    print(f"\nAverage R:R (All): {trades_df['Actual_RR'].mean():.2f}")
    if wins > 0:
        print(f"Average R:R (Wins): {trades_df[trades_df['Actual_RR'] > 0]['Actual_RR'].mean():.2f}")
    
    print(f"\nNet P&L: ${net_profit:.2f}")
    print(f"Return: {return_pct:.2f}%")
    print(f"Sharpe Ratio: {sharpe:.2f}")
    
    print(f"\nMax Drawdown: {max_dd:.1f}%")
    
    # Consecutive Losses
    loss_streak = 0
    max_loss_streak = 0
    for outcome in trades_df['Actual_RR']:
        if outcome < 0:
            loss_streak += 1
            max_loss_streak = max(max_loss_streak, loss_streak)
        else:
            loss_streak = 0
    print(f"Max Consecutive Losses: {max_loss_streak}")

    # Save Results
    csv_path = f'data/backtest_results_{symbol}_enhanced.csv'
    trades_df.to_csv(csv_path, index=False)
    print(f"\n✅ Detailed trades saved to: {csv_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python backtest_enhanced_sniper.py <SYMBOL>")
    else:
        backtest_enhanced_sniper(sys.argv[1])
