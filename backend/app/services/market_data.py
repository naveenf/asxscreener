"""
Market Data Service

Helper functions for fetching stock market data using yfinance.
"""

import yfinance as yf
import pandas as pd
from typing import List, Dict, Optional
from fastapi import HTTPException
from pathlib import Path
import logging
import os

def normalize_ticker(ticker: str) -> str:
    """Ensure ticker has .AX suffix for ASX stocks."""
    ticker = ticker.upper().strip()
    if not ticker.endswith(".AX"):
        return f"{ticker}.AX"
    return ticker

def get_current_prices(tickers: List[str]) -> Dict[str, float]:
    """
    Fetch current prices for a list of tickers using yfinance.
    Returns a dict {ticker_input: current_price}
    """
    if not tickers:
        return {}
    
    # Map input ticker to yfinance ticker
    ticker_map = {t: normalize_ticker(t) for t in tickers}
    yf_tickers = list(ticker_map.values())
    
    try:
        # Fetch data for all tickers
        # Use grouping='ticker' to ensure consistent structure for single/multi tickers
        data = yf.download(yf_tickers, period="1d", progress=False, group_by='ticker')
        
        prices = {}
        
        if data.empty:
            return prices

        for original_ticker, yf_ticker in ticker_map.items():
            try:
                # Handle DataFrame structure variations based on number of tickers
                if len(yf_tickers) == 1:
                    if isinstance(data.columns, pd.MultiIndex):
                        last_price = data[yf_ticker]['Close'].iloc[-1]
                    else:
                        last_price = data['Close'].iloc[-1]
                else:
                    # Multi-ticker: data[yf_ticker]['Close']
                    last_price = data[yf_ticker]['Close'].iloc[-1]
                
                prices[original_ticker] = float(last_price)
            except Exception:
                # Price not found for this ticker
                continue
                
        return prices
    except Exception as e:
        print(f"Error fetching prices: {e}")
        return {}

def validate_and_get_price(ticker: str) -> float:
    """
    Check if ticker is valid and return current price.
    Raises HTTPException if invalid.
    """
    yf_ticker = normalize_ticker(ticker)
    try:
        t = yf.Ticker(yf_ticker)
        # Try fast_info first
        price = t.fast_info.last_price
        if price is not None:
            return float(price)
        
        # Fallback to history
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
            
        raise Exception("No data found")
    except Exception:
         raise HTTPException(status_code=400, detail=f"Invalid ticker symbol: {ticker}")

def update_all_stocks_data(tickers: List[str], data_dir: Path) -> Dict[str, bool]:
    """
    Batch update CSV files for all tickers with latest data.
    Uses a single yf.download call for efficiency.
    """
    if not tickers:
        return {}
        
    yf_tickers = [normalize_ticker(t) for t in tickers]
    results = {t: False for t in tickers}
    
    try:
        # Download last 7 days to ensure we cover weekends/holidays and overlap with CSV
        print(f"Downloading latest data for {len(tickers)} stocks from yfinance...")
        new_data = yf.download(yf_tickers, period="7d", interval="1d", progress=False, group_by='ticker')
        
        if new_data.empty:
            print("No new data downloaded from yfinance")
            return results

        print(f"Download complete. Data shape: {new_data.shape}")

        for ticker in tickers:
            try:
                yf_t = normalize_ticker(ticker)
                
                # Extract data for this ticker robustly
                ticker_df = None
                if isinstance(new_data.columns, pd.MultiIndex):
                    # For MultiIndex, ticker is in the first level
                    if yf_t in new_data.columns.get_level_values(0):
                        ticker_df = new_data[yf_t].copy()
                else:
                    # For single ticker or non-MultiIndex
                    if len(yf_tickers) == 1:
                        ticker_df = new_data.copy()
                
                if ticker_df is None or ticker_df.empty:
                    continue
                
                ticker_df = ticker_df.dropna(subset=['Close'])
                if ticker_df.empty:
                    continue
                
                # Ensure index is datetime and timezone-naive
                if ticker_df.index.tz is not None:
                    ticker_df.index = ticker_df.index.tz_localize(None)
                
                # Floor to midnight
                ticker_df.index = ticker_df.index.floor('D')
                
                csv_path = data_dir / f"{yf_t}.csv"
                if csv_path.exists():
                    # Load existing data
                    existing_df = pd.read_csv(csv_path, index_col='Date', parse_dates=True)
                    
                    if existing_df.index.tz is not None:
                        existing_df.index = existing_df.index.tz_localize(None)
                    existing_df.index = existing_df.index.floor('D')
                    
                    # Combine and remove duplicates
                    combined_df = pd.concat([existing_df, ticker_df])
                    combined_df = combined_df[~combined_df.index.duplicated(keep='last')].sort_index()
                    
                    combined_df.index.name = 'Date'
                    combined_df.to_csv(csv_path)
                    # Force update file modification time to now
                    os.utime(csv_path, None)
                else:
                    ticker_df.index.name = 'Date'
                    ticker_df.to_csv(csv_path)
                
                results[ticker] = True
            except Exception as e:
                print(f"Error updating {ticker}: {e}")
                
        return results
    except Exception as e:
        print(f"Batch update failed: {e}")
        return results
