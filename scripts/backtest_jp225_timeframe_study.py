"""
JP225_USD timeframe / target_rr / stage study
=============================================
Question that started it: JP225 ran 5m + a Daily trend gate at RR 1.5 with a
breakeven stage, and had degraded live (+0.226R over 218 trades through Jul
2026 -> -0.201R over the 71 since, Welch t=-3.16, p=0.002). Would a 15m base,
a different HTF pairing, a different target, or a different stage score better
on ROI, win rate and Sharpe?

Answer it produced (adopted Oct 16, 2026): keep 5m and the Daily gate, raise
target_rr 1.5 -> 3.5, and remove the breakeven stage. See CLAUDE.md.

Engine
------
Nothing is re-implemented. The signal builder, outcome table, sequencing and
metrics are imported from scripts/backtest_htf_direction_filter.py (whose
build_signals was verified bar-by-bar against the real
SmaScalpingDetector.analyze, and which is the engine behind the Sep 19 HTF-gate
adoption). The poll-limited stop-stage replay is imported from
scripts/backtest_xag_walkforward_retune.py.

`--verify` re-checks that engine against the REAL detector for JP225
specifically, daily gate included: it samples engine-signal and
engine-non-signal bars and compares signal / direction / stop-loss.

Methodology guards inherited from those modules:
  1. GAP PRICING   - a stop hit on a session-gap bar books at that bar's OPEN.
  2. BROKER SL/TP  - tested intrabar (those orders rest at Oanda); stop tested
                     before target, so same-bar ambiguity resolves against us.
  3. OUR STOP MOVE - poll-limited to 5m closes, never intrabar.
     WARNING: the shared replay samples the poll price through the NEXT bar's
     close and then tests that same bar's range, so a stage can fire one bar
     early. It flatters any stage relative to no-stage, which makes a
     "remove the stage" conclusion conservative and a "add a stage" conclusion
     suspect. See CLAUDE.md -> Methodology Warnings.
  4. One position at a time, compounding equity, risk_pct 1.0% from
     best_strategies.json.
  5. Weekly pre-close flattening at Friday 06:00 UTC (JP225's own close time).
     Reported BOTH ways: JP225 is not in ALWAYS_CLOSE_PAIRS, so which applies
     depends on config/trade_settings -> holiday_close_enabled, which is not
     readable from the repo.
  6. NO-LOOKAHEAD on the HTF gate: an HTF bar is used only once its own close
     (open + granularity) has passed, via the as-of join in attach_htf.

Data
----
Base bars from data/forex_raw/JP225_USD_{5,15}_Min.csv (70k rows each: 5m is
~1 YEAR, 15m ~3 years). The 5m limit is why nothing here can be walk-forward
validated across regimes the way BCO and XAG were - the fit/held-out split is
*inside* one favourable year.

⚠️ The repo's JP225_USD_{4_Hour,Daily}.csv start 2024-09-22, which caps a gated
15m run at 2 years. The committed results used a BACKFILLED copy paged back to
2023-08. Recreate it with:

    python scripts/download_htf_trend_data.py      # then pass --htf-dir

and pass --htf-dir <dir>. With the default (data/forex_raw) the script still
runs but window B is ~2 years, not 3, so its numbers will NOT match the
committed CSVs.

Outputs (data/):
  backtest_jp225_tf_matrix.csv        tf x gate x target_rr x stage x flatten
  backtest_jp225_tf_walkforward.csv   fit / held-out split, 15m long window
  backtest_jp225_rr_ladder.csv        target_rr 1.5-10, both stage settings,
                                      both flatten settings - the plateau check
  backtest_jp225_stage_grid.csv       25 stage cells at the adopted target,
                                      paired dR vs no-stage with t and p
  backtest_jp225_gate_split.csv       kept-vs-blocked expectancy per HTF gate
  backtest_jp225_mfe.csv              max favourable excursion of the REAL live
                                      trades - is a bigger target reachable?
                                      NEEDS an export (see below); skipped
                                      without one.

The MFE step is the only part that needs live data, and the repo deliberately
does NOT carry raw trade prices (every tracked CSV here is an aggregate). Export
it yourself to data/live_trades_jp225.csv with columns
open_ts,direction,buy_price,orig_sl from the forex_portfolio Firestore
collection, where orig_sl is the ORIGINALLY PLACED stop - for a trade whose stop
was later moved that is signal_stop_loss + (take_profit - signal_take_profit),
NOT stop_loss. See CLAUDE.md -> Methodology Warnings, "signal_stop_loss is NOT
the stop that was placed"; pairing the wrong one fabricates every R.

Usage:
  python scripts/backtest_jp225_timeframe_study.py --htf-dir <dir> [--verify]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest_htf_direction_filter as H          # noqa: E402
import backtest_xag_walkforward_retune as X        # noqa: E402

SYMBOL = "JP225_USD"
SPREAD = H.SPREADS[SYMBOL]
WEEKLY_CLOSE = H.WEEKLY_CLOSE[SYMBOL]              # Friday 06:00 UTC
RISK_PCT = 0.01
RETIRED_STAGE = {"be_at_r": 0.25, "be_to_r": -0.1, "sl_precision": 1}
STAGE_CFG = RETIRED_STAGE   # the stage this study REMOVED; kept to reproduce the before/after
ADOPTED_RR = 3.5
TF_SUFFIX = {"5m": "5_Min", "15m": "15_Min"}
GRAN_DELTA = {"4h": pd.Timedelta(hours=4), "daily": pd.Timedelta(days=1)}
HTF_FILE = {"4h": "4_Hour", "daily": "Daily"}
FIT_END = pd.Timestamp("2025-12-31 23:59:59")

# replay_with_stage reads these as module globals in the XAG module
X.WEEKLY_CLOSE = WEEKLY_CLOSE


def load_base(tf):
    return H.prep_base(H.load_bars(SYMBOL, TF_SUFFIX[tf]))


def load_gates(base, tf, htf_dir):
    """{gate_name: (buy_ok, sell_ok)} plus the window the gates are valid over."""
    gates, raw, starts, ends = {}, {}, [], []
    for name in ("4h", "daily"):
        fn = Path(htf_dir) / f"{SYMBOL}_{HTF_FILE[name]}.csv"
        df = pd.read_csv(fn)
        d = pd.to_datetime(df["Date"], utc=True, format="mixed")
        df = df.assign(Date=d.dt.tz_convert(None)).set_index("Date").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        tr = H.htf_trend(df, GRAN_DELTA[name])
        starts.append(tr["htf_close"].min())
        ends.append(tr["htf_close"].max())
        t = H.attach_htf(base, tf, tr, GRAN_DELTA[name]).values
        gates[name] = (t == 1, t == -1)
        raw[name] = df
    return gates, max(starts), min(ends), raw


def run_variant(base, out, tf, gate, rr, flatten, params, mask, poll5=None, stage=False):
    is_buy, is_sell = H.build_signals(base, params)
    is_buy, is_sell = is_buy & mask, is_sell & mask
    if gate is not None:
        is_buy, is_sell = is_buy & gate[0], is_sell & gate[1]
    t0, t1 = base.index[mask].min(), base.index[mask].max()
    if stage:
        tr = X.replay_with_stage(base, poll5, is_buy, is_sell, rr, SPREAD, STAGE_CFG, flatten)
        if not len(tr):
            m = H.metrics(pd.DatetimeIndex([]), np.array([]), RISK_PCT, t0, t1)
            m["promotion_bar_pass"] = False
            return m
        tdf = pd.DataFrame(tr, columns=["ei", "xi", "r", "be", "lk"])
        xt = base.index[tdf["xi"].values]
        rs = tdf["r"].values
    else:
        ent, ex, rs = H.walk(out, is_buy, is_sell, rr, flatten)
        xt = base.index[ex] if len(ex) else pd.DatetimeIndex([])
    m = H.metrics(xt, rs, RISK_PCT, t0, t1)
    m["promotion_bar_pass"] = H.passes_bar(m)
    return m


def verify_engine_vs_detector(d, params_full, rr, n_sample=200, seed=0):
    """Sample engine-signal and engine-non-signal bars and compare the imported
    engine against the REAL SmaScalpingDetector, daily gate included."""
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.sma_scalping_detector import SmaScalpingDetector
    base, gate = d["base"], d["gates"]["daily"]
    params = {k: v for k, v in params_full.items()
              if k not in ("htf_trend_align", "htf_trend_tf")}
    ib, isl = H.build_signals(base, params)
    eb, es = ib & gate[0], isl & gate[1]
    htf = d["htf_raw"]["daily"]
    det = SmaScalpingDetector()
    rng = np.random.default_rng(seed)
    si = np.where(eb | es)[0]
    ni = np.where(~(eb | es))[0]
    ni = ni[ni > 200]
    sample = np.concatenate([rng.choice(si, min(n_sample, len(si)), replace=False),
                             rng.choice(ni, n_sample, replace=False)])
    out = H.Outcomes(base, 0.0, WEEKLY_CLOSE)
    mm_sig = mm_dir = mm_sl = 0
    for t in sample:
        data = {"base": base.iloc[t - 149:t + 1], "htf_trend": htf[htf.index <= base.index[t]]}
        r = det.analyze(data, SYMBOL, target_rr=rr, spread=0.0, params=params_full)
        exp = "BUY" if eb[t] else ("SELL" if es[t] else None)
        got = r["signal"] if r else None
        if (got is None) != (exp is None):
            mm_sig += 1
            continue
        if exp is None:
            continue
        if got != exp:
            mm_dir += 1
            continue
        sl = out.sl_b[t] if exp == "BUY" else out.sl_s[t]
        if abs(r["stop_loss"] - sl) > 1e-6 * max(1.0, abs(sl)):
            mm_sl += 1
    print(f"engine fidelity vs real detector: {len(sample)} bars sampled "
          f"({len(sample) - n_sample} signal + {n_sample} non-signal) -> "
          f"{mm_sig} signal, {mm_dir} direction, {mm_sl} stop-loss mismatches")
    return mm_sig + mm_dir + mm_sl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--htf-dir", default=None,
                    help="directory holding backfilled JP225 H4/Daily CSVs "
                         "(default: data/forex_raw)")
    ap.add_argument("--verify", action="store_true",
                    help="re-check the engine against the real detector first")
    args = ap.parse_args()
    htf_dir = args.htf_dir or (ROOT / "data" / "forex_raw")

    cfg = json.loads((ROOT / "data" / "metadata" / "best_strategies.json").read_text())
    prod = cfg[SYMBOL]["strategies"][0]
    params = {k: v for k, v in prod["params"].items()
              if k not in ("htf_trend_align", "htf_trend_tf")}
    prod_rr = prod["target_rr"]
    print(f"config under test: 5m  rr={prod_rr}  gate=daily  params={params}")

    data = {}
    for tf in ("5m", "15m"):
        base = load_base(tf)
        gates, g0, g1, htf_raw = load_gates(base, tf, htf_dir)
        bclose = base.index + H.TF_DELTA[tf]
        valid = np.asarray((bclose >= g0) & (bclose <= g1))
        data[tf] = dict(base=base, gates=gates, valid=valid, htf_raw=htf_raw,
                        out=H.Outcomes(base, SPREAD, WEEKLY_CLOSE))
        print(f"{tf:3s}: {len(base)} bars {base.index[0]} -> {base.index[-1]}; "
              f"gates valid {base.index[valid].min()} -> {base.index[valid].max()}")
    poll5 = data["5m"]["base"][["Close"]]

    if args.verify:
        if verify_engine_vs_detector(data["5m"], prod["params"], prod_rr) != 0:
            raise SystemExit("engine does NOT match the real detector — fix before trusting output")

    # Window A: the overlap of the 5m file and the gate validity -> both TFs equal
    a0 = max(data["5m"]["base"].index[data["5m"]["valid"]].min(),
             data["15m"]["base"].index[data["15m"]["valid"]].min())
    a1 = min(data["5m"]["base"].index[data["5m"]["valid"]].max(),
             data["15m"]["base"].index[data["15m"]["valid"]].max())
    print(f"\nwindow A (head-to-head) {a0} -> {a1}")
    print(f"window B (15m long)     {data['15m']['base'].index[data['15m']['valid']].min()} -> "
          f"{data['15m']['base'].index[data['15m']['valid']].max()}")

    RRS = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
    rows = []
    for win, label in (("A", "head2head_1yr"), ("B", "15m_long_3yr")):
        for tf in ("5m", "15m"):
            if win == "B" and tf == "5m":
                continue
            d = data[tf]
            mask = d["valid"].copy()
            if win == "A":
                mask &= np.asarray((d["base"].index >= a0) & (d["base"].index <= a1))
            for gname in ("none", "4h", "daily"):
                gate = None if gname == "none" else d["gates"][gname]
                for rr in RRS:
                    for flatten in (True, False):
                        for stage in (True, False):
                            m = run_variant(d["base"], d["out"], tf, gate, rr, flatten,
                                            params, mask, poll5 if tf == "15m" else d["base"][["Close"]],
                                            stage=stage)
                            rows.append({"window": label, "tf": tf, "gate": gname,
                                         "target_rr": rr, "flatten": flatten,
                                         "stage": "BE 0.25->-0.1" if stage else "none",
                                         **m})
            print(f"  done {label} {tf}")
    mat = pd.DataFrame(rows)
    mat.to_csv(ROOT / "data" / "backtest_jp225_tf_matrix.csv", index=False)
    print(f"\nSaved {len(mat)} rows -> data/backtest_jp225_tf_matrix.csv")

    # ---- Window C: walk-forward on the 15m long window -------------------
    d = data["15m"]
    wf = []
    for gname in ("none", "4h", "daily"):
        gate = None if gname == "none" else d["gates"][gname]
        for rr in RRS:
            for stage in (True, False):
                for part, mk in (("fit", d["valid"] & np.asarray(d["base"].index <= FIT_END)),
                                 ("heldout", d["valid"] & np.asarray(d["base"].index > FIT_END))):
                    m = run_variant(d["base"], d["out"], "15m", gate, rr, True,
                                    params, mk, poll5, stage=stage)
                    wf.append({"part": part, "gate": gname, "target_rr": rr,
                               "stage": "BE" if stage else "none", **m})
    wfd = pd.DataFrame(wf)
    wfd.to_csv(ROOT / "data" / "backtest_jp225_tf_walkforward.csv", index=False)
    print(f"Saved {len(wfd)} rows -> data/backtest_jp225_tf_walkforward.csv")

    d5 = data["5m"]
    gate5 = d5["gates"]["daily"]
    rr_ladder(d5, gate5, params, poll5)
    stage_grid(d5, gate5, params, poll5)
    gate_split(d5, params, poll5)
    mfe_table(d5)
    return mat, wfd


# ---------------------------------------------------------------------------
# target_rr ladder -- the plateau check. Reported for BOTH stage settings and
# BOTH flatten settings, because the ladder's SHAPE differs between them and
# quoting the wrong one is an easy way to claim a plateau that isn't there.
# ---------------------------------------------------------------------------
def _path_stats(tr, base):
    rs = tr["r"].values
    eq = INITIAL = 10_000.0
    eq = INITIAL * np.cumprod(1.0 + RISK_PCT * rs)
    full = np.concatenate([[INITIAL], eq])
    dd = ((full - np.maximum.accumulate(full)) / np.maximum.accumulate(full) * 100).min()
    half = len(rs) // 2
    fit = tr["exit"] <= FIT_5M_SPLIT
    hold_d = ((base.index[tr["xi"].values].values - base.index[tr["ei"].values].values)
              .astype("timedelta64[m]").astype(float) / 1440.0)
    return dict(trades=len(rs), win_rate=round(100 * (rs > 0).mean(), 1),
                exp_R=round(float(rs.mean()), 4), total_R=round(float(rs.sum()), 1),
                roi_pct=round(100 * (eq[-1] / INITIAL - 1), 2), max_dd_pct=round(dd, 2),
                ret_over_dd=round(abs(100 * (eq[-1] / INITIAL - 1) / dd), 2) if dd < 0 else np.nan,
                h1_R=round(float(rs[:half].mean()), 4), h2_R=round(float(rs[half:].mean()), 4),
                fit_expR=round(float(tr.loc[fit, "r"].mean()), 4),
                heldout_expR=round(float(tr.loc[~fit, "r"].mean()), 4),
                max_hold_days=round(float(hold_d.max()), 1),
                mean_hold_h=round(float(hold_d.mean() * 24), 1))


FIT_5M_SPLIT = pd.Timestamp("2026-03-31 23:59:59")
RR_LADDER = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0, 8.0, 10.0]


def causal_poll(poll, tf="5m"):
    """Shift the poll index forward one bar.

    `replay_with_stage` samples poll prices through the NEXT bar's close and
    then tests that same bar's range, so a stop move decided at bar k's close
    is applied to bar k's OWN high/low — a one-bar lookahead. Shifting the poll
    index by one bar period makes the move apply from bar k+1 onward, which is
    what a 5-minutely production poll actually achieves.

    MEASURED on JP225 at RR 3.5: as-shipped the retired BE stage scores ROI
    +47.8% / expR +0.210, causally it scores +75.0% / +0.303. So the
    as-shipped off-by-one makes a stage look WORSE than it is, and its paired
    ΔR vs no-stage goes from -0.325R (p=0.0155) to -0.206R (p=0.1024). Any
    "this stage is harmful" verdict from the unshifted engine is overstated.
    No-stage runs are unaffected — they never sample a poll.
    """
    out = poll.copy()
    out.index = out.index + H.TF_DELTA[tf]
    return out


def _replay(base, poll5, is_buy, is_sell, rr, stage, flatten):
    tr = pd.DataFrame(X.replay_with_stage(base, poll5, is_buy, is_sell, rr, SPREAD, stage, flatten),
                      columns=["ei", "xi", "r", "be", "lk"])
    if len(tr):
        tr["exit"] = base.index[tr["xi"].values]
    else:
        tr["exit"] = pd.Series(dtype="datetime64[ns]")
    return tr


def _gated(base, params, gate):
    is_buy, is_sell = H.build_signals(base, params)
    return is_buy & gate[0], is_sell & gate[1]


def rr_ladder(d, gate, params, poll5):
    base = d["base"]
    ib, isl = _gated(base, params, gate)
    poll = causal_poll(poll5)
    rows = []
    for flatten in (True, False):
        for stage, lab in ((RETIRED_STAGE, "BE 0.25->-0.1"), ({}, "none")):
            for rr in RR_LADDER:
                tr = _replay(base, poll, ib, isl, rr, stage, flatten)
                rows.append({"target_rr": rr, "stage": lab, "flatten": flatten,
                             "poll_model": "causal", **_path_stats(tr, base)})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "data" / "backtest_jp225_rr_ladder.csv", index=False)
    print(f"Saved {len(out)} rows -> data/backtest_jp225_rr_ladder.csv")
    for flatten in (True, False):
        for lab in ("none", "BE 0.25->-0.1"):
            sub = out[(out.flatten == flatten) & (out.stage == lab)].sort_values("target_rr")
            best = sub.loc[sub["ret_over_dd"].idxmax(), "target_rr"]
            print(f"  flatten={'ON ' if flatten else 'OFF'} stage={lab:14s} "
                  f"ret/DD peak at rr={best}: "
                  + " ".join(f"{r.target_rr:g}:{r.ret_over_dd:.2f}" for r in sub.itertuples()))
    return out


# ---------------------------------------------------------------------------
# Stage grid at the ADOPTED target, with the paired test CLAUDE.md requires.
# Paired on identical ENTRY BARS: a stage changes how a trade exits, so the
# same entry appears in both arms and the difference is a per-trade delta.
# ---------------------------------------------------------------------------
def _stage_cells():
    cells = [{}]
    for at in (0.25, 0.5, 1.0, 1.5):
        for to in (-0.2, -0.1, 0.0):
            cells.append({"be_at_r": at, "be_to_r": to, "sl_precision": 1})
    for at in (1.5, 2.0, 2.5, 3.0):
        for to in (0.5, 1.0, 1.5, 2.0):
            if to < at:
                cells.append({"lock_at_r": at, "lock_to_r": to, "sl_precision": 1})
    return cells


def _stage_label(c):
    if not c:
        return "no stage"
    if "be_at_r" in c:
        return f"BE {c['be_at_r']}->{c['be_to_r']}"
    return f"lock {c['lock_at_r']}->{c['lock_to_r']}"


def stage_grid(d, gate, params, poll5, rr=None, flatten=True):
    from scipy import stats
    rr = rr or ADOPTED_RR
    base = d["base"]
    ib, isl = _gated(base, params, gate)
    rows = []
    for poll, model in ((causal_poll(poll5), "causal"), (poll5, "as-shipped")):
        bl = _replay(base, poll, ib, isl, rr, {}, flatten)
        for c in _stage_cells():
            tr = _replay(base, poll, ib, isl, rr, c, flatten)
            if len(tr) < 30:
                continue
            m = tr.merge(bl, on="ei", suffixes=("_s", "_b"))
            dr = m["r_s"] - m["r_b"]
            tt, pv = stats.ttest_1samp(dr, 0) if len(dr) > 2 else (np.nan, np.nan)
            ch = m[dr.abs() > 1e-9]
            rows.append({"stage": _stage_label(c), "target_rr": rr, "flatten": flatten,
                     "poll_model": model, **_path_stats(tr, base),
                     "paired_n": len(m), "changed": int(len(ch)),
                     "dR_vs_none": round(float(dr.mean()), 4),
                     "t": round(float(tt), 2), "p": round(float(pv), 4),
                     "R_truncated": round(float((ch.loc[ch["r_b"] > ch["r_s"], "r_s"]
                                                 - ch.loc[ch["r_b"] > ch["r_s"], "r_b"]).sum()), 1),
                     "R_rescued": round(float((ch.loc[ch["r_b"] < ch["r_s"], "r_s"]
                                               - ch.loc[ch["r_b"] < ch["r_s"], "r_b"]).sum()), 1)})
    out = pd.DataFrame(rows).sort_values(["poll_model", "ret_over_dd"], ascending=[True, False])
    out.to_csv(ROOT / "data" / "backtest_jp225_stage_grid.csv", index=False)
    print(f"Saved {len(out)} rows -> data/backtest_jp225_stage_grid.csv")
    for model in ("causal", "as-shipped"):
        g = out[out.poll_model == model]
        b = g[g.stage == "no stage"].iloc[0]
        better = g[(g.stage != "no stage") & (g.roi_pct > b.roi_pct)
                   & (g.max_dd_pct > b.max_dd_pct)]
        sig_neg = g[(g.p < 0.05) & (g.dR_vs_none < 0)]
        best = g.loc[g["ret_over_dd"].idxmax()]
        print(f"  [{model:10s}] no-stage ROI {b.roi_pct}% DD {b.max_dd_pct}% ret/DD {b.ret_over_dd}; "
              f"best ret/DD cell = {best.stage} ({best.ret_over_dd}); "
              f"beating no-stage on BOTH roi and dd: {len(better)}; "
              f"significantly negative dR: {len(sig_neg)} of {len(g) - 1}")
    return out


# ---------------------------------------------------------------------------
# Is an HTF gate earning its keep? With NO stage a trade's outcome depends only
# on its entry bar, so a gate changes WHICH trades are taken, not how any trade
# ends -- a paired test is identically zero and meaningless. The real test is
# whether the trades a gate BLOCKS were worse than the ones it ADMITS.
# ---------------------------------------------------------------------------
def gate_split(d, params, poll5, rr=None, flatten=True):
    from scipy import stats
    rr = rr or ADOPTED_RR
    base = d["base"]
    ib, isl = H.build_signals(base, params)
    tr = _replay(base, poll5, ib, isl, rr, {}, flatten)
    rows = []
    for name in ("4h", "daily"):
        gb, gs = d["gates"][name]
        ok = np.array([bool((gb[i] and ib[i]) or (gs[i] and isl[i])) for i in tr["ei"]])
        a, b = tr.loc[ok, "r"].values, tr.loc[~ok, "r"].values
        tt, pv = stats.ttest_ind(a, b, equal_var=False)
        se = float(np.hypot(a.std(ddof=1) / np.sqrt(len(a)), b.std(ddof=1) / np.sqrt(len(b))))
        rows.append({"gate": name, "target_rr": rr,
                     "admitted_n": len(a), "admitted_expR": round(float(a.mean()), 4),
                     "admitted_WR": round(100 * float((a > 0).mean()), 1),
                     "blocked_n": len(b), "blocked_expR": round(float(b.mean()), 4),
                     "blocked_WR": round(100 * float((b > 0).mean()), 1),
                     "difference_R": round(float(a.mean() - b.mean()), 4),
                     "welch_t": round(float(tt), 2), "p": round(float(pv), 4),
                     "ci_lo": round(float(a.mean() - b.mean() - 1.96 * se), 3),
                     "ci_hi": round(float(a.mean() - b.mean() + 1.96 * se), 3)})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "data" / "backtest_jp225_gate_split.csv", index=False)
    print(f"Saved {len(out)} rows -> data/backtest_jp225_gate_split.csv")
    for r in out.itertuples():
        print(f"  {r.gate:5s} gate: admits {r.admitted_n} at {r.admitted_expR:+.3f}R, "
              f"blocks {r.blocked_n} at {r.blocked_expR:+.3f}R  "
              f"diff {r.difference_R:+.3f}R t={r.welch_t:+.2f} p={r.p}")
    return out


# ---------------------------------------------------------------------------
# Was a bigger target ever REACHABLE? Measured on the REAL live trades, not
# simulated ones: for each closed JP225 trade that actually ran at RR ~1.5,
# how far did price go in our favour before the ORIGINAL stop would have
# filled? This is the check that should gate any target change, in either
# direction -- see CLAUDE.md -> Live divergence.
#
# Needs the live trade export; skipped with a message when absent.
# ---------------------------------------------------------------------------
def mfe_table(d, trades_csv=None):
    path = Path(trades_csv) if trades_csv else (ROOT / "data" / "live_trades_jp225.csv")
    if not path.exists():
        print(f"  (skipping MFE: no live-trade export at {path}; see docstring)")
        return None
    base = d["base"]
    lv = pd.read_csv(path)
    lv["open_ts"] = pd.to_datetime(lv["open_ts"], utc=True).dt.tz_localize(None)
    bars = base[["High", "Low"]]
    recs = []
    for _, r in lv.iterrows():
        sgn = -1 if str(r["direction"]).upper().startswith("S") else 1
        risk = abs(r["buy_price"] - r["orig_sl"])
        if not risk > 0:
            continue
        w = bars[(bars.index >= r["open_ts"]) & (bars.index <= r["open_ts"] + pd.Timedelta(days=10))]
        best = -np.inf
        for _, b in w.iterrows():
            adv = (b["High"] - r["buy_price"]) / risk if sgn == 1 else (r["buy_price"] - b["Low"]) / risk
            best = max(best, adv)
            if (b["Low"] <= r["orig_sl"]) if sgn == 1 else (b["High"] >= r["orig_sl"]):
                break
        if np.isfinite(best):
            recs.append({"open_ts": r["open_ts"], "direction": r["direction"], "mfe_R": best})
    m = pd.DataFrame(recs)
    rows = [{"target_rr": rr, "pct_reaching": round(100 * float((m["mfe_R"] >= rr).mean()), 1),
             "implied_expR": round(float((m["mfe_R"] >= rr).mean() * rr
                                         - (1 - (m["mfe_R"] >= rr).mean())), 4)}
            for rr in RR_LADDER]
    out = pd.DataFrame(rows)
    out["n_trades"] = len(m)
    for q in (25, 50, 75, 90, 95):
        out[f"mfe_p{q}"] = round(float(np.percentile(m["mfe_R"], q)), 2)
    out.to_csv(ROOT / "data" / "backtest_jp225_mfe.csv", index=False)
    print(f"Saved {len(out)} rows -> data/backtest_jp225_mfe.csv  (n={len(m)} live trades)")
    return out


if __name__ == "__main__":
    main()
