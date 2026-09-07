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
│   ├── forex_raw/              # Forex CSVs (5m, 15m only — see Data Retention)
│   └── metadata/
│       ├── best_strategies.json  # Strategy config map (source of truth)
│       ├── forex_pairs.json
│       └── stock_list.json
├── scripts/                    # Backtest sweeps — see Documentation Organization
│   └── download_forex.py       # Data fetcher (M15 + M5 only)
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
| XAG_USD | 15m | 3.0 | 1.0% | 35 | 2 | `adx_min=25`, **`sma_ordered`**, `body_ratio_min=0.3`, `di_slope`, `avoid[7,8,9]` | 1.46 ‡‡ | -18.6 ‡‡ |
| JP225_USD | 5m | 1.5 | 1.0% | 30 | 2 | `adx_min=20`, `adx_rising`, `di_slope`, `atr_ratio=1.2`, `di_spread=15`, `avoid[21-23]` | 5.87 | -5.85 |
| NAS100_USD | 15m | 3.5 | 1.0% | 35 | 2 | `adx_min=30`, `atr_ratio=1.2`, `di_slope`, `avoid[7,8,20-23]` | 14.36 ‡ | -1.99 |
| UK100_GBP | 15m | 3.5 | 1.0% | 35 | 2 | `atr_ratio=1.2`, `avoid[15-19]` | 8.45 ‡ | -3.94 |
| BCO_USD | 15m | 2.5 | 1.0% | **35** | 1 | `adx_min=15`, **`atr_ratio=1.2`**, **`di_spread=20`**, `avoid[20-23]` | 1.61 ‡‡ | -15.4 ‡‡ |
| EUR_USD | 15m | 6.0 | 1.0% | 25 | 2 | `atr_ratio=1.0`, `avoid[20-23]` | 5.56 ‡ | -10.47 |
| USD_JPY | 15m | 3.0 | 0.5% | 30 | 1 | `avoid[15-21]` | 2.85 ‡ | -8.65 |

‡‡ **The only rows measured over 3 years with walk-forward validation** — BCO (fit
2023-08→2025-12) and XAG (fit 2023-09→2025-12), both held out on 2026. Every OTHER row in this
table is a ~10-month single-window figure and does not survive contact with older data — see
*Two-window reality check* below. Do not compare ‡‡ rows to the others: their Sharpes look *worse*
because they are honest, and their MaxDD figures are realistic rather than best-case.

† Measured with gapped stops priced at the true post-weekend open. **Not comparable** to the
other rows, which use the legacy backtester that books every stop at exactly -1R (see the
gap-pricing warning below). Lower ≠ worse.
‡ Live performance has diverged from these figures — see *Live divergence* below.

**Disabled at runtime** via the Settings page (Firestore `config/strategy_overrides`, not the
JSON): **EUR_USD**, **USD_JPY** and — from Sep 7, 2026 — **UK100_GBP**. EUR_USD and USD_JPY for
sustained negative live returns; UK100 on the 3-year re-measure: Sharpe 0.19, MaxDD -36.3%,
CAGR/DD 0.05, and -0.42 Sharpe if the pre-close flatten applies to it. It is also the worst live
P&L on record (-$460) and the slowest pair at 3.7 trades/month. Their configs are retained above
so re-enabling needs no re-derivation.

⚠️ UK100's true economics depend on `config/trade_settings → holiday_close_enabled`: held over
weekends it scores ROI +6.1%, flattened before the weekly close it scores **-14.5%**. That toggle
is not readable from the repo — check it on the Settings page before re-enabling.

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

### Two-window reality check (Sep 2026, after the data backfill)

Every config in the table above was swept on the ~10 months that were the only data on disk. With
3 years of 15m now available, the same configs re-measured on their tuned window vs everything:

| Pair | Doc Sharpe | Reproduces on tuned window? | 3-yr Sharpe | 3-yr MaxDD | 3-yr CAGR/DD |
|------|-----------:|-----------------------------|------------:|-----------:|-------------:|
| XAU_USD | 6.48 | ✅ 6.57 | 1.92 | -40.9% | 0.90 |
| XAG_USD ⚠️sup | 4.60 | ✅ 4.38 | 1.45 | -17.6% | 0.79 |
| BCO_USD | 1.47 | ~ 1.29 | 0.08 → **1.61 retuned** | -45.1% → **-15.4%** | 0.04 → **1.73** |
| NAS100_USD | 14.36 | ❌ 2.58 | 1.41 | -19.7% | 0.70 |
| UK100_GBP | 8.45 | ❌ 3.90 | 0.19 | -36.3% | 0.05 |
| JP225_USD | 5.87 | ❌ 1.58 | 0.69 | -25.2% | 1.04 |
| USD_JPY | 2.85 | ❌ 0.81 | 0.21 | -16.1% | 0.19 |
| EUR_USD | 5.56 | ❌ -5.03 | -0.54 | -37.3% | 0.21 |

⚠️sup **XAG's row describes the config SUPERSEDED on Sep 7, 2026** — it is kept because it is
why the pair was retuned, not as a description of what runs now. See Recent Changes.

XAU and XAG reproduce (they were re-derived Aug 2026 on this data), which **validates the
pipeline** — so the drops are real out-of-sample degradation, not a measurement difference. The
five that do not reproduce are stale figures from older sweeps on different windows or timeframes.

⚠️ **Expect 15-25% drawdowns, not 5-10%.** The old figures are the minimum over a short,
favourably-selected window. These configs win 23-29% of trades at 2.5-3.5R, which guarantees long
losing runs — observed maximum streaks are **12-18 consecutive losses**. At 1% risk a 15-loss
streak is ~14% drawdown; at XAU's 1.5% it is ~20%. Bootstrapping each pair's GOOD window out to
full length already yields -11% to -24%, so most of the increase is path length, not deterioration.
This is a position-sizing fact, not a config problem.

⚠️ **7 of 8 pairs score far better on their tuned window than on unseen data** (XAU +0.975R vs
+0.050R; XAG +0.569 vs -0.044; UK100 +0.588 vs -0.040; BCO +0.158 vs -0.056). Part overfitting —
each config was the best cell of a large sweep on that window — and part regime, since 2026 was
strong nearly everywhere. **The next retune must be walk-forward** (fit older, validate on a
held-out recent year). The split-half check currently in the sweep scripts fits and tests inside
the same window and structurally cannot catch this. BCO's Sep 2026 retune is the worked example.

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
| BCO_USD | Lock 2R→+1R, cooldown 90 min | ⚠️ **Unevidenced on the current config.** Raised to +1.5R Sep 4, 2026 and reverted Sep 7 — see Config-consistency below. Only 15 trades exist since the Aug 24 RR migration |
| NAS100_USD | Lock 1.5R→+0.5R, cooldown 90 min | MaxDD -10.47%→-5.44%, ROI +27.8%→+32.8%, WR 35.4%→52.3%, months positive 7/11→9/11 |
| JP225_USD | Breakeven 0.25R→-0.1R, no cooldown | Live-verified on drawdown (-17.0%→-7.6%, replicates in both windows). The old backtest figure Sharpe 2.53→5.63 is NOT reproducible — do not cite it |

### Live verification (Sep 4, 2026)

Every production stage re-tested by replaying each pair's REAL closed trades against raw price
bars — not against a cached sweep CSV. Method: broker SL/TP tested intrabar (those orders rest at
Oanda), stage triggers fired only on a ~5-minute poll sample (see the poll-limited warning under
Methodology Warnings), gaps filled at the bar open, trades sorted chronologically before any
equity path. Two windows: **faithful** (5m bars as poll samples, bounded by the 20,000-bar cap on
5m files, ~mid-May 2026 onward) and a **wider** cross-check (15m closes as the poll proxy, which
under-fires stages and so is conservative about them, reaching back to Jan/Feb 2026).

⚠️ **Config-consistency — read before trusting any row below.** These replays used whatever
trades fell in the window, and two pairs changed R:R on Aug 24, 2026 *inside* it. Checking the
implied R:R of every trade actually replayed:

| Pair | R:R mix in window | Verdict validity |
|------|-------------------|------------------|
| XAU_USD | 43/58 at RR 3.5, stable | ✅ valid |
| JP225_USD | 77/107 at RR 1.5, rest 1.4-1.6 | ✅ valid |
| NAS100_USD | 11 at 3.5, 7 at 2.5 — mixed | ⚠️ underpowered AND config-mixed |
| XAG_USD | **~99% at RR 12** (retired config), 1 at 3.0 | ❌ **invalid for RR 3.0** |
| BCO_USD | **127/142 at RR 5.0** (retired), 15 at 2.5 | ❌ **invalid for RR 2.5** |

XAG stays naked and BCO keeps its documented lock, so no harm followed — but neither pair's row
below describes what it runs today. **Always check the implied R:R distribution of the trades a
replay consumed** (`|take_profit - buy_price| / |buy_price - orig_sl|`) before believing it; a
config change inside the window silently mixes two different strategies.

**Faithful window — production stage vs no stage:**

| Pair | n | Fired | ROI% base→stage | MaxDD% base→stage | Sharpe base→stage | Verdict |
|------|--:|------:|-----------------|-------------------|-------------------|---------|
| BCO_USD (lock 2.0→1.0) † | 142 | 30 | 6.14 → **-3.46** | -17.42 → -16.03 | 0.50 → **-0.15** | ❌ Harmful — buys 1.4pp of DD with the entire edge |
| JP225_USD (BE 0.25→-0.1) | 107 | 48 | 1.45 → **10.49** | -17.01 → **-7.63** | 0.27 → **1.65** | ✅ Keep — on the drawdown result |
| NAS100_USD (lock 1.5→0.5) | 24 | 7 | 12.66 → 5.95 | -4.90 → -4.43 | 4.06 → 2.57 | ⚠️ Underpowered — cannot conclude |
| XAU_USD (none) | 59 | — | 90.28 | -10.04 | 5.46 | ✅ Naked is correct |
| XAG_USD (none) | 98 | — | 44.00 | -18.21 | 1.74 | ✅ Naked is correct |

† BCO run WITH production weekend flattening — see the BCO baseline trap below.

**Wider window cross-check (n roughly 2-3x):** BCO 56.01→41.89 ROI · JP225 79.79→**62.90**
(ROI *falls*) with DD -17.01→-10.15 · NAS100 22.44→21.49 with DD -15.68→**-9.76** ·
XAU 152.57→81.90 · XAG 394.27→105.91.

The windows **agree** on BCO (harmful) and on XAU/XAG (a stage is never free). They **disagree on
JP225's ROI** (+9.0pp faithful, -16.9pp wider); its drawdown gain replicates in both.

**Best alternative per pair (faithful window):**

| Pair | Baseline ROI / DD / Sharpe | Best by drawdown | Best by ROI |
|------|---------------------------|------------------|-------------|
| BCO_USD † | 6.14 / -17.42 / 0.50 | **lock 2.0→1.5 — 6.94 / -10.91 / 0.62, OOS PASS** | BE 1.0→-0.2 — 10.68 / -12.92, OOS fail |
| JP225_USD | 1.45 / -17.01 / 0.27 | BE 0.25→0.0 — 10.90 / -6.88, OOS fail | BE 0.25→-0.2 — 12.75, OOS fail |
| NAS100_USD | 12.66 / -4.90 / 4.06 | lock 2.0→1.5 — **4 fires** | lock 2.5→1.5 — **1 fire** |
| XAU_USD | 90.28 / -10.04 / 5.46 | BE 0.25→0.0 — 60.53 / -4.43, PASS | BE 1.0→-0.2 — 81.35 / -7.28 |
| XAG_USD | 44.00 / -18.21 / 1.74 | lock 2.0→1.5 — 9.19 / -10.03 | lock 2.0→1.0 — 29.02, OOS fail |

**XAU and XAG: every one of 17 candidate stages reduces ROI, in BOTH windows, without exception.**
Drawdown can be bought, expensively — XAG's best-DD cell costs 79% of the return (44.0%→9.2%) to
halve drawdown. Running these two naked is well supported. Do not revisit on drawdown grounds
alone.

**BCO: the deployed lock is the wrong cell, not the wrong idea.** `lock 2.0→1.5` beats both the
deployed `2.0→1.0` AND the no-stage baseline on ROI, drawdown and Sharpe, in both windows, and is
the only BCO cell that passes the split-half check. The whole difference is 0.5R of give-back on
~30 trades. NOT YET ADOPTED — needs explicit approval.

⚠️ **No stage's effect on expectancy is statistically significant.** Paired per-trade ΔR
(stage minus baseline), faithful window — every 95% CI straddles zero:

| Pair | Stage | n | Changed | Mean ΔR | t | 95% CI |
|------|-------|--:|--------:|--------:|---:|--------|
| BCO_USD | lock 2.0→1.0 | 142 | 36 | -0.188 | -1.47 | [-0.437, +0.062] |
| JP225_USD | BE 0.25→-0.1 | 107 | 48 | +0.077 | +1.03 | [-0.069, +0.223] |
| NAS100_USD | lock 1.5→0.5 | 24 | 7 | -0.265 | -1.05 | [-0.760, +0.230] |
| XAU_USD | lock 2.0→1.0 | 59 | 13 | -0.257 | -1.77 | [-0.541, +0.027] |
| XAG_USD | lock 2.0→1.0 | 98 | 25 | -0.145 | -0.55 | [-0.664, +0.374] |

The large ROI swings above are compounding artifacts of per-trade differences a t-test cannot
separate from noise. **Drawdown verdicts are the robust ones** — they replicate across both
windows and both trigger models, and drawdown is a tail statistic a handful of trades legitimately
controls. Treat ROI and Sharpe verdicts on 24-142 trades as directional at best.

Against this file's own promotion bar: BCO's *baseline* fails split-half in the faithful window
(h1 -0.12, h2 +0.23), JP225's production BE fails it (h1 +0.24, h2 -0.05), NAS100 fails the
trade-count bar outright. Only XAU and XAG clear all three — and there the answer is add nothing.

⚠️ **CLAUDE.md's old JP225 figure "Sharpe 2.53→5.63" is NOT reproducible from live data.**
Do not cite it. The defensible claim for JP225 is the drawdown result, which replicates.

⚠️ **NAS100's justification is artifact-shaped.** "149/151 configs cut drawdown" is precisely the
result the intrabar-trigger artifact manufactures, and on this exact pair and stage that artifact
is worth +7.9pp ROI and +0.68 Sharpe (see the poll-limited warning). The lock is not validated.
Do not add a second mechanism here.

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


## Data Retention

`download_forex.py` appends incrementally (reads the file, fetches from its newest bar, dedupes
on `Date`), then **trims to a rolling row cap and writes that back — trimmed bars are deleted
from disk.** Caps are per timeframe in `MAX_ROWS`:

| File | Bars/month (measured) | Cap | History |
|------|----------------------:|----:|---------|
| `_5_Min` | ~5,675 | 70,000 | **~1 year** |
| `_15_Min` | ~1,895 | 70,000 | **~3 years** |

Densities are measured from live Oanda history, not the theoretical 5-day week — holidays and
weekend gaps make the real rate lower, so calendar-based row estimates overstate depth by ~10%.

Caps were sized against **simulated trade counts for each pair's current config on raw bars**
(not against the live trade cache, which mixes retired configurations). Signal rates differ ~9x
across pairs, so the slow pairs bind:

| Pair | TF | Trades/month | Months to 200 trades |
|------|----|-------------:|---------------------:|
| JP225_USD | 5m | 31.7 | 6.3 |
| BCO_USD | 15m | 24.1 | 8.3 |
| USD_JPY | 15m | 19.7 | 10.1 |
| EUR_USD | 15m | 12.4 | 16.1 |
| XAG_USD | 15m | 8.6 | 23.3 |
| XAU_USD | 15m | 5.7 | **34.9** |
| NAS100_USD | 15m | 4.6 | **43.1** |
| UK100_GBP | 15m | 3.7 | **53.9** |

⚠️ **A stop-stage question needs far more than 200 trades.** To detect a 0.20R per-trade effect at
80% power: JP225 needs ~9.5 months and BCO ~23 — both reachable. XAU needs ~176 months, NAS100
~200, UK100 ~257. **Those pairs are not answerable statistically at any practical data volume**
and must be decided on mechanism instead (e.g. "a lock below the take-profit truncates the tail
the edge depends on" — visible in a handful of trades, no p-value required). More history helps
JP225 and BCO; for the rest it buys precision that will never arrive.

⚠️ **Until Sep 4, 2026 this was a single global 20,000**, which bit hardest on exactly the two
timeframes the system trades — leaving only ~3.2 months of 5m and ~9.6 months of 15m. That
silently bounded every sweep in this repo and is a structural reason configs kept getting promoted
on short windows: on a sparse pair the file rolled forward faster than trades accrued, so the
≥60-trade promotion bar was unreachable no matter how long you waited. If a historical analysis
here looks oddly short-windowed, this is why.

`download_forex.py` only ever fetches FORWARD from its newest bar, so it can never recover trimmed
history. After raising a cap, run `scripts/download_forex_max_history.py` once to page backwards
and refill; the 5-minute cron maintains it from there.

**Only M15 and M5 are downloaded.** H1, H4 and Silver's M3 were dropped Sep 4, 2026 — every active
pair runs SmaScalping, which reads `data['base']` only, and both MTF loaders already guard on
`base` being None. ⚠️ **Re-enable them in `download_forex.py` BEFORE re-activating any archived
strategy that needs them** — PVTScalping is 1h-based; EnhancedSniper, NewBreakout and DailyORB use
H1/H4 filters. Without the files they receive None and are skipped silently rather than erroring.

## Methodology Warnings

**Gap-pricing bug.** Every script in `scripts/` except `backtest_weekend_gap_impact.py` and
`backtest_xag_15m_filter_sweep.py` books a stopped-out trade at exactly -1R, because it tests bar
high/low against the SL price. A weekend gap opens *past* the stop, so real fills are worse
(observed: NAS100 -2.55R, BCO -2.16R, EUR_USD -1.94R, XAU -1.45R). Every Sharpe in this file not
marked † is therefore mildly optimistic. Copy the `is_gap_bar` handling for any work on stops or
tail risk.

**Stop-stage triggers are poll-limited, NOT candle-based.** `run_pair_lock_checks()` never
reads a candle close. It calls `OandaPriceService.get_current_price()` — a single **S5
(5-second) midpoint** candle — and it runs inside `run_forex_refresh_task`, which cron fires at
minutes `1,6,11,…,56`. So the live system observes price **once every ~5 minutes**, on every
pair, regardless of that pair's signal timeframe. A stage can only fire on a price still present
at a 5-minute sample.

Any backtest or replay that fires a stage on an intrabar **high/low** is therefore wrong, and
wrong in a direction that manufactures a benefit. Measured on NAS100 (102 trades, same bars, same
stage, ONLY the trigger price differs):

| Trigger model | Fires | ROI% | MaxDD% | Sharpe |
|---|--:|---|---|---|
| no stage at all | 0 | 22.44 | -15.68 | 1.67 |
| lock 1.5→0.5, fires at a 5-min poll | 18 | 21.49 | -9.76 | 1.73 |
| lock 1.5→0.5, fires on intrabar high/low | **25** | **30.32** | **-8.40** | **2.35** |

Intrabar fires 32-39% more often across pairs and here fabricates improvement on **all three axes
at once**. Which metric it inflates varies (on JP225 it flatters drawdown instead of ROI), but it
always inflates the stage relative to the baseline.

The intrabar model fires on brief spikes to the threshold — and brief spikes are exactly the
population that then reverses to -1R, so "catching" them invents the entire drawdown gain. A real
poll sees only a *sustained* move, which selects for genuine winners, truncates them, and leaves
the whipsaw losers at a full -1R. **XAU was nearly deployed on that artifact (Sep 3-4, 2026).**
Broker SL/TP are different — those orders rest at Oanda and DO fill intrabar. Only *our* stop
move is poll-limited. `scripts/replay_stop_stages.py` models this correctly; copy its handling.

**⚠️ Data trap: `signal_stop_loss` is NOT the stop that was placed.**
`oanda_trade_service.py:398-410` re-anchors SL and TP off the **live fill** before placing the
order, and `_log_to_portfolio` writes those re-anchored levels to `stop_loss`/`take_profit` with
`buy_price` = the actual fill. `signal_stop_loss`/`signal_take_profit` are anchored to the signal
CANDLE CLOSE — a different price. **Pairing `signal_stop_loss` with `buy_price` fabricates the
risk distance and silently corrupts every R, ROI, drawdown and Sharpe downstream.** An entire
analysis was invalidated by this on Sep 4, 2026.

The offset is constant per trade: `stop_loss - signal_stop_loss == take_profit -
signal_take_profit` holds to 7e-12 across all 662 unmoved trades. So for a trade whose stop was
later moved, recover the ORIGINALLY PLACED stop as
`signal_stop_loss + (take_profit - signal_take_profit)` — the stop-move job never touches TP.
(183 rows carry no `signal_*` at all; all pre-2026-03-20.)

**⚠️ Data trap: BCO's baseline is not "no stage".** BCO is in `ALWAYS_CLOSE_PAIRS`, so it is
force-flattened before every weekly close. An unconstrained replay holds 25 of 142 BCO trades
across a Friday 21:00 close (median hold 95 hours) and those 25 contribute **+30.4R against a
+9.6R total** — the entire baseline and more comes from trades production would never have kept.
Any BCO comparison must model Friday flattening or it is measuring an impossible counterfactual.
The verdict flips without it.

**Promotion bar.** This repo has repeatedly promoted configs on short windows that then failed
live — EUR_AUD (BT Sharpe 4.52 → -0.07 full dataset), NAS100 (14.36 on 15 trades → negative
live), UK100 (8.45 → -$460 live). Before deploying a swept config, require: **≥60 trades**,
**positive mean R in both halves** of a split-half out-of-sample check, and a **contiguous
plateau** of passing neighbours rather than an isolated peak. When a sweep tests hundreds of
cells, the top row is a hypothesis, not a result — confirm it with a per-parameter marginal
analysis that holds up independently of the ranking.

---

## ⚠️ Do NOT Apply

- `sma_ordered` to NAS100 — destroys Sharpe (2.67→-1.04). SMAs lag on fast moves.
  ⚠️ **Corrected Sep 7, 2026 — this entry previously named XAG too, and that was wrong.** The
  evidence was NAS100's, generalised to a pair where it had never been tested. On XAG
  `sma_ordered` wins **84.2% of 103,680 paired cells** — the single strongest lever on the pair,
  now in production. It was also adopted on nothing else: re-test per pair before assuming.
- `di_slope`, `di_persist=2`, `di_threshold`>30, or `adx_min`>15 to **USD_JPY** — all harmful;
  DI spread is too tight on JPY.
- `di_persist=2` to XAG **on 5m** — kills the edge (+86%→+10%). This is 5m-specific: XAG on 15m
  and NAS100 on 15m both run persist=2 in production, where 2 candles is 30 min rather than 10.
- `rsi_filter` on any 5m pair — adds noise.
- `atr_ratio ≥ 1.3` to BCO — 1.3 destroys 2026 entirely (OOS expR +0.002, then -0.151 at 1.4) and
  1.5 collapses WR to 4.5%. **`atr_ratio = 1.2` is the opposite — one of the three best levers on
  the pair** (cut drawdown in 99% of 13,824 paired cells). The cliff is between 1.2 and 1.3.
  `avoid[0-5]` also harmful (blocks the London open where BCO trends).
- ⚠️ **Corrected Sep 2026 — two long-standing entries here were wrong:**
  - *"`di_spread=10` is inert — DI>30 already implies it"* — the premise is false. DI+ > 30 places
    no bound on DI-, so the spread is an independent constraint. `di_spread=10` really is near-inert
    (helps 37% of paired cells), but that generalised to "spread does not matter" and cost the
    **`di_spread=20`** setting, which helps 77% of 13,824 paired cells and is now in production.
  - *"`adx_min ≥ 20` destroys the edge"* — true only against the OLD di=30 config. Inside
    di=35/atr=1.2 it is mildly positive (61% of 864 cells). Still the weakest lever; not adopted.
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

⚠️ **Every write to a `forex_portfolio` doc MUST set `updated_at`** — creates included.
`trade_cache.get_forex_trades_cached()` delta-syncs with `where('updated_at', '>', cursor)`,
and a Firestore inequality filter **skips docs where the field is absent**, permanently — not
until the next cycle. Two writers in `oanda_trade_service.py` omitted it (trade creation and the
"not found in Oanda open trades" auto-close), so 17 trades worth -$594 never appeared in Trade
History or Analytics at all, and one was still stuck OPEN 11 days after closing. Fixed Aug 31,
2026, with the stranded docs repaired from Oanda; the invariant is tested in
`backend/tests/test_trade_doc_updated_at.py`.

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
| `backtest_stop_stage_sweep.py` | Profit-lock / breakeven stages, gap-priced + OOS-gated. ⚠️ Simulates its own entries; prefer `replay_stop_stages.py` for any pair with live history |
| `replay_stop_stages.py` | **Stop-stage verification against REAL live trades.** Poll-limited triggers, reconstructed original stops, BCO weekend flattening. The authoritative tool for stage decisions |
| `backtest_xau_15m_filter_sweep.py` | XAU entry-filter grid (9,528 cells). Result: nothing beats the current config |
| `backtest_bco_noise_filter_sweep.py` | BCO filter sweep |
| `backtest_prod_vs_live_comparison.py` | Live vs backtest comparison, all pairs |
| `download_forex_max_history.py` | **One-off** Oanda backfill — pages backwards to fill history the old row cap trimmed away. Run once after changing `MAX_ROWS`; the cron maintains it after |

Their outputs live alongside in `data/backtest_*.csv` plus
`data/weekend_held_trade_isolation.csv`.

---

## Recent Changes

**Sep 7, 2026 — XAG_USD retuned on 3 years, walk-forward validated: added `sma_ordered`,
`adx_min=25`, `body_ratio_min=0.3`, `avoid_hours=[7,8,9]`; removed `atr_ratio_min=1.2`.**
The second config here validated walk-forward, after BCO. The OLD config had **no edge outside a
single half-year**: -0.029R across the 27-month fit window (2023-09→2025-12, 205 trades), with
2026-H1 alone contributing 36.6R of a 34.7R lifetime total (105%) and the other six sections
summing to -1.9R. Fit blind to 2026, then held out: **in-sample +0.333R, held-out +0.357R** — it
does not depend on the 2026 regime. Full 3 years: expectancy +0.126R→**+0.340R**, ROI
35.3%→**92.3%**, Sharpe 0.68→**1.46**, MaxDD -21.6%→**-18.6%**, PF 1.17→1.51, worst streak 12→10,
203 trades. Positive in **all four calendar years** (old config lost money in 2023 and 2025);
5/7 six-month sections positive and best-section concentration 105%→38%. From a 207,360-cell grid
but not a lucky cell: **32.6% of the grid clears the fit-window bar the old config fails**, all 25
one-step neighbours are positive in BOTH windows, and split-half on the fit window is +0.444/+0.222.
`target_rr` deliberately NOT raised — RR 3.5-4.0 score better on both windows, but raising targets
is the direction the live record says fails.
⚠️ **Gated on execution, not config.** At the ~1.5 realised payoff seen live on every pair
(winners closed manually before TP), this config computes to **-0.163R** and only turns positive if
wins are held past ~2.0R. The old config was worse (-0.298R). No entry filter fixes this — it is
the same defect that retired XAG's 12R and BCO's 5R targets.
Confirmed unchanged by the same sweep: **XAG stays naked** (65/82 stage cells cut drawdown but
35/82 have significantly NEGATIVE ΔR; best-ROI cells are compounding artifacts), **keeps holding
over weekends** (flattening costs 92.3%→69.8% ROI), and **the 5m→15m migration holds** (5m gives
2.4x the trades for under half the expectancy and cannot be walk-forward validated — its history
is almost entirely the favourable 2026 regime).
Sweep: `scripts/backtest_xag_walkforward_retune.py` → `data/backtest_xag_wf_*.csv`.

**Sep 7, 2026 — XAU_USD retune evaluated and REJECTED; config unchanged.** A 414,720-cell
walk-forward sweep produced a candidate (di 35→40, `di_slope`, `sma_ordered`, `avoid[8,9,20-23]`)
that beat the incumbent on the fit window (+0.543R vs +0.094R), cut bootstrap-median drawdown
~-28%→~-17%, and was positive in all four years. **It was not deployed**: on the held-out 2026 year
it was **significantly WORSE** (ΔexpR -0.975, 95% CI [-1.893, -0.056], t=-2.08 — the only
significant comparison in the study, and it ran against the candidate), earning +0.108R vs the
incumbent's +1.083R. Deploying a config that just underperformed on the only unseen data available,
replacing one that is currently the best live pair (+$3,128), was judged the weaker bet. Revisit if
live signals degrade.
⚠️ **XAU's stored `sharpe: 6.48` is a ~10-month tuned-window figure and is not reproducible.**
Freshly measured over 3 years: **daily-annualised Sharpe 1.14, MaxDD -40.9%** (bootstrap median
-28%; the observed -40.9% is a p5 unlucky ordering — quote the bootstrap). Its edge is heavily
2026-concentrated: 40 of 329 trades supply **63% of lifetime R**. `risk_pct` remains 1.5%, the only
pair above 1.0%; cutting to 1.0% takes
bootstrap-median DD ~-28%→~-20% for a third of the CAGR, and **the incumbent cannot reach -12% DD
by cutting risk at any level**. All 32 candidate stop-stages have ΔR CIs straddling zero: XAU stays
naked.
Sweep artifacts were NOT retained — XAU's config did not change, so only this summary is kept.
Reproduce with the conventions in `scripts/backtest_xag_walkforward_retune.py`.

**Sep 7, 2026 — full-history replay of all 5 active pairs on the backfilled 3-year data.**
Replayed with an engine validated bar-by-bar against the real `SmaScalpingDetector.analyze()`
(0 signal / 0 stop-loss mismatches per pair), gap-priced, with poll-limited stage triggers. ⚠️ **Several long-standing figures in this file did not reproduce.**
Measured 3-year daily-annualised Sharpe / MaxDD: BCO **1.63 / -13.1%** (reproduces the Sep 7
retune), XAU **1.14 / -40.9%**, NAS100 **0.84 / -20.0%**, XAG(old) **0.68 / -21.6%**. JP225 is
5m-only so its window is **1 year, not 3** (463 trades, 87% of its R from 2026-H1) — do not table it
beside the others. Trade rates also differ materially from the Data Retention table (measured
BCO 12.3/mo not 24.1, XAU 9.3 not 5.7, NAS100 7.2 not 4.6). **No stage's per-trade ΔR is
statistically significant on 209-423 paired trades**; BCO's deployed lock measures **neutral**
(ΔR -0.011, t=-0.63), not harmful as previously recorded, and NAS100's lock made drawdown *worse*
in the primary run and sign-flips with the flatten toggle. Only these findings were retained — no
config changed for those pairs, so the replay artifacts were not kept. The equivalent engine lives
in `scripts/backtest_xag_walkforward_retune.py` (see its reference-replay section).

**Sep 7, 2026 — BCO_USD retuned on 3.1 years: `di_threshold` 30→35, `atr_ratio_min` 1.0→1.2,
`di_spread_min` 0→20.** The first config in this repo validated walk-forward. Measured with
production's Friday flattening and gap-priced stops over 2023-08→2026-09:
**ROI +6.2%→+105.2%, Sharpe 0.08→1.61, MaxDD -45.1%→-15.4%**, expectancy +0.017R→+0.174R on 444
trades — and **positive in all four calendar years** (+0.211/+0.156/+0.174/+0.172) where the old
config lost money in 2023 and 2024. Selected blind to 2026: in-sample +0.174R, held-out 2026
+0.172R. The old config *failed its own walk-forward* (in-sample Sharpe **-0.56**; all its profit
was 2026). From a 41,472-cell sweep, but not a lucky cell — **37.8% of the grid beats the old
config on ROI, Sharpe and drawdown simultaneously**, and the three adopted levers each hold across
thousands of paired cells (di 35: 72%, atr 1.2: 88%, spread 20: 77%), computed blind to 2026.
t-stat +2.39 vs the old config's +0.36. Trade count drops 1038→444.

`target_rr` was deliberately NOT changed — the RR axis is nearly flat from 2.0-3.5 over 3 years,
so August's 5.0→2.5 retune addressed the wrong parameter; `di_threshold=30` admitting weak signals
was the real defect. `adx_min=20` (grid peak, Sharpe 1.90) was rejected as an interaction artifact:
harmful in isolation, jagged on its own axis. The 2.0R→+1.0R profit lock was re-tested and kept —
neutral (±0.1 Sharpe); every tighter stage is harmful.
Sweep: an agent run against `data/forex_raw/BCO_USD_15_Min.csv`; reproduce with
`scripts/replay_stop_stages.py` conventions.

**Sep 7, 2026 — BCO_USD lock reverted +1.5R → +1.0R.** The Sep 4 change was withdrawn: 127 of
the 142 trades supporting it predated the Aug 24 RR 5.0→2.5 migration, so ~89% of the evidence
described a retired configuration. At RR 2.5 a 2.0R trigger sits 80% of the way to TP and fires on
only 1-2 of the 15 post-migration trades — the same defect that retired XAG's 3R lock. The
apparent ROI gain was also a compounding artifact; total ΔR was negative even on the old data.
**No BCO lock setting is currently evidenced**; settling it needs ~23 months of post-migration
trades, and deeper history cannot help because it only adds pre-migration ones. Retention caps
were also finalised at 70,000 rows per timeframe (~1 year of 5m, ~3 years of 15m).

**Sep 4, 2026 — data retention raised; H1/H4/M3 downloads dropped.** The row cap was a single
global 20,000, leaving only ~3.2 months of 5m and ~9.6 months of 15m and silently bounding every
backtest. Now per-timeframe: **5m and 15m both 70,000 rows (~1 year / ~3 years)**, sized from
measured bar density and simulated per-pair trade counts. H1, H4 and
Silver's M3 are no longer fetched — nothing active reads them. `download_forex_max_history.py` was
rewritten from a broken yfinance version (60-day cap, wrote to a filename nothing read) into an
Oanda backwards-paging backfill; run it once to refill, then the cron maintains it.
See Data Retention.

**Sep 4, 2026 — BCO_USD lock target raised +1.0R → +1.5R.** The only config change from the
stop-stage review below. Replayed against BCO's real trades with weekend flattening modelled and
triggers poll-limited: the deployed +1R capped ~30 winners hard enough to remove the pair's whole
edge (ROI 6.14→-3.46, Sharpe 0.50→-0.15) for 1.4pp of drawdown. +1.5R scores ROI 6.99, MaxDD
-10.91% (vs -17.42% naked), Sharpe 0.62, and is the only BCO cell passing split-half. Adopted as
a **drawdown** decision — the per-trade effect is not statistically significant. JP225, NAS100,
XAU and XAG were all left exactly as they were.

**Sep 4, 2026 — stop-stage trigger model corrected; all live stages re-verified; two data
traps documented.** A proposed XAU breakeven was built and then withdrawn before commit: its
drawdown gain existed only because the replay fired on intrabar highs, while production polls
price every ~5 minutes. An independent re-analysis then found two further errors that had
corrupted the first pass — `signal_stop_loss` is not the placed stop, and BCO's baseline must
model weekend flattening. Both are written up under Methodology Warnings; both silently corrupt
every downstream metric. Corrected verdicts: **BCO's deployed lock 2.0→1.0 is harmful**
(ROI 6.14→-3.46, Sharpe 0.50→-0.15) while the neighbouring **lock 2.0→1.5 beats both it and the
no-stage baseline on all three axes** and is the only BCO cell passing split-half — not yet
adopted. **JP225's breakeven is kept on its drawdown result**, which replicates across windows;
its ROI effect does not. **NAS100 is underpowered** (n=24) and its published justification is
artifact-shaped. **XAU and XAG stay naked** — all 17 candidate stages reduce ROI in both windows.
No config was changed. Crucially, **no stage's effect on expectancy is statistically significant**
— every 95% CI straddles zero, so drawdown is the only axis worth deciding on.
Also added `scripts/backtest_xau_15m_filter_sweep.py` (9,528 cells): **no entry filter beats the
current XAU config** — 0 cells improve drawdown and ROI together. XAG's 5,792-cell sweep was
re-checked too; its 5 apparent challengers all rest on `avoid=post_ny`, which fails a marginal
test (helps 36% of 680 paired cells, negative medians). Both entry configs stand unchanged.

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
