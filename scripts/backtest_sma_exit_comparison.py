"""
SmaScalping 5m — SMA20 exit vs SMA50 exit comparison.
Runs both exit variants for all deployed pairs + XAU + XAG.
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

PAIRS = {
    "XAU_USD":    dict(di=35.0, adx=0.0,  rr=5.0,  spread=0.50),
    "XAG_USD":    dict(di=35.0, adx=0.0,  rr=10.0, spread=0.03),
    "WHEAT_USD":  dict(di=30.0, adx=30.0, rr=3.0,  spread=0.010),
    "NAS100_USD": dict(di=35.0, adx=0.0,  rr=4.5,  spread=2.30),
    "JP225_USD":  dict(di=30.0, adx=20.0, rr=5.0,  spread=17.0),
    "AUD_USD":    dict(di=35.0, adx=0.0,  rr=2.5,  spread=0.0002),
    "USD_CAD":    dict(di=35.0, adx=0.0,  rr=3.0,  spread=0.0002),
}


def load(symbol: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"{symbol}_5_Min.csv", parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX"], inplace=True)
    return df


def backtest(df, rr, spread, di, adx_min, sma_exit_col):
    """
    Full backtest with SMA exit + SL/TP.
    sma_exit_col: 'SMA20' or 'SMA50' — close below/above this triggers exit.
    """
    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    sma20    = df["SMA20"].values
    sma50    = df["SMA50"].values
    sma100   = df["SMA100"].values
    sma_exit = df[sma_exit_col].values
    di_plus  = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    adx      = df["ADX"].values

    balance   = INITIAL_BALANCE
    trades    = []
    in_trade  = False
    sl = tp = direction = None
    exit_counts = {"SL": 0, "TP": 0, "SMA": 0}

    for i in range(3, len(df)):
        c, h, l = closes[i], highs[i], lows[i]
        sma_val  = sma_exit[i]

        if in_trade:
            # Check SL/TP first (intra-candle)
            hit_tp = hit_sl = hit_sma = False
            if direction == "BUY":
                if l <= sl:         hit_sl  = True
                elif h >= tp:       hit_tp  = True
                elif c < sma_val:   hit_sma = True
            else:
                if h >= sl:         hit_sl  = True
                elif l <= tp:       hit_tp  = True
                elif c > sma_val:   hit_sma = True

            if hit_sl or hit_tp or hit_sma:
                if hit_sl:
                    pnl = balance * RISK_PCT * -1
                    exit_counts["SL"] += 1
                    result = "LOSS"
                elif hit_tp:
                    pnl = balance * RISK_PCT * rr
                    exit_counts["TP"] += 1
                    result = "WIN"
                else:  # SMA exit — use close price, calculate actual R
                    if direction == "BUY":
                        risk = entry_price - sl
                        actual_r = (c - entry_price) / risk if risk > 0 else 0
                    else:
                        risk = sl - entry_price
                        actual_r = (entry_price - c) / risk if risk > 0 else 0
                    pnl = balance * RISK_PCT * actual_r
                    exit_counts["SMA"] += 1
                    result = "WIN" if actual_r > 0 else "LOSS"

                balance += pnl
                trades.append({"result": result, "pnl": pnl, "balance": balance})
                in_trade = False
            continue

        # Entry
        adx_ok  = adx[i] >= adx_min
        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus[i] > di and adx_ok)
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
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

        entry_price = c
        in_trade = True

    if len(trades) < 8:
        return None, None

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

    stats = {"n": n, "wins": int(wins), "wr": round(wr, 1), "roi": round(roi, 2),
             "sharpe": round(sharpe, 2), "max_dd": round(max_dd, 2)}
    return stats, exit_counts


if __name__ == "__main__":
    rows = []

    print(f"\n{'Symbol':<14} {'Exit':<6} | {'N':>5} {'WR%':>6} {'ROI%':>8} "
          f"{'Sharpe':>7} {'MaxDD%':>7} | {'SL%':>5} {'TP%':>5} {'SMA%':>6}")
    print("─" * 80)

    for symbol, p in PAIRS.items():
        df = load(symbol)

        for sma_col in ("SMA20", "SMA50"):
            r, exits = backtest(df, p["rr"], p["spread"], p["di"], p["adx"], sma_col)
            if r is None:
                print(f"  {symbol:<14} {sma_col:<6} — insufficient trades")
                continue

            total = exits["SL"] + exits["TP"] + exits["SMA"]
            sl_pct  = exits["SL"]  / total * 100
            tp_pct  = exits["TP"]  / total * 100
            sma_pct = exits["SMA"] / total * 100

            marker = " ◄" if sma_col == "SMA50" else ""
            print(f"  {symbol:<14} {sma_col:<6} | {r['n']:>5} {r['wr']:>6.1f} {r['roi']:>8.2f} "
                  f"{r['sharpe']:>7.2f} {r['max_dd']:>7.2f} | "
                  f"{sl_pct:>4.0f}% {tp_pct:>4.0f}% {sma_pct:>5.0f}%{marker}")

            rows.append({"symbol": symbol, "exit": sma_col, **r,
                         "sl_pct": round(sl_pct,1), "tp_pct": round(tp_pct,1),
                         "sma_exit_pct": round(sma_pct,1)})

        print()  # blank line between pairs

    pd.DataFrame(rows).to_csv("data/backtest_sma_exit_comparison.csv", index=False)
    print("\nSaved → data/backtest_sma_exit_comparison.csv")
