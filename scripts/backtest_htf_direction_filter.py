"""
HTF (4H / Daily) trend-direction gate on top of production SmaScalping configs
================================================================================
Research question: does gating entries on higher-timeframe trend direction
(only LONG when HTF trend is up, only SHORT when HTF trend is down) improve
win rate, drawdown, and Sharpe/expectancy for the 5 currently-active live
pairs — XAU_USD, XAG_USD, JP225_USD, NAS100_USD, BCO_USD?

This does NOT change any production config. Every pair's entry filters, RR,
risk_pct and stop logic are read verbatim from best_strategies.json. The ONLY
thing that differs between variants is an extra AND-gate on top of the
existing signal.

Variants per pair, run over the SAME (maximum overlapping) window:
  (a) baseline    — production config, no HTF filter (control)
  (b) +4H         — require H4 trend aligned with trade direction
  (c) +Daily      — require Daily trend aligned with trade direction

HTF trend signal: Close vs SMA(50) on the HTF series (close > SMA50 = up,
close < SMA50 = down, anything else / NaN = neutral -> blocks BOTH
directions). SMA50 mirrors this project's own convention (SmaScalping's
SMA20/50/100 stack; see indicators.py / sma_scalping_detector.py) and is the
only period that both the H4 file (~3,083 bars) and the thin Daily file
(~515 bars) can support with a meaningful warm-up.

No-lookahead join: every 15m/5m signal bar is matched to the last HTF bar
that was FULLY CLOSED as of that signal bar's own close time, via
merge_asof(direction="backward") on real close timestamps (HTF bar "Date" is
its OPEN time per download_forex.py's Oanda convention, so htf_close =
htf_open + granularity is compared against base_close = base_open +
base_granularity — never the other way around).

Engine: the same gap-priced, sparse-table replay engine validated in
scripts/backtest_xag_walkforward_retune.py (0 mismatches vs the real
SmaScalpingDetector.analyze() bar-by-bar loop). Gap-priced stops, broker
SL/TP fill intrabar, one position at a time, compounding equity. BCO_USD is
force-flattened before its weekly close (ALWAYS_CLOSE_PAIRS in tasks.py); the
other 4 pairs are run naked (not flattened), matching this repo's established
convention for XAU/XAG/JP225/NAS100 in the Sep 2026 full-history replay and
walk-forward scripts.

Window: for each pair, base-timeframe data is restricted to the overlap
between [base file coverage] and [HTF file coverage] (~2024-09-19 onward,
bounded further to ~2025-09 for JP225 since it runs on 5m, which this repo
only retains ~1 year of). Indicators are computed on each pair's FULL base
file first (so SMA/ADX warm-up is unaffected), then only entries inside the
overlap window are allowed to open — exits are found normally past the window
edge, same as any live trade would be.

Output: data/backtest_htf_direction_filter.csv (one row per pair x variant).
⚠️ The committed version of this file is TRIMMED to XAG_USD and JP225_USD only
— the two pairs whose gate was actually adopted (see CLAUDE.md Recent Changes).
XAU_USD/NAS100_USD/BCO_USD were tested and rejected (see that entry for why);
re-running this script regenerates the full 5-pair file locally, which is
correct and expected to differ from what's committed.

Usage: python scripts/backtest_htf_direction_filter.py
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app.services.indicators import TechnicalIndicators  # noqa: E402

DATA_DIR = ROOT / "data" / "forex_raw"
META = ROOT / "data" / "metadata" / "best_strategies.json"
OUT = ROOT / "data" / "backtest_htf_direction_filter.csv"

INITIAL_BALANCE = 10_000.0
GAP_THRESHOLD = pd.Timedelta(hours=6)
HTF_TREND_PERIOD = 50

# Oanda spreads (Standard Constants convention used throughout this repo's
# sweep scripts; matches backtest_prod_vs_live_comparison.py).
SPREADS = {
    "XAU_USD": 0.50, "XAG_USD": 0.03, "BCO_USD": 0.04,
    "JP225_USD": 17.0, "NAS100_USD": 2.30,
}

PAIRS = ["XAU_USD", "XAG_USD", "JP225_USD", "NAS100_USD", "BCO_USD"]

# market_close_schedule.WEEKLY_CLOSE_UTC, restricted to these 5 pairs.
WEEKLY_CLOSE = {
    "XAU_USD": (4, 21, 0), "XAG_USD": (4, 21, 0), "BCO_USD": (4, 21, 0),
    "NAS100_USD": (4, 21, 0), "JP225_USD": (4, 6, 0),
}
BLOCK_MIN_BEFORE, CLOSE_MIN_BEFORE = 65, 60
ALWAYS_CLOSE_PAIRS = {"BCO_USD"}   # tasks.py — the only pair force-flattened

TF_SUFFIX = {"15m": "15_Min", "5m": "5_Min"}
TF_DELTA = {"15m": pd.Timedelta(minutes=15), "5m": pd.Timedelta(minutes=5)}


# ---------------------------------------------------------------------------
# Data + indicators
# ---------------------------------------------------------------------------
def load_bars(symbol, suffix):
    fn = DATA_DIR / f"{symbol}_{suffix}.csv"
    df = pd.read_csv(fn, parse_dates=["Date"]).set_index("Date").sort_index()
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df[~df.index.duplicated(keep="last")]


def prep_base(df):
    df = TechnicalIndicators.add_all_indicators(df.copy())
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df["ATR_avg20"] = df["ATR"].shift(1).rolling(20).mean()
    df["Vol_avg20"] = df["Volume"].shift(1).rolling(20).mean()
    return df


def htf_trend(df, granularity_delta, period=HTF_TREND_PERIOD):
    """Close vs SMA(period) on an HTF series -> +1 up / -1 down / 0 neutral,
    aligned to each HTF bar's own CLOSE time (open time + granularity) so a
    backward as-of join never sees a still-forming bar."""
    df = df.sort_index().copy()
    sma = df["Close"].rolling(period).mean()
    trend = np.where(df["Close"] > sma, 1, np.where(df["Close"] < sma, -1, 0))
    trend = np.where(sma.isna().values, 0, trend)  # no valid SMA yet -> neutral (blocks both)
    out = pd.DataFrame({"htf_close": df.index + granularity_delta, "trend": trend})
    return out.sort_values("htf_close")


def attach_htf(base_df, base_tf, htf_df, htf_delta):
    """As-of backward join: for each base bar, the trend of the last HTF bar
    that had FULLY CLOSED by the time this base bar's own close is known."""
    left = pd.DataFrame({"base_close": base_df.index + TF_DELTA[base_tf]},
                        index=base_df.index).reset_index().rename(columns={"Date": "base_open"})
    left = left.sort_values("base_close")
    merged = pd.merge_asof(left, htf_df, left_on="base_close", right_on="htf_close",
                            direction="backward")
    merged = merged.set_index("base_open").sort_index()
    return merged["trend"].reindex(base_df.index).fillna(0).astype(int)


# ---------------------------------------------------------------------------
# Signal builder -- verbatim port of SmaScalpingDetector.analyze
# (identical to scripts/backtest_xag_walkforward_retune.py::build_signals)
# ---------------------------------------------------------------------------
def build_signals(df, params):
    di_threshold = float(params.get("di_threshold", 35.0))
    adx_min = float(params.get("adx_min", 0.0))
    di_persist = max(1, int(params.get("di_persist", 1)))
    adx_rising = bool(params.get("adx_rising", False))
    sma_ordered = bool(params.get("sma_ordered", False))
    di_spread_min = float(params.get("di_spread_min", 0.0))
    rsi_filter = bool(params.get("rsi_filter", False))
    body_ratio_min = float(params.get("body_ratio_min", 0.0))
    vol_ratio_min = float(params.get("vol_ratio_min", 0.0))
    atr_ratio_min = float(params.get("atr_ratio_min", 0.0))
    di_slope = bool(params.get("di_slope", False))
    avoid_hours = set(params.get("avoid_hours", []))

    c, o, h, l = (df[x] for x in ("Close", "Open", "High", "Low"))
    s20, s50, s100 = df["SMA20"], df["SMA50"], df["SMA100"]
    dp, dm, adx, atr = df["DIPlus"], df["DIMinus"], df["ADX"], df["ATR"]

    valid = pd.concat([s20, s50, s100, dp, dm, adx, l, h, o], axis=1).notna().all(axis=1)
    adx_ok = adx >= adx_min

    dp_pers = (dp > di_threshold)
    dm_pers = (dm > di_threshold)
    for j in range(1, di_persist):
        dp_pers &= (dp.shift(j) > di_threshold)
        dm_pers &= (dm.shift(j) > di_threshold)

    adx_rising_ok = (adx > adx.shift(1)) if adx_rising else pd.Series(True, index=df.index)

    if sma_ordered:
        ord_buy, ord_sell = (s20 > s50) & (s50 > s100), (s20 < s50) & (s50 < s100)
    else:
        ord_buy = ord_sell = pd.Series(True, index=df.index)

    spr_buy = (dp - dm) >= di_spread_min
    spr_sell = (dm - dp) >= di_spread_min

    if rsi_filter and "RSI" in df.columns:
        rsi = df["RSI"]
        rsi_buy = (rsi > 50.0) & (rsi < 75.0) & rsi.notna()
        rsi_sell = (rsi > 25.0) & (rsi < 50.0) & rsi.notna()
    else:
        rsi_buy = rsi_sell = pd.Series(True, index=df.index)

    if body_ratio_min > 0.0:
        rng = h - l
        body_buy = ((c - o) / rng >= body_ratio_min).where(rng > 0, False)
        body_sell = ((o - c) / rng >= body_ratio_min).where(rng > 0, False)
    else:
        body_buy = body_sell = pd.Series(True, index=df.index)

    if vol_ratio_min > 0.0 and "Volume" in df.columns:
        va = df["Vol_avg20"]
        vol_ok = (va > 0) & (df["Volume"] >= vol_ratio_min * va)
    else:
        vol_ok = pd.Series(True, index=df.index)

    if atr_ratio_min > 0.0:
        aa = df["ATR_avg20"]
        atr_ok = (aa > 0) & (atr >= atr_ratio_min * aa)
    else:
        atr_ok = pd.Series(True, index=df.index)

    if di_slope:
        slope_buy, slope_sell = dp > dp.shift(2), dm > dm.shift(2)
    else:
        slope_buy = slope_sell = pd.Series(True, index=df.index)

    if avoid_hours:
        sess = ~pd.Series(df.index.hour, index=df.index).isin(avoid_hours)
    else:
        sess = pd.Series(True, index=df.index)

    common = valid & adx_ok & adx_rising_ok & vol_ok & atr_ok & sess
    is_buy = (common & (c > s20) & (c > s50) & (c > s100) & dp_pers & (dp > dm)
              & ord_buy & spr_buy & rsi_buy & body_buy & slope_buy).fillna(False)
    is_sell = (common & (c < s20) & (c < s50) & (c < s100) & dm_pers & (dm > dp)
               & ord_sell & spr_sell & rsi_sell & body_sell & slope_sell).fillna(False)
    is_sell &= ~is_buy
    return is_buy.values, is_sell.values


# ---------------------------------------------------------------------------
# Sparse-table "first index at or after s whose value crosses x"
# (identical to scripts/backtest_xag_walkforward_retune.py::RangeExtreme)
# ---------------------------------------------------------------------------
class RangeExtreme:
    def __init__(self, v, mode):
        self.mode = mode
        self.n = len(v)
        K = 1
        while (1 << K) < self.n:
            K += 1
        K += 1
        npad = 1 << (K - 1)
        self.npad = npad
        self.K = K
        neutral = np.inf if mode == "min" else -np.inf
        base = np.full(npad, neutral, dtype=np.float64)
        base[: self.n] = v
        tab = np.empty((K, npad), dtype=np.float64)
        tab[0] = base
        for k in range(1, K):
            span = 1 << (k - 1)
            shifted = np.concatenate([tab[k - 1][span:], np.full(span, neutral)])
            tab[k] = np.minimum(tab[k - 1], shifted) if mode == "min" \
                else np.maximum(tab[k - 1], shifted)
        self.tab = tab

    def first_cross(self, starts, x):
        npad, n = self.npad, self.n
        pos = np.clip(starts.astype(np.int64), 0, npad)
        for k in range(self.K - 1, -1, -1):
            width = 1 << k
            can = pos + width <= npad
            blk = self.tab[k][np.where(can, np.minimum(pos, npad - 1), 0)]
            fails = blk > x if self.mode == "min" else blk < x
            pos = np.where(can & fails, pos + width, pos)
        return np.where(pos < n, pos, n)


# ---------------------------------------------------------------------------
# Precomputed per-bar trade geometry and outcomes
# (identical to scripts/backtest_xag_walkforward_retune.py::Outcomes)
# ---------------------------------------------------------------------------
class Outcomes:
    def __init__(self, df, spread, weekly_close):
        self.idx = df.index
        n = len(df)
        self.n = n
        self.c = df["Close"].values.astype(float)
        self.o = df["Open"].values.astype(float)
        self.h = df["High"].values.astype(float)
        self.l = df["Low"].values.astype(float)
        atr = df["ATR"].values.astype(float)
        self.is_gap = (df.index.to_series().diff() > GAP_THRESHOLD).values

        prev_low = np.full(n, np.nan)
        prev_high = np.full(n, np.nan)
        prev_low[2:] = np.minimum(self.l[:-2], self.l[1:-1])
        prev_high[2:] = np.maximum(self.h[:-2], self.h[1:-1])

        price = self.c
        with np.errstate(invalid="ignore"):
            sd_b = np.maximum(price - prev_low, np.nan_to_num(atr, nan=-np.inf))
            sd_s = np.maximum(prev_high - price, np.nan_to_num(atr, nan=-np.inf))
        sd_b = np.where(np.isnan(atr), price - prev_low, sd_b)
        sd_s = np.where(np.isnan(atr), prev_high - price, sd_s)

        self.sl_b = price - sd_b - spread
        self.sl_s = price + sd_s + spread
        self.risk_b = price - self.sl_b
        self.risk_s = self.sl_s - price

        self.ok_b = (price >= prev_low) & (self.risk_b > 0) & ~np.isnan(prev_low)
        self.ok_s = (price <= prev_high) & (self.risk_s > 0) & ~np.isnan(prev_high)
        self.ok_b[:2] = False
        self.ok_s[:2] = False

        self.rmin = RangeExtreme(self.l, "min")
        self.rmax = RangeExtreme(self.h, "max")

        wd, hh, mm = weekly_close
        close_dt = df.index.normalize() + pd.Timedelta(hours=hh, minutes=mm)
        mins_to = (close_dt - df.index).total_seconds() / 60.0
        in_win = (df.index.dayofweek == wd) & (mins_to >= 0) & (mins_to <= BLOCK_MIN_BEFORE)
        self.block_mask = np.asarray(in_win)
        self.close_mask = np.asarray(in_win & (mins_to <= CLOSE_MIN_BEFORE))
        self._close_positions = np.where(self.close_mask)[0]

        self._cache = {}

    def table(self, rr, flatten):
        key = (rr, flatten)
        if key in self._cache:
            return self._cache[key]
        n = self.n
        starts = np.arange(n) + 1
        res = {}
        for d in ("BUY", "SELL"):
            if d == "BUY":
                sl, risk = self.sl_b, self.risk_b
                tp = self.c + risk * rr
                j_sl = self.rmin.first_cross(starts, sl)
                j_tp = self.rmax.first_cross(starts, tp)
            else:
                sl, risk = self.sl_s, self.risk_s
                tp = self.c - risk * rr
                j_sl = self.rmax.first_cross(starts, sl)
                j_tp = self.rmin.first_cross(starts, tp)

            j_pc = np.full(n, n, dtype=np.int64)
            if flatten and len(self._close_positions):
                p = np.searchsorted(self._close_positions, starts, side="left")
                j_pc = np.where(p < len(self._close_positions),
                                self._close_positions[np.minimum(p, len(self._close_positions) - 1)], n)

            j = np.minimum(np.minimum(j_sl, j_tp), j_pc)
            hit_sl = (j_sl == j) & (j < n)
            hit_tp = (~hit_sl) & (j_tp == j) & (j < n)
            hit_pc = (~hit_sl) & (~hit_tp) & (j < n)

            jj = np.clip(j, 0, n - 1)
            gap = self.is_gap[jj]
            op = self.o[jj]

            fill = np.where(hit_sl, sl, np.where(hit_tp, tp, self.c[jj]))
            if d == "BUY":
                gap_sl = hit_sl & gap & (op < sl)
                gap_tp = hit_tp & gap & (op > tp)
            else:
                gap_sl = hit_sl & gap & (op > sl)
                gap_tp = hit_tp & gap & (op < tp)
            fill = np.where(gap_sl | gap_tp, op, fill)

            r = ((fill - self.c) / risk) if d == "BUY" else ((self.c - fill) / risk)
            r = np.where(j < n, r, np.nan)
            res[d] = (j, r)
        self._cache[key] = res
        return res


def walk(out, cand_buy, cand_sell, rr, flatten):
    """Greedy one-position-at-a-time sequencing over admitted signal bars."""
    tab = out.table(rr, flatten)
    n = out.n
    cand = (cand_buy & out.ok_b) | (cand_sell & out.ok_s)
    if flatten:
        cand = cand & ~out.block_mask
    bars = np.where(cand)[0]
    if len(bars) == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64), np.array([])

    jb, rb = tab["BUY"]
    js, rs = tab["SELL"]
    ent, ex, rr_out = [], [], []
    free_at = -1
    for i in bars:
        if i < free_at:
            continue
        if cand_buy[i]:
            j, r = jb[i], rb[i]
        else:
            j, r = js[i], rs[i]
        if j >= n or not np.isfinite(r):
            break
        ent.append(i); ex.append(j); rr_out.append(r)
        free_at = j + 1
    return (np.asarray(ent, dtype=np.int64), np.asarray(ex, dtype=np.int64),
            np.asarray(rr_out, dtype=float))


# ---------------------------------------------------------------------------
# Metrics (identical conventions to backtest_xag_walkforward_retune.py)
# ---------------------------------------------------------------------------
def equity_curve(rs, risk_pct):
    return INITIAL_BALANCE * np.cumprod(1.0 + risk_pct * rs)


def max_dd(eq):
    if len(eq) == 0:
        return 0.0
    full = np.concatenate([[INITIAL_BALANCE], eq])
    peak = np.maximum.accumulate(full)
    return float(((full - peak) / peak * 100).min())


def longest_loss_streak(rs):
    best = cur = 0
    for r in rs:
        cur = cur + 1 if r <= 0 else 0
        if cur > best:
            best = cur
    return best


def daily_sharpe(exit_times, rs, risk_pct, t0, t1):
    if len(rs) < 3:
        return np.nan
    eq = equity_curve(rs, risk_pct)
    days = pd.DatetimeIndex(exit_times).normalize()
    grid = pd.date_range(t0.normalize(), t1.normalize(), freq="D")
    grid = grid[grid.dayofweek < 5]
    if len(grid) < 5:
        return np.nan
    pos = np.searchsorted(grid.values, days.values, side="left")
    pos = np.clip(pos, 0, len(grid) - 1)
    arr = np.full(len(grid), np.nan)
    arr[pos] = eq
    arr[0] = arr[0] if np.isfinite(arr[0]) else INITIAL_BALANCE
    s = pd.Series(arr).ffill().values
    rets = np.diff(s) / s[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) < 3 or rets.std(ddof=1) == 0:
        return np.nan
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))


def metrics(exit_times, rs, risk_pct, t0, t1):
    n = len(rs)
    if n == 0:
        return {k: np.nan for k in
                ("trades", "win_rate", "exp_R", "total_R", "roi_pct", "max_dd_pct",
                 "sharpe_daily", "pf", "streak", "h1_R", "h2_R", "worst_R")} | {"trades": 0}
    eq = equity_curve(rs, risk_pct)
    roi = (eq[-1] / INITIAL_BALANCE - 1) * 100
    dd = max_dd(eq)
    gains = rs[rs > 0].sum(); losses = -rs[rs <= 0].sum()
    half = n // 2
    return {
        "trades": n,
        "win_rate": round(float((rs > 0).mean() * 100), 1),
        "exp_R": round(float(rs.mean()), 4),
        "total_R": round(float(rs.sum()), 1),
        "roi_pct": round(float(roi), 2),
        "max_dd_pct": round(dd, 2),
        "sharpe_daily": round(daily_sharpe(exit_times, rs, risk_pct, t0, t1), 2),
        "pf": round(float(gains / losses), 2) if losses > 0 else np.nan,
        "streak": longest_loss_streak(rs),
        "h1_R": round(float(rs[:half].mean()), 4) if half >= 1 else np.nan,
        "h2_R": round(float(rs[half:].mean()), 4) if n - half >= 1 else np.nan,
        "worst_R": round(float(rs.min()), 2),
    }


def passes_bar(m):
    """This repo's promotion bar: >=60 trades, positive mean R in BOTH halves
    of a split-half check."""
    if m["trades"] < 60:
        return False
    h1, h2 = m["h1_R"], m["h2_R"]
    return bool(np.isfinite(h1) and np.isfinite(h2) and h1 > 0 and h2 > 0)


# ---------------------------------------------------------------------------
# Per-pair run
# ---------------------------------------------------------------------------
def run_pair(symbol, cfg):
    strat = cfg["strategies"][0]
    tf = strat["timeframe"]
    rr = strat["target_rr"]
    risk_pct = cfg["risk_pct"]
    params = strat["params"]
    spread = SPREADS[symbol]
    weekly_close = WEEKLY_CLOSE[symbol]
    flatten = symbol in ALWAYS_CLOSE_PAIRS

    base = prep_base(load_bars(symbol, TF_SUFFIX[tf]))
    h4_raw = load_bars(symbol, "4_Hour")
    d_raw = load_bars(symbol, "Daily")

    h4_trend = htf_trend(h4_raw, pd.Timedelta(hours=4))
    d_trend = htf_trend(d_raw, pd.Timedelta(days=1))

    base["htf4_trend"] = attach_htf(base, tf, h4_trend, pd.Timedelta(hours=4))
    base["htfD_trend"] = attach_htf(base, tf, d_trend, pd.Timedelta(days=1))

    # Overlap window: HTF file coverage (own close time) intersected with base
    # file coverage. Baseline and both HTF variants all run on this SAME window
    # so the comparison is apples-to-apples; only the HTF gate differs.
    htf_start = max(h4_trend["htf_close"].min(), d_trend["htf_close"].min())
    htf_end = min(h4_trend["htf_close"].max(), d_trend["htf_close"].max())
    base_close = base.index + TF_DELTA[tf]
    window_mask = (base_close >= htf_start) & (base_close <= htf_end)
    win_start, win_end = base.index[window_mask].min(), base.index[window_mask].max()

    out = Outcomes(base, spread, weekly_close)
    is_buy, is_sell = build_signals(base, params)
    window_mask = np.asarray(window_mask)
    is_buy = is_buy & window_mask
    is_sell = is_sell & window_mask

    htf4_up = (base["htf4_trend"].values == 1)
    htf4_dn = (base["htf4_trend"].values == -1)
    htfD_up = (base["htfD_trend"].values == 1)
    htfD_dn = (base["htfD_trend"].values == -1)

    variants = {
        "baseline": (is_buy, is_sell),
        "+4H": (is_buy & htf4_up, is_sell & htf4_dn),
        "+Daily": (is_buy & htfD_up, is_sell & htfD_dn),
    }

    rows = []
    base_trades = None
    for label, (vb, vs) in variants.items():
        ent, ex, rs = walk(out, vb, vs, rr, flatten)
        xt = base.index[ex] if len(ex) else pd.DatetimeIndex([])
        m = metrics(xt, rs, risk_pct, win_start, win_end)
        if label == "baseline":
            base_trades = m["trades"]
        row = {
            "pair": symbol, "variant": label, "tf": tf, "target_rr": rr,
            "risk_pct": risk_pct, "window_start": win_start, "window_end": win_end,
            **m,
            "pct_of_baseline": round(100 * m["trades"] / base_trades, 1) if base_trades else np.nan,
            "promotion_bar_pass": passes_bar(m),
        }
        rows.append(row)
        print(f"  [{symbol}] {label:10s} n={m['trades']:4d} ({row['pct_of_baseline']:>5}% of base)  "
              f"WR={m['win_rate']:>5}%  expR={m['exp_R']:>7}  ROI={m['roi_pct']:>8}%  "
              f"Sharpe={m['sharpe_daily']:>6}  MaxDD={m['max_dd_pct']:>7}%  PF={m['pf']:>5}  "
              f"bar_pass={row['promotion_bar_pass']}")
    return rows


def main():
    cfgs = json.loads(META.read_text())
    all_rows = []
    for symbol in PAIRS:
        print(f"\n=== {symbol} ===")
        all_rows.extend(run_pair(symbol, cfgs[symbol]))
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT, index=False)
    print(f"\nSaved {len(df)} rows -> {OUT}")


if __name__ == "__main__":
    main()
