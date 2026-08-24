"""
Stop-stage sweep — XAG_USD / XAU_USD / NAS100_USD
==================================================
Question: can a profit lock or a breakeven stage cut drawdown on these three
pairs without giving up ROI? None of them has a stop-move stage today.

Replaces scripts/backtest_breakeven_sweep.py, which is dead code — it imports
backtest_lock_sweep_v2, deleted in Aug 2026. This version is self-contained.

Two stage types, matching decide_stop_move() in tasks.py:
  stage 0  SL at -1R                          (original)
  be       price reaches be_at_r  -> SL to be_to_r   (small loss near entry)
  lock     price reaches lock_at_r -> SL to lock_to_r (into profit)
Both may be configured together; the lock wins if a bar clears both.

Simulation rules, carried over from the original sweep:
  - Arming is evaluated AFTER exits each candle, so a spike-and-reverse inside
    one bar cannot retroactively rescue a trade.
  - Ties within a bar resolve to the worse outcome (SL checked before TP).
  - A moved SL takes effect from the NEXT candle onward.
Plus, new here:
  - Gapped stops fill at the true post-weekend open, not at the stop price.
  - Every row carries a split-half out-of-sample check.

Cooldown is NOT modelled: it blocks re-entry after a locked trade closes, which
would need the full signal stream re-simulated. Live results with a cooldown
will differ slightly from any lock row here — treat lock rows as an upper bound.

Output: data/backtest_stop_stage_sweep.csv
"""

import sys
import itertools
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_stop_stage_sweep.csv")
INITIAL_BALANCE = 10_000.0
MIN_TRADES      = 30
MIN_HALF        = 12

# Current production configs (best_strategies.json, Aug 25 2026)
PAIRS = {
    "XAG_USD": dict(timeframe="15m", rr=3.0, risk_pct=0.010, spread=0.003,
                    di=35.0, persist=2, adx_min=0.0, adx_rising=False,
                    atr_ratio=1.2, di_slope=True, avoid_hours=[]),
    "XAU_USD": dict(timeframe="15m", rr=3.5, risk_pct=0.015, spread=0.30,
                    di=35.0, persist=2, adx_min=0.0, adx_rising=True,
                    atr_ratio=0.0, di_slope=False, avoid_hours=[8, 9]),
    "NAS100_USD": dict(timeframe="15m", rr=3.5, risk_pct=0.010, spread=1.5,
                       di=35.0, persist=2, adx_min=30.0, adx_rising=False,
                       atr_ratio=1.2, di_slope=True,
                       avoid_hours=[7, 8, 20, 21, 22, 23]),
}

BE_GRID   = [(t, l) for t in (0.25, 0.5, 0.75, 1.0, 1.5)
                    for l in (-0.3, -0.2, -0.1, 0.0)]
LOCK_GRID = [(1.0, 0.5), (1.5, 0.5), (1.5, 1.0), (2.0, 1.0),
             (2.0, 1.5), (2.5, 1.5), (2.5, 2.0)]


def load_and_prep(symbol, timeframe):
    tf = "15_Min" if timeframe == "15m" else "5_Min"
    df = pd.read_csv(DATA_DIR / f"{symbol}_{tf}.csv", parse_dates=["Date"])
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


def run(df, cfg, be=None, lock=None):
    """Replay one config with an optional breakeven and/or lock stage."""
    c, h, l, o = (df[x].values for x in ("Close", "High", "Low", "Open"))
    s20, s50, s100 = (df[x].values for x in ("SMA20", "SMA50", "SMA100"))
    dp, dm = df["DIPlus"].values, df["DIMinus"].values
    adx, atr, atrma = df["ADX"].values, df["ATR"].values, df["ATR_avg20"].values
    T, hour = df.index, df.index.hour.values
    is_gap_bar = (df.index.to_series().diff() > pd.Timedelta(hours=6)).values

    rr, di, persist = cfg["rr"], cfg["di"], cfg["persist"]
    ah = set(cfg["avoid_hours"])
    be_at, be_to     = be   if be   else (None, None)
    lock_at, lock_to = lock if lock else (None, None)

    trades = []
    in_trade = False
    sl = tp = entry = risk = direction = None
    be_fired = lock_fired = False

    for i in range(max(3, persist), len(df)):
        if in_trade:
            # --- exits first; ties resolve to the worse outcome ---
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
                continue
            if hit_tp:
                trades.append({"date": T[i], "r": rr})
                in_trade = False
                continue

            # --- arming, evaluated only after exits ---
            fav = h[i] if direction == "BUY" else l[i]
            r_reached = (fav - entry) / risk if direction == "BUY" else (entry - fav) / risk
            if not lock_fired and lock_at is not None and r_reached >= lock_at:
                sl = entry + lock_to * risk if direction == "BUY" else entry - lock_to * risk
                lock_fired = True
            elif not be_fired and not lock_fired and be_at is not None and r_reached >= be_at:
                sl = entry + be_to * risk if direction == "BUY" else entry - be_to * risk
                be_fired = True
            continue

        if hour[i] in ah or adx[i] < cfg["adx_min"]:
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
            sl_p = c[i] - max(c[i] - prev_low, atr[i]) - cfg["spread"]
            risk = c[i] - sl_p
            if risk <= 0:
                continue
            direction, sl, tp = "BUY", sl_p, c[i] + risk * rr
        else:
            sl_p = c[i] + max(prev_high - c[i], atr[i]) + cfg["spread"]
            risk = sl_p - c[i]
            if risk <= 0:
                continue
            direction, sl, tp = "SELL", sl_p, c[i] - risk * rr
        entry, in_trade = c[i], True
        be_fired = lock_fired = False

    return pd.DataFrame(trades)


def metrics(t, cfg, mid):
    if len(t) < MIN_TRADES:
        return None
    bal, eq = INITIAL_BALANCE, []
    for r in t["r"].values:
        bal += bal * cfg["risk_pct"] * r
        eq.append(bal)
    eq = np.array(eq)
    peak = np.maximum.accumulate(eq)
    rets = pd.Series(np.diff(np.concatenate([[INITIAL_BALANCE], eq])) / INITIAL_BALANCE)
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    h1, h2 = t[t["date"] <= mid], t[t["date"] > mid]
    ok_halves = len(h1) >= MIN_HALF and len(h2) >= MIN_HALF
    e1 = float(h1["r"].mean()) if ok_halves else np.nan
    e2 = float(h2["r"].mean()) if ok_halves else np.nan
    months = t.assign(M=pd.to_datetime(t["date"]).dt.to_period("M")).groupby("M")["r"].mean()
    return {
        "trades": len(t),
        "win_rate": round((t["r"] > 0).mean() * 100, 1),
        "roi": round((eq[-1] - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(float(((eq - peak) / peak * 100).min()), 2),
        "expectancy_R": round(float(t["r"].mean()), 3),
        "exp_R_half1": round(e1, 3) if ok_halves else np.nan,
        "exp_R_half2": round(e2, 3) if ok_halves else np.nan,
        "oos_pass": bool(ok_halves and min(e1, e2) > 0),
        "months_pos": int((months > 0).sum()),
        "months_total": len(months),
    }


if __name__ == "__main__":
    rows = []
    for symbol, cfg in PAIRS.items():
        df = load_and_prep(symbol, cfg["timeframe"])
        mid = df.index[len(df) // 2]
        base = metrics(run(df, cfg), cfg, mid)
        print(f"\n{'='*100}")
        print(f"  {symbol}  {cfg['timeframe']}  RR={cfg['rr']}  "
              f"{df.index[0].date()} → {df.index[-1].date()}")
        print(f"  BASELINE (no stage): ROI {base['roi']:+.2f}%  Sharpe {base['sharpe']:.2f}  "
              f"MaxDD {base['max_dd']:.2f}%  n={base['trades']}  months+ "
              f"{base['months_pos']}/{base['months_total']}")
        print(f"{'='*100}")
        rows.append({"pair": symbol, "stage": "baseline", "be": "", "lock": "", **base})

        combos = ([("be", b, None) for b in BE_GRID]
                  + [("lock", None, k) for k in LOCK_GRID if k[0] < cfg["rr"]]
                  + [("be+lock", b, k) for b in BE_GRID for k in LOCK_GRID
                     if k[0] < cfg["rr"] and b[0] < k[0]])
        for stage, be, lock in combos:
            m = metrics(run(df, cfg, be=be, lock=lock), cfg, mid)
            if m is None:
                continue
            rows.append({"pair": symbol, "stage": stage,
                         "be": f"{be[0]}->{be[1]}" if be else "",
                         "lock": f"{lock[0]}->{lock[1]}" if lock else "", **m})

        sub = pd.DataFrame([r for r in rows if r["pair"] == symbol and r["stage"] != "baseline"])
        # The brief: cut drawdown without giving up ROI.
        better = sub[(sub.max_dd > base["max_dd"]) & (sub.roi >= base["roi"]) & sub.oos_pass]
        print(f"  {len(sub)} configs tested, {len(better)} cut drawdown at >= baseline ROI "
              f"(and passed OOS)")
        if len(better):
            cols = ["stage", "be", "lock", "trades", "win_rate", "roi", "sharpe",
                    "max_dd", "exp_R_half1", "exp_R_half2", "months_pos"]
            print(better.sort_values("max_dd", ascending=False)[cols]
                  .head(12).to_string(index=False))
        else:
            print("  → nothing beats baseline on both axes.")

    out = pd.DataFrame(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(out)} rows → {OUT_FILE}")
