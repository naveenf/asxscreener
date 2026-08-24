"""
Weekend Gap Impact — All Active Pairs
======================================
Every backtest in this repo books a stopped-out trade at exactly -1R, because
it tests bar high/low against the SL price. A weekend gap opens *past* the stop,
so the real fill is worse — sometimes far worse. That makes every "hold over the
weekend" result in data/ optimistic by an unmeasured amount.

Measured gap sizes (Fri close -> Sun open, in ATR units; SL floor is 1xATR):
    BCO 2.73 median / 61% of weekends >2 ATR   ... down to USD_JPY 1.23 / 31%
Every active pair gaps more than 1 ATR on the median weekend.

This script runs each pair's production config three ways:
  1. naive     — stops always fill at -1R (what the existing scripts assume)
  2. gap-real  — stops that gap through fill at the actual open price
  3. flat      — positions closed Friday >=19:00 UTC, and no new entries after
                 that (19:00 UTC gives a 2h buffer in EDT, 3h in EST, so the
                 rule needs no DST handling)

Compare (2) vs (3) — that is the honest question. Comparing against (1) just
measures the bug.

Output: data/backtest_weekend_gap_impact.csv
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_weekend_gap_impact.csv")
INITIAL_BALANCE = 10_000.0
FLAT_UTC_HOUR   = 19   # Friday cutoff; 2h buffer in EDT, 3h in EST

# Production configs (best_strategies.json, Aug 2026)
PAIRS = {
    "XAU_USD": dict(timeframe="15m", rr=3.5, risk_pct=0.015, spread=0.30,
                    di=35.0, persist=2, adx_min=0.0, adx_rising=True,
                    atr_ratio=0.0, di_slope=False, di_spread_min=0.0, avoid_hours=[8, 9]),
    "XAG_USD": dict(timeframe="5m", rr=12.0, risk_pct=0.01, spread=0.003,
                    di=35.0, persist=1, adx_min=0.0, adx_rising=False,
                    atr_ratio=1.2, di_slope=True, di_spread_min=0.0, avoid_hours=[14, 15, 16]),
    "BCO_USD": dict(timeframe="15m", rr=5.0, risk_pct=0.01, spread=0.03,
                    di=30.0, persist=1, adx_min=15.0, adx_rising=False,
                    atr_ratio=1.0, di_slope=False, di_spread_min=0.0, avoid_hours=[20, 21, 22, 23]),
    "JP225_USD": dict(timeframe="5m", rr=1.5, risk_pct=0.01, spread=3.0,
                      di=30.0, persist=2, adx_min=20.0, adx_rising=True,
                      atr_ratio=1.2, di_slope=True, di_spread_min=15.0, avoid_hours=[21, 22, 23]),
    "NAS100_USD": dict(timeframe="15m", rr=3.5, risk_pct=0.01, spread=1.5,
                       di=35.0, persist=2, adx_min=30.0, adx_rising=False,
                       atr_ratio=1.2, di_slope=True, di_spread_min=0.0,
                       avoid_hours=[7, 8, 20, 21, 22, 23]),
    "UK100_GBP": dict(timeframe="15m", rr=3.5, risk_pct=0.01, spread=0.80,
                      di=35.0, persist=2, adx_min=0.0, adx_rising=False,
                      atr_ratio=1.2, di_slope=False, di_spread_min=0.0,
                      avoid_hours=[15, 16, 17, 18, 19]),
    "EUR_USD": dict(timeframe="15m", rr=6.0, risk_pct=0.01, spread=0.0001,
                    di=25.0, persist=2, adx_min=0.0, adx_rising=False,
                    atr_ratio=1.0, di_slope=False, di_spread_min=0.0,
                    avoid_hours=[20, 21, 22, 23]),
    "USD_JPY": dict(timeframe="15m", rr=3.0, risk_pct=0.005, spread=0.02,
                    di=30.0, persist=1, adx_min=0.0, adx_rising=False,
                    atr_ratio=0.0, di_slope=False, di_spread_min=0.0,
                    avoid_hours=[15, 16, 17, 18, 19, 20, 21]),
}


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


def run(df, cfg, gap_real, weekend_flat):
    c, h, l, o = (df[x].values for x in ("Close", "High", "Low", "Open"))
    s20, s50, s100 = (df[x].values for x in ("SMA20", "SMA50", "SMA100"))
    dp, dm = df["DIPlus"].values, df["DIMinus"].values
    adx, atr, atrma = df["ADX"].values, df["ATR"].values, df["ATR_avg20"].values
    T, dow, hour = df.index, df.index.dayofweek.values, df.index.hour.values
    # a bar preceded by a >6h break is the first bar after the weekend
    is_gap_bar = (df.index.to_series().diff() > pd.Timedelta(hours=6)).values

    rr, risk_pct, spread = cfg["rr"], cfg["risk_pct"], cfg["spread"]
    di, persist, ah = cfg["di"], cfg["persist"], set(cfg["avoid_hours"])

    bal, trades = INITIAL_BALANCE, []
    in_trade = False
    sl = tp = entry = direction = None

    def close(r_mult, when):
        nonlocal bal, in_trade
        pnl = bal * risk_pct * r_mult
        bal += pnl
        trades.append({"date": when, "r": r_mult, "pnl": pnl, "balance": bal})
        in_trade = False

    for i in range(max(3, persist), len(df)):
        flat_now = weekend_flat and dow[i] == 4 and hour[i] >= FLAT_UTC_HOUR

        if in_trade:
            risk_dist = abs(entry - sl)
            hit_sl = (l[i] <= sl) if direction == "BUY" else (h[i] >= sl)
            hit_tp = (h[i] >= tp) if direction == "BUY" else (l[i] <= tp)
            if hit_sl:
                fill = sl
                if gap_real and is_gap_bar[i]:
                    gapped = o[i] < sl if direction == "BUY" else o[i] > sl
                    if gapped:
                        fill = o[i]
                r = (fill - entry) / risk_dist if direction == "BUY" else (entry - fill) / risk_dist
                close(float(r), T[i])
            elif hit_tp:
                close(rr, T[i])
            elif flat_now:
                r = (c[i] - entry) / risk_dist if direction == "BUY" else (entry - c[i]) / risk_dist
                close(float(r), T[i])
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

        if cfg["di_spread_min"] > 0:
            if is_buy and (dp[i] - dm[i]) < cfg["di_spread_min"]:
                continue
            if is_sell and (dm[i] - dp[i]) < cfg["di_spread_min"]:
                continue
        if cfg["di_slope"]:                      # live detector: iloc[-1] > iloc[-3]
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
            sl_p = c[i] - max(c[i] - prev_low, atr[i]) - spread
            risk = c[i] - sl_p
            if risk <= 0:
                continue
            direction, sl, tp = "BUY", sl_p, c[i] + risk * rr
        else:
            sl_p = c[i] + max(prev_high - c[i], atr[i]) + spread
            risk = sl_p - c[i]
            if risk <= 0:
                continue
            direction, sl, tp = "SELL", sl_p, c[i] - risk * rr
        entry, in_trade = c[i], True

    if len(trades) < 15:
        return None
    t = pd.DataFrame(trades)
    rets = t["pnl"] / INITIAL_BALANCE
    eq = t["balance"].values
    peak = np.maximum.accumulate(eq)
    months = t.assign(M=pd.to_datetime(t["date"]).dt.to_period("M")).groupby("M")["r"].mean()
    return {
        "trades": len(t),
        "win_rate": round((t["r"] > 0).mean() * 100, 1),
        "roi": round(t["pnl"].sum() / INITIAL_BALANCE * 100, 2),
        "sharpe": round(float(rets.mean() / rets.std() * np.sqrt(252)), 2),
        "max_dd": round(float(((eq - peak) / peak * 100).min()), 2),
        "worst_R": round(float(t["r"].min()), 2),
        "months_pos": f"{int((months > 0).sum())}/{len(months)}",
    }


if __name__ == "__main__":
    rows = []
    hdr = (f"{'pair':<11}{'scenario':<26}{'n':>5}{'WR%':>7}{'ROI%':>8}"
           f"{'Sharpe':>8}{'MaxDD%':>9}{'worstR':>8}{'mon+':>7}")
    for symbol, cfg in PAIRS.items():
        try:
            df = load_and_prep(symbol, cfg["timeframe"])
        except Exception as e:
            print(f"{symbol}: load error {e}")
            continue
        print(f"\n{'='*90}\n  {symbol}  {cfg['timeframe']}  RR={cfg['rr']}  "
              f"{df.index[0].date()} → {df.index[-1].date()}\n{'='*90}")
        print(hdr)
        print("-" * 90)
        for label, gap_real, flat in [
            ("1 naive (stops @ -1R)", False, False),
            ("2 gap-priced, hold", True, False),
            ("3 gap-priced, Fri flat", True, True),
        ]:
            m = run(df, cfg, gap_real, flat)
            if m is None:
                continue
            rows.append({"pair": symbol, "scenario": label, **m})
            print(f"{symbol:<11}{label:<26}{m['trades']:>5}{m['win_rate']:>7}"
                  f"{m['roi']:>8}{m['sharpe']:>8}{m['max_dd']:>9}"
                  f"{m['worst_R']:>8}{m['months_pos']:>7}")

    out = pd.DataFrame(rows)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_FILE, index=False)

    print(f"\n{'='*90}\n  SUMMARY — scenario 3 vs 2 (the honest comparison)\n{'='*90}")
    p = out.pivot(index="pair", columns="scenario")
    print(f"{'pair':<12}{'ΔSharpe':>10}{'ΔROI%':>10}{'worstR hold':>14}{'worstR flat':>14}")
    for pair in p.index:
        s2 = p.loc[pair, ("sharpe", "2 gap-priced, hold")]
        s3 = p.loc[pair, ("sharpe", "3 gap-priced, Fri flat")]
        r2 = p.loc[pair, ("roi", "2 gap-priced, hold")]
        r3 = p.loc[pair, ("roi", "3 gap-priced, Fri flat")]
        w2 = p.loc[pair, ("worst_R", "2 gap-priced, hold")]
        w3 = p.loc[pair, ("worst_R", "3 gap-priced, Fri flat")]
        print(f"{pair:<12}{s3-s2:>+10.2f}{r3-r2:>+10.2f}{w2:>14.2f}{w3:>14.2f}")
    print(f"\nSaved {len(out)} rows → {OUT_FILE}")
