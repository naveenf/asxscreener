"""
SmaScalping — Fixed TP vs SMA20 trailing exit comparison across ALL deployed pairs.

Uses full production params per pair (from best_strategies.json).
Each pair tested in two modes:
  A) Fixed SL/TP only  — trade closes only when hard SL or TP is hit
  B) SMA20 trailing    — hard SL + TP + close below SMA20 exits early (current live behaviour)

Output: data/backtest_sma_all_pairs_exit_mode.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_sma_all_pairs_exit_mode.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

TF_SUFFIX = {"5m": "5_Min", "15m": "15_Min"}

# Full production params — keep in sync with best_strategies.json
PAIRS = {
    "XAU_USD": dict(
        tf="15m", di=35.0, adx_min=0.0, rr=5.0, spread=0.50,
        di_persist=2, adx_rising=True, di_slope=False,
        atr_ratio=0.0, avoid_hours={8, 9},
    ),
    "XAG_USD": dict(
        tf="5m",  di=35.0, adx_min=0.0, rr=12.0, spread=0.03,
        di_persist=1, adx_rising=False, di_slope=True,
        atr_ratio=1.2, avoid_hours={14, 15, 16},
    ),
    "JP225_USD": dict(
        tf="5m",  di=30.0, adx_min=20.0, rr=5.0, spread=17.0,
        di_persist=2, adx_rising=False, di_slope=True,
        atr_ratio=0.0, avoid_hours=set(),
    ),
    "NAS100_USD": dict(
        tf="5m",  di=35.0, adx_min=0.0, rr=4.5, spread=2.30,
        di_persist=1, adx_rising=False, di_slope=True,
        atr_ratio=1.0, avoid_hours={7, 21, 22, 23},
    ),
    "USD_JPY": dict(
        tf="5m",  di=30.0, adx_min=0.0, rr=2.5, spread=0.0002,
        di_persist=1, adx_rising=False, di_slope=False,
        atr_ratio=0.0, avoid_hours={15, 16, 17, 18, 19, 20, 21},
    ),
}


def load_and_prep(symbol: str, tf: str) -> pd.DataFrame:
    csv = DATA_DIR / f"{symbol}_{TF_SUFFIX[tf]}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for period, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(period).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def run_backtest(df: pd.DataFrame, p: dict, exit_mode: str) -> dict | None:
    """
    exit_mode: 'fixed' | 'sma20'
    """
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
    hours    = df.index.hour

    rr           = p["rr"]
    spread       = p["spread"]
    di_thr       = p["di"]
    adx_min      = p["adx_min"]
    di_persist   = p["di_persist"]
    adx_rising   = p["adx_rising"]
    di_slope_on  = p["di_slope"]
    atr_ratio    = p["atr_ratio"]
    avoid_hours  = p["avoid_hours"]

    balance    = INITIAL_BALANCE
    trades     = []
    in_trade   = False
    sl = tp = direction = entry_price = risk_amount = None
    exit_counts = {"SL": 0, "TP": 0, "SMA": 0}

    start = max(22, di_persist + 2)

    for i in range(start, len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # --- Exit ---
        if in_trade:
            exited = False; result = None; r_mult = None

            if direction == "BUY":
                if l <= sl:
                    result = "LOSS"; r_mult = -1.0; exit_counts["SL"] += 1; exited = True
                elif h >= tp:
                    result = "WIN";  r_mult = rr;   exit_counts["TP"] += 1; exited = True
                elif exit_mode == "sma20" and c < sma20[i]:
                    r_mult = (c - entry_price) / risk_amount
                    result = "WIN" if r_mult > 0 else "LOSS"
                    exit_counts["SMA"] += 1; exited = True
            else:
                if h >= sl:
                    result = "LOSS"; r_mult = -1.0; exit_counts["SL"] += 1; exited = True
                elif l <= tp:
                    result = "WIN";  r_mult = rr;   exit_counts["TP"] += 1; exited = True
                elif exit_mode == "sma20" and c > sma20[i]:
                    r_mult = (entry_price - c) / risk_amount
                    result = "WIN" if r_mult > 0 else "LOSS"
                    exit_counts["SMA"] += 1; exited = True

            if exited:
                pnl = balance * RISK_PCT * r_mult
                balance += pnl
                trades.append({"result": result, "pnl": pnl, "balance": balance,
                               "r_mult": round(r_mult, 3)})
                in_trade = False
            continue

        # --- Session filter ---
        if hours[i] in avoid_hours:
            continue

        # --- DI persistence ---
        di_plus_pers  = all(di_plus[i - j]  > di_thr for j in range(di_persist))
        di_minus_pers = all(di_minus[i - j] > di_thr for j in range(di_persist))

        # --- ADX rising ---
        adx_rising_ok = (adx_arr[i] > adx_arr[i - 1]) if adx_rising else True

        # --- DI slope ---
        di_slope_buy  = (di_plus[i]  > di_plus[i - 2])  if di_slope_on else True
        di_slope_sell = (di_minus[i] > di_minus[i - 2]) if di_slope_on else True

        # --- ATR expansion ---
        if atr_ratio > 0.0:
            atr_avg = atr_arr[i - 20:i].mean()
            atr_ok  = (atr_avg > 0) and (atr_arr[i] >= atr_ratio * atr_avg)
        else:
            atr_ok = True

        adx_ok = adx_arr[i] >= adx_min

        is_buy = (
            c > sma20[i] and c > sma50[i] and c > sma100[i]
            and di_plus_pers and di_plus[i] > di_minus[i]
            and adx_ok and adx_rising_ok and di_slope_buy and atr_ok
        )
        is_sell = (
            c < sma20[i] and c < sma50[i] and c < sma100[i]
            and di_minus_pers and di_minus[i] > di_plus[i]
            and adx_ok and adx_rising_ok and di_slope_sell and atr_ok
        )

        if not (is_buy or is_sell):
            continue

        # --- Structural validity ---
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # --- ATR floor SL ---
        atr_val = atr_arr[i]
        if is_buy:
            stop_dist  = max(c - prev_low, atr_val)
            sl_p       = c - stop_dist - spread
            risk       = c - sl_p
            if risk <= 0: continue
            direction  = "BUY";  sl = sl_p;  tp = c + risk * rr
        else:
            stop_dist  = max(prev_high - c, atr_val)
            sl_p       = c + stop_dist + spread
            risk       = sl_p - c
            if risk <= 0: continue
            direction  = "SELL"; sl = sl_p;  tp = c - risk * rr

        entry_price = c; risk_amount = risk; in_trade = True

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
    total  = sum(exit_counts.values())

    return {
        "exit_mode": exit_mode,
        "trades":    n,
        "win_rate":  round(wr, 1),
        "roi":       round(roi, 2),
        "sharpe":    round(sharpe, 2),
        "max_dd":    round(max_dd, 2),
        "avg_r":     round(df_t["r_mult"].mean(), 3),
        "sl_pct":    round(exit_counts["SL"] / total * 100, 1) if total else 0,
        "tp_pct":    round(exit_counts["TP"] / total * 100, 1) if total else 0,
        "sma_pct":   round(exit_counts["SMA"] / total * 100, 1) if total else 0,
    }


if __name__ == "__main__":
    print("SmaScalping — Fixed TP vs SMA20 Trailing Exit (all deployed pairs)")
    print("=" * 90)

    rows = []
    verdicts = {}

    for symbol, p in PAIRS.items():
        csv = DATA_DIR / f"{symbol}_{TF_SUFFIX[p['tf']]}.csv"
        if not csv.exists():
            print(f"\n  {symbol} — data file missing, skipping")
            continue

        df = load_and_prep(symbol, p["tf"])
        period = f"{df.index[0].date()} → {df.index[-1].date()}"

        print(f"\n  {symbol}  {p['tf']}  RR={p['rr']}  {period}")
        print(f"  {'Mode':<18} {'Trades':>6}  {'WR%':>6}  {'ROI%':>8}  {'Sharpe':>7}  "
              f"{'MaxDD%':>8}  {'Avg-R':>7}  {'SL%':>5}  {'TP%':>5}  {'SMA%':>6}")
        print("  " + "-" * 83)

        pair_rows = {}
        for mode in ("fixed", "sma20"):
            r = run_backtest(df, p, mode)
            if r is None:
                print(f"  {mode:<18} — insufficient trades")
                continue
            label = "Fixed SL/TP      " if mode == "fixed" else "SMA20 trailing   "
            print(f"  {label}  n={r['trades']:>3}  wr={r['win_rate']:>5.1f}%  "
                  f"roi={r['roi']:>8.2f}%  sharpe={r['sharpe']:>6.2f}  "
                  f"dd={r['max_dd']:>7.2f}%  avg_r={r['avg_r']:>+6.3f}  "
                  f"sl={r['sl_pct']:>4.0f}%  tp={r['tp_pct']:>4.0f}%  sma={r['sma_pct']:>4.0f}%")
            pair_rows[mode] = r
            rows.append({"symbol": symbol, "timeframe": p["tf"], "rr": p["rr"],
                         "period": period, **r})

        if "fixed" in pair_rows and "sma20" in pair_rows:
            f, s = pair_rows["fixed"], pair_rows["sma20"]
            roi_delta    = s["roi"]    - f["roi"]
            sharpe_delta = s["sharpe"] - f["sharpe"]
            winner = "SMA20" if s["sharpe"] > f["sharpe"] else "Fixed"
            verdicts[symbol] = winner
            print(f"  {'Delta (SMA20 vs Fixed)':<18}  "
                  f"{'':>5}  {'':>6}  "
                  f"roi={roi_delta:>+8.2f}%  sharpe={sharpe_delta:>+6.2f}  "
                  f"{'':>8}  {'':>7}")
            print(f"  → Winner: {winner}")

    print("\n" + "=" * 90)
    print("  SUMMARY — Which exit wins per pair (by Sharpe):")
    for sym, w in verdicts.items():
        marker = "  ← currently overridden to Fixed" if sym == "XAG_USD" else ""
        print(f"    {sym:<14}: {w}{marker}")

    pd.DataFrame(rows).to_csv(OUT_FILE, index=False)
    print(f"\nSaved → {OUT_FILE}")
