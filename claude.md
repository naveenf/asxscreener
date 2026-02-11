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
    *   **Take Profit:** 2.5x Risk (conservative for structural breakouts).
    *   **Exit:** On HTF trend reversal (DI flip) or weakness (ADX < 20).
*   **Best For:** Silver (XAG_USD) - complements impulse-driven SilverSniper strategy.
*   **Performance (2026-02-11):**
    *   Win Rate: **58.3%** (exceeds SilverSniper's 55.6%)
    *   ROI: **+27.19%** (exceeds SilverSniper's 19.02% by 43%)
    *   Sharpe: **1.99** (exceptional risk-adjusted returns)
    *   Max Drawdown: **-2.0%** (minimal capital drawdown)
    *   Sample: 12 trades (7 wins) over 4-month backtest.

### 8. Commodity Sniper (Time-Filtered Precision)
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

### 9. Heiken Ashi Gold (Hardened)
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

### 10. Triple Trend (Structural Alignment)
*   **Logic:** A robust trend-following system using three layers of confirmation.
*   **Indicators:** Fibonacci Structure (50-bar), Pivot Point Supertrend (Factor 3.0), Ehlers Instantaneous Trend.
*   **Rules:**
    *   **Anchor:** Fibonacci position must be positive for BUY, negative for SELL.
    *   **Confirmation:** Supertrend must align with the Anchor.
    *   **Trigger:** Instant Trend Trigger must cross the Instant Trend line.
*   **Best For:** Steady trending stocks and FX pairs.

## Latest Test Results (2026-02-06)

### Verified Profitable Portfolio (Top 6 Performers)
The following assets and strategies have been verified with consistent positive ROI across multiple backtest runs.

| Rank | Asset | Strategy | ROI (Verified) | Trades | Win Rate | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 🥇 | **Gold (XAU_USD)** | HeikenAshi | **+46.75%** | 64 | 40.6% | ✅ ACTIVE |
| 🥈 | **JP225 (Nikkei)** | HeikenAshi | **+32.3%** | 209 | 31.1% | ✅ ACTIVE |
| 🥉 | **Silver (XAG_USD)** | DailyORB + SilverSniper | **+27.19%** (ORB) | 12+9 | 58.3% + 55.6% | ✅ **DUAL ACTIVE** |
| 4 | **WHEAT** | CommoditySniper | **+7.95%** | 14 | 35.7% | ✅ ACTIVE |
| 5 | **AUD_USD** | **EnhancedSniper** | **+3.0%** | **66.7%** | ✅ **READY** |
| 6 | **BCO (Oil)** | CommoditySniper | **+2.03%** | 13 | 30.8% | ⚠️ MONITORING |

**Average Portfolio ROI (Top 5):** **+21.8%** ✅

**Deployment Note:** As of Feb 11, 2026, the live screener whitelist includes these 6 assets with multi-strategy support:
- **Silver (XAG_USD):** Now uses BOTH DailyORB (15m + 4h, +27.19% ROI) and SilverSniper (5m + 15m, +19.02% ROI) in parallel for increased signal frequency and coverage.
- **AUD_USD:** Upgraded to EnhancedSniper with 2.5R target.
- **Multi-Strategy Framework:** `best_strategies.json` and `forex_screener.py` updated to support multiple strategies per asset, enabling complementary approaches.

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
- [FOREX_SNIPER_OPTIMIZATION_RESULTS.md](./FOREX_SNIPER_OPTIMIZATION_RESULTS.md)
- [PROFITABLE_STRATEGIES_VERIFICATION.md](./PROFITABLE_STRATEGIES_VERIFICATION.md)
- [BACKTEST_RESULTS_ANALYSIS.md](./BACKTEST_RESULTS_ANALYSIS.md)
- [V2_REALISTIC_RESULTS_EXPLAINED.md](./V2_REALISTIC_RESULTS_EXPLAINED.md)
