"""
Enhanced Sniper Strategy Backtester
Comprehensive validation with RR tracking, frequency analysis, and casket breakdown.
"""

import pandas as pd
import numpy as np
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.sniper_detector import SniperDetector

CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
POSITION_SIZE = 1000.0
SPREAD_COST = 0.00015

class EnhancedBacktester:
    def __init__(self):
        self.detector = SniperDetector()
        self.all_trades = []
        self.all_signals = []  # Track all signal occurrences

    def run_backtest(self, symbol, df_all):
        """Run backtest on a single symbol with enhanced tracking."""
        trades = []
        signals_generated = []
        position = None
        entry_price = 0.0
        entry_time = None
        sl_price = 0.0
        initial_risk = 0.0
        is_breakeven = False
        highest_rr = 0.0

        # Add indicators
        df_all = TechnicalIndicators.add_all_indicators(df_all)
        df_all['EMA8'] = df_all['Close'].ewm(span=8, adjust=False).mean()

        for i in range(220, len(df_all)):
            current = df_all.iloc[i]
            current_time = current.name

            # EXIT LOGIC
            if position:
                exit_signal = False
                exit_reason = None
                final_price = current['Close']

                # Calculate current RR
                reward = (current['Close'] - entry_price) if position == 'BUY' else (entry_price - current['Close'])
                current_rr = reward / initial_risk if initial_risk > 0 else 0
                highest_rr = max(highest_rr, current_rr)

                # Break-even at 1.5 RR
                if not is_breakeven and current_rr >= 1.5:
                    sl_price = entry_price
                    is_breakeven = True

                # Trailing stop at 2.0 RR
                if current_rr >= 2.0:
                    if position == 'BUY':
                        sl_price = max(sl_price, current['EMA8'])
                    else:
                        sl_price = min(sl_price, current['EMA8'])

                # Check stop hit
                if position == 'BUY' and current['Low'] <= sl_price:
                    exit_signal = True
                    final_price = sl_price
                    if is_breakeven and sl_price == entry_price:
                        exit_reason = 'break_even'
                    elif current_rr >= 2.0:
                        exit_reason = 'trailing_stop'
                    else:
                        exit_reason = 'initial_stop'

                elif position == 'SELL' and current['High'] >= sl_price:
                    exit_signal = True
                    final_price = sl_price
                    if is_breakeven and sl_price == entry_price:
                        exit_reason = 'break_even'
                    elif current_rr >= 2.0:
                        exit_reason = 'trailing_stop'
                    else:
                        exit_reason = 'initial_stop'

                # Execute exit
                if exit_signal:
                    pnl = (final_price - entry_price) / entry_price if position == 'BUY' else (entry_price - final_price) / entry_price
                    pnl_net = pnl - SPREAD_COST

                    holding_bars = (current_time - entry_time).total_seconds() / 900  # 15m bars

                    trade = {
                        'symbol': symbol,
                        'casket': self.detector.get_casket(symbol),
                        'direction': position,
                        'entry_time': entry_time.isoformat(),
                        'exit_time': current_time.isoformat(),
                        'entry_price': float(entry_price),
                        'exit_price': float(final_price),
                        'initial_risk': float(initial_risk),
                        'pnl_pct': float(pnl * 100),
                        'pnl_net_pct': float(pnl_net * 100),
                        'pnl_dollars': float(pnl_net * POSITION_SIZE),
                        'rr_achieved': float(current_rr),
                        'rr_max': float(highest_rr),
                        'holding_bars': int(holding_bars),
                        'exit_reason': exit_reason,
                        'is_winner': bool(pnl_net > 0)
                    }
                    trades.append(trade)

                    position = None
                    highest_rr = 0.0

            # ENTRY LOGIC
            if not position:
                window = df_all.iloc[max(0, i-220):i+1]
                analysis = self.detector.analyze(window, symbol)

                if analysis:
                    # Track signal occurrence (for frequency analysis)
                    signals_generated.append({
                        'symbol': symbol,
                        'casket': analysis['casket'],
                        'timestamp': current_time.isoformat(),
                        'signal': analysis['signal']
                    })

                    # Open position
                    position = analysis['signal']
                    entry_price = analysis['price']
                    entry_time = current_time
                    sl_price = analysis['sl']
                    initial_risk = abs(entry_price - sl_price)

                    # Ensure minimum risk (prevent division by zero)
                    if initial_risk < entry_price * 0.0001:
                        initial_risk = entry_price * 0.001

                    is_breakeven = False

        return trades, signals_generated

    def analyze_signal_frequency(self):
        """Analyze signal frequency (signals per day)."""
        if not self.all_signals:
            return {}

        df_signals = pd.DataFrame(self.all_signals)
        df_signals['date'] = pd.to_datetime(df_signals['timestamp']).dt.date

        signals_per_day = df_signals.groupby('date').size()

        return {
            'total_signals': len(df_signals),
            'total_days': len(signals_per_day),
            'avg_signals_per_day': float(signals_per_day.mean()),
            'max_signals_per_day': int(signals_per_day.max()),
            'min_signals_per_day': int(signals_per_day.min()),
            'days_with_0_signals': int((signals_per_day == 0).sum()) if len(signals_per_day) > 0 else 0,
            'days_with_1_3_signals': int(((signals_per_day >= 1) & (signals_per_day <= 3)).sum()),
            'days_with_4plus_signals': int((signals_per_day > 3).sum()),
            'signals_by_casket': df_signals.groupby('casket').size().to_dict()
        }

    def calculate_metrics(self):
        """Calculate comprehensive performance metrics."""
        if not self.all_trades:
            return {}

        df_trades = pd.DataFrame(self.all_trades)

        # Overall metrics
        total_trades = len(df_trades)
        winners = df_trades[df_trades['is_winner']]
        losers = df_trades[~df_trades['is_winner']]

        win_rate = len(winners) / total_trades * 100 if total_trades > 0 else 0

        gross_profit = winners['pnl_dollars'].sum() if len(winners) > 0 else 0
        gross_loss = abs(losers['pnl_dollars'].sum()) if len(losers) > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # RR metrics
        avg_rr_winners = winners['rr_achieved'].mean() if len(winners) > 0 else 0
        max_rr_captured = df_trades['rr_achieved'].max() if total_trades > 0 else 0
        winners_above_3rr = len(winners[winners['rr_achieved'] >= 3.0])

        # Best/worst trades
        best_trade = df_trades.loc[df_trades['pnl_net_pct'].idxmax()].to_dict() if total_trades > 0 else {}
        worst_trade = df_trades.loc[df_trades['pnl_net_pct'].idxmin()].to_dict() if total_trades > 0 else {}

        # Exit reason breakdown
        exit_reasons = df_trades.groupby('exit_reason').agg({
            'pnl_net_pct': ['count', 'mean'],
            'holding_bars': 'mean'
        }).to_dict()

        # Casket breakdown
        casket_metrics = {}
        for casket in df_trades['casket'].unique():
            casket_trades = df_trades[df_trades['casket'] == casket]
            casket_winners = casket_trades[casket_trades['is_winner']]
            casket_losers = casket_trades[~casket_trades['is_winner']]

            casket_gross_profit = casket_winners['pnl_dollars'].sum() if len(casket_winners) > 0 else 0
            casket_gross_loss = abs(casket_losers['pnl_dollars'].sum()) if len(casket_losers) > 0 else 0
            casket_pf = casket_gross_profit / casket_gross_loss if casket_gross_loss > 0 else float('inf')

            casket_metrics[casket] = {
                'total_trades': len(casket_trades),
                'winners': len(casket_winners),
                'losers': len(casket_losers),
                'win_rate': len(casket_winners) / len(casket_trades) * 100 if len(casket_trades) > 0 else 0,
                'avg_rr': casket_winners['rr_achieved'].mean() if len(casket_winners) > 0 else 0,
                'best_rr': casket_trades['rr_achieved'].max() if len(casket_trades) > 0 else 0,
                'profit_factor': casket_pf,
                'net_profit': casket_trades['pnl_dollars'].sum()
            }

        return {
            'total_trades': total_trades,
            'winning_trades': len(winners),
            'losing_trades': len(losers),
            'win_rate_pct': round(win_rate, 2),
            'profit_factor': round(profit_factor, 2),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'net_profit': round(gross_profit - gross_loss, 2),
            'avg_rr_per_win': round(avg_rr_winners, 2),
            'max_rr_captured': round(max_rr_captured, 2),
            'winners_above_3rr': winners_above_3rr,
            'pct_winners_above_3rr': round(winners_above_3rr / len(winners) * 100, 2) if len(winners) > 0 else 0,
            'avg_holding_bars': round(df_trades['holding_bars'].mean(), 1),
            'best_trade': {
                'symbol': best_trade.get('symbol', 'N/A'),
                'pnl_pct': round(best_trade.get('pnl_net_pct', 0), 2),
                'rr': round(best_trade.get('rr_achieved', 0), 2)
            },
            'worst_trade': {
                'symbol': worst_trade.get('symbol', 'N/A'),
                'pnl_pct': round(worst_trade.get('pnl_net_pct', 0), 2),
                'rr': round(worst_trade.get('rr_achieved', 0), 2)
            },
            'casket_breakdown': casket_metrics
        }

    def print_report(self, metrics, frequency):
        """Print comprehensive backtest report."""
        print("\n" + "="*80)
        print("SNIPER STRATEGY BACKTEST REPORT")
        print("="*80)

        print(f"\n📊 OVERALL PERFORMANCE:")
        print(f"  Total Trades:              {metrics['total_trades']}")
        print(f"  Winning Trades:            {metrics['winning_trades']}")
        print(f"  Losing Trades:             {metrics['losing_trades']}")
        print(f"  Win Rate:                  {metrics['win_rate_pct']}%")
        print(f"  Profit Factor:             {metrics['profit_factor']}")
        print(f"  Net Profit:                ${metrics['net_profit']:.2f}")

        print(f"\n🎯 RISK-REWARD METRICS:")
        print(f"  Avg RR per Win:            1:{metrics['avg_rr_per_win']}")
        print(f"  Max RR Captured:           1:{metrics['max_rr_captured']}")
        print(f"  Winners with RR >= 3.0:    {metrics['winners_above_3rr']} ({metrics['pct_winners_above_3rr']}%)")
        print(f"  Avg Holding Period:        {metrics['avg_holding_bars']} bars (~{metrics['avg_holding_bars']/4:.1f} hours)")

        print(f"\n🏆 BEST TRADE:")
        print(f"  {metrics['best_trade']['symbol']}: +{metrics['best_trade']['pnl_pct']}% (1:{metrics['best_trade']['rr']} RR)")

        print(f"\n❌ WORST TRADE:")
        print(f"  {metrics['worst_trade']['symbol']}: {metrics['worst_trade']['pnl_pct']}% (1:{metrics['worst_trade']['rr']} RR)")

        print(f"\n📈 SIGNAL FREQUENCY:")
        print(f"  Total Signals:             {frequency['total_signals']}")
        print(f"  Total Days:                {frequency['total_days']}")
        print(f"  Avg Signals/Day:           {frequency['avg_signals_per_day']:.2f}")
        print(f"  Max Signals/Day:           {frequency['max_signals_per_day']}")
        print(f"  Days with 1-3 signals:     {frequency['days_with_1_3_signals']}")
        print(f"  Days with 4+ signals:      {frequency['days_with_4plus_signals']}")

        if frequency['avg_signals_per_day'] > 3.0:
            print(f"\n  ⚠️  WARNING: Avg > 3 signals/day. Consider tightening filters.")
        else:
            print(f"\n  ✅ Signal frequency within target (<=3/day)")

        print(f"\n🗂️  CASKET BREAKDOWN:")
        print(f"  {'Casket':<12} | {'Trades':<7} | {'Win%':<6} | {'Avg RR':<7} | {'Best RR':<8} | {'PF':<5} | {'Net $':<10}")
        print("  " + "-"*76)

        for casket, stats in metrics['casket_breakdown'].items():
            print(f"  {casket:<12} | {stats['total_trades']:<7} | {stats['win_rate']:<6.1f} | "
                  f"1:{stats['avg_rr']:<5.2f} | 1:{stats['best_rr']:<6.2f} | "
                  f"{stats['profit_factor']:<5.2f} | ${stats['net_profit']:<9.2f}")

        print("\n" + "="*80)

        # Validation against targets
        print("\n✅ TARGET VALIDATION:")
        targets_met = []

        if frequency['avg_signals_per_day'] <= 3.0:
            targets_met.append("✅ Signal frequency <= 3/day")
        else:
            targets_met.append("❌ Signal frequency > 3/day")

        if 40 <= metrics['win_rate_pct'] <= 50:
            targets_met.append("✅ Win rate: 40-50%")
        else:
            targets_met.append(f"⚠️  Win rate: {metrics['win_rate_pct']}% (target: 40-50%)")

        if metrics['avg_rr_per_win'] >= 3.0:
            targets_met.append("✅ Avg RR per win >= 3.0")
        else:
            targets_met.append(f"⚠️  Avg RR per win: {metrics['avg_rr_per_win']} (target: >= 3.0)")

        if metrics['profit_factor'] >= 2.0:
            targets_met.append("✅ Profit factor >= 2.0")
        else:
            targets_met.append(f"⚠️  Profit factor: {metrics['profit_factor']} (target: >= 2.0)")

        for target in targets_met:
            print(f"  {target}")

        print("\n" + "="*80)

def main():
    print("="*80)
    print("ENHANCED SNIPER BACKTEST - Starting...")
    print("="*80)

    backtester = EnhancedBacktester()

    # Load forex pairs
    with open(CONFIG_PATH, 'r') as f:
        symbols = [p['symbol'] for p in json.load(f)['pairs']]

    print(f"\nTesting {len(symbols)} symbols...")

    # Run backtest on all symbols
    for symbol in symbols:
        data_path = PROJECT_ROOT / 'data' / 'forex_raw' / f"{symbol}.csv"
        if not data_path.exists():
            print(f"  {symbol}: Data not found")
            continue

        try:
            df = pd.read_csv(data_path, header=[0, 1, 2], index_col=0)
            df.columns = df.columns.get_level_values(0)
            df.index = pd.to_datetime(df.index)
            df.sort_index(inplace=True)

            trades, signals = backtester.run_backtest(symbol, df)
            backtester.all_trades.extend(trades)
            backtester.all_signals.extend(signals)

            if trades:
                print(f"  {symbol}: {len(signals)} signals → {len(trades)} trades")
            else:
                print(f"  {symbol}: {len(signals)} signals → 0 trades")
        except Exception as e:
            print(f"  {symbol}: Error - {e}")

    # Calculate metrics
    if not backtester.all_trades:
        print("\n❌ No trades generated. Strategy too restrictive or market conditions unfavorable.")
        return

    metrics = backtester.calculate_metrics()
    frequency = backtester.analyze_signal_frequency()

    # Print report
    backtester.print_report(metrics, frequency)

    # Save results
    results_dir = PROJECT_ROOT / 'data' / 'backtest_results'
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Save trades
    trades_file = results_dir / f'sniper_trades_{timestamp}.json'
    with open(trades_file, 'w') as f:
        json.dump(backtester.all_trades, f, indent=2)

    # Save metrics
    metrics_file = results_dir / f'sniper_metrics_{timestamp}.json'
    combined = {
        'metrics': metrics,
        'frequency': frequency,
        'timestamp': timestamp
    }
    with open(metrics_file, 'w') as f:
        json.dump(combined, f, indent=2)

    print(f"\n💾 Results saved:")
    print(f"  Trades:  {trades_file}")
    print(f"  Metrics: {metrics_file}")

if __name__ == "__main__":
    main()
