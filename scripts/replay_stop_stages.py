"""
Stop-stage replay over REAL live trades — 5-minute poll model
==============================================================
Companion to scripts/backtest_stop_stage_sweep.py. Takes the trades the live
system ACTUALLY took (already shaped by MAX_CONCURRENT_TRADES, cooldowns,
pre-close blocks and the Settings toggles) and re-prices each one under a
candidate stop-move stage.

⚠️ THE TRIGGER MODEL IS THE WHOLE BALLGAME — read this before trusting output.

run_pair_lock_checks() does NOT read candle closes. It calls
OandaPriceService.get_current_price(), a single S5 midpoint candle, and it is
called from run_forex_refresh_task, which cron fires at minutes
1,6,11,...,56 — i.e. the live system observes price roughly ONCE EVERY FIVE
MINUTES, whatever the pair's signal timeframe is.

So a stage can only fire on a price that was still there at a 5-minute sample.
An earlier version of this script fired stages on the intrabar HIGH of a 15m
bar and produced a completely different — and wrong — answer for XAU:

    XAU_USD, BE 0.5R -> 0.0R, 92 live trades
      intrabar-high trigger : 46.3R total, MaxDD  -5.0R   ("52% less drawdown!")
      5-minute poll trigger : 38.8R total, MaxDD -10.5R   (no DD gain, -18% return)
      no stage at all       : 47.2R total, MaxDD -10.5R

The intrabar model fires on brief spikes to the threshold, and brief spikes are
exactly the population that then reverses to -1R — so "catching" them
manufactured the entire drawdown benefit. A real 5-minute poll only sees a
SUSTAINED move to the threshold, which selects for genuine winners, truncates
them, and leaves the whipsaw losers at a full -1R. Strictly worse than doing
nothing. XAU was very nearly deployed on that artifact.

Broker-side SL and TP are different: those orders sit at Oanda and DO fill
intrabar, so they are tested against bar high/low. Only OUR stop-move decision
is poll-limited.

⚠️ BCO'S BASELINE IS NOT "NO STAGE". BCO is in ALWAYS_CLOSE_PAIRS, so production
force-flattens it before every weekly close. An unconstrained replay holds 25 of
142 BCO trades across a Friday 21:00 close (median 95 hours) and those 25
contribute +30.4R of a +9.6R total — the whole baseline comes from trades that
could never have been held. FLATTEN_FRIDAY below models this; without it BCO's
verdict flips. Any BCO comparison that skips it measures an impossible
counterfactual.

Not modelled, both mildly optimistic: spread on the moved stop (a be_to_r of
0.0 sits at the exact entry price and fills marginally negative), and the extra
trades that freed capacity would have allowed.

Coverage note: 5m history is capped at 20,000 bars (~mid-May 2026), so the poll
model can only be applied to trades from then on. Trade counts per pair are
reported — treat anything under ~30 as indicative only.

Usage: python scripts/replay_stop_stages.py
"""

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

TRADES_CSV = Path("data/cache/forex_trades_naveenf_opt_gmail_com.csv")
DATA_DIR   = Path("data/forex_raw")

# Live stages, mirroring PAIR_LOCK_CONFIGS in backend/app/services/tasks.py.
# None = pair currently runs a naked broker SL/TP with no stop movement.
PRODUCTION = {
    "BCO_USD":    dict(lock_at=2.0, lock_to=1.5),
    "NAS100_USD": dict(lock_at=1.5, lock_to=0.5),
    "JP225_USD":  dict(be_at=0.25, be_to=-0.1),
    "XAU_USD":    None,
    "XAG_USD":    None,
    "UK100_GBP":  None,
    "EUR_USD":    None,
    "USD_JPY":    None,
}
RISK_PCT = {"XAU_USD": 0.015}   # everything else 1.0%; see best_strategies.json
MAX_BARS = 12000     # ~6 weeks of 5m bars
# Pairs production force-flattens before the weekly close (ALWAYS_CLOSE_PAIRS in
# tasks.py). Their baseline MUST model this — see the header warning.
FLATTEN_FRIDAY = {"BCO_USD": (4, 20)}   # symbol -> (weekday, UTC hour)


def load_trades():
    """Closed trades with the ORIGINALLY PLACED stop reconstructed.

    ⚠️ `signal_stop_loss` is NOT the stop that was placed. oanda_trade_service
    re-anchors SL and TP off the live fill before sending the order, so
    `buy_price` (the fill) pairs with `stop_loss`/`take_profit`, never with
    `signal_stop_loss`. Mixing them fabricates the risk distance and silently
    corrupts every R, ROI, drawdown and Sharpe downstream.

    The re-anchor offset is identical for SL and TP (verified to 7e-12 across
    all 662 unmoved trades), and the stop-move job never touches TP — so for a
    trade whose stop was later moved, the original stop is recoverable as
    signal_stop_loss + (take_profit - signal_take_profit).
    """
    t = pd.read_csv(TRADES_CSV)
    for c in ("created_at", "closed_at", "updated_at"):
        t[c] = pd.to_datetime(t[c], utc=True, errors="coerce")
    t = t[t.status == "CLOSED"].copy()
    moved = t.lock_fired.notna() | t.be_fired.notna()
    offset = t.take_profit - t.signal_take_profit
    t["orig_sl"] = np.where(moved, t.signal_stop_loss + offset, t.stop_loss)
    t = t[t.orig_sl.notna() & t.take_profit.notna() & t.buy_price.notna()]
    return t[(t.buy_price - t.orig_sl).abs() > 0].sort_values("created_at")


def load_prices(symbol):
    p = pd.read_csv(DATA_DIR / f"{symbol}_5_Min.csv")
    col = "Date" if "Date" in p.columns else "Datetime"
    p[col] = pd.to_datetime(p[col], utc=True)
    return p.set_index(col).sort_index()


def replay(prices, tr, be_at=None, be_to=None, lock_at=None, lock_to=None):
    """Realised R for one live trade under the given stage config.

    Fills (broker SL/TP) use bar high/low — those orders rest at Oanda.
    Stage triggers use bar CLOSE only, modelling the 5-minute poll. Stop is
    checked before target, so same-bar ambiguity resolves against us. Lock is
    tested before breakeven, mirroring decide_stop_move.
    """
    entry = float(tr["buy_price"])
    sl = float(tr["orig_sl"])          # reconstructed; see load_trades
    tp = float(tr["take_profit"])
    direction = tr["direction"]
    risk = abs(entry - sl)
    if risk <= 0:
        return None

    cur_sl, be_done, lock_done = sl, False, False
    flat = FLATTEN_FRIDAY.get(tr["symbol"])
    for ts, b in prices[prices.index > tr["created_at"]].head(MAX_BARS).iterrows():
        hi, lo, close = float(b["High"]), float(b["Low"]), float(b["Close"])

        if flat and ts.dayofweek == flat[0] and ts.hour >= flat[1]:
            return (close - entry) / risk if direction == "BUY" else (entry - close) / risk

        if (direction == "BUY" and lo <= cur_sl) or (direction == "SELL" and hi >= cur_sl):
            return (cur_sl - entry) / risk if direction == "BUY" else (entry - cur_sl) / risk
        if (direction == "BUY" and hi >= tp) or (direction == "SELL" and lo <= tp):
            return (tp - entry) / risk if direction == "BUY" else (entry - tp) / risk

        # --- poll: only the sampled price can move our stop ---
        r_polled = (close - entry) / risk if direction == "BUY" else (entry - close) / risk
        if lock_at is not None and not lock_done and r_polled >= lock_at:
            cur_sl = entry + lock_to * risk if direction == "BUY" else entry - lock_to * risk
            lock_done = True
        elif be_at is not None and not be_done and r_polled >= be_at:
            cur_sl = entry + be_to * risk if direction == "BUY" else entry - be_to * risk
            be_done = True
    return None      # still open at the end of the price data


def evaluate(prices, trades, mid, risk_pct=0.01, **kw):
    rows = [(r["created_at"], replay(prices, r, **kw)) for _, r in trades.iterrows()]
    d = pd.DataFrame([(a, b) for a, b in rows if b is not None], columns=["date", "r"])
    if d.empty:
        return None
    rets = d.r.values * risk_pct
    eq = 10000 * np.cumprod(1 + rets)
    peak = np.maximum.accumulate(np.concatenate([[10000.0], eq]))
    dd = (np.concatenate([[10000.0], eq]) / peak - 1).min() * 100
    sd = rets.std(ddof=1) if len(rets) > 1 else np.nan
    h1, h2 = d[d.date <= mid].r, d[d.date > mid].r
    return {
        "n": len(d),
        "totR": round(float(d.r.sum()), 1),
        "meanR": round(float(d.r.mean()), 3),
        "roi%": round(float(eq[-1] / 10000 - 1) * 100, 2),
        "maxDD%": round(float(dd), 2),
        "sharpe": round(float(rets.mean() / sd * np.sqrt(252)), 2) if sd and sd > 0 else np.nan,
        "win%": round(100 * float((d.r > 0).mean()), 1),
        "h1": round(float(h1.mean()), 3) if len(h1) else np.nan,
        "h2": round(float(h2.mean()), 3) if len(h2) else np.nan,
        "oos": "PASS" if len(h1) and len(h2) and h1.mean() > 0 and h2.mean() > 0 else "FAIL",
    }


def candidate_grid():
    yield "baseline", {}
    for a, b in itertools.product([0.25, 0.5, 0.75, 1.0], [0.0, -0.1, -0.2]):
        yield f"BE {a}->{b}", dict(be_at=a, be_to=b)
    for a, b in [(1.5, 0.5), (2.0, 1.0), (2.0, 1.5), (2.5, 1.5)]:
        yield f"LOCK {a}->{b}", dict(lock_at=a, lock_to=b)


if __name__ == "__main__":
    t = load_trades()
    verdicts = []

    for symbol, live in PRODUCTION.items():
        try:
            prices = load_prices(symbol)
        except FileNotFoundError:
            print(f"\n{symbol}: no 5m data — skipped")
            continue

        tr = t[(t.symbol == symbol)
               & t.signal_stop_loss.notna()
               & t.signal_take_profit.notna()
               & (t.created_at >= prices.index.min())].sort_values("created_at")
        if len(tr) < 10:
            print(f"\n{symbol}: only {len(tr)} trades inside the 5m window — skipped")
            continue

        mid = tr.created_at.iloc[len(tr) // 2]
        print(f"\n===== {symbol}: {len(tr)} live trades "
              f"({tr.created_at.min().date()} → {tr.created_at.max().date()}) =====")

        rows = []
        for name, kw in candidate_grid():
            m = evaluate(prices, tr, mid, RISK_PCT.get(symbol, 0.01), **kw)
            if m:
                rows.append({"stage": name, **m})
        out = pd.DataFrame(rows)
        base = out.iloc[0]
        out["dROI"] = (out["roi%"] - base["roi%"]).round(2)
        out["dDD"] = (out["maxDD%"] - base["maxDD%"]).round(2)
        print(out.to_string(index=False))

        if live:
            m = evaluate(prices, tr, mid, RISK_PCT.get(symbol, 0.01), **live)
            verdicts.append({
                "pair": symbol, "live_stage": str(live), "n": m["n"],
                "roi%": m["roi%"], "base_roi%": base["roi%"],
                "dROI": round(m["roi%"] - base["roi%"], 2),
                "maxDD%": m["maxDD%"], "base_DD%": base["maxDD%"],
                "dDD": round(m["maxDD%"] - base["maxDD%"], 2),
                "sharpe": m["sharpe"], "base_sharpe": base["sharpe"],
            })
        else:
            verdicts.append({"pair": symbol, "live_stage": "none (naked SL/TP)",
                             "n": int(base["n"]), "roi%": base["roi%"],
                             "base_roi%": base["roi%"], "dROI": 0.0,
                             "maxDD%": base["maxDD%"], "base_DD%": base["maxDD%"],
                             "dDD": 0.0, "sharpe": base["sharpe"],
                             "base_sharpe": base["sharpe"]})

    print("\n\n########## PRODUCTION STAGE VERDICT (5-minute poll model) ##########")
    print(pd.DataFrame(verdicts).to_string(index=False))
