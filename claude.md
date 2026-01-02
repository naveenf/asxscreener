# Claude Context - ASX Stock Screener

**Purpose:** This file provides complete context for AI assistants working on this project.

**Last Updated:** 2026-01-02

---

## Project Overview

### What This Application Does

An automated stock screening system for the Australian Securities Exchange (ASX) that identifies trading opportunities based on ADX (Average Directional Index) and Directional Indicator (DI) technical analysis.

**Core Function:** Scan ASX stocks daily, calculate technical indicators, detect buy/sell signals, score them, and display results via a web UI.

### Current Status

- **Phase 1-5:** Complete ✓
- **Stocks Tracked:** 10 (test set)
- **Target:** ASX Top 200
- **Data Source:** Yahoo Finance (free, daily OHLC)
- **Found Signals:** 1 (NAB.AX - Score: 67.6/100)

---

## Trading Strategy (Critical - Do Not Change Without User Approval)

### Entry Conditions (ALL must be true)

1. **ADX > 30** - Trend strength threshold
   - ADX measures trend strength (0-100 scale)
   - Below 30 = weak/no trend
   - Above 30 = strong trend (tradeable)

2. **DI+ > DI-** - Bullish trend confirmation
   - DI+ (green line) = upward pressure
   - DI- (red line) = downward pressure
   - DI+ > DI- = bulls in control

### Exit Conditions (Either triggers exit)

1. **15% Profit Target** - Price reaches entry_price * 1.15
2. **Trend Reversal** - DI+ crosses below DI- (bears take control)

### Scoring Algorithm (0-100)

**Purpose:** Rank signals by strength/quality

```
Base Score: 50

Bonuses:
+ ADX Strength:     0-25 points  (higher ADX = stronger trend)
                    Formula: min((ADX - 30) * 1.25, 25)

+ DI Spread:        0-15 points  (bigger gap = clearer signal)
                    Formula: min((DI+ - DI-) * 0.5, 15)

+ Above SMA200:     +10 points   (bullish context)

+ Fresh Crossover:  +5 points    (DI+ just crossed above DI-)

Maximum: 100 points
```

**Score Interpretation:**
- 70-100: Strong signal (green)
- 50-69: Medium signal (orange)
- 0-49: Weak signal (gray)

### Why This Strategy?

**Original Source:** Pine Script indicator (provided by user in `pinescript_adx_di.txt`)

**Key Principle:** Trend following
- Enter when strong trend confirmed (ADX > 30 + DI+ > DI-)
- Exit when trend weakens or profit target hit
- Works on any timeframe (currently using daily)

---

## Technical Architecture

### Tech Stack

**Backend:**
- Python 3.13
- FastAPI (REST API framework)
- Pandas/NumPy (data processing)
- yfinance (Yahoo Finance API client)
- Pydantic (data validation)
- Uvicorn (ASGI server)

**Frontend:**
- React 18
- Vite (build tool)
- Vanilla CSS (no framework)
- Native fetch API (no axios)

**Data Storage:**
- CSV files (raw stock data)
- JSON files (processed signals)
- No database (simple file-based)

### Project Structure

```
asx-screener/
├── backend/                    # Python FastAPI backend
│   ├── app/
│   │   ├── main.py            # FastAPI application entry point
│   │   ├── config.py          # Settings (periods, thresholds, paths)
│   │   │
│   │   ├── services/          # Core business logic
│   │   │   ├── indicators.py      # ADX/DI/SMA calculations
│   │   │   ├── signal_detector.py # Entry/exit logic + scoring
│   │   │   └── screener.py        # Orchestrator (main loop)
│   │   │
│   │   ├── api/
│   │   │   └── routes.py      # REST endpoints
│   │   │
│   │   └── models/
│   │       └── stock.py       # Pydantic models for API
│   │
│   ├── tests/                 # Unit tests (not implemented yet)
│   ├── venv/                  # Python virtual environment
│   └── requirements.txt       # Python dependencies
│
├── frontend/                  # React frontend
│   ├── src/
│   │   ├── main.jsx          # React entry point
│   │   ├── App.jsx           # Main app component
│   │   │
│   │   ├── components/
│   │   │   ├── Header.jsx        # Header with status/refresh
│   │   │   ├── SignalList.jsx    # List container + filters
│   │   │   └── SignalCard.jsx    # Individual signal card
│   │   │
│   │   └── services/
│   │       └── api.js        # API client (fetch wrapper)
│   │
│   ├── index.html            # HTML template
│   ├── package.json          # NPM dependencies
│   └── vite.config.js        # Vite configuration (proxy)
│
├── data/
│   ├── raw/                  # CSV files (one per stock)
│   │   ├── CBA.AX.csv
│   │   ├── NAB.AX.csv
│   │   └── ...
│   │
│   ├── processed/
│   │   └── signals.json      # Latest screening results
│   │
│   └── metadata/
│       └── stock_list.json   # List of stocks to track
│
├── scripts/
│   └── download_data.py      # Data fetcher (Yahoo Finance)
│
├── README.md                 # User documentation
├── QUICKSTART.md            # Quick start guide
└── claude.md                # This file
```

---

## Data Flow

### 1. Data Download (Manual/Scheduled)

```
User runs: python scripts/download_data.py
    ↓
Reads: data/metadata/stock_list.json
    ↓
For each stock:
    - Fetches from Yahoo Finance (yfinance library)
    - Downloads 2 years of daily OHLC data
    - Saves to data/raw/{TICKER}.csv
```

**CSV Format:**
```csv
Date,Open,High,Low,Close,Volume,Dividends,Stock Splits
2024-01-02 00:00:00+11:00,104.71,106.36,104.66,106.36,1628690,0.0,0.0
```

### 2. Indicator Calculation

```
User triggers screening (UI refresh or python -m app.services.screener)
    ↓
For each stock CSV:
    - Load into pandas DataFrame
    - Calculate True Range
    - Calculate Directional Movement (DM+ and DM-)
    - Apply Wilder's smoothing (EMA with alpha=1/14)
    - Calculate DI+ and DI- (smoothed DM / smoothed TR * 100)
    - Calculate DX (|DI+ - DI-| / (DI+ + DI-) * 100)
    - Calculate ADX (SMA of DX over 14 periods)
    - Calculate SMA200 (simple moving average of Close)
```

### 3. Signal Detection

```
For each stock with calculated indicators:
    ↓
Check entry conditions:
    - Is ADX > 30? (trend strength)
    - Is DI+ > DI-? (bullish direction)
    ↓
If YES:
    - Calculate score (0-100)
    - Create signal object
    - Add to signals list
    ↓
If NO:
    - Skip this stock
```

### 4. Output Generation

```
Sort signals by score (highest first)
    ↓
Save to: data/processed/signals.json
    ↓
Return to API caller
```

### 5. Frontend Display

```
React app polls: GET /api/signals
    ↓
Receives JSON array of signals
    ↓
Renders SignalCard for each signal:
    - Color-coded score badge
    - Indicator values (ADX, DI+, DI-)
    - Badges (Above SMA200, Strong Trend, etc.)
```

---

## Critical Implementation Details

### ADX Calculation (MUST match Pine Script exactly)

**Why Critical:** User's strategy is based on specific Pine Script indicator. Calculations must match exactly or signals will be wrong.

**Key Points:**

1. **Wilder's Smoothing (NOT simple average)**
   ```python
   # CORRECT (Wilder's method):
   smoothed = series.ewm(alpha=1/period, adjust=False).mean()

   # WRONG (simple moving average):
   smoothed = series.rolling(period).mean()
   ```

2. **Implementation in `backend/app/services/indicators.py`:**
   ```python
   def calculate_adx(df, period=14):
       # Step 1: True Range
       # Step 2: Directional Movement
       # Step 3: Wilder's smoothing
       # Step 4: DI+ and DI- calculation
       # Step 5: DX calculation
       # Step 6: ADX (SMA of DX)
   ```

3. **Validation:** Compare output with TradingView using same stock and timeframe. Values should match within 0.1-0.5 due to rounding.

### Data Source Constraints

**Current:** Daily data from Yahoo Finance (`interval='1d'`)

**User's Original Intent:** 4-hour data

**Why Daily Instead:**
- Yahoo Finance 1H/4H data is unreliable for ASX stocks
- Daily data is rock-solid and free
- Strategy works on any timeframe
- Can switch to 4H later by:
  1. Download 1H data: `stock.history(period='2y', interval='1h')`
  2. Resample to 4H: `df_1h.resample('4H').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'})`

**Code Location:** `scripts/download_data.py` line 41-49 (commented code shows 4H approach)

### API Design Decisions

**Why FastAPI over Flask:**
- Async support (future websockets for real-time)
- Auto-generated API docs (OpenAPI/Swagger)
- Built-in validation (Pydantic)
- Better performance
- Type hints support

**Why File-Based Storage:**
- Simple (no database setup)
- Easy to inspect (`cat data/processed/signals.json`)
- Good enough for 10-200 stocks
- Can migrate to SQLite/PostgreSQL later if needed

**CORS Configuration:**
- Allows localhost:5173 (Vite default)
- Allows localhost:3000 (common React port)
- Location: `backend/app/main.py` line 19-26

---

## Configuration & Settings

### Location: `backend/app/config.py`

**Key Settings:**

```python
ADX_PERIOD = 14           # Period for ADX calculation (Wilder's standard)
ADX_THRESHOLD = 30.0      # Entry condition threshold
SMA_PERIOD = 200          # Long-term trend filter
PROFIT_TARGET = 0.15      # 15% exit target
```

**To Change Strategy Parameters:**
1. Edit `backend/app/config.py`
2. Restart backend server
3. Click "Refresh" in UI to re-run screener with new settings

### Stock List: `data/metadata/stock_list.json`

**Current (10 test stocks):**
```json
{
  "stocks": [
    {"ticker": "CBA.AX", "name": "Commonwealth Bank", "sector": "Financials"},
    {"ticker": "NAB.AX", "name": "National Australia Bank", "sector": "Financials"},
    ...
  ]
}
```

**To Add Stocks:**
1. Edit this file
2. Add new entries with format: `{"ticker": "XYZ.AX", "name": "...", "sector": "..."}`
3. Run: `python scripts/download_data.py` to fetch new data
4. Click "Refresh" in UI

**ASX Ticker Format:** All ASX stocks end with `.AX` (e.g., `BHP.AX`, `CBA.AX`)

---

## API Reference

### Endpoints

**Base URL:** `http://localhost:8000`

#### GET /api/signals
Get current trading signals.

**Query Parameters:**
- `min_score` (float, 0-100): Filter by minimum score (default: 0)
- `sort_by` (string): Sort field - "score" | "adx" | "ticker" (default: "score")

**Response:**
```json
[
  {
    "ticker": "NAB.AX",
    "name": "National Australia Bank",
    "signal": "BUY",
    "score": 67.59,
    "current_price": 42.24,
    "indicators": {
      "ADX": 30.89,
      "DIPlus": 26.46,
      "DIMinus": 13.5,
      "SMA200": 39.0,
      "above_sma200": true
    },
    "entry_conditions": {
      "adx_above_30": true,
      "di_plus_above_di_minus": true,
      "fresh_crossover": false
    },
    "timestamp": "2026-01-02T00:00:00+11:00",
    "sector": "Financials"
  }
]
```

#### GET /api/stocks/{ticker}
Get details for specific stock.

**Example:** `/api/stocks/NAB.AX`

#### GET /api/status
Get screener status.

**Response:**
```json
{
  "last_updated": "2026-01-02T11:08:22.164336",
  "total_stocks": 10,
  "signals_count": 1,
  "status": "ready"
}
```

#### POST /api/refresh
Trigger data refresh and re-run screener.

**Response:**
```json
{
  "status": "success",
  "message": "Data refreshed successfully",
  "signals_found": 1,
  "timestamp": "2026-01-02T11:08:22.164336"
}
```

---

## Common Enhancement Scenarios

### 1. Change Entry/Exit Conditions

**File:** `backend/app/services/signal_detector.py`

**Entry Logic (line 48-80):**
```python
def detect_entry_signal(self, df):
    # Modify these conditions:
    adx_above_threshold = latest['ADX'] > self.adx_threshold
    di_plus_above_di_minus = latest['DIPlus'] > latest['DIMinus']

    # Example: Add volume filter
    # volume_sufficient = latest['Volume'] > average_volume * 1.5

    has_signal = adx_above_threshold and di_plus_above_di_minus
    # has_signal = has_signal and volume_sufficient  # If adding volume
```

**Exit Logic (line 130-170):**
```python
def detect_exit_signal(self, df, entry_price):
    # Modify profit target:
    profit_target_hit = profit_pct >= self.profit_target  # Change self.profit_target

    # Modify trend reversal:
    trend_reversal = ...  # Current: DI+ crosses below DI-

    # Example: Add stop loss
    # stop_loss_hit = current_price <= entry_price * 0.95  # 5% stop
```

### 2. Change Scoring Algorithm

**File:** `backend/app/services/signal_detector.py`

**Function:** `calculate_score()` (line 82-128)

```python
def calculate_score(self, signal_info, df):
    score = 50.0  # Base score - adjust as needed

    # Modify bonuses:
    adx_bonus = min((adx - 30) * 1.25, 25.0)  # Change multiplier or max
    spread_bonus = min(di_spread * 0.5, 15.0)  # Change multiplier or max

    # Add new factors:
    # if volume > avg_volume:
    #     score += 10

    # if rsi_oversold:
    #     score += 5
```

### 3. Add New Indicators

**File:** `backend/app/services/indicators.py`

**Steps:**
1. Add calculation method to `TechnicalIndicators` class
2. Call from `add_all_indicators()` method
3. Update `signal_detector.py` to use new indicator
4. Update `backend/app/models/stock.py` to include in API response

**Example - Add RSI:**
```python
# In indicators.py
@staticmethod
def calculate_rsi(df, period=14):
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# In add_all_indicators()
df['RSI'] = TechnicalIndicators.calculate_rsi(df, period=14)
```

### 4. Change Timeframe (Daily → 4H)

**File:** `scripts/download_data.py`

**Change line 41:**
```python
# Current (daily):
df = stock.history(period='2y', interval='1d')

# Change to 4H:
df_1h = stock.history(period='2y', interval='1h')
df = df_1h.resample('4H').agg({
    'Open': 'first',
    'High': 'max',
    'Low': 'min',
    'Close': 'last',
    'Volume': 'sum'
}).dropna()
```

**Note:** Yahoo Finance may not have reliable 1H data for all ASX stocks. Test thoroughly.

### 5. Scale to ASX 200

**Current:** 10 test stocks
**Target:** Top 200 ASX stocks

**Steps:**
1. Get full ASX 200 list (from ASX website or data provider)
2. Update `data/metadata/stock_list.json` with all 200 tickers
3. Run data download: `python scripts/download_data.py`
4. Performance considerations:
   - Add progress bar (use `tqdm` library)
   - Implement rate limiting (Yahoo Finance has limits)
   - Consider parallel downloads (use `concurrent.futures`)
   - Move to SQLite for faster queries

**Example Rate Limiting:**
```python
import time

for stock in stocks:
    download_stock_data(stock['ticker'])
    time.sleep(1)  # 1 second delay between requests
```

### 6. Add Backtesting

**Create:** `scripts/backtest.py`

**Purpose:** Test strategy on historical data

**Logic:**
```python
1. For each stock:
   2. For each date in historical data:
      3. Check if entry signal occurred
      4. If yes, simulate position:
         - Entry price = close price
         - Track until exit condition
         - Record profit/loss
   5. Calculate metrics:
      - Win rate
      - Average profit
      - Maximum drawdown
      - Sharpe ratio
```

### 7. Add Real-Time Updates

**Current:** Manual refresh or 5-minute auto-refresh

**Enhancement:** WebSocket connection for live updates

**Backend Changes:**
```python
# In main.py, add WebSocket support:
from fastapi import WebSocket

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        # Send updates every minute
        signals = await get_latest_signals()
        await websocket.send_json(signals)
        await asyncio.sleep(60)
```

**Frontend Changes:**
```javascript
// In App.jsx:
useEffect(() => {
  const ws = new WebSocket('ws://localhost:8000/ws');
  ws.onmessage = (event) => {
    const signals = JSON.parse(event.data);
    setSignals(signals);
  };
  return () => ws.close();
}, []);
```

### 8. Add Email/SMS Alerts

**Create:** `backend/app/services/alerts.py`

**Options:**
- Email: Use `smtplib` or SendGrid API
- SMS: Use Twilio API
- Push: Use Firebase Cloud Messaging

**Example:**
```python
def send_alert(signal):
    if signal['score'] >= 70:
        send_email(
            to='user@example.com',
            subject=f'High Score Signal: {signal["ticker"]}',
            body=f'Score: {signal["score"]}, ADX: {signal["indicators"]["ADX"]}'
        )
```

### 9. Deploy to Production

**Options:**

**a) Cloud VPS (DigitalOcean, AWS, etc.):**
```bash
# Install dependencies
apt-get update
apt-get install python3 python3-pip nodejs npm

# Setup backend
cd backend
pip3 install -r requirements.txt
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Setup frontend
cd frontend
npm install
npm run build
# Serve with nginx or use PM2
```

**b) Docker (Recommended):**
```dockerfile
# Dockerfile for backend
FROM python:3.13-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Dockerfile for frontend
FROM node:18-alpine
WORKDIR /app
COPY frontend/package*.json .
RUN npm install
COPY frontend/ .
RUN npm run build
# Serve with nginx
```

**c) Heroku:**
```bash
# Create Procfile
web: cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT

# Deploy
heroku create asx-screener
git push heroku main
```

---

## Testing Guidelines

### Manual Testing Checklist

**Backend:**
- [ ] Data download completes without errors
- [ ] CSV files contain valid OHLC data
- [ ] Indicators calculate correctly (compare with TradingView)
- [ ] Signals match expected entry conditions
- [ ] API endpoints return correct data
- [ ] CORS works from frontend

**Frontend:**
- [ ] UI loads without errors
- [ ] Signals display correctly
- [ ] Score colors match thresholds (green/orange/gray)
- [ ] Filter slider works
- [ ] Refresh button triggers API call
- [ ] Auto-refresh works (5 min interval)
- [ ] Responsive on mobile

**Integration:**
- [ ] End-to-end: Download → Calculate → Screen → Display
- [ ] Refresh flow works from UI
- [ ] Error handling displays errors properly

### Validation Against TradingView

**Purpose:** Ensure ADX calculations match Pine Script exactly

**Steps:**
1. Pick a stock (e.g., CBA.AX)
2. Open in TradingView with ADX indicator (period 14)
3. Compare last 5 values with our output
4. Acceptable difference: ±0.5 (due to rounding)

**Command:**
```bash
cd backend
./venv/bin/python3 test_indicators.py
```

---

## Troubleshooting Guide

### Issue: No signals found

**Possible Causes:**
1. ADX below 30 for all stocks (weak market)
2. No DI+ > DI- conditions met (bearish market)
3. Calculation error

**Debug Steps:**
```python
# Add debug output in screener.py:
print(f"ADX: {latest['ADX']}, DI+: {latest['DIPlus']}, DI-: {latest['DIMinus']}")
```

### Issue: Indicators showing NaN

**Cause:** Insufficient data for calculation

**Solution:**
- ADX needs minimum 14 periods
- SMA200 needs minimum 200 periods
- Ensure CSV has enough rows

### Issue: Frontend won't connect to backend

**Check:**
1. Backend running on port 8000? `curl http://localhost:8000/health`
2. CORS configured correctly? Check `backend/app/main.py`
3. Proxy configured? Check `frontend/vite.config.js`

### Issue: Yahoo Finance download fails

**Possible Causes:**
1. Network issues
2. Ticker doesn't exist
3. Rate limiting

**Solutions:**
- Add retry logic
- Add delay between requests
- Verify ticker format (must end with .AX for ASX)

---

## Development Best Practices

### Before Making Changes

1. **Understand current behavior first**
   - Run the app
   - Observe current signals
   - Note current indicator values

2. **Read relevant code sections**
   - Entry/exit logic: `signal_detector.py`
   - Indicators: `indicators.py`
   - API: `routes.py`

3. **Test in isolation**
   - Create test script before modifying main code
   - Use sample data to verify calculations

### After Making Changes

1. **Test backend:**
   ```bash
   cd backend
   ./venv/bin/python3 -m app.services.screener
   ```

2. **Verify signals.json:**
   ```bash
   cat data/processed/signals.json | python -m json.tool
   ```

3. **Test API:**
   ```bash
   curl http://localhost:8000/api/signals | python -m json.tool
   ```

4. **Test frontend:**
   - Open http://localhost:5173
   - Check browser console for errors
   - Verify data displays correctly

### Git Workflow (Recommended)

```bash
# Create feature branch
git checkout -b feature/new-indicator

# Make changes
# ... edit files ...

# Test changes
# ... run tests ...

# Commit
git add .
git commit -m "Add RSI indicator to signal scoring"

# Merge to main
git checkout main
git merge feature/new-indicator
```

---

## Important Files Reference

### Most Frequently Modified

1. **`backend/app/config.py`** - Change thresholds, periods, settings
2. **`backend/app/services/signal_detector.py`** - Entry/exit logic, scoring
3. **`data/metadata/stock_list.json`** - Add/remove stocks

### Rarely Modified (Core Logic)

1. **`backend/app/services/indicators.py`** - ADX/DI calculations (only change if strategy fundamentally changes)
2. **`backend/app/main.py`** - FastAPI setup
3. **`frontend/src/App.jsx`** - Main app logic

### Reference Only

1. **`pinescript_adx_di.txt`** - Original Pine Script (DO NOT DELETE - reference for indicator calculations)
2. **`profit_trade.png`, `stoploss_trade.png`** - Strategy examples (DO NOT DELETE)

---

## Performance Considerations

### Current Performance

- **10 stocks:** ~1-2 seconds
- **200 stocks:** Estimated 20-30 seconds
- **Bottleneck:** CSV I/O and pandas calculations

### Optimization Strategies

**If screening takes > 30 seconds:**

1. **Parallel Processing:**
   ```python
   from concurrent.futures import ProcessPoolExecutor

   with ProcessPoolExecutor(max_workers=4) as executor:
       results = executor.map(process_stock, stocks)
   ```

2. **Move to Database:**
   - Store OHLC in SQLite/PostgreSQL
   - Pre-calculate indicators (update daily)
   - Query only latest values

3. **Cache Indicators:**
   - Don't recalculate on every screen
   - Update only when new data arrives

4. **Use Parquet Instead of CSV:**
   - Faster I/O
   - Smaller file size
   - Better for time series

---

## Security Considerations

### Current Status

- **No authentication** (local development only)
- **No input validation** (trusted data source)
- **No rate limiting** (single user)

### Before Production Deployment

1. **Add Authentication:**
   - JWT tokens or session-based
   - Protect API endpoints

2. **Input Validation:**
   - Validate ticker symbols
   - Sanitize user inputs

3. **Rate Limiting:**
   - Prevent API abuse
   - Use `slowapi` library

4. **HTTPS:**
   - SSL/TLS certificates
   - Secure data in transit

5. **Environment Variables:**
   - Move secrets to `.env`
   - Never commit API keys

---

## Dependencies & Versions

### Python (Backend)

```
fastapi>=0.109.0       # Web framework
uvicorn>=0.27.0        # ASGI server
pandas>=2.0.0          # Data manipulation
numpy>=1.24.0          # Numerical computing
yfinance>=0.2.35       # Yahoo Finance API
pydantic>=2.5.0        # Data validation
pydantic-settings>=2.1.0  # Settings management
```

### JavaScript (Frontend)

```
react@^18.2.0                  # UI library
react-dom@^18.2.0              # React DOM
vite@^5.0.11                   # Build tool
@vitejs/plugin-react@^4.2.1    # Vite React plugin
```

### Breaking Changes to Watch

- **Pandas 3.0:** May change API
- **FastAPI 1.0:** Potential breaking changes
- **React 19:** New features, potential deprecations

---

## Known Limitations

1. **Daily data only** - Not true 4H as user originally wanted (Yahoo Finance limitation)
2. **No database** - File-based storage limits scalability
3. **No real-time** - Manual/scheduled refresh only
4. **No backtesting** - Can't verify strategy performance historically
5. **No position tracking** - Doesn't track actual trades, only signals
6. **Single market** - ASX only (could expand to other exchanges)

---

## Future Enhancement Ideas

### Short Term (Easy)
- [ ] Add more stocks to screen (ASX 200)
- [ ] Email alerts for high-score signals
- [ ] Export signals to CSV
- [ ] Dark mode for UI
- [ ] Mobile app (React Native)

### Medium Term (Moderate)
- [ ] Backtesting engine
- [ ] Multiple strategy support
- [ ] Position tracker (track actual trades)
- [ ] Performance analytics dashboard
- [ ] Watchlist feature

### Long Term (Complex)
- [ ] Real-time data (WebSockets)
- [ ] Machine learning signal enhancement
- [ ] Multi-exchange support (NYSE, NASDAQ, etc.)
- [ ] Automated trading integration (broker API)
- [ ] Social features (share signals, leaderboards)

---

## Contact & Support

**Project Owner:** [User]

**AI Assistant:** Claude (Anthropic)

**Documentation:**
- README.md - User guide
- QUICKSTART.md - Quick start
- claude.md - This file (AI context)

**API Documentation:** http://localhost:8000/docs (when running)

---

## Version History

**v1.0.0** - 2026-01-02
- Initial implementation
- Phases 1-5 complete
- 10 test stocks
- Daily data from Yahoo Finance
- React UI with FastAPI backend
- ADX/DI strategy with scoring

---

**End of Claude Context Document**

*Last updated: 2026-01-02*
*For questions or enhancements, provide this file to your AI assistant*
