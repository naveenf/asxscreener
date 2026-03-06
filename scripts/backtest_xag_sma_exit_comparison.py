"""
XAG_USD SmaScalping — Exit strategy comparison.

Compares three exit modes, all using full production entry filters:
  A) Fixed RR=12  (current)           — hard SL + TP at 12×risk
  B) SMA20 trailing exit              — hard SL + close below SMA20 exits early
  C) SMA50 trailing exit              — hard SL + close below SMA50 exits early

All modes:
  - TP is capped at 12R (current deployed)
  - Hard SL is always enforced (structural + ATR floor)
  - SMA trailing exit: variable R pnl based on exit price vs entry risk

Production entry filters:
  di_threshold=35, di_persist=1, atr_ratio=1.2, di_slope=True, avoid_hours={14,15,16}

Output: data/backtest_xag_sma_exit_comparison.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_xag_sma_exit_comparison.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

SYMBOL       = "XAG_USD"
SPREAD       = 0.03
DI_THRESHOLD = 35.0
DI_PERSIST   = 1
ATR_RATIO    = 1.2
AVOID_HOURS  = {14, 15, 16}
TARGET_RR    = 12.0


def load_and_prep() -> pd.DataFrame:
    csv = DATA_DIR / f"{SYMBOL}_5_Min.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for period, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(period).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def run_backtest(df: pd.DataFrame, exit_mode: str) -> dict | None:
    """
    exit_mode: 'fixed'  — hard SL + TP at TARGET_RR
               'sma20'  — hard SL + TP + SMA20 close-below trailing exit
               'sma50'  — hard SL + TP + SMA50 close-below trailing exit
    """
    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    sma20    = df["SMA20"].values
    sma50    = df["SMA50"].values
    sma100   = df["SMA100"].values
    di_plus  = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    atr_arr  = df["ATR"].values
    hours    = df.index.hour

    sma_trail = sma20 if exit_mode == "sma20" else sma50

    balance    = INITIAL_BALANCE
    trades     = []
    in_trade   = False
    sl = tp = direction = entry_price = risk_amount = None
    start = 22

    for i in range(start, len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # --- Exit ---
        if in_trade:
            exited   = False
            result   = None
            exit_prc = None

            if direction == "BUY":
                # Hard SL (worst case, checked first)
                if l <= sl:
                    result   = "LOSS"
                    exit_prc = sl
                    exited   = True
                # TP
                elif h >= tp:
                    result   = "WIN"
                    exit_prc = tp
                    exited   = True
                # Trailing SMA exit (close below SMA)
                elif exit_mode != "fixed" and c < sma_trail[i]:
                    result   = "WIN" if c > entry_price else "LOSS"
                    exit_prc = c
                    exited   = True
            else:  # SELL
                if h >= sl:
                    result   = "LOSS"
                    exit_prc = sl
                    exited   = True
                elif l <= tp:
                    result   = "WIN"
                    exit_prc = tp
                    exited   = True
                elif exit_mode != "fixed" and c > sma_trail[i]:
                    result   = "WIN" if c < entry_price else "LOSS"
                    exit_prc = c
                    exited   = True

            if exited:
                if direction == "BUY":
                    r_mult = (exit_prc - entry_price) / risk_amount
                else:
                    r_mult = (entry_price - exit_prc) / risk_amount
                pnl      = balance * RISK_PCT * r_mult
                balance += pnl
                trades.append({"result": result, "pnl": pnl, "balance": balance,
                               "r_mult": round(r_mult, 3)})
                in_trade = False
            continue

        # --- Session filter ---
        if hours[i] in AVOID_HOURS:
            continue

        # --- Entry filters ---
        di_plus_pers  = all(di_plus[i - j]  > DI_THRESHOLD for j in range(DI_PERSIST))
        di_minus_pers = all(di_minus[i - j] > DI_THRESHOLD for j in range(DI_PERSIST))
        di_slope_buy  = di_plus[i]  > di_plus[i - 2]
        di_slope_sell = di_minus[i] > di_minus[i - 2]
        atr_avg       = atr_arr[i - 20:i].mean()
        atr_ok        = (atr_avg > 0) and (atr_arr[i] >= ATR_RATIO * atr_avg)

        is_buy = (
            c > sma20[i] and c > sma50[i] and c > sma100[i]
            and di_plus_pers and di_plus[i] > di_minus[i]
            and di_slope_buy and atr_ok
        )
        is_sell = (
            c < sma20[i] and c < sma50[i] and c < sma100[i]
            and di_minus_pers and di_minus[i] > di_plus[i]
            and di_slope_sell and atr_ok
        )

        if not (is_buy or is_sell):
            continue

        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        atr_val = atr_arr[i]
        if is_buy:
            stop_dist   = max(c - prev_low, atr_val)
            sl_p        = c - stop_dist - SPREAD
            risk        = c - sl_p
            if risk <= 0: continue
            direction    = "BUY"
            sl           = sl_p
            tp           = c + risk * TARGET_RR
            entry_price  = c
            risk_amount  = risk
        else:
            stop_dist   = max(prev_high - c, atr_val)
            sl_p        = c + stop_dist + SPREAD
            risk        = sl_p - c
            if risk <= 0: continue
            direction    = "SELL"
            sl           = sl_p
            tp           = c - risk * TARGET_RR
            entry_price  = c
            risk_amount  = risk

        in_trade = True

    if len(trades) < 5:
        return None

    df_t   = pd.DataFrame(trades)
    n      = len(df_t)
    wins   = (df_t["result"] == "WIN").sum()
    wr     = wins / n * 100
    roi    = df_t["pnl"].sum() / INITIAL_BALANCE * 100
    rets   = df_t["pnl"] / INITIAL_BALANCE
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    equity = df_t["balance"].values
    peak   = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak * 100).min())
    avg_r  = df_t["r_mult"].mean()

    return {
        "exit_mode": exit_mode,
        "trades":    n,
        "wins":      int(wins),
        "win_rate":  round(wr, 1),
        "roi":       round(roi, 2),
        "sharpe":    round(sharpe, 2),
        "max_dd":    round(max_dd, 2),
        "avg_r":     round(avg_r, 3),
    }


if __name__ == "__main__":
    print(f"XAG_USD SmaScalping — Exit Mode Comparison (RR cap={TARGET_RR})")
    print(f"Filters: DI>{DI_THRESHOLD}  persist={DI_PERSIST}  atr_ratio={ATR_RATIO}  "
          f"di_slope=True  avoid_hours={sorted(AVOID_HOURS)}")
    print("=" * 80)

    df = load_and_prep()
    period = f"{df.index[0].date()} → {df.index[-1].date()}"
    print(f"Data: {SYMBOL} 5m  {period}  ({len(df):,} rows)\n")

    modes = [
        ("fixed", "Fixed SL/TP (RR=12)  [current]"),
        ("sma20", "SMA20 trailing exit              "),
        ("sma50", "SMA50 trailing exit              "),
    ]

    print(f"  {'Mode':<36} {'Trades':>6}  {'WR%':>6}  {'ROI%':>8}  {'Sharpe':>7}  "
          f"{'MaxDD%':>8}  {'Avg-R':>7}")
    print("  " + "-" * 75)

    rows = []
    for mode_key, mode_label in modes:
        r = run_backtest(df, mode_key)
        if r is None:
            print(f"  {mode_label}  — insufficient trades")
            continue
        print(f"  {mode_label}  n={r['trades']:>3}  wr={r['win_rate']:>5.1f}%  "
              f"roi={r['roi']:>8.2f}%  sharpe={r['sharpe']:>6.2f}  "
              f"dd={r['max_dd']:>7.2f}%  avg_r={r['avg_r']:>+6.3f}")
        rows.append({"symbol": SYMBOL, "timeframe": "5m", "period": period, **r})

    print()

    # Delta vs fixed baseline
    if len(rows) == 3:
        base = rows[0]
        print("  Deltas vs Fixed SL/TP baseline:")
        for r in rows[1:]:
            print(f"    {r['exit_mode'].upper():<6}: "
                  f"ROI {r['roi']-base['roi']:>+.2f}%  "
                  f"Sharpe {r['sharpe']-base['sharpe']:>+.2f}  "
                  f"MaxDD {r['max_dd']-base['max_dd']:>+.2f}%  "
                  f"Trades {r['trades']-base['trades']:>+d}")

    pd.DataFrame(rows).to_csv(OUT_FILE, index=False)
    print(f"\nSaved → {OUT_FILE}")
