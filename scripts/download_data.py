"""
ASX Stock Data Downloader

Downloads historical stock data from Yahoo Finance for ASX stocks.
Starting with daily data for reliability (can switch to 4H later).
"""

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime
import json
import sys
import time
import logging
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'data' / 'raw'
METADATA_DIR = PROJECT_ROOT / 'data' / 'metadata'

# Download configuration
MAX_WORKERS = 1          # Parallel downloads
REQUEST_DELAY = 1.5      # Seconds between requests
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


def download_stock_data(ticker: str, period: str = '2y', interval: str = '1d'):
    """
    Download historical data from Yahoo Finance.

    Args:
        ticker: Stock ticker (e.g., 'CBA.AX')
        period: Time period ('1y', '2y', etc.)
        interval: Data interval ('1d' for daily, '1h' for hourly)

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"Downloading {ticker}...", end=' ')

    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, timeout=10)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            print("⚠️  No data available")
            return False

        # Ensure we have a single-level column index if yfinance returned MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Handle duplicate columns (e.g. if yfinance returns multiple 'Close' columns)
        if df.columns.duplicated().any():
            # print(f"⚠️  Duplicate columns found for {ticker}, keeping first")
            df = df.loc[:, ~df.columns.duplicated()]

        # Data validation
        if len(df) < MIN_DATA_ROWS:
            print(f"⚠️  Insufficient data ({len(df)} rows)")
            return False

        # Check for zero prices or missing data
        if 'Close' in df.columns:
            if (df['Close'] == 0).any():
                print(f"⚠️  Contains zero prices")
                return False
        else:
            print(f"⚠️  'Close' column not found")
            return False

        # For 4-hour data (future enhancement):
        # Uncomment the following lines and use interval='1h' above
        # df_4h = df.resample('4H').agg({
        #     'Open': 'first',
        #     'High': 'max',
        #     'Low': 'min',
        #     'Close': 'last',
        #     'Volume': 'sum'
        # }).dropna()
        # df = df_4h

        # Save to CSV
        output_file = DATA_DIR / f"{ticker}.csv"
        df.to_csv(output_file)

        # Get date range
        date_from = df.index[0].strftime('%Y-%m-%d')
        date_to = df.index[-1].strftime('%Y-%m-%d')

        print(f"✓ {len(df)} rows ({date_from} to {date_to})")
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def download_stock_data_with_retry(ticker: str, max_retries: int = MAX_RETRIES):
    """
    Download stock data with retry logic and rate limiting.

    Args:
        ticker: Stock ticker (e.g., 'CBA.AX')
        max_retries: Maximum number of retry attempts

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

            success = download_stock_data(ticker)

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
    print("=" * 60)
    print("ASX Stock Data Downloader")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print(f"Interval: Daily (1d)")
    print(f"Period: 2 years")
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
    logging.info("Starting download session")
    print(f"Logging to: {log_file}\n")

    # Load stock list
    stocks = load_stock_list()
    print(f"Found {len(stocks)} stocks to download\n")

    # Download each stock with parallel processing and progress bar
    success_count = 0
    failed_stocks = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all download tasks
        futures = {
            executor.submit(download_stock_data_with_retry, stock['ticker']): stock
            for stock in stocks
        }

        # Process results with progress bar
        for future in tqdm(as_completed(futures), total=len(stocks), desc="Downloading stocks"):
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
    print(f"Download complete: {success_count}/{len(stocks)} successful")

    if failed_stocks:
        print(f"\nFailed stocks ({len(failed_stocks)}):")
        for ticker in failed_stocks:
            print(f"  - {ticker}")

    print(f"\nDetailed log: {log_file}")
    print("=" * 60)

    logging.info(f"Download session complete: {success_count}/{len(stocks)} successful")


if __name__ == '__main__':
    main()
