"""
Sniper Strategy Backtest with Global Ranking (Elite 3 Selection)
Simulates the real "Top 3 signals per day" screening approach.
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
from backend.app.services.sniper_ranker import SniperRanker

CONFIG_PATH = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
POSITION_SIZE = 1000.0
SPREAD_COST = 0.00015

class RankedBacktester:
    """Backtest with daily Top 3 signal selection."""

    def __init__(self):
        self.detector = SniperDetector()
        self.ranker = SniperRanker()
        self.all_trades = []
        self.daily_signals = defaultdict(list)  # date -> list of signals
        self.data_cache = {}  # symbol -> dataframe

    def load_all_data(self, symbols):
        """Pre-load all symbol data for efficient resampling."""
        print("\nLoading data for all symbols...")
        for symbol in symbols:
            data_path = PROJECT_ROOT / 'data' / 'forex_raw' / f"{symbol}.csv"
            if not data_path.exists():
                continue

            try:
                df = pd.read_csv(data_path, index_col=0)
                df.index = pd.to_datetime(df.index)
                df.sort_index(inplace=True)

                # Add indicators
                df = TechnicalIndicators.add_all_indicators(df)
                df['EMA8'] = df['Close'].ewm(span=8, adjust=False).mean()

                self.data_cache[symbol] = df
                print(f"  ✓ {symbol}: {len(df)} rows")
            except Exception as e:
                print(f"  ✗ {symbol}: {e}")

    def generate_signals_for_day(self, date):
        """Generate all potential signals for a specific day, then rank."""
        day_signals = []

        # For each symbol, check if there's a signal on this date
        for symbol, df in self.data_cache.items():
            # Get data up to and including this date
            df_up_to_date = df[df.index.date <= date]

            if len(df_up_to_date) < 220:
                continue

            # Check last bar of this date for signal
            day_data = df_up_to_date[df_up_to_date.index.date == date]

            if day_data.empty:
                continue

            # Check each 15m bar on this date
            for i in range(len(day_data)):
                current_timestamp = day_data.index[i]
                bar_index = df.index.get_loc(current_timestamp)

                if bar_index < 220:
                    continue

                # Get window for analysis
                window = df.iloc[max(0, bar_index-220):bar_index+1]

                # Check for signal
                signal = self.detector.analyze(window, symbol)

                if signal:
                    # Calculate composite score
                    df_15m_window = window
                    df_1h = TechnicalIndicators.resample_to_1h(df_15m_window)
                    df_1h = TechnicalIndicators.add_all_indicators(df_1h)

                    composite = self.ranker.calculate_composite_score(
                        signal, df_15m_window, df_1h
                    )

                    signal_with_score = {
                        'symbol': symbol,
                        'timestamp': current_timestamp,
                        'date': date,
                        'signal': signal['signal'],
                        'price': signal['price'],
                        'sl': signal['sl'],
                        'casket': signal['casket'],
                        'composite_score': composite,
                        'final_score': composite['final_score']
                    }

                    day_signals.append(signal_with_score)

        # Rank and select top 3
        if day_signals:
            day_signals.sort(key=lambda x: x['final_score'], reverse=True)
            top_3 = day_signals[:3]

            for rank, sig in enumerate(top_3, 1):
                sig['rank'] = rank

            return top_3, len(day_signals)
        else:
            return [], 0

    def simulate_trade(self, entry_signal, symbol_data):
        """Simulate a trade from entry signal."""
        entry_time = entry_signal['timestamp']
        entry_price = entry_signal['price']
        position = entry_signal['signal']
        sl_price = entry_signal['sl']
        initial_risk = abs(entry_price - sl_price)

        if initial_risk < entry_price * 0.0001:
            initial_risk = entry_price * 0.001

        is_breakeven = False
        highest_rr = 0.0

        # Get data after entry
        df_after = symbol_data[symbol_data.index > entry_time]

        for i, (timestamp, row) in enumerate(df_after.iterrows()):
            # Calculate current RR
            reward = (row['Close'] - entry_price) if position == 'BUY' else (entry_price - row['Close'])
            current_rr = reward / initial_risk if initial_risk > 0 else 0
            highest_rr = max(highest_rr, current_rr)

            # Break-even at 1.5 RR
            if not is_breakeven and current_rr >= 1.5:
                sl_price = entry_price
                is_breakeven = True

            # Trailing stop at 2.0 RR
            if current_rr >= 2.0:
                if position == 'BUY':
                    sl_price = max(sl_price, row['EMA8'])
                else:
                    sl_price = min(sl_price, row['EMA8'])

            # Check stop hit
            exit_signal = False
            exit_reason = None
            final_price = row['Close']

            if position == 'BUY' and row['Low'] <= sl_price:
                exit_signal = True
                final_price = sl_price
                if is_breakeven and sl_price == entry_price:
                    exit_reason = 'break_even'
                elif current_rr >= 2.0:
                    exit_reason = 'trailing_stop'
                else:
                    exit_reason = 'initial_stop'

            elif position == 'SELL' and row['High'] >= sl_price:
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
                holding_bars = i + 1

                trade = {
                    'symbol': entry_signal['symbol'],
                    'casket': entry_signal['casket'],
                    'rank': entry_signal['rank'],
                    'direction': position,
                    'entry_time': entry_time.isoformat(),
                    'exit_time': timestamp.isoformat(),
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
                    'is_winner': bool(pnl_net > 0),
                    'composite_score': entry_signal['composite_score']
                }

                return trade

            # Max holding period: 100 bars (~25 hours)
            if i >= 100:
                pnl = (row['Close'] - entry_price) / entry_price if position == 'BUY' else (entry_price - row['Close'])
                pnl_net = pnl - SPREAD_COST

                trade = {
                    'symbol': entry_signal['symbol'],
                    'casket': entry_signal['casket'],
                    'rank': entry_signal['rank'],
                    'direction': position,
                    'entry_time': entry_time.isoformat(),
                    'exit_time': timestamp.isoformat(),
                    'entry_price': float(entry_price),
                    'exit_price': float(row['Close']),
                    'initial_risk': float(initial_risk),
                    'pnl_pct': float(pnl * 100),
                    'pnl_net_pct': float(pnl_net * 100),
                    'pnl_dollars': float(pnl_net * POSITION_SIZE),
                    'rr_achieved': float(current_rr),
                    'rr_max': float(highest_rr),
                    'holding_bars': int(i + 1),
                    'exit_reason': 'time_stop',
                    'is_winner': bool(pnl_net > 0),
                    'composite_score': entry_signal['composite_score']
                }

                return trade

        # If reached end of data
        return None

    def run_backtest(self):
        """Run backtest with daily ranking."""
        print("\nStarting ranked backtest (Elite 3 selection per day)...")

        # Get all unique dates
        all_dates = set()
        for df in self.data_cache.values():
            all_dates.update(df.index.date)

        all_dates = sorted(all_dates)
        print(f"Backtesting {len(all_dates)} days...")

        total_signals_found = 0
        total_signals_selected = 0

        for date in all_dates:
            top_3, total_day = self.generate_signals_for_day(date)
            total_signals_found += total_day

            if top_3:
                print(f"\n{date}: {total_day} signals → Top 3 selected")
                total_signals_selected += len(top_3)

                for sig in top_3:
                    print(f"  #{sig['rank']}: {sig['symbol']} {sig['signal']} @ {sig['timestamp'].strftime('%H:%M')} "
                          f"(score: {sig['final_score']:.2f})")

                    # Simulate trade
                    symbol_data = self.data_cache[sig['symbol']]
                    trade = self.simulate_trade(sig, symbol_data)

                    if trade:
                        self.all_trades.append(trade)
            else:
                print(f"{date}: {total_day} signals (no elite signals)")

        return {
            'total_days': len(all_dates),
            'total_signals_found': total_signals_found,
            'total_signals_selected': total_signals_selected,
            'avg_signals_per_day': total_signals_found / len(all_dates) if len(all_dates) > 0 else 0,
            'avg_elite_per_day': total_signals_selected / len(all_dates) if len(all_dates) > 0 else 0
        }

    def calculate_metrics(self):
        """Calculate comprehensive metrics (reusing from enhanced backtester)."""
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

        # Best/worst
        best_trade = df_trades.loc[df_trades['pnl_net_pct'].idxmax()].to_dict() if total_trades > 0 else {}
        worst_trade = df_trades.loc[df_trades['pnl_net_pct'].idxmin()].to_dict() if total_trades > 0 else {}

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
        """Print comprehensive report."""
        print("\n" + "="*80)
        print("SNIPER STRATEGY BACKTEST - WITH GLOBAL RANKING (Elite 3)")
        print("="*80)

        print(f"\n📊 SIGNAL FREQUENCY:")
        print(f"  Total Days Tested:         {frequency['total_days']}")
        print(f"  Total Signals Found:       {frequency['total_signals_found']}")
        print(f"  Avg Signals/Day (before):  {frequency['avg_signals_per_day']:.2f}")
        print(f"  Elite Signals Selected:    {frequency['total_signals_selected']}")
        print(f"  Avg Elite/Day (after):     {frequency['avg_elite_per_day']:.2f}")

        if frequency['avg_elite_per_day'] <= 3.0:
            print(f"  ✅ Signal frequency within target (<=3/day)")
        else:
            print(f"  ⚠️  Signal frequency above target")

        print(f"\n📈 OVERALL PERFORMANCE:")
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

        print(f"\n🗂️  CASKET BREAKDOWN:")
        print(f"  {'Casket':<12} | {'Trades':<7} | {'Win%':<6} | {'Avg RR':<7} | {'Best RR':<8} | {'PF':<5} | {'Net $':<10}")
        print("  " + "-"*76)

        for casket, stats in metrics['casket_breakdown'].items():
            print(f"  {casket:<12} | {stats['total_trades']:<7} | {stats['win_rate']:<6.1f} | "
                  f"1:{stats['avg_rr']:<5.2f} | 1:{stats['best_rr']:<6.2f} | "
                  f"{stats['profit_factor']:<5.2f} | ${stats['net_profit']:<9.2f}")

        print("\n" + "="*80)

        # Target validation
        print("\n✅ TARGET VALIDATION:")
        targets = []

        if frequency['avg_elite_per_day'] <= 3.0:
            targets.append("✅ Elite signal frequency <= 3/day")
        else:
            targets.append(f"⚠️  Elite signals: {frequency['avg_elite_per_day']:.2f}/day (target: <= 3)")

        if 40 <= metrics['win_rate_pct'] <= 50:
            targets.append("✅ Win rate: 40-50%")
        else:
            targets.append(f"⚠️  Win rate: {metrics['win_rate_pct']}% (target: 40-50%)")

        if metrics['avg_rr_per_win'] >= 3.0:
            targets.append("✅ Avg RR per win >= 3.0")
        else:
            targets.append(f"⚠️  Avg RR per win: {metrics['avg_rr_per_win']} (target: >= 3.0)")

        if metrics['profit_factor'] >= 2.0:
            targets.append("✅ Profit factor >= 2.0")
        else:
            targets.append(f"⚠️  Profit factor: {metrics['profit_factor']} (target: >= 2.0)")

        for target in targets:
            print(f"  {target}")

        print("\n" + "="*80)

def main():
    print("="*80)
    print("SNIPER BACKTEST WITH GLOBAL RANKING")
    print("="*80)

    backtester = RankedBacktester()

    # Load config
    with open(CONFIG_PATH, 'r') as f:
        symbols = [p['symbol'] for p in json.load(f)['pairs']]

    # Load all data
    backtester.load_all_data(symbols)

    # Run backtest
    frequency = backtester.run_backtest()

    # Calculate metrics
    if not backtester.all_trades:
        print("\n❌ No trades generated.")
        return

    metrics = backtester.calculate_metrics()

    # Print report
    backtester.print_report(metrics, frequency)

    # Save results
    results_dir = PROJECT_ROOT / 'data' / 'backtest_results'
    results_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    trades_file = results_dir / f'sniper_ranked_trades_{timestamp}.json'
    with open(trades_file, 'w') as f:
        json.dump(backtester.all_trades, f, indent=2)

    metrics_file = results_dir / f'sniper_ranked_metrics_{timestamp}.json'
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
