"""
SmaScalping 15m — Noise Filter Sweep
======================================
Tests individual and combined noise filters on top of the best base config
for 4 candidate pairs: GBP_JPY, UK100_GBP, EUR_AUD, EUR_USD.

Filters tested:
  - di_slope    : DI+ (BUY) or DI- (SELL) must be rising vs prior candle
  - adx_rising  : ADX must be rising vs prior candle
  - adx_min     : ADX floor (0, 15, 20, 25)
  - atr_ratio   : ATR >= N × 20-bar ATR average (0=off, 1.0, 1.2)
  - avoid_hours : block entry in specific UTC hours (pair-specific candidates)

Base configs (best from sweep):
  GBP_JPY   DI>25  RR=4.0  p=2  spread=0.04
  UK100_GBP DI>35  RR=6.0  p=2  spread=0.80
  EUR_AUD   DI>30  RR=5.0  p=1  spread=0.0002
  EUR_USD   DI>25  RR=6.0  p=2  spread=0.0001

Output: data/backtest_noise_filter_sweep.csv
"""

import sys
import itertools
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_noise_filter_sweep.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
MIN_TRADES      = 10

# Base configs from 15m sweep
PAIRS = {
    "GBP_JPY": dict(
        di=25.0, rr=4.0, persist=2, spread=0.04,
        avoid_candidates=[
            [],                         # no filter
            [22, 23, 0, 1, 2, 3],       # Asia session (thin GBP liquidity)
            [7, 8],                     # London open (volatile)
            [20, 21, 22, 23],           # Late NY / pre-London thin
            [0, 1, 2, 3, 4, 5],        # Deep Asia / Sydney only
            [19, 20, 21, 22, 23],       # Broader pre-London
        ],
    ),
    "UK100_GBP": dict(
        di=35.0, rr=6.0, persist=2, spread=0.80,
        avoid_candidates=[
            [],
            [20, 21, 22, 23],           # Post-NYSE close / pre-London thin
            [19, 20, 21, 22, 23],       # Broader off-hours
            [7, 8],                     # London open volatility
            [15, 16, 17, 18, 19],       # Post-UK close
            [20, 21, 22, 23, 0, 1, 2],  # Full off-market hours
        ],
    ),
    "EUR_AUD": dict(
        di=30.0, rr=5.0, persist=1, spread=0.0002,
        avoid_candidates=[
            [],
            [22, 23, 0, 1],             # Sydney/Asia open
            [20, 21, 22, 23],           # Pre-London thin hours
            [14, 15, 16],               # London-NY overlap (news)
            [7, 8],                     # London open spike
            [22, 23, 0, 1, 2, 3],       # Full Asia session
        ],
    ),
    "EUR_USD": dict(
        di=25.0, rr=6.0, persist=2, spread=0.0001,
        avoid_candidates=[
            [],
            [20, 21, 22, 23],           # Post-NY / pre-London dead zone
            [14, 15, 16],               # London-NY overlap volatility
            [7, 8],                     # London open
            [19, 20, 21, 22, 23],       # Broader pre-London
            [22, 23, 0, 1, 2, 3],       # Deep off-hours
        ],
    ),
}

ADX_MIN_VALS  = [0.0, 15.0, 20.0, 25.0]
ATR_RATIO_VALS = [0.0, 1.0, 1.2]
DI_SLOPE_VALS  = [False, True]
ADX_RISING_VALS = [False, True]


def load_and_prep(symbol: str) -> pd.DataFrame:
    csv = DATA_DIR / f"{symbol}_15_Min.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df["ATR_avg20"] = df["ATR"].rolling(20).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR", "ATR_avg20"],
              inplace=True)
    return df


def run_backtest(df, rr, di, adx_min, spread, di_persist,
                 di_slope=False, adx_rising=False,
                 atr_ratio=0.0, avoid_hours=None):
    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    sma20    = df["SMA20"].values
    sma50    = df["SMA50"].values
    sma100   = df["SMA100"].values
    di_plus  = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    adx_arr  = df["ADX"].values
    atr_arr  = df["ATR"].values
    atr_ma   = df["ATR_avg20"].values
    times    = df.index
    ah_set   = set(avoid_hours) if avoid_hours else set()

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(max(3, di_persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # --- Exit ---
        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            continue

        # --- Time filter ---
        if ah_set and times[i].hour in ah_set:
            continue

        # --- ADX ---
        adx_val = adx_arr[i]
        if adx_val < adx_min:
            continue
        if adx_rising and i > 0 and adx_val <= adx_arr[i - 1]:
            continue

        # --- ATR ratio ---
        if atr_ratio > 0 and not np.isnan(atr_ma[i]) and atr_ma[i] > 0:
            if atr_arr[i] < atr_ratio * atr_ma[i]:
                continue

        # --- DI persist ---
        di_plus_pers  = all(di_plus[i - j]  > di for j in range(di_persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(di_persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i])

        if not (is_buy or is_sell):
            continue

        # --- DI slope ---
        if di_slope and i > 0:
            if is_buy  and di_plus[i]  <= di_plus[i - 1]:  continue
            if is_sell and di_minus[i] <= di_minus[i - 1]: continue

        # --- Structural validity ---
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # --- ATR floor SL ---
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
    return {"trades": n, "win_rate": round(wr, 1), "roi": round(roi, 2),
            "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


def _close(balance, rr, win):
    pnl = balance * RISK_PCT * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": balance + pnl}


def label_filters(di_slope, adx_rising, adx_min, atr_ratio, avoid_hours):
    parts = []
    if di_slope:    parts.append("di_slope")
    if adx_rising:  parts.append("adx_rising")
    if adx_min > 0: parts.append(f"adx_min={adx_min:.0f}")
    if atr_ratio > 0: parts.append(f"atr_ratio={atr_ratio}")
    if avoid_hours: parts.append(f"avoid={avoid_hours}")
    return ", ".join(parts) if parts else "base (no filters)"


if __name__ == "__main__":
    all_rows = []

    for symbol, cfg in PAIRS.items():
        print(f"\n{'='*80}")
        print(f"  {symbol}  |  DI>{cfg['di']:.0f}  RR={cfg['rr']}  persist={cfg['persist']}")
        print(f"{'='*80}")

        try:
            df = load_and_prep(symbol)
        except Exception as e:
            print(f"  Load error: {e}")
            continue

        period = f"{df.index[0].date()} → {df.index[-1].date()}"
        print(f"  Data: {len(df)} bars  |  {period}\n")

        results = []

        # Sweep: all combinations of single filters + avoid_hours candidates
        for di_slope, adx_rising, adx_min, atr_ratio, avoid_hours in itertools.product(
            DI_SLOPE_VALS,
            ADX_RISING_VALS,
            ADX_MIN_VALS,
            ATR_RATIO_VALS,
            cfg["avoid_candidates"],
        ):
            r = run_backtest(
                df,
                rr=cfg["rr"], di=cfg["di"], adx_min=adx_min,
                spread=cfg["spread"], di_persist=cfg["persist"],
                di_slope=di_slope, adx_rising=adx_rising,
                atr_ratio=atr_ratio, avoid_hours=avoid_hours,
            )
            if r is None:
                continue
            lbl = label_filters(di_slope, adx_rising, adx_min, atr_ratio, avoid_hours)
            results.append({
                "symbol": symbol, "filters": lbl,
                "di_slope": di_slope, "adx_rising": adx_rising,
                "adx_min": adx_min, "atr_ratio": atr_ratio,
                "avoid_hours": str(avoid_hours) if avoid_hours else "",
                **r
            })

        if not results:
            print("  No configs with sufficient trades.")
            continue

        results.sort(key=lambda x: x["sharpe"], reverse=True)
        baseline = next((r for r in results if r["filters"] == "base (no filters)"), None)

        print(f"  {'Filters':<55} {'n':>4} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
        print("  " + "-" * 92)

        # Show baseline first, then top 15 by Sharpe
        shown = set()
        display = []
        if baseline:
            display.append(("BASE", baseline))
            shown.add(baseline["filters"])

        for r in results[:20]:
            if r["filters"] not in shown:
                display.append(("", r))
                shown.add(r["filters"])
            if len(display) >= 16:
                break

        for tag, r in display:
            tag_str = f"[{tag}] " if tag else "       "
            print(f"  {tag_str}{r['filters']:<50} n={r['trades']:>3}  "
                  f"wr={r['win_rate']:>5.1f}%  roi={r['roi']:>7.2f}%  "
                  f"sharpe={r['sharpe']:>5.2f}  dd={r['max_dd']:>7.2f}%")

        best = results[0]
        if baseline:
            sharpe_gain = round(best["sharpe"] - baseline["sharpe"], 2)
            roi_gain    = round(best["roi"]    - baseline["roi"],    2)
            dd_delta    = round(best["max_dd"] - baseline["max_dd"], 2)
            print(f"\n  Best vs Baseline:")
            print(f"    Sharpe: {baseline['sharpe']:.2f} → {best['sharpe']:.2f}  ({'+' if sharpe_gain>0 else ''}{sharpe_gain})")
            print(f"    ROI:    {baseline['roi']:.2f}% → {best['roi']:.2f}%  ({'+' if roi_gain>0 else ''}{roi_gain}%)")
            print(f"    MaxDD:  {baseline['max_dd']:.2f}% → {best['max_dd']:.2f}%  ({'+' if dd_delta>0 else ''}{dd_delta}%)")
            print(f"    Filters: {best['filters']}")

        all_rows.extend(results[:20])

    # Save top results per pair
    df_out = pd.DataFrame(all_rows)
    df_out.to_csv(OUT_FILE, index=False)
    print(f"\n\nSaved → {OUT_FILE}")

    # Final summary table
    print("\n" + "="*80)
    print("SUMMARY — Best config per pair (noise-filtered)")
    print("="*80)
    print(f"  {'Symbol':<14} {'Base Sharpe':>11} {'Best Sharpe':>11} {'Gain':>6} {'ROI%':>8} {'MaxDD%':>8}  Filters")
    print("  " + "-"*90)

    base_sharpes = {
        "GBP_JPY":   4.69,
        "UK100_GBP": 4.62,
        "EUR_AUD":   3.02,
        "EUR_USD":   3.18,
    }

    for symbol in PAIRS:
        subset = [r for r in all_rows if r["symbol"] == symbol]
        if not subset:
            continue
        best = max(subset, key=lambda x: x["sharpe"])
        base_s = base_sharpes.get(symbol, 0)
        gain = round(best["sharpe"] - base_s, 2)
        print(f"  {symbol:<14} {base_s:>11.2f} {best['sharpe']:>11.2f} {'+' if gain>=0 else ''}{gain:>5.2f} "
              f"{best['roi']:>7.2f}% {best['max_dd']:>7.2f}%  {best['filters']}")
