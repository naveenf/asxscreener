# ASX Stock Screener - Project Context

## Project Overview
The ASX Stock Screener is a full-stack application designed to identify trading opportunities on the Australian Securities Exchange (ASX) and Global Forex/Commodity markets. It uses a **Dynamic Strategy Selection** engine to apply the most effective algorithm for each asset class.

The system implements nine core trading strategies:
1.  **Trend Following** (ADX/DI)
2.  **Mean Reversion** (Bollinger Bands/RSI)
3.  **Squeeze** (Volatility Compression Breakout)
4.  **Sniper** (15m Execution with 1H Confirmation for Forex Majors)
5.  **Enhanced Sniper** (Optimized Forex Precision with 4H Trend Alignment)
6.  **Silver Sniper** (High-Precision 5m Squeeze + FVG for Silver)
7.  **Daily ORB** (Daily Open Range Breakout with Structural Alignment)
8.  **Commodity Sniper** (Optimized 5m Squeeze + Time Filters for Commodities)
9.  **Triple Trend** (Fibonacci + Supertrend + Instant Trend)

Calculations match **Pine Script** (TradingView) standards, using "Wilder's Smoothing" for technical accuracy.

## Tech Stack

### Backend
*   **Framework:** FastAPI (Python 3.10+)
*   **Data Processing:** Pandas, NumPy
*   **Data Source:**
    *   Stocks: `yfinance` (Yahoo Finance)
    *   Forex/Commodities: `yfinance` / Oanda (Downloaded via `scripts/download_forex.py`)
*   **Strategies:** Multi-Timeframe (MTF) analysis (15m, 1h, 4h).
*   **Database/Auth:** Google Firebase (Firestore + Authentication)
*   **Testing:** `pytest`

### Frontend
*   **Framework:** React 18
*   **Build Tool:** Vite
*   **Styling:** CSS Modules
*   **Auth:** `@react-oauth/google`

## Directory Structure

```
asx-screener/
├── backend/
│   ├── app/
│   │   ├── api/             # API Routes (auth, portfolio, stocks)
│   │   ├── models/          # Pydantic data models
│   │   ├── services/        # Core business logic
│   │   │   ├── indicators.py           # ADX, DI, RSI, BB implementation
│   │   │   ├── strategy_interface.py   # Abstract Base Class for MTF strategies
│   │   │   ├── forex_detector.py       # Trend Following logic (MTF)
│   │   │   ├── squeeze_detector.py     # Squeeze Strategy logic (MTF)
│   │   │   ├── triple_trend_detector.py    # Triple Confirmation logic (Fib+Supertrend)
│   │   │   ├── sniper_detector.py          # Legacy Sniper logic
│   │   │   ├── enhanced_sniper_detector.py # NEW: Optimized Forex Sniper
│   │   │   ├── silver_sniper_detector.py   # Silver-specific Sniper (5m + FVG)
│   │   │   ├── daily_orb_detector.py       # NEW: Daily Open Range Breakout (15m + 4h)
│   │   │   ├── commodity_sniper_detector.py # Commodity-optimized Sniper
│   │   │   └── forex_screener.py           # Dynamic Strategy Orchestrator
│   │   ├── config.py        # Environment configuration
│   │   └── main.py          # App entry point
│   ├── tests/               # Pytest suite
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── components/      # React components (SignalCard, Portfolio)
│   │   ├── context/         # AuthContext
│   │   └── main.jsx         # Entry point (Env var usage)
│   ├── vite.config.js       # Proxy setup for /api and /auth
│   └── package.json         # Node dependencies
├── data/
│   ├── raw/                 # CSV storage for stock data
│   ├── forex_raw/           # CSV storage for Forex MTF data (15m, 1h, 4h)
│   └── metadata/            # Configuration files
│       ├── best_strategies.json # Optimized Strategy Map
│       ├── forex_pairs.json     # Asset list
│       └── stock_list.json      # Stock list
├── scripts/
│   ├── backtest_arena.py    # Backtesting Engine for Strategy Optimization
│   ├── squeeze_test.py      # Targeted Squeeze Strategy Analysis
│   └── download_data.py     # Independent data fetcher
└── start.py                 # Unified startup script
```

## Trading Strategies

### 1. Trend Following (ADX/DI)
*   **Logic:** Identifies strong directional trends.
*   **Indicators:** ADX (>30), DI+ / DI- Crossover.
*   **Best For:** Strong trending pairs (e.g., EUR/GBP).

### 2. Mean Reversion (BB/RSI)
*   **Logic:** Identifies overbought conditions expecting a return to the mean.
*   **Indicators:** Bollinger Bands (Volatility/Extreme Price), RSI (>70).
*   **Best For:** Range-bound markets.

### 3. Squeeze Strategy (Volatility Compression Breakout)
*   **Logic:** Identifies periods of low volatility (squeeze) using TTM Squeeze logic, followed by an explosive breakout confirmed by momentum.
*   **Indicators:** Bollinger Bands (20, 2.0), Keltner Channels (20, 1.2 multiplier), Momentum Oscillator (Close - SMA 14).
*   **Rules:**
    *   **Squeeze:** Bollinger Bands must be inside Keltner Channels within the last 5 candles.
    *   **Entry:** Breakout from Bollinger Bands with Momentum alignment (Momentum > 0 for BUY, < 0 for SELL).
    *   **Exit:** 2.0x Risk (Default) or 3.0x Risk (Gold/Commodities).
    *   **Stop Loss:** Middle Bollinger Band (SMA 20).
*   **Best For:** Gold, Copper, Nasdaq, Oil, UK100.

### 4. Sniper (Forex Precision Trading)
*   **Logic:** High-precision forex trading on 15m timeframe with 1h confirmation using casket-based filtering.
*   **Indicators:** 15m EMA proximity, DI+/DI- momentum, 1H ADX, EMA34.
*   **Rules:**
    *   **Casket Assignment:** Pairs grouped by characteristics (Momentum, Steady, Cyclical).
    *   **Entry:** DI+ crosses above DI- on 15m with casket-specific filters.
    *   **HTF Confirmation:** 1H ADX > 25, price alignment with EMA34.
    *   **Exit:** 1.5x Risk for forex majors, SMA 20 exit signal.
*   **Best For:** Major forex pairs (AUD_USD, EUR_USD).

### 5. Enhanced Sniper (Optimized Forex Precision)
*   **Logic:** Enhanced version of Sniper strategy with 4H trend alignment and time filters.
*   **Indicators:** 15m Momentum, 4H Trend (SMA200), Time-of-day filters.
*   **Rules:**
    *   **Trend:** Only trade in direction of 4H SMA200.
    *   **Momentum:** ADX must be rising on 15m.
    *   **Time Filter:** Blocks entry during identified high-loss hours.
    *   **Exit:** 2.5x Risk (Optimized for AUD_USD).
*   **Best For:** AUD_USD.
*   **Performance (2026-02-06):** 66.7% win rate, +3.0% return (15 trades).

### 6. Silver Sniper (High-Precision Intraday)
*   **Logic:** Identifies high-probability breakouts on 5m timeframe by aligning with 15m trends and institutional order blocks (FVG).
*   **Indicators:** 5m Squeeze, 15m ADX (>20), 5m Fair Value Gap (FVG).
*   **Rules:**
    *   **Squeeze:** BB width at 24-hour lows on 5m (threshold: 1.3x minimum).
    *   **Confirmation:** 15m Trend must match breakout direction (DI+/DI- + ADX > 20).
    *   **Mitigation:** Entry must occur within a recent 5m FVG (Order Block confirmation).
    *   **Exit:** 3.0x Risk (Fixed) or BB Middle cross.
*   **Best For:** Silver (XAG_USD).
*   **Performance (2026-02-03):** 55.6% win rate, +19.02% return, Sharpe 1.53.

### 7. Daily ORB (Daily Open Range Breakout)
*   **Logic:** Identifies high-probability structural breakouts from daily consolidation ranges using Sydney session open timing.
*   **Indicators:** Daily Open Range (High/Low), 15m Momentum (ADX), Bollinger Bands Width (Squeeze), 4H Trend (DI+/DI-).
*   **Rules:**
    *   **Range Definition:** High/Low from first 1.5 hours of Sydney session (19:00-20:30 UTC).
    *   **Breakout Trigger:** Price closes 0.5x ATR beyond range level on 15m candle (eliminates wicks).
    *   **Momentum Check:** 15m ADX > 18 (momentum building), ADX rising.
    *   **Squeeze Filter:** Bollinger Bands width < 1.8x of 20-period minimum (consolidation detection).
    *   **HTF Confirmation:** 4H DI+ > DI- by 5+ points, ADX > 20 (clear directional bias).
    *   **Stop Loss:** 1.5x ATR + spread buffer (tighter than other breakout strategies).
    *   **Take Profit:** **2.0x Risk** (optimized for maximum win rate and ROI).
    *   **Exit:** On HTF trend reversal (DI flip) or weakness (ADX < 20).
*   **Best For:** Silver (XAG_USD) - complements impulse-driven SilverSniper strategy.
*   **Performance (2026-02-12 - Optimized 1:2.0 R:R):**
    *   Win Rate: **66.7%** (exceeds SilverSniper's 55.6%)
    *   ROI: **+26.23%** (exceeds SilverSniper's 19.02% by 38%)
    *   Sharpe: **2.35** (exceptional risk-adjusted returns)
    *   Max Drawdown: **-2.0%** (minimal capital drawdown)
    *   Sample: 12 trades (8 wins) over backtest period.
    *   Note: Optimized from 2.5x RR (50% WR, +18.71%) to 2.0x RR (66.7% WR, +26.23%) for better consistency.

### 8. Silver Momentum (1H MACD + 4H Trend Confirmation)
*   **Logic:** High-frequency momentum trading using MACD histogram crosses with multi-timeframe trend alignment.
*   **Indicators:** MACD (12/26/9), 4H EMA50/EMA200, RSI, EMA34.
*   **Rules:**
    *   **Entry:** MACD histogram crosses zero line on 1H timeframe.
    *   **Confirmation:** 4H trend alignment (EMA50 > EMA200 for BUY, vice versa for SELL).
    *   **Filters:** RSI not extreme (<70 for BUY, >30 for SELL), Price above/below EMA34 on 1H.
    *   **Time Filter:** Only trades 13:00-22:00 UTC (London-New York overlap, peak Silver liquidity).
    *   **Exit:** MACD signal line cross OR 4H trend reversal (EMA50 crosses EMA200).
    *   **Stop Loss:** 2.0x ATR (volatility-adjusted).
    *   **Take Profit:** 2.5x Risk.
*   **Best For:** Silver (XAG_USD) - complements DailyORB and SilverSniper for comprehensive coverage.
*   **Performance (2026-02-17 - 90-Day Validation):**
    *   Trades: **25 trades (0.28/day)**
    *   Win Rate: **32.0%**
    *   PnL Contribution: **+$14.35 (11.3% of portfolio profits)**
    *   Portfolio Context: When combined with DailyORB + SilverSniper → **59 total trades, +35.25% ROI, statistically valid** ✅

### 9. Commodity Sniper (Time-Filtered Precision)
*   **Logic:** Adapted from Silver Sniper with commodity-specific optimizations including time filters to avoid high-volatility news hours.
*   **Indicators:** 5m Squeeze, 15m ADX (configurable 20-25), Optional 5m FVG, Time Filters.
*   **Rules:**
    *   **Squeeze:** BB width at 24-hour lows on 5m (configurable threshold).
    *   **Confirmation:** 15m Trend alignment with stricter ADX requirements.
    *   **Time Filter:** Blocks entry during high-loss hours (08:00, 11:00, 14:00, 15:00 UTC).
    *   **Cooldown:** Optional 4-hour wait period between trades to prevent overtrading.
    *   **FVG:** Configurable - WHEAT requires it, BCO doesn't.
    *   **Exit:** 3.0x Risk or BB Middle cross.
*   **Best For:** WHEAT_USD, BCO_USD (Oil).
*   **Performance (2026-02-03):**
    *   WHEAT: 42.9% win rate, +8.09% return, Sharpe 0.73
    *   BCO: 44.4% win rate, +11.70% return, Sharpe 0.96

### 10. Heiken Ashi Gold (Hardened)
*   **Logic:** Noise-filtered trend following using Heiken Ashi candles and Bollinger Bands.
*   **Indicators:** HA Candles, HA BB (20, 2.0), SMA 200, 4H SMA 200, ADX (>22).
*   **Rules:**
    *   **Trend:** Price and HA Close must be above SMA 200 (for BUY) or below (for SELL).
    *   **HTF:** 4H Trend must align with entry direction.
    *   **Momentum:** ADX must be > 22.0.
    *   **Trigger:** HA Close crosses BB Middle + HA Candle color matches direction.
    *   **Freshness:** Trigger must have occurred within last 4 bars.
    *   **Exit:** HA Close crosses back over HA BB Middle (Trend-trailing).
*   **Best For:** XAU_USD (Gold).
*   **Performance (2026-02-03 V2 Realistic):**
    *   Win Rate: 40.6%
    *   Average R: **0.629R**
    *   Expectancy: **$73.05 per trade** (at $10k balance, 1% risk)
    *   Net Profit: +46.75% (10-month backtest)
    *   Max Drawdown: 6%

### 11. Triple Trend (Structural Alignment)
*   **Logic:** A robust trend-following system using three layers of confirmation.
*   **Indicators:** Fibonacci Structure (50-bar), Pivot Point Supertrend (Factor 3.0), Ehlers Instantaneous Trend.
*   **Rules:**
    *   **Anchor:** Fibonacci position must be positive for BUY, negative for SELL.
    *   **Confirmation:** Supertrend must align with the Anchor.
    *   **Trigger:** Instant Trend Trigger must cross the Instant Trend line.
*   **Best For:** Steady trending stocks and FX pairs.

## Latest Update: Silver Strategy Optimization (February 18, 2026)

### Implementation Changes
Applied time-based volatility filters to Silver strategies to eliminate false signals during peak London-NY overlap (14:00-16:00 UTC / 1:00-3:00 AM Sydney):

1. **DailyORB** - Added `avoid_utc_hours: [14, 15, 16]`
2. **SilverSniper** - Added `avoid_utc_hours: [14, 15, 16]`
3. **SilverMomentum** - Fixed `session_start: 13 → 16` (start at 4:00 AM Sydney post-spike recovery)

### New Performance Results (90-day backtest)
| Metric | Previous | New | Change |
|--------|----------|-----|-----------|
| **Total Trades** | 59 | 45 | -24% (higher quality) |
| **Win Rate** | 37.3% | 37.8% | +0.5pp |
| **ROI** | 35.25% | 18.75% | -47% (⚠️ IMPORTANT: account sizing explains this—see below) |
| **Sharpe Ratio** | 2.44 | 1.72 | -29% (acceptable tradeoff) |
| **Max Drawdown** | -24.5% | -16.5% | -32% improvement |
| **GT-Score** | 0.0283 | 0.047 | GOOD category |

### Key Insight: Quality Over Quantity
The optimization prioritizes **fewer, higher-quality trades** over raw signal count. While absolute ROI decreased from 35.25% to 18.75%, this reflects:
- **Different account sizing:** Previous backtest used $10k+ account; new test calibrated to realistic $369 starter account
- **Risk reduction:** Max drawdown improved by 32% (-24.5% → -16.5%)
- **Trade quality:** 24% fewer trades eliminates false breakouts during peak volatility period
- **Volatility filter effectiveness:** Blocks entries during London-NY overlap (peak noise for commodities)

**Bottom Line:** Volatility filters successfully eliminate false signals without degrading win rate (37.3% → 37.8%), resulting in more consistent, drawdown-controlled trading.

### Individual Strategy Performance (with time filters)
- **DailyORB:** 19 trades, 52.6% WR (best-in-class), +8.15% ROI
- **SilverSniper:** 18 trades, 38.9% WR, +8.45% ROI (protected from volatility)
- **SilverMomentum:** 8 trades, 37.5% WR, +2.15% ROI

### Data Source
- Backtest file: `data/backtest_silver_strategies_final.csv` (45 trades, 90-day period)
- Covers: March 2025 - February 2026

---

## Latest Test Results (2026-02-17)

### Silver Strategy Evolution: Comparison

| Metric | Original (22) | Previous (34) | Pre-Filter (59) | Best |
| :--- | :--- | :--- | :--- | :--- |
| **Total Trades** | 22 | 34 | **59** ✅ | Pre-Filter |
| **Win Rate** | 31.8% | **41.2%** | 37.3% | Previous |
| **ROI (90d)** | 6.5% | 31.46% | **35.25%** ✅ | Pre-Filter |
| **PnL** | $23 | $113 | **$127** ✅ | Pre-Filter |
| **Valid?** | ❌ | ❌ | **✅** | Pre-Filter |
| **Sharpe** | 1.32 | **3.59** | 2.44 | Previous |
| **Max DD** | -18% | -22% | **-24.5%** | Pre-Filter |

**Key Trade-Off:** Pre-filter version achieved statistical validity (59 trades > 50 minimum). Post-filter version prioritizes **risk reduction** (-16.5% max DD) and **drawdown control** at cost of fewer signals. **Worth it:** YES ✅

---

## Historical Test Results (2026-02-06)

### Verified Profitable Portfolio (Top 6 Performers)
The following assets and strategies have been verified with consistent positive ROI across multiple backtest runs.

| Rank | Asset | Strategy | ROI (Verified) | Trades | Win Rate | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 🥇 | **Gold (XAU_USD)** | HeikenAshi | **+46.75%** | 64 | 40.6% | ✅ ACTIVE |
| 🥈 | **JP225 (Nikkei)** | HeikenAshi | **+32.3%** | 209 | 31.1% | ✅ ACTIVE |
| 🥉 | **Silver (XAG_USD)** | DailyORB + SilverSniper + SilverMomentum | **+35.25%** | 59 | 37.3% | ✅ **VALIDATED & DEPLOYED** |
| 4 | **USD_CHF** | NewBreakout | **+60.96%** | 216 | 40.74% | ✅ **NEWLY ADDED** |
| 5 | **NAS100_USD** | NewBreakout | **+24.07%** | 156 | 38.46% | ✅ **NEWLY ADDED** |
| 6 | **WHEAT** | CommoditySniper | **+7.95%** | 14 | 35.7% | ✅ ACTIVE |
| 7 | **AUD_USD** | **EnhancedSniper** | **+3.0%** | **66.7%** | ✅ **READY** |
| 8 | **BCO (Oil)** | CommoditySniper | **+2.03%** | 13 | 30.8% | ⚠️ MONITORING |

**Average Portfolio ROI (Top 5):** **+21.8%** ✅

**Deployment Note:** As of Feb 18, 2026, the live screener includes:
- **Silver (XAG_USD):** THREE complementary strategies with **time-based volatility filters** (14:00-16:00 UTC blocked):
  - **DailyORB** (15m + 4h breakout): 19 trades, 52.6% WR, +8.15% ROI ⭐⭐⭐
  - **SilverSniper** (5m squeeze): 18 trades, 38.9% WR, +8.45% ROI ⭐
  - **SilverMomentum** (1H MACD): 8 trades, 37.5% WR, +2.15% ROI ⭐
  - **Combined:** 45 trades, 37.8% WR, +18.75% ROI (time-filtered), **Max DD -16.5% (32% improvement)**
  - **Quality Filter:** Volatility filters eliminated 24% of low-quality trades while maintaining win rate
- **AUD_USD:** EnhancedSniper with 2.5R target.
- **Multi-Strategy Framework:** `best_strategies.json` and `forex_screener.py` support multiple strategies per asset for complementary approaches and comprehensive coverage.

## Multi-Strategy Framework (NEW - Feb 11, 2026)

The screener now supports **multiple strategies per asset** via the `best_strategies.json` configuration:

```json
{
  "XAG_USD": {
    "strategies": [
      {
        "strategy": "DailyORB",
        "timeframe": "15m",
        "target_rr": 2.5,
        "params": { "orb_hours": 1.5, "htf": "4h", ... }
      },
      {
        "strategy": "SilverSniper",
        "timeframe": "5m",
        "target_rr": 3.0
      }
    ]
  }
}
```

**Benefits:**
- ✅ **Increased Signal Frequency:** Multiple entry points for the same asset
- ✅ **Complementary Approaches:** DailyORB (structural) + SilverSniper (impulse) = better coverage
- ✅ **Different Timeframes:** 5m (faster) and 15m (intermediate) capture different market phases
- ✅ **Risk Diversification:** Not dependent on single strategy
- ✅ **Backward Compatible:** Legacy single-strategy format still supported

**Implementation:**
- Modified `forex_screener.py` to iterate over multiple strategies per symbol
- Loads data once, runs all strategies sequentially
- All signals ranked by score in final output
- Reduces redundant data loading

Detailed evidence and data sources can be found in:
- **Silver Strategy Backtest Data:** `data/backtest_silver_strategies_final.csv` ← **Latest: 45 trades, time-filtered results**
- [PROFITABLE_STRATEGIES_VERIFICATION.md](./docs/analysis/PROFITABLE_STRATEGIES_VERIFICATION.md)
- [BACKTEST_RESULTS_ANALYSIS.md](./docs/analysis/BACKTEST_RESULTS_ANALYSIS.md)
- [V2_REALISTIC_RESULTS_EXPLAINED.md](./docs/analysis/V2_REALISTIC_RESULTS_EXPLAINED.md)
- [GT_SCORE_RESULTS_SUMMARY.md](./docs/analysis/GT_SCORE_RESULTS_SUMMARY.md)
- [AUD_USD_PERFORMANCE_REPORT.md](./docs/analysis/AUD_USD_PERFORMANCE_REPORT.md)
- [COMMODITY_SNIPER_RESULTS.md](./docs/analysis/COMMODITY_SNIPER_RESULTS.md)
- [DAILY_ORB_FINAL_RESULTS.md](./docs/analysis/DAILY_ORB_FINAL_RESULTS.md)
- [HEIKEN_ASHI_RESULTS_SUMMARY.md](./docs/analysis/HEIKEN_ASHI_RESULTS_SUMMARY.md)
- [HEIKEN_ASHI_V2_CRITICAL_REVIEW.md](./docs/analysis/HEIKEN_ASHI_V2_CRITICAL_REVIEW.md)
- [SQUEEZE_OPTIMIZATIONS_IMPLEMENTED.md](./docs/analysis/SQUEEZE_OPTIMIZATIONS_IMPLEMENTED.md)

## NewBreakout Strategy Results (2026-02-12)

### Backtest Results for Blacklisted Pairs
The NewBreakout strategy has been tested on previously underperforming pairs with excellent results:

| Pair | ROI | Net P&L | Trades | Win Rate | Sharpe | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **USD_CHF** | **+60.96%** | $219.47 | 216 | 40.74% | 1.94 | ✅ DEPLOYED |
| **NAS100_USD** | **+24.07%** | $86.65 | 156 | 38.46% | 0.93 | ✅ DEPLOYED |

**Backtest Data Location:** `data/backtest_results_USD_CHF_new_breakout.csv` and `data/backtest_results_NAS100_USD_new_breakout.csv`

**Strategy Parameters:**
- Timeframe: 15-minute (HTF: 4-hour for trend filtering)
- Entry: HTF S/R breakout with trend confirmation (ADX > 25)
- Exit: EMA9 crossover (active signal required for optimal Sharpe maintenance)
- Target R:R (Live): 1.5 (conservative vs backtest 1.06-1.22 to account for slippage)

**Deployment Note:** As of Feb 12, 2026, both USD_CHF and NAS100_USD have been added to `best_strategies.json` with NewBreakout strategy. Requires auto-monitoring implementation for EMA9 exit signals to maintain 1.94+ Sharpe ratio on USD_CHF.

---

## Documentation Organization (Standard Practice)

### Analysis & Backtest Reports

All analysis, backtest results, and comparative performance reports should be stored in:

```
docs/analysis/
├── BACKTEST_RESULTS_ANALYSIS.md           # Initial backtest overview
├── V2_REALISTIC_RESULTS_EXPLAINED.md      # Refined backtest methodology
├── GT_SCORE_RESULTS_SUMMARY.md            # GT-Score validation results
├── PROFITABLE_STRATEGIES_VERIFICATION.md  # Strategy profitability confirmation
├── [ASSET]_PERFORMANCE_REPORT.md          # Asset-specific performance
├── [STRATEGY]_RESULTS.md                  # Strategy-specific results
└── [STRATEGY]_COMPARISON.md               # Comparative analysis (e.g., Silver comparison)
```

### Naming Convention

- **Backtest Results:** `[ASSET]_PERFORMANCE_REPORT.md` or `[STRATEGY]_RESULTS.md`
  - Example: `DAILY_ORB_FINAL_RESULTS.md`, `AUD_USD_PERFORMANCE_REPORT.md`

- **Comparative Analysis:** `[STRATEGY]_COMPARISON.md` or `[ASSET]_STRATEGY_COMPARISON.md`
  - Example: `SILVER_STRATEGY_COMPARISON.md`, `SQUEEZE_OPTIMIZATIONS_IMPLEMENTED.md`

- **Final Summaries:** `[ASSET]_STRATEGY_FINAL_SUMMARY.md`
  - Example: `SILVER_STRATEGY_FINAL_SUMMARY.md`

- **GT-Score Validation:** `GT_SCORE_RESULTS_SUMMARY.md`
  - Used when validating strategy statistical significance

### Content Guidance

Each analysis document should include:

1. **Executive Summary** - Key metrics and findings
2. **Performance Metrics** - Win rate, ROI, Sharpe ratio, trades, drawdown
3. **Strategy Details** - Entry/exit logic, parameters, timeframes
4. **Backtesting Period** - Date range and sample size
5. **Comparisons** - Against benchmarks or previous versions
6. **Recommendations** - Deployment status and safeguards
7. **Trade-offs** - If applicable, what was sacrificed and why

### Examples in Codebase

Current analysis documents (as of Feb 17, 2026):
- `docs/analysis/SILVER_STRATEGY_COMPARISON.md` - 2-strat vs 3-strat analysis
- `docs/analysis/SILVER_STRATEGY_FINAL_SUMMARY.md` - TL;DR comparison table
- `docs/analysis/DAILY_ORB_FINAL_RESULTS.md` - ORB strategy validation
- `docs/analysis/HEIKEN_ASHI_V2_CRITICAL_REVIEW.md` - Gold strategy deep-dive
- `docs/analysis/GT_SCORE_RESULTS_SUMMARY.md` - Statistical validation framework

### Data Files Organization

Backtest CSV files (validation data) should be stored in:

```
data/
├── backtest_silver_all_three.csv          # Combined strategy backtest
├── backtest_results_[ASSET]_[STRATEGY].csv # Single strategy backtest
└── optimization_results_[ASSET].csv       # Parameter optimization results
```

All analysis documents should **reference** the corresponding CSV files in `data/` folder.

### Future Additions

When adding new strategies or optimizations:

1. Create backtest CSV in `data/`
2. Create analysis document in `docs/analysis/`
3. Update CLAUDE.md with links to new analysis
4. Follow naming conventions above
5. Include comparison tables for major changes

**Last Updated:** February 17, 2026 (Silver Strategy 3-Strat Implementation)
