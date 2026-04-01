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
├── scripts/
│   ├── backtest_sma_15m_all_pairs.py      # 15m pair exploration sweep
│   ├── backtest_noise_filter_sweep.py     # Filter sweep for active pairs
│   ├── backtest_bco_strategy_compare.py   # BCO config derivation
│   ├── backtest_jp225_time_filter.py      # JP225 time filter validation
│   ├── backtest_sma_all_pairs_exit_mode.py # Exit mode validation (SMA20 disabled)
│   ├── backtest_sma_jpy_pairs.py          # USD_JPY config sweep
│   ├── backtest_rr_sweep.py               # R:R sweep across all active pairs
│   └── download_forex.py                  # Data fetcher
└── docs/analysis/              # Backtest reports
```

---

## Trading Strategies (Active)

| # | Strategy | Key Indicators | Pairs |
|---|----------|---------------|-------|
| 1 | **SMA Scalping** | SMA20/50/100 stack, DI+/DI-, ATR SL floor | XAU, XAG, JP225, NAS100, USD_JPY, BCO, UK100, EUR_USD |

All 8 active pairs run SmaScalping only. Heiken Ashi, Daily ORB, Silver Sniper, PVTScalping, and NewBreakout are archived — see archived table below.

---

**Suspended (live underperformance):** AUD_USD (live WR 20% vs 34.8% BT), USD_CAD (0% WR, Sharpe -0.49), GBP_JPY (live WR 12.5% vs BT 27.8%; 15m BT Sharpe 4.69 base — not yet deployed), EUR_AUD (full dataset Sharpe -0.07 vs BT 4.52; over-fitted on short Dec 2025–Feb 2026 window — suspended Apr 1, 2026).
**USD_JPY migrated to 15m (Apr 2, 2026):** Full sweep confirmed 15m outperforms 5m — Sharpe 2.85 vs 1.37, MaxDD -8.65% vs -18.63%, Avg-R 0.45 vs 0.18 (trades: `data/backtest_usdjpy_15m_production_trades.csv`). Config: DI>30, RR=3.0, persist=1, avoid_hours=[15–21]; adx_min and di_spread_min removed (no benefit on 15m).
**NOT deployed:** AU200_AUD (Sharpe 2.10, MaxDD -9.22%).

### SMA Scalping Rules & Gotchas

**Core entry (LONG):** Price > SMA20/50/100 · DI+ > DI- · DI+ > threshold for N candles · ADX ≥ adx_min · entry not below 2-candle lows
**Stop Loss:** `max(structural_distance, 1×ATR)` — ATR floor prevents noise-triggered stops.
**Exit mechanism:** Broker-level SL and TP orders placed on Oanda at entry — trade closes **only** when SL or TP is hit. SMA20 trailing exit is disabled for all SmaScalping pairs. Backtesting showed SMA20 exit cut 60–89% of trades short before TP, reducing Sharpe by 2–5 points per pair (validated Mar 6, 2026 — see `data/backtest_sma_all_pairs_exit_mode.csv`).

**Optional noise filters** (configured per-pair in `best_strategies.json`):

| Filter | Description |
|--------|-------------|
| `di_persist` | DI must exceed threshold for N consecutive candles. Use 2 for choppy pairs (JP225, NAS100 15m, UK100, EUR_USD); keep 1 for fast-moving (XAG 5m, BCO). |
| `adx_min` | ADX floor. JP225 uses 20, NAS100 uses 25. |
| `adx_rising` | ADX must be rising vs previous candle. XAU uses this. |
| `atr_ratio_min` | ATR ≥ N × 20-bar average. XAG=1.2 (needs volatile regimes for 12R), NAS100=1.0. |
| `di_slope` | DI+ must be rising over last 2 candles — targets fading-momentum entries. Safe for most pairs. |
| `avoid_hours` | Block entry during specified UTC hours. XAU=[8,9] (London open), XAG=[14,15,16] (London-NY overlap), NAS100=[7,8,21,22,23] (pre-London + post-NYSE), USD_JPY=[15,16,17,18,19,20,21] (NY open + evening). |
| `di_spread_min` | Min DI+/DI- gap — rejects marginal crossings. |
| `body_ratio_min` | Min candle body/range ratio — rejects doji candles. |

**R:R sweep findings (Apr 1, 2026 — `data/backtest_rr_sweep.csv`):**

| Pair | Old RR | New RR | Notes |
|------|--------|--------|-------|
| XAU_USD | 5.0 | 3.5 | Sharpe improves significantly (5.41→7.96); plateau at 3.5–4.0 |
| JP225_USD | 5.0 | 1.5 | WR jumps 29%→52%; drawdown risk decreases at lower RR |
| UK100_GBP | 6.0 | 3.5 | Sharpe nearly unchanged (8.45→8.04); reduces TP distance |
| NAS100_USD | 3.0 | 2.5 | Marginal Sharpe difference; 2.5 improves trade frequency |
| EUR_USD | 6.0 | 6.0 | Confirmed optimal — lower values destroy Sharpe |
| XAG_USD | 12.0 | 12.0 | High-RR tail regime; Sharpe rises monotonically to 11.0–12.0 |
| BCO_USD | 4.0 | 4.0 | Already at sweep peak |
| USD_JPY | 2.5 | 3.0 | Migrated to 15m Apr 2, 2026; 15m sweep peak at RR=3.0 |

**⚠️ Do NOT apply:**
- `sma_ordered` to NAS100 or XAG — destroys Sharpe (NAS100: 2.67→-1.04). SMAs lag on fast moves.
- `di_slope` to USD_JPY — harmful (-1.02 Sharpe).
- `di_persist=2` to USD_JPY — harmful (Sharpe 1.69→0.89, MaxDD balloons to -18.4%).
- `di_threshold` above 30 for USD_JPY — DI spread too tight on JPY; di=35 produces negative ROI.
- `adx_min` above 15 for USD_JPY — adx_min=20+ over-filters (Sharpe 1.69→1.15); sweet spot is 15.
- `rsi_filter` on any 5m pair — adds noise.
- `di_persist=2` to XAG (5m) — kills edge (XAG: +86%→+10%). Note: NAS100 15m uses persist=2 in production — the restriction was validated on 5m only.
- SMA20 trailing exit — validated harmful on all tested pairs; 60–89% of trades exit early, avg-R collapses to <0.25R vs 0.96–2.44R with fixed TP. Do not re-enable `check_exit` for SmaScalping in `portfolio_monitor.py` or `oanda_trade_service.py`.

---

## Active Strategy Configuration (Apr 1, 2026)

8 active pairs, all running SmaScalping. EUR_AUD suspended Apr 1, 2026 (live Sharpe -0.07 vs BT 4.52 — over-fitted short window). RR values updated for XAU, JP225, UK100, NAS100 based on full RR sweep (see `data/backtest_rr_sweep.csv`). Other strategies archived in `data/metadata/best_strategies_archived.json`.

**Active pairs** (`best_strategies.json` + `forex_pairs.json`):

| Asset | Strategy | TF | Sharpe | ROI% | WR% | MaxDD% | risk_pct | RR |
|-------|----------|----|--------|------|-----|--------|----------|----|
| UK100_GBP | SmaScalping | 15m | 8.45 | 42.7% | 42.1% | -3.94% | 1.0% | 3.5 |
| XAU_USD | SmaScalping | 15m | 6.48 | 39.9% | 35.5% | -7.73% | 1.5% | 3.5 |
| XAG_USD | SmaScalping | 5m | 6.30 | 115.7% | 26.5% | -6.79% | 1.0% | 12.0 |
| JP225_USD | SmaScalping | 5m | 5.87 | 52.5% | 35.0% | -5.85% | 1.0% | 1.5 |
| EUR_USD | SmaScalping | 15m | 5.56 | 56.2% | 29.5% | -10.47% | 1.0% | 6.0 |
| NAS100_USD | SmaScalping | 15m | 4.31 | 37.4% | 39.0% | -5.85% | 1.0% | 2.5 |
| BCO_USD | SmaScalping | 15m | 3.18 | 25.4% | 29.4% | -8.74% | 1.0% | 4.0 |
| USD_JPY | SmaScalping | 15m | 2.85 | 50.54% | 34.5% | -8.65% | 1.0% | 3.0 |

**New 15m SmaScalping configs (added Mar 27, 2026):**

| Asset | DI> | RR | persist | Filters | Trades | Notes |
|-------|-----|-----|---------|---------|--------|-------|
| UK100_GBP | 35 | 3.5 | 2 | `atr_ratio=1.2, avoid_hours=[15,16,17,18,19]` | 19 | Replaces PVTScalping 1h (Sharpe 2.99). Blocks post-UK-close dead volume. Low trade count — monitor closely. RR reduced from 6.0 → 3.5 (Apr 1, 2026 sweep). |
| EUR_USD | 25 | 6.0 | 2 | `atr_ratio=1.0, avoid_hours=[20,21,22,23]` | 44 | Strongest new addition — 44 trades, clean 2-filter config. Blocks NY/pre-London dead zone. MaxDD -10.47% elevated — use 1% risk. RR=6.0 confirmed optimal. |
| NAS100_USD | 30 | 2.5 | 2 | `di_slope=true, adx_min=25, atr_ratio=1.0, avoid_hours=[7,8,21,22,23]` | 59 | Replaces NewBreakout (Sharpe 3.36, never triggered live). Mirrors old 5m filter set + adx_min=25. MaxDD -5.85% — best of all active pairs. RR reduced from 3.0 → 2.5 (Apr 1, 2026 sweep). |

**Archived (configs preserved in `best_strategies_archived.json`, not running):**

| Asset | Strategy | Sharpe | Reason archived |
|-------|----------|--------|-----------------|
| UK100_GBP | PVTScalping | 2.99 | Replaced by SmaScalping 15m (Sharpe 8.45) Mar 27, 2026 |
| NAS100_USD | NewBreakout | 3.36 | Replaced by SmaScalping 15m (Sharpe 4.31) Mar 27, 2026 — never triggered in live trading |
| XAG_USD | PVTScalping | 4.95 | Reducing strategy clutter |
| XAG_USD | DailyORB | 1.99 | Reducing strategy clutter |
| XAG_USD | SilverSniper | 1.53 | Reducing strategy clutter |
| NAS100_USD | PVTScalping | 6.24 | Replaced by NewBreakout, then SmaScalping 15m |
| NAS100_USD | SmaScalping (5m) | 3.28 | Replaced by NewBreakout Mar 14 (JP225 correlation), then back to SmaScalping 15m Mar 27 |
| XAU_USD | HeikenAshi | 2.35 | Reducing strategy clutter |
| USD_CHF | NewBreakout | 1.94 | Low Sharpe; insufficient live data |
| AUD_USD | SmaScalping | — | Suspended: live WR 20% vs BT 34.8% |
| USD_CAD | SmaScalping | — | Suspended: 0% live WR, Sharpe -0.49 |
| GBP_JPY | SmaScalping | — | Suspended 5m: live WR 12.5% vs BT 27.8%. 15m BT Sharpe 4.69 (base) / 6.57 (filtered) — not yet deployed, insufficient live data. |
| EUR_AUD | SmaScalping | 4.52 (BT only) | Suspended Apr 1, 2026: full dataset Sharpe -0.07 vs BT 4.52. Over-fitted on short Dec 2025–Feb 2026 window. |
| USD_JPY | SmaScalping 5m | 1.37 (live BT) | Replaced by 15m Apr 2, 2026: 5m Sharpe 1.37, MaxDD -18.63%. 15m Sharpe 2.85, MaxDD -8.65%. |

**Suspended (Mar 3, 2026):** AUD_USD, USD_CAD suspended for live underperformance. BCO_USD re-added Mar 19, 2026. JP225 HeikenAshi archived Mar 3, 2026. EUR_AUD suspended Apr 1, 2026.

---


## Trade History & Analytics

**Status:** ✅ Production Ready — See [docs/features/TRADE_HISTORY.md](./docs/features/TRADE_HISTORY.md)
- Filtering, sorting, CSV export; equity curve, monthly returns, strategy comparison charts
- Auto-sync with Oanda every 5 minutes; default date range: Feb 19, 2026+

---

## Documentation Organization

- When adding strategies: run backtest sweep → save CSV to `data/` → update `best_strategies.json` + `forex_pairs.json` → update CLAUDE.md active table

**Active backtest data:** `data/backtest_sma_15m_all_pairs.csv`, `data/backtest_noise_filter_sweep.csv`, `data/backtest_sma_nas100_15m_filter_sweep.csv`, `data/backtest_bco_strategy_compare.csv`, `data/backtest_sma_jpy_pairs.csv`, `data/backtest_sma_all_pairs_exit_mode.csv`, `data/backtest_rr_sweep.csv`, `data/backtest_usdjpy_15m_production_trades.csv`

**Last Updated:** April 2, 2026 — USD_JPY migrated to 15m (DI>30, RR=3.0, Sharpe 2.85, MaxDD -8.65% vs -18.63% on 5m). April 1, 2026 — EUR_AUD suspended (live Sharpe -0.07 vs BT 4.52; over-fitted short Dec 2025–Feb 2026 window). RR values updated via full sweep (`data/backtest_rr_sweep.csv`): XAU_USD 5.0→3.5 (sweep peak at 3.5–4.0), JP225_USD 5.0→1.5 (WR jumps 29%→52%), UK100_GBP 6.0→3.5 (sweep peak at 3.5), NAS100_USD 3.0→2.5. EUR_USD confirmed at RR=6.0 (optimal, lower values destroy Sharpe). XAG confirmed at RR=12.0 (high-RR tail regime). BCO and USD_JPY unchanged. Previous update: March 27, 2026 — NAS100_USD switched from NewBreakout (Sharpe 3.36, never triggered live) to SmaScalping 15m (Sharpe 4.31, ROI +37.4%, MaxDD -5.85%, WR 39.0%, 59 trades, DI>30, RR=3.0, p=2, di_slope, adx_min=25, atr_ratio=1.0, avoid_hours=[7,8,21,22,23]). Also: Added EUR_USD SmaScalping 15m (Sharpe 5.56, ROI +56.2%, MaxDD -10.47%, WR 29.5%, 44 trades, DI>25, RR=6.0, p=2, atr_ratio=1.0, avoid_hours=[20,21,22,23]); EUR_AUD SmaScalping 15m (Sharpe 4.52, ROI +23.3%, MaxDD -8.65%, WR 30.8%, 26 trades, DI>30, RR=5.0, p=1, di_slope, adx_min=15, avoid_hours=[7,8]); UK100_GBP switched from PVTScalping 1h to SmaScalping 15m (Sharpe 8.45, ROI +42.7%, MaxDD -3.94%, WR 42.1%, 19 trades, DI>35, RR=6.0, p=2, atr_ratio=1.2, avoid_hours=[15,16,17,18,19]).

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
