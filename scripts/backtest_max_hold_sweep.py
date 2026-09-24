"""
Max-hold (time stop) sweep
==========================
Evidence for PAIR_MAX_HOLD_DAYS in backend/app/services/tasks.py.

A SmaScalping entry is built from 15m structure — a 2-candle structural stop
with a 1xATR floor — which are the parameters of a trade meant to resolve in
hours. Nothing bounded how long one could actually run: XAU_USD has a measured
132-day hold. Because oanda_trade_service.py enforces one position per pair (it
skips a symbol already open in Oanda), such a trade locks the pair out for its
whole duration.

This script answers three questions:
  1. Is the long-hold behaviour generic, or an XAU quirk?       -> census
  2. What does a max-hold cap of N days do to each pair?        -> sweep
  3. Does a cap reduce FINANCING cost?                          -> financing cols

Nothing is taken on trust from CLAUDE.md. Every number derives from
data/forex_raw/*.csv using the entry logic of
backend/app/services/sma_scalping_detector.py and the real
backend.app.services.indicators.TechnicalIndicators.

Methodology guards (same as backtest_xag_walkforward_retune.py)
--------------------------------------------------------------
 1. GAP PRICING. A stop or target hit on a session-gap bar (>6h since the
    previous bar) books at that bar's OPEN when the open is already past the
    level — never a flat -1R.
 2. BROKER SL/TP FILL INTRABAR (they rest at Oanda), tested against high/low,
    stop before target so same-bar ambiguity resolves against us.
 3. OUR STOP MOVES ARE POLL-LIMITED, never intrabar: stage triggers are sampled
    at 5m bar closes, mirroring run_pair_lock_checks' ~5-minute polling.
 4. One position at a time per pair (production enforces exactly this).
 5. BCO_USD is force-flattened before the weekly close (ALWAYS_CLOSE_PAIRS).
 6. The max-hold exit books at the CLOSE of the first bar at or past the cap —
    it is our own action, so it cannot fill intrabar.

Financing
---------
Financing is charged on NOTIONAL, and risk-based sizing makes notional a large
multiple of risk:

    units    = risk_$ / risk_dist
    notional = units * entry_price = risk_$ * L,   L = entry_price / risk_dist
    fin_$    = notional * daily_rate * calendar_days
    fin_R    = fin_$ / risk_$ = L * daily_rate * calendar_days

so financing in R is size-independent and driven by leverage x time-in-market.
Longs and shorts are charged symmetrically here, which OVERSTATES the cost for
FX majors (real FX carry is a rate differential and can be positive on a short)
— treat EUR_USD/USD_JPY financing as an upper bound. Measure the real figure
with OandaPriceService.get_financing_charges() instead of trusting this model.

Result (2023-2026, financing at 5%/yr)
--------------------------------------
Adopted 7 days, as ROBUSTNESS and TAIL-RISK control — NOT an ROI upgrade and
NOT a financing fix:
  * XAU_USD    split-half FAIL (h1 -0.01) -> PASS (+0.12/+0.35);
               MaxDD -44.1% -> -33.1%, Sharpe 0.91 -> 1.22
  * NAS100_USD split-half FAIL (h1 -0.01) -> PASS (+0.01/+0.25); Sharpe 0.52 -> 0.65
  * BCO_USD    Sharpe 1.45 -> 1.55;  XAG_USD unchanged;  JP225_USD inert
  * The paired per-trade effect is NOT significant (XAU 7d: +0.005R, t=0.18,
    95% CI [-0.046, +0.055]). The large ROI swings in the cap sweep are
    sequencing artifacts — the same trap documented for the stop stages.
  * 3d and 5d score HIGHER on ROI but their paired point estimates are NEGATIVE
    (-0.058R and -0.034R). Those are the overfit cells; 7d is the
    expectancy-neutral one. This is why the cap is 7 and not 5.
  * A cap does NOT reduce financing: XAU 11.58R uncapped vs 12.98R at 7 days.
    Capping frees capacity that new trades immediately consume.
  * The three runtime-disabled pairs (EUR_USD, USD_JPY, UK100_GBP) are negative
    net of financing under BOTH configs and fail split-half in both — the cap
    does not rescue them. Keep them disabled.

Outputs (data/):
  backtest_max_hold_census.csv   hold-time distribution, all 8 pairs
  backtest_max_hold_sweep.csv    per-pair x cap metrics, gross and net of financing
  backtest_max_hold_paired.csv   paired per-trade dR with t-stat and 95% CI

Usage:  python scripts/backtest_max_hold_sweep.py [--quick]
"""

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

INITIAL_BALANCE = 5_000.0
GAP_THRESHOLD = pd.Timedelta(hours=6)
FINANCING_ANNUAL = 0.05          # see the Financing note above
HTF_TREND_PERIOD = 50

WINDOW_START = pd.Timestamp("2023-01-01")
WINDOW_END = pd.Timestamp("2026-09-24 23:59:59")
CAPS = [None, 1, 2, 3, 5, 7, 10, 14, 21]

ACTIVE = ["XAU_USD", "XAG_USD", "NAS100_USD", "BCO_USD", "JP225_USD"]
INERT = ["EUR_USD", "USD_JPY", "UK100_GBP"]      # disabled at runtime; measured anyway
ALL_PAIRS = ACTIVE + INERT

# Oanda spreads — the convention used across this repo's sweep scripts.
SPREADS = {
    "XAU_USD": 0.50, "XAG_USD": 0.03, "BCO_USD": 0.04,
    "JP225_USD": 17.0, "NAS100_USD": 2.30,
    "EUR_USD": 0.0002, "USD_JPY": 0.02, "UK100_GBP": 1.5,
}

# market_close_schedule.WEEKLY_CLOSE_UTC
WEEKLY_CLOSE = {
    "XAU_USD": (4, 21, 0), "XAG_USD": (4, 21, 0), "BCO_USD": (4, 21, 0),
    "NAS100_USD": (4, 21, 0), "JP225_USD": (4, 6, 0),
    "EUR_USD": (4, 21, 0), "USD_JPY": (4, 21, 0), "UK100_GBP": (4, 16, 30),
}
BLOCK_MIN_BEFORE, CLOSE_MIN_BEFORE = 65, 60
ALWAYS_CLOSE_PAIRS = {"BCO_USD"}      # tasks.py

# tasks.py PAIR_LOCK_CONFIGS, as deployed
STAGES = {
    "BCO_USD":    {"lock_at_r": 2.0, "lock_to_r": 1.0, "cooldown_min": 90},
    "NAS100_USD": {"lock_at_r": 1.5, "lock_to_r": 0.5, "cooldown_min": 90},
    "JP225_USD":  {"be_at_r": 0.25, "be_to_r": -0.1},
}

TF_SUFFIX = {"15m": "15_Min", "5m": "5_Min"}
TF_DELTA = {"15m": pd.Timedelta(minutes=15), "5m": pd.Timedelta(minutes=5)}
HTF_FILE = {"4h": "4_Hour", "daily": "Daily"}
HTF_DELTA = {"4h": pd.Timedelta(hours=4), "daily": pd.Timedelta(days=1)}


# ---------------------------------------------------------------------------
# Data + indicators (the real module; indicators are never re-implemented)
# ---------------------------------------------------------------------------
def load_bars(symbol, suffix):
    df = pd.read_csv(DATA_DIR / f"{symbol}_{suffix}.csv",
                     parse_dates=["Date"]).set_index("Date").sort_index()
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


def htf_trend(df, granularity_delta, period=HTF_TREND_PERIOD):
    """Close vs SMA(period) on an HTF series, aligned to each HTF bar's own CLOSE
    time (open + granularity) so a backward as-of join never sees a forming bar."""
    df = df.sort_index().copy()
    sma = df["Close"].rolling(period).mean()
    trend = np.where(df["Close"] > sma, 1, np.where(df["Close"] < sma, -1, 0))
    trend = np.where(sma.isna().values, 0, trend)      # no SMA yet -> blocks both
    return pd.DataFrame({"htf_close": df.index + granularity_delta,
                         "trend": trend}).sort_values("htf_close")


def attach_htf(base_df, base_tf, htf_df):
    left = pd.DataFrame({"base_close": base_df.index + TF_DELTA[base_tf]},
                        index=base_df.index).reset_index().rename(columns={"Date": "base_open"})
    left = left.sort_values("base_close")
    merged = pd.merge_asof(left, htf_df, left_on="base_close",
                           right_on="htf_close", direction="backward")
    merged = merged.set_index("base_open").sort_index()
    return merged["trend"].reindex(base_df.index).fillna(0).astype(int)


# ---------------------------------------------------------------------------
# Signal builder — verbatim port of SmaScalpingDetector.analyze
# (identical to backtest_xag_walkforward_retune.py / backtest_htf_direction_filter.py)
# ---------------------------------------------------------------------------
def build_signals(df, params, htf=None):
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
    T = pd.Series(True, index=df.index)

    valid = pd.concat([s20, s50, s100, dp, dm, adx, l, h, o], axis=1).notna().all(axis=1)
    adx_ok = adx >= adx_min

    dp_pers, dm_pers = (dp > di_threshold), (dm > di_threshold)
    for j in range(1, di_persist):
        dp_pers &= (dp.shift(j) > di_threshold)
        dm_pers &= (dm.shift(j) > di_threshold)

    adx_rising_ok = (adx > adx.shift(1)) if adx_rising else T

    if sma_ordered:
        ord_buy, ord_sell = (s20 > s50) & (s50 > s100), (s20 < s50) & (s50 < s100)
    else:
        ord_buy = ord_sell = T

    spr_buy, spr_sell = (dp - dm) >= di_spread_min, (dm - dp) >= di_spread_min

    if rsi_filter and "RSI" in df.columns:
        rsi = df["RSI"]
        rsi_buy = (rsi > 50.0) & (rsi < 75.0) & rsi.notna()
        rsi_sell = (rsi > 25.0) & (rsi < 50.0) & rsi.notna()
    else:
        rsi_buy = rsi_sell = T

    if body_ratio_min > 0.0:
        rng = h - l
        body_buy = ((c - o) / rng >= body_ratio_min).where(rng > 0, False)
        body_sell = ((o - c) / rng >= body_ratio_min).where(rng > 0, False)
    else:
        body_buy = body_sell = T

    if vol_ratio_min > 0.0 and "Volume" in df.columns:
        va = df["Vol_avg20"]
        vol_ok = (va > 0) & (df["Volume"] >= vol_ratio_min * va)
    else:
        vol_ok = T

    if atr_ratio_min > 0.0:
        aa = df["ATR_avg20"]
        atr_ok = (aa > 0) & (atr >= atr_ratio_min * aa)
    else:
        atr_ok = T

    if di_slope:
        slope_buy, slope_sell = dp > dp.shift(2), dm > dm.shift(2)
    else:
        slope_buy = slope_sell = T

    sess = ~pd.Series(df.index.hour, index=df.index).isin(avoid_hours) if avoid_hours else T

    if htf is not None:
        htf_buy, htf_sell = (htf == 1), (htf == -1)
    else:
        htf_buy = htf_sell = T

    common = valid & adx_ok & adx_rising_ok & vol_ok & atr_ok & sess
    is_buy = (common & (c > s20) & (c > s50) & (c > s100) & dp_pers & (dp > dm)
              & ord_buy & spr_buy & rsi_buy & body_buy & slope_buy & htf_buy).fillna(False)
    is_sell = (common & (c < s20) & (c < s50) & (c < s100) & dm_pers & (dm > dp)
               & ord_sell & spr_sell & rsi_sell & body_sell & slope_sell & htf_sell).fillna(False)
    is_sell &= ~is_buy
    return is_buy.values, is_sell.values


# ---------------------------------------------------------------------------
# Stage decision — mirrors tasks.decide_stop_move
# ---------------------------------------------------------------------------
def decide_stop_move(cfg, r_current, be_fired, lock_fired):
    if lock_fired:
        return None
    if cfg.get("lock_at_r") is not None and r_current >= cfg["lock_at_r"]:
        return "lock", cfg["lock_to_r"]
    if cfg.get("be_at_r") is not None and not be_fired and r_current >= cfg["be_at_r"]:
        return "be", cfg["be_to_r"]
    return None


# ---------------------------------------------------------------------------
# Replay: one position at a time, gap-priced, poll-limited stages, optional cap
# ---------------------------------------------------------------------------
def replay(symbol, df, poll5, is_buy, is_sell, rr, spread, stage_cfg, flatten,
           weekly_close, win_start, win_end, max_hold_days=None):
    idx = df.index
    c, o, h, l = (df[x].values for x in ("Close", "Open", "High", "Low"))
    atr = df["ATR"].values
    n = len(df)
    is_gap = (idx.to_series().diff() > GAP_THRESHOLD).values

    if flatten:
        wd, hh, mm = weekly_close
        close_dt = idx.normalize() + pd.Timedelta(hours=hh, minutes=mm)
        mins_to = (close_dt - idx).total_seconds() / 60.0
        in_win = np.asarray((idx.dayofweek == wd) & (mins_to >= 0) & (mins_to <= BLOCK_MIN_BEFORE))
        block_mask = in_win
        close_mask = np.asarray(in_win & (mins_to <= CLOSE_MIN_BEFORE))
    else:
        block_mask = close_mask = np.zeros(n, dtype=bool)

    in_window = np.asarray((idx >= win_start) & (idx <= win_end))
    p_times = poll5.index.values if poll5 is not None else None
    p_px = poll5["Close"].values if poll5 is not None else None
    bar_ns = idx.values
    cooldown_min = stage_cfg.get("cooldown_min", 0)
    has_stage = bool(stage_cfg)
    mh = pd.Timedelta(days=max_hold_days) if max_hold_days else None

    trades = []
    in_trade = False
    entry = sl = tp = risk = None
    direction = None
    entry_i = 0
    be_fired = lock_fired = False
    cooldown_until = None

    for i in range(2, n):
        if in_trade:
            hit_sl = (l[i] <= sl) if direction == "BUY" else (h[i] >= sl)
            hit_tp = (h[i] >= tp) if direction == "BUY" else (l[i] <= tp)
            exit_r = reason = None

            if hit_sl:
                fill = sl
                if is_gap[i] and ((direction == "BUY" and o[i] < sl) or
                                  (direction == "SELL" and o[i] > sl)):
                    fill, reason = o[i], "SL_GAP"
                else:
                    reason = "SL"
                exit_r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
            elif hit_tp:
                fill = tp
                if is_gap[i] and ((direction == "BUY" and o[i] > tp) or
                                  (direction == "SELL" and o[i] < tp)):
                    fill, reason = o[i], "TP_GAP"
                else:
                    reason = "TP"
                exit_r = (fill - entry) / risk if direction == "BUY" else (entry - fill) / risk
            elif close_mask[i]:
                exit_r = (c[i] - entry) / risk if direction == "BUY" else (entry - c[i]) / risk
                reason = "PRECLOSE"
            elif mh is not None and (idx[i] - idx[entry_i]) >= mh:
                # Our own action, so it books at the bar CLOSE — never intrabar.
                exit_r = (c[i] - entry) / risk if direction == "BUY" else (entry - c[i]) / risk
                reason = "MAXHOLD"

            if exit_r is not None:
                trades.append(dict(
                    symbol=symbol, entry_time=idx[entry_i], exit_time=idx[i],
                    direction=direction, r=float(exit_r), reason=reason,
                    entry_price=entry, risk_dist=risk, lev=entry / risk,
                    hold_days=(idx[i] - idx[entry_i]).total_seconds() / 86400.0,
                    be_fired=be_fired, lock_fired=lock_fired))
                if lock_fired and cooldown_min > 0:
                    cooldown_until = idx[i] + pd.Timedelta(minutes=cooldown_min)
                in_trade = False
                continue

            # Poll-limited stop move: samples strictly inside (bar i close, bar i+1 close]
            if has_stage and not lock_fired:
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

        if not in_window[i] or block_mask[i] or not (is_buy[i] or is_sell[i]):
            continue
        if cooldown_until is not None and idx[i] < cooldown_until:
            continue

        direction = "BUY" if is_buy[i] else "SELL"
        price = c[i]
        prev_low, prev_high = min(l[i - 2], l[i - 1]), max(h[i - 2], h[i - 1])
        if direction == "BUY" and price < prev_low:
            continue
        if direction == "SELL" and price > prev_high:
            continue

        a = atr[i]
        if direction == "BUY":
            stop_dist = max(price - prev_low, a) if a == a else (price - prev_low)
            sl_p = price - stop_dist - spread
            risk = price - sl_p
            if risk <= 0:
                continue
            tp = price + risk * rr
        else:
            stop_dist = max(prev_high - price, a) if a == a else (prev_high - price)
            sl_p = price + stop_dist + spread
            risk = sl_p - price
            if risk <= 0:
                continue
            tp = price - risk * rr

        entry, sl, entry_i = price, sl_p, i
        in_trade = True
        be_fired = lock_fired = False

    return pd.DataFrame(trades)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def financing_r(d, annual=FINANCING_ANNUAL):
    return d["lev"] * (annual / 365.0) * d["hold_days"]


def max_dd(eq):
    full = np.concatenate([[INITIAL_BALANCE], eq])
    peak = np.maximum.accumulate(full)
    return float(((full - peak) / peak * 100).min())


def daily_sharpe(exit_times, eq, t0, t1):
    if len(eq) < 3:
        return np.nan
    days = pd.DatetimeIndex(exit_times).normalize()
    grid = pd.date_range(t0.normalize(), t1.normalize(), freq="D")
    grid = grid[grid.dayofweek < 5]
    if len(grid) < 5:
        return np.nan
    pos = np.clip(np.searchsorted(grid.values, days.values, side="left"), 0, len(grid) - 1)
    arr = np.full(len(grid), np.nan)
    arr[pos] = eq
    if not np.isfinite(arr[0]):
        arr[0] = INITIAL_BALANCE
    s = pd.Series(arr).ffill().values
    rets = np.diff(s) / s[:-1]
    rets = rets[np.isfinite(rets)]
    if len(rets) < 3 or rets.std(ddof=1) == 0:
        return np.nan
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))


def metrics(d, risk_pct, t0, t1):
    if len(d) == 0:
        return dict(trades=0)
    gross = d["r"].values
    fin = financing_r(d).values
    net = gross - fin
    eq = INITIAL_BALANCE * np.cumprod(1.0 + risk_pct * net)
    half = len(net) // 2
    return dict(
        trades=len(d),
        win_rate=100.0 * (gross > 0).mean(),
        gross_R=gross.sum(),
        financing_R=fin.sum(),
        net_R=net.sum(),
        exp_net_R=net.mean(),
        roi_pct=100.0 * (eq[-1] / INITIAL_BALANCE - 1.0),
        max_dd_pct=max_dd(eq),
        sharpe_daily=daily_sharpe(d["exit_time"], eq, t0, t1),
        position_days=d["hold_days"].sum(),
        max_hold_days=d["hold_days"].max(),
        maxhold_exits=int((d["reason"] == "MAXHOLD").sum()),
        h1_net_R=net[:half].mean() if half else np.nan,
        h2_net_R=net[half:].mean(),
        oos="PASS" if half and net[:half].mean() > 0 and net[half:].mean() > 0 else "FAIL",
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
_PREP_CACHE = {}


def prepared(symbol):
    if symbol in _PREP_CACHE:
        return _PREP_CACHE[symbol]
    import json
    cfgs = json.load(open(META))
    st = cfgs[symbol]["strategies"][0]
    tf, rr, params = st["timeframe"], float(st["target_rr"]), st["params"]
    risk_pct = float(cfgs[symbol]["risk_pct"])
    df = prep(load_bars(symbol, TF_SUFFIX[tf]))
    poll5 = load_bars(symbol, "5_Min") if tf != "5m" else df
    htf = None
    if params.get("htf_trend_align"):
        k = params["htf_trend_tf"]
        htf = attach_htf(df, tf, htf_trend(load_bars(symbol, HTF_FILE[k]), HTF_DELTA[k]))
    is_buy, is_sell = build_signals(df, params, htf)
    _PREP_CACHE[symbol] = (df, poll5, is_buy, is_sell, rr, risk_pct, tf)
    return _PREP_CACHE[symbol]


def run_pair(symbol, cap):
    df, poll5, is_buy, is_sell, rr, risk_pct, tf = prepared(symbol)
    d = replay(symbol, df, poll5, is_buy, is_sell, rr, SPREADS[symbol],
               STAGES.get(symbol, {}), symbol in ALWAYS_CLOSE_PAIRS,
               WEEKLY_CLOSE[symbol], WINDOW_START, WINDOW_END, cap)
    return d, risk_pct, tf


def paired_effect(symbol, cap):
    """Per-trade dR on entries BOTH configs took — the ROI columns cannot
    separate a real effect from a sequencing artifact, this can."""
    base, _, _ = run_pair(symbol, None)
    capped, _, _ = run_pair(symbol, cap)
    if len(base) == 0 or len(capped) == 0:
        return None
    a = base.set_index("entry_time")
    b = capped.set_index("entry_time")
    common = a.index.intersection(b.index)
    if len(common) < 3:
        return None
    da = a.loc[common, "r"] - financing_r(a.loc[common])
    db = b.loc[common, "r"] - financing_r(b.loc[common])
    diff = (db - da).values
    diff = diff[np.isfinite(diff)]
    se = diff.std(ddof=1) / np.sqrt(len(diff))
    return dict(pair=symbol, cap=cap, matched=len(common),
                changed=int((np.abs(diff) > 1e-9).sum()),
                mean_dR=diff.mean(),
                t_stat=diff.mean() / se if se else np.nan,
                ci_low=diff.mean() - 1.96 * se, ci_high=diff.mean() + 1.96 * se)


def main():
    quick = "--quick" in sys.argv
    pairs = ACTIVE if quick else ALL_PAIRS
    caps = [None, 3, 5, 7] if quick else CAPS

    # ---- 1. census: is the long-hold behaviour generic? ----
    census = []
    for p in pairs:
        d, risk_pct, tf = run_pair(p, None)
        if len(d) == 0:
            continue
        hd = d["hold_days"]
        census.append(dict(
            pair=p, group="ACTIVE" if p in ACTIVE else "INERT", timeframe=tf,
            trades=len(d), median_hold_hours=hd.median() * 24,
            p90_hold_days=hd.quantile(0.9), max_hold_days=hd.max(),
            trades_over_7d=int((hd > 7).sum()),
            pct_trades_over_7d=100.0 * (hd > 7).mean(),
            R_from_over_7d=d.loc[hd > 7, "r"].sum(), R_total=d["r"].sum(),
            position_days=hd.sum(),
            pct_position_days_from_over_7d=100.0 * hd[hd > 7].sum() / hd.sum(),
            median_leverage=d["lev"].median()))
    cdf = pd.DataFrame(census)
    cdf.to_csv(OUT / "backtest_max_hold_census.csv", index=False)
    print("\n=== HOLD-TIME CENSUS (no cap) ===")
    print(cdf.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # ---- 2. the cap sweep ----
    rows = []
    for p in pairs:
        for cap in caps:
            d, risk_pct, tf = run_pair(p, cap)
            m = metrics(d, risk_pct, WINDOW_START, WINDOW_END)
            m.update(pair=p, group="ACTIVE" if p in ACTIVE else "INERT",
                     cap_days="none" if cap is None else cap, risk_pct=risk_pct)
            rows.append(m)
    sdf = pd.DataFrame(rows)
    cols = ["group", "pair", "cap_days", "trades", "maxhold_exits", "win_rate",
            "gross_R", "financing_R", "net_R", "exp_net_R", "roi_pct",
            "max_dd_pct", "sharpe_daily", "position_days", "max_hold_days",
            "h1_net_R", "h2_net_R", "oos"]
    sdf = sdf[cols + [c for c in sdf.columns if c not in cols]]
    sdf.to_csv(OUT / "backtest_max_hold_sweep.csv", index=False)
    print("\n=== MAX-HOLD SWEEP (financing at 5%/yr) ===")
    print(sdf[cols].to_string(index=False, float_format=lambda x: f"{x:,.2f}"))

    # ---- 3. paired per-trade effect: the promotion-bar test ----
    pr = [r for p in pairs for cap in (3, 5, 7)
          if (r := paired_effect(p, cap)) is not None]
    pdf = pd.DataFrame(pr)
    pdf.to_csv(OUT / "backtest_max_hold_paired.csv", index=False)
    print("\n=== PAIRED PER-TRADE EFFECT (matched entries; 95% CI) ===")
    print(pdf.to_string(index=False, float_format=lambda x: f"{x:,.4f}"))
    print("\nEvery CI straddling zero means the ROI columns above are sequencing "
          "artifacts, not per-trade improvement. 7d was chosen over 3d/5d because "
          "it is the expectancy-NEUTRAL cell — 3d and 5d have negative point "
          "estimates despite scoring higher on ROI.")

    print(f"\nWrote:\n  {OUT/'backtest_max_hold_census.csv'}"
          f"\n  {OUT/'backtest_max_hold_sweep.csv'}"
          f"\n  {OUT/'backtest_max_hold_paired.csv'}")


if __name__ == "__main__":
    main()
