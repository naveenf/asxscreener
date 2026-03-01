# ASX Stock Screener - Project Context

## Project Overview
Full-stack app identifying trading opportunities on ASX and Global Forex/Commodity markets via a **Dynamic Strategy Selection** engine. Calculations match **Pine Script** (TradingView) standards using Wilder's Smoothing.

**Strategies:** Trend Following, Mean Reversion, Squeeze, Sniper, Enhanced Sniper, Silver Sniper, Daily ORB, Silver Momentum, Commodity Sniper, Heiken Ashi Gold, Triple Trend, PVT Scalping, SMA Scalping.

---

## Git Workflow

### ⚠️ NEVER auto-commit — always ask user first

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

## Trading Strategies

| # | Strategy | Key Indicators | Best For |
|---|----------|---------------|----------|
| 1 | **Trend Following** | ADX>30, DI+/DI- crossover | Strong trending pairs |
| 2 | **Mean Reversion** | Bollinger Bands, RSI>70 | Range-bound markets |
| 3 | **Squeeze** | BB inside KC, Momentum oscillator | Gold, Oil, Nasdaq, UK100 |
| 4 | **Sniper** | 15m EMA/DI, 1H ADX>25, EMA34 | Major forex (AUD_USD, EUR_USD) |
| 5 | **Enhanced Sniper** | 15m Momentum, 4H SMA200, time filter | AUD_USD (2.5R) |
| 6 | **Silver Sniper** | 5m Squeeze, 15m ADX>20, FVG | XAG_USD (3.0R) |
| 7 | **Daily ORB** | Sydney session range, 4H DI, BB width | XAG_USD (2.0R) |
| 8 | **Silver Momentum** | 1H MACD, 4H EMA50/200, 13-22 UTC only | XAG_USD (2.5R) |
| 9 | **Commodity Sniper** | 5m Squeeze, 15m ADX, time filter | BCO_USD (3.0R) |
| 10 | **Heiken Ashi Gold** | HA candles, SMA200, 4H trend, ADX>22 | XAU_USD |
| 11 | **Triple Trend** | Fibonacci, Supertrend, Ehlers IT | Steady trending pairs |
| 12 | **PVT Scalping** | PVT>0.05, EMA50, SMA100, circuit breaker | UK100, NAS100, XAG |
| 13 | **SMA Scalping** | SMA20/50/100 stack, DI+/DI-, ATR SL floor | Multi-pair (see below) |

**Silver time filter (all 3 XAG strategies):** `avoid_utc_hours: [14, 15, 16]` — blocks London-NY overlap noise.

---

## SMA Scalping — Deployed Configs (Feb 28, 2026)

| Pair | TF | DI> | RR | persist | Extra filters | Trades | WR% | ROI% | Sharpe | MaxDD |
|------|----|-----|----|---------|--------------|--------|-----|------|--------|-------|
| XAU_USD | 15m | 35 | 5.0 | 2 | `adx_rising` | 30 | 36.7% | 41.3% | 6.48 | -7.73% |
| XAG_USD | 5m | 35 | 10.0 | 1 | `atr_ratio=1.2, di_slope` | 43 | 25.6% | 106.9% | 5.59 | -4.90% |
| JP225_USD | 5m | 30 | 5.0 | 2 | `adx_min=20, di_slope` | 37 | 35.1% | 48.2% | 5.93 | -3.94% |
| NAS100_USD | 5m | 35 | 4.5 | 1 | `atr_ratio=1.0, di_slope` | 39 | 28.2% | 22.5% | 3.28 | -10.47% |
| GBP_JPY | 15m | 25 | 5.0 | 1 | — | 36 | 27.8% | 25.4% | 3.58 | -10.60% |
| USD_JPY | 5m | 30 | 2.5 | 1 | `avoid_hours=[15-21]` | 134 | 37.3% | 47.8% | 2.78 | -7.38% |
| AUD_USD | 5m | 35 | 2.5 | 2 | — | 46 | 34.8% | 9.8% | 1.90 | -7.30% |
| USD_CAD | 5m | 35 | 3.0 | 1 | — | 46 | 23.9% | -2.6% | -0.49 | -17.38% |

**NOT deployed:** AU200_AUD (Sharpe 1.59, MaxDD -21%). See `data/backtest_sma_au200.csv`.

### SMA Scalping Rules & Gotchas

**Core entry (LONG):** Price > SMA20/50/100 · DI+ > DI- · DI+ > threshold for N candles · ADX ≥ adx_min · entry not below 2-candle lows
**Stop Loss:** `max(structural_distance, 1×ATR)` — ATR floor prevents noise-triggered stops.

**Optional noise filters** (configured per-pair in `best_strategies.json`):

| Filter | Description |
|--------|-------------|
| `di_persist` | DI must exceed threshold for N consecutive candles. Use 2 for choppy pairs (JP225, AUD_USD); keep 1 for fast-moving (XAG, NAS100). |
| `adx_min` | ADX floor. JP225 uses 20. |
| `adx_rising` | ADX must be rising vs previous candle. XAU uses this. |
| `atr_ratio_min` | ATR ≥ N × 20-bar average. XAG=1.2 (needs volatile regimes for 10R), NAS100=1.0. |
| `di_slope` | DI+ must be rising over last 2 candles — targets fading-momentum entries. Safe for most pairs. |
| `avoid_hours` | Block entry during specified UTC hours. USD_JPY uses [15–21]. |
| `di_spread_min` | Min DI+/DI- gap — rejects marginal crossings. |
| `body_ratio_min` | Min candle body/range ratio — rejects doji candles. |

**⚠️ Do NOT apply:**
- `sma_ordered` to NAS100 or XAG — destroys Sharpe (NAS100: 2.67→-1.04). SMAs lag on fast moves.
- `atr_ratio=1.2` to GBP_JPY — harmful.
- `di_slope` to USD_JPY — harmful (-1.02 Sharpe).
- `rsi_filter` on any 5m pair — adds noise.
- `di_persist=2` to XAG or NAS100 — kills edge (XAG: +86%→+10%).

---

## Portfolio Deployment Status

| Asset | Strategy | ROI | WR% | Status |
|-------|----------|-----|-----|--------|
| UK100_GBP | PVT Scalping | +93.67% | 66.0% | ✅ ACTIVE |
| XAU_USD | HeikenAshi + SmaScalping | +46.75% / +41.3% | 40.6% / 36.7% | ✅ ACTIVE |
| XAG_USD | DailyORB + SilverSniper + SilverMomentum + SmaScalping | combined | ~38% | ✅ ACTIVE |
| USD_CHF | NewBreakout | +60.96% | 40.74% | ✅ ACTIVE |
| JP225_USD | HeikenAshi + SmaScalping | +32.3% / +48.2% | 31.1% / 35.1% | ✅ ACTIVE |
| GBP_JPY | SmaScalping | +25.4% | 27.8% | ✅ ACTIVE |
| USD_JPY | SmaScalping | +47.8% | 37.3% | ⚠️ MONITORING |
| NAS100_USD | NewBreakout + PVT + SmaScalping | +11.6% / +72% / +22.5% | 38.5% / 75.8% / 28.2% | ⚠️ VALIDATING |
| AUD_USD | EnhancedSniper + SmaScalping | +3.0% / +9.8% | 66.7% / 34.8% | ⚠️ MONITORING |
| BCO_USD | CommoditySniper | +11.70% | 44.4% | ⚠️ MONITORING |
| USD_CAD | SmaScalping | -2.6% | 23.9% | ⚠️ MONITORING |

**USD_CAD warning:** Break-even WR at 3.0R is 25%; suspend if live WR falls below 25%.

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

**Last Updated:** February 28, 2026 — SmaScalping noise filter optimization across 8 pairs.
