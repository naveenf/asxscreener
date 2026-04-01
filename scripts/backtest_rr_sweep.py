"""
SmaScalping — R:R Sweep (All Active Pairs)
===========================================
For each active pair, holds all production filters fixed and sweeps RR
from 1.5 to current_rr (inclusive) in 0.5 steps.

Goal: find the lowest RR where Sharpe stays close to the production value,
for more consistent account growth (more frequent, smaller wins).

Active pairs & current RR:
  XAU_USD   15m  RR=5.0
  XAG_USD    5m  RR=12.0
  JP225_USD  5m  RR=5.0
  NAS100_USD 15m  RR=3.0
  UK100_GBP 15m  RR=6.0
  EUR_USD   15m  RR=6.0
  EUR_AUD   15m  RR=5.0
  USD_JPY    5m  RR=2.5
  BCO_USD   15m  RR=4.0

Output: data/backtest_rr_sweep.csv
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_rr_sweep.csv")
INITIAL_BALANCE = 10_000.0
MIN_TRADES      = 10

# Production configs — all filters held fixed, only RR is swept
PAIRS = {
    "XAU_USD": dict(
        timeframe="15m", current_rr=5.0, risk_pct=0.015, spread=0.30,
        di=35.0, persist=2, adx_min=0.0, adx_rising=True,
        atr_ratio=0.0, di_slope=False, di_spread_min=0.0,
        avoid_hours=[8, 9],
    ),
    "XAG_USD": dict(
        timeframe="5m", current_rr=12.0, risk_pct=0.01, spread=0.003,
        di=35.0, persist=1, adx_min=0.0, adx_rising=False,
        atr_ratio=1.2, di_slope=True, di_spread_min=0.0,
        avoid_hours=[14, 15, 16],
    ),
    "JP225_USD": dict(
        timeframe="5m", current_rr=5.0, risk_pct=0.01, spread=3.0,
        di=30.0, persist=2, adx_min=20.0, adx_rising=True,
        atr_ratio=1.2, di_slope=True, di_spread_min=15.0,
        avoid_hours=[21, 22, 23],
    ),
    "NAS100_USD": dict(
        timeframe="15m", current_rr=3.0, risk_pct=0.01, spread=1.5,
        di=30.0, persist=2, adx_min=25.0, adx_rising=False,
        atr_ratio=1.0, di_slope=True, di_spread_min=0.0,
        avoid_hours=[7, 8, 21, 22, 23],
    ),
    "UK100_GBP": dict(
        timeframe="15m", current_rr=6.0, risk_pct=0.01, spread=0.80,
        di=35.0, persist=2, adx_min=0.0, adx_rising=False,
        atr_ratio=1.2, di_slope=False, di_spread_min=0.0,
        avoid_hours=[15, 16, 17, 18, 19],
    ),
    "EUR_USD": dict(
        timeframe="15m", current_rr=6.0, risk_pct=0.01, spread=0.0001,
        di=25.0, persist=2, adx_min=0.0, adx_rising=False,
        atr_ratio=1.0, di_slope=False, di_spread_min=0.0,
        avoid_hours=[20, 21, 22, 23],
    ),
    "EUR_AUD": dict(
        timeframe="15m", current_rr=5.0, risk_pct=0.01, spread=0.0002,
        di=30.0, persist=1, adx_min=15.0, adx_rising=False,
        atr_ratio=0.0, di_slope=True, di_spread_min=0.0,
        avoid_hours=[7, 8],
    ),
    "USD_JPY": dict(
        timeframe="5m", current_rr=2.5, risk_pct=0.01, spread=0.02,
        di=30.0, persist=1, adx_min=15.0, adx_rising=False,
        atr_ratio=0.0, di_slope=False, di_spread_min=15.0,
        avoid_hours=[15, 16, 17, 18, 19, 20, 21],
    ),
    "BCO_USD": dict(
        timeframe="15m", current_rr=4.0, risk_pct=0.01, spread=0.03,
        di=30.0, persist=1, adx_min=15.0, adx_rising=False,
        atr_ratio=0.0, di_slope=False, di_spread_min=0.0,
        avoid_hours=[],
    ),
}


def load_and_prep(symbol: str, timeframe: str) -> pd.DataFrame:
    tf_str = "15_Min" if timeframe == "15m" else "5_Min"
    csv = DATA_DIR / f"{symbol}_{tf_str}.csv"
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


def run_backtest(df, rr, cfg) -> dict | None:
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

    di         = cfg["di"]
    persist    = cfg["persist"]
    adx_min    = cfg["adx_min"]
    adx_rising = cfg["adx_rising"]
    atr_ratio  = cfg["atr_ratio"]
    di_slope   = cfg["di_slope"]
    di_spread_min = cfg["di_spread_min"]
    spread     = cfg["spread"]
    risk_pct   = cfg["risk_pct"]
    ah_set     = set(cfg["avoid_hours"])

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(max(3, persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # --- Exit ---
        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False, risk_pct)); balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True,  risk_pct)); balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False, risk_pct)); balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True,  risk_pct)); balance = trades[-1]["balance"]; in_trade = False
            continue

        # --- Time filter ---
        if ah_set and times[i].hour in ah_set:
            continue

        # --- ADX floor ---
        adx_val = adx_arr[i]
        if adx_val < adx_min:
            continue

        # --- ADX rising ---
        if adx_rising and i > 0 and adx_val <= adx_arr[i - 1]:
            continue

        # --- ATR ratio ---
        if atr_ratio > 0 and not np.isnan(atr_ma[i]) and atr_ma[i] > 0:
            if atr_arr[i] < atr_ratio * atr_ma[i]:
                continue

        # --- DI persist ---
        di_plus_pers  = all(di_plus[i - j]  > di for j in range(persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i])

        if not (is_buy or is_sell):
            continue

        # --- DI spread min ---
        if di_spread_min > 0:
            if is_buy  and (di_plus[i]  - di_minus[i]) < di_spread_min: continue
            if is_sell and (di_minus[i] - di_plus[i])  < di_spread_min: continue

        # --- DI slope ---
        if di_slope and i > 0:
            if is_buy  and di_plus[i]  <= di_plus[i - 1]:  continue
            if is_sell and di_minus[i] <= di_minus[i - 1]: continue

        # --- Structural validity (no entry below 2-candle lows) ---
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # --- ATR floor SL ---
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

    if len(trades) < MIN_TRADES:
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
        "win_rate": round(wr, 1),
        "roi": round(roi, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
    }


def _close(balance, rr, win, risk_pct):
    pnl = balance * risk_pct * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": balance + pnl}


def rr_range(current_rr: float) -> list[float]:
    """Generate RR values from 1.5 to current_rr in 0.5 steps."""
    vals = []
    v = 1.5
    while v <= current_rr + 1e-9:
        vals.append(round(v, 1))
        v += 0.5
    return vals


if __name__ == "__main__":
    all_rows = []
    summary  = []

    for symbol, cfg in PAIRS.items():
        print(f"\n{'='*70}")
        print(f"  {symbol}  ({cfg['timeframe']})  current RR={cfg['current_rr']}  "
              f"risk={cfg['risk_pct']*100:.1f}%")
        print(f"{'='*70}")

        try:
            df = load_and_prep(symbol, cfg["timeframe"])
        except Exception as e:
            print(f"  Load error: {e}")
            continue

        period = f"{df.index[0].date()} → {df.index[-1].date()}"
        print(f"  Data: {len(df)} bars  |  {period}\n")

        rr_vals    = rr_range(cfg["current_rr"])
        base_result = None
        pair_rows   = []

        print(f"  {'RR':>5}  {'n':>4}  {'WR%':>6}  {'ROI%':>8}  {'Sharpe':>7}  {'MaxDD%':>8}  {'ΔSharpe':>8}")
        print("  " + "-" * 62)

        for rr in rr_vals:
            r = run_backtest(df, rr, cfg)
            if r is None:
                print(f"  {rr:>5.1f}  — insufficient trades (<{MIN_TRADES})")
                continue

            is_current = abs(rr - cfg["current_rr"]) < 1e-6
            if is_current:
                base_result = r

            pair_rows.append({"symbol": symbol, "timeframe": cfg["timeframe"],
                               "rr": rr, "current_rr": cfg["current_rr"], **r})

        # Print results — compute delta after we have the base
        for row in pair_rows:
            is_current = abs(row["rr"] - cfg["current_rr"]) < 1e-6
            delta_s = ""
            if base_result:
                d = row["sharpe"] - base_result["sharpe"]
                delta_s = f"  {'→ CURRENT' if is_current else ('+' if d >= 0 else '')}{d:+.2f}" if not is_current else "  [CURRENT]"
            tag = " ◄" if is_current else ""
            print(f"  {row['rr']:>5.1f}  {row['trades']:>4}  {row['win_rate']:>6.1f}%  "
                  f"{row['roi']:>7.2f}%  {row['sharpe']:>7.2f}  {row['max_dd']:>7.2f}%  "
                  f"{delta_s}{tag}")

        all_rows.extend(pair_rows)

        # Recommend: highest Sharpe among RRs <= current that are >= 85% of current Sharpe
        if base_result and pair_rows:
            threshold = base_result["sharpe"] * 0.85
            candidates = [r for r in pair_rows
                          if r["rr"] <= cfg["current_rr"] and r["sharpe"] >= threshold]
            if candidates:
                recommended = min(candidates, key=lambda x: x["rr"])
            else:
                # fallback: closest to current Sharpe
                recommended = min(pair_rows, key=lambda x: abs(x["sharpe"] - base_result["sharpe"]))

            sharpe_delta = round(recommended["sharpe"] - base_result["sharpe"], 2)
            roi_delta    = round(recommended["roi"]    - base_result["roi"],    2)
            dd_delta     = round(recommended["max_dd"] - base_result["max_dd"], 2)

            print(f"\n  Recommended RR: {recommended['rr']}  "
                  f"(Sharpe {base_result['sharpe']:.2f} → {recommended['sharpe']:.2f}, "
                  f"{'+' if sharpe_delta>=0 else ''}{sharpe_delta})")
            print(f"  Trades: {base_result['trades']} → {recommended['trades']}  "
                  f"WR: {base_result['win_rate']:.1f}% → {recommended['win_rate']:.1f}%  "
                  f"MaxDD: {base_result['max_dd']:.2f}% → {recommended['max_dd']:.2f}%")

            summary.append({
                "symbol":           symbol,
                "timeframe":        cfg["timeframe"],
                "current_rr":       cfg["current_rr"],
                "current_sharpe":   base_result["sharpe"] if base_result else None,
                "current_wr":       base_result["win_rate"] if base_result else None,
                "current_roi":      base_result["roi"] if base_result else None,
                "current_maxdd":    base_result["max_dd"] if base_result else None,
                "current_trades":   base_result["trades"] if base_result else None,
                "rec_rr":           recommended["rr"],
                "rec_sharpe":       recommended["sharpe"],
                "rec_wr":           recommended["win_rate"],
                "rec_roi":          recommended["roi"],
                "rec_maxdd":        recommended["max_dd"],
                "rec_trades":       recommended["trades"],
                "sharpe_delta":     sharpe_delta,
                "roi_delta":        roi_delta,
                "dd_delta":         dd_delta,
            })

    # Save full sweep
    df_out = pd.DataFrame(all_rows)
    df_out.to_csv(OUT_FILE, index=False)
    print(f"\n\nSaved → {OUT_FILE}")

    # Final summary table
    print("\n" + "=" * 110)
    print("SUMMARY — Lowest RR with Sharpe ≥ 85% of current (all production filters held fixed)")
    print("=" * 110)
    print(f"  {'Symbol':<14} {'TF':>4}  {'Cur RR':>6} {'Cur Sh':>7} {'Cur WR':>7} {'Cur ROI':>8} {'Cur DD':>8}  "
          f"{'Rec RR':>6} {'Rec Sh':>7} {'Rec WR':>7} {'Rec ROI':>8} {'Rec DD':>8}  {'ΔSharpe':>8}")
    print("  " + "-" * 105)
    for s in summary:
        print(f"  {s['symbol']:<14} {s['timeframe']:>4}  "
              f"{s['current_rr']:>6.1f} {s['current_sharpe']:>7.2f} {s['current_wr']:>6.1f}% "
              f"{s['current_roi']:>7.2f}% {s['current_maxdd']:>7.2f}%  "
              f"{s['rec_rr']:>6.1f} {s['rec_sharpe']:>7.2f} {s['rec_wr']:>6.1f}% "
              f"{s['rec_roi']:>7.2f}% {s['rec_maxdd']:>7.2f}%  "
              f"{'+' if s['sharpe_delta']>=0 else ''}{s['sharpe_delta']:>7.2f}")
