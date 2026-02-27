"""
XAU_USD & XAG_USD — SmaScalping 5m vs 15m comparison.

For each pair:
  1. Baseline 5m results (deployed params)
  2. 15m sweep: DI threshold x R:R x di_persist
  3. Side-by-side delta table

Outputs:
  data/backtest_sma_gold_silver_15m_summary.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import product

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_SUMMARY     = Path("data/backtest_sma_gold_silver_15m_summary.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

PAIRS = {
    "XAU_USD": dict(spread=0.50, di5=35.0, rr5=5.0,  persist5=2),
    "XAG_USD": dict(spread=0.03, di5=35.0, rr5=10.0, persist5=1),
}

DI_THRESHOLDS  = [25, 30, 35]
RR_VALUES      = [3.0, 5.0, 7.0, 10.0]
PERSIST_VALUES = [1, 2]


def load_and_prep(symbol: str, tf: str) -> pd.DataFrame:
    """tf: '5_Min' or '15_Min'"""
    csv = DATA_DIR / f"{symbol}_{tf}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def run_backtest(df, rr, di, di_persist, spread, adx_min=0.0):
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

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(max(3, di_persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        if in_trade:
            result = None
            if direction == "BUY":
                if l <= sl:   result = "LOSS"
                elif h >= tp: result = "WIN"
            else:
                if h >= sl:   result = "LOSS"
                elif l <= tp: result = "WIN"
            if result:
                pnl = balance * RISK_PCT * (rr if result == "WIN" else -1)
                balance += pnl
                trades.append({"result": result, "pnl": pnl, "balance": balance})
                in_trade = False
            continue

        di_plus_pers  = all(di_plus[i - j]  > di for j in range(di_persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(di_persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i] and adx_arr[i] >= adx_min)
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i] and adx_arr[i] >= adx_min)

        if not (is_buy or is_sell):
            continue

        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

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

    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


def print_comparison(label_a, s_a, label_b, s_b):
    print(f"\n  {'Metric':<16} {label_a:>12} {label_b:>12} {'Delta':>10}")
    print(f"  {'-'*52}")
    for k, label, better in [
        ("trades",   "Trades",    None),
        ("win_rate", "Win Rate%", "higher"),
        ("roi",      "ROI%",      "higher"),
        ("sharpe",   "Sharpe",    "higher"),
        ("max_dd",   "MaxDD%",    "higher"),
    ]:
        v_a, v_b = s_a[k], s_b[k]
        delta = v_b - v_a
        sign  = "+" if delta >= 0 else ""
        flag  = ""
        if better == "higher" and delta > 0:  flag = " ✓"
        if better == "higher" and delta < 0:  flag = " ✗"
        if k == "max_dd":
            flag = " ✓" if delta > 0 else " ✗"
        print(f"  {label:<16} {str(v_a):>12} {str(v_b):>12} {sign}{delta:>+9.2f}{flag}")


if __name__ == "__main__":
    all_rows = []

    for symbol, p in PAIRS.items():
        spread = p["spread"]

        # ── Load both timeframes ──
        df5  = load_and_prep(symbol, "5_Min")
        df15 = load_and_prep(symbol, "15_Min")

        period5  = f"{df5.index[0].date()}→{df5.index[-1].date()}"
        period15 = f"{df15.index[0].date()}→{df15.index[-1].date()}"

        print(f"\n{'='*72}")
        print(f"  {symbol}")
        print(f"  5m  period : {period5}  ({len(df5):,} rows)")
        print(f"  15m period : {period15}  ({len(df15):,} rows)")
        print(f"{'='*72}")

        # ── Baseline 5m (deployed params) ──
        base5 = run_backtest(df5, rr=p["rr5"], di=p["di5"],
                             di_persist=p["persist5"], spread=spread)
        print(f"\n  ── 5m BASELINE (deployed: DI>{p['di5']}  RR={p['rr5']}  persist={p['persist5']}) ──")
        if base5:
            print(f"  n={base5['trades']}  wr={base5['win_rate']}%  roi={base5['roi']:+.2f}%  "
                  f"sharpe={base5['sharpe']:.2f}  dd={base5['max_dd']:.2f}%")
        else:
            print("  insufficient trades")

        # ── 15m sweep ──
        print(f"\n  ── 15m SWEEP ──")
        print(f"  {'DI':>3} {'RR':>5} {'Pers':>5} │ {'Trades':>6} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
        print("  " + "─" * 57)

        best15 = {"sharpe": -999, "params": None, "stats": None}
        prev_di = None

        for di, rr, persist in product(DI_THRESHOLDS, RR_VALUES, PERSIST_VALUES):
            if di != prev_di and prev_di is not None:
                print()
            prev_di = di

            r = run_backtest(df15, rr=rr, di=di, di_persist=persist, spread=spread)
            if r is None:
                print(f"  DI>{di:2d}  RR={rr:4.1f}  p={persist} │ insufficient trades")
                continue

            marker = " ◄ best" if r["sharpe"] > best15["sharpe"] else ""
            print(f"  DI>{di:2d}  RR={rr:4.1f}  p={persist} │ "
                  f"n={r['trades']:>4}  wr={r['win_rate']:>5.1f}%  "
                  f"roi={r['roi']:>7.2f}%  sharpe={r['sharpe']:>5.2f}  "
                  f"dd={r['max_dd']:>7.2f}%{marker}")

            if r["sharpe"] > best15["sharpe"]:
                best15 = {"sharpe": r["sharpe"], "params": (di, rr, persist), "stats": r}

            all_rows.append({
                "symbol": symbol, "timeframe": "15m",
                "di_threshold": di, "target_rr": rr,
                "di_persist": persist, "spread": spread,
                "period": period15, **r,
            })

        # ── Side-by-side: 5m deployed vs best 15m ──
        if base5 and best15["params"]:
            di15, rr15, p15 = best15["params"]
            s15 = best15["stats"]
            print(f"\n  ── COMPARISON: 5m deployed vs best 15m (DI>{di15} RR={rr15} persist={p15}) ──")
            print_comparison(
                f"5m(RR={p['rr5']})",
                base5,
                f"15m(RR={rr15})",
                s15,
            )

        # Also record 5m baseline
        if base5:
            all_rows.append({
                "symbol": symbol, "timeframe": "5m",
                "di_threshold": p["di5"], "target_rr": p["rr5"],
                "di_persist": p["persist5"], "spread": spread,
                "period": period5, **base5,
            })

    pd.DataFrame(all_rows).to_csv(OUT_SUMMARY, index=False)
    print(f"\n\nSaved → {OUT_SUMMARY}")
