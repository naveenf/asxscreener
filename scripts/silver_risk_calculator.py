import argparse

def calculate_risk(balance, risk_pct, leverage, entry, stop_loss):
    risk_amount = balance * (risk_pct / 100.0)
    stop_distance = abs(entry - stop_loss)
    
    if stop_distance == 0:
        print("Error: Stop loss cannot be equal to entry price.")
        return

    # Units based on risk
    # Risk = Units * Stop_Distance
    units_by_risk = risk_amount / stop_distance
    
    # Units based on leverage (Buying Power)
    max_notional = balance * leverage
    max_units_by_leverage = max_notional / entry
    
    # Final Units (Min of both, rounded down)
    final_units = int(min(units_by_risk, max_units_by_leverage))
    
    if final_units < 1:
        print(f"\n⚠️ WARNING: Your risk/stop-loss requires less than 1 unit. You cannot trade this setup safely with {risk_pct}% risk.")
        print(f"Minimum trade size is 1 unit. To trade 1 unit, your risk would be ${stop_distance:.2f} ({ (stop_distance/balance)*100:.2f}% of account).")
        return

    actual_risk = final_units * stop_distance
    actual_risk_pct = (actual_risk / balance) * 100
    margin_required = (final_units * entry) / leverage
    notional_value = final_units * entry

    print(f"\n--- SILVER RISK CALCULATOR ($360 Account) ---")
    print(f"Inputs: Balance=${balance}, Risk={risk_pct}%, Leverage={leverage}:1")
    print(f"Entry: ${entry:.3f} | Stop Loss: ${stop_loss:.3f} | Distance: ${stop_distance:.3f}")
    print("-" * 45)
    print(f"✅ RECOMMENDED UNITS: {final_units}")
    print(f"Notional Value: ${notional_value:.2f}")
    print(f"Margin Required: ${margin_required:.2f} ({(margin_required/balance)*100:.1f}% of account)")
    print(f"Actual Risk: ${actual_risk:.2f} ({actual_risk_pct:.2f}%)")
    print("-" * 45)
    
    if margin_required > balance:
        print("❌ CRITICAL: Margin required exceeds account balance! Lower your units or increase leverage (if possible).")
    elif (margin_required / balance) > 0.5:
        print("⚠️ CAUTION: This trade uses more than 50% of your available margin.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Silver Position Sizing Calculator")
    parser.add_argument("--balance", type=float, default=360.0, help="Account balance")
    parser.add_argument("--risk", type=float, default=2.0, help="Risk percentage (e.g. 2.0)")
    parser.add_argument("--leverage", type=float, default=10.0, help="Account leverage")
    parser.add_argument("--entry", type=float, required=True, help="Entry price")
    parser.add_argument("--sl", type=float, required=True, help="Stop loss price")
    
    args = parser.parse_args()
    calculate_risk(args.balance, args.risk, args.leverage, args.entry, args.sl)
