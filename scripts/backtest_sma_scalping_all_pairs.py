"""
SmaScalping 5m — all-pairs backtest using deployed parameters.
Generates data/backtest_sma_scalping_all_pairs.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR  = Path("data/forex_raw")
OUT_FILE  = Path("data/backtest_sma_scalping_all_pairs.csv")

INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

# Deployed parameters per pair (di_threshold, adx_min, target_rr, spread)
DEPLOYED = {
    # Pairs added in current session — optimised params
    "WHEAT_USD":   dict(di=30.0, adx=30.0, rr=3.0,  spread=0.010),
    "NAS100_USD":  dict(di=35.0, adx=0.0,  rr=4.5,  spread=2.30),
    "JP225_USD":   dict(di=30.0, adx=20.0, rr=5.0,  spread=17.0),
    "AUD_USD":     dict(di=35.0, adx=0.0,  rr=2.5,  spread=0.0002),
    "USD_CAD":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0002),
    # XAU/XAG already have dedicated backtest files — include for completeness
    "XAU_USD":     dict(di=35.0, adx=0.0,  rr=5.0,  spread=0.50),
    "XAG_USD":     dict(di=35.0, adx=0.0,  rr=10.0, spread=0.03),
    # Reference pairs (not deployed, shown for comparison)
    "BCO_USD":     dict(di=35.0, adx=0.0,  rr=5.0,  spread=0.05),
    "EUR_USD":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0001),
    "GBP_USD":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0002),
    "USD_CHF":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0002),
    "USD_JPY":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.02),
    "NZD_USD":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0002),
    "AUD_JPY":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.03),
    "CAD_JPY":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.03),
    "CHF_JPY":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.03),
    "EUR_JPY":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.02),
    "GBP_JPY":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.03),
    "EUR_AUD":     dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0003),
    "UK100_GBP":   dict(di=35.0, adx=0.0,  rr=5.0,  spread=1.0),
    "XCU_USD":     dict(di=35.0, adx=0.0,  rr=5.0,  spread=0.001),
}


def load_and_prep(symbol: str) -> pd.DataFrame:
    csv = DATA_DIR / f"{symbol}_5_Min.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX"], inplace=True)
    return df


def run_backtest(df, rr, di, adx_min, spread):
    closes  = df["Close"].values
    highs   = df["High"].values
    lows    = df["Low"].values
    sma20   = df["SMA20"].values
    sma50   = df["SMA50"].values
    sma100  = df["SMA100"].values
    di_plus = df["DIPlus"].values
    di_minus= df["DIMinus"].values
    adx     = df["ADX"].values

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(3, len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        if in_trade:
            if direction == "BUY":
                if l <= sl:   trades.append(_close(balance, rr, False)); balance += trades[-1]["pnl"]; in_trade = False
                elif h >= tp: trades.append(_close(balance, rr, True));  balance += trades[-1]["pnl"]; in_trade = False
            else:
                if h >= sl:   trades.append(_close(balance, rr, False)); balance += trades[-1]["pnl"]; in_trade = False
                elif l <= tp: trades.append(_close(balance, rr, True));  balance += trades[-1]["pnl"]; in_trade = False
            if not in_trade:
                trades[-1]["balance"] = balance
            continue

        adx_ok   = adx[i] >= adx_min
        is_buy   = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                    and di_plus[i] > di and adx_ok)
        is_sell  = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                    and di_minus[i] > di and adx_ok)

        if not (is_buy or is_sell):
            continue

        prev_low  = min(lows[i-2],  lows[i-1])
        prev_high = max(highs[i-2], highs[i-1])

        if is_buy:
            sl_p = prev_low - spread;  risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * rr
        else:
            sl_p = prev_high + spread; risk = sl_p - c
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
    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}


def _close(balance, rr, win):
    pnl = balance * RISK_PCT * (rr if win else -1)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl, "balance": 0}


if __name__ == "__main__":
    rows = []
    for symbol, p in DEPLOYED.items():
        csv = DATA_DIR / f"{symbol}_5_Min.csv"
        if not csv.exists():
            print(f"  {symbol:<14} — no data file, skipping")
            continue
        try:
            df = load_and_prep(symbol)
        except Exception as e:
            print(f"  {symbol:<14} — load error: {e}")
            continue

        period = f"{df.index[0].date()} → {df.index[-1].date()}"
        r = run_backtest(df, p["rr"], p["di"], p["adx"], p["spread"])
        if r is None:
            print(f"  {symbol:<14} — insufficient trades (<8)")
            continue

        tag = "DEPLOYED" if symbol in ("WHEAT_USD","NAS100_USD","JP225_USD","AUD_USD","USD_CAD") else ""
        print(f"  {symbol:<14} rr={p['rr']} di>{p['di']} adx>{p['adx']}  "
              f"n={r['trades']:>4}  wr={r['win_rate']:>5.1f}%  roi={r['roi']:>7.2f}%  "
              f"sharpe={r['sharpe']:>5.2f}  dd={r['max_dd']:>7.2f}%  {tag}")
        rows.append({"symbol": symbol, "rr": p["rr"], "di_threshold": p["di"],
                     "adx_min": p["adx"], "spread": p["spread"], "period": period,
                     **r})

    pd.DataFrame(rows).to_csv(OUT_FILE, index=False)
    print(f"\nSaved → {OUT_FILE}  ({len(rows)} rows)")
