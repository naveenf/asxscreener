# ASX Stock Screener - Project Context

## Project Overview
The ASX Stock Screener is a full-stack application designed to identify trading opportunities on the Australian Securities Exchange (ASX) and Global Forex/Commodity markets. It uses a **Dynamic Strategy Selection** engine to apply the most effective algorithm for each asset class.

The system implements five core trading strategies:
1.  **Trend Following** (ADX/DI)
2.  **Mean Reversion** (Bollinger Bands/RSI)
3.  **Squeeze** (Volatility Compression Breakout)
4.  **Silver Sniper / Sniper** (High-Precision 5m Squeeze + FVG)
5.  **Triple Trend** (Fibonacci + Supertrend + Instant Trend)

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
│   │   │   ├── triple_trend_detector.py# Triple Confirmation logic (Fib+Supertrend)
│   │   │   ├── sniper_detector.py      # Legacy Sniper logic
│   │   │   └── forex_screener.py       # Dynamic Strategy Orchestrator
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

### 4. Silver Sniper / Sniper (Intraday Momentum)
*   **Logic:** Identifies high-probability breakouts on lower timeframes by aligning with higher timeframe trends and institutional order blocks (FVG).
*   **Indicators:** 5m Squeeze, 15m ADX (>20), 5m Fair Value Gap (FVG).
*   **Rules:**
    *   **Squeeze:** BB width at 24-hour lows on 5m.
    *   **Confirmation:** 15m Trend must match breakout direction.
    *   **Mitigation:** Entry must occur within a recent 5m FVG (Order Block confirmation).
    *   **Exit:** 3.0x Risk (Fixed) or BB Middle cross.
*   **Best For:** Silver (XAG_USD), Oil (BCO_USD), Wheat.

### 5. Triple Trend (Structural Alignment)
*   **Logic:** A robust trend-following system using three layers of confirmation.
*   **Indicators:** Fibonacci Structure (50-bar), Pivot Point Supertrend (Factor 3.0), Ehlers Instantaneous Trend.
*   **Rules:**
    *   **Anchor:** Fibonacci position must be positive for BUY, negative for SELL.
    *   **Confirmation:** Supertrend must align with the Anchor.
    *   **Trigger:** Instant Trend Trigger must cross the Instant Trend line.
*   **Best For:** Steady trending stocks and FX pairs.

## Latest Test Results (2026-01-30)

### Sniper Optimization (M5 Base, M15 HTF)
*   **XAG_USD (Silver):** Optimized for **5m** with RR 3.0. Win Rate: **66.7%** (SilverSniper strategy).
*   **BCO_USD (Oil):** Optimized for **5m** with RR 3.0. (Sniper strategy).
*   **WHEAT_USD:** Optimized for **5m** with RR 3.0. (Sniper strategy).

### 1H Squeeze Algo Optimization (Multiplier 1.2)
| Symbol | Best RR | Profit (Units) | Status |
| :--- | :--- | :--- | :--- |
| **XAU_USD (Gold)** | 3.0 | **+7.9** | **Top Performer** |
| **XCU_USD (Copper)** | 2.0 | **+6.1** | **Strong Profit** |
| **AUD_USD** | 1.5 | +2.2 | Consistent |
| **USD_JPY** | 1.5 | -1.2 | Defensive |
| **UK100_GBP** | 2.0 | **+2.1** | Profitable |


## Key Workflows

### 1. Backtest Arena & Optimization
*   **Engine:** `scripts/backtest_arena.py` runs all strategies against all pairs using 15m, 1h, and 4h data.
*   **Optimization:** Determines the best algorithm and timeframe for each specific pair.
*   **Result:** Generates `data/metadata/best_strategies.json`.

### 2. Dynamic Live Screening
*   **Orchestrator:** `app.services.forex_screener.py` loads `best_strategies.json`.
*   **Execution:** 
    *   Loads specific "Base" timeframe (e.g., Silver 1H, Nasdaq 15M).
    *   Applies the designated strategy (e.g., Squeeze).
    *   Checks "HTF" (Higher Timeframe) for trend confirmation.
*   **Refresh Logic (NEW):**
    *   **Asynchronous Processing:** Long-running downloads and screening tasks move to non-blocking background threads via FastAPI `BackgroundTasks`.
    *   **Automated Scheduling:** 
        *   **High-Frequency Sniper:** Refreshes every 5 minutes (at :00, :05, :10...) for Silver, Oil, and Wheat.
        *   **Forex Universe:** Refreshes every 15 minutes (at :01, :16, :31, :46) to capture closed candles.
        *   **ASX Stocks:** Refreshes daily at 18:00 AEST once EOD data is available.
    *   **Portfolio Instant Price:** Individual holdings can be updated on-demand with a 1-minute server-side cache to prevent API throttling.
    *   **UI Feedback:** Real-time polling of refresh status with Toast notifications upon completion.

### 3. Oanda Auto-Trading Bot
*   **Orchestrator:** `app.services.oanda_trade_service.py` executes trades for authorized users.
*   **Execution Rules:**
    *   **Risk Management:** 2% risk of AUD balance per trade.
    *   **Position Sizing:** Margin-aware calculation; capped at 50% of available margin.
    *   **Source of Truth:** **Oanda is the Absolute Source of Truth**. The bot fetches live open trades directly from the API.
    *   **Firestore Sync (NEW):** If Firestore shows a trade as `OPEN` but Oanda says it is closed (e.g., manual intervention), the bot automatically syncs Firestore to `CLOSED` to maintain data integrity.
    *   **Trade Protection:** Every order includes hard Stop Loss and Take Profit (GTC) with Fill-or-Kill (FOK) execution.
    *   **Ranking:** Prioritizes trades based on Backtest performance score.
*   **Supported User:** naveenf.opt@gmail.com.

### 4. Email Notifications
*   **Service:** `app.services.notification.py` sends HTML alerts via SMTP.
*   **Smart Diff Logic:** Only notifies users of *new* signals or *exits* to prevent spam.
*   **Rich Content:** Includes Entry, SL, TP, and Strategy name for new signals; PnL and R:R achieved for exits.

### 5. Data Pipeline
*   **Download:** `scripts/download_data.py` (Stocks) and `scripts/download_forex.py` (Forex/Commodities).
*   **Freshness:** Checked automatically on startup (>1 day old = refresh).

## Building and Running

### Prerequisites
*   Python 3.10+, Node.js 18+, Firebase Project (Firestore enabled).

### Unified Startup
```bash
python start.py
```
*   **Backend:** `http://localhost:8000` (Docs at `/docs`)
*   **Frontend:** `http://localhost:5173`

### Configuration Files (Gitignored)
1.  `backend/serviceAccountKey.json`: Firebase Admin credentials.
2.  `backend/.env`: `GOOGLE_CLIENT_ID=...`
3.  `frontend/.env`: `VITE_GOOGLE_CLIENT_ID=...`
