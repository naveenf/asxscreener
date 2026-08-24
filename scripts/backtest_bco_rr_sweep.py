"""
BCO_USD — R:R Sweep (production filters fixed)
===============================================
Live trade history (Mar–Aug 2026) shows the configured high R:R targets are
almost never reached: BCO's 5R target was hit on 7.3% of wins, and realised
payoff sat at ~1.3 regardless of what the config asked for, because winners
were closed manually well before TP.

This sweep asks: at an R:R that will actually be held (1.0–6.0), does the
underlying signal still carry an edge? It holds every production filter fixed
(from best_strategies.json) and sweeps target_rr only.

Reports a split-half out-of-sample check, so a single flattering number can't
be mistaken for a validated result — the repo has a history of promoting
configs on short windows (EUR_AUD, NAS100) that then failed live.

Result (Aug 2026): RR 2.5 beat the live RR 5.0 on Sharpe (1.37 vs 1.26 with
gapped stops priced honestly), ROI, and monthly consistency (8/11 vs 5/10),
with 35% more trades. Deployed alongside the weekend flat — see
scripts/backtest_weekend_gap_impact.py for that half of the decision, and note
the two interact: the weekend flat is only beneficial at the lower target.

Output: data/backtest_bco_rr_sweep.csv
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_bco_rr_sweep.csv")
INITIAL_BALANCE = 10_000.0
MIN_TRADES      = 15
FLAT_UTC_HOUR   = 19   # matches WEEKEND_FLAT_CONFIGS in tasks.py

# Current production configs (best_strategies.json, Aug 2026)
PAIRS = {
    "BCO_USD_15m": dict(
        symbol="BCO_USD", timeframe="15m", current_rr=5.0, risk_pct=0.01, spread=0.03,
        di=30.0, persist=1, adx_min=15.0, adx_rising=False,
        atr_ratio=1.0, di_slope=False, di_spread_min=0.0,
        avoid_hours=[20, 21, 22, 23],
    ),
}

RR_GRID = [round(1.0 + 0.5 * i, 1) for i in range(11)]  # 1.0 .. 6.0


def load_and_prep(symbol: str, timeframe: str) -> pd.DataFrame:
    tf_str = "15_Min" if timeframe == "15m" else "5_Min"
    df = pd.read_csv(DATA_DIR / f"{symbol}_{tf_str}.csv", parse_dates=["Date"])
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


def run_backtest(df, rr, cfg, weekend_flat=False) -> pd.DataFrame | None:
    """Returns per-trade DataFrame, or None if too few trades.

    Mirrors scripts/backtest_rr_sweep.py exit logic (broker SL/TP only) so
    results stay comparable with the numbers recorded in CLAUDE.md.
    """
    closes, highs, lows = df["Close"].values, df["High"].values, df["Low"].values
    sma20, sma50, sma100 = df["SMA20"].values, df["SMA50"].values, df["SMA100"].values
    di_plus, di_minus = df["DIPlus"].values, df["DIMinus"].values
    adx_arr, atr_arr, atr_ma = df["ADX"].values, df["ATR"].values, df["ATR_avg20"].values
    times = df.index

    di, persist   = cfg["di"], cfg["persist"]
    adx_min       = cfg["adx_min"]
    adx_rising    = cfg["adx_rising"]
    atr_ratio     = cfg["atr_ratio"]
    di_slope      = cfg["di_slope"]
    di_spread_min = cfg["di_spread_min"]
    spread        = cfg["spread"]
    risk_pct      = cfg["risk_pct"]
    ah_set        = set(cfg["avoid_hours"])

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None
    entry_price = None

    def close_trade(r_mult, when):
        nonlocal balance, in_trade
        pnl = balance * risk_pct * r_mult
        balance += pnl
        trades.append({"date": when, "r": r_mult, "pnl": pnl, "balance": balance})
        in_trade = False

    for i in range(max(3, persist), len(df)):
        c, h, l, t = closes[i], highs[i], lows[i], times[i]

        if in_trade:
            hit_sl = (l <= sl) if direction == "BUY" else (h >= sl)
            hit_tp = (h >= tp) if direction == "BUY" else (l <= tp)
            if hit_sl:
                close_trade(-1.0, t)
            elif hit_tp:
                close_trade(rr, t)
            elif weekend_flat and t.dayofweek == 4 and t.hour >= FLAT_UTC_HOUR:
                # Flatten at market on Friday evening rather than carry the gap.
                risk_dist = abs(entry_price - sl)
                r_now = (c - entry_price) / risk_dist if direction == "BUY" \
                    else (entry_price - c) / risk_dist
                close_trade(float(r_now), t)
            continue

        if weekend_flat and t.dayofweek == 4 and t.hour >= FLAT_UTC_HOUR:
            continue  # don't open into the weekend
        if ah_set and t.hour in ah_set:
            continue

        adx_val = adx_arr[i]
        if adx_val < adx_min:
            continue
        if adx_rising and adx_val <= adx_arr[i - 1]:
            continue
        if atr_ratio > 0 and not np.isnan(atr_ma[i]) and atr_ma[i] > 0:
            if atr_arr[i] < atr_ratio * atr_ma[i]:
                continue

        di_plus_pers  = all(di_plus[i - j]  > di for j in range(persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i])
        if not (is_buy or is_sell):
            continue

        if di_spread_min > 0:
            if is_buy  and (di_plus[i]  - di_minus[i]) < di_spread_min: continue
            if is_sell and (di_minus[i] - di_plus[i])  < di_spread_min: continue

        # live detector compares iloc[-1] > iloc[-3]
        if di_slope:
            if is_buy  and di_plus[i]  <= di_plus[i - 2]:  continue
            if is_sell and di_minus[i] <= di_minus[i - 2]: continue

        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        atr_val = atr_arr[i]
        if is_buy:
            sl_p = c - max(c - prev_low, atr_val) - spread
            risk = c - sl_p
            if risk <= 0: continue
            direction, sl, tp = "BUY", sl_p, c + risk * rr
        else:
            sl_p = c + max(prev_high - c, atr_val) + spread
            risk = sl_p - c
            if risk <= 0: continue
            direction, sl, tp = "SELL", sl_p, c - risk * rr

        entry_price = c
        in_trade = True

    if len(trades) < MIN_TRADES:
        return None
    return pd.DataFrame(trades)


def metrics(df_t: pd.DataFrame) -> dict:
    n = len(df_t)
    wr = (df_t["r"] > 0).mean() * 100
    roi = df_t["pnl"].sum() / INITIAL_BALANCE * 100
    rets = df_t["pnl"] / INITIAL_BALANCE
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    eq = df_t["balance"].values
    peak = np.maximum.accumulate(eq)
    max_dd = float(((eq - peak) / peak * 100).min())
    return {
        "trades": n,
        "win_rate": round(wr, 1),
        "roi": round(roi, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "expectancy_R": round(df_t["r"].mean(), 3),
    }


if __name__ == "__main__":
    rows = []
    for label, cfg in PAIRS.items():
        try:
            df = load_and_prep(cfg["symbol"], cfg["timeframe"])
        except Exception as e:
            print(f"{label}: load error {e}")
            continue

        mid = df.index[len(df) // 2]
        print(f"\n{'='*94}")
        print(f"  {label}   bars={len(df)}   {df.index[0].date()} → {df.index[-1].date()}"
              f"   (split at {mid.date()})")
        print(f"{'='*94}")
        print(f"  {'mode':<9}{'RR':>5}{'n':>6}{'WR%':>7}{'ROI%':>9}{'Sharpe':>8}"
              f"{'MaxDD%':>9}{'ExpR':>7}   {'OOS-1st':>9}{'OOS-2nd':>9}")
        print("  " + "-" * 90)

        for weekend_flat in (False, True):
            mode = "wknd-flat" if weekend_flat else "baseline"
            for rr in RR_GRID:
                t = run_backtest(df, rr, cfg, weekend_flat)
                if t is None:
                    continue
                m = metrics(t)

                # split-half out-of-sample: expectancy in R on each half
                h1 = t[t["date"] <= mid]
                h2 = t[t["date"] > mid]
                e1 = round(h1["r"].mean(), 2) if len(h1) >= 10 else float("nan")
                e2 = round(h2["r"].mean(), 2) if len(h2) >= 10 else float("nan")

                rows.append({"pair": label, "mode": mode, "rr": rr, **m,
                             "exp_R_half1": e1, "exp_R_half2": e2,
                             "n_half1": len(h1), "n_half2": len(h2)})
                print(f"  {mode:<9}{rr:>5.1f}{m['trades']:>6}{m['win_rate']:>7.1f}"
                      f"{m['roi']:>9.2f}{m['sharpe']:>8.2f}{m['max_dd']:>9.2f}"
                      f"{m['expectancy_R']:>7.2f}   {e1:>9.2f}{e2:>9.2f}")

    out = pd.DataFrame(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_FILE, index=False)
    print(f"\nSaved {len(out)} rows → {OUT_FILE}")
