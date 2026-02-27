"""
SmaScalping — deployed-pairs backtest using current production parameters.

Matches the live detector exactly:
  - DI threshold + DI dominance (DI+ > DI-)
  - ADX min
  - di_persist: DI must exceed threshold for N consecutive candles
  - Structural validity: price not already past the 2-candle SL level
  - ATR floor for stop loss: SL = max(structural_distance, 1×ATR)

Deployed pairs and timeframes (Feb 2026):
  XAU_USD   15m  DI>35  RR=5.0   di_persist=2
  XAG_USD    5m  DI>35  RR=10.0  di_persist=1
  JP225_USD  5m  DI>30  RR=5.0   di_persist=2  adx_min=20
  AUD_USD    5m  DI>35  RR=2.5   di_persist=2
  USD_CAD    5m  DI>35  RR=3.0   di_persist=1
  NAS100_USD 5m  DI>35  RR=4.5   di_persist=1

Generates: data/backtest_sma_scalping_all_pairs.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_sma_scalping_all_pairs.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

# Current deployed parameters — keep in sync with best_strategies.json
DEPLOYED = {
    #          tf      di     adx    rr     persist  spread
    "XAU_USD":    dict(tf="15m", di=35.0, adx=0.0,  rr=5.0,  persist=2, spread=0.50),
    "XAG_USD":    dict(tf="5m",  di=35.0, adx=0.0,  rr=10.0, persist=1, spread=0.03),
    "JP225_USD":  dict(tf="5m",  di=30.0, adx=20.0, rr=5.0,  persist=2, spread=17.0),
    "AUD_USD":    dict(tf="5m",  di=35.0, adx=0.0,  rr=2.5,  persist=2, spread=0.0002),
    "USD_CAD":    dict(tf="5m",  di=35.0, adx=0.0,  rr=3.0,  persist=1, spread=0.0002),
    "NAS100_USD": dict(tf="5m",  di=35.0, adx=0.0,  rr=4.5,  persist=1, spread=2.30),
}

TF_SUFFIX = {"5m": "5_Min", "15m": "15_Min"}


def load_and_prep(symbol: str, tf: str) -> pd.DataFrame:
    suffix = TF_SUFFIX[tf]
    csv = DATA_DIR / f"{symbol}_{suffix}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def run_backtest(df, rr, di, adx_min, spread, di_persist):
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

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(max(3, di_persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # --- Exit ---
        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False)); balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True));  balance = trades[-1]["balance"]; in_trade = False
            continue

        # --- Entry: DI persistence + dominance + ADX ---
        adx_ok        = adx_arr[i] >= adx_min
        di_plus_pers  = all(di_plus[i - j]  > di for j in range(di_persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(di_persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i] and adx_ok)
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i] and adx_ok)

        if not (is_buy or is_sell):
            continue

        # --- Structural validity ---
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # --- ATR floor for SL ---
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

    if len(trades) < 5:
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
    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


def _close(balance, rr, win):
    pnl = balance * RISK_PCT * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": balance + pnl}


if __name__ == "__main__":
    print("SmaScalping — Deployed Pairs Backtest")
    print("=" * 78)
    print(f"  {'Symbol':<14} {'TF':<4} {'DI':>3} {'RR':>5} {'p':>2} {'Trades':>6} "
          f"{'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
    print("  " + "-" * 67)

    rows = []
    for symbol, p in DEPLOYED.items():
        tf_suffix = TF_SUFFIX[p["tf"]]
        csv = DATA_DIR / f"{symbol}_{tf_suffix}.csv"
        if not csv.exists():
            print(f"  {symbol:<14} — no {p['tf']} data file, skipping")
            continue
        try:
            df = load_and_prep(symbol, p["tf"])
        except Exception as e:
            print(f"  {symbol:<14} — load error: {e}")
            continue

        period = f"{df.index[0].date()} → {df.index[-1].date()}"
        r = run_backtest(df, p["rr"], p["di"], p["adx"], p["spread"], p["persist"])
        if r is None:
            print(f"  {symbol:<14} — insufficient trades (<5)")
            continue

        print(f"  {symbol:<14} {p['tf']:<4} DI>{p['di']:<4.0f} RR={p['rr']:<4.1f} p={p['persist']}  "
              f"n={r['trades']:>4}  wr={r['win_rate']:>5.1f}%  roi={r['roi']:>7.2f}%  "
              f"sharpe={r['sharpe']:>5.2f}  dd={r['max_dd']:>7.2f}%")
        rows.append({"symbol": symbol, "timeframe": p["tf"], "rr": p["rr"],
                     "di_threshold": p["di"], "adx_min": p["adx"],
                     "di_persist": p["persist"], "spread": p["spread"],
                     "period": period, **r})

    pd.DataFrame(rows).to_csv(OUT_FILE, index=False)
    print(f"\nSaved → {OUT_FILE}  ({len(rows)} pairs)")
