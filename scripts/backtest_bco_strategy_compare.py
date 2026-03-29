"""
BCO/USD Strategy Comparison Backtest
=====================================
Tests three strategies across timeframes to find the best fit for Brent Crude Oil:

  1. SMA Scalping  — 5m  (⚠️  short history: Jan 14 2026+)
  2. SMA Scalping  — 15m (Oct 2025+, ~5 months)
  3. PVT Scalping  — 1H  (Feb 2025+, ~13 months)

For each strategy a parameter grid is swept; the top 5 configs by Sharpe are shown.
Best overall config per strategy is saved to: data/backtest_bco_strategy_compare.csv

BCO spread: ~$0.04
"""

import sys
import itertools
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

# ---------------------------------------------------------------------------
DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_bco_strategy_compare.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
BCO_SPREAD      = 0.04   # ~$0.04 typical for Brent on Oanda
TF_SUFFIX       = {"5m": "5_Min", "15m": "15_Min", "1h": "1_Hour"}


# ---------------------------------------------------------------------------
# Data loader
# ---------------------------------------------------------------------------

def load_df(tf: str) -> pd.DataFrame:
    suffix = TF_SUFFIX[tf]
    csv = DATA_DIR / f"BCO_USD_{suffix}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def load_df_pvt(tf: str = "1h") -> pd.DataFrame:
    """Load and add PVT-specific indicators."""
    suffix = TF_SUFFIX[tf]
    csv = DATA_DIR / f"BCO_USD_{suffix}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    # EMA50, SMA100
    df["EMA50"]  = df["Close"].ewm(span=50, adjust=False).mean()
    df["SMA100"] = df["Close"].rolling(100).mean()
    # PVT
    df = TechnicalIndicators.calculate_pvt(df)
    df.dropna(subset=["EMA50", "SMA100", "RSI", "PVT", "ATR"], inplace=True)
    return df


# ---------------------------------------------------------------------------
# SMA Scalping backtest
# ---------------------------------------------------------------------------

def _close(balance: float, rr: float, win: bool) -> dict:
    pnl = balance * RISK_PCT * (rr if win else -1.0)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": balance + pnl}


def run_sma_backtest(df: pd.DataFrame, rr: float, di: float, adx_min: float,
                     spread: float, di_persist: int,
                     atr_ratio: float = 0.0, avoid_hours: list = None,
                     adx_rising: bool = False, di_slope: bool = False) -> dict | None:
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
    times    = df.index

    # ATR 20-bar rolling average for atr_ratio filter
    atr_ma20 = pd.Series(atr_arr).rolling(20).mean().values

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(max(3, di_persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]
        hour = times[i].hour

        # --- Exit ---
        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            continue

        # --- Time filter ---
        if avoid_hours and hour in avoid_hours:
            continue

        # --- Entry filters ---
        adx_val = adx_arr[i]
        adx_ok  = adx_val >= adx_min

        # ADX rising
        if adx_rising and i > 0 and adx_arr[i] <= adx_arr[i - 1]:
            adx_ok = False

        # ATR ratio
        if atr_ratio > 0 and not np.isnan(atr_ma20[i]) and atr_ma20[i] > 0:
            if atr_arr[i] < atr_ratio * atr_ma20[i]:
                continue

        di_plus_pers  = all(di_plus[i - j]  > di for j in range(di_persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(di_persist))

        # DI slope
        if di_slope and i > 0:
            di_plus_rising  = di_plus[i]  > di_plus[i - 1]
            di_minus_rising = di_minus[i] > di_minus[i - 1]
        else:
            di_plus_rising = di_minus_rising = True

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i]
                   and adx_ok and di_plus_rising)
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i]
                   and adx_ok and di_minus_rising)

        if not (is_buy or is_sell):
            continue

        # Structural validity
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # ATR floor SL
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

    if len(trades) < 8:
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
    return {"trades": n, "win_rate": round(wr, 1), "roi": round(roi, 2),
            "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


# ---------------------------------------------------------------------------
# PVT Scalping backtest (1H)
# ---------------------------------------------------------------------------

def run_pvt_backtest(df: pd.DataFrame, rr: float, spread: float,
                     pvt_threshold: float = 0.05,
                     pvt_consec: int = 1,
                     avoid_hours: list = None) -> dict | None:
    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    ema50    = df["EMA50"].values
    sma100   = df["SMA100"].values
    rsi_arr  = df["RSI"].values
    pvt_arr  = df["PVT"].values
    atr_arr  = df["ATR"].values
    times    = df.index

    # Daily SMA200 — forward-filled from daily resampled series
    df_daily = df.resample("D").agg({"Close": "last"}).dropna()
    df_daily["SMA200"] = df_daily["Close"].rolling(200).mean()
    sma200_daily = df_daily["SMA200"].reindex(df.index, method="ffill")

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    min_history = max(pvt_consec, 2)

    for i in range(min_history, len(df)):
        c, h, l = closes[i], highs[i], lows[i]
        hour = times[i].hour

        # --- Exit ---
        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            continue

        # --- Time filter ---
        if avoid_hours and hour in avoid_hours:
            continue

        # --- Daily SMA200 trend ---
        sma200_val = sma200_daily.iloc[i]
        if np.isnan(sma200_val):
            continue

        # --- PVT consecutive ---
        pvt_buy_consec  = all(pvt_arr[i - j] >  pvt_threshold for j in range(pvt_consec))
        pvt_sell_consec = all(pvt_arr[i - j] < -pvt_threshold for j in range(pvt_consec))

        # --- Full entry conditions ---
        is_buy = (c > ema50[i] and c > sma100[i]
                  and rsi_arr[i] > 20
                  and pvt_buy_consec
                  and c > sma200_val)

        is_sell = (c < ema50[i] and c < sma100[i]
                   and rsi_arr[i] < 80
                   and pvt_sell_consec
                   and c < sma200_val)

        if not (is_buy or is_sell):
            continue

        # ATR-based SL
        atr_val   = atr_arr[i]
        min_sl    = c * 0.002
        sl_dist   = max(atr_val + spread, min_sl)

        if is_buy:
            sl_p = c - sl_dist
            risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * rr
        else:
            sl_p = c + sl_dist
            risk = sl_p - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_p;  tp = c - risk * rr

        in_trade = True

    if len(trades) < 8:
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
    return {"trades": n, "win_rate": round(wr, 1), "roi": round(roi, 2),
            "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


# ---------------------------------------------------------------------------
# Sweep helpers
# ---------------------------------------------------------------------------

def sweep_sma(df: pd.DataFrame, tf: str, label: str) -> list:
    results = []
    grid = list(itertools.product(
        [25.0, 30.0, 35.0],          # DI threshold
        [3.0, 4.0, 5.0, 6.0, 8.0],   # RR
        [1, 2],                       # di_persist
        [0.0, 15.0, 20.0],            # adx_min
        [False, True],                # adx_rising
        [False, True],                # di_slope
    ))
    for (di, rr, persist, adx_min, adx_rising, di_slope) in grid:
        r = run_sma_backtest(df, rr=rr, di=di, adx_min=adx_min,
                              spread=BCO_SPREAD, di_persist=persist,
                              adx_rising=adx_rising, di_slope=di_slope)
        if r:
            results.append({
                "strategy": "SmaScalping", "tf": tf, "label": label,
                "di": di, "rr": rr, "persist": persist,
                "adx_min": adx_min, "adx_rising": adx_rising, "di_slope": di_slope,
                **r
            })
    return results


def sweep_pvt(df: pd.DataFrame) -> list:
    results = []
    grid = list(itertools.product(
        [1.5, 2.0, 2.5, 3.0, 3.5],   # RR
        [0.01, 0.05, 0.10],           # pvt_threshold
        [1, 2, 3],                    # pvt_consec
    ))
    for (rr, pvt_thresh, pvt_consec) in grid:
        r = run_pvt_backtest(df, rr=rr, spread=BCO_SPREAD,
                             pvt_threshold=pvt_thresh, pvt_consec=pvt_consec)
        if r:
            results.append({
                "strategy": "PVTScalping", "tf": "1h", "label": "1H (Feb 2025+)",
                "rr": rr, "pvt_threshold": pvt_thresh, "pvt_consec": pvt_consec,
                **r
            })
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\nBCO/USD Strategy Comparison Backtest")
    print("=" * 80)

    all_results = []

    # ── SMA Scalping 5m ──────────────────────────────────────────────────────
    print("\n[1/3] SMA Scalping 5m  ⚠️  short history (Jan 14 2026+)...")
    try:
        df5 = load_df("5m")
        period5 = f"{df5.index[0].date()} → {df5.index[-1].date()}"
        label5  = f"5m ({period5})"
        res5 = sweep_sma(df5, "5m", label5)
        all_results.extend(res5)
        if res5:
            top5 = sorted(res5, key=lambda x: x["sharpe"], reverse=True)[:5]
            print(f"   Period: {period5}  |  configs tested: {len(res5)}")
            print(f"   {'DI':>4} {'RR':>5} {'p':>2} {'adx':>4} {'rise':>5} {'slope':>6} "
                  f"{'n':>5} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
            print("   " + "-" * 60)
            for r in top5:
                print(f"   {r['di']:>4.0f} {r['rr']:>5.1f} {r['persist']:>2} {r['adx_min']:>4.0f} "
                      f"{'Y' if r['adx_rising'] else 'N':>5} {'Y' if r['di_slope'] else 'N':>6} "
                      f"{r['trades']:>5} {r['win_rate']:>6.1f}% {r['roi']:>7.2f}%  "
                      f"{r['sharpe']:>6.2f}  {r['max_dd']:>7.2f}%")
        else:
            print("   No valid configs (insufficient trades).")
    except Exception as e:
        print(f"   ERROR: {e}")

    # ── SMA Scalping 15m ─────────────────────────────────────────────────────
    print("\n[2/3] SMA Scalping 15m...")
    try:
        df15 = load_df("15m")
        period15 = f"{df15.index[0].date()} → {df15.index[-1].date()}"
        label15  = f"15m ({period15})"
        res15 = sweep_sma(df15, "15m", label15)
        all_results.extend(res15)
        if res15:
            top15 = sorted(res15, key=lambda x: x["sharpe"], reverse=True)[:5]
            print(f"   Period: {period15}  |  configs tested: {len(res15)}")
            print(f"   {'DI':>4} {'RR':>5} {'p':>2} {'adx':>4} {'rise':>5} {'slope':>6} "
                  f"{'n':>5} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
            print("   " + "-" * 60)
            for r in top15:
                print(f"   {r['di']:>4.0f} {r['rr']:>5.1f} {r['persist']:>2} {r['adx_min']:>4.0f} "
                      f"{'Y' if r['adx_rising'] else 'N':>5} {'Y' if r['di_slope'] else 'N':>6} "
                      f"{r['trades']:>5} {r['win_rate']:>6.1f}% {r['roi']:>7.2f}%  "
                      f"{r['sharpe']:>6.2f}  {r['max_dd']:>7.2f}%")
        else:
            print("   No valid configs (insufficient trades).")
    except Exception as e:
        print(f"   ERROR: {e}")

    # ── PVT Scalping 1H ──────────────────────────────────────────────────────
    print("\n[3/3] PVT Scalping 1H...")
    try:
        df1h = load_df_pvt("1h")
        period1h = f"{df1h.index[0].date()} → {df1h.index[-1].date()}"
        res1h = sweep_pvt(df1h)
        all_results.extend(res1h)
        if res1h:
            top1h = sorted(res1h, key=lambda x: x["sharpe"], reverse=True)[:5]
            print(f"   Period: {period1h}  |  configs tested: {len(res1h)}")
            print(f"   {'RR':>5} {'pvt_thr':>8} {'consec':>7} "
                  f"{'n':>5} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
            print("   " + "-" * 56)
            for r in top1h:
                print(f"   {r['rr']:>5.1f} {r['pvt_threshold']:>8.2f} {r['pvt_consec']:>7} "
                      f"{r['trades']:>5} {r['win_rate']:>6.1f}% {r['roi']:>7.2f}%  "
                      f"{r['sharpe']:>6.2f}  {r['max_dd']:>7.2f}%")
        else:
            print("   No valid configs (insufficient trades).")
    except Exception as e:
        print(f"   ERROR: {e}")

    # ── Summary: best per strategy ───────────────────────────────────────────
    print("\n" + "=" * 80)
    print("BEST CONFIG PER STRATEGY  (by Sharpe)")
    print("=" * 80)
    print(f"  {'Strategy':<20} {'TF':<5} {'RR':>5} {'Trades':>7} {'WR%':>6} "
          f"{'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
    print("  " + "-" * 68)

    rows_out = []
    for strat_tf, label_fmt in [("SmaScalping_5m", "SmaScalping 5m"),
                                 ("SmaScalping_15m", "SmaScalping 15m"),
                                 ("PVTScalping_1h", "PVTScalping 1H")]:
        strat, tf = strat_tf.split("_")
        subset = [r for r in all_results if r["strategy"] == strat and r["tf"] == tf]
        if not subset:
            print(f"  {label_fmt:<20} — no valid configs")
            continue
        best = max(subset, key=lambda x: x["sharpe"])
        rr   = best["rr"]
        print(f"  {label_fmt:<20} {tf:<5} {rr:>5.1f} {best['trades']:>7} {best['win_rate']:>6.1f}% "
              f"{best['roi']:>7.2f}%  {best['sharpe']:>6.2f}  {best['max_dd']:>7.2f}%")
        rows_out.append(best)

    # Save full results
    if all_results:
        pd.DataFrame(all_results).sort_values("sharpe", ascending=False).to_csv(OUT_FILE, index=False)
        print(f"\nFull results saved → {OUT_FILE}")
