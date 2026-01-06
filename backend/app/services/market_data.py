"""
Market Data Service

Helper functions for fetching stock market data using yfinance.
"""

import yfinance as yf
import pandas as pd
from typing import List, Dict
from fastapi import HTTPException

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
