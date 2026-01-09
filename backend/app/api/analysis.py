"""
Analysis Routes

On-demand stock analysis for any ticker (including non-ASX300).
Downloads data if missing and runs both strategy detectors.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Optional, List
import yfinance as yf
import pandas as pd
from datetime import datetime
from pathlib import Path
import json

from ..config import settings
from ..services.indicators import TechnicalIndicators
from ..services.triple_trend_detector import TripleTrendDetector
from ..services.mean_reversion_detector import MeanReversionDetector

router = APIRouter(prefix="/api/analyze")

def get_stock_name(ticker: str) -> str:
    """Try to get stock name from metadata or yfinance."""
    # Check metadata first
    try:
        metadata_file = settings.METADATA_DIR / 'stock_list.json'
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                data = json.load(f)
                for stock in data.get('stocks', []):
                    if stock['ticker'] == ticker:
                        return stock.get('name', ticker)
    except Exception:
        pass
        
    # Fallback to yfinance
    try:
        ticker_obj = yf.Ticker(ticker)
        return ticker_obj.info.get('longName', ticker)
    except Exception:
        return ticker

def download_single_stock(ticker: str) -> pd.DataFrame:
    """Download history for a single stock."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", interval="1d")
        
        if df.empty:
            raise ValueError("No data found")
            
        return df
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to download data for {ticker}: {str(e)}")

@router.get("/{ticker}")
async def analyze_stock(ticker: str):
    """
    Analyze a specific stock on demand.
    
    1. Checks if data exists locally, otherwise downloads it.
    2. Runs Triple Trend Detector.
    3. Runs Mean Reversion Detector.
    4. Returns combined analysis.
    """
    ticker = ticker.upper()
    
    # 1. Get Data
    csv_path = settings.RAW_DATA_DIR / f"{ticker}.csv"
    df = None
    
    if csv_path.exists():
        try:
            # Load cached data to check freshness
            df_temp = pd.read_csv(csv_path, index_col='Date', parse_dates=True)
            if not df_temp.empty:
                last_date = df_temp.index[-1].date()
                now = datetime.now()
                today_date = now.date()
                
                # ASX Market Hours (approximate)
                market_open_hour = 10
                market_close_hour = 16
                
                is_stale = False
                
                if last_date < today_date:
                    # If data is from yesterday (or older)
                    if now.hour >= market_open_hour:
                         # Market is OPEN today, so we need today's candle (even if partial)
                         is_stale = True
                    # Else: Pre-market, yesterday's EOD is sufficient
                    
                elif last_date == today_date:
                    # Data includes today's candle
                    file_mod_time = datetime.fromtimestamp(csv_path.stat().st_mtime)
                    age_minutes = (now - file_mod_time).total_seconds() / 60
                    
                    if now.hour >= market_close_hour and file_mod_time.hour < market_close_hour:
                        # Market just closed, but we have intraday data -> Refresh for EOD
                        is_stale = True
                    elif market_open_hour <= now.hour < market_close_hour and age_minutes > 20:
                        # Market is OPEN, and data is > 20 mins old -> Refresh for live price
                        is_stale = True
                
                if not is_stale:
                    df = df_temp
                    # Ensure index is tz-naive
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                        
        except Exception as e:
            print(f"Error reading cache for {ticker}: {e}")
            pass # Force re-download on error
    
    if df is None or df.empty:
        # Download fresh
        df = download_single_stock(ticker)
        # Save to cache
        df.to_csv(csv_path)
    
    # Ensure correct format for indicators
    if df.index.name != 'Date':
        df.index.name = 'Date'
    
    current_price = df['Close'].iloc[-1]
    
    # Prepare DataFrame for Analysis (Strictly EOD)
    # If the last row is today's date (intraday), we exclude it for technical analysis
    # to avoid repainting or false signals based on incomplete candles.
    analysis_df = df.copy()
    if analysis_df.index[-1].date() == datetime.now().date():
        analysis_df = analysis_df.iloc[:-1]
        
    # 2. Calculate Indicators on EOD Data
    try:
        analysis_df = TechnicalIndicators.add_all_indicators(
            analysis_df,
            adx_period=settings.ADX_PERIOD,
            sma_period=settings.SMA_PERIOD,
            atr_period=settings.ATR_PERIOD,
            volume_period=settings.VOLUME_PERIOD,
            rsi_period=settings.RSI_PERIOD,
            bb_period=settings.BB_PERIOD,
            bb_std_dev=settings.BB_STD_DEV
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indicator calculation failed: {str(e)}")
        
    stock_name = get_stock_name(ticker)
    
    # 3. Run Detectors on EOD Data
    
    # --- Triple Trend Strategy ---
    trend_detector = TripleTrendDetector(
        profit_target=settings.PROFIT_TARGET,
        stop_loss=settings.TREND_FOLLOWING_STOP_LOSS,
        time_limit=settings.TREND_FOLLOWING_TIME_LIMIT
    )
    
    # We need to manually construct the result because analyze_stock only returns if signal exists
    # But we want the status regardless of BUY signal
    trend_entry = trend_detector.detect_entry_signal(analysis_df)
    trend_score = trend_detector.calculate_score(trend_entry, analysis_df)
    
    # Logic for Trend Signal
    current_trend_signal = "HOLD"
    if trend_entry['has_signal']:
        current_trend_signal = "BUY"
    elif trend_entry.get('is_bullish'):
        current_trend_signal = "BULLISH"
    elif analysis_df['Fib_Pos'].iloc[-1] <= 0 and analysis_df['PP_Trend'].iloc[-1] == -1:
        current_trend_signal = "SELL" # Both major trend indicators are bearish
    
    trend_result = {
        "strategy": "Trend Following",
        "signal": current_trend_signal,
        "score": round(trend_score, 1),
        "indicators": {
            "Fib_Pos": int(trend_entry.get('fib_pos', 0)) if trend_entry.get('has_signal') else int(analysis_df['Fib_Pos'].iloc[-1]),
            "Supertrend": int(trend_entry.get('st_trend', 0)) if trend_entry.get('has_signal') else int(analysis_df['PP_Trend'].iloc[-1]),
            "Instant_Trend": "BULLISH" if analysis_df['IT_Trigger'].iloc[-1] > analysis_df['IT_Trend'].iloc[-1] else "BEARISH"
        }
    }
    
    # --- Mean Reversion Strategy ---
    mr_detector = MeanReversionDetector(
        rsi_threshold=settings.RSI_THRESHOLD,
        profit_target=settings.MEAN_REVERSION_PROFIT_TARGET,
        bb_period=settings.BB_PERIOD,
        bb_std_dev=settings.BB_STD_DEV,
        rsi_period=settings.RSI_PERIOD
    )
    
    mr_entry = mr_detector.detect_entry_signal(analysis_df)
    mr_score = mr_detector.calculate_score(mr_entry, analysis_df)
    
    # Logic for MR Signal
    current_mr_signal = "HOLD"
    if mr_entry['has_signal']:
        current_mr_signal = "BUY"
    elif analysis_df['RSI'].iloc[-1] > 70 or analysis_df['Close'].iloc[-1] > analysis_df['BB_Upper'].iloc[-1]:
        current_mr_signal = "SELL" # Overbought state
    
    mr_result = {
        "strategy": "Mean Reversion",
        "signal": current_mr_signal,
        "score": round(mr_score, 1),
        "indicators": {
            "RSI": round(analysis_df['RSI'].iloc[-1], 1),
            "BB_Position": "OVERSOLD" if analysis_df['Close'].iloc[-1] < analysis_df['BB_Lower'].iloc[-1] else ("OVERBOUGHT" if analysis_df['Close'].iloc[-1] > analysis_df['BB_Upper'].iloc[-1] else "NORMAL"),
            "BB_Lower": round(analysis_df['BB_Lower'].iloc[-1], 2)
        }
    }
    
    return {
        "ticker": ticker,
        "name": stock_name,
        "current_price": round(current_price, 2),
        "last_updated": datetime.now().isoformat(),
        "strategies": {
            "trend": trend_result,
            "mean_reversion": mr_result
        }
    }
