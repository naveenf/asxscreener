"""
ASX Stock Data Downloader

Downloads historical stock data from Yahoo Finance for ASX stocks.
Starting with daily data for reliability (can switch to 4H later).
"""

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import json
import sys
import time
import logging
import argparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'raw'
METADATA_DIR = PROJECT_ROOT / 'data' / 'metadata'

# Download configuration
MAX_WORKERS = 1          # Parallel downloads
REQUEST_DELAY = 0.4      # Seconds between requests
MAX_RETRIES = 3          # Retry attempts for failed downloads
MIN_DATA_ROWS = 200      # Minimum rows required (~1 year)

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_stock_list():
    """Load stock list from metadata file."""
    stock_list_file = METADATA_DIR / 'stock_list.json'

    if not stock_list_file.exists():
        print(f"Error: Stock list file not found at {stock_list_file}")
        sys.exit(1)

    with open(stock_list_file, 'r') as f:
        data = json.load(f)

    return data['stocks']


def get_portfolio_tickers():
    """Fetch unique tickers from all user portfolios in Firestore."""
    try:
        # Add backend to path to import firebase_setup
        sys.path.append(str(PROJECT_ROOT / 'backend'))
        from app.firebase_setup import db
        
        tickers = set()
        # Query all 'portfolio' collections (ASX stocks)
        docs = db.collection_group('portfolio').stream()
        
        for doc in docs:
            data = doc.to_dict()
            if 'ticker' in data:
                t = data['ticker'].upper().strip()
                # Ensure .AX suffix if missing (simple heuristic)
                if not t.endswith('.AX') and not t.endswith('.F'): 
                    # Assuming ASX if not futures. 
                    # Ideally we trust user input or validate, but for download we normalize.
                    t += '.AX'
                tickers.add(t)
                
        print(f"Found {len(tickers)} unique tickers from user portfolios.")
        return list(tickers)
    except Exception as e:
        print(f"Warning: Failed to fetch portfolio tickers (Firebase error): {e}")
        return []


def download_stock_data(ticker: str, period: str = '2y', interval: str = '1d', force: bool = False):
    """
    Download historical data from Yahoo Finance.
    
    Args:
        ticker: Stock ticker (e.g., 'CBA.AX')
        period: Time period ('1y', '2y', etc.)
        interval: Data interval ('1d' for daily, '1h' for hourly)
        force: Force full re-download

    Returns:
        bool: True if successful, False otherwise
    """
    output_file = DATA_DIR / f"{ticker}.csv"
    existing_df = None
    start_date = None

    if output_file.exists() and not force:
        try:
            existing_df = pd.read_csv(output_file)
            if not existing_df.empty:
                # Ensure Date is datetime and index
                if 'Date' in existing_df.columns:
                    existing_df['Date'] = pd.to_datetime(existing_df['Date'])
                    existing_df.set_index('Date', inplace=True)
                elif isinstance(existing_df.index, pd.DatetimeIndex):
                    pass # Already fine
                else:
                    # Try to convert index if it's not named Date
                    existing_df.index = pd.to_datetime(existing_df.index)
                
                last_date = existing_df.index.max()
                
                # yfinance 'start' is inclusive. Using last_date directly and drop_duplicates later
                # is safer for ensuring no gaps if timezone issues occur.
                start_date = last_date.strftime('%Y-%m-%d')
                
                # If last update was today or later, we can potentially skip 
                # but markets might still be open/updating. 
                # Since this is daily data, if last_date is yesterday, we update.
                now = datetime.now()
                is_fresh = False

                if last_date.date() == now.date():
                    # We have today's data. 
                    # If it's after market close (17:00), we might want to ensure it's the final EOD candle,
                    # but typically yfinance updates existing daily candle.
                    # For efficiency, if we ran it today, we consider it fresh.
                    is_fresh = True
                
                elif (now.date() - last_date.date()).days == 1:
                    # Last data is yesterday.
                    # If it's before 17:00 (5 PM), today's market is still open or pre-market.
                    # We don't want partial intraday data if we only care about EOD.
                    if now.hour < 17:
                        is_fresh = True
                
                if is_fresh:
                    # Only print if verbose or just silently skip? 
                    # For progress bar context, maybe just return True
                    # But the user sees "Updating..." if we don't return here.
                    # Actually, the caller prints "Downloading stocks...".
                    # We should probably just return True.
                    return True
        except Exception as e:
            print(f"⚠️ Warning: Could not read {output_file}: {e}")
            existing_df = None
            start_date = None

    if start_date:
        print(f"Updating {ticker} (since {start_date})...", end=' ')
    else:
        print(f"Downloading {ticker} (full {period})...", end=' ')

    try:
        if start_date:
            df = yf.download(ticker, start=start_date, interval=interval, progress=False, timeout=10)
        else:
            df = yf.download(ticker, period=period, interval=interval, progress=False, timeout=10)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            if start_date:
                print("✓ Up to date")
                return True
            print("⚠️  No data available")
            return False

        # Ensure we have a single-level column index if yfinance returned MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Handle duplicate columns
        if df.columns.duplicated().any():
            df = df.loc[:, ~df.columns.duplicated()]

        # Data validation for fresh download
        if not start_date and len(df) < MIN_DATA_ROWS:
            print(f"⚠️  Insufficient data ({len(df)} rows)")
            return False

        # Check for zero prices
        if 'Close' in df.columns:
            if (df['Close'] == 0).any():
                print(f"⚠️  Contains zero prices")
                return False
        else:
            print(f"⚠️  'Close' column not found")
            return False

        # If appending, check for gaps (Splits)
        if existing_df is not None and not df.empty:
            # Match types for index comparison
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            
            # Check for split/gap at the junction or overlap
            overlap_dates = existing_df.index.intersection(df.index)
            
            split_detected = False
            old_price = 0
            new_price = 0

            if not overlap_dates.empty:
                # Check the most recent overlapping date
                last_overlap_date = overlap_dates.max()
                old_val = existing_df.loc[last_overlap_date, 'Close']
                new_val = df.loc[last_overlap_date, 'Close']
                
                # Handle potential Series if multiple rows for same date
                old_price = old_val.iloc[-1] if isinstance(old_val, pd.Series) else old_val
                new_price = new_val.iloc[-1] if isinstance(new_val, pd.Series) else new_val
                
                if old_price > 0:
                    change = abs(new_price - old_price) / old_price
                    if change > 0.5:
                        split_detected = True
            else:
                # No overlap, check last old price vs first new price
                old_price = existing_df['Close'].iloc[-1]
                new_price = df['Close'].iloc[0]
                
                if old_price > 0:
                    change = abs(new_price - old_price) / old_price
                    if change > 0.5:
                        split_detected = True

            if split_detected:
                change_pct = (abs(new_price - old_price) / old_price) * 100
                msg = f"\n⚠️  Potential split/gap detected for {ticker}! Existing: {old_price:.2f} -> New: {new_price:.2f} ({change_pct:.1f}% change). Recommended: Run with --tickers {ticker} --force to refresh history."
                print(msg, flush=True)
                logging.warning(msg)

            # Combine
            combined_df = pd.concat([existing_df, df])
            # Keep the latest data for any overlapping dates (yfinance might update yesterday's close)
            combined_df = combined_df[~combined_df.index.duplicated(keep='last')]
            combined_df.sort_index(inplace=True)
            df = combined_df

        # Save to CSV
        df.to_csv(output_file)

        # Get date range
        date_from = df.index[0].strftime('%Y-%m-%d')
        date_to = df.index[-1].strftime('%Y-%m-%d')

        if start_date:
             print(f"✓ {len(df)} rows total")
        else:
             print(f"✓ {len(df)} rows ({date_from} to {date_to})")
             
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def download_stock_data_with_retry(ticker: str, max_retries: int = MAX_RETRIES, force: bool = False):
    """
    Download stock data with retry logic and rate limiting.

    Args:
        ticker: Stock ticker (e.g., 'CBA.AX')
        max_retries: Maximum number of retry attempts
        force: Force full re-download

    Returns:
        bool: True if successful, False otherwise
    """
    for attempt in range(max_retries):
        try:
            # Rate limiting - wait before each request
            if attempt > 0:
                wait_time = REQUEST_DELAY * (2 ** (attempt - 1))  # Exponential backoff
                time.sleep(wait_time)
            else:
                time.sleep(REQUEST_DELAY)

            success = download_stock_data(ticker, force=force)

            if success:
                logging.info(f"Success: {ticker}")
                return True
            else:
                logging.warning(f"No data: {ticker}")
                return False

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = REQUEST_DELAY * (2 ** attempt)
                logging.warning(f"Retry {attempt+1}/{max_retries} for {ticker}: {e}")
                print(f"  Retrying {ticker} in {wait_time:.1f}s...")
                time.sleep(wait_time)
            else:
                logging.error(f"Failed after {max_retries} attempts: {ticker} - {e}")
                return False

    return False


def main():
    """Main download function."""
    parser = argparse.ArgumentParser(description="ASX Stock Data Downloader")
    parser.add_argument("--force", action="store_true", help="Force full re-download of all data")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to download (e.g. CBA.AX BHP.AX)")
    args = parser.parse_args()

    print("=" * 60)
    print("ASX Stock Data Downloader")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Interval: Daily (1d)")
    print(f"Period: 2 years (Full) or Incremental")
    print(f"Force download: {args.force}")
    if args.tickers:
        print(f"Target tickers: {', '.join(args.tickers)}")
    print(f"Max workers: {MAX_WORKERS}")
    print(f"Request delay: {REQUEST_DELAY}s")
    print("=" * 60)
    print()

    # Setup logging
    log_file = PROJECT_ROOT / f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logging.info(f"Starting download session (Force={args.force}, Tickers={args.tickers})")
    print(f"Logging to: {log_file}\n")

    # Load stock list
    stocks_meta = load_stock_list()
    
    # Fetch portfolio tickers
    portfolio_tickers = get_portfolio_tickers()
    
    # Merge lists
    # Create a set of existing tickers for fast lookup
    existing_tickers = {s['ticker'] for s in stocks_meta}
    
    # Add new tickers from portfolio
    for t in portfolio_tickers:
        if t not in existing_tickers:
            stocks_meta.append({'ticker': t, 'name': t, 'sector': 'Unknown'})
            existing_tickers.add(t)
            
    # Filter by tickers if specified
    if args.tickers:
        args_tickers_upper = [t.upper() for t in args.tickers]
        stocks_meta = [s for s in stocks_meta if s['ticker'].upper() in args_tickers_upper]
        if not stocks_meta:
            print(f"Error: None of the specified tickers {args.tickers} found in system/portfolio.")
            sys.exit(1)

    print(f"Total stocks to download: {len(stocks_meta)}\n")

    # Download each stock with parallel processing and progress bar
    success_count = 0
    failed_stocks = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all download tasks
        futures = {
            executor.submit(download_stock_data_with_retry, stock['ticker'], force=args.force): stock
            for stock in stocks_meta
        }

        # Process results with progress bar
        for future in tqdm(as_completed(futures), total=len(stocks_meta), desc="Downloading stocks"):
            stock = futures[future]
            ticker = stock['ticker']

            try:
                if future.result():
                    success_count += 1
                else:
                    failed_stocks.append(ticker)
            except Exception as e:
                failed_stocks.append(ticker)
                logging.error(f"Exception for {ticker}: {e}")
                print(f"\n✗ Exception for {ticker}: {e}")

    # Summary
    print()
    print("=" * 60)
    print(f"Download complete: {success_count}/{len(stocks_meta)} successful")

    if failed_stocks:
        print(f"\nFailed stocks ({len(failed_stocks)}):")
        for ticker in failed_stocks:
            print(f"  - {ticker}")

    print(f"\nDetailed log: {log_file}")
    print("=" * 60)

    logging.info(f"Download session complete: {success_count}/{len(stocks_meta)} successful")


if __name__ == '__main__':
    main()
