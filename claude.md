# ASX Stock Screener - Project Context

## Project Overview
Full-stack app identifying trading opportunities on ASX and Global Forex/Commodity markets via a **Dynamic Strategy Selection** engine. Calculations match **Pine Script** (TradingView) standards using Wilder's Smoothing.

**Strategies (active):** Silver Sniper, Daily ORB, Heiken Ashi, PVT Scalping, SMA Scalping, NewBreakout.

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
│       ├── forex_detector.py              # Trend Following (MTF)
│       ├── squeeze_detector.py            # Squeeze Strategy
│       ├── sniper_detector.py             # Legacy Sniper
│       ├── enhanced_sniper_detector.py    # Optimized Forex Sniper
│       ├── silver_sniper_detector.py      # Silver 5m + FVG
│       ├── daily_orb_detector.py          # Daily Open Range Breakout
│       ├── commodity_sniper_detector.py   # Commodity-optimized Sniper
│       ├── triple_trend_detector.py       # Fib + Supertrend
│       ├── pvt_scalping_detector.py       # PVT Scalping
│       ├── sma_scalping_detector.py       # SMA Scalping
│       └── strategy_interface.py          # Abstract Base Class
├── data/
│   ├── raw/                    # Stock CSVs
│   ├── forex_raw/              # Forex MTF CSVs (5m, 15m, 1h, 4h)
│   └── metadata/
│       ├── best_strategies.json  # Strategy config map (source of truth)
│       ├── forex_pairs.json
│       └── stock_list.json
├── scripts/
│   ├── backtest_arena.py       # Backtesting engine
│   └── download_forex.py       # Data fetcher
└── docs/analysis/              # Backtest reports
```

---

## Trading Strategies (Active)

| # | Strategy | Key Indicators | Pairs |
|---|----------|---------------|-------|
| 1 | **SMA Scalping** | SMA20/50/100 stack, DI+/DI-, ATR SL floor | XAU, XAG, JP225, NAS100, USD_JPY |
| 2 | **PVT Scalping** | PVT>0.05, EMA50, SMA100, circuit breaker | UK100, NAS100, XAG |
| 3 | **NewBreakout** | 15m S/R breakout, EMA34, ADX>25, HTF 4h | NAS100, USD_CHF |
| 4 | **Heiken Ashi** | HA candles, SMA200, 4H trend, ADX>22 | XAU |
| 5 | **Daily ORB** | Sydney session range, 4H DI, BB width | XAG (2.0R) |
| 6 | **Silver Sniper** | 5m Squeeze, 15m ADX>20, FVG | XAG (3.0R) |

**Silver time filter (all XAG strategies):** `avoid_utc_hours: [14, 15, 16]` — blocks London-NY overlap noise.

---

## SMA Scalping — Deployed Configs (Mar 3, 2026)

| Pair | TF | DI> | RR | persist | Extra filters | Trades | WR% | ROI% | Sharpe | MaxDD |
|------|----|-----|----|---------|--------------|--------|-----|------|--------|-------|
| XAU_USD | 15m | 35 | 5.0 | 2 | `adx_rising, avoid_hours=[8,9]` | 26 | 42.3% | 47.1% | 7.97 | -5.85% |
| XAG_USD | 5m | 35 | 10.0 | 1 | `atr_ratio=1.2, di_slope, avoid_hours=[14,15,16]` | 45 | 20.0% | 64.2% | 4.17 | -7.73% |
| JP225_USD | 5m | 30 | 5.0 | 2 | `adx_min=20, di_slope` | 37 | 35.1% | 48.2% | 5.93 | -3.94% |
| NAS100_USD | 5m | 35 | 4.5 | 1 | `atr_ratio=1.0, di_slope, avoid_hours=[7,21,22,23]` | 34 | 32.4% | 28.8% | 4.42 | -10.47% |
| USD_JPY | 5m | 30 | 2.5 | 1 | `avoid_hours=[15-21]` | 134 | 37.3% | 47.8% | 2.78 | -7.38% |

**Suspended (live underperformance):** AUD_USD (live WR 20% vs 34.8% BT), USD_CAD (0% WR, Sharpe -0.49), GBP_JPY (live WR 12.5% vs 27.8% BT).
**NOT deployed:** AU200_AUD (Sharpe 1.59, MaxDD -21%). See `data/backtest_sma_au200.csv`.

### SMA Scalping Rules & Gotchas

**Core entry (LONG):** Price > SMA20/50/100 · DI+ > DI- · DI+ > threshold for N candles · ADX ≥ adx_min · entry not below 2-candle lows
**Stop Loss:** `max(structural_distance, 1×ATR)` — ATR floor prevents noise-triggered stops.

**Optional noise filters** (configured per-pair in `best_strategies.json`):

| Filter | Description |
|--------|-------------|
| `di_persist` | DI must exceed threshold for N consecutive candles. Use 2 for choppy pairs (JP225); keep 1 for fast-moving (XAG, NAS100). |
| `adx_min` | ADX floor. JP225 uses 20. |
| `adx_rising` | ADX must be rising vs previous candle. XAU uses this. |
| `atr_ratio_min` | ATR ≥ N × 20-bar average. XAG=1.2 (needs volatile regimes for 10R), NAS100=1.0. |
| `di_slope` | DI+ must be rising over last 2 candles — targets fading-momentum entries. Safe for most pairs. |
| `avoid_hours` | Block entry during specified UTC hours. XAU=[8,9] (London open), XAG=[14,15,16] (London-NY overlap), NAS100=[7,21,22,23] (pre-London + post-NYSE), USD_JPY=[15–21]. |
| `di_spread_min` | Min DI+/DI- gap — rejects marginal crossings. |
| `body_ratio_min` | Min candle body/range ratio — rejects doji candles. |

**⚠️ Do NOT apply:**
- `sma_ordered` to NAS100 or XAG — destroys Sharpe (NAS100: 2.67→-1.04). SMAs lag on fast moves.
- `di_slope` to USD_JPY — harmful (-1.02 Sharpe).
- `rsi_filter` on any 5m pair — adds noise.
- `di_persist=2` to XAG or NAS100 — kills edge (XAG: +86%→+10%).

---

## Portfolio Deployment Status (Mar 3, 2026)

| Asset | Strategy | Sharpe | BT WR% | Status |
|-------|----------|--------|--------|--------|
| NAS100_USD | NewBreakout + PVTScalping + SmaScalping | 8.48 / 6.24 / 4.42 | 38.5% / 75.8% / 32.4% | ✅ ACTIVE |
| XAU_USD | SmaScalping + HeikenAshi | 7.97 / 2.35 | 42.3% / 40.6% | ✅ ACTIVE |
| UK100_GBP | PVTScalping | 5.79 | 66.0% | ✅ ACTIVE |
| JP225_USD | SmaScalping | 5.93 | 35.1% | ✅ ACTIVE |
| XAG_USD | SmaScalping + PVTScalping + DailyORB + SilverSniper | 4.17 / 4.95 / 1.99 / 1.53 | 20.0% / — / — / — | ✅ ACTIVE |
| USD_JPY | SmaScalping | 2.78 | 37.3% | ⚠️ MONITORING (live WR 15.4% vs BT 37.3%) |
| USD_CHF | NewBreakout | 1.94 | 40.7% | ⚠️ MONITORING (insufficient live data) |

**Suspended (Mar 3, 2026):** AUD_USD, USD_CAD, BCO_USD, JP225 HeikenAshi — removed due to live underperformance or insufficient Sharpe.

---

## Multi-Strategy Framework

`best_strategies.json` supports multiple strategies per asset. `forex_screener.py` loads data once, runs all strategies, ranks by score.

```json
"XAG_USD": {
  "strategies": [
    { "strategy": "DailyORB", "timeframe": "15m", "target_rr": 2.0, "params": { ... } },
    { "strategy": "SilverSniper", "timeframe": "5m", "target_rr": 3.0 },
    { "strategy": "SmaScalping", "timeframe": "5m", "target_rr": 10.0, "params": { ... } }
  ]
}
```

Backward compatible with legacy single-strategy format.

---

## Trade History & Analytics

**Status:** ✅ Production Ready — See [docs/features/TRADE_HISTORY.md](./docs/features/TRADE_HISTORY.md)
- Filtering, sorting, CSV export; equity curve, monthly returns, strategy comparison charts
- Auto-sync with Oanda every 5 minutes; default date range: Feb 19, 2026+

---

## NewBreakout Strategy

- **Timeframe:** 15m (HTF: 4h trend filter, ADX>25)
- **Exit:** EMA9 crossover
- **USD_CHF:** 1.5R target · **NAS100_USD:** 2.0R target (1.5R was unprofitable: -3.6% ROI)

---

## Documentation Organization

- Analysis reports → `docs/analysis/[ASSET]_PERFORMANCE_REPORT.md` or `[STRATEGY]_RESULTS.md`
- Backtest CSVs → `data/backtest_results_[ASSET]_[STRATEGY].csv`
- When adding strategies: create CSV in `data/`, create doc in `docs/analysis/`, update CLAUDE.md

**Key analysis docs:** `docs/analysis/` — DAILY_ORB_FINAL_RESULTS.md, HEIKEN_ASHI_V2_CRITICAL_REVIEW.md, GT_SCORE_RESULTS_SUMMARY.md, SILVER_STRATEGY_FINAL_SUMMARY.md

**Last Updated:** March 3, 2026 — Portfolio pruned to 7 pairs; suspended AUD_USD, USD_CAD, BCO_USD, JP225 HeikenAshi based on live underperformance.

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
