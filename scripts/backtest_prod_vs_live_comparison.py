"""
Production Config Validation + Live Period Comparison
======================================================
1. Full-dataset backtest for all 8 active pairs using exact production configs
2. Same-period backtest (Mar 10 – Apr 10, 2026) for USD_JPY and NAS100_USD
3. Targeted sweep for USD_JPY and NAS100_USD: di_threshold, adx_min, avoid_hours variations

Output:
  data/backtest_prod_full.csv          — full-period results, all 8 pairs
  data/backtest_prod_live_period.csv   — Mar10–Apr10 window, USD_JPY + NAS100_USD
  data/backtest_prod_retune_sweep.csv  — retuning sweep, USD_JPY + NAS100_USD
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path("/mnt/d/VSProjects/Stock Scanner/asx-screener")))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("/mnt/d/VSProjects/Stock Scanner/asx-screener/data/forex_raw")
INITIAL_BALANCE = 10_000.0
MIN_TRADES      = 5   # relaxed for the 31-day window
RISK_PCT_DEFAULT = 0.01

SPREADS = {
    "XAU_USD": 0.50, "XAG_USD": 0.03, "BCO_USD": 0.04,
    "UK100_GBP": 0.80, "JP225_USD": 17.0, "NAS100_USD": 2.30,
    "EUR_USD": 0.0001, "USD_JPY": 0.02,
}

# ── Production configs (exact match to best_strategies.json) ──────────────────
PROD_CONFIGS = {
    "XAU_USD": dict(
        tf="15_Min", rr=3.5, risk_pct=0.015,
        di=35.0, persist=2, adx_min=0.0, adx_rising=True,
        atr_ratio=1.0, di_slope=False, di_spread=0.0,
        avoid_hours={8, 9},
    ),
    "XAG_USD": dict(
        tf="5_Min", rr=12.0, risk_pct=0.01,
        di=35.0, persist=1, adx_min=0.0, adx_rising=False,
        atr_ratio=1.2, di_slope=True, di_spread=0.0,
        avoid_hours={14, 15, 16},
    ),
    "JP225_USD": dict(
        tf="5_Min", rr=1.5, risk_pct=0.01,
        di=30.0, persist=2, adx_min=20.0, adx_rising=True,
        atr_ratio=1.2, di_slope=True, di_spread=15.0,
        avoid_hours={21, 22, 23},
    ),
    "NAS100_USD": dict(
        tf="15_Min", rr=2.5, risk_pct=0.01,
        di=30.0, persist=2, adx_min=25.0, adx_rising=False,
        atr_ratio=1.0, di_slope=True, di_spread=0.0,
        avoid_hours={7, 8, 21, 22, 23},
    ),
    "UK100_GBP": dict(
        tf="15_Min", rr=3.5, risk_pct=0.01,
        di=35.0, persist=2, adx_min=0.0, adx_rising=False,
        atr_ratio=1.2, di_slope=False, di_spread=0.0,
        avoid_hours={15, 16, 17, 18, 19},
    ),
    "EUR_USD": dict(
        tf="15_Min", rr=6.0, risk_pct=0.01,
        di=25.0, persist=2, adx_min=0.0, adx_rising=False,
        atr_ratio=1.0, di_slope=False, di_spread=0.0,
        avoid_hours={20, 21, 22, 23},
    ),
    "USD_JPY": dict(
        tf="15_Min", rr=3.0, risk_pct=0.005,
        di=30.0, persist=1, adx_min=0.0, adx_rising=False,
        atr_ratio=0.0, di_slope=False, di_spread=0.0,
        avoid_hours={15, 16, 17, 18, 19, 20, 21},
    ),
    "BCO_USD": dict(
        tf="15_Min", rr=5.0, risk_pct=0.01,
        di=30.0, persist=1, adx_min=15.0, adx_rising=False,
        atr_ratio=1.0, di_slope=False, di_spread=0.0,
        avoid_hours={20, 21, 22, 23},
    ),
}

LIVE_START = pd.Timestamp("2026-03-10")
LIVE_END   = pd.Timestamp("2026-04-10")


# ── Data loading ──────────────────────────────────────────────────────────────
def load_and_prep(symbol: str, tf: str) -> pd.DataFrame:
    csv = DATA_DIR / f"{symbol}_{tf}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df["ATR_avg20"] = df["ATR"].rolling(20).mean()
    df.dropna(
        subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR", "ATR_avg20"],
        inplace=True,
    )
    return df


# ── Core backtest ─────────────────────────────────────────────────────────────
def run_backtest(df: pd.DataFrame, cfg: dict, min_trades: int = MIN_TRADES) -> dict | None:
    rr         = cfg["rr"]
    di         = cfg["di"]
    persist    = cfg["persist"]
    adx_min    = cfg["adx_min"]
    adx_rising = cfg["adx_rising"]
    atr_ratio  = cfg["atr_ratio"]
    di_slope   = cfg["di_slope"]
    di_spread  = cfg["di_spread"]
    avoid_h    = cfg["avoid_hours"]
    risk_pct   = cfg["risk_pct"]
    symbol     = cfg.get("symbol", "UNK")
    spread     = SPREADS.get(symbol, 0.0002)

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

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None
    start = max(3, persist)

    for i in range(start, len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # Exit
        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    pnl = balance * risk_pct * -1
                    trades.append({"result": "LOSS", "pnl": pnl, "balance": balance + pnl, "ts": times[i]})
                    balance += pnl; in_trade = False
                elif h >= tp:
                    pnl = balance * risk_pct * rr
                    trades.append({"result": "WIN", "pnl": pnl, "balance": balance + pnl, "ts": times[i]})
                    balance += pnl; in_trade = False
            else:
                if h >= sl:
                    pnl = balance * risk_pct * -1
                    trades.append({"result": "LOSS", "pnl": pnl, "balance": balance + pnl, "ts": times[i]})
                    balance += pnl; in_trade = False
                elif l <= tp:
                    pnl = balance * risk_pct * rr
                    trades.append({"result": "WIN", "pnl": pnl, "balance": balance + pnl, "ts": times[i]})
                    balance += pnl; in_trade = False
            continue

        # Time filter
        if avoid_h and times[i].hour in avoid_h:
            continue

        # ADX floor
        if adx_arr[i] < adx_min:
            continue

        # ADX rising
        if adx_rising and i > 0 and adx_arr[i] <= adx_arr[i - 1]:
            continue

        # ATR ratio
        if atr_ratio > 0 and not np.isnan(atr_ma[i]) and atr_ma[i] > 0:
            if atr_arr[i] < atr_ratio * atr_ma[i]:
                continue

        # DI persist
        di_plus_pers  = all(di_plus[i - j]  > di for j in range(persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i])

        if not (is_buy or is_sell):
            continue

        # DI spread min
        if di_spread > 0:
            if is_buy  and (di_plus[i]  - di_minus[i]) < di_spread: continue
            if is_sell and (di_minus[i] - di_plus[i])  < di_spread: continue

        # DI slope
        if di_slope and i > 0:
            if is_buy  and di_plus[i]  <= di_plus[i - 1]:  continue
            if is_sell and di_minus[i] <= di_minus[i - 1]: continue

        # Structural validity
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # ATR-floored SL
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

    if len(trades) < min_trades:
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
    return {
        "trades": n,
        "wins":   int(wins),
        "win_rate": round(wr, 1),
        "roi":    round(roi, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TASK 1 — Full-dataset backtest, all 8 pairs
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("TASK 1 — Full-dataset backtest (all available data), all 8 production pairs")
print("=" * 80)

full_rows = []
for symbol, cfg in PROD_CONFIGS.items():
    cfg = dict(cfg, symbol=symbol)
    try:
        df = load_and_prep(symbol, cfg["tf"])
    except Exception as e:
        print(f"  {symbol}: load error — {e}")
        continue

    period = f"{df.index[0].date()} → {df.index[-1].date()}"
    r = run_backtest(df, cfg, min_trades=MIN_TRADES)
    if r is None:
        print(f"  {symbol}: insufficient trades")
        continue

    row = {"symbol": symbol, "tf": cfg["tf"].replace("_Min","m"),
           "di": cfg["di"], "rr": cfg["rr"], "period": period, **r}
    full_rows.append(row)
    print(f"  {symbol:<14} | {period} | n={r['trades']:>4} | WR={r['win_rate']:>5.1f}% | "
          f"ROI={r['roi']:>+7.2f}% | Sharpe={r['sharpe']:>5.2f} | MaxDD={r['max_dd']:>7.2f}%")

df_full = pd.DataFrame(full_rows)
df_full.to_csv(
    "/mnt/d/VSProjects/Stock Scanner/asx-screener/data/backtest_prod_full.csv",
    index=False
)


# ─────────────────────────────────────────────────────────────────────────────
# TASK 2 — Same-period backtest (Mar 10 – Apr 10) for USD_JPY and NAS100_USD
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("TASK 2 — Live-period backtest (Mar 10 – Apr 10, 2026): USD_JPY + NAS100_USD")
print("=" * 80)

period_rows = []
for symbol in ["USD_JPY", "NAS100_USD"]:
    cfg = dict(PROD_CONFIGS[symbol], symbol=symbol)
    df_all = load_and_prep(symbol, cfg["tf"])
    df_win = df_all.loc[LIVE_START:LIVE_END].copy()
    print(f"  {symbol}: {len(df_win)} bars in live window "
          f"({df_win.index[0].date() if len(df_win) else 'empty'} → "
          f"{df_win.index[-1].date() if len(df_win) else 'empty'})")

    r = run_backtest(df_win, cfg, min_trades=1)
    if r is None:
        print(f"    → No results (0 trades)")
        row_data = {"symbol": symbol, "window": "Mar10-Apr10",
                    "trades": 0, "win_rate": None, "roi": None, "sharpe": None, "max_dd": None}
    else:
        row_data = {"symbol": symbol, "window": "Mar10-Apr10", **r}
        print(f"    n={r['trades']} | WR={r['win_rate']:.1f}% | "
              f"ROI={r['roi']:+.2f}% | Sharpe={r['sharpe']:.2f} | MaxDD={r['max_dd']:.2f}%")
    period_rows.append(row_data)

df_period = pd.DataFrame(period_rows)
df_period.to_csv(
    "/mnt/d/VSProjects/Stock Scanner/asx-screener/data/backtest_prod_live_period.csv",
    index=False
)


# ─────────────────────────────────────────────────────────────────────────────
# TASK 3 — Retuning sweep: USD_JPY and NAS100_USD (live period only)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("TASK 3 — Retuning sweep (live period Mar10–Apr10): USD_JPY + NAS100_USD")
print("=" * 80)

sweep_rows = []

# ── USD_JPY sweep ─────────────────────────────────────────────────────────────
print("\n  [USD_JPY] — sweeping di_threshold, adx_min, avoid_hours")
df_jpy_all = load_and_prep("USD_JPY", "15_Min")
df_jpy_win = df_jpy_all.loc[LIVE_START:LIVE_END].copy()

# Also keep full-period df for reference
df_jpy_full = df_jpy_all.copy()

jpy_base = dict(PROD_CONFIGS["USD_JPY"], symbol="USD_JPY")

# Avoid-hours variants
avoid_variants_jpy = {
    "prod [15-21]":    {15, 16, 17, 18, 19, 20, 21},
    "tight [14-22]":   {14, 15, 16, 17, 18, 19, 20, 21, 22},
    "Asia-only [21-0]": {21, 22, 23, 0},
    "no filter":        set(),
    "NY+eve [13-22]":  {13, 14, 15, 16, 17, 18, 19, 20, 21, 22},
}

for di_val in [25.0, 30.0, 35.0]:
    for adx_val in [0.0, 10.0, 15.0, 20.0]:
        for ah_label, ah_set in avoid_variants_jpy.items():
            cfg_test = dict(jpy_base, di=di_val, adx_min=adx_val, avoid_hours=ah_set)

            # live window
            r_live = run_backtest(df_jpy_win, cfg_test, min_trades=1)
            # full period
            r_full = run_backtest(df_jpy_full, cfg_test, min_trades=MIN_TRADES)

            row = {
                "symbol":      "USD_JPY",
                "di":          di_val,
                "adx_min":     adx_val,
                "avoid_hours": ah_label,
                "rr":          jpy_base["rr"],
                # live window
                "live_trades":   r_live["trades"]   if r_live else 0,
                "live_wr":       r_live["win_rate"]  if r_live else None,
                "live_roi":      r_live["roi"]       if r_live else None,
                "live_sharpe":   r_live["sharpe"]    if r_live else None,
                "live_maxdd":    r_live["max_dd"]    if r_live else None,
                # full period
                "full_trades":   r_full["trades"]   if r_full else None,
                "full_wr":       r_full["win_rate"]  if r_full else None,
                "full_roi":      r_full["roi"]       if r_full else None,
                "full_sharpe":   r_full["sharpe"]    if r_full else None,
                "full_maxdd":    r_full["max_dd"]    if r_full else None,
                "is_prod":       (di_val == 30.0 and adx_val == 0.0 and ah_label == "prod [15-21]"),
            }
            sweep_rows.append(row)

# ── NAS100 sweep ──────────────────────────────────────────────────────────────
print("\n  [NAS100_USD] — sweeping di_threshold, adx_min, avoid_hours")
df_nas_all = load_and_prep("NAS100_USD", "15_Min")
df_nas_win = df_nas_all.loc[LIVE_START:LIVE_END].copy()
df_nas_full = df_nas_all.copy()

nas_base = dict(PROD_CONFIGS["NAS100_USD"], symbol="NAS100_USD")

avoid_variants_nas = {
    "prod [7,8,21-23]": {7, 8, 21, 22, 23},
    "tight [7,8,20-23]": {7, 8, 20, 21, 22, 23},
    "US-hours only [13-22]": {13, 14, 15, 16, 17, 18, 19, 20, 21, 22},
    "no filter":        set(),
    "extended [6,7,8,20-23]": {6, 7, 8, 20, 21, 22, 23},
}

for di_val in [25.0, 30.0, 35.0]:
    for adx_val in [0.0, 15.0, 20.0, 25.0]:
        for ah_label, ah_set in avoid_variants_nas.items():
            cfg_test = dict(nas_base, di=di_val, adx_min=adx_val, avoid_hours=ah_set)

            r_live = run_backtest(df_nas_win, cfg_test, min_trades=1)
            r_full = run_backtest(df_nas_full, cfg_test, min_trades=MIN_TRADES)

            row = {
                "symbol":      "NAS100_USD",
                "di":          di_val,
                "adx_min":     adx_val,
                "avoid_hours": ah_label,
                "rr":          nas_base["rr"],
                "live_trades":   r_live["trades"]   if r_live else 0,
                "live_wr":       r_live["win_rate"]  if r_live else None,
                "live_roi":      r_live["roi"]       if r_live else None,
                "live_sharpe":   r_live["sharpe"]    if r_live else None,
                "live_maxdd":    r_live["max_dd"]    if r_live else None,
                "full_trades":   r_full["trades"]   if r_full else None,
                "full_wr":       r_full["win_rate"]  if r_full else None,
                "full_roi":      r_full["roi"]       if r_full else None,
                "full_sharpe":   r_full["sharpe"]    if r_full else None,
                "full_maxdd":    r_full["max_dd"]    if r_full else None,
                "is_prod":       (di_val == 30.0 and adx_val == 25.0 and ah_label == "prod [7,8,21-23]"),
            }
            sweep_rows.append(row)

df_sweep = pd.DataFrame(sweep_rows)
df_sweep.to_csv(
    "/mnt/d/VSProjects/Stock Scanner/asx-screener/data/backtest_prod_retune_sweep.csv",
    index=False
)

# ─────────────────────────────────────────────────────────────────────────────
# Print sweep results summary — top 10 per pair, sorted by live_sharpe
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("SWEEP RESULTS — USD_JPY (top configs by live-period Sharpe, full_sharpe >= 1.5)")
print("=" * 80)

jpy_sweep = df_sweep[df_sweep["symbol"] == "USD_JPY"].copy()
jpy_sweep = jpy_sweep[jpy_sweep["live_trades"] >= 3]
# Must not destroy full-period performance
jpy_sweep_ok = jpy_sweep[
    jpy_sweep["full_sharpe"].notna() & (jpy_sweep["full_sharpe"] >= 1.5)
].sort_values("live_sharpe", ascending=False).head(15)

print(f"\n  {'DI':>4} {'ADXmin':>6} {'AvoidH':<22} {'RR':>4} | "
      f"{'LiveN':>6} {'LiveWR':>7} {'LiveROI':>8} {'LiveSh':>7} {'LiveDD':>7} | "
      f"{'FullN':>6} {'FullSh':>7} {'FullROI':>8}")
print("  " + "-" * 110)
for _, row in jpy_sweep_ok.iterrows():
    tag = " ← PROD" if row.get("is_prod") else ""
    print(f"  {row['di']:>4.0f} {row['adx_min']:>6.0f} {row['avoid_hours']:<22} {row['rr']:>4.1f} | "
          f"{int(row['live_trades']):>6} {row['live_wr']:>6.1f}% {row['live_roi']:>+7.2f}% "
          f"{row['live_sharpe']:>7.2f} {row['live_maxdd']:>7.2f}% | "
          f"{int(row['full_trades']) if pd.notna(row['full_trades']) else '-':>6} "
          f"{row['full_sharpe']:>7.2f} {row['full_roi']:>+7.2f}%{tag}")

# Show prod row even if filtered out
prod_row_jpy = jpy_sweep[jpy_sweep["is_prod"] == True]
if not prod_row_jpy.empty and prod_row_jpy.index[0] not in jpy_sweep_ok.index:
    r = prod_row_jpy.iloc[0]
    print(f"\n  [PROD config] DI={r['di']:.0f} ADX={r['adx_min']:.0f} AH={r['avoid_hours']} | "
          f"live n={r['live_trades']:.0f} WR={r['live_wr']}% ROI={r['live_roi']:+.2f}% "
          f"Sh={r['live_sharpe']} | full Sh={r['full_sharpe']}")

print("\n" + "=" * 80)
print("SWEEP RESULTS — NAS100_USD (top configs by live-period Sharpe, full_sharpe >= 2.0)")
print("=" * 80)

nas_sweep = df_sweep[df_sweep["symbol"] == "NAS100_USD"].copy()
nas_sweep = nas_sweep[nas_sweep["live_trades"] >= 3]
nas_sweep_ok = nas_sweep[
    nas_sweep["full_sharpe"].notna() & (nas_sweep["full_sharpe"] >= 2.0)
].sort_values("live_sharpe", ascending=False).head(15)

print(f"\n  {'DI':>4} {'ADXmin':>6} {'AvoidH':<28} {'RR':>4} | "
      f"{'LiveN':>6} {'LiveWR':>7} {'LiveROI':>8} {'LiveSh':>7} {'LiveDD':>7} | "
      f"{'FullN':>6} {'FullSh':>7} {'FullROI':>8}")
print("  " + "-" * 115)
for _, row in nas_sweep_ok.iterrows():
    tag = " ← PROD" if row.get("is_prod") else ""
    print(f"  {row['di']:>4.0f} {row['adx_min']:>6.0f} {row['avoid_hours']:<28} {row['rr']:>4.1f} | "
          f"{int(row['live_trades']):>6} {row['live_wr']:>6.1f}% {row['live_roi']:>+7.2f}% "
          f"{row['live_sharpe']:>7.2f} {row['live_maxdd']:>7.2f}% | "
          f"{int(row['full_trades']) if pd.notna(row['full_trades']) else '-':>6} "
          f"{row['full_sharpe']:>7.2f} {row['full_roi']:>+7.2f}%{tag}")

prod_row_nas = nas_sweep[nas_sweep["is_prod"] == True]
if not prod_row_nas.empty and prod_row_nas.index[0] not in nas_sweep_ok.index:
    r = prod_row_nas.iloc[0]
    print(f"\n  [PROD config] DI={r['di']:.0f} ADX={r['adx_min']:.0f} AH={r['avoid_hours']} | "
          f"live n={r['live_trades']:.0f} WR={r['live_wr']}% ROI={r['live_roi']:+.2f}% "
          f"Sh={r['live_sharpe']} | full Sh={r['full_sharpe']}")

print(f"\n\nSaved:")
print(f"  /mnt/d/VSProjects/Stock Scanner/asx-screener/data/backtest_prod_full.csv")
print(f"  /mnt/d/VSProjects/Stock Scanner/asx-screener/data/backtest_prod_live_period.csv")
print(f"  /mnt/d/VSProjects/Stock Scanner/asx-screener/data/backtest_prod_retune_sweep.csv")
