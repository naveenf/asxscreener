# ASX Stock Screener

ADX/DI-based stock screening application for Australian Securities Exchange (ASX) stocks.

## Getting Started

### 1. Prerequisites & Configuration

To run the application on a new system, you must provide the following configuration files:

#### Backend Configuration
- **File**: `backend/serviceAccountKey.json`
  - Generate this from the [Firebase Console](https://console.firebase.google.com) (Project Settings > Service Accounts > Generate new private key).
- **File**: `backend/.env`
  - Content:
    ```ini
    GOOGLE_CLIENT_ID=your_google_client_id_here
    ```

#### Frontend Configuration
- **File**: `frontend/.env`
  - Content:
    ```ini
    VITE_GOOGLE_CLIENT_ID=your_google_client_id_here
    ```

### 2. Startup

The application uses a unified startup script that manages the backend, frontend, and data freshness automatically.

From the project root directory, run:

```bash
python start.py
```

This script will:
1. Verify all prerequisites and dependencies.
2. Download fresh ASX stock data if needed.
3. Start the FastAPI Backend (Port 8000).
4. Start the Vite Frontend (Port 5173).
5. Automatically open your default web browser to the application.

### 3. Access
- **Frontend UI:** http://localhost:5173
- **Backend API Docs:** http://localhost:8000/docs

## API Endpoints

**GET /api/signals** - Get current signals
Query params: `min_score` (0-100), `sort_by` (score|adx|ticker)

**GET /api/stocks/{ticker}** - Get specific stock detail

**GET /api/status** - Get screener status

**POST /api/refresh** - Trigger data refresh

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

## Frontend Features

- ✅ Real-time signal display
- ✅ Score-based color coding (Green: 70+, Orange: 50-70, Gray: <50)
- ✅ Minimum score filter (slider)
- ✅ Auto-refresh every 5 minutes
- ✅ Manual refresh button
- ✅ Responsive design

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

### Features

- **Persistent Portfolio**: Your stocks, buy dates, and transaction details are saved in the cloud.

- **Cross-Device Sync**: Log in with the same Gmail on any computer to see your portfolio.

- **Google Login**: Secure authentication without needing a new password.



## Strategy Validation Standards (GT-Score)



To reduce overfitting and ensure robust performance in live trading, we use the **GT-Score** composite objective function (published 2026) for strategy validation.



### The Formula

`GT-Score = (μ · ln(z) · r²) / σ_d`



| Component | Description |

|-----------|-------------|

| **μ (Mean Return)** | Average return per trade. |

| **ln(z)** | Statistical significance gate (outperformance vs noise). |

| **r² (Consistency)** | Measures equity curve smoothness. |

| **σ_d (Downside Risk)** | Penalizes only losing trades, not upside volatility. |



### Interpretation

- **> 0.10**: Excellent — strong, consistent, statistically significant edge.

- **0.05 - 0.10**: Good — reliable strategy with room for optimization.

- **0.01 - 0.05**: Viable — edge exists but may be fragile.

- **< 0.00**: Poor — likely overfit or underperforming.



**Validation Requirement:** A minimum of **50 trades** is required for a valid GT-Score. Strategies with fewer trades are marked as "INSUFFICIENT DATA".



### Tools

Use the provided CLI tool to analyze any backtest CSV:

```bash

python scripts/calculate_gt_score.py data/your_backtest_results.csv

```
