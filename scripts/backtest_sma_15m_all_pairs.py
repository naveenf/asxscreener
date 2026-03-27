"""
SmaScalping 15m — Full Pair Sweep
==================================
Tests every pair in data/forex_raw/ that has a 15m CSV against a grid of:
  DI threshold : 25, 30, 35
  RR           : 2.5, 3.0, 4.0, 5.0, 6.0
  di_persist   : 1, 2

Reports the best config per pair (by Sharpe), sorted descending.
Minimum 10 trades required to appear in results.

Output: data/backtest_sma_15m_all_pairs.csv
"""

import sys
import itertools
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_sma_15m_all_pairs.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
MIN_TRADES      = 10

# Realistic Oanda spreads (in price units)
SPREADS = {
    "XAU_USD":   0.50,
    "XAG_USD":   0.03,
    "BCO_USD":   0.04,
    "XCU_USD":   0.0005,
    "AU200_AUD": 0.50,
    "UK100_GBP": 0.80,
    "JP225_USD": 17.0,
    "NAS100_USD": 2.30,
    "EUR_USD":   0.0001,
    "GBP_USD":   0.0001,
    "AUD_USD":   0.0001,
    "NZD_USD":   0.0002,
    "USD_CAD":   0.0002,
    "USD_CHF":   0.0002,
    "USD_JPY":   0.02,
    "EUR_JPY":   0.03,
    "GBP_JPY":   0.04,
    "AUD_JPY":   0.03,
    "CAD_JPY":   0.03,
    "CHF_JPY":   0.03,
    "EUR_AUD":   0.0002,
    "CORN_USD":  1.50,
    "WHEAT_USD": 2.00,
    "SOYBN_USD": 2.00,
}

DI_THRESHOLDS = [25.0, 30.0, 35.0]
RR_VALUES     = [2.5, 3.0, 4.0, 5.0, 6.0]
PERSIST_VALUES = [1, 2]


def load_and_prep(symbol: str) -> pd.DataFrame:
    csv = DATA_DIR / f"{symbol}_15_Min.csv"
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
    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


def _close(balance, rr, win):
    pnl = balance * RISK_PCT * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": balance + pnl}


if __name__ == "__main__":
    # Collect all pairs with 15m data
    pairs = sorted([f.stem.replace("_15_Min", "")
                    for f in DATA_DIR.glob("*_15_Min.csv")])

    print(f"SmaScalping 15m — Full Pair Sweep  ({len(pairs)} pairs)")
    print(f"Grid: DI={DI_THRESHOLDS}, RR={RR_VALUES}, persist={PERSIST_VALUES}")
    print("=" * 90)

    results = []
    for symbol in pairs:
        spread = SPREADS.get(symbol, 0.0002)
        try:
            df = load_and_prep(symbol)
        except Exception as e:
            print(f"  {symbol:<16} — load error: {e}")
            continue

        period = f"{df.index[0].date()} → {df.index[-1].date()}"
        best = None

        for di, rr, persist in itertools.product(DI_THRESHOLDS, RR_VALUES, PERSIST_VALUES):
            r = run_backtest(df, rr, di, 0.0, spread, persist)
            if r is None:
                continue
            if best is None or r["sharpe"] > best["sharpe"]:
                best = {"di": di, "rr": rr, "persist": persist, **r}

        if best is None:
            print(f"  {symbol:<16} — no config with ≥{MIN_TRADES} trades")
            continue

        results.append({
            "symbol":      symbol,
            "timeframe":   "15m",
            "di_threshold": best["di"],
            "rr":          best["rr"],
            "di_persist":  best["persist"],
            "spread":      spread,
            "period":      period,
            "trades":      best["trades"],
            "win_rate":    best["win_rate"],
            "roi":         best["roi"],
            "sharpe":      best["sharpe"],
            "max_dd":      best["max_dd"],
        })

    # Sort by Sharpe descending
    results.sort(key=lambda x: x["sharpe"], reverse=True)

    print(f"\n{'Symbol':<16} {'DI':>3} {'RR':>5} {'p':>2} {'Trades':>6} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
    print("-" * 72)
    for r in results:
        flag = ""
        if r["sharpe"] >= 2.0 and r["roi"] > 0:
            flag = " ✓"
        print(f"  {r['symbol']:<14} DI>{r['di_threshold']:<4.0f} RR={r['rr']:<4.1f} p={r['di_persist']}  "
              f"n={r['trades']:>4}  wr={r['win_rate']:>5.1f}%  roi={r['roi']:>7.2f}%  "
              f"sharpe={r['sharpe']:>5.2f}  dd={r['max_dd']:>7.2f}%{flag}")

    print(f"\nPairs with Sharpe ≥ 2.0 and positive ROI:")
    good = [r for r in results if r["sharpe"] >= 2.0 and r["roi"] > 0]
    for r in good:
        print(f"  {r['symbol']:<14} Sharpe={r['sharpe']:.2f}  ROI={r['roi']:.1f}%  "
              f"WR={r['win_rate']:.1f}%  MaxDD={r['max_dd']:.2f}%  "
              f"DI>{r['di_threshold']:.0f} RR={r['rr']} p={r['di_persist']}")

    df_out = pd.DataFrame(results)
    df_out.to_csv(OUT_FILE, index=False)
    print(f"\nSaved → {OUT_FILE}  ({len(results)} pairs)")
