"""
BCO_USD 15m — Noise Filter Sweep
=================================
Baseline (current prod): DI>30, RR=4.0, persist=1, adx_min=15
                         no avoid_hours, no atr_ratio, no di_slope, no di_spread

Sweeps:
  1. avoid_hours combos
  2. atr_ratio_min (1.0, 1.2, 1.5)
  3. di_persist (2)
  4. di_slope
  5. di_spread_min (10, 15)
  6. adx_min (20, 25)
  7. RR sweep (3.0, 3.5, 4.5, 5.0) with best filter combo

Output: data/backtest_bco_noise_filter_sweep.csv
"""

import sys
import itertools
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_bco_noise_filter_sweep.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
MIN_TRADES      = 10

SPREAD = 0.04  # BCO_USD Oanda spread

# --- Fixed prod values ---
DI_THRESH = 30.0
BASE_RR   = 4.0
BASE_PERSIST = 1
BASE_ADX_MIN = 15.0


def load_and_prep():
    csv = DATA_DIR / "BCO_USD_15_Min.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def _close(balance, rr, win):
    pnl = balance * RISK_PCT * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": balance + pnl}


def _metrics(trades):
    if len(trades) < MIN_TRADES:
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
    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


def run_backtest(df, rr, di, persist, spread,
                 adx_min=15.0, adx_rising=False, avoid_hours=None,
                 atr_ratio=0.0, di_slope=False, di_spread=0.0):
    if avoid_hours is None:
        avoid_hours = set()

    closes  = df["Close"].values
    highs   = df["High"].values
    lows    = df["Low"].values
    sma20   = df["SMA20"].values
    sma50   = df["SMA50"].values
    sma100  = df["SMA100"].values
    di_plus = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    adx_arr = df["ADX"].values
    atr_arr = df["ATR"].values

    if atr_ratio > 0:
        atr_avg20 = pd.Series(atr_arr).rolling(20).mean().values
    else:
        atr_avg20 = atr_arr

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None
    start = max(3, persist, 21 if atr_ratio > 0 else 3)

    for i in range(start, len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # Exit
        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            continue

        # Time filter
        if avoid_hours and df.index[i].hour in avoid_hours:
            continue

        # Filters
        di_plus_pers  = all(di_plus[i - j]  > di for j in range(persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(persist))

        adx_ok = adx_arr[i] >= adx_min
        if adx_rising:
            adx_ok = adx_ok and (adx_arr[i] > adx_arr[i - 1])

        atr_ok = (atr_arr[i] >= atr_ratio * atr_avg20[i]) if (atr_ratio > 0 and atr_avg20[i] > 0) else True

        di_slope_buy  = (di_plus[i]  > di_plus[i - 1])  if di_slope else True
        di_slope_sell = (di_minus[i] > di_minus[i - 1]) if di_slope else True

        di_sprd_buy  = ((di_plus[i]  - di_minus[i]) >= di_spread) if di_spread > 0 else True
        di_sprd_sell = ((di_minus[i] - di_plus[i])  >= di_spread) if di_spread > 0 else True

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i]
                   and adx_ok and atr_ok and di_slope_buy and di_sprd_buy)
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i]
                   and adx_ok and atr_ok and di_slope_sell and di_sprd_sell)

        if not (is_buy or is_sell):
            continue

        # Structural validity
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # SL/TP with ATR floor
        atr_val = atr_arr[i]
        if is_buy:
            stop_dist = max(c - prev_low, atr_val)
            sl_p = c - stop_dist - spread
            risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * rr
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_p = c + stop_dist + spread
            risk = sl_p - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_p;  tp = c - risk * rr

        in_trade = True

    return _metrics(trades)


if __name__ == "__main__":
    print("Loading BCO_USD 15m data...")
    df = load_and_prep()
    print(f"Data: {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} bars)\n")

    results = []

    def record(label, rr, avoid_hours=None, atr_ratio=0.0, persist=1,
               di_slope=False, di_spread=0.0, adx_min=15.0):
        r = run_backtest(df, rr=rr, di=DI_THRESH, persist=persist, spread=SPREAD,
                         adx_min=adx_min, avoid_hours=avoid_hours or set(),
                         atr_ratio=atr_ratio, di_slope=di_slope, di_spread=di_spread)
        if r is None:
            print(f"  {label:<55} — < {MIN_TRADES} trades, skipped")
            return
        results.append({"filter_combo": label, "rr": rr, **r})
        print(f"  {label:<55} n={r['trades']:>3}  wr={r['win_rate']:>5.1f}%  "
              f"roi={r['roi']:>+8.2f}%  sharpe={r['sharpe']:>5.2f}  dd={r['max_dd']:>7.2f}%")

    # --- Baseline ---
    print("=== BASELINE ===")
    record("Baseline  DI>30 RR=4.0 p=1 adx=15", BASE_RR)

    # --- 1. avoid_hours ---
    print("\n=== avoid_hours ===")
    record("avoid [0-5]  (pre-London dead zone)",         BASE_RR, avoid_hours={0,1,2,3,4,5})
    record("avoid [20-23]  (post-NY)",                    BASE_RR, avoid_hours={20,21,22,23})
    record("avoid [0-5,20-23]  (both dead zones)",        BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23})

    # --- 2. atr_ratio_min ---
    print("\n=== atr_ratio_min ===")
    record("atr_ratio=1.0",                               BASE_RR, atr_ratio=1.0)
    record("atr_ratio=1.2",                               BASE_RR, atr_ratio=1.2)
    record("atr_ratio=1.5",                               BASE_RR, atr_ratio=1.5)

    # --- 3. di_persist=2 ---
    print("\n=== di_persist ===")
    record("persist=2",                                   BASE_RR, persist=2)

    # --- 4. di_slope ---
    print("\n=== di_slope ===")
    record("di_slope=True",                               BASE_RR, di_slope=True)

    # --- 5. di_spread_min ---
    print("\n=== di_spread_min ===")
    record("di_spread=10",                                BASE_RR, di_spread=10.0)
    record("di_spread=15",                                BASE_RR, di_spread=15.0)

    # --- 6. adx_min ---
    print("\n=== adx_min ===")
    record("adx_min=20",                                  BASE_RR, adx_min=20.0)
    record("adx_min=25",                                  BASE_RR, adx_min=25.0)

    # --- 7. Combinations of top single filters (tested iteratively) ---
    print("\n=== combinations ===")
    # avoid + atr_ratio
    record("avoid[0-5]+atr_ratio=1.0",                   BASE_RR, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.0)
    record("avoid[0-5]+atr_ratio=1.2",                   BASE_RR, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.2)
    record("avoid[20-23]+atr_ratio=1.0",                 BASE_RR, avoid_hours={20,21,22,23}, atr_ratio=1.0)
    record("avoid[20-23]+atr_ratio=1.2",                 BASE_RR, avoid_hours={20,21,22,23}, atr_ratio=1.2)
    record("avoid[0-5,20-23]+atr_ratio=1.0",             BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, atr_ratio=1.0)
    record("avoid[0-5,20-23]+atr_ratio=1.2",             BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, atr_ratio=1.2)
    # avoid + persist
    record("avoid[0-5]+persist=2",                       BASE_RR, avoid_hours={0,1,2,3,4,5}, persist=2)
    record("avoid[20-23]+persist=2",                     BASE_RR, avoid_hours={20,21,22,23}, persist=2)
    record("avoid[0-5,20-23]+persist=2",                 BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, persist=2)
    # avoid + di_slope
    record("avoid[0-5]+di_slope",                        BASE_RR, avoid_hours={0,1,2,3,4,5}, di_slope=True)
    record("avoid[20-23]+di_slope",                      BASE_RR, avoid_hours={20,21,22,23}, di_slope=True)
    record("avoid[0-5,20-23]+di_slope",                  BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, di_slope=True)
    # avoid + adx
    record("avoid[0-5]+adx_min=20",                      BASE_RR, avoid_hours={0,1,2,3,4,5}, adx_min=20.0)
    record("avoid[20-23]+adx_min=20",                    BASE_RR, avoid_hours={20,21,22,23}, adx_min=20.0)
    record("avoid[0-5,20-23]+adx_min=20",                BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, adx_min=20.0)
    # avoid + di_spread
    record("avoid[0-5]+di_spread=10",                    BASE_RR, avoid_hours={0,1,2,3,4,5}, di_spread=10.0)
    record("avoid[20-23]+di_spread=10",                  BASE_RR, avoid_hours={20,21,22,23}, di_spread=10.0)
    record("avoid[0-5,20-23]+di_spread=10",              BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, di_spread=10.0)
    # 3-way combos
    record("avoid[0-5]+atr=1.0+persist=2",               BASE_RR, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.0, persist=2)
    record("avoid[0-5,20-23]+atr=1.0+persist=2",         BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, atr_ratio=1.0, persist=2)
    record("avoid[0-5]+atr=1.2+persist=2",               BASE_RR, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.2, persist=2)
    record("avoid[0-5,20-23]+atr=1.2+persist=2",         BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, atr_ratio=1.2, persist=2)
    record("avoid[0-5]+atr=1.0+di_slope",                BASE_RR, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.0, di_slope=True)
    record("avoid[0-5,20-23]+atr=1.0+di_slope",         BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, atr_ratio=1.0, di_slope=True)
    record("avoid[0-5]+di_spread=10+adx_min=20",         BASE_RR, avoid_hours={0,1,2,3,4,5}, di_spread=10.0, adx_min=20.0)
    record("avoid[0-5,20-23]+di_spread=10+adx_min=20",  BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, di_spread=10.0, adx_min=20.0)
    record("avoid[0-5]+persist=2+di_slope",              BASE_RR, avoid_hours={0,1,2,3,4,5}, persist=2, di_slope=True)
    record("avoid[0-5,20-23]+persist=2+di_slope",        BASE_RR, avoid_hours={0,1,2,3,4,5,20,21,22,23}, persist=2, di_slope=True)

    # --- 8. RR sweep with best filter combos ---
    # We'll sweep the top individual and combination filters at different RR values
    print("\n=== RR sweep (baseline only) ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"Baseline RR={rr}",                      rr)

    # Pick the best combo so far and sweep RR on it
    if results:
        best_so_far = max(results, key=lambda x: x["sharpe"])
        best_label  = best_so_far["filter_combo"]
        print(f"\n  >>> Best so far: {best_label}  Sharpe={best_so_far['sharpe']}")

    # We'll also sweep RR on a few promising combos identified during the sweep
    print("\n=== RR sweep on avoid[0-5]+atr=1.0 ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"avoid[0-5]+atr=1.0 RR={rr}",           rr, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.0)

    print("\n=== RR sweep on avoid[0-5]+atr=1.2 ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"avoid[0-5]+atr=1.2 RR={rr}",           rr, avoid_hours={0,1,2,3,4,5}, atr_ratio=1.2)

    print("\n=== RR sweep on avoid[20-23]+atr=1.0 ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"avoid[20-23]+atr=1.0 RR={rr}",         rr, avoid_hours={20,21,22,23}, atr_ratio=1.0)

    print("\n=== RR sweep on avoid[0-5,20-23] ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"avoid[0-5,20-23] RR={rr}",             rr, avoid_hours={0,1,2,3,4,5,20,21,22,23})

    print("\n=== RR sweep on avoid[0-5]+persist=2 ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"avoid[0-5]+persist=2 RR={rr}",         rr, avoid_hours={0,1,2,3,4,5}, persist=2)

    print("\n=== RR sweep on avoid[0-5,20-23]+atr=1.0+persist=2 ===")
    for rr in [3.0, 3.5, 4.5, 5.0]:
        record(f"avoid[0-5,20-23]+atr=1.0+persist=2 RR={rr}", rr,
               avoid_hours={0,1,2,3,4,5,20,21,22,23}, atr_ratio=1.0, persist=2)

    # --- Summary ---
    print("\n\n=== TOP 15 BY SHARPE ===")
    results_sorted = sorted(results, key=lambda x: x["sharpe"], reverse=True)
    print(f"\n{'#':<3} {'Filter Combo':<57} {'RR':>4} {'Trades':>6} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
    print("-" * 105)
    for rank, r in enumerate(results_sorted[:15], 1):
        tag = " <- PROD" if r["filter_combo"].startswith("Baseline  DI>30") else ""
        print(f"  {rank:<2} {r['filter_combo']:<57} {r['rr']:>4.1f} {r['trades']:>6}  "
              f"{r['win_rate']:>5.1f}%  {r['roi']:>+8.2f}%  {r['sharpe']:>5.2f}  {r['max_dd']:>7.2f}%{tag}")

    # Save CSV
    df_out = pd.DataFrame(results_sorted)
    df_out.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(results)} configs → {OUT_FILE}")
