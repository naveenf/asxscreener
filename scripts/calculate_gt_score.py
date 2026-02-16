"""
GT-Score Calculator for Backtest CSV Results
Analyze existing backtest CSV files and calculate the GT-Score.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
import argparse

# Add parent directory to path to import backend services
sys.path.append(str(Path(__file__).parent.parent))

from backend.app.services.backtest_metrics import calculate_gt_score, MIN_TRADES

def analyze_csv(csv_path: str):
    print(f"\n=== GT-SCORE ANALYSIS: {csv_path} ===")
    
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # 1. Identify Return Column
    return_col = None
    for col in ['Profit_Pct', 'pnl_pct', 'Return_Pct', 'Return']:
        if col in df.columns:
            return_col = col
            break
            
    if return_col is None:
        print(f"Could not find return column in {df.columns.tolist()}")
        return
        
    print(f"Found return column: {return_col}")

    # 2. Identify Balance/Equity Column
    equity_col = None
    for col in ['Balance', 'portfolio_value', 'Equity', 'peak']:
        if col in df.columns:
            equity_col = col
            break
            
    if equity_col is None:
        print("Could not find equity column. Using cumulative returns fallback.")
        equity_df = None
    else:
        print(f"Found equity column: {equity_col}")
        equity_df = pd.DataFrame({'portfolio_value': df[equity_col]})

    # 3. Calculate GT-Score
    raw_returns = df[return_col].values
    
    # Robust detection: Check column name or presence of large values (>1.0)
    # A single value > 1.0 (100%) in a trading context almost certainly means percentage.
    # Exception: Cryptos/hyper-volatility, but for ASX/Forex it's a safe bet.
    if return_col == 'Profit_Pct' or np.max(np.abs(raw_returns)) > 1.0:
        returns = raw_returns / 100.0
        print("✓ Detected percentage format (dividing by 100)")
    else:
        returns = raw_returns
        print("✓ Detected decimal format")

    result = calculate_gt_score(returns, equity_df)

    # 4. Display Report
    if result['valid']:
        status = "✅ VALID"
    else:
        status = "❌ INSUFFICIENT DATA"
        
    print(f"\nRESULTS:")
    print(f"  Total Trades:           {result['trade_count']}")
    print(f"  GT-Score:               {result['gt_score']:.6f} ({status})")
    
    if result['valid']:
        score = result['gt_score']
        if score > 0.10: interp = "Excellent"
        elif score > 0.05: interp = "Good"
        elif score > 0.01: interp = "Viable"
        elif score > 0.00: interp = "Marginal"
        else: interp = "Poor"
        print(f"  Interpretation:         {interp}")
    else:
        needed = MIN_TRADES - result['trade_count']
        print(f"  ⚠️  WARNING: Statistical significance is low.")
        print(f"  Need {needed} more trades to meet validation threshold ({MIN_TRADES}).")
        print(f"  Current score is for reference only and likely overfit.")
        
    print("\nCOMPONENTS:")
    c = result['components']
    print(f"  mu (Mean Return):      {c['mu']:.6f}")
    print(f"  z (Significance):     {c['z_score']:.4f} (ln_z: {c['ln_z_term']:.4f})")
    print(f"  r2 (Consistency):     {c['r_squared']:.4f}")
    print(f"  sigma_d (Downside):   {c['sigma_d']:.6f}")
    print("-" * 40)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calculate GT-Score from Backtest CSV")
    parser.add_argument("csv_path", help="Path to the backtest results CSV file")
    
    args = parser.parse_args()
    analyze_csv(args.csv_path)
