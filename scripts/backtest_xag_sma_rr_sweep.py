"""
XAG_USD SmaScalping — R:R sweep with full production filters.

Production params (from best_strategies.json):
  timeframe:    5m
  di_threshold: 35.0
  di_persist:   1
  atr_ratio_min: 1.2  (ATR >= 1.2 × 20-bar ATR avg)
  di_slope:     True  (DI+ rising vs 2 candles ago)
  avoid_hours:  [14, 15, 16]  (UTC, London-NY overlap)
  spread:       0.03

Sweeps R:R: 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0

Output: data/backtest_xag_sma_rr_sweep.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_FILE        = Path("data/backtest_xag_sma_rr_sweep.csv")
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01

# Production config
SYMBOL       = "XAG_USD"
SPREAD       = 0.03
DI_THRESHOLD = 35.0
DI_PERSIST   = 1
ATR_RATIO    = 1.2   # ATR >= 1.2 × 20-bar avg
DI_SLOPE     = True
AVOID_HOURS  = {14, 15, 16}

RR_VALUES = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]


def load_and_prep() -> pd.DataFrame:
    csv = DATA_DIR / f"{SYMBOL}_5_Min.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for period, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(period).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR"],
              inplace=True)
    return df


def run_backtest(df: pd.DataFrame, rr: float) -> dict | None:
    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    sma20    = df["SMA20"].values
    sma50    = df["SMA50"].values
    sma100   = df["SMA100"].values
    di_plus  = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    atr_arr  = df["ATR"].values
    hours    = df.index.hour  # UTC hours

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    # Need at least 22 bars of history for ATR avg (20 bars) + di_slope (2 back) + persist
    start = 22

    for i in range(start, len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        # --- Exit ---
        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    pnl = balance * RISK_PCT * -1
                    balance += pnl
                    trades.append({"result": "LOSS", "pnl": pnl, "balance": balance})
                    in_trade = False
                elif h >= tp:
                    pnl = balance * RISK_PCT * rr
                    balance += pnl
                    trades.append({"result": "WIN", "pnl": pnl, "balance": balance})
                    in_trade = False
            else:  # SELL
                if h >= sl:
                    pnl = balance * RISK_PCT * -1
                    balance += pnl
                    trades.append({"result": "LOSS", "pnl": pnl, "balance": balance})
                    in_trade = False
                elif l <= tp:
                    pnl = balance * RISK_PCT * rr
                    balance += pnl
                    trades.append({"result": "WIN", "pnl": pnl, "balance": balance})
                    in_trade = False
            continue

        # --- Session filter ---
        if hours[i] in AVOID_HOURS:
            continue

        # --- DI persistence ---
        di_plus_pers  = all(di_plus[i - j]  > DI_THRESHOLD for j in range(DI_PERSIST))
        di_minus_pers = all(di_minus[i - j] > DI_THRESHOLD for j in range(DI_PERSIST))

        # --- DI slope (DI at i vs DI at i-2) ---
        di_slope_buy  = di_plus[i]  > di_plus[i - 2]
        di_slope_sell = di_minus[i] > di_minus[i - 2]

        # --- ATR expansion (ATR >= ratio × 20-bar avg, excl. current) ---
        atr_avg = atr_arr[i - 20:i].mean()
        atr_ok  = (atr_avg > 0) and (atr_arr[i] >= ATR_RATIO * atr_avg)

        # --- Entry conditions ---
        is_buy = (
            c > sma20[i] and c > sma50[i] and c > sma100[i]
            and di_plus_pers
            and di_plus[i] > di_minus[i]
            and di_slope_buy
            and atr_ok
        )
        is_sell = (
            c < sma20[i] and c < sma50[i] and c < sma100[i]
            and di_minus_pers
            and di_minus[i] > di_plus[i]
            and di_slope_sell
            and atr_ok
        )

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
            sl_p  = c - stop_dist - SPREAD
            risk  = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * rr
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_p  = c + stop_dist + SPREAD
            risk  = sl_p - c
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

    # Expectancy in R (per trade)
    wr_frac   = wins / n
    expectancy = wr_frac * rr - (1 - wr_frac) * 1.0

    return {
        "rr":         rr,
        "trades":     n,
        "wins":       int(wins),
        "win_rate":   round(wr, 1),
        "roi":        round(roi, 2),
        "sharpe":     round(sharpe, 2),
        "max_dd":     round(max_dd, 2),
        "expectancy": round(expectancy, 3),
    }


if __name__ == "__main__":
    print(f"XAG_USD SmaScalping — R:R Sweep")
    print(f"Filters: DI>{DI_THRESHOLD}  persist={DI_PERSIST}  atr_ratio={ATR_RATIO}  "
          f"di_slope={DI_SLOPE}  avoid_hours={sorted(AVOID_HOURS)}")
    print("=" * 80)

    df = load_and_prep()
    period = f"{df.index[0].date()} → {df.index[-1].date()}"
    print(f"Data: {SYMBOL} 5m  {period}  ({len(df):,} rows)\n")

    print(f"  {'RR':>5}  {'Trades':>6}  {'WR%':>6}  {'ROI%':>8}  {'Sharpe':>7}  "
          f"{'MaxDD%':>8}  {'Expect-R':>9}")
    print("  " + "-" * 65)

    rows = []
    best_sharpe = {"sharpe": -999, "rr": None}
    best_roi    = {"roi": -999, "rr": None}

    for rr in RR_VALUES:
        r = run_backtest(df, rr)
        if r is None:
            print(f"  RR={rr:<5.1f}  — insufficient trades")
            continue

        marker = ""
        if r["sharpe"] > best_sharpe["sharpe"]:
            best_sharpe = {"sharpe": r["sharpe"], "rr": rr}
        if r["roi"] > best_roi["roi"]:
            best_roi = {"roi": r["roi"], "rr": rr}

        print(f"  RR={rr:<5.1f}  n={r['trades']:>4}  wr={r['win_rate']:>5.1f}%  "
              f"roi={r['roi']:>8.2f}%  sharpe={r['sharpe']:>6.2f}  "
              f"dd={r['max_dd']:>7.2f}%  exp={r['expectancy']:>+7.3f}R")

        rows.append({"symbol": SYMBOL, "timeframe": "5m", "period": period, **r})

    print()
    print(f"  Best Sharpe : RR={best_sharpe['rr']}  ({best_sharpe['sharpe']:.2f})")
    print(f"  Best ROI    : RR={best_roi['rr']}  ({best_roi['roi']:.2f}%)")
    print()
    print(f"  Current deployed RR=12.0 — highlighted above as reference")

    pd.DataFrame(rows).to_csv(OUT_FILE, index=False)
    print(f"\nSaved → {OUT_FILE}  ({len(rows)} R:R configs)")
