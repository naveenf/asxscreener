"""
Analyze backtest results to identify high-loss trading hours.
Generates time filter recommendations for Enhanced Sniper strategy.
"""

import pandas as pd
import sys

def analyze_loss_hours(csv_path: str, min_trades: int = 2, loss_threshold: float = 60.0):
    """
    Analyze loss patterns by hour of day.

    Args:
        csv_path: Path to backtest results CSV
        min_trades: Minimum trades per hour to consider
        loss_threshold: Loss rate % threshold to flag hour as problematic
    """
    print(f"\n{'='*60}")
    print(f"LOSS HOUR ANALYSIS")
    print(f"{'='*60}")
    print(f"File: {csv_path}")

    # Load backtest results
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ File not found: {csv_path}")
        return []

    if len(df) == 0:
        print("❌ No trades found in CSV")
        return []

    # Parse timestamps
    df['Entry_Time'] = pd.to_datetime(df['Entry_Time'])
    df['Hour_UTC'] = df['Entry_Time'].dt.hour
    df['Day_of_Week'] = df['Entry_Time'].dt.day_name()

    # Classify trades
    # 'Exit_Reason' can be 'STOP_LOSS', 'TAKE_PROFIT', 'OPEN'
    df['Is_Loss'] = df['Exit_Reason'] == 'STOP_LOSS'

    # Group by hour
    hourly_stats = df.groupby('Hour_UTC').agg({
        'Trade_Num': 'count',
        'Is_Loss': ['sum', 'mean']
    }).round(3)

    hourly_stats.columns = ['Trade_Count', 'Losses', 'Loss_Rate']
    hourly_stats['Loss_Rate'] = hourly_stats['Loss_Rate'] * 100
    hourly_stats = hourly_stats.sort_values('Loss_Rate', ascending=False)

    print(f"\n{'Hour (UTC)':<12} {'Trades':<8} {'Losses':<8} {'Loss Rate':<12} {'Flag'}")
    print("-" * 60)

    problem_hours = []

    for hour, row in hourly_stats.iterrows():
        trade_count = int(row['Trade_Count'])
        losses = int(row['Losses'])
        loss_rate = row['Loss_Rate']

        # Flag problematic hours
        is_problem = (trade_count >= min_trades) and (loss_rate >= loss_threshold)
        flag = "⚠️ BLOCK" if is_problem else ""

        if is_problem:
            problem_hours.append(int(hour))

        print(f"{hour:02d}:00 - {hour:02d}:59   {trade_count:<8} {losses:<8} {loss_rate:>6.1f}%      {flag}")

    # Day of week analysis
    print(f"\n{'='*60}")
    print("LOSS RATE BY DAY OF WEEK")
    print(f"{'='*60}")

    daily_stats = df.groupby('Day_of_Week').agg({
        'Trade_Num': 'count',
        'Is_Loss': ['sum', 'mean']
    }).round(3)

    daily_stats.columns = ['Trade_Count', 'Losses', 'Loss_Rate']
    daily_stats['Loss_Rate'] = daily_stats['Loss_Rate'] * 100

    # Reorder to weekday sequence
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    daily_stats = daily_stats.reindex([d for d in day_order if d in daily_stats.index])

    for day, row in daily_stats.iterrows():
        print(f"{day:<12} Trades: {int(row['Trade_Count']):<3}  Losses: {int(row['Losses']):<3}  Loss Rate: {row['Loss_Rate']:>6.1f}%")

    # Recommendations
    print(f"\n{'='*60}")
    print("RECOMMENDATIONS")
    print(f"{'='*60}")

    if len(problem_hours) > 0:
        print(f"\n✅ Add time filter to block these hours: {sorted(problem_hours)}")
        print(f"\nCode snippet for enhanced_sniper_detector.py:")
        print(f"```python")
        print(f"HIGH_LOSS_HOURS = {sorted(problem_hours)}  # UTC")
        print(f"")
        print(f"# In analyze() method, add after loading data:")
        print(f"current_hour = df_15m.iloc[-1]['time'].hour")
        print(f"if current_hour in HIGH_LOSS_HOURS:")
        print(f"    return None  # Block entry during high-loss hours")
        print(f"```")
    else:
        print(f"\n✅ No problematic hours identified (all hours have <{loss_threshold}% loss rate or <{min_trades} trades)")
        print(f"   Time filters may not be necessary for this asset.")

    return problem_hours

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_loss_hours.py <backtest_csv_path>")
        print("Example: python analyze_loss_hours.py data/backtest_results_AUD_USD_enhanced.csv")
        sys.exit(1)

    csv_path = sys.argv[1]
    analyze_loss_hours(csv_path, min_trades=2, loss_threshold=60.0)
