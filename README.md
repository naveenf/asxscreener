# ASX Stock Screener

ADX/DI-based stock screening application for Australian Securities Exchange (ASX) stocks.

## What's Been Built

### ✅ Phase 1-4 Complete

**Data Pipeline:**
- ✅ Downloads historical data from Yahoo Finance
- ✅ 10 test stocks across mixed sectors (Banking, Mining, Healthcare, Retail, Tech, Telecom, Real Estate)
- ✅ 508 rows per stock (2 years of daily data)

**Indicator Engine:**
- ✅ ADX/DI calculations (matches Pine Script exactly using Wilder's smoothing)
- ✅ 200 SMA calculation
- ✅ Crossover detection

**Signal Detection:**
- ✅ Entry logic: ADX > 30 AND DI+ > DI-
- ✅ Exit logic: 15% profit OR DI+ crosses below DI-
- ✅ Scoring algorithm (0-100 scale)

**Backend API:**
- ✅ FastAPI REST API
- ✅ Auto-generated docs at /docs
- ✅ CORS enabled for React frontend

## Current Status

**Found 1 BUY Signal:**
- **NAB** (National Australia Bank) - Score: 67.6/100
  - Price: $42.24
  - ADX: 30.9 ✓
  - DI+: 26.5 > DI-: 13.5 ✓
  - Above 200 SMA ✓

## Quick Start

### Backend Setup

```bash
# Navigate to backend
cd backend

# Activate virtual environment
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start API server
uvicorn app.main:app --reload --port 8000
```

### API Endpoints

**GET /api/signals** - Get current signals
Query params: `min_score` (0-100), `sort_by` (score|adx|ticker)

**GET /api/stocks/{ticker}** - Get specific stock detail

**GET /api/status** - Get screener status

**POST /api/refresh** - Trigger data refresh

**Docs:** http://localhost:8000/docs

### Run Screener Manually

```bash
cd backend
./venv/bin/python3 -m app.services.screener
```

## Trading Strategy

**Entry Conditions:**
1. ADX crosses above 30 (trend strength)
2. DI+ (green) > DI- (red) (bullish trend)

**Exit Conditions:**
1. 15% Take Profit
2. OR DI+ crosses below DI- (trend reversal)

**Scoring (0-100):**
- Base: 50
- ADX strength bonus: 0-25
- DI spread bonus: 0-15
- Above SMA200: +10
- Fresh crossover: +5

## Project Structure

```
asx-screener/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # REST endpoints
│   │   ├── main.py                # FastAPI app
│   │   ├── config.py              # Settings
│   │   ├── models/stock.py        # Pydantic models
│   │   └── services/
│   │       ├── indicators.py      # ADX/DI calculations
│   │       ├── signal_detector.py # Signal logic
│   │       └── screener.py        # Orchestrator
│   └── requirements.txt
├── data/
│   ├── raw/                       # CSV files (10 stocks)
│   ├── processed/
│   │   └── signals.json           # Latest signals
│   └── metadata/
│       └── stock_list.json        # Stock definitions
└── scripts/
    └── download_data.py           # Data downloader
```

## Test Stocks (10)

1. **CBA.AX** - Commonwealth Bank (Financials)
2. **NAB.AX** - National Australia Bank (Financials) ⭐ BUY SIGNAL
3. **BHP.AX** - BHP Group (Materials)
4. **FMG.AX** - Fortescue Metals (Materials)
5. **CSL.AX** - CSL Limited (Healthcare)
6. **WES.AX** - Wesfarmers (Consumer Staples)
7. **WOW.AX** - Woolworths (Consumer Staples)
8. **WTC.AX** - WiseTech Global (Technology)
9. **TLS.AX** - Telstra (Telecommunication)
10. **GMG.AX** - Goodman Group (Real Estate)

## Frontend Setup

### Install Dependencies

```bash
cd frontend
npm install
```

### Start Frontend Development Server

```bash
cd frontend
npm run dev
```

Frontend will be available at: **http://localhost:5173**

### Frontend Features

- ✅ Real-time signal display
- ✅ Score-based color coding (Green: 70+, Orange: 50-70, Gray: <50)
- ✅ Minimum score filter (slider)
- ✅ Auto-refresh every 5 minutes
- ✅ Manual refresh button
- ✅ Responsive design

## Running the Complete Application

### Terminal 1: Backend API
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Terminal 2: Frontend
```bash
cd frontend
npm run dev
```

### Access
- **Frontend UI:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

## Next Steps

### Phase 6: Testing (Current)
- End-to-end pipeline testing
- Manual verification against TradingView
- UI/UX testing

### Phase 7: Scale to 200 Stocks
- Add remaining 190 ASX stocks
- Performance optimization
- Scheduled refresh (every 4 hours)
- Deploy to production

## Technical Details

**ADX Calculation:**
- Uses Wilder's smoothing (EMA with alpha=1/period)
- Matches Pine Script implementation exactly
- Period: 14 (default)

**Data Source:**
- Yahoo Finance (free)
- Daily data (1d interval)
- 2 years of history

**Scoring Example (NAB):**
```
Base score: 50
+ ADX bonus: (30.9 - 30) * 1.25 = 1.13
+ DI spread: (26.5 - 13.5) * 0.5 = 6.5
+ Above SMA200: 10
+ Fresh crossover: 0
Total: 67.63 ≈ 67.6
```

## Cloud Sync & Portfolio (New)

The application now supports user portfolios synchronized across devices using Google Firebase.

### Setup Instructions

1.  **Google OAuth**:
    *   Set `GOOGLE_CLIENT_ID` in `backend/.env`.
2.  **Firebase Database**:
    *   Create a Firebase project at [console.firebase.google.com](https://console.firebase.google.com).
    *   Enable **Firestore Database**.
    *   Go to **Project Settings > Service Accounts** and generate a new private key.
    *   Save the JSON file as `backend/serviceAccountKey.json`.

### Features
- **Persistent Portfolio**: Your stocks, buy dates, and transaction details are saved in the cloud.
- **Cross-Device Sync**: Log in with the same Gmail on any computer to see your portfolio.
- **Google Login**: Secure authentication without needing a new password.
