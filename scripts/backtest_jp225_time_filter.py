"""
JP225 SmaScalping — Sydney morning time filter backtest
Tests whether filtering 8am–11am Sydney/Melbourne (AEDT, UTC+11) improves results.

Deployed config (baseline):
  DI>30, RR=5.0, persist=2, adx_min=20, di_slope=True,
  adx_rising=True, atr_ratio_min=1.2, di_spread_min=15

Sydney/Melbourne AEDT = UTC+11
  8am–11am AEDT → 21:00–00:00 UTC (avoid_hours=[21, 22, 23, 0])
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators

# ── Config ────────────────────────────────────────────────────────────────────
CSV_PATH    = PROJECT_ROOT / "data" / "forex_raw" / "JP225_USD_5_Min.csv"
SPREAD      = 10.0          # ~10 pt spread on JP225
INITIAL_BAL = 10_000.0
RISK_PCT    = 0.015         # 1.5% per trade (deployed risk)

# Deployed params
DI_THRESHOLD  = 30.0
RR            = 5.0
PERSIST       = 2
ADX_MIN       = 20.0
DI_SLOPE      = True
ADX_RISING    = True
ATR_RATIO_MIN = 1.2
DI_SPREAD_MIN = 15.0

# Sydney morning = 8–11am AEDT = UTC 21,22,23,0
SYDNEY_MORNING_UTC = {21, 22, 23, 0}


# ── Data loading ──────────────────────────────────────────────────────────────
def load_data():
    df = pd.read_csv(CSV_PATH, parse_dates=["Date"])
    df["Date"] = pd.to_datetime(df["Date"], utc=True)
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    atr_avg = df["ATR"].rolling(20).mean()
    df["ATR_avg20"] = atr_avg
    df.dropna(subset=["SMA20", "SMA50", "SMA100",
                      "DIPlus", "DIMinus", "ADX", "ATR", "ATR_avg20"], inplace=True)
    return df


# ── Backtest engine ───────────────────────────────────────────────────────────
def run_backtest(df: pd.DataFrame, avoid_hours: set = None, label: str = ""):
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
    atr_avg  = df["ATR_avg20"].values
    idx      = df.index  # DatetimeIndex (UTC-aware)

    balance  = INITIAL_BAL
    trades   = []
    in_trade = False
    sl = tp = direction = None
    entry_bar = None

    for i in range(max(3, PERSIST), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    pnl = -balance * RISK_PCT
                    trades.append({"result": "LOSS", "pnl": pnl, "balance": balance + pnl,
                                   "direction": direction, "ts": idx[entry_bar]})
                    balance += pnl; in_trade = False
                elif h >= tp:
                    pnl = balance * RISK_PCT * RR
                    trades.append({"result": "WIN", "pnl": pnl, "balance": balance + pnl,
                                   "direction": direction, "ts": idx[entry_bar]})
                    balance += pnl; in_trade = False
            else:
                if h >= sl:
                    pnl = -balance * RISK_PCT
                    trades.append({"result": "LOSS", "pnl": pnl, "balance": balance + pnl,
                                   "direction": direction, "ts": idx[entry_bar]})
                    balance += pnl; in_trade = False
                elif l <= tp:
                    pnl = balance * RISK_PCT * RR
                    trades.append({"result": "WIN", "pnl": pnl, "balance": balance + pnl,
                                   "direction": direction, "ts": idx[entry_bar]})
                    balance += pnl; in_trade = False
            continue

        # ── Time filter ──
        if avoid_hours and idx[i].hour in avoid_hours:
            continue

        # ── DI persist ──
        di_plus_ok  = all(di_plus[i - j]  > DI_THRESHOLD for j in range(PERSIST))
        di_minus_ok = all(di_minus[i - j] > DI_THRESHOLD for j in range(PERSIST))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_ok and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_ok and di_minus[i] > di_plus[i])

        if not (is_buy or is_sell):
            continue

        # ── ADX min ──
        if adx_arr[i] < ADX_MIN:
            continue

        # ── ADX rising ──
        if ADX_RISING and adx_arr[i] <= adx_arr[i - 1]:
            continue

        # ── DI slope (DI+ rising for BUY, DI- rising for SELL) ──
        if DI_SLOPE:
            if is_buy  and di_plus[i]  <= di_plus[i - 1]:  continue
            if is_sell and di_minus[i] <= di_minus[i - 1]: continue

        # ── ATR ratio ──
        if atr_arr[i] < ATR_RATIO_MIN * atr_avg[i]:
            continue

        # ── DI spread ──
        if abs(di_plus[i] - di_minus[i]) < DI_SPREAD_MIN:
            continue

        # ── Entry not below/above 2-candle extremes ──
        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        # ── Build SL / TP ──
        atr_val = atr_arr[i]
        if is_buy:
            stop_dist = max(c - prev_low, atr_val)
            sl_price  = c - stop_dist - SPREAD
            risk      = c - sl_price
            if risk <= 0: continue
            direction = "BUY"; sl = sl_price; tp = c + risk * RR
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_price  = c + stop_dist + SPREAD
            risk      = sl_price - c
            if risk <= 0: continue
            direction = "SELL"; sl = sl_price; tp = c - risk * RR

        in_trade = True
        entry_bar = i

    if not trades:
        return None, []

    df_t   = pd.DataFrame(trades)
    n      = len(df_t)
    wins   = (df_t["result"] == "WIN").sum()
    wr     = wins / n * 100
    roi    = df_t["pnl"].sum() / INITIAL_BAL * 100
    rets   = df_t["pnl"] / INITIAL_BAL
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    equity = INITIAL_BAL + df_t["pnl"].cumsum().values
    peak   = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak * 100).min())
    avg_rr = df_t.apply(
        lambda r: RR if r["result"] == "WIN" else -1.0, axis=1).mean()

    stats = {
        "label":    label,
        "trades":   n,
        "wins":     int(wins),
        "win_rate": round(wr, 1),
        "roi":      round(roi, 2),
        "sharpe":   round(sharpe, 2),
        "max_dd":   round(max_dd, 2),
        "avg_rr":   round(avg_rr, 2),
    }
    return stats, df_t


# ── Hour-by-hour loss analysis ────────────────────────────────────────────────
def hour_breakdown(trades_df: pd.DataFrame):
    """Show win rate and P&L by UTC entry hour."""
    trades_df = trades_df.copy()
    trades_df["utc_hour"] = pd.to_datetime(trades_df["ts"], utc=True).dt.tz_localize(None).dt.hour
    grp = trades_df.groupby("utc_hour").agg(
        n=("result", "count"),
        wins=("result", lambda x: (x == "WIN").sum()),
        pnl=("pnl", "sum"),
    )
    grp["wr%"] = (grp["wins"] / grp["n"] * 100).round(1)
    grp["pnl"] = grp["pnl"].round(2)
    return grp


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("JP225_USD SmaScalping — Sydney Morning Filter Analysis")
    print("=" * 65)
    print(f"Config: DI>{DI_THRESHOLD}, RR={RR}, persist={PERSIST}, adx_min={ADX_MIN}")
    print(f"        adx_rising={ADX_RISING}, di_slope={DI_SLOPE}, "
          f"atr_ratio={ATR_RATIO_MIN}, di_spread_min={DI_SPREAD_MIN}")
    print(f"Sydney filter: 8–11am AEDT = UTC hours {sorted(SYDNEY_MORNING_UTC)}")
    print()

    df = load_data()
    period = f"{df.index[0].date()} → {df.index[-1].date()}"
    print(f"Data: {len(df)} bars  |  {period}")
    print()

    # Run baseline (no filter)
    base_stats, base_trades = run_backtest(df, avoid_hours=None, label="Baseline (no filter)")
    # Run with Sydney morning filter
    filt_stats, filt_trades = run_backtest(df, avoid_hours=SYDNEY_MORNING_UTC,
                                           label="Sydney 8–11am filtered (UTC 21,22,23,0)")

    # ── Results table ──
    header = f"{'Metric':<22} {'Baseline':>14} {'Filtered':>14} {'Delta':>10}"
    print(header)
    print("-" * 62)

    metrics = [
        ("Trades",    "trades",   ""),
        ("Win Rate%", "win_rate", "%"),
        ("ROI%",      "roi",      "%"),
        ("Sharpe",    "sharpe",   ""),
        ("Max DD%",   "max_dd",   "%"),
        ("Avg R",     "avg_rr",   "R"),
    ]
    for label, key, unit in metrics:
        b = base_stats[key]
        f = filt_stats[key]
        d = round(f - b, 2) if isinstance(b, float) else f - b
        sign = "+" if d > 0 else ""
        print(f"  {label:<20} {str(b)+unit:>14} {str(f)+unit:>14} {sign}{d}{unit:>8}")

    # ── Hour breakdown for baseline trades ──
    print()
    print("Entry hour analysis (baseline, all trades by UTC hour):")
    print("-" * 55)
    bd = hour_breakdown(base_trades)
    print(f"  {'UTC hr':>6}  {'n':>4}  {'WR%':>6}  {'P&L ($)':>10}  Sydney?")
    print("  " + "-" * 45)
    for hr, row in bd.iterrows():
        sydney = "← 8–11am Sydney" if hr in SYDNEY_MORNING_UTC else ""
        print(f"  {hr:>6}  {int(row['n']):>4}  {row['wr%']:>6.1f}%  "
              f"{row['pnl']:>10.2f}  {sydney}")

    # ── Trades filtered out ──
    if not base_trades.empty and not filt_trades.empty:
        blocked_hours = set(base_trades["ts"].dt.hour) & SYDNEY_MORNING_UTC
        n_blocked = base_trades[base_trades["ts"].dt.hour.isin(SYDNEY_MORNING_UTC)]
        print()
        print(f"Trades removed by filter: {len(n_blocked)} "
              f"(of {len(base_trades)} baseline trades)")
        if not n_blocked.empty:
            wins_b = (n_blocked["result"] == "WIN").sum()
            pnl_b  = n_blocked["pnl"].sum()
            wr_b   = wins_b / len(n_blocked) * 100
            print(f"  WR in filtered window: {wr_b:.1f}%  |  P&L: ${pnl_b:.2f}")

    # ── Verdict ──
    print()
    print("=" * 65)
    sharpe_delta = filt_stats["sharpe"] - base_stats["sharpe"]
    roi_delta    = filt_stats["roi"]    - base_stats["roi"]

    if sharpe_delta > 0.2 and roi_delta > 0:
        verdict = "✅ Filter HELPS — recommend adding avoid_hours=[21,22,23,0]"
    elif sharpe_delta < -0.2 or roi_delta < -5:
        verdict = "❌ Filter HURTS — do NOT apply"
    else:
        verdict = "⚠️  Marginal impact — not worth adding complexity"
    print(f"Verdict: {verdict}")
    print("=" * 65)


if __name__ == "__main__":
    main()
