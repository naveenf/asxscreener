"""
XAG_USD 15m — Noise Filter Sweep (gap-priced, OOS-gated)
=========================================================
XAG runs live on 5m at RR=12. Over 10 months of 15m data that target produces
Sharpe 0.09 / ROI +1.0% with a 8.3% win rate — the 12R target essentially never
pays, which matches the live record (1.5% of XAG wins reached 80% of target).

Every 15m R:R produced a better result than that, but the R:R surface was
jagged (2.0 passed OOS, 3.0 failed, 3.5 passed, 4.0 passed, 5.0 failed) with no
contiguous plateau. The likely cause: XAG's filters — atr_ratio=1.2, di_slope,
avoid_hours=[14,15,16] — were all fitted on 5m bar dynamics and are simply the
wrong filters for 15m. So refit the filters here first, then read R:R off the
winner rather than the other way round.

Two guards this sweep applies that earlier sweeps in this repo did not:

  1. Gapped stops are priced at the true post-weekend open, not at -1R. Every
     other script books stops at exactly -1R, which flatters any config that
     holds over weekends (see scripts/backtest_weekend_gap_impact.py).

  2. Every cell must pass a split-half out-of-sample gate — positive mean R in
     BOTH halves of the window — before it is eligible. Reported separately
     from the headline number so a flattering full-window Sharpe cannot be
     mistaken for a validated one. This repo has promoted configs on short
     windows before (EUR_AUD Sharpe 4.52 -> -0.07 live; NAS100 14.36 on 15
     trades -> negative live).

Because this sweep tests many configs, the count of cells tried is reported.
Treat the top of a large grid as a hypothesis, not a result: with ~200 cells,
some will clear any fixed bar by chance. Prefer a config sitting inside a
contiguous region of passing neighbours over an isolated peak.

Output: data/backtest_xag_15m_filter_sweep.csv
"""

import sys
import itertools
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_xag_15m_filter_sweep.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
SPREAD          = 0.003          # XAG_USD Oanda spread
MIN_TRADES      = 40             # 10 months of 15m; below this Sharpe is noise
MIN_HALF_TRADES = 15
FLAT_UTC_HOUR   = 19             # matches WEEKEND_FLAT_CONFIGS in tasks.py

# Live 5m config, for reference in the output
LIVE_5M = dict(di=35.0, persist=1, adx_min=0.0, atr_ratio=1.2, di_slope=True,
               avoid_hours=[14, 15, 16], rr=12.0)

# --- Sweep grid -------------------------------------------------------------
DI_GRID         = [25.0, 30.0, 35.0]
ATR_GRID        = [0.0, 1.0, 1.2]
SLOPE_GRID      = [False, True]
ADX_GRID        = [0.0, 15.0, 20.0]
PERSIST_GRID    = [1, 2]
# XAG's live avoid_hours block the London-NY overlap; on 15m that may be wrong,
# so test dropping it and the two thin-session windows used by other pairs.
AVOID_GRID      = {
    "none":        [],
    "live_5m":     [14, 15, 16],
    "post_ny":     [20, 21, 22, 23],
    "pre_london":  [5, 6, 7],
}
RR_GRID         = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]


def load_and_prep():
    df = pd.read_csv(DATA_DIR / "XAG_USD_15_Min.csv", parse_dates=["Date"])
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
    """Replay one config. Returns a per-trade DataFrame of realised R."""
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
        if cfg["atr_ratio"] > 0 and not np.isnan(atrma[i]) and atrma[i] > 0:
            if atr[i] < cfg["atr_ratio"] * atrma[i]:
                continue

        dp_ok = all(dp[i - j] > di for j in range(persist))
        dm_ok = all(dm[i - j] > di for j in range(persist))
        is_buy = c[i] > s20[i] and c[i] > s50[i] and c[i] > s100[i] and dp_ok and dp[i] > dm[i]
        is_sell = c[i] < s20[i] and c[i] < s50[i] and c[i] < s100[i] and dm_ok and dm[i] > dp[i]
        if not (is_buy or is_sell):
            continue

        if cfg["di_slope"]:                     # live detector: iloc[-1] > iloc[-3]
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
    """Aggregate one trade list, including the split-half OOS gate."""
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
    print(f"XAG_USD 15m  bars={len(df)}  {df.index[0].date()} → {df.index[-1].date()}")
    print(f"split-half boundary: {mid.date()}\n")

    rows = []
    combos = list(itertools.product(DI_GRID, ATR_GRID, SLOPE_GRID, ADX_GRID,
                                    PERSIST_GRID, AVOID_GRID.items(), RR_GRID))
    print(f"Testing {len(combos) * 2} cells (x2 for weekend hold/flat)...")

    for di, atr_r, slope, adx_min, persist, (ah_name, ah), rr in combos:
        cfg = dict(di=di, atr_ratio=atr_r, di_slope=slope, adx_min=adx_min,
                   persist=persist, avoid_hours=ah, rr=rr)
        for flat in (False, True):
            t = run(df, cfg, weekend_flat=flat)
            m = metrics(t, mid)
            if m is None:
                continue
            rows.append({
                "di": di, "atr_ratio": atr_r, "di_slope": slope, "adx_min": adx_min,
                "persist": persist, "avoid": ah_name, "rr": rr,
                "weekend": "flat" if flat else "hold", **m,
            })

    out = pd.DataFrame(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_FILE, index=False)

    print(f"\n{len(out)} cells met the {MIN_TRADES}-trade floor; "
          f"{int(out.oos_pass.sum())} also passed the split-half gate.\n")

    ok = out[out.oos_pass].sort_values("sharpe", ascending=False)
    cols = ["di", "atr_ratio", "di_slope", "adx_min", "persist", "avoid", "rr",
            "weekend", "trades", "win_rate", "roi", "sharpe", "max_dd",
            "worst_R", "exp_R_half1", "exp_R_half2", "months_pos", "months_total"]
    print("TOP 25 OOS-PASSING CONFIGS")
    print(ok[cols].head(25).to_string(index=False))
    print(f"\nSaved {len(out)} rows → {OUT_FILE}")
