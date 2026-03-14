"""
NAS100_USD — 3-Strategy Comparison Backtest
============================================
Compares SmaScalping, PVTScalping, and NewBreakout on NAS100_USD
using historical forex_raw data.

Strategies:
  SmaScalping  — 5m,  DI>35, RR=4.5, persist=1, atr_ratio=1.0, di_slope, avoid[7,21,22,23]
  PVTScalping  — 1h,  PVT>0.05, EMA50, SMA100, Daily SMA200, RR=2.5
  NewBreakout  — 15m+4h HTF, S/R breakout, ADX>25, EMA34, ATR×2 SL, RR=2.0

Outputs:
  data/backtest_nas100_strategy_compare.csv   — all trades (one row per trade)
  data/backtest_nas100_strategy_summary.csv   — per-strategy summary
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.app.services.indicators import TechnicalIndicators

DATA_DIR        = Path("data/forex_raw")
OUT_TRADES      = Path("data/backtest_nas100_strategy_compare.csv")
OUT_SUMMARY     = Path("data/backtest_nas100_strategy_summary.csv")
SYMBOL          = "NAS100_USD"
INITIAL_BALANCE = 10_000.0
RISK_PCT        = 0.01
NAS_SPREAD      = 2.30   # points


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_csv(symbol: str, tf_suffix: str) -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}_{tf_suffix}.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df


def compute_metrics(trades: list, initial_balance: float) -> dict:
    if len(trades) < 5:
        return None
    df_t  = pd.DataFrame(trades)
    n     = len(df_t)
    wins  = (df_t["result"] == "WIN").sum()
    wr    = wins / n * 100
    roi   = df_t["pnl"].sum() / initial_balance * 100
    rets  = df_t["pnl"] / initial_balance
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    equity = df_t["balance"].values
    peak   = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak * 100).min())
    return {
        "trades": n, "wins": int(wins),
        "win_rate": round(wr, 1),
        "roi": round(roi, 2),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "trade_rows": df_t,
    }


def make_trade_row(strategy, direction, date, entry, sl, tp, result, pnl, balance):
    return {
        "strategy":  strategy,
        "date":      date,
        "direction": direction,
        "entry":     round(entry, 3),
        "sl":        round(sl, 3),
        "tp":        round(tp, 3),
        "result":    result,
        "pnl":       round(pnl, 2),
        "balance":   round(balance, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SmaScalping — 5m
# ─────────────────────────────────────────────────────────────────────────────

def run_sma_scalping():
    df = load_csv(SYMBOL, "5_Min")
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df["ATR_MA20"] = df["ATR"].rolling(20).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100", "DIPlus", "DIMinus", "ADX", "ATR", "ATR_MA20"],
              inplace=True)

    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    sma20    = df["SMA20"].values
    sma50    = df["SMA50"].values
    sma100   = df["SMA100"].values
    di_plus  = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    atr_arr  = df["ATR"].values
    atr_ma   = df["ATR_MA20"].values
    hours    = df.index.hour
    AVOID    = {7, 21, 22, 23}
    DI_THR   = 35.0
    RR       = 4.5
    SPREAD   = NAS_SPREAD

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(3, len(df)):
        c, h, l = closes[i], highs[i], lows[i]
        hour = hours[i]

        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    pnl = -balance * RISK_PCT
                    balance += pnl
                    trades.append(make_trade_row("SmaScalping", direction, df.index[i], entry_price, sl, tp, "LOSS", pnl, balance))
                    in_trade = False
                elif h >= tp:
                    pnl = balance * RISK_PCT * RR
                    balance += pnl
                    trades.append(make_trade_row("SmaScalping", direction, df.index[i], entry_price, sl, tp, "WIN", pnl, balance))
                    in_trade = False
            else:
                if h >= sl:
                    pnl = -balance * RISK_PCT
                    balance += pnl
                    trades.append(make_trade_row("SmaScalping", direction, df.index[i], entry_price, sl, tp, "LOSS", pnl, balance))
                    in_trade = False
                elif l <= tp:
                    pnl = balance * RISK_PCT * RR
                    balance += pnl
                    trades.append(make_trade_row("SmaScalping", direction, df.index[i], entry_price, sl, tp, "WIN", pnl, balance))
                    in_trade = False
            continue

        if hour in AVOID:
            continue

        # DI persist=1 + dominance
        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus[i]  > DI_THR and di_plus[i]  > di_minus[i]
                   and di_plus[i]  > di_plus[i-1])   # di_slope
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus[i] > DI_THR and di_minus[i] > di_plus[i]
                   and di_minus[i] > di_minus[i-1])  # di_slope

        if not (is_buy or is_sell):
            continue

        # atr_ratio_min=1.0
        if atr_ma[i] > 0 and atr_arr[i] < 1.0 * atr_ma[i]:
            continue

        # Structural validity
        prev_low  = min(lows[i-2],  lows[i-1])
        prev_high = max(highs[i-2], highs[i-1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        atr_val = atr_arr[i]
        if is_buy:
            stop_dist = max(c - prev_low, atr_val)
            sl_p = c - stop_dist - SPREAD
            risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * RR
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_p = c + stop_dist + SPREAD
            risk = sl_p - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_p;  tp = c - risk * RR

        entry_price = c
        in_trade = True

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# PVTScalping — 1h
# ─────────────────────────────────────────────────────────────────────────────

def run_pvt_scalping():
    df = load_csv(SYMBOL, "1_Hour")
    df = TechnicalIndicators.add_all_indicators(df)

    # Manually add PVT if not present
    if "PVT" not in df.columns:
        df = TechnicalIndicators.calculate_pvt(df)
    if "EMA50" not in df.columns:
        df["EMA50"] = TechnicalIndicators.calculate_ema(df, column="Close", period=50)
    if "SMA100" not in df.columns:
        df["SMA100"] = TechnicalIndicators.calculate_sma(df, column="Close", period=100)

    # Daily SMA200 (resampled)
    df_daily = df.resample("D").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
    df_daily["SMA200"] = df_daily["Close"].rolling(200).mean()

    df.dropna(subset=["EMA50", "SMA100", "RSI", "PVT", "ATR"], inplace=True)

    RR       = 2.5
    PVT_THR  = 0.05
    ATR_MULT = 2.0
    SPREAD   = NAS_SPREAD

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = entry_price = None
    consec_losses = 0

    for i in range(250, len(df)):
        row   = df.iloc[i]
        c     = float(row["Close"])
        h     = float(row["High"])
        l     = float(row["Low"])
        ts    = df.index[i]
        hour  = ts.hour

        # Daily SMA200 — get latest available
        daily_up_to = df_daily[df_daily.index.date <= ts.date()]
        if len(daily_up_to) < 200 or pd.isna(daily_up_to["SMA200"].iloc[-1]):
            continue
        sma200 = float(daily_up_to["SMA200"].iloc[-1])

        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    pnl = -balance * RISK_PCT
                    balance += pnl
                    trades.append(make_trade_row("PVTScalping", direction, ts, entry_price, sl, tp, "LOSS", pnl, balance))
                    in_trade = False; consec_losses += 1
                elif h >= tp:
                    pnl = balance * RISK_PCT * RR
                    balance += pnl
                    trades.append(make_trade_row("PVTScalping", direction, ts, entry_price, sl, tp, "WIN", pnl, balance))
                    in_trade = False; consec_losses = 0
            else:
                if h >= sl:
                    pnl = -balance * RISK_PCT
                    balance += pnl
                    trades.append(make_trade_row("PVTScalping", direction, ts, entry_price, sl, tp, "LOSS", pnl, balance))
                    in_trade = False; consec_losses += 1
                elif l <= tp:
                    pnl = balance * RISK_PCT * RR
                    balance += pnl
                    trades.append(make_trade_row("PVTScalping", direction, ts, entry_price, sl, tp, "WIN", pnl, balance))
                    in_trade = False; consec_losses = 0
            continue

        if consec_losses >= 5:
            consec_losses = 0   # reset circuit breaker after cooling off period (handled by skip)
            continue

        # Trading hours: 10-23 UTC
        if not (10 <= hour < 23):
            continue

        pvt    = float(row["PVT"])
        ema50  = float(row["EMA50"])
        sma100 = float(row["SMA100"])
        rsi    = float(row["RSI"])
        atr    = float(row["ATR"])

        long_signal  = (c > ema50 and c > sma100 and rsi > 20 and pvt >  PVT_THR and c > sma200)
        short_signal = (c < ema50 and c < sma100 and rsi < 80 and pvt < -PVT_THR and c < sma200)

        if not (long_signal or short_signal):
            continue

        if long_signal:
            sl_p = c - atr * ATR_MULT - SPREAD
            risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * RR
        else:
            sl_p = c + atr * ATR_MULT + SPREAD
            risk = sl_p - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_p;  tp = c - risk * RR

        entry_price = c
        in_trade = True

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# NewBreakout — 15m + 4h HTF
# ─────────────────────────────────────────────────────────────────────────────

def run_new_breakout():
    df_15m = load_csv(SYMBOL, "15_Min")
    df_4h  = load_csv(SYMBOL, "4_Hour")

    df_15m = TechnicalIndicators.add_all_indicators(df_15m)
    df_4h  = TechnicalIndicators.add_all_indicators(df_4h)

    if "EMA34" not in df_15m.columns:
        df_15m["EMA34"] = TechnicalIndicators.calculate_ema(df_15m, column="Close", period=34)
    if "EMA34" not in df_4h.columns:
        df_4h["EMA34"]  = TechnicalIndicators.calculate_ema(df_4h,  column="Close", period=34)

    df_15m.dropna(subset=["ATR", "DIPlus", "DIMinus", "ADX"], inplace=True)
    df_4h.dropna(subset=["EMA34", "ADX", "DIPlus", "DIMinus"], inplace=True)

    SR_LOOKBACK = 40
    ADX_THR     = 25.0
    ATR_MULT    = 2.0
    RR          = 2.0
    SPREAD      = NAS_SPREAD

    balance  = INITIAL_BALANCE
    trades   = []
    in_trade = False
    sl = tp = direction = entry_price = None

    for i in range(SR_LOOKBACK + 2, len(df_15m)):
        ts  = df_15m.index[i]
        row = df_15m.iloc[i]
        c   = float(row["Close"])
        h   = float(row["High"])
        l   = float(row["Low"])

        # 4H HTF trend at this point in time
        htf_up_to = df_4h[df_4h.index <= ts]
        if len(htf_up_to) < 2:
            continue
        htf = htf_up_to.iloc[-1]

        if float(htf["ADX"]) > ADX_THR:
            if float(htf["Close"]) > float(htf["EMA34"]) and float(htf["DIPlus"]) > float(htf["DIMinus"]):
                htf_trend = "bullish"
            elif float(htf["Close"]) < float(htf["EMA34"]) and float(htf["DIMinus"]) > float(htf["DIPlus"]):
                htf_trend = "bearish"
            else:
                htf_trend = "neutral"
        else:
            htf_trend = "neutral"

        if htf_trend == "neutral":
            continue

        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    pnl = -balance * RISK_PCT
                    balance += pnl
                    trades.append(make_trade_row("NewBreakout", direction, ts, entry_price, sl, tp, "LOSS", pnl, balance))
                    in_trade = False
                elif h >= tp:
                    pnl = balance * RISK_PCT * RR
                    balance += pnl
                    trades.append(make_trade_row("NewBreakout", direction, ts, entry_price, sl, tp, "WIN", pnl, balance))
                    in_trade = False
            else:
                if h >= sl:
                    pnl = -balance * RISK_PCT
                    balance += pnl
                    trades.append(make_trade_row("NewBreakout", direction, ts, entry_price, sl, tp, "LOSS", pnl, balance))
                    in_trade = False
                elif l <= tp:
                    pnl = balance * RISK_PCT * RR
                    balance += pnl
                    trades.append(make_trade_row("NewBreakout", direction, ts, entry_price, sl, tp, "WIN", pnl, balance))
                    in_trade = False
            continue

        window = df_15m.iloc[i - SR_LOOKBACK: i]
        recent_high = float(window["High"].max())
        recent_low  = float(window["Low"].min())
        prev_close  = float(df_15m.iloc[i-1]["Close"])

        is_buy  = htf_trend == "bullish" and c > recent_high and prev_close <= recent_high
        is_sell = htf_trend == "bearish" and c < recent_low  and prev_close >= recent_low

        if not (is_buy or is_sell):
            continue

        atr = float(row["ATR"])
        if atr <= 0:
            continue

        if is_buy:
            sl_p = c - atr * ATR_MULT - SPREAD
            risk = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * RR
        else:
            sl_p = c + atr * ATR_MULT + SPREAD
            risk = sl_p - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_p;  tp = c - risk * RR

        entry_price = c
        in_trade = True

    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nNAS100_USD — 3-Strategy Backtest Comparison")
    print("=" * 72)

    all_trade_rows = []
    summary_rows   = []

    strategies = [
        ("SmaScalping",  run_sma_scalping,  "5m",   RR_val := 4.5),
        ("PVTScalping",  run_pvt_scalping,  "1h",   2.5),
        ("NewBreakout",  run_new_breakout,  "15m",  2.0),
    ]

    for name, fn, tf, rr in [
        ("SmaScalping", run_sma_scalping, "5m",  4.5),
        ("PVTScalping", run_pvt_scalping, "1h",  2.5),
        ("NewBreakout", run_new_breakout, "15m", 2.0),
    ]:
        print(f"\n  Running {name} ({tf}, RR={rr})...")
        try:
            trades = fn()
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        m = compute_metrics(trades, INITIAL_BALANCE)
        if m is None:
            print(f"  {name}: insufficient trades (<5)")
            continue

        print(f"  Trades={m['trades']}  WR={m['win_rate']}%  ROI={m['roi']}%  "
              f"Sharpe={m['sharpe']}  MaxDD={m['max_dd']}%")

        df_rows = m.pop("trade_rows")
        all_trade_rows.append(df_rows)
        summary_rows.append({"strategy": name, "timeframe": tf, "rr": rr, **m})

    print("\n")
    print("  " + "-" * 68)
    print(f"  {'Strategy':<14} {'TF':<5} {'RR':>4} {'Trades':>6} {'WR%':>6} "
          f"{'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
    print("  " + "-" * 68)
    for r in summary_rows:
        print(f"  {r['strategy']:<14} {r['timeframe']:<5} {r['rr']:>4.1f}  "
              f"n={r['trades']:>4}  wr={r['win_rate']:>5.1f}%  roi={r['roi']:>7.2f}%  "
              f"sharpe={r['sharpe']:>5.2f}  dd={r['max_dd']:>7.2f}%")
    print("  " + "-" * 68)

    if all_trade_rows:
        pd.concat(all_trade_rows, ignore_index=True).to_csv(OUT_TRADES, index=False)
        print(f"\n  Trades CSV → {OUT_TRADES}")

    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(OUT_SUMMARY, index=False)
        print(f"  Summary CSV → {OUT_SUMMARY}")

    print()
