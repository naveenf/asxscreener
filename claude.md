# ASX Stock Screener - Project Context

## Project Overview
Full-stack app identifying trading opportunities on ASX and Global Forex/Commodity markets via a **Dynamic Strategy Selection** engine. Calculations match **Pine Script** (TradingView) standards using Wilder's Smoothing.

**Strategies (active):** SMA Scalping.

---

## Git Workflow

### ⚠️ NEVER commit without explicit user confirmation — no exceptions

This applies to **all contexts**: direct edits, subagents, implementation plans, automated workflows, and skill-driven development. No commit may be created by any agent or subagent without the user first approving the exact commit message.

**Conventional Commits format** (1-2 lines max):
```
feat: Add time-based volatility filters for Silver strategies
fix: Correct DailyORB session_start parameter
```
**Allowed types:** `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `perf`

**Rules:**
- ✅ 1-2 lines max, meaningful action verbs, specific scope
- ❌ NO verbose paragraphs, NO co-author lines, NO implementation details

**Workflow:** Implement → ask "Ready to commit: `<msg>`?" → user approves → commit → push only if explicitly requested.

**Subagent/plan execution rule:** When dispatching subagents or executing implementation plans, instruct every subagent NOT to commit. Collect all changes, then present a single commit summary to the user for approval before committing.

---

## Tech Stack

- **Backend:** FastAPI (Python 3.10+), Pandas/NumPy, yfinance + Oanda, Firebase Firestore + Auth, pytest
- **Frontend:** React 18, Vite, CSS Modules, `@react-oauth/google`, Recharts
- **Start:** `start.py` (unified launcher)

---

## Directory Structure

```
asx-screener/
├── backend/app/
│   ├── api/                    # Routes (auth, portfolio, stocks)
│   ├── models/                 # Pydantic models
│   └── services/
│       ├── indicators.py                  # ADX, DI, RSI, BB
│       ├── forex_screener.py              # Dynamic Strategy Orchestrator
│       ├── sma_scalping_detector.py       # SMA Scalping (active)
│       └── strategy_interface.py          # Abstract Base Class
├── data/
│   ├── raw/                    # Stock CSVs
│   ├── forex_raw/              # Forex MTF CSVs (5m, 15m, 1h, 4h)
│   └── metadata/
│       ├── best_strategies.json  # Strategy config map (source of truth)
│       ├── forex_pairs.json
│       └── stock_list.json
├── scripts/                    # Backtest sweeps — see Documentation Organization
│   └── download_forex.py       # Data fetcher
└── docs/analysis/              # Backtest reports
```

---

## Trading Strategies

All 8 active pairs run **SmaScalping** only (SMA20/50/100 stack, DI+/DI-, ATR SL floor).
Everything else — HeikenAshi, DailyORB, SilverSniper, PVTScalping, NewBreakout — is archived
in `data/metadata/best_strategies_archived.json` and not running.

### Core mechanics

**Entry (LONG):** Price > SMA20/50/100 · DI+ > DI- · DI+ > threshold for N candles · ADX ≥ adx_min · entry not below 2-candle lows
**Stop loss:** `max(structural_distance, 1×ATR)` — the ATR floor prevents noise-triggered stops.
**Exit:** Broker-level SL and TP placed on Oanda at entry. A trade closes **only** on SL or TP.
No trailing exit — SMA20 trailing was validated harmful on every pair (60–89% of trades cut
short, avg-R collapsing below 0.25R). Do not re-enable `check_exit` for SmaScalping.

### Filter reference

Configured per-pair in `best_strategies.json`.

| Filter | Meaning |
|--------|---------|
| `di_persist` | DI must exceed threshold for N consecutive candles. **Timeframe-sensitive** — 2 candles is 30 min on 15m but only 10 min on 5m, so the same value behaves differently. |
| `adx_min` | ADX floor. |
| `adx_rising` | ADX must be rising vs the previous candle. |
| `atr_ratio_min` | ATR ≥ N × its 20-bar average — gates on volatility regime. |
| `di_slope` | DI must be rising vs 2 candles ago (live: `iloc[-1] > iloc[-3]`). |
| `avoid_hours` | Block entry during these UTC hours. |
| `di_spread_min` | Minimum DI+/DI- gap — rejects marginal crossings. |
| `body_ratio_min` | Minimum candle body/range ratio — rejects dojis. |

---

## Active Configuration

Source of truth is `best_strategies.json` (+ `forex_pairs.json` for the pair list). This table
mirrors it — if they disagree, the JSON wins.

| Asset | TF | RR | risk | DI> | persist | Other filters | Sharpe | MaxDD% |
|-------|----|----|------|-----|---------|---------------|--------|--------|
| XAU_USD | 15m | 3.5 | 1.5% | 35 | 2 | `adx_rising`, `avoid[8,9]` | 6.48 | -7.73 |
| XAG_USD | 15m | 3.0 | 1.0% | 35 | 2 | `atr_ratio=1.2`, `di_slope` | 4.60 † | -6.28 |
| JP225_USD | 5m | 1.5 | 1.0% | 30 | 2 | `adx_min=20`, `adx_rising`, `di_slope`, `atr_ratio=1.2`, `di_spread=15`, `avoid[21-23]` | 5.87 | -5.85 |
| NAS100_USD | 15m | 3.5 | 1.0% | 35 | 2 | `adx_min=30`, `atr_ratio=1.2`, `di_slope`, `avoid[7,8,20-23]` | 14.36 ‡ | -1.99 |
| UK100_GBP | 15m | 3.5 | 1.0% | 35 | 2 | `atr_ratio=1.2`, `avoid[15-19]` | 8.45 ‡ | -3.94 |
| BCO_USD | 15m | 2.5 | 1.0% | 30 | 1 | `adx_min=15`, `atr_ratio=1.0`, `avoid[20-23]` | 1.47 † | -17.91 |
| EUR_USD | 15m | 6.0 | 1.0% | 25 | 2 | `atr_ratio=1.0`, `avoid[20-23]` | 5.56 ‡ | -10.47 |
| USD_JPY | 15m | 3.0 | 0.5% | 30 | 1 | `avoid[15-21]` | 2.85 ‡ | -8.65 |

† Measured with gapped stops priced at the true post-weekend open. **Not comparable** to the
other rows, which use the legacy backtester that books every stop at exactly -1R (see the
gap-pricing warning below). Lower ≠ worse.
‡ Live performance has diverged from these figures — see *Live divergence* below.

**Disabled at runtime** via the Settings page (Firestore `config/strategy_overrides`, not the
JSON): **EUR_USD** and **USD_JPY**, both for sustained negative live returns. Their configs are
retained above so re-enabling needs no re-derivation.

### Live divergence (as of Aug 2026, 927 trades since Mar 10)

Backtest Sharpe has consistently over-predicted live results. Live P&L by pair:
XAU +$3,128 · JP225 +$1,183 · XAG +$1,020 · NAS100 -$89 · EUR_USD -$95 · BCO -$97 ·
USD_JPY -$302 · UK100 -$460.

Root cause is **execution, not signal**: realised payoff (avg win ÷ avg loss) sits at ~1.5 on
every pair regardless of the configured R:R, because winners get closed manually well before
TP. The higher the target, the less often it is reached — JP225's 1.5R target is hit on 47% of
wins, XAG's old 12R on 1.5%. **The pairs whose targets match actual holding behaviour are the
profitable ones.** Set `target_rr` to what will actually be held, not to what maximises a
backtest.

---

## Stop-Move Stages

Config: `PAIR_LOCK_CONFIGS` in `tasks.py`. Decision logic is the pure function
`decide_stop_move()` (tested in `backend/tests/test_stop_stage_decision.py`). Two stage types,
either or both per pair. Firestore state: `config/lock_state_{symbol}` → `{cooldown_until}`,
written only for pairs with `cooldown_min`.

- **Profit lock** (`lock_at_r`/`lock_to_r`) — late trigger, moves SL into profit to protect a
  large winner from reversing. Sets `lock_fired`, starts a cooldown blocking new entries
  (spent-momentum guard).
- **Breakeven** (`be_at_r`/`be_to_r`) — early trigger, moves SL to a small loss. For pairs with
  a small TP and no fat tail to protect, where the pain is the *count* of full -1R losses. Sets
  `be_fired`, no cooldown — nothing was locked in, so blocking re-entry has no rationale.

| Pair | Stage | Justification |
|------|-------|---------------|
| BCO_USD | Lock 2R→+1R, cooldown 90 min | Sharpe 1.67→2.44; ~20 trades per dataset rescued from 2R reversals |
| NAS100_USD | Lock 1.5R→+0.5R, cooldown 90 min | MaxDD -10.47%→-5.44%, ROI +27.8%→+32.8%, WR 35.4%→52.3%, months positive 7/11→9/11 |
| JP225_USD | Breakeven 0.25R→-0.1R, no cooldown | Sharpe 2.53→5.63, MaxDD -6.83%→-2.28%; full -1R losses cut from 100%→15% of trades |

**Neither stage generalises — sweep before adding one.** Run
`scripts/backtest_stop_stage_sweep.py` (self-contained; gap-priced, OOS-gated) against the pair's
current config. Results so far (`data/backtest_stop_stage_sweep.csv`, 151 configs per pair):

| Pair | Outcome |
|------|---------|
| NAS100_USD | **149/151 configs cut drawdown** — structural, not a lucky cell. Adopted lock 1.5R→+0.5R. |
| XAG_USD | 82/151 cut drawdown but only **1/151** held ROI, and none passed OOS. Median ROI 64.5%→39.3% for no DD gain. Do not add. |
| XAU_USD | Only **3/151** cut drawdown; the median makes it *worse* (-7.28%→-9.97%). Harmful on both axes. Do not add. |
| All 8 pairs (breakeven, Aug 2026) | Only JP225 clears convincingly. XAU, UK100, USD_JPY, BCO: 0/20. |

**NAS100 caveats.** Trade count rises 48→65 because early exits free capacity in a
one-position-at-a-time simulator, so this is not a pure like-for-like. Cooldown is not modelled
either — treat lock rows as an upper bound. And NAS100 is the pair whose backtests have diverged
most from live (-$89 realised against a recorded 14.36 Sharpe), so this was adopted as **risk
reduction on a pair that is not currently earning**, not as an ROI upgrade. Breakeven was also
viable here (BE 1.0→0.0 + lock 1.5→0.5 gave MaxDD -4.49%) but deliberately not adopted — one
mechanism is enough on this pair.

⚠️ **Do not add equality filters to the cooldown query.** `check_pair_lock_cooldowns()` runs ONE
Firestore query filtering on `updated_at` alone (`COOLDOWN_LOOKBACK_MIN`, 6h) and applies
symbol/status/`lock_fired`/`lock_cooldown_set` client-side in `select_cooldown_candidates()`.
That keeps it on Firestore's automatic single-field index. The previous version filtered
server-side per pair and returned every locked trade ever, on every cycle — ~14k reads/day,
growing with history and with each pair added. Adding those filters back needs a composite index,
and this project has no versioned index config (no `firestore.indexes.json`), so it would fail
only at runtime.

**XAG has no lock.** Its 3R→+2R lock was removed with the 15m/RR3.0 migration — the take-profit
*is* 3R there, so the lock could never fire. Re-add only with a threshold swept against the
current config.

---

## Weekly Pre-Close

Positions are flattened before the weekly close by `run_preclose_check()` in `tasks.py`
(scheduled every 5 min in `main.py`), driven by `market_close_schedule.py`:

- `WEEKLY_CLOSE_UTC` — per-pair Friday close time (most pairs 21:00 UTC; UK100 16:30; JP225 06:00)
- Entries blocked from **65 min** before close, positions closed from **60 min** before
- Holiday-aware, and each trade can opt out with `keep_through_close=True`

**Global toggle:** `config/trade_settings` → `holiday_close_enabled` (default True). When off,
ordinary pre-close flattening is deferred so positions can be carried through a holiday —
**entries stay blocked either way**.

**`ALWAYS_CLOSE_PAIRS` (`tasks.py`) overrides that toggle.** Currently `{"BCO_USD"}`. Decision
logic is the pure function `pairs_to_close_now()` (tested in
`backend/tests/test_preclose_always_close.py`). Per-trade `keep_through_close` still wins.

**Why BCO is forced:** its weekend gaps are **2.73 ATR at the median** against a 1×ATR stop
floor, and 61% of weekends gap more than 2 ATR. A broker stop fills at the gapped open, not the
stop price, so the position is unprotected regardless of the toggle. Live cost: the Apr 12 /
Jun 7 / Aug 2 2026 gaps took **-$639 across three trades** against a ~-$50 typical loss. Worst
trade **-4.27R held vs -1.24R closed**. The toggle being off is why the Jun 7 and Aug 2 losses
happened despite the pre-close job existing since Apr 17, 2026.

⚠️ **Do NOT extend `ALWAYS_CLOSE_PAIRS` on gap size alone.** Gaps are large on every pair
(median 1.23–2.73 ATR) but they cut **both ways**. Weekend-held trades are the *best* trades on
7 of 8 pairs (XAG +5.48 avg R, UK100 +2.38, EUR_USD +1.75, XAU +1.66, BCO +1.29, vs non-weekend
trades at -0.69 to +0.88); USD_JPY is the only other pair where holding loses (-0.16R). The
deciding number is **average R of weekend-held trades**
(`data/weekend_held_trade_isolation.csv`), never the gap magnitude.

⚠️ **`OandaPriceService.close_trade()` catches its own exceptions** (including 404) and returns
`None` on failure, or a response containing `orderRejectTransaction` on rejection. Callers in
`trade_closer.py` and `_close_open_positions_for_pair` depend on that contract — do not add a
second `close_trade` or change it to raise.


## Methodology Warnings

**Gap-pricing bug.** Every script in `scripts/` except `backtest_weekend_gap_impact.py` and
`backtest_xag_15m_filter_sweep.py` books a stopped-out trade at exactly -1R, because it tests bar
high/low against the SL price. A weekend gap opens *past* the stop, so real fills are worse
(observed: NAS100 -2.55R, BCO -2.16R, EUR_USD -1.94R, XAU -1.45R). Every Sharpe in this file not
marked † is therefore mildly optimistic. Copy the `is_gap_bar` handling for any work on stops or
tail risk.

**Promotion bar.** This repo has repeatedly promoted configs on short windows that then failed
live — EUR_AUD (BT Sharpe 4.52 → -0.07 full dataset), NAS100 (14.36 on 15 trades → negative
live), UK100 (8.45 → -$460 live). Before deploying a swept config, require: **≥60 trades**,
**positive mean R in both halves** of a split-half out-of-sample check, and a **contiguous
plateau** of passing neighbours rather than an isolated peak. When a sweep tests hundreds of
cells, the top row is a hypothesis, not a result — confirm it with a per-parameter marginal
analysis that holds up independently of the ranking.

---

## ⚠️ Do NOT Apply

- `sma_ordered` to NAS100 or XAG — destroys Sharpe (NAS100 2.67→-1.04). SMAs lag on fast moves.
- `di_slope`, `di_persist=2`, `di_threshold`>30, or `adx_min`>15 to **USD_JPY** — all harmful;
  DI spread is too tight on JPY.
- `di_persist=2` to XAG **on 5m** — kills the edge (+86%→+10%). This is 5m-specific: XAG on 15m
  and NAS100 on 15m both run persist=2 in production, where 2 candles is 30 min rather than 10.
- `rsi_filter` on any 5m pair — adds noise.
- `adx_min ≥ 20` or `atr_ratio = 1.5` to BCO — the first destroys the edge (Sharpe -0.83 at 25),
  the second collapses WR to 4.5%. `avoid[0-5]` also harmful (blocks the London open where BCO
  trends). `di_spread=10` is inert — DI>30 already implies it.
- **Ratcheting SL** (1R→0.5R, 2R→1R) and **SMA20-triggered trailing SL** — tested across all 8
  pairs, all worse (XAG 5.55→-0.11). Cutting early into a fixed-RR structure destroys the
  fat-tail wins that justify a low win rate. Do not re-test. JP225's breakeven stage is distinct:
  it moves to a small *loss* very early rather than locking *profit*, and only helps where there
  is no fat tail to protect.

---

## Not Running

**Suspended for live underperformance:** AUD_USD (live WR 20% vs BT 34.8%), USD_CAD (0% live WR),
GBP_JPY (live WR 12.5% vs BT 27.8%), EUR_AUD (full-dataset Sharpe -0.07 vs BT 4.52 — overfitted
to a short Dec 2025–Feb 2026 window).
**Never deployed:** AU200_AUD (BT Sharpe 2.10).
**Archived strategies:** all non-SmaScalping configs, preserved in `best_strategies_archived.json`.

`best_strategies.json` and `forex_pairs.json` must stay in sync — a pair present in
`forex_pairs.json` without a `best_strategies.json` entry silently runs a `TrendFollowing`
fallback that the Settings page cannot toggle.
---


## Trade History & Analytics

**Status:** ✅ Production Ready — See [docs/features/TRADE_HISTORY.md](./docs/features/TRADE_HISTORY.md)
- Filtering, sorting, CSV export; equity curve, monthly returns, strategy comparison charts
- Auto-sync with Oanda every 5 minutes; default date range: Feb 19, 2026+

---

## Documentation Organization

- When adding strategies: run backtest sweep → save CSV to `data/` → update `best_strategies.json` + `forex_pairs.json` → update CLAUDE.md active table

**Adding or changing a strategy:** run the sweep → save CSV to `data/` → update
`best_strategies.json` (+ `forex_pairs.json` if new) → update the Active Configuration table
above. Clear the superseded rows rather than appending; this file describes the current system,
not its history. Git carries the history.

**Sweep scripts** (`scripts/`):

| Script | Purpose |
|--------|---------|
| `backtest_xag_15m_filter_sweep.py` | Full filter grid, gap-priced + OOS-gated. **Use this as the template for new sweeps.** |
| `backtest_weekend_gap_impact.py` | Weekend gap cost per pair; prices gapped stops at the true open |
| `backtest_bco_rr_sweep.py` | BCO R:R sweep with split-half OOS check |
| `backtest_stop_stage_sweep.py` | Profit-lock / breakeven stages, gap-priced + OOS-gated — re-run before adding a stage to any pair |
| `backtest_bco_noise_filter_sweep.py` | BCO filter sweep |
| `backtest_nas100_investigation.py` | NAS100 filter sweep — re-run as more data arrives (its 2.2 MB output was not retained) |
| `backtest_prod_vs_live_comparison.py` | Live vs backtest comparison, all pairs |

Their outputs live alongside in `data/backtest_*.csv` plus
`data/weekend_held_trade_isolation.csv`.

---

## Recent Changes

**Aug 25, 2026 — NAS100_USD profit lock 1.5R→+0.5R, cooldown 90 min.** Adopted to cut drawdown
on a pair that is not earning live: MaxDD -10.47%→-5.44%, ROI +27.8%→+32.8%, WR 35.4%→52.3%,
9/11 months positive. Swept XAG and XAU at the same time — both rejected, see Stop-Move Stages.
Also replaced `backtest_breakeven_sweep.py`, which was dead code (it imported
`backtest_lock_sweep_v2`, deleted Aug 2026, so it crashed on run), with the self-contained
`backtest_stop_stage_sweep.py`.

**Aug 24, 2026 — XAG_USD migrated 5m/RR12 → 15m/RR3.0.** The 12R target was never reached
(1.5% of live wins); on 10 months of 15m data it scored Sharpe 0.09 / ROI +1.0% with an 8.3% win
rate. New config: `di_persist` 1→2, `avoid_hours` [14,15,16] dropped, RR 12→3.0; DI>35,
`atr_ratio=1.2`, `di_slope` unchanged. Result: Sharpe 4.60, ROI +64.5%, MaxDD -6.28% (halved),
10/11 months positive, OOS halves +0.41R / +0.77R. `di_persist=2` is the lever — reverting it
alone drops Sharpe to 1.62. Chosen from a 5,792-cell sweep but confirmed independently by
per-parameter marginals and a contiguous plateau (RR 2.5–3.5 all score 4.3–4.9). XAG holds over
weekends (flatting costs 4.60→3.07) and its 3R profit lock was removed as unreachable.
Sweep: `scripts/backtest_xag_15m_filter_sweep.py`.

**Aug 24, 2026 — BCO_USD RR 5.0→2.5, and forced into `ALWAYS_CLOSE_PAIRS`.** The 5R target was
reached on 7.3% of live wins; RR 2.5 scores Sharpe 1.37 vs 1.26 with 35% more trades and 8/11
months positive. Separately, BCO now closes before the weekly close even when
`holiday_close_enabled` is off — see Weekly Pre-Close. That toggle being off is why the Jun 7 and
Aug 2 2026 gap losses happened despite the pre-close job existing since April.

**Aug 21, 2026 — JP225_USD breakeven stage** (0.25R→-0.1R). See Stop-Move Stages.

Older changes (NAS100 retune Jun 2026, XAG/BCO locks Apr 2026, USD_JPY 15m migration Apr 2026,
the Mar 2026 move to SmaScalping 15m) are in git history.


---

## Strategy Toggle Settings (March 2, 2026)

Frontend Settings page (`/settings` nav tab) lets the admin user (`naveenf.opt@gmail.com`) enable/disable individual pair+strategy combos at runtime. Changes persist to Firestore and are picked up by the next cron run without restarting the server.

**How it works:**
- Firestore doc: `config/strategy_overrides` → `{ disabled: ["PAIR::Strategy", ...], updated_by, updated_at }`
- `disabled` list approach — new strategies default ON (no config update needed when adding a pair)
- Backend reads overrides at the start of every `run_forex_refresh_task()` and skips disabled combos
- `is_admin` flag is derived server-side and returned in the GET response — frontend never makes privilege decisions locally

**API:**
- `GET /api/settings/strategy-overrides` — any logged-in user (read-only for non-admin)
- `PUT /api/settings/strategy-overrides` — admin only (403 for others); validates keys against `best_strategies.json` before writing

**Files:**
- `backend/app/api/settings.py` — GET/PUT endpoints
- `backend/app/services/tasks.py` — Firestore read at cron start
- `backend/app/services/forex_screener.py` — `disabled_combos` param in `screen_all()` and `run_orchestrated_refresh()`
- `frontend/src/components/Settings.jsx` + `Settings.module.css` — toggle UI

**Known limitations / gotchas:**
- `best_strategies.json` and `forex_pairs.json` must stay in sync — pairs in `forex_pairs.json` without a `best_strategies.json` entry run a silent `TrendFollowing` fallback that cannot be toggled via Settings
- `db.collection(...).set(...)` is a full-replace (no `merge=True`) — intentional; do NOT add side fields to the `config/strategy_overrides` doc that you want preserved across saves
- Expired Google token produces a toast error with no auto-recovery; user must log out and back in
- `_build_combos` reads `best_strategies.json` from disk on every API call (fast enough at this scale)
