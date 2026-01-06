# ASX Stock Screener - Project Context

## Project Overview
The ASX Stock Screener is a full-stack application designed to identify trading opportunities on the Australian Securities Exchange (ASX). It implements dual trading strategies: **Trend Following** (based on ADX/DI) and **Mean Reversion** (based on Bollinger Bands/RSI). The core calculation logic matches **Pine Script** (TradingView) standards, particularly using "Wilder's Smoothing" for technical accuracy.

## Tech Stack

### Backend
*   **Framework:** FastAPI (Python 3.10+)
*   **Data Processing:** Pandas, NumPy
*   **Data Source:** `yfinance` (Yahoo Finance)
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
│   │   │   ├── signal_detector.py      # Trend Following logic
│   │   │   ├── mean_reversion_detector.py # Mean Reversion logic
│   │   │   └── screener.py             # Analysis orchestrator
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
│   └── metadata/            # Stock lists (ASX200)
├── scripts/
│   └── download_data.py     # Independent data fetcher
└── start.py                 # Unified startup script
```

## Trading Strategies

### 1. Trend Following (ADX/DI)
*   **Logic:** Identifies strong directional trends.
*   **Indicators:** ADX (Trend strength), DI+ / DI- (Direction).
*   **Signals:**
    *   **Entry:** ADX > 30 AND DI+ > DI-
    *   **Exit:** 15% Profit OR DI+ crosses below DI- (Trend reversal)
*   **Smoothing:** Uses **Wilder's Smoothing** (EMA with `alpha=1/period`).

### 2. Mean Reversion (BB/RSI)
*   **Logic:** Identifies overbought conditions expecting a return to the mean.
*   **Indicators:** Bollinger Bands (Volatility/Extreme Price), RSI (Momentum).
*   **Signals:**
    *   **Entry:** Price > Upper Bollinger Band AND RSI > 70
    *   **Exit:** Price returns to Middle Bollinger Band (Mean) OR 7% Profit Target.

## Key Workflows

### 1. Data Pipeline
*   **Download:** `scripts/download_data.py` fetches 2 years of daily OHLC data.
*   **Analysis:** `app.services.screener` orchestrates both detectors, scoring signals on a 0-100 scale based on signal strength and trend alignment.

### 2. Authentication & Portfolio
*   **Frontend:** Uses Google OAuth to get an ID token.
*   **Backend:** Verifies token via Firebase Admin SDK and stores portfolios in Firestore (`users` collection).

## Building and Running

### Prerequisites
*   Python 3.10+, Node.js 18+, Firebase Project (Firestore enabled).

### Configuration
Requires three sensitive files (gitignored):
1.  `backend/serviceAccountKey.json`: Firebase Admin credentials.
2.  `backend/.env`: `GOOGLE_CLIENT_ID=...`
3.  `frontend/.env`: `VITE_GOOGLE_CLIENT_ID=...`

### Unified Startup
```bash
python start.py
```
*   **Backend:** `http://localhost:8000` (Docs at `/docs`)
*   **Frontend:** `http://localhost:5173`

## Development Conventions
*   **Frontend Vars:** Must start with `VITE_` to be exposed by Vite.
*   **API Proxy:** `vite.config.js` proxies `/api` and `/auth` to the backend.
*   **Data Freshness:** Automatically checked on startup (>7 days = refresh).