"""
NAS100_USD SmaScalping 15m — full investigation + filter sweep
Output: data/backtest_nas100_investigation.csv
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from itertools import product
from backend.app.services.indicators import TechnicalIndicators

# ── constants ────────────────────────────────────────────────────────────────
DATA_DIR        = Path("data/forex_raw")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
MIN_TRADES      = 10
SPREAD          = 2.0   # NAS100 index spread in points

# ── load & prep ──────────────────────────────────────────────────────────────
def load_and_prep(symbol="NAS100_USD", tf_str="15_Min"):
    csv = DATA_DIR / f"{symbol}_{tf_str}.csv"
    df  = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20,"SMA20"),(50,"SMA50"),(100,"SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(
        subset=["SMA20","SMA50","SMA100","DIPlus","DIMinus","ADX","ATR"],
        inplace=True
    )
    return df

# ── core backtest ─────────────────────────────────────────────────────────────
def run_backtest(df, rr, di, persist, spread,
                 adx_min=0.0, adx_rising=False, avoid_hours=None,
                 atr_ratio=0.0, di_slope=False, di_spread=0.0):
    if avoid_hours is None:
        avoid_hours = set()

    closes  = df["Close"].values;  highs = df["High"].values;  lows = df["Low"].values
    sma20   = df["SMA20"].values;  sma50 = df["SMA50"].values; sma100 = df["SMA100"].values
    di_plus = df["DIPlus"].values; di_minus = df["DIMinus"].values
    adx_arr = df["ADX"].values;    atr_arr  = df["ATR"].values

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
                if l <= sl:
                    trades.append(_close(balance, rr, False, df.index[i]))
                    balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp:
                    trades.append(_close(balance, rr, True, df.index[i]))
                    balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:
                    trades.append(_close(balance, rr, False, df.index[i]))
                    balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp:
                    trades.append(_close(balance, rr, True, df.index[i]))
                    balance = trades[-1]["balance"]; in_trade = False
            continue

        # Time filter
        if avoid_hours and df.index[i].hour in avoid_hours:
            continue

        # DI persistence
        di_plus_pers  = all(di_plus[i-j]  > di for j in range(persist))
        di_minus_pers = all(di_minus[i-j] > di for j in range(persist))

        # ADX filter
        adx_ok = adx_arr[i] >= adx_min
        if adx_rising:
            adx_ok = adx_ok and (adx_arr[i] > adx_arr[i-1])

        # ATR ratio filter
        atr_ok = (atr_arr[i] >= atr_ratio * atr_avg20[i]) if (atr_ratio > 0 and atr_avg20[i] > 0) else True

        # DI slope — compare to 2 bars back to match sma_scalping_detector.py (iloc[-1] > iloc[-3])
        di_slope_buy  = (di_plus[i]  > di_plus[i-2])  if di_slope else True
        di_slope_sell = (di_minus[i] > di_minus[i-2]) if di_slope else True

        # DI spread
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
        prev_low  = min(lows[i-2],  lows[i-1])
        prev_high = max(highs[i-2], highs[i-1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # SL/TP with ATR floor
        atr_val = atr_arr[i]
        if is_buy:
            stop_dist = max(c - prev_low, atr_val)
            sl_p = c - stop_dist - spread
            risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY"; sl = sl_p; tp = c + risk * rr
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_p = c + stop_dist + spread
            risk = sl_p - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_p; tp = c - risk * rr
        in_trade = True

    return trades


def _close(balance, rr, win, ts):
    pnl = balance * RISK_PCT * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl,
            "balance": balance + pnl, "ts": ts}


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
    avg_r  = (df_t["pnl"] / INITIAL_BALANCE / RISK_PCT).mean()
    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2),
            "max_dd": round(max_dd, 2), "avg_r": round(avg_r, 3)}


def monthly_breakdown(trades):
    if not trades:
        return {}
    df_t = pd.DataFrame(trades)
    df_t["month"] = df_t["ts"].dt.to_period("M").astype(str)
    out = {}
    for m, grp in df_t.groupby("month"):
        n    = len(grp)
        wins = (grp["result"] == "WIN").sum()
        roi  = grp["pnl"].sum() / INITIAL_BALANCE * 100
        out[m] = {"n": n, "wr": round(wins/n*100, 1), "roi": round(roi, 2)}
    return out


# ── production config ─────────────────────────────────────────────────────────
PROD = dict(
    rr=3.5, di=35, persist=2, spread=SPREAD,
    adx_min=30.0, adx_rising=False,
    avoid_hours={7, 8, 20, 21, 22, 23},
    atr_ratio=1.2, di_slope=True, di_spread=0.0
)

# ── avoid_hours candidates ────────────────────────────────────────────────────
AVOID_SETS = {
    "none":             set(),
    "current":          {7, 8, 21, 22, 23},
    "plus20":           {7, 8, 20, 21, 22, 23},
    "plus9":            {7, 8, 9, 21, 22, 23},
    "deep_prelondon":   {21, 22, 23, 0, 1, 2},
    "plus6":            {6, 7, 8, 21, 22, 23},
    "eu_open":          {13, 14, 21, 22, 23},
    "long_london":      {7, 8, 9, 10, 21, 22, 23},
}

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    print("Loading NAS100_USD 15m data...")
    df = load_and_prep()
    print(f"  Bars after warmup: {len(df)}")
    print(f"  Date range: {df.index[0]} → {df.index[-1]}")
    print()

    # ── Step 1: baseline ──────────────────────────────────────────────────────
    print("=" * 70)
    print("STEP 1 — BASELINE (production config)")
    print("=" * 70)
    prod_trades = run_backtest(df, **PROD)
    m = _metrics(prod_trades)
    print(f"  Trades: {m['trades']}  |  WR: {m['win_rate']}%  |  ROI: {m['roi']:+.2f}%  |  "
          f"Sharpe: {m['sharpe']}  |  MaxDD: {m['max_dd']}%  |  Avg-R: {m['avg_r']}")
    print()

    # ── Step 2: monthly breakdown ─────────────────────────────────────────────
    print("=" * 70)
    print("STEP 2 — MONTHLY BREAKDOWN (production config)")
    print("=" * 70)
    mb = monthly_breakdown(prod_trades)
    print(f"  {'Month':<12} {'Trades':>7} {'WR%':>7} {'ROI%':>8}")
    print(f"  {'-'*38}")
    for month, stats in sorted(mb.items()):
        print(f"  {month:<12} {stats['n']:>7} {stats['wr']:>6.1f}% {stats['roi']:>+7.2f}%")
    print()

    # ── Step 3: full filter sweep ─────────────────────────────────────────────
    print("=" * 70)
    print("STEP 3 — FILTER SWEEP")
    print("=" * 70)

    rr_vals      = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    di_vals      = [25, 30, 35]
    persist_vals = [1, 2, 3]
    adx_vals     = [0, 20, 25, 30]
    di_slope_v   = [True, False]
    adx_rising_v = [False, True]
    atr_ratio_v  = [0.0, 0.8, 1.0, 1.2, 1.5]

    rows = []
    total = (len(rr_vals) * len(di_vals) * len(persist_vals) *
             len(adx_vals) * len(di_slope_v) * len(adx_rising_v) *
             len(atr_ratio_v) * len(AVOID_SETS))
    print(f"  Total combinations: {total:,}")

    done = 0
    for (rr, di, persist, adx_min, di_slope, adx_rising,
         atr_ratio, (av_name, av_set)) in product(
            rr_vals, di_vals, persist_vals, adx_vals,
            di_slope_v, adx_rising_v, atr_ratio_v,
            AVOID_SETS.items()):

        done += 1
        if done % 2000 == 0:
            print(f"  ... {done:,}/{total:,} done", flush=True)

        t = run_backtest(df, rr=rr, di=di, persist=persist,
                         spread=SPREAD, adx_min=adx_min,
                         adx_rising=adx_rising, avoid_hours=av_set,
                         atr_ratio=atr_ratio, di_slope=di_slope)
        m2 = _metrics(t)
        if m2 is None:
            continue

        row = {
            "rr": rr, "di": di, "persist": persist,
            "adx_min": adx_min, "adx_rising": adx_rising,
            "atr_ratio": atr_ratio, "di_slope": di_slope,
            "avoid_hours": av_name,
            **m2
        }
        rows.append(row)

    print(f"  Completed {done:,} combinations, {len(rows)} passed MIN_TRADES filter")
    print()

    sweep_df = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    out_path = Path("data/backtest_nas100_investigation.csv")
    sweep_df.to_csv(out_path, index=False)
    print(f"  Saved to {out_path.resolve()}")
    print()

    # ── Step 4: top-3 validation + monthly ────────────────────────────────────
    print("=" * 70)
    print("STEP 4 — TOP-3 CONFIG VALIDATION")
    print("=" * 70)

    # pick top-3 that are meaningfully different (differ on at least 2 dimensions)
    top_candidates = sweep_df.head(30)
    selected = []
    for _, row in top_candidates.iterrows():
        if len(selected) >= 3:
            break
        is_dup = False
        for prev in selected:
            diffs = sum([
                row["rr"]        != prev["rr"],
                row["di"]        != prev["di"],
                row["persist"]   != prev["persist"],
                row["adx_min"]   != prev["adx_min"],
                row["atr_ratio"] != prev["atr_ratio"],
                row["di_slope"]  != prev["di_slope"],
                row["adx_rising"]!= prev["adx_rising"],
                row["avoid_hours"]!= prev["avoid_hours"],
            ])
            if diffs < 2:
                is_dup = True
                break
        if not is_dup:
            selected.append(row)

    top3_results = []
    for rank, row in enumerate(selected, 1):
        av_set  = AVOID_SETS[row["avoid_hours"]]
        t3 = run_backtest(
            df,
            rr         = row["rr"],
            di         = row["di"],
            persist    = int(row["persist"]),
            spread     = SPREAD,
            adx_min    = row["adx_min"],
            adx_rising = bool(row["adx_rising"]),
            avoid_hours= av_set,
            atr_ratio  = row["atr_ratio"],
            di_slope   = bool(row["di_slope"]),
        )
        m3   = _metrics(t3)
        mb3  = monthly_breakdown(t3)
        top3_results.append((rank, row, m3, mb3))

        print(f"  Top-{rank}: RR={row['rr']} DI>{row['di']} p={row['persist']} "
              f"adx_min={row['adx_min']} adx_rising={row['adx_rising']} "
              f"atr_ratio={row['atr_ratio']} di_slope={row['di_slope']} "
              f"avoid={row['avoid_hours']}")
        print(f"    Trades={m3['trades']}  WR={m3['win_rate']}%  "
              f"ROI={m3['roi']:+.2f}%  Sharpe={m3['sharpe']}  "
              f"MaxDD={m3['max_dd']}%  Avg-R={m3['avg_r']}")
        print(f"    Monthly:")
        for month, s in sorted(mb3.items()):
            print(f"      {month}: n={s['n']} WR={s['wr']}% ROI={s['roi']:+.2f}%")
        print()

    # ── Step 5: summary ───────────────────────────────────────────────────────
    print("=" * 70)
    print("STEP 5 — SUMMARY TABLE")
    print("=" * 70)

    # production metrics
    pm = _metrics(prod_trades)
    pm_mb = monthly_breakdown(prod_trades)

    header = (f"  {'Config':<40} {'Trades':>7} {'WR%':>6} {'ROI%':>8} "
              f"{'Sharpe':>7} {'MaxDD%':>8} {'Avg-R':>6}")
    sep    = "  " + "-" * 95
    print(header)
    print(sep)

    def fmt_row(label, m):
        return (f"  {label:<40} {m['trades']:>7} {m['win_rate']:>5.1f}% "
                f"{m['roi']:>+7.2f}% {m['sharpe']:>7.2f} "
                f"{m['max_dd']:>7.2f}% {m['avg_r']:>6.3f}")

    print(fmt_row("PROD (current)", pm))
    for rank, row, m3, mb3 in top3_results:
        label = (f"Top-{rank} RR={row['rr']} DI>{row['di']} "
                 f"p={int(row['persist'])} adx={row['adx_min']}")
        print(fmt_row(label, m3))

    print(sep)
    print()

    # monthly comparison
    all_months = sorted(set(list(pm_mb.keys()) +
                            [m for _, _, _, mb3 in top3_results for m in mb3]))
    print(f"  Monthly ROI% comparison:")
    col_labels = ["PROD"] + [f"Top-{r}" for r, _, _, _ in top3_results]
    hdr2 = f"  {'Month':<10}" + "".join(f"{c:>10}" for c in col_labels)
    print(hdr2)
    print("  " + "-" * (10 + 10*len(col_labels)))
    for m in all_months:
        prod_roi = f"{pm_mb.get(m, {}).get('roi', 0):+.2f}%" if m in pm_mb else "  —"
        row_s = f"  {m:<10}{prod_roi:>10}"
        for _, _, _, mb3 in top3_results:
            v = f"{mb3.get(m, {}).get('roi', 0):+.2f}%" if m in mb3 else "  —"
            row_s += f"{v:>10}"
        print(row_s)
    print()

    # findings
    print("  FINDINGS:")
    dom_month = max(pm_mb, key=lambda x: abs(pm_mb[x]['roi'])) if pm_mb else "N/A"
    dom_roi   = pm_mb.get(dom_month, {}).get("roi", 0)
    total_roi = pm["roi"]
    if total_roi != 0 and abs(dom_roi) > abs(total_roi) * 0.5:
        print(f"  ⚠ {dom_month} dominates prod ROI: {dom_roi:+.2f}% vs total {total_roi:+.2f}%")
        print(f"    Overfit risk: strategy may be shaped by a single month's regime.")
    else:
        print(f"  Distribution looks spread across months — low overfit risk.")

    # best sweep config recommendation
    best = sweep_df.iloc[0]
    print()
    print(f"  RECOMMENDATION:")
    print(f"    Best sweep config → RR={best['rr']}, DI>{best['di']}, persist={int(best['persist'])},")
    print(f"    adx_min={best['adx_min']}, adx_rising={best['adx_rising']},")
    print(f"    atr_ratio={best['atr_ratio']}, di_slope={best['di_slope']},")
    print(f"    avoid_hours={best['avoid_hours']}")
    print(f"    Sharpe={best['sharpe']}  ROI={best['roi']:+.2f}%  "
          f"WR={best['win_rate']}%  MaxDD={best['max_dd']}%")
    print()
    print(f"  Prod Sharpe: {pm['sharpe']}  →  Best sweep Sharpe: {best['sharpe']}")

    print()
    print(f"Full sweep saved to: {out_path.resolve()}")


if __name__ == "__main__":
    main()
