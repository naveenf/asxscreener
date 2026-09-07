"""
XAG_USD walk-forward retune
===========================
Mirrors the methodology that produced the BCO_USD retune: select a candidate
using ONLY the fit window (2023-09-20 -> 2025-12-31), then measure it once on
a held-out 2026 window that was never used for selection.

Nothing here is taken on trust from CLAUDE.md or docs/. Every number is derived
from data/forex_raw/XAG_USD_{15,5}_Min.csv using the entry logic of
backend/app/services/sma_scalping_detector.py and the real
backend.app.services.indicators.TechnicalIndicators.

Engine
------
The signal builder and the trade mechanics are ported from
scripts/backtest_full_history_replay.py (build_signals / replay), whose fidelity
against the REAL detector was re-verified for XAG in this session: 300 sampled
bars (150 signal + 150 non-signal), 0 signal mismatches, 0 stop-loss mismatches.

Because the grid is ~100k cells, the bar-by-bar replay loop is replaced by a
precomputed outcome table that is mathematically identical for a pair with NO
stop-move stage (XAG has none in PAIR_LOCK_CONFIGS):

  * entry price / SL / TP at bar i depend only on the bar (Close, 2-bar
    structural level, ATR, spread, rr) -- not on which filters admitted it;
  * with no stop move, the exit of a trade opened at i is the first later bar
    that touches SL or TP, found with a sparse-table descent (exact, vectorised);
  * one-position-at-a-time sequencing is then a greedy walk over signal bars.

Equivalence to the reference replay loop is asserted at startup
(--verify runs both on the incumbent config and compares every trade).

Methodology guards preserved from the reference engine
------------------------------------------------------
 1. GAP PRICING. A stop hit on a session-gap bar (>6h since the previous bar)
    books at that bar's OPEN when the open is already past the stop -- never a
    flat -1R. Take-profit gaps are priced the same way, in our favour.
 2. BROKER SL/TP FILL INTRABAR (they rest at Oanda), tested against high/low.
    Stop is tested before target, so same-bar ambiguity resolves against us.
 3. OUR STOP MOVE IS POLL-LIMITED, never intrabar. The stop-stage grid samples
    price at 5m bar closes where the 5m file covers the period and falls back to
    the 15m close otherwise (which UNDER-fires stages -> conservative).
 4. One position at a time, compounding equity, risk_pct from best_strategies.json.
 5. Weekly pre-close flattening is OFF for the primary run (XAG is not in
    ALWAYS_CLOSE_PAIRS); a sensitivity run with it ON is reported.

Outputs (data/):
  backtest_xag_wf_grid.csv            full filter/RR grid, fit + held-out columns
  backtest_xag_wf_hypotheses.csv      sma_ordered / rsi_filter paired grid
  backtest_xag_wf_marginals.csv       paired-cell marginal analysis (fit only)
  backtest_xag_wf_final.csv           incumbent vs candidate, all windows
  backtest_xag_wf_sections.csv        6-month sections
  backtest_xag_wf_stage_grid.csv      stop-move stage grid
  backtest_xag_wf_5m.csv              provisional 5m grid

Usage:  python scripts/backtest_xag_walkforward_retune.py [--verify] [--quick]
"""

import itertools
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
OUT = ROOT / "data"

SYMBOL = "XAG_USD"
SPREAD = 0.003          # as used by every existing XAG sweep in this repo
INITIAL_BALANCE = 10_000.0
GAP_THRESHOLD = pd.Timedelta(hours=6)

FIT_END = pd.Timestamp("2025-12-31 23:59:59")
OOS_START = pd.Timestamp("2026-01-01 00:00:00")

# market_close_schedule.WEEKLY_CLOSE_UTC[XAG_USD] -> Friday 21:00
WEEKLY_CLOSE = (4, 21, 0)
BLOCK_MIN_BEFORE, CLOSE_MIN_BEFORE = 65, 60


# ---------------------------------------------------------------------------
# Data + indicators (the real module; indicators are never re-implemented)
# ---------------------------------------------------------------------------
def load_bars(tf):
    fn = DATA_DIR / f"{SYMBOL}_{'15' if tf == '15m' else '5'}_Min.csv"
    df = pd.read_csv(fn, parse_dates=["Date"]).set_index("Date").sort_index()
    if df.index.tz is not None:
        df.index = df.index.tz_convert(None)
    return df[~df.index.duplicated(keep="last")]


def prep(df):
    df = TechnicalIndicators.add_all_indicators(df.copy())
    for p, col in [(20, "SMA20"), (50, "SMA50"), (100, "SMA100")]:
        df[col] = df["Close"].rolling(p).mean()
    df["ATR_avg20"] = df["ATR"].shift(1).rolling(20).mean()
    df["Vol_avg20"] = df["Volume"].shift(1).rolling(20).mean()
    return df


# ---------------------------------------------------------------------------
# Signal builder -- verbatim port of SmaScalpingDetector.analyze
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
# ---------------------------------------------------------------------------
class RangeExtreme:
    """Vectorised `first j >= s with v[j] <= x` (mode "min") or `>= x` (mode
    "max"), via a sparse-table descent.

    The array is padded up to a power of two with a NEUTRAL sentinel (+inf for
    min, -inf for max) so that a block of every size always exists -- without
    that padding the descent cannot skip near the end of the array and silently
    returns wrong indices for late bars.
    """

    def __init__(self, v, mode):
        self.mode = mode
        self.n = len(v)
        K = 1
        while (1 << K) < self.n:
            K += 1
        K += 1                                  # need levels 0..K-1, block 2^(K-1) >= n
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
# ---------------------------------------------------------------------------
class Outcomes:
    def __init__(self, df, spread):
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

        # structural-validity + positive-risk gate (filter independent)
        self.ok_b = (price >= prev_low) & (self.risk_b > 0) & ~np.isnan(prev_low)
        self.ok_s = (price <= prev_high) & (self.risk_s > 0) & ~np.isnan(prev_high)
        self.ok_b[:2] = False
        self.ok_s[:2] = False

        self.rmin = RangeExtreme(self.l, "min")
        self.rmax = RangeExtreme(self.h, "max")

        # weekly pre-close masks
        wd, hh, mm = WEEKLY_CLOSE
        close_dt = df.index.normalize() + pd.Timedelta(hours=hh, minutes=mm)
        mins_to = (close_dt - df.index).total_seconds() / 60.0
        in_win = (df.index.dayofweek == wd) & (mins_to >= 0) & (mins_to <= BLOCK_MIN_BEFORE)
        self.block_mask = np.asarray(in_win)
        self.close_mask = np.asarray(in_win & (mins_to <= CLOSE_MIN_BEFORE))
        self._close_positions = np.where(self.close_mask)[0]

        self._cache = {}

    def table(self, rr, flatten):
        """(exit_j, r) arrays per direction for target_rr `rr`."""
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
            reason = np.where(hit_sl, np.where(gap_sl, 4, 1),
                              np.where(hit_tp, np.where(gap_tp, 5, 2),
                                       np.where(hit_pc, 3, 0)))
            res[d] = (j, r, reason)
        self._cache[key] = res
        return res


def walk(out, is_buy, is_sell, rr, flatten):
    """Greedy one-position-at-a-time sequencing over admitted signal bars."""
    tab = out.table(rr, flatten)
    n = out.n
    cand = (is_buy & out.ok_b) | (is_sell & out.ok_s)
    if flatten:
        cand = cand & ~out.block_mask
    bars = np.where(cand)[0]
    if len(bars) == 0:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64), np.array([]), np.array([])

    jb, rb, qb = tab["BUY"]
    js, rs, qs = tab["SELL"]
    ent, ex, rr_out, reas = [], [], [], []
    free_at = -1
    for i in bars:
        if i < free_at:
            continue
        if is_buy[i]:
            j, r, q = jb[i], rb[i], qb[i]
        else:
            j, r, q = js[i], rs[i], qs[i]
        if j >= n or not np.isfinite(r):
            break             # never exits: stays open to end of data, blocking the rest
        ent.append(i); ex.append(j); rr_out.append(r); reas.append(q)
        free_at = j + 1   # reference loop `continue`s on the exit bar
    return (np.asarray(ent, dtype=np.int64), np.asarray(ex, dtype=np.int64),
            np.asarray(rr_out, dtype=float), np.asarray(reas, dtype=int))


# ---------------------------------------------------------------------------
# Metrics
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
    arr[pos] = eq                      # later trades overwrite -> last of day
    arr[0] = arr[0] if np.isfinite(arr[0]) else INITIAL_BALANCE
    s = pd.Series(arr).ffill().values
    rets = np.diff(s) / s[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) < 3 or rets.std(ddof=1) == 0:
        return np.nan
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))


def metrics(exit_times, rs, risk_pct, t0, t1, prefix=""):
    d = {}
    n = len(rs)
    d[prefix + "trades"] = n
    if n == 0:
        for k in ("win_rate", "exp_R", "total_R", "roi_pct", "cagr_pct", "max_dd_pct",
                  "cagr_dd", "sharpe_daily", "pf", "streak", "h1_R", "h2_R", "worst_R"):
            d[prefix + k] = np.nan
        return d
    eq = equity_curve(rs, risk_pct)
    years = max((t1 - t0).days / 365.25, 1e-9)
    roi = (eq[-1] / INITIAL_BALANCE - 1) * 100
    cagr = ((eq[-1] / INITIAL_BALANCE) ** (1 / years) - 1) * 100
    dd = max_dd(eq)
    gains = rs[rs > 0].sum(); losses = -rs[rs <= 0].sum()
    half = n // 2
    d.update({
        prefix + "win_rate": round(float((rs > 0).mean() * 100), 1),
        prefix + "exp_R": round(float(rs.mean()), 4),
        prefix + "total_R": round(float(rs.sum()), 1),
        prefix + "roi_pct": round(float(roi), 2),
        prefix + "cagr_pct": round(float(cagr), 2),
        prefix + "max_dd_pct": round(dd, 2),
        prefix + "cagr_dd": round(float(cagr / abs(dd)), 2) if dd < 0 else np.nan,
        prefix + "sharpe_daily": round(daily_sharpe(exit_times, rs, risk_pct, t0, t1), 2),
        prefix + "pf": round(float(gains / losses), 2) if losses > 0 else np.nan,
        prefix + "streak": longest_loss_streak(rs),
        prefix + "h1_R": round(float(rs[:half].mean()), 4) if half >= 1 else np.nan,
        prefix + "h2_R": round(float(rs[half:].mean()), 4) if n - half >= 1 else np.nan,
        prefix + "worst_R": round(float(rs.min()), 2),
    })
    return d


# ---------------------------------------------------------------------------
# Reference replay (bar-by-bar, from backtest_full_history_replay.py) --
# used ONLY to prove the fast engine is equivalent.
# ---------------------------------------------------------------------------
def reference_replay(df, is_buy, is_sell, rr, spread, flatten):
    idx = df.index
    c = df["Close"].values; o = df["Open"].values
    h = df["High"].values; l = df["Low"].values
    atr = df["ATR"].values
    n = len(df)
    is_gap = (idx.to_series().diff() > GAP_THRESHOLD).values
    if flatten:
        wd, hh, mm = WEEKLY_CLOSE
        close_dt = idx.normalize() + pd.Timedelta(hours=hh, minutes=mm)
        mins_to = (close_dt - idx).total_seconds() / 60.0
        in_win = np.asarray((idx.dayofweek == wd) & (mins_to >= 0) & (mins_to <= BLOCK_MIN_BEFORE))
        block_mask = in_win
        close_mask = np.asarray(in_win & (mins_to <= CLOSE_MIN_BEFORE))
    else:
        block_mask = close_mask = np.zeros(n, dtype=bool)

    trades = []
    in_trade = False
    entry = sl = tp = risk = None
    direction = None; entry_i = 0
    for i in range(2, n):
        if in_trade:
            hit_sl = (l[i] <= sl) if direction == "BUY" else (h[i] >= sl)
            hit_tp = (h[i] >= tp) if direction == "BUY" else (l[i] <= tp)
            exit_r = None
            if hit_sl:
                fill = sl
                if is_gap[i] and ((direction == "BUY" and o[i] < sl) or (direction == "SELL" and o[i] > sl)):
                    fill = o[i]
                exit_r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
            elif hit_tp:
                fill = tp
                if is_gap[i] and ((direction == "BUY" and o[i] > tp) or (direction == "SELL" and o[i] < tp)):
                    fill = o[i]
                exit_r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
            elif close_mask[i]:
                exit_r = (c[i] - entry) / risk if direction == "BUY" else (entry - c[i]) / risk
            if exit_r is not None:
                trades.append((entry_i, i, float(exit_r)))
                in_trade = False
            continue
        if block_mask[i] or not (is_buy[i] or is_sell[i]):
            continue
        direction = "BUY" if is_buy[i] else "SELL"
        price = c[i]
        prev_low = min(l[i - 2], l[i - 1]); prev_high = max(h[i - 2], h[i - 1])
        if direction == "BUY" and price < prev_low:
            continue
        if direction == "SELL" and price > prev_high:
            continue
        a = atr[i]
        if direction == "BUY":
            stop_dist = max(price - prev_low, a) if a == a else (price - prev_low)
            sl_p = price - stop_dist - spread; risk = price - sl_p
            if risk <= 0:
                continue
            tp = price + risk * rr
        else:
            stop_dist = max(prev_high - price, a) if a == a else (prev_high - price)
            sl_p = price + stop_dist + spread; risk = sl_p - price
            if risk <= 0:
                continue
            tp = price - risk * rr
        entry, sl, entry_i = price, sl_p, i
        in_trade = True
    return trades


def verify_engine(df, out, params, rr):
    is_buy, is_sell = build_signals(df, params)
    ok = True
    for flatten in (False, True):
        ref = reference_replay(df, is_buy, is_sell, rr, SPREAD, flatten)
        ent, ex, rs, _ = walk(out, is_buy, is_sell, rr, flatten)
        # reference keeps a final still-open trade only if it exited; both drop opens
        m = min(len(ref), len(ent))
        bad = 0
        for k in range(m):
            if ref[k][0] != ent[k] or ref[k][1] != ex[k] or abs(ref[k][2] - rs[k]) > 1e-9:
                bad += 1
        print(f"  equivalence flatten={flatten}: ref {len(ref)} trades, fast {len(ent)} trades, "
              f"{bad} mismatches over {m} compared")
        ok &= (bad == 0) and abs(len(ref) - len(ent)) <= 1
    return ok


# ---------------------------------------------------------------------------
# Stop-move stage replay (poll-limited) -- only for the stage grid
# ---------------------------------------------------------------------------
def decide_stop_move(cfg, r_current, be_fired, lock_fired):
    if lock_fired:
        return None
    lock_at_r = cfg.get("lock_at_r")
    if lock_at_r is not None and r_current >= lock_at_r:
        return "lock", cfg["lock_to_r"]
    be_at_r = cfg.get("be_at_r")
    if be_at_r is not None and not be_fired and r_current >= be_at_r:
        return "be", cfg["be_to_r"]
    return None


def replay_with_stage(df, poll5, is_buy, is_sell, rr, spread, stage_cfg, flatten):
    """Bar-by-bar with poll-limited stop moves (5m closes as poll samples)."""
    idx = df.index
    c = df["Close"].values; o = df["Open"].values
    h = df["High"].values; l = df["Low"].values
    atr = df["ATR"].values
    n = len(df)
    is_gap = (idx.to_series().diff() > GAP_THRESHOLD).values
    if flatten:
        wd, hh, mm = WEEKLY_CLOSE
        close_dt = idx.normalize() + pd.Timedelta(hours=hh, minutes=mm)
        mins_to = (close_dt - idx).total_seconds() / 60.0
        in_win = np.asarray((idx.dayofweek == wd) & (mins_to >= 0) & (mins_to <= BLOCK_MIN_BEFORE))
        block_mask, close_mask = in_win, np.asarray(in_win & (mins_to <= CLOSE_MIN_BEFORE))
    else:
        block_mask = close_mask = np.zeros(n, dtype=bool)

    p_times = poll5.index.values if poll5 is not None else None
    p_px = poll5["Close"].values if poll5 is not None else None
    bar_ns = idx.values
    cooldown_min = stage_cfg.get("cooldown_min", 0)
    has_stage = bool(stage_cfg)

    trades = []
    in_trade = False
    entry = sl = tp = risk = None
    direction = None; entry_i = 0
    be_fired = lock_fired = False
    cooldown_until = None
    for i in range(2, n):
        if in_trade:
            hit_sl = (l[i] <= sl) if direction == "BUY" else (h[i] >= sl)
            hit_tp = (h[i] >= tp) if direction == "BUY" else (l[i] <= tp)
            exit_r = None
            if hit_sl:
                fill = sl
                if is_gap[i] and ((direction == "BUY" and o[i] < sl) or (direction == "SELL" and o[i] > sl)):
                    fill = o[i]
                exit_r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
            elif hit_tp:
                fill = tp
                if is_gap[i] and ((direction == "BUY" and o[i] > tp) or (direction == "SELL" and o[i] < tp)):
                    fill = o[i]
                exit_r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
            elif close_mask[i]:
                exit_r = (c[i] - entry) / risk if direction == "BUY" else (entry - c[i]) / risk
            if exit_r is not None:
                trades.append((entry_i, i, float(exit_r), be_fired, lock_fired))
                if lock_fired and cooldown_min > 0:
                    cooldown_until = idx[i] + pd.Timedelta(minutes=cooldown_min)
                in_trade = False
                continue
            if has_stage and not lock_fired:
                # poll samples strictly inside (bar i close, bar i+1 close]
                if p_times is None or bar_ns[i] < p_times[0]:
                    samples = [c[i]]
                else:
                    t1 = bar_ns[i + 1] if i + 1 < n else bar_ns[i]
                    a = np.searchsorted(p_times, bar_ns[i], side="right")
                    b = np.searchsorted(p_times, t1, side="right")
                    samples = p_px[a:b] if b > a else [c[i]]
                for px in samples:
                    r_pol = (px - entry) / risk if direction == "BUY" else (entry - px) / risk
                    d = decide_stop_move(stage_cfg, r_pol, be_fired, lock_fired)
                    if d is None:
                        continue
                    stg, to_r = d
                    sl = entry + to_r * risk if direction == "BUY" else entry - to_r * risk
                    if stg == "lock":
                        lock_fired = True
                        break
                    be_fired = True
            continue
        if block_mask[i] or not (is_buy[i] or is_sell[i]):
            continue
        if cooldown_until is not None and idx[i] < cooldown_until:
            continue
        direction = "BUY" if is_buy[i] else "SELL"
        price = c[i]
        prev_low = min(l[i - 2], l[i - 1]); prev_high = max(h[i - 2], h[i - 1])
        if direction == "BUY" and price < prev_low:
            continue
        if direction == "SELL" and price > prev_high:
            continue
        a = atr[i]
        if direction == "BUY":
            stop_dist = max(price - prev_low, a) if a == a else (price - prev_low)
            sl_p = price - stop_dist - spread; risk = price - sl_p
            if risk <= 0:
                continue
            tp = price + risk * rr
        else:
            stop_dist = max(prev_high - price, a) if a == a else (prev_high - price)
            sl_p = price + stop_dist + spread; risk = sl_p - price
            if risk <= 0:
                continue
            tp = price - risk * rr
        entry, sl, entry_i = price, sl_p, i
        in_trade = True
        be_fired = lock_fired = False
    return trades


# ---------------------------------------------------------------------------
# Grid definition
# ---------------------------------------------------------------------------
AVOID_BLOCKS = {
    "none": [],
    "asia": [0, 1, 2, 3, 4, 5, 6],
    "london_open": [7, 8, 9],
    "ny_pm": [15, 16, 17, 18, 19],
    "post_ny": [20, 21, 22, 23],
}

GRID = {
    "di_threshold": [25.0, 30.0, 35.0, 40.0],
    "di_persist": [1, 2, 3],
    "adx_min": [0.0, 15.0, 20.0, 25.0],
    "adx_rising": [False, True],
    "atr_ratio_min": [0.0, 1.0, 1.2],
    "di_slope": [False, True],
    "di_spread_min": [0.0, 10.0, 20.0],
    "body_ratio_min": [0.0, 0.3],
    "sma_ordered": [False, True],   # CLAUDE.md says "do NOT apply to XAG" -- tested, not assumed
    "avoid": list(AVOID_BLOCKS.keys()),
}
RRS = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]

INCUMBENT = {"di_threshold": 35.0, "di_persist": 2, "adx_min": 0.0, "adx_rising": False,
             "atr_ratio_min": 1.2, "di_slope": True, "di_spread_min": 0.0,
             "body_ratio_min": 0.0, "sma_ordered": False, "avoid": "none"}
INCUMBENT_RR = 3.0

_G = {}


def cell_params(combo):
    p = dict(combo)
    p["avoid_hours"] = AVOID_BLOCKS[p.pop("avoid")]
    return p


def eval_combo(combo):
    df, out, risk_pct = _G["df"], _G["out"], _G["risk_pct"]
    idx = df.index
    is_buy, is_sell = build_signals(df, cell_params(combo))
    rows = []
    for rr in RRS:
        ent, ex, rs, reas = walk(out, is_buy, is_sell, rr, False)
        if len(ent) == 0:
            continue
        et = idx[ent]
        xt = idx[ex]
        fit = et <= FIT_END
        oos = et >= OOS_START
        row = dict(combo)
        row["target_rr"] = rr
        row.update(metrics(xt[fit], rs[fit], risk_pct, _G["fit_t0"], _G["fit_t1"], "fit_"))
        row.update(metrics(xt[oos], rs[oos], risk_pct, _G["oos_t0"], _G["oos_t1"], "oos_"))
        row.update(metrics(xt, rs, risk_pct, idx[0], idx[-1], "all_"))
        rows.append(row)
    return rows


def _init(df, out, risk_pct, bounds):
    _G["df"] = df; _G["out"] = out; _G["risk_pct"] = risk_pct
    _G["fit_t0"], _G["fit_t1"], _G["oos_t0"], _G["oos_t1"] = bounds


def run_grid(df, out, risk_pct, bounds, grid, rrs, workers=8, label="grid"):
    global RRS
    RRS = rrs
    keys = list(grid.keys())
    combos = [dict(zip(keys, v)) for v in itertools.product(*[grid[k] for k in keys])]
    print(f"[{label}] {len(combos)} filter combos x {len(rrs)} RR = {len(combos)*len(rrs)} cells")
    import multiprocessing as mp
    ctx = mp.get_context("fork")
    with ctx.Pool(workers, initializer=_init, initargs=(df, out, risk_pct, bounds)) as pool:
        rows = []
        for i, r in enumerate(pool.imap_unordered(eval_combo, combos, chunksize=16)):
            rows.extend(r)
            if (i + 1) % 2000 == 0:
                print(f"  {i+1}/{len(combos)} combos", flush=True)
    return pd.DataFrame(rows)


def marginal(gdf, param, value, baseline, keys):
    """% of PAIRED cells (all else equal) where `value` beats `baseline` on
    fit-window expectancy. Blind to 2026 by construction."""
    others = [k for k in keys if k != param]
    a = gdf[gdf[param] == value].set_index(others)
    b = gdf[gdf[param] == baseline].set_index(others)
    j = a[["fit_exp_R", "fit_roi_pct", "fit_max_dd_pct"]].join(
        b[["fit_exp_R", "fit_roi_pct", "fit_max_dd_pct"]], lsuffix="_a", rsuffix="_b", how="inner")
    j = j.dropna(subset=["fit_exp_R_a", "fit_exp_R_b"])
    if len(j) == 0:
        return None
    return {
        "param": param, "value": value, "vs_baseline": baseline, "paired_cells": len(j),
        "pct_better_expR": round(float((j["fit_exp_R_a"] > j["fit_exp_R_b"]).mean() * 100), 1),
        "pct_better_roi": round(float((j["fit_roi_pct_a"] > j["fit_roi_pct_b"]).mean() * 100), 1),
        "pct_better_dd": round(float((j["fit_max_dd_pct_a"] > j["fit_max_dd_pct_b"]).mean() * 100), 1),
        "median_dExpR": round(float((j["fit_exp_R_a"] - j["fit_exp_R_b"]).median()), 4),
    }


def trades_frame(df, out, combo, rr, risk_pct, flatten=False):
    is_buy, is_sell = build_signals(df, cell_params(combo))
    ent, ex, rs, reas = walk(out, is_buy, is_sell, rr, flatten)
    return pd.DataFrame({"entry_time": df.index[ent], "exit_time": df.index[ex],
                         "direction": np.where(is_buy[ent], "BUY", "SELL"),
                         "r": rs, "reason_code": reas, "risk_pct": risk_pct})


def sections_table(t, risk_pct):
    if len(t) == 0:
        return pd.DataFrame()
    d = pd.DatetimeIndex(t["exit_time"])
    lab = pd.Series([f"{y}-{'H1' if m <= 6 else 'H2'}" for y, m in zip(d.year, d.month)],
                    index=t.index)
    rows = []
    for k in sorted(lab.unique()):
        sub = t[lab == k]
        rs = sub["r"].values
        rows.append({"section": k, "trades": len(sub),
                     "win_rate": round(float((rs > 0).mean() * 100), 1),
                     "exp_R": round(float(rs.mean()), 4),
                     "total_R": round(float(rs.sum()), 1)})
    return pd.DataFrame(rows)


def yearly_table(t):
    if len(t) == 0:
        return pd.DataFrame()
    y = pd.DatetimeIndex(t["exit_time"]).year
    rows = []
    for k in sorted(set(y)):
        rs = t["r"].values[y == k]
        rows.append({"year": k, "trades": len(rs),
                     "win_rate": round(float((rs > 0).mean() * 100), 1),
                     "exp_R": round(float(rs.mean()), 4),
                     "total_R": round(float(rs.sum()), 1)})
    return pd.DataFrame(rows)


def paired_ttest(a, b):
    m = a.merge(b, on="entry_time", suffixes=("_s", "_n"))
    d = (m["r_s"] - m["r_n"]).values
    if len(d) < 3:
        return {}
    mean = d.mean(); se = d.std(ddof=1) / np.sqrt(len(d))
    ci = 1.96 * se
    return {"paired_n": len(d), "changed": int((np.abs(d) > 1e-9).sum()),
            "mean_dR": round(float(mean), 4),
            "t": round(float(mean / se), 2) if se > 0 else np.nan,
            "ci_lo": round(float(mean - ci), 4), "ci_hi": round(float(mean + ci), 4),
            "significant": bool((mean - ci) * (mean + ci) > 0)}


def passes_bar(row):
    """The repo's promotion bar, evaluated on the FIT window only."""
    return (row["fit_trades"] >= 60 and row["fit_exp_R"] > 0
            and row["fit_h1_R"] > 0 and row["fit_h2_R"] > 0)


def neighbours_pass(gdf, row, keys):
    """Contiguous-plateau check: fraction of 1-step neighbours on each axis that
    also pass the fit-window bar."""
    tot = ok = 0
    for k in keys + ["target_rr"]:
        vals = sorted(gdf[k].unique(), key=lambda z: (str(type(z)), z)) if k != "avoid" \
            else list(gdf[k].unique())
        if k == "avoid":
            cand = [v for v in vals if v != row[k]]
        else:
            i = vals.index(row[k])
            cand = [vals[j] for j in (i - 1, i + 1) if 0 <= j < len(vals)]
        for v in cand:
            sel = gdf
            for kk in keys + ["target_rr"]:
                sel = sel[sel[kk] == (v if kk == k else row[kk])]
            if len(sel) == 0:
                continue
            tot += 1
            ok += int(passes_bar(sel.iloc[0]))
    return ok, tot


# The candidate produced by the greedy forward marginal selection below,
# fixed here so downstream stages (sections, stop-stage grid) use one definition.
CANDIDATE = {"di_threshold": 35.0, "di_persist": 2, "adx_min": 25.0, "adx_rising": False,
             "atr_ratio_min": 0.0, "di_slope": True, "di_spread_min": 0.0,
             "body_ratio_min": 0.3, "sma_ordered": True, "avoid": "london_open"}
CANDIDATE_RR = 3.0


def main_5m():
    """PROVISIONAL 5m re-check. The 5m file starts ~2025-09-10, so the fit window
    is only ~3.7 months and this CANNOT be walk-forward validated the way 15m can."""
    cfgs = json.loads(META.read_text())
    risk_pct = cfgs[SYMBOL]["risk_pct"]
    df = prep(load_bars("5m"))
    out = Outcomes(df, SPREAD)
    print(f"5m bars: {len(df)}  {df.index[0]} -> {df.index[-1]}")
    assert verify_engine(df, out, cell_params(INCUMBENT), 3.0), "engine mismatch on 5m"
    bounds = (df.index[0], FIT_END, OOS_START, df.index[-1])
    rrs = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    for rr in rrs:
        out.table(rr, False)
    # Reduced grid: 5m carries only ~1 year, so a fine grid would only buy
    # precision the window cannot support. This is a provisional re-check.
    g5 = {"di_threshold": [25.0, 30.0, 35.0, 40.0], "di_persist": [1, 2, 3],
          "adx_min": [0.0, 20.0, 25.0], "adx_rising": [False, True],
          "atr_ratio_min": [0.0, 1.2], "di_slope": [False, True],
          "di_spread_min": [0.0, 20.0], "body_ratio_min": [0.0, 0.3],
          "sma_ordered": [False, True], "avoid": ["none", "asia", "london_open", "post_ny"]}
    gdf = run_grid(df, out, risk_pct, bounds, g5, rrs, workers=8, label="5m")
    gdf.to_csv(OUT / "backtest_xag_wf_5m.csv.gz", index=False, compression="gzip")
    print(f"5m grid rows: {len(gdf)}")
    cols = ["di_threshold", "di_persist", "adx_min", "adx_rising", "atr_ratio_min", "di_slope",
            "di_spread_min", "body_ratio_min", "sma_ordered", "avoid", "target_rr",
            "all_trades", "all_win_rate", "all_exp_R", "all_roi_pct", "all_max_dd_pct",
            "all_sharpe_daily", "all_h1_R", "all_h2_R"]
    ok = gdf[(gdf.all_trades >= 60) & (gdf.all_exp_R > 0) & (gdf.all_h1_R > 0) & (gdf.all_h2_R > 0)]
    print(f"5m cells clearing the bar on the WHOLE (1-year) file: {len(ok)} of {len(gdf)}")
    print(ok.sort_values("all_exp_R", ascending=False)[cols].head(15).to_string(index=False))
    for lab, c, rr in [("incumbent 15m config on 5m bars", INCUMBENT, INCUMBENT_RR),
                       ("candidate 15m config on 5m bars", CANDIDATE, CANDIDATE_RR)]:
        s = gdf.copy()
        for k, v in c.items():
            s = s[s[k] == v]
        s = s[s.target_rr == rr]
        print(f"\n{lab}:")
        print(s[cols].to_string(index=False))


def main_stages():
    """Stop-move stage grid (poll-limited triggers) for incumbent and candidate."""
    cfgs = json.loads(META.read_text())
    risk_pct = cfgs[SYMBOL]["risk_pct"]
    df = prep(load_bars("15m"))
    try:
        poll5 = load_bars("5m")
    except FileNotFoundError:
        poll5 = None
    pre = float((df.index < poll5.index[0]).mean() * 100) if poll5 is not None else 100.0
    print(f"poll source: 5m closes; {pre:.1f}% of 15m bars predate the 5m file and fall back "
          f"to the 15m close (UNDER-fires stages -> conservative)")
    frames = []
    for lab, c, rr in [("incumbent", INCUMBENT, INCUMBENT_RR), ("candidate", CANDIDATE, CANDIDATE_RR)]:
        sg, base = run_stage_grid(df, poll5, c, rr, risk_pct)
        sg["config"] = lab
        frames.append(sg)
        print(f"\n=== STOP-STAGE GRID -- {lab} (baseline: {base['trades']} trades, "
              f"expR {base['exp_R']}, ROI {base['roi_pct']}%, DD {base['max_dd_pct']}%, "
              f"Sharpe {base['sharpe_daily']}) ===")
        show = ["stage", "stage_trades", "changed", "stage_roi_pct", "d_roi", "stage_max_dd_pct",
                "d_dd", "stage_sharpe_daily", "d_totR", "mean_dR", "t", "ci_lo", "ci_hi",
                "significant"]
        print(sg.sort_values("d_dd")[show].head(12).to_string(index=False))
        print("  ... best by ROI:")
        print(sg.sort_values("d_roi", ascending=False)[show].head(8).to_string(index=False))
        print(f"  stages improving DD: {int((sg.d_dd > 0).sum())}/{len(sg)}   "
              f"improving ROI: {int((sg.d_roi > 0).sum())}/{len(sg)}   "
              f"statistically significant dR: {int(sg.significant.sum())}/{len(sg)}")
    pd.concat(frames).to_csv(OUT / "backtest_xag_wf_stage_grid.csv", index=False)


def main():
    quick = "--quick" in sys.argv
    cfgs = json.loads(META.read_text())
    risk_pct = cfgs[SYMBOL]["risk_pct"]
    inc_strat = cfgs[SYMBOL]["strategies"][0]
    print(f"Incumbent from best_strategies.json: tf={inc_strat['timeframe']} "
          f"rr={inc_strat['target_rr']} risk={risk_pct} params={inc_strat['params']}")

    df = prep(load_bars("15m"))
    out = Outcomes(df, SPREAD)
    print(f"15m bars: {len(df)}  {df.index[0]} -> {df.index[-1]}")

    print("\n=== ENGINE EQUIVALENCE (fast table vs reference bar-by-bar loop) ===")
    assert verify_engine(df, out, cell_params(INCUMBENT), INCUMBENT_RR), "engine mismatch"

    bounds = (df.index[0], FIT_END, OOS_START, df.index[-1])
    for rr in RRS:
        out.table(rr, False)                    # warm cache before fork

    grid = {k: (v[:2] if quick else v) for k, v in GRID.items()}
    gdf = run_grid(df, out, risk_pct, bounds, grid, RRS, workers=8, label="main")
    gdf.to_csv(OUT / "backtest_xag_wf_grid.csv.gz", index=False, compression="gzip")
    print(f"grid rows: {len(gdf)}")

    # ---- hypothesis grid: sma_ordered / rsi_filter (paired) ----
    hyp = {"di_threshold": [30.0, 35.0, 40.0], "di_persist": [1, 2],
           "adx_min": [0.0, 20.0], "adx_rising": [False],
           "atr_ratio_min": [0.0, 1.0, 1.2], "di_slope": [False, True],
           "di_spread_min": [0.0, 20.0], "body_ratio_min": [0.0],
           "avoid": ["none"], "sma_ordered": [False, True], "rsi_filter": [False, True]}
    hdf = run_grid(df, out, risk_pct, bounds, hyp, [2.5, 3.0, 3.5], workers=8, label="hypoth")
    hdf.to_csv(OUT / "backtest_xag_wf_hypotheses.csv", index=False)

    print("\n=== HYPOTHESIS TESTS (fit window, paired cells) ===")
    hkeys = [k for k in hyp if k != "target_rr"]
    hrows = []
    for p, v, b in [("sma_ordered", True, False), ("rsi_filter", True, False)]:
        r = marginal(hdf, p, v, b, hkeys + ["target_rr"])
        if r:
            hrows.append(r)
    print(pd.DataFrame(hrows).to_string(index=False))
    return df, out, gdf, hdf, risk_pct, hrows




# ---------------------------------------------------------------------------
# Stage 2: selection (blind to 2026), marginals, sections, stage grid, 5m
# ---------------------------------------------------------------------------
STAGE_GRID = ([{"lock_at_r": a, "lock_to_r": b, "cooldown_min": cd}
               for a in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5)
               for b in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5)
               for cd in (0, 90) if b < a]
              + [{"be_at_r": a, "be_to_r": b}
                 for a in (0.25, 0.5, 0.75, 1.0, 1.5)
                 for b in (-0.3, -0.2, -0.1, 0.0)])


def stage_label(cfg):
    if not cfg:
        return "none"
    if "lock_at_r" in cfg:
        return f"lock {cfg['lock_at_r']}R->+{cfg['lock_to_r']}R cd{cfg.get('cooldown_min', 0)}m"
    return f"BE {cfg['be_at_r']}R->{cfg['be_to_r']}R"


def run_stage_grid(df, poll5, combo, rr, risk_pct):
    is_buy, is_sell = build_signals(df, cell_params(combo))
    base = replay_with_stage(df, poll5, is_buy, is_sell, rr, SPREAD, {}, False)
    bt = pd.DataFrame(base, columns=["ei", "xi", "r", "be", "lk"])
    bt["entry_time"] = df.index[bt["ei"].values]
    bt["exit_time"] = df.index[bt["xi"].values]
    b_m = metrics(bt["exit_time"], bt["r"].values, risk_pct, df.index[0], df.index[-1], "")
    rows = []
    for cfg in STAGE_GRID:
        tr = pd.DataFrame(replay_with_stage(df, poll5, is_buy, is_sell, rr, SPREAD, cfg, False),
                          columns=["ei", "xi", "r", "be", "lk"])
        if len(tr) == 0:
            continue
        tr["entry_time"] = df.index[tr["ei"].values]
        tr["exit_time"] = df.index[tr["xi"].values]
        mm = metrics(tr["exit_time"], tr["r"].values, risk_pct, df.index[0], df.index[-1], "")
        tt = paired_ttest(tr[["entry_time", "r"]], bt[["entry_time", "r"]])
        rows.append({"stage": stage_label(cfg), **{f"stage_{k}": v for k, v in mm.items()},
                     **{f"base_{k}": v for k, v in b_m.items()},
                     "d_roi": round(mm["roi_pct"] - b_m["roi_pct"], 2),
                     "d_dd": round(mm["max_dd_pct"] - b_m["max_dd_pct"], 2),
                     "d_totR": round(mm["total_R"] - b_m["total_R"], 1), **tt})
    return pd.DataFrame(rows), b_m


def forward_select(gdf, bar=60.0, max_steps=8):
    """Greedy forward selection on FIT-window paired-cell marginals only.

    At each step every not-yet-adopted (param, value) is scored as the fraction
    of PAIRED cells (all else equal, within the already-adopted slice) where it
    beats the INCUMBENT value. The best is adopted if it clears `bar`.
    Nothing here reads an oos_* column, so the whole chain is blind to 2026.
    Note the paired-cell population shrinks each step -- a lever adopted on a
    few hundred pairs is much weaker evidence than one adopted on 100k.
    """
    ax = {**GRID, "target_rr": RRS}
    keys = list(ax.keys())
    inc = dict(INCUMBENT); inc["target_rr"] = INCUMBENT_RR
    adopted, log = {}, []
    for step in range(1, max_steps + 1):
        sub = gdf.copy()
        for k, v in adopted.items():
            sub = sub[sub[k] == v]
        cands = []
        for k, vals in ax.items():
            if k in adopted:
                continue
            for v in vals:
                if v == inc[k]:
                    continue
                r = marginal(sub, k, v, inc[k], keys)
                if r:
                    cands.append(r)
        cd = pd.DataFrame(cands).sort_values("pct_better_expR", ascending=False)
        print(f"\n### STEP {step} -- conditioned on {adopted or 'nothing'}")
        print(cd.head(8).to_string(index=False))
        best = cd.iloc[0]
        if best.pct_better_expR < bar:
            print(f"--> nothing left clears {bar}%; STOP")
            break
        adopted[best.param] = best.value
        log.append({"step": step, **best.to_dict(),
                    "conditioned_on": str({k: v for k, v in adopted.items() if k != best.param})})
        print(f"--> ADOPT {best.param} = {best.value} "
              f"({best.pct_better_expR}% of {best.paired_cells} paired cells)")
    return adopted, pd.DataFrame(log)


def main_report():
    cfgs = json.loads(META.read_text())
    risk_pct = cfgs[SYMBOL]["risk_pct"]
    _gz, _pl = OUT / "backtest_xag_wf_grid.csv.gz", OUT / "backtest_xag_wf_grid.csv"
    _src = _gz if _gz.exists() else _pl
    if not _src.exists():
        raise SystemExit(
            f"Grid not found ({_gz.name} or {_pl.name}). "
            "Run this script with no arguments first to build it."
        )
    gdf = pd.read_csv(_src)
    ax = {**GRID, "target_rr": RRS}
    keys = list(ax.keys())
    inc = dict(INCUMBENT); inc["target_rr"] = INCUMBENT_RR
    print(f"grid cells: {len(gdf)}")

    # ---- flat marginals vs the incumbent value, whole grid ----
    rows = []
    for k, vals in ax.items():
        for v in vals:
            if v == inc[k]:
                continue
            r = marginal(gdf, k, v, inc[k], keys)
            if r:
                rows.append(r)
    md = pd.DataFrame(rows)
    md.to_csv(OUT / "backtest_xag_wf_marginals.csv", index=False)
    print("\n=== MARGINALS vs INCUMBENT VALUE (fit window, blind to 2026) ===")
    print(md.to_string(index=False))

    print("\n=== GREEDY FORWARD SELECTION (fit window, blind to 2026) ===")
    adopted, log = forward_select(gdf)
    log.to_csv(OUT / "backtest_xag_wf_marginals_forward.csv", index=False)
    print("\nadopted:", adopted)

    # ---- candidate comparison, three windows ----
    df = prep(load_bars("15m"))
    out = Outcomes(df, SPREAD)
    cands = {
        "INCUMBENT": (dict(INCUMBENT), INCUMBENT_RR),
        "D_sma_ordered_only": ({**INCUMBENT, "sma_ordered": True}, INCUMBENT_RR),
        "CANDIDATE_rr3.0": (dict(CANDIDATE), 3.0),
        "CANDIDATE_rr2.5": (dict(CANDIDATE), 2.5),
        "CANDIDATE_rr4.0": (dict(CANDIDATE), 4.0),
        "CANDIDATE_rr5.0": (dict(CANDIDATE), 5.0),
    }
    frows, secs, yrs = [], [], []
    for name, (c, rr) in cands.items():
        s = gdf.copy()
        for k, v in c.items():
            s = s[s[k] == v]
        s = s[s.target_rr == rr]
        r = s.iloc[0].to_dict(); r["config"] = name; frows.append(r)

        t = trades_frame(df, out, c, rr, risk_pct)
        tf_on = trades_frame(df, out, c, rr, risk_pct, flatten=True)
        sec = sections_table(t, risk_pct); sec["config"] = name; secs.append(sec)
        y = yearly_table(t); y["config"] = name; yrs.append(y)
        rs = t["r"].values
        a = metrics(t["exit_time"], rs, risk_pct, df.index[0], df.index[-1], "")
        b = metrics(tf_on["exit_time"], tf_on["r"].values, risk_pct, df.index[0], df.index[-1], "")
        frows[-1].update({
            "flat_on_trades": b["trades"], "flat_on_expR": b["exp_R"],
            "flat_on_roi": b["roi_pct"], "flat_on_dd": b["max_dd_pct"],
            "sections_positive": f"{int((sec.total_R > 0).sum())}/{len(sec)}",
            "best_section_pct_of_total": round(100 * sec.total_R.max() / sec.total_R.sum(), 1)
            if sec.total_R.sum() > 0 else np.nan,
            "years_positive": f"{int((y.total_R > 0).sum())}/{len(y)}",
            **{f"expR_if_wins_capped_at_{K}R": round(float(np.minimum(rs, K).mean()), 4)
               for K in (1.5, 2.0, 2.5, 3.0)},
        })
    fd = pd.DataFrame(frows).set_index("config")
    fd.to_csv(OUT / "backtest_xag_wf_final.csv")
    pd.concat(secs).to_csv(OUT / "backtest_xag_wf_sections.csv", index=False)
    pd.concat(yrs).to_csv(OUT / "backtest_xag_wf_years.csv", index=False)

    for w, lab in [("fit_", "FIT 2023-09-20..2025-12-31"),
                   ("oos_", "HELD-OUT 2026-01-01..2026-09-07"),
                   ("all_", "FULL 3.0 years")]:
        cols = [c for c in fd.columns if c.startswith(w)]
        print(f"\n=== {lab} ===")
        print(fd[cols].rename(columns=lambda x: x[len(w):]).to_string())
    print("\n=== SECTION / YEAR CONCENTRATION + weekend-flatten + live-execution stress ===")
    print(fd[["sections_positive", "best_section_pct_of_total", "years_positive",
              "flat_on_expR", "flat_on_roi", "flat_on_dd",
              "expR_if_wins_capped_at_1.5R", "expR_if_wins_capped_at_2.0R",
              "expR_if_wins_capped_at_2.5R", "expR_if_wins_capped_at_3.0R"]].to_string())
    print("\n=== 6-MONTH SECTIONS (total R) ===")
    print(pd.concat(secs).pivot(index="section", columns="config", values="total_R").to_string())
    print("\n=== PER CALENDAR YEAR (mean R) ===")
    print(pd.concat(yrs).pivot(index="year", columns="config", values="exp_R").to_string())

    # ---- contiguous-plateau check: every 1-step neighbour of the candidate ----
    cc = dict(CANDIDATE); cc["target_rr"] = CANDIDATE_RR
    nrows = []
    for k, vals in ax.items():
        for v in vals:
            if v == cc[k]:
                continue
            q = gdf.copy()
            for kk, vv in cc.items():
                q = q[q[kk] == (v if kk == k else vv)]
            if len(q) == 0:
                continue
            r = q.iloc[0]
            nrows.append({"neighbour": f"{k}={v}", "fit_n": r.fit_trades, "fit_expR": r.fit_exp_R,
                          "fit_dd": r.fit_max_dd_pct, "oos_n": r.oos_trades, "oos_expR": r.oos_exp_R,
                          "all_expR": r.all_exp_R, "all_roi": r.all_roi_pct,
                          "all_dd": r.all_max_dd_pct, "all_sharpe": r.all_sharpe_daily})
    nb = pd.DataFrame(nrows)
    nb.to_csv(OUT / "backtest_xag_wf_neighbours.csv", index=False)
    print("\n=== CONTIGUOUS-PLATEAU CHECK: 1-step neighbours of the candidate ===")
    print(nb.to_string(index=False))
    print(f"neighbours positive on FIT: {int((nb.fit_expR > 0).sum())}/{len(nb)}   "
          f"positive on HELD-OUT 2026: {int((nb.oos_expR > 0).sum())}/{len(nb)}")


if __name__ == "__main__":
    if "--five-min" in sys.argv:
        main_5m()
    elif "--stages" in sys.argv:
        main_stages()
    elif "--report" in sys.argv:
        main_report()
    else:
        main()
