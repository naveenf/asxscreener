"""
USD_JPY — 5m (production) vs 15m SmaScalping trade-level comparison.

Uses existing forex_raw CSVs — no download.

Production 5m config (source of truth from best_strategies.json):
  DI>30, RR=2.5, persist=1, adx_min=15, di_spread_min=15,
  avoid_hours=[15,16,17,18,19,20,21]

15m config: same filters, sweep over RR and DI to find best.
Constraints (CLAUDE.md):
  - di_persist locked to 1  (persist=2: Sharpe 1.69→0.89)
  - no di_slope              (harmful: -1.02 Sharpe)
  - di_threshold ≤ 30       (DI spread too tight above 30)
  - adx_min ≤ 15            (sweet spot; 20+ over-filters)
"""

import os, sys
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import product

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators

# ── constants ─────────────────────────────────────────────────────────────────
SYMBOL      = "USD_JPY"
SPREAD      = 0.009
INITIAL_BAL = 10_000.0
RISK_PCT    = 0.01
DATA_DIR    = PROJECT_ROOT / "data" / "forex_raw"
OUT_TRADES  = PROJECT_ROOT / "data" / "backtest_usdjpy_trades.csv"
OUT_SWEEP   = PROJECT_ROOT / "data" / "backtest_usdjpy_15m_vs_5m.csv"

TF_SUFFIX = {"5m": "5_Min", "15m": "15_Min"}

# ── former 5m config (archived Apr 2, 2026 — replaced by 15m) ────────────────
# Sharpe 1.37, MaxDD -18.63%, Avg-R 0.18 on 5m
PROD_5M = dict(
    di_threshold  = 30.0,
    rr            = 2.5,
    di_persist    = 1,
    adx_min       = 15.0,
    di_spread_min = 15.0,
    avoid_hours   = [15, 16, 17, 18, 19, 20, 21],
)

# ── production 15m config (live from Apr 2, 2026) ────────────────────────────
# Sharpe 2.85, MaxDD -8.65%, Avg-R 0.45 on 15m
PROD_15M = dict(
    di_threshold  = 30.0,
    rr            = 3.0,
    di_persist    = 1,
    adx_min       = 0.0,
    di_spread_min = 0.0,
    avoid_hours   = [15, 16, 17, 18, 19, 20, 21],
)

# ── 15m sweep grid (USD_JPY-safe) ─────────────────────────────────────────────
DI_THRESHOLDS  = [20.0, 25.0, 30.0]
RR_RATIOS      = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
ADX_MIN_VALS   = [0.0, 15.0]
DI_SPREAD_VALS = [0.0, 10.0, 15.0]
AVOID_OPTS     = [
    [],
    [15, 16, 17, 18, 19, 20, 21],
    [20, 21, 22, 23],
]


# ── data loading ──────────────────────────────────────────────────────────────

def load_and_prep(tf_label):
    csv = DATA_DIR / f"{SYMBOL}_{TF_SUFFIX[tf_label]}.csv"
    df  = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20","SMA50","SMA100","DIPlus","DIMinus","ADX","ATR"],
              inplace=True)
    return df


# ── backtest engine ───────────────────────────────────────────────────────────

def run_backtest(df, rr, di_threshold, di_persist,
                 adx_min=0.0, di_spread_min=0.0, avoid_hours=None,
                 record_trades=False):
    if avoid_hours is None:
        avoid_hours = []

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
    idx      = df.index
    hours    = idx.hour

    balance  = INITIAL_BAL
    trades   = []
    in_trade = False
    sl = tp = direction = entry_time = entry_price = None

    for i in range(max(3, di_persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    win = False
                elif h >= tp:
                    win = True
                else:
                    continue
            else:
                if h >= sl:
                    win = False
                elif l <= tp:
                    win = True
                else:
                    continue

            pnl     = balance * RISK_PCT * (rr if win else -1.0)
            balance += pnl
            trade_rec = {
                "entry_time":  entry_time,
                "exit_time":   idx[i],
                "direction":   direction,
                "entry_price": round(entry_price, 5),
                "sl":          round(sl, 5),
                "tp":          round(tp, 5),
                "result":      "WIN" if win else "LOSS",
                "pnl":         round(pnl, 2),
                "balance":     round(balance, 2),
            }
            trades.append(trade_rec)
            in_trade = False
            continue

        if avoid_hours and hours[i] in avoid_hours:
            continue
        if adx_min > 0 and adx_arr[i] < adx_min:
            continue

        di_plus_pers  = all(di_plus[i - j]  > di_threshold for j in range(di_persist))
        di_minus_pers = all(di_minus[i - j] > di_threshold for j in range(di_persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i])

        if not (is_buy or is_sell):
            continue

        if di_spread_min > 0 and abs(di_plus[i] - di_minus[i]) < di_spread_min:
            continue

        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        atr_val = atr_arr[i]
        if is_buy:
            stop_dist = max(c - prev_low, atr_val)
            sl_p      = c - stop_dist - SPREAD
            risk      = c - sl_p
            if risk <= 0: continue
            direction, sl, tp = "BUY",  sl_p, c + risk * rr
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_p      = c + stop_dist + SPREAD
            risk      = sl_p - c
            if risk <= 0: continue
            direction, sl, tp = "SELL", sl_p, c - risk * rr

        entry_time  = idx[i]
        entry_price = c
        in_trade    = True

    if len(trades) < 5:
        return None, []

    df_t   = pd.DataFrame(trades)
    n      = len(df_t)
    wins   = (df_t["result"] == "WIN").sum()
    wr     = wins / n * 100
    roi    = df_t["pnl"].sum() / INITIAL_BAL * 100
    rets   = df_t["pnl"] / INITIAL_BAL
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    equity = df_t["balance"].values
    peak   = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak * 100).min())
    avg_r  = float((df_t["pnl"] / (INITIAL_BAL * RISK_PCT)).mean())

    stats = {
        "trades": n, "wins": int(wins), "win_rate": round(wr, 1),
        "roi": round(roi, 2), "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2), "avg_r": round(avg_r, 2),
    }
    return stats, trades if record_trades else []


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"USD_JPY — 5m vs 15m SmaScalping")
    print("=" * 80)

    df5  = load_and_prep("5m")
    df15 = load_and_prep("15m")
    p5   = f"{df5.index[0].date()} → {df5.index[-1].date()}"
    p15  = f"{df15.index[0].date()} → {df15.index[-1].date()}"
    print(f"  5m  data: {p5}  ({len(df5)} bars)")
    print(f"  15m data: {p15}  ({len(df15)} bars)")

    all_trades = []
    sweep_rows = []

    # ── production 5m ─────────────────────────────────────────────────────────
    print("\n[1] Production 5m config…")
    cfg = PROD_5M
    stats5, trades5 = run_backtest(
        df5, record_trades=True,
        rr=cfg["rr"], di_threshold=cfg["di_threshold"],
        di_persist=cfg["di_persist"], adx_min=cfg["adx_min"],
        di_spread_min=cfg["di_spread_min"], avoid_hours=cfg["avoid_hours"],
    )
    if stats5:
        for t in trades5:
            t.update({"config": "5m_production", "timeframe": "5m",
                       "rr": cfg["rr"], "di_threshold": cfg["di_threshold"]})
        all_trades.extend(trades5)
        sweep_rows.append({"config": "5m_PRODUCTION", "timeframe": "5m",
                            "di_threshold": cfg["di_threshold"], "rr": cfg["rr"],
                            "adx_min": cfg["adx_min"],
                            "di_spread_min": cfg["di_spread_min"],
                            "avoid_hours": str(cfg["avoid_hours"]),
                            "period": p5, **stats5})
        print(f"  OK — {stats5['trades']} trades")
    else:
        print("  No results.")

    # ── 15m sweep ─────────────────────────────────────────────────────────────
    print("\n[2] 15m sweep…")
    total_combos = (len(DI_THRESHOLDS) * len(RR_RATIOS) *
                    len(ADX_MIN_VALS) * len(DI_SPREAD_VALS) * len(AVOID_OPTS))
    done = 0
    for di, rr, adx_min, di_spread_min, avoid_hours in product(
            DI_THRESHOLDS, RR_RATIOS, ADX_MIN_VALS, DI_SPREAD_VALS, AVOID_OPTS):
        done += 1
        stats, _ = run_backtest(
            df15, rr=rr, di_threshold=di, di_persist=1,
            adx_min=adx_min, di_spread_min=di_spread_min,
            avoid_hours=avoid_hours, record_trades=False,
        )
        if stats is None:
            continue
        sweep_rows.append({
            "config": "15m_sweep", "timeframe": "15m",
            "di_threshold": di, "rr": rr, "adx_min": adx_min,
            "di_spread_min": di_spread_min,
            "avoid_hours": str(avoid_hours),
            "period": p15, **stats,
        })

    print(f"  {done} combos tested, {len(sweep_rows) - (1 if stats5 else 0)} 15m results")

    # ── find best 15m config and record its trades ─────────────────────────────
    df_sweep = pd.DataFrame(sweep_rows)
    eligible = df_sweep[(df_sweep["timeframe"] == "15m") &
                        (df_sweep["trades"] >= 15) &
                        (df_sweep["roi"] > 0)]

    best15_stats = None
    best15_cfg   = None
    if not eligible.empty:
        best_row = eligible.loc[eligible["sharpe"].idxmax()]
        best15_cfg = {
            "di_threshold":  best_row["di_threshold"],
            "rr":            best_row["rr"],
            "di_persist":    1,
            "adx_min":       best_row["adx_min"],
            "di_spread_min": best_row["di_spread_min"],
            "avoid_hours":   eval(best_row["avoid_hours"]),
        }
        best15_stats, trades15 = run_backtest(
            df15, record_trades=True, **best15_cfg
        )
        for t in trades15:
            t.update({"config": "15m_best", "timeframe": "15m",
                       "rr": best15_cfg["rr"],
                       "di_threshold": best15_cfg["di_threshold"]})
        all_trades.extend(trades15)

    # ── save CSVs ─────────────────────────────────────────────────────────────
    pd.DataFrame(all_trades).to_csv(OUT_TRADES, index=False)
    df_sweep.to_csv(OUT_SWEEP, index=False)
    print(f"\nTrades CSV   → {OUT_TRADES}")
    print(f"Sweep CSV    → {OUT_SWEEP}")

    # ── comparison table ──────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)

    col_w = [22, 8, 8, 8, 8, 8, 8, 8]
    headers = ["Config", "Trades", "WR%", "ROI%", "Sharpe", "MaxDD%", "Avg-R", "RR"]
    row_fmt = "  {:<22} {:>8} {:>8} {:>8} {:>8} {:>8} {:>8} {:>8}"
    sep     = "  " + "-" * (sum(col_w) + len(col_w) * 1)

    print(row_fmt.format(*headers))
    print(sep)

    def fmt_row(label, s, rr):
        return row_fmt.format(
            label,
            s["trades"],
            f"{s['win_rate']}%",
            f"{s['roi']}%",
            s["sharpe"],
            f"{s['max_dd']}%",
            s["avg_r"],
            rr,
        )

    if stats5:
        print(fmt_row("5m  production", stats5, PROD_5M["rr"]))

    if not eligible.empty:
        print(sep)
        top5 = eligible.nlargest(5, "sharpe")
        for _, row in top5.iterrows():
            label = (f"15m DI>{row['di_threshold']:.0f} "
                     f"adx≥{row['adx_min']:.0f} "
                     f"sprd≥{row['di_spread_min']:.0f}")
            s = {k: row[k] for k in
                 ["trades","win_rate","roi","sharpe","max_dd","avg_r"]}
            print(fmt_row(label, s, row["rr"]))

    print(sep)

    # 15m baseline: same filters as 5m production
    same_filters = df_sweep[
        (df_sweep["timeframe"] == "15m") &
        (df_sweep["di_threshold"] == PROD_5M["di_threshold"]) &
        (df_sweep["rr"] == PROD_5M["rr"]) &
        (df_sweep["adx_min"] == PROD_5M["adx_min"]) &
        (df_sweep["di_spread_min"] == PROD_5M["di_spread_min"]) &
        (df_sweep["avoid_hours"] == str(PROD_5M["avoid_hours"]))
    ]
    if not same_filters.empty:
        row = same_filters.iloc[0]
        s   = {k: row[k] for k in
               ["trades","win_rate","roi","sharpe","max_dd","avg_r"]}
        print(fmt_row("15m same filters as 5m", s, row["rr"]))

    print()

    # ── filter breakdown ───────────────────────────────────────────────────────
    print("15m sweep summary:")
    all15 = df_sweep[df_sweep["timeframe"] == "15m"]
    pos15 = all15[all15["roi"] > 0]
    print(f"  {len(pos15)}/{len(all15)} configs profitable  "
          f"| best Sharpe={all15['sharpe'].max():.2f}  "
          f"best ROI={all15['roi'].max():.2f}%")

    if best15_cfg:
        print(f"\nBest 15m config (Sharpe {best15_stats['sharpe']:.2f}):")
        print(f"  DI>{best15_cfg['di_threshold']:.0f}  RR={best15_cfg['rr']:.1f}  "
              f"adx_min={best15_cfg['adx_min']:.0f}  "
              f"di_spread_min={best15_cfg['di_spread_min']:.0f}  "
              f"avoid_hours={best15_cfg['avoid_hours']}")


if __name__ == "__main__":
    main()
