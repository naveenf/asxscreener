"""
SmaScalping backtest for USD_JPY and GBP_JPY.

Downloads fresh 5m and 15m data from Oanda, then sweeps:
  DI thresholds: 25, 30, 35
  RR ratios: 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0
  DI persist: 1, 2

Spreads (typical Oanda):
  USD_JPY: 0.009 (0.9 pips)
  GBP_JPY: 0.018 (1.8 pips)
"""

import os, sys, time
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── load .env ─────────────────────────────────────────────────────────────────
for f in [PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"]:
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
        break

from oandapyV20 import API
import oandapyV20.endpoints.instruments as instruments
from backend.app.services.indicators import TechnicalIndicators

# ── config ────────────────────────────────────────────────────────────────────
PAIRS = {
    "USD_JPY": 0.009,   # ~0.9 pip spread
    "GBP_JPY": 0.018,   # ~1.8 pip spread
}
DATA_DIR      = PROJECT_ROOT / "data" / "forex_raw"
OUT_FILE      = PROJECT_ROOT / "data" / "backtest_sma_jpy_pairs.csv"
INITIAL_BAL   = 10_000.0
RISK_PCT      = 0.01

DI_THRESHOLDS = [25.0, 30.0, 35.0]
RR_RATIOS     = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
PERSIST_VALS  = [1, 2]
TF_MAP        = {"5m": "M5", "15m": "M15"}
TF_SUFFIX     = {"5m": "5_Min", "15m": "15_Min"}

# ── Oanda helpers ─────────────────────────────────────────────────────────────

def get_api():
    token = os.environ.get("OANDA_ACCESS_TOKEN")
    env   = os.environ.get("OANDA_ENV", "live")
    return API(access_token=token, environment=env,
               request_params={"timeout": 30})


def fetch_candles(api, symbol, granularity, start_time=None, count=5000):
    params = {"granularity": granularity,
              "alignmentTimezone": "America/New_York"}
    if start_time:
        params["from"]  = start_time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z")
        params["count"] = count
    else:
        params["count"] = count
    r = instruments.InstrumentsCandles(instrument=symbol, params=params)
    api.request(r)
    return r.response.get("candles", [])


def parse_candles(candles):
    rows = []
    for c in candles:
        if not c["complete"]:
            continue
        rows.append({
            "Date":   c["time"],
            "Open":   float(c["mid"]["o"]),
            "High":   float(c["mid"]["h"]),
            "Low":    float(c["mid"]["l"]),
            "Close":  float(c["mid"]["c"]),
            "Volume": int(c["volume"]),
        })
    return rows


def download_tf(api, symbol, tf_label):
    gran   = TF_MAP[tf_label]
    suffix = TF_SUFFIX[tf_label]
    csv    = DATA_DIR / f"{symbol}_{suffix}.csv"

    existing_df = None
    start_time  = None

    if csv.exists():
        try:
            existing_df = pd.read_csv(csv)
            existing_df["Date"] = pd.to_datetime(existing_df["Date"])
            start_time = existing_df["Date"].max()
            print(f"  [{symbol} {tf_label}] Existing file, last: {start_time}. Appending…")
        except Exception as e:
            print(f"  [{symbol} {tf_label}] Read error ({e}), starting fresh.")

    if start_time is None:
        start_time = datetime.utcnow() - timedelta(days=180)

    all_rows = []
    cur = start_time
    while True:
        candles = fetch_candles(api, symbol, gran, cur, count=5000)
        if not candles:
            break
        rows = parse_candles(candles)
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = pd.to_datetime(rows[-1]["Date"])
        if len(rows) < 5000:
            break
        cur = last_ts
        time.sleep(0.3)

    if not all_rows:
        print(f"  [{symbol} {tf_label}] No new candles.")
        return

    new_df = pd.DataFrame(all_rows)
    new_df["Date"] = pd.to_datetime(new_df["Date"])

    if existing_df is not None:
        combined = (pd.concat([existing_df, new_df])
                    .drop_duplicates(subset=["Date"], keep="last")
                    .sort_values("Date"))
    else:
        combined = new_df.sort_values("Date")

    combined.to_csv(csv, index=False)
    print(f"  [{symbol} {tf_label}] Saved {len(combined)} rows → {csv.name}")


# ── indicator prep ────────────────────────────────────────────────────────────

def load_and_prep(symbol, tf_label):
    suffix = TF_SUFFIX[tf_label]
    csv    = DATA_DIR / f"{symbol}_{suffix}.csv"
    df = pd.read_csv(csv, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    df.sort_index(inplace=True)
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    df = TechnicalIndicators.add_all_indicators(df)
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df.dropna(subset=["SMA20", "SMA50", "SMA100",
                      "DIPlus", "DIMinus", "ADX", "ATR"], inplace=True)
    return df


# ── backtest engine ───────────────────────────────────────────────────────────

def _close(balance, rr, win):
    pnl = balance * RISK_PCT * (rr if win else -1.0)
    return {"result": "WIN" if win else "LOSS", "pnl": pnl,
            "balance": balance + pnl}


def run_backtest(df, rr, di, persist, spread):
    closes   = df["Close"].values
    highs    = df["High"].values
    lows     = df["Low"].values
    sma20    = df["SMA20"].values
    sma50    = df["SMA50"].values
    sma100   = df["SMA100"].values
    di_plus  = df["DIPlus"].values
    di_minus = df["DIMinus"].values
    atr_arr  = df["ATR"].values

    balance  = INITIAL_BAL
    trades   = []
    in_trade = False
    sl = tp = direction = None

    for i in range(max(3, persist), len(df)):
        c, h, l = closes[i], highs[i], lows[i]

        if in_trade:
            if direction == "BUY":
                if l <= sl:
                    trades.append(_close(balance, rr, False))
                    balance = trades[-1]["balance"]; in_trade = False
                elif h >= tp:
                    trades.append(_close(balance, rr, True))
                    balance = trades[-1]["balance"]; in_trade = False
            else:
                if h >= sl:
                    trades.append(_close(balance, rr, False))
                    balance = trades[-1]["balance"]; in_trade = False
                elif l <= tp:
                    trades.append(_close(balance, rr, True))
                    balance = trades[-1]["balance"]; in_trade = False
            continue

        di_plus_pers  = all(di_plus[i - j]  > di for j in range(persist))
        di_minus_pers = all(di_minus[i - j] > di for j in range(persist))

        is_buy  = (c > sma20[i] and c > sma50[i] and c > sma100[i]
                   and di_plus_pers and di_plus[i] > di_minus[i])
        is_sell = (c < sma20[i] and c < sma50[i] and c < sma100[i]
                   and di_minus_pers and di_minus[i] > di_plus[i])

        if not (is_buy or is_sell):
            continue

        prev_low  = min(lows[i - 2],  lows[i - 1])
        prev_high = max(highs[i - 2], highs[i - 1])
        if is_buy  and c < prev_low:  continue
        if is_sell and c > prev_high: continue

        atr_val = atr_arr[i]
        if is_buy:
            stop_dist = max(c - prev_low, atr_val)
            sl_p  = c - stop_dist - spread
            risk  = c - sl_p
            if risk <= 0: continue
            direction = "BUY";  sl = sl_p;  tp = c + risk * rr
        else:
            stop_dist = max(prev_high - c, atr_val)
            sl_p  = c + stop_dist + spread
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
    roi    = df_t["pnl"].sum() / INITIAL_BAL * 100
    rets   = df_t["pnl"] / INITIAL_BAL
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    equity = df_t["balance"].values
    peak   = np.maximum.accumulate(equity)
    max_dd = float(((equity - peak) / peak * 100).min())
    return {"trades": n, "wins": int(wins), "win_rate": round(wr, 1),
            "roi": round(roi, 2), "sharpe": round(sharpe, 2),
            "max_dd": round(max_dd, 2)}


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("USD_JPY & GBP_JPY — SmaScalping Backtest")
    print("=" * 80)

    api = get_api()

    # 1. Download
    print("\n[1] Downloading data from Oanda…")
    for symbol in PAIRS:
        for tf in ["5m", "15m"]:
            download_tf(api, symbol, tf)

    # 2. Sweep
    print("\n[2] Running backtest sweep…")
    results = []

    for symbol, spread in PAIRS.items():
        for tf in ["5m", "15m"]:
            csv = DATA_DIR / f"{symbol}_{TF_SUFFIX[tf]}.csv"
            if not csv.exists():
                print(f"\n  [{symbol} {tf}] No data — skipping")
                continue
            try:
                df = load_and_prep(symbol, tf)
            except Exception as e:
                print(f"\n  [{symbol} {tf}] Load error: {e}")
                continue

            period = f"{df.index[0].date()} → {df.index[-1].date()}"
            print(f"\n  {symbol} {tf}  ({period}, {len(df)} bars)")
            print(f"  {'DI':>4} {'RR':>5} {'p':>2} | "
                  f"{'Trades':>6} {'WR%':>6} {'ROI%':>8} {'Sharpe':>7} {'MaxDD%':>8}")
            print("  " + "-" * 57)

            for di in DI_THRESHOLDS:
                for rr in RR_RATIOS:
                    for persist in PERSIST_VALS:
                        r = run_backtest(df, rr, di, persist, spread)
                        if r is None:
                            continue
                        tag = "✅" if r["roi"] > 0 and r["sharpe"] >= 1.0 else (
                              "⚠️" if r["roi"] > 0 else "❌")
                        print(f"  DI>{di:<4.0f} RR={rr:<4.1f} p={persist} | "
                              f"n={r['trades']:>4}  "
                              f"wr={r['win_rate']:>5.1f}%  "
                              f"roi={r['roi']:>7.2f}%  "
                              f"sharpe={r['sharpe']:>5.2f}  "
                              f"dd={r['max_dd']:>7.2f}%  {tag}")
                        results.append({
                            "symbol": symbol, "timeframe": tf,
                            "di_threshold": di, "rr": rr,
                            "di_persist": persist, "spread": spread,
                            "period": period, **r,
                        })

    if not results:
        print("\nNo results.")
        return

    df_r = pd.DataFrame(results)
    df_r.to_csv(OUT_FILE, index=False)
    print(f"\nAll results saved → {OUT_FILE}")

    # 3. Summary — best per symbol+timeframe
    print("\n" + "=" * 80)
    print("SUMMARY — Best by Sharpe (min 15 trades, ROI > 0)")
    print("=" * 80)

    for symbol in PAIRS:
        for tf in ["5m", "15m"]:
            sub = df_r[(df_r["symbol"] == symbol) &
                       (df_r["timeframe"] == tf) &
                       (df_r["trades"] >= 15) &
                       (df_r["roi"] > 0)]
            if sub.empty:
                print(f"\n  {symbol} {tf}: no profitable configs with ≥15 trades")
                continue
            best = sub.loc[sub["sharpe"].idxmax()]
            print(f"\n  {symbol} {tf}:")
            print(f"    Best:  DI>{best['di_threshold']:.0f}  RR={best['rr']:.1f}  "
                  f"persist={best['di_persist']:.0f}")
            print(f"    Stats: Trades={best['trades']:.0f}  WR={best['win_rate']:.1f}%  "
                  f"ROI={best['roi']:.2f}%  Sharpe={best['sharpe']:.2f}  "
                  f"MaxDD={best['max_dd']:.2f}%")

    # 4. Positive configs count
    print("\n" + "-" * 80)
    print("Positive ROI configs summary:")
    for symbol in PAIRS:
        for tf in ["5m", "15m"]:
            sub = df_r[(df_r["symbol"] == symbol) & (df_r["timeframe"] == tf)]
            pos = sub[sub["roi"] > 0]
            total = len(sub)
            print(f"  {symbol} {tf}: {len(pos)}/{total} configs profitable  "
                  f"| best Sharpe={sub['sharpe'].max():.2f}  "
                  f"best ROI={sub['roi'].max():.2f}%")


if __name__ == "__main__":
    main()
