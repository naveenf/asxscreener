# Quick Start Guide - ASX Stock Screener

## Complete Application is Ready! 🎉

Your ASX Stock Screener is fully built and ready to run.

## Start the Application

### Option 1: Run Everything (Recommended)

Open **2 terminals** and run these commands:

**Terminal 1 - Backend:**
```bash
cd "/mnt/d/VSProjects/Stock Scanner/asx-screener/backend"
./venv/bin/python3 -m uvicorn app.main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd "/mnt/d/VSProjects/Stock Scanner/asx-screener/frontend"
npm install   # First time only
npm run dev
```

### Option 2: Just the Screener (No UI)

```bash
cd "/mnt/d/VSProjects/Stock Scanner/asx-screener/backend"
./venv/bin/python3 -m app.services.screener
```

## Access Points

- **Frontend UI:** http://localhost:5173
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs
- **Signals JSON:** `data/processed/signals.json`

## What You'll See

### Current Signal (NAB)
- **Ticker:** NAB.AX
- **Name:** National Australia Bank
- **Score:** 67.6/100 (Medium-High)
- **Price:** $42.24
- **ADX:** 30.9 ✓
- **DI+:** 26.5 > DI-: 13.5 ✓
- **Above 200 SMA:** ✓

### Frontend Features
- Color-coded signal cards (green = high score, orange = medium, gray = low)
- Filter by minimum score (slider)
- Auto-refresh every 5 minutes
- Manual refresh button
- Responsive design for mobile/desktop

## API Endpoints

### GET /api/signals
Get all current signals
```bash
curl http://localhost:8000/api/signals
```

### GET /api/signals?min_score=60
Filter by minimum score
```bash
curl "http://localhost:8000/api/signals?min_score=60"
```

### GET /api/stocks/NAB.AX
Get specific stock detail
```bash
curl http://localhost:8000/api/stocks/NAB.AX
```

### GET /api/status
Get screener status
```bash
curl http://localhost:8000/api/status
```

### POST /api/refresh
Trigger data refresh
```bash
curl -X POST http://localhost:8000/api/refresh
```

## Refresh Data

### From Frontend
Click the "🔄 Refresh" button in the header

### From Command Line
```bash
cd backend
./venv/bin/python3 -m app.services.screener
```

## Trading Strategy

**Entry Signal:**
1. ADX > 30 (strong trend)
2. DI+ (green) > DI- (red) (bullish)

**Exit Signal:**
1. 15% profit reached
2. OR DI+ crosses below DI- (trend reversal)

**Score Calculation:**
- Base: 50 points
- ADX strength: +0 to +25 (higher ADX)
- DI spread: +0 to +15 (DI+ vs DI-)
- Above 200 SMA: +10
- Fresh crossover: +5
- **Max:** 100 points

## Next Steps

1. **Test the UI** - Open http://localhost:5173 and explore
2. **Try the API** - Visit http://localhost:8000/docs for interactive API docs
3. **Add More Stocks** - Edit `data/metadata/stock_list.json` to add more ASX tickers
4. **Verify Signals** - Compare with TradingView to validate ADX/DI calculations
5. **Scale Up** - Expand to full ASX 200 stocks

## Troubleshooting

**Backend won't start:**
```bash
cd backend
./venv/bin/pip install -r requirements.txt
```

**Frontend won't start:**
```bash
cd frontend
npm install
```

**No signals.json file:**
```bash
cd backend
./venv/bin/python3 -m app.services.screener
```

**CORS errors:**
- Make sure backend is running on port 8000
- Make sure frontend is running on port 5173

## Project Structure

```
asx-screener/
├── backend/           # Python FastAPI backend
│   ├── app/
│   │   ├── services/  # Core logic (indicators, screener)
│   │   ├── api/       # REST endpoints
│   │   └── main.py    # FastAPI app
│   └── venv/          # Python virtual environment
│
├── frontend/          # React frontend
│   ├── src/
│   │   ├── components/  # UI components
│   │   ├── services/    # API client
│   │   └── App.jsx      # Main app
│   └── node_modules/    # NPM packages
│
└── data/
    ├── raw/           # CSV files (stock data)
    └── processed/     # signals.json
```

## Support

- **Documentation:** See README.md
- **API Docs:** http://localhost:8000/docs
- **Logs:** Check terminal output for errors

---

**Enjoy your ASX Stock Screener!** 🚀📈
