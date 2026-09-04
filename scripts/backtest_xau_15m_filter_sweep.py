"""
XAU_USD 15m — Noise Filter Sweep (gap-priced, OOS-gated)
=========================================================
XAU is the account's biggest live earner (+$3,400 realised) and its config has
never been swept on the current 15m dataset — only the stop-stage family was
(Aug 25, 2026), which found nothing: 3/151 cells cut drawdown and the median
made it worse (-7.28% -> -9.97%). So the profit-lock / breakeven route is
closed for this pair; this sweep asks whether the ENTRY filters can cut
drawdown without giving up ROI.

Live config being challenged: di=35, persist=2, adx_rising=True, avoid=[8,9],
rr=3.5, risk 1.5%. Its stop-stage baseline on this data was
trades=58, ROI +131.62%, Sharpe 6.56, MaxDD -7.28%.

Note the 58-trade baseline is below the repo's own 60-trade promotion floor, so
the incumbent is itself thinly evidenced — a challenger must beat it on trade
count as well as on ROI/DD to be worth adopting.

Same two guards as the XAG sweep this is adapted from:

  1. Gapped stops are priced at the true post-weekend open, not at -1R.
  2. Every cell must pass a split-half out-of-sample gate (positive mean R in
     BOTH halves) before it is eligible.

With ~13k cells some will clear any fixed bar by chance. Read the top row as a
hypothesis and confirm it with the per-parameter marginal analysis before
believing it — that check is what rejected XAG's `post_ny` winner.

Output: data/backtest_xau_15m_filter_sweep.csv
"""

import sys
import itertools
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_xau_15m_filter_sweep.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.015          # XAU live risk_pct
SPREAD          = 0.30           # XAU_USD Oanda spread
MIN_TRADES      = 40
MIN_HALF_TRADES = 15
FLAT_UTC_HOUR   = 19

LIVE = dict(di=35.0, persist=2, adx_min=0.0, adx_rising=True, atr_ratio=0.0,
            di_slope=False, avoid_hours=[8, 9], rr=3.5)

# --- Sweep grid -------------------------------------------------------------
DI_GRID       = [25.0, 30.0, 35.0]
ATR_GRID      = [0.0, 1.0, 1.2]
SLOPE_GRID    = [False, True]
ADX_GRID      = [0.0, 15.0, 20.0]
PERSIST_GRID  = [1, 2]
RISING_GRID   = [False, True]
AVOID_GRID    = {
    "none":       [],
    "live":       [8, 9],
    "post_ny":    [20, 21, 22, 23],
    "pre_london": [5, 6, 7],
}
RR_GRID       = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]


def load_and_prep():
    df = pd.read_csv(DATA_DIR / "XAU_USD_15_Min.csv", parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df["ATR_avg20"] = df["ATR"].rolling(20).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus",
                      "ADX", "ATR", "ATR_avg20"], inplace=True)
    return df


def run(df, cfg, weekend_flat=False):
    c, h, l, o = (df[x].values for x in ("Close", "High", "Low", "Open"))
    s20, s50, s100 = (df[x].values for x in ("SMA20", "SMA50", "SMA100"))
    dp, dm = df["DIPlus"].values, df["DIMinus"].values
    adx, atr, atrma = df["ADX"].values, df["ATR"].values, df["ATR_avg20"].values
    T, dow, hour = df.index, df.index.dayofweek.values, df.index.hour.values
    is_gap_bar = (df.index.to_series().diff() > pd.Timedelta(hours=6)).values

    rr, di, persist = cfg["rr"], cfg["di"], cfg["persist"]
    ah = set(cfg["avoid_hours"])

    trades = []
    in_trade = False
    sl = tp = entry = direction = None

    for i in range(max(3, persist), len(df)):
        flat_now = weekend_flat and dow[i] == 4 and hour[i] >= FLAT_UTC_HOUR

        if in_trade:
            risk = abs(entry - sl)
            hit_sl = (l[i] <= sl) if direction == "BUY" else (h[i] >= sl)
            hit_tp = (h[i] >= tp) if direction == "BUY" else (l[i] <= tp)
            if hit_sl:
                fill = sl
                if is_gap_bar[i]:
                    gapped = o[i] < sl if direction == "BUY" else o[i] > sl
                    if gapped:
                        fill = o[i]
                r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
                trades.append({"date": T[i], "r": float(r)})
                in_trade = False
            elif hit_tp:
                trades.append({"date": T[i], "r": rr})
                in_trade = False
            elif flat_now:
                r = (c[i] - entry) / risk if direction == "BUY" else (entry - c[i]) / risk
                trades.append({"date": T[i], "r": float(r)})
                in_trade = False
            continue

        if flat_now or hour[i] in ah:
            continue
        if adx[i] < cfg["adx_min"]:
            continue
        if cfg["adx_rising"] and adx[i] <= adx[i - 1]:
            continue
        if cfg["atr_ratio"] > 0 and not np.isnan(atrma[i]) and atrma[i] > 0:
            if atr[i] < cfg["atr_ratio"] * atrma[i]:
                continue

        dp_ok = all(dp[i - j] > di for j in range(persist))
        dm_ok = all(dm[i - j] > di for j in range(persist))
        is_buy = c[i] > s20[i] and c[i] > s50[i] and c[i] > s100[i] and dp_ok and dp[i] > dm[i]
        is_sell = c[i] < s20[i] and c[i] < s50[i] and c[i] < s100[i] and dm_ok and dm[i] > dp[i]
        if not (is_buy or is_sell):
            continue

        if cfg["di_slope"]:
            if is_buy and dp[i] <= dp[i - 2]:
                continue
            if is_sell and dm[i] <= dm[i - 2]:
                continue

        prev_low, prev_high = min(l[i - 2], l[i - 1]), max(h[i - 2], h[i - 1])
        if is_buy and c[i] < prev_low:
            continue
        if is_sell and c[i] > prev_high:
            continue

        if is_buy:
            sl_p = c[i] - max(c[i] - prev_low, atr[i]) - SPREAD
            risk = c[i] - sl_p
            if risk <= 0:
                continue
            direction, sl, tp = "BUY", sl_p, c[i] + risk * rr
        else:
            sl_p = c[i] + max(prev_high - c[i], atr[i]) + SPREAD
            risk = sl_p - c[i]
            if risk <= 0:
                continue
            direction, sl, tp = "SELL", sl_p, c[i] - risk * rr
        entry, in_trade = c[i], True

    return pd.DataFrame(trades)


def metrics(t, mid):
    if len(t) < MIN_TRADES:
        return None
    bal = INITIAL_BALANCE
    eq = []
    for r in t["r"].values:
        bal += bal * RISK_PCT * r
        eq.append(bal)
    eq = np.array(eq)
    peak = np.maximum.accumulate(eq)
    rets = pd.Series(np.diff(np.concatenate([[INITIAL_BALANCE], eq])) / INITIAL_BALANCE)
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0

    h1, h2 = t[t["date"] <= mid], t[t["date"] > mid]
    if len(h1) < MIN_HALF_TRADES or len(h2) < MIN_HALF_TRADES:
        e1 = e2 = np.nan
        passed = False
    else:
        e1, e2 = h1["r"].mean(), h2["r"].mean()
        passed = min(e1, e2) > 0.05

    months = t.assign(M=pd.to_datetime(t["date"]).dt.to_period("M")).groupby("M")["r"].mean()
    return {
        "trades": len(t),
        "win_rate": round((t["r"] > 0).mean() * 100, 1),
        "roi": round((eq[-1] - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(float(((eq - peak) / peak * 100).min()), 2),
        "expectancy_R": round(float(t["r"].mean()), 3),
        "worst_R": round(float(t["r"].min()), 2),
        "exp_R_half1": round(float(e1), 3) if e1 == e1 else np.nan,
        "exp_R_half2": round(float(e2), 3) if e2 == e2 else np.nan,
        "oos_pass": passed,
        "months_pos": int((months > 0).sum()),
        "months_total": len(months),
    }


if __name__ == "__main__":
    df = load_and_prep()
    mid = df.index[len(df) // 2]
    print(f"XAU_USD 15m  bars={len(df)}  {df.index[0].date()} → {df.index[-1].date()}")
    print(f"split-half boundary: {mid.date()}\n")

    rows = []
    combos = list(itertools.product(DI_GRID, ATR_GRID, SLOPE_GRID, ADX_GRID,
                                    PERSIST_GRID, RISING_GRID,
                                    AVOID_GRID.items(), RR_GRID))
    print(f"Testing {len(combos) * 2} cells (x2 for weekend hold/flat)...", flush=True)

    for n, (di, atr_r, slope, adx_min, persist, rising, (ah_name, ah), rr) in enumerate(combos):
        cfg = dict(di=di, atr_ratio=atr_r, di_slope=slope, adx_min=adx_min,
                   persist=persist, adx_rising=rising, avoid_hours=ah, rr=rr)
        for flat in (False, True):
            t = run(df, cfg, weekend_flat=flat)
            m = metrics(t, mid)
            if m is None:
                continue
            rows.append({
                "di": di, "atr_ratio": atr_r, "di_slope": slope, "adx_min": adx_min,
                "persist": persist, "adx_rising": rising, "avoid": ah_name, "rr": rr,
                "weekend": "flat" if flat else "hold", **m,
            })
        if n % 500 == 0:
            print(f"  ...{n}/{len(combos)} combos, {len(rows)} rows kept", flush=True)

    out = pd.DataFrame(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_FILE, index=False)

    print(f"\n{len(out)} cells met the {MIN_TRADES}-trade floor; "
          f"{int(out.oos_pass.sum())} also passed the split-half gate.\n")

    ok = out[out.oos_pass].sort_values("sharpe", ascending=False)
    cols = ["di", "atr_ratio", "di_slope", "adx_min", "persist", "adx_rising",
            "avoid", "rr", "weekend", "trades", "win_rate", "roi", "sharpe",
            "max_dd", "worst_R", "exp_R_half1", "exp_R_half2", "months_pos", "months_total"]
    print("TOP 25 OOS-PASSING CONFIGS")
    print(ok[cols].head(25).to_string(index=False))
    print(f"\nSaved {len(out)} rows → {OUT_FILE}")
