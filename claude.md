# ASX Stock Screener - Project Context

## Project Overview
The ASX Stock Screener is a full-stack application designed to identify trading opportunities on the Australian Securities Exchange (ASX) and Global Forex/Commodity markets. It uses a **Dynamic Strategy Selection** engine to apply the most effective algorithm for each asset class.

The system implements eight core trading strategies:
1.  **Trend Following** (ADX/DI)
2.  **Mean Reversion** (Bollinger Bands/RSI)
3.  **Squeeze** (Volatility Compression Breakout)
4.  **Sniper** (15m Execution with 1H Confirmation for Forex Majors)
5.  **Enhanced Sniper** (Optimized Forex Precision with 4H Trend Alignment)
6.  **Silver Sniper** (High-Precision 5m Squeeze + FVG for Silver)
7.  **Commodity Sniper** (Optimized 5m Squeeze + Time Filters for Commodities)
8.  **Triple Trend** (Fibonacci + Supertrend + Instant Trend)

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

### 7. Commodity Sniper (Time-Filtered Precision)
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

### 8. Heiken Ashi Gold (Hardened)
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

### 9. Triple Trend (Structural Alignment)
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
| 🥉 | **Silver (XAG_USD)** | SilverSniper | **+19.02%** | 9 | 55.6% | ✅ ACTIVE |
| 4 | **WHEAT** | CommoditySniper | **+7.95%** | 14 | 35.7% | ✅ ACTIVE |
| 5 | **AUD_USD** | **EnhancedSniper** | **+3.0%** | **66.7%** | ✅ **READY** |
| 6 | **BCO (Oil)** | CommoditySniper | **+2.03%** | 13 | 30.8% | ⚠️ MONITORING |

**Average Portfolio ROI (Top 5):** **+21.8%** ✅

**Deployment Note:** As of Feb 6, 2026, the live screener whitelist includes these 6 assets. AUD_USD has been upgraded to EnhancedSniper with 2.5R target.

Detailed evidence and data sources can be found in:
- [FOREX_SNIPER_OPTIMIZATION_RESULTS.md](./FOREX_SNIPER_OPTIMIZATION_RESULTS.md)
- [PROFITABLE_STRATEGIES_VERIFICATION.md](./PROFITABLE_STRATEGIES_VERIFICATION.md)
- [BACKTEST_RESULTS_ANALYSIS.md](./BACKTEST_RESULTS_ANALYSIS.md)
- [V2_REALISTIC_RESULTS_EXPLAINED.md](./V2_REALISTIC_RESULTS_EXPLAINED.md)
