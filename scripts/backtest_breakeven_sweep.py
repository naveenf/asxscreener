"""
Breakeven-stage sweep across all 8 active pairs.

Question: does adding an early "move SL to ~breakeven" stage generalise beyond
XAG, or is it a XAG-specific artifact? Tested on top of each pair's CURRENT
production config and current live lock, so a positive result is directly
actionable and a negative one rules the pair out.

Stop ladder per trade:
  stage 0  SL at -1R                      (original)
  stage 1  price reaches be_trigger  -> SL moves to be_level  (near breakeven;
           be_level may be slightly negative, which is more noise-resistant
           than an exact-entry stop while still far better than -1R)
  stage 2  price reaches lock_trigger -> SL moves to +lock_r  (existing live
           mechanism; only XAG_USD and BCO_USD have one today)

Arming is evaluated AFTER exits each candle, so a spike-and-reverse inside one
bar cannot retroactively rescue a trade. Ties within a bar resolve to the
worse outcome.

Output: data/backtest_breakeven_sweep.csv
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
from backtest_lock_sweep_v2 import load_configs, load_and_prep, INITIAL_BALANCE

MIN_TRADES = 10

# Locks currently live in PAIR_LOCK_CONFIGS (tasks.py). None for the rest.
LIVE_LOCKS = {
    "XAG_USD": (3.0, 2.0, 5),     # trigger_r, lock_r, cooldown candles
    "BCO_USD": (2.0, 1.0, 6),
}

BE_TRIGGERS = [0.25, 0.5, 0.75, 1.0, 1.5]
BE_LEVELS   = [-0.3, -0.2, -0.1, 0.0]


def run(df, cfg, rr, be_trig=None, be_level=0.0,
        lock_trig=None, lock_r=None, cooldown=0):
    risk_pct = cfg["risk_pct"]; spread = cfg["spread"]
    di = cfg["di"]; persist = cfg["persist"]; adx_min = cfg["adx_min"]
    adx_rising = cfg["adx_rising"]; atr_ratio = cfg["atr_ratio"]
    di_slope = cfg["di_slope"]; di_spread = cfg["di_spread"]
    avoid = cfg["avoid_hours"]

    C = df["Close"].values; H = df["High"].values; L = df["Low"].values
    s20 = df["SMA20"].values; s50 = df["SMA50"].values; s100 = df["SMA100"].values
    dp = df["DIPlus"].values; dm = df["DIMinus"].values
    adx = df["ADX"].values; atr = df["ATR"].values
    idx = df.index
    aavg = pd.Series(atr).rolling(20).mean().values if atr_ratio > 0 else atr

    bal = INITIAL_BALANCE; trades = []; intr = False; stage = 0
    sl = tp = entry = risk = dirn = be_px = lk_px = None
    mfe = 0.0; block = -1
    start = max(3, persist, 21 if atr_ratio > 0 else 3)

    for i in range(start, len(df)):
        c, h, l = C[i], H[i], L[i]

        if intr:
            fav = (h - entry) / risk if dirn == "BUY" else (entry - l) / risk
            mfe = max(mfe, fav)
            lvl = {0: -1.0, 1: be_level, 2: lock_r}[stage]
            ex = None
            if dirn == "BUY":
                if l <= sl:   ex = lvl
                elif h >= tp: ex = rr
            else:
                if h >= sl:   ex = lvl
                elif l <= tp: ex = rr

            if ex is not None:
                pnl = bal * risk_pct * ex; bal += pnl
                trades.append({"r": ex, "pnl": pnl, "balance": bal,
                               "ts": idx[i], "mfe": mfe, "stage": stage})
                if stage == 2 and cooldown > 0:
                    block = i + cooldown
                intr = False; stage = 0; mfe = 0.0
                continue

            if lock_trig is not None and stage < 2:
                if (h >= lk_px) if dirn == "BUY" else (l <= lk_px):
                    stage = 2
                    sl = (entry + lock_r * risk) if dirn == "BUY" else (entry - lock_r * risk)
                    continue
            if be_trig is not None and stage == 0:
                if (h >= be_px) if dirn == "BUY" else (l <= be_px):
                    stage = 1
                    sl = (entry + be_level * risk) if dirn == "BUY" else (entry - be_level * risk)
            continue

        if i < block: continue
        if avoid and idx[i].hour in avoid: continue

        dpp = all(dp[i - j] > di for j in range(persist))
        dmp = all(dm[i - j] > di for j in range(persist))
        aok = adx[i] >= adx_min
        if adx_rising: aok = aok and adx[i] > adx[i - 1]
        tok = (atr[i] >= atr_ratio * aavg[i]) if (atr_ratio > 0 and aavg[i] > 0) else True
        sb = (dp[i] > dp[i - 2]) if di_slope else True
        ss = (dm[i] > dm[i - 2]) if di_slope else True
        pb = ((dp[i] - dm[i]) >= di_spread) if di_spread > 0 else True
        ps = ((dm[i] - dp[i]) >= di_spread) if di_spread > 0 else True

        buy = (c > s20[i] and c > s50[i] and c > s100[i] and dpp
               and dp[i] > dm[i] and aok and tok and sb and pb)
        sell = (c < s20[i] and c < s50[i] and c < s100[i] and dmp
                and dm[i] > dp[i] and aok and tok and ss and ps)
        if not (buy or sell): continue

        pl = min(L[i - 2], L[i - 1]); ph = max(H[i - 2], H[i - 1])
        if buy and c < pl: continue
        if sell and c > ph: continue

        a = atr[i]
        if buy:
            sd = max(c - pl, a); slp = c - sd - spread; risk = c - slp
            if risk <= 0: continue
            dirn, entry, sl, tp = "BUY", c, slp, c + risk * rr
            be_px = c + risk * be_trig if be_trig is not None else None
            lk_px = c + risk * lock_trig if lock_trig is not None else None
        else:
            sd = max(ph - c, a); slp = c + sd + spread; risk = slp - c
            if risk <= 0: continue
            dirn, entry, sl, tp = "SELL", c, slp, c - risk * rr
            be_px = c - risk * be_trig if be_trig is not None else None
            lk_px = c - risk * lock_trig if lock_trig is not None else None
        intr = True; stage = 0; mfe = 0.0

    return trades


def stats(t, rr, lock_r):
    if len(t) < MIN_TRADES: return None
    d = pd.DataFrame(t); n = len(d)
    r = d["pnl"] / INITIAL_BALANCE
    eq = d["balance"].values; pk = np.maximum.accumulate(eq)
    is_tp = d["r"] >= rr * 0.99
    is_lock = (d["stage"] == 2) & ~is_tp
    is_be = d["stage"] == 1
    is_full = d["stage"] == 0
    return {
        "trades": n,
        "win_rate": round(100 * (d.r > 0).mean(), 1),
        "roi": round(d.pnl.sum() / INITIAL_BALANCE * 100, 2),
        "sharpe": round(float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0.0, 2),
        "max_dd": round(float(((eq - pk) / pk * 100).min()), 2),
        "avg_r": round(d.r.mean(), 3),
        "pct_tp": round(100 * is_tp.sum() / n, 1),
        "pct_lock": round(100 * is_lock.sum() / n, 1),
        "pct_be": round(100 * is_be.sum() / n, 1),
        "pct_fullloss": round(100 * is_full.sum() / n, 1),
        "giveback_3R": int(((d.mfe >= 3) & (d.r <= 0)).sum()),
    }


def monthly(t):
    d = pd.DataFrame(t)
    d["m"] = d["ts"].dt.to_period("M").astype(str)
    return {m: g["pnl"].sum() / INITIAL_BALANCE * 100 for m, g in d.groupby("m")}


def main():
    cfgs = load_configs()
    rows = []
    summary = []

    for sym, cfg in cfgs.items():
        df = load_and_prep(sym, cfg["timeframe"])
        rr = cfg["rr"]
        lt, lr, cd = LIVE_LOCKS.get(sym, (None, None, 0))

        base_t = run(df, cfg, rr, None, 0.0, lt, lr, cd)
        base = stats(base_t, rr, lr)
        if base is None:
            print(f"{sym}: baseline <{MIN_TRADES} trades, skipped")
            continue
        mb_base = monthly(base_t)

        print("=" * 112)
        print(f"{sym}  ({cfg['timeframe']}, RR={rr}, lock="
              f"{'none' if lt is None else f'{lt}R->+{lr}R cd{cd}'})   "
              f"{df.index[0].date()} -> {df.index[-1].date()}")
        print("=" * 112)
        print(f"  {'BEtrig':>7} {'BElvl':>6} {'n':>4} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} "
              f"{'MaxDD%':>8} {'AvgR':>7} {'%TP':>6} {'%lock':>6} {'%BE':>6} {'%-1R':>6} "
              f"{'give3R':>7} {'dSharpe':>8} {'dROI':>8}")
        print("  " + "-" * 108)
        print(f"  {'none':>7} {'':>6} {base['trades']:>4} {base['win_rate']:>5.1f}% "
              f"{base['roi']:>+7.2f}% {base['sharpe']:>7.2f} {base['max_dd']:>7.2f}% "
              f"{base['avg_r']:>7.3f} {base['pct_tp']:>5.1f}% {base['pct_lock']:>5.1f}% "
              f"{base['pct_be']:>5.1f}% {base['pct_fullloss']:>5.1f}% {base['giveback_3R']:>7} "
              f"{'—':>8} {'—':>8}")

        best = None
        for bt in BE_TRIGGERS:
            for bl in BE_LEVELS:
                t = run(df, cfg, rr, bt, bl, lt, lr, cd)
                s = stats(t, rr, lr)
                if s is None: continue
                d_sh = round(s["sharpe"] - base["sharpe"], 2)
                d_roi = round(s["roi"] - base["roi"], 2)
                rows.append({"symbol": sym, "tf": cfg["timeframe"], "rr": rr,
                             "be_trigger": bt, "be_level": bl,
                             "lock": f"{lt}->{lr}" if lt else "none",
                             **s, "d_sharpe": d_sh, "d_roi": d_roi,
                             "base_sharpe": base["sharpe"], "base_roi": base["roi"]})
                print(f"  {bt:>7.2f} {bl:>6.2f} {s['trades']:>4} {s['win_rate']:>5.1f}% "
                      f"{s['roi']:>+7.2f}% {s['sharpe']:>7.2f} {s['max_dd']:>7.2f}% "
                      f"{s['avg_r']:>7.3f} {s['pct_tp']:>5.1f}% {s['pct_lock']:>5.1f}% "
                      f"{s['pct_be']:>5.1f}% {s['pct_fullloss']:>5.1f}% {s['giveback_3R']:>7} "
                      f"{d_sh:>+8.2f} {d_roi:>+7.2f}%")
                if best is None or s["sharpe"] > best[0]["sharpe"]:
                    best = (s, bt, bl, t)
            print()

        if best:
            s, bt, bl, t = best
            mb = monthly(t)
            months = sorted(set(mb_base) | set(mb))
            nb = sum(mb.get(m, 0) > mb_base.get(m, 0) for m in months)
            summary.append({
                "symbol": sym, "base_sharpe": base["sharpe"], "base_roi": base["roi"],
                "base_dd": base["max_dd"], "base_loss": base["pct_fullloss"],
                "be_trigger": bt, "be_level": bl,
                "sharpe": s["sharpe"], "roi": s["roi"], "dd": s["max_dd"],
                "loss": s["pct_fullloss"], "months_better": f"{nb}/{len(months)}",
                "d_sharpe": round(s["sharpe"] - base["sharpe"], 2),
                "d_roi": round(s["roi"] - base["roi"], 2),
            })

    pd.DataFrame(rows).to_csv("data/backtest_breakeven_sweep.csv", index=False)

    print("=" * 112)
    print("SUMMARY — best BE config per pair (by Sharpe) vs current production")
    print("=" * 112)
    print(f"  {'Pair':<12} {'BEtrig':>7} {'BElvl':>6} | {'Sharpe':>15} | {'ROI%':>17} | "
          f"{'MaxDD%':>15} | {'%-1R losses':>16} | {'mths':>6}")
    print("  " + "-" * 108)
    for s in summary:
        print(f"  {s['symbol']:<12} {s['be_trigger']:>7.2f} {s['be_level']:>6.2f} | "
              f"{s['base_sharpe']:>6.2f} -> {s['sharpe']:>5.2f} | "
              f"{s['base_roi']:>+7.2f}% -> {s['roi']:>+6.2f}% | "
              f"{s['base_dd']:>6.2f} -> {s['dd']:>6.2f} | "
              f"{s['base_loss']:>6.1f}% -> {s['loss']:>6.1f}% | {s['months_better']:>6}")
    print()
    print("  %-1R losses = share of trades stopped at the full original -1R stop")
    print("  Saved: data/backtest_breakeven_sweep.csv")


if __name__ == "__main__":
    main()
