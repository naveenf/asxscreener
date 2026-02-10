#!/usr/bin/env python3
"""
ASX Stock Screener - Unified Startup Script

Cross-platform launcher that automates the entire application startup:
1. Verifies prerequisites (venv, node_modules)
2. Downloads fresh data if needed (checks 7-day freshness)
3. Starts backend server (FastAPI/Uvicorn)
4. Starts frontend server (Vite)
5. Opens browser automatically
6. Handles graceful shutdown on Ctrl+C

Usage:
    python3 start.py
"""

import sys
import os
import subprocess
import signal
import time
import webbrowser
from pathlib import Path
from datetime import datetime


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).parent.absolute()
DATA_FRESHNESS_DAYS = 1
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
BACKEND_HEALTH_URL = f"http://localhost:{BACKEND_PORT}/health"
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"
HEALTH_CHECK_TIMEOUT = 240  # seconds
HEALTH_CHECK_INTERVAL = 1  # seconds


# ============================================================
# GLOBAL PROCESS HANDLES
# ============================================================

backend_process = None
frontend_process = None


# ============================================================
# COLOR UTILITIES
# ============================================================

class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_success(msg):
    """Print success message in green"""
    print(f"{Colors.GREEN}✓{Colors.RESET} {msg}")


def print_warning(msg):
    """Print warning message in yellow"""
    print(f"{Colors.YELLOW}⚠️{Colors.RESET}  {msg}")


def print_error(msg):
    """Print error message in red"""
    print(f"{Colors.RED}✗{Colors.RESET} {msg}")


def print_info(msg):
    """Print info message in blue"""
    print(f"{Colors.BLUE}ℹ{Colors.RESET}  {msg}")


def print_header(msg):
    """Print header with separator"""
    separator = "=" * 60
    print(f"\n{Colors.BOLD}{Colors.CYAN}{separator}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{msg}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{separator}{Colors.RESET}\n")


# ============================================================
# PREREQUISITE CHECKS
# ============================================================

def check_prerequisites():
    """
    Verify that required prerequisites exist.

    Checks:
    - Backend virtual environment (backend/venv/)
    - Frontend node modules (frontend/node_modules/)

    Raises SystemExit if prerequisites are missing.
    """
    errors = []

    # Check backend venv
    venv_dir = PROJECT_ROOT / 'backend' / 'venv'
    if sys.platform == 'win32':
        venv_python = venv_dir / 'Scripts' / 'python.exe'
    else:
        venv_python = venv_dir / 'bin' / 'python3'

    if not venv_python.exists():
        errors.append(
            f"Backend virtual environment not found at: {venv_dir}\n"
            f"  To create it, run:\n"
            f"    cd backend\n"
            f"    python3 -m venv venv\n"
            f"    source venv/bin/activate  # or: venv\\Scripts\\activate on Windows\n"
            f"    pip install -r requirements.txt"
        )

    # Check frontend node_modules
    node_modules_dir = PROJECT_ROOT / 'frontend' / 'node_modules'
    react_dir = node_modules_dir / 'react'

    if not react_dir.exists():
        errors.append(
            f"Frontend node modules not found at: {node_modules_dir}\n"
            f"  To install them, run:\n"
            f"    cd frontend\n"
            f"    npm install"
        )

    if errors:
        print_error("Missing prerequisites!\n")
        for error in errors:
            print(f"{error}\n")
        sys.exit(1)

    print_success("All prerequisites satisfied")


# ============================================================
# DATA MANAGEMENT
# ============================================================

def get_active_tickers():
    """Load current tickers from stock_list.json."""
    stock_list_file = PROJECT_ROOT / 'data' / 'metadata' / 'stock_list.json'
    if not stock_list_file.exists():
        return set()
    try:
        import json
        with open(stock_list_file, 'r') as f:
            data = json.load(f)
            return {s['ticker'] for s in data.get('stocks', [])}
    except Exception:
        return set()

def get_relevant_csv_files():
    """Get CSV files in raw data directory that belong to the active stock list."""
    data_dir = PROJECT_ROOT / 'data' / 'raw'
    if not data_dir.exists():
        return []
    
    active_tickers = get_active_tickers()
    csv_files = list(data_dir.glob('*.csv'))
    
    if not active_tickers:
        return csv_files
        
    return [f for f in csv_files if f.stem in active_tickers]

def check_data_freshness():
    """
    Check if stock data needs updating.

    Returns True if:
    - Data directory doesn't exist
    - No relevant CSV files found
    - Data for any active stock is older than DATA_FRESHNESS_DAYS

    Returns:
        bool: True if data needs updating, False otherwise
    """
    relevant_files = get_relevant_csv_files()
    if not relevant_files:
        return True

    # Check age of oldest relevant file
    try:
        oldest_file = min(relevant_files, key=lambda f: f.stat().st_mtime)
        age_seconds = time.time() - oldest_file.stat().st_mtime
        age_days = age_seconds / 86400

        return age_days > DATA_FRESHNESS_DAYS
    except Exception as e:
        print_warning(f"Error checking data age: {e}")
        return False


def download_forex_data():
    """
    Download forex/commodity data using the OANDA script.
    """
    forex_script = PROJECT_ROOT / 'scripts' / 'download_forex.py'
    if not forex_script.exists():
        return

    # Get venv python path
    if sys.platform == 'win32':
        venv_python = PROJECT_ROOT / 'backend' / 'venv' / 'Scripts' / 'python.exe'
    else:
        venv_python = PROJECT_ROOT / 'backend' / 'venv' / 'bin' / 'python3'

    try:
        print_info("Updating forex/commodity data (Incremental)...")
        subprocess.run([str(venv_python), str(forex_script)], cwd=str(PROJECT_ROOT), check=True)
        print_success("Forex data update completed")
    except subprocess.CalledProcessError as e:
        print_error(f"Forex download failed: {e}")

def download_data():
    """
    Download stock data using the existing download script.
    """
    print_info("Updating stock data (Incremental)...")

    download_script = PROJECT_ROOT / 'scripts' / 'download_data.py'

    if not download_script.exists():
        print_error(f"Download script not found: {download_script}")
        sys.exit(1)

    # Get venv python path
    if sys.platform == 'win32':
        venv_python = PROJECT_ROOT / 'backend' / 'venv' / 'Scripts' / 'python.exe'
    else:
        venv_python = PROJECT_ROOT / 'backend' / 'venv' / 'bin' / 'python3'

    try:
        # 1. Download Stocks
        subprocess.run([str(venv_python), str(download_script)], cwd=str(PROJECT_ROOT), check=True)
        print_success("Stock data download completed")
        
        # 2. Download Forex
        download_forex_data()

    except subprocess.CalledProcessError as e:
        print_error(f"Data download failed: {e}")
        print_warning("Continuing with existing data (if available)...")
    except KeyboardInterrupt:
        print_warning("\nData download interrupted")
        sys.exit(1)


# ============================================================
# BACKEND SERVER MANAGEMENT
# ============================================================

def run_screener():
    """
    Run the stock and forex screeners to generate fresh signals.
    """
    # Get venv python path
    if sys.platform == 'win32':
        venv_python = PROJECT_ROOT / 'backend' / 'venv' / 'Scripts' / 'python.exe'
    else:
        venv_python = PROJECT_ROOT / 'backend' / 'venv' / 'bin' / 'python3'
        
    # --- STOCK SCREENER ---
    print_info("Running stock screener to generate fresh signals...")
    
    # Update stock list from our ASX 300 source
    print_info("Updating ASX 300 stock list...")
    list_generator = PROJECT_ROOT / 'scripts' / 'generate_asx300_list.py'
    try:
        subprocess.run([str(venv_python), str(list_generator)], check=True)
    except Exception as e:
        print_warning(f"Could not update stock list: {e}")

    try:
        # Run the screener module as a module (-m), not a script
        env = os.environ.copy()
        env['PYTHONPATH'] = str(PROJECT_ROOT / 'backend')
        
        subprocess.run(
            [str(venv_python), '-m', 'app.services.screener'],
            cwd=str(PROJECT_ROOT / 'backend'),
            env=env,
            check=True
        )
        print_success("Stock screener completed successfully")
    except Exception as e:
        print_error(f"Stock screener failed: {e}")

    # --- FOREX SCREENER ---
    print_info("Running forex/commodity screener...")
    try:
        # Run the forex screener manually using a one-liner that calls the orchestrator
        config_path = PROJECT_ROOT / 'data' / 'metadata' / 'forex_pairs.json'
        data_dir = PROJECT_ROOT / 'data' / 'forex_raw'
        output_path = PROJECT_ROOT / 'data' / 'processed' / 'forex_signals.json'
        
        if config_path.exists():
            cmd = [
                str(venv_python), 
                "-c", 
                f"from app.services.forex_screener import ForexScreener; from pathlib import Path; s = ForexScreener(data_dir=Path(r'{data_dir}'), config_path=Path(r'{config_path}'), output_path=Path(r'{output_path}')); res = s.screen_all(); print(f'Forex analyzed: {{res[\"analyzed_count\"]}} symbols, {{res[\"signals_count\"]}} signals found.')"
            ]
            env = os.environ.copy()
            env['PYTHONPATH'] = str(PROJECT_ROOT / 'backend')
            
            subprocess.run(cmd, cwd=str(PROJECT_ROOT / 'backend'), env=env, check=True)
            print_success("Forex screener completed successfully")
    except Exception as e:
        print_error(f"Forex screener failed: {e}")

def start_backend():
    """
    Start the backend server (FastAPI/Uvicorn).

    Returns the subprocess handle.
    """
    global backend_process

    backend_dir = PROJECT_ROOT / 'backend'

    # Get venv python path
    if sys.platform == 'win32':
        venv_python = backend_dir / 'venv' / 'Scripts' / 'python.exe'
    else:
        venv_python = backend_dir / 'venv' / 'bin' / 'python3'

    cmd = [
        str(venv_python),
        '-u', # Force unbuffered stdout
        '-m', 'uvicorn',
        'app.main:app',
        '--host', '0.0.0.0',
        '--port', str(BACKEND_PORT)
    ]

    try:
        backend_process = subprocess.Popen(
            cmd,
            cwd=str(backend_dir),
            stdout=sys.stdout, # Pipe directly to console
            stderr=sys.stderr, # Pipe directly to console
            text=True,
            bufsize=0 # Unbuffered
        )
        print_info(f"Backend server starting on port {BACKEND_PORT}...")

    except Exception as e:
        print_error(f"Failed to start backend: {e}")
        sys.exit(1)


def wait_for_backend():
    """
    Wait for backend to be ready by polling the health endpoint.

    Polls /health endpoint until successful response or timeout.
    """
    import urllib.request
    import urllib.error
    start_time = time.time()
    attempt = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > HEALTH_CHECK_TIMEOUT:
            print_error(f"Backend failed to start within {HEALTH_CHECK_TIMEOUT} seconds")
            if backend_process:
                backend_process.terminate()
            sys.exit(1)

        try:
            with urllib.request.urlopen(BACKEND_HEALTH_URL, timeout=2) as response:
                if response.status == 200:
                    print_success(f"Backend ready on http://localhost:{BACKEND_PORT}")
                    break
        except (urllib.error.URLError, OSError):
            pass

        attempt += 1
        print(f"  Waiting for backend... ({attempt}/{HEALTH_CHECK_TIMEOUT})", end='\r')
        time.sleep(HEALTH_CHECK_INTERVAL)


# ============================================================
# FRONTEND SERVER MANAGEMENT
# ============================================================

def start_frontend():
    """
    Start the frontend server (Vite).

    Returns the subprocess handle.
    """
    global frontend_process

    frontend_dir = PROJECT_ROOT / 'frontend'

    cmd = ['npm', 'run', 'dev']

    try:
        frontend_process = subprocess.Popen(
            cmd,
            cwd=str(frontend_dir),
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            bufsize=0
        )
        print_info(f"Frontend server starting on port {FRONTEND_PORT}...")

    except Exception as e:
        print_error(f"Failed to start frontend: {e}")
        if backend_process:
            backend_process.terminate()
        sys.exit(1)


def wait_for_frontend():
    """
    Wait for frontend to be ready.

    Polls the frontend URL until successful response or timeout.
    """
    import urllib.request
    import urllib.error
    start_time = time.time()
    attempt = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > HEALTH_CHECK_TIMEOUT:
            print_error(f"Frontend failed to start within {HEALTH_CHECK_TIMEOUT} seconds")
            if frontend_process:
                frontend_process.terminate()
            if backend_process:
                backend_process.terminate()
            sys.exit(1)

        try:
            with urllib.request.urlopen(FRONTEND_URL, timeout=2) as response:
                if response.status == 200:
                    print_success(f"Frontend ready on {FRONTEND_URL}")
                    break
        except (urllib.error.URLError, OSError):
            pass

        attempt += 1
        print(f"  Waiting for frontend... ({attempt}/{HEALTH_CHECK_TIMEOUT})", end='\r')
        time.sleep(HEALTH_CHECK_INTERVAL)


# ============================================================
# BROWSER MANAGEMENT
# ============================================================

def open_browser():
    """
    Open the default browser to the frontend URL.

    Waits 2 seconds for servers to stabilize before opening.
    """
    time.sleep(2)  # Give servers time to stabilize

    try:
        print_info(f"Opening browser to {FRONTEND_URL}...")
        webbrowser.open(FRONTEND_URL)
        print_success("Browser opened")
    except Exception as e:
        print_warning(f"Could not open browser automatically: {e}")
        print_info(f"Please open manually: {FRONTEND_URL}")


# ============================================================
# SHUTDOWN MANAGEMENT
# ============================================================

def signal_handler(signum, frame):
    """
    Handle shutdown signals (Ctrl+C, SIGTERM).

    Gracefully terminates both backend and frontend processes.
    """
    print("\n")
    print_info("Shutting down gracefully...")

    # Terminate backend
    if backend_process:
        print("  Stopping backend server...")
        backend_process.terminate()
        try:
            backend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_process.kill()

    # Terminate frontend
    if frontend_process:
        print("  Stopping frontend server...")
        frontend_process.terminate()
        try:
            frontend_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            frontend_process.kill()

    print_success("All servers stopped")
    print("  Goodbye!\n")
    sys.exit(0)


# ============================================================
# STARTUP SUMMARY
# ============================================================

def print_startup_summary():
    """
    Print final startup summary with all relevant information.
    """
    # Get data stats
    relevant_files = get_relevant_csv_files()
    csv_count = len(relevant_files)

    # Get last update time
    if csv_count > 0:
        oldest_file = min(relevant_files, key=lambda f: f.stat().st_mtime)
        age_seconds = time.time() - oldest_file.stat().st_mtime
        age_days = int(age_seconds / 86400)
        data_age = f"{age_days} day{'s' if age_days != 1 else ''} ago"
    else:
        data_age = "No data"

    separator = "=" * 60
    print(f"\n{Colors.BOLD}{Colors.GREEN}{separator}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.GREEN}ASX Stock Screener - Ready!{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.GREEN}{separator}{Colors.RESET}\n")

    print(f"{Colors.BOLD}Backend:{Colors.RESET}   http://localhost:{BACKEND_PORT}")
    print(f"{Colors.BOLD}Frontend:{Colors.RESET}  {FRONTEND_URL}")
    print(f"{Colors.BOLD}API Docs:{Colors.RESET}  http://localhost:{BACKEND_PORT}/docs")
    print()
    print(f"{Colors.BOLD}Data:{Colors.RESET}      {csv_count} stock{'s' if csv_count != 1 else ''}, last updated {data_age}")
    print()
    print(f"{Colors.YELLOW}Press Ctrl+C to stop all servers{Colors.RESET}")
    print(f"\n{Colors.BOLD}{Colors.GREEN}{separator}{Colors.RESET}\n")


# ============================================================
# MAIN FUNCTION
# ============================================================

def main():
    """
    Main startup orchestration.

    Executes all startup steps in sequence:
    1. Print header
    2. Check prerequisites
    3. Check data freshness (download if needed)
    4. Start backend server
    5. Start frontend server
    6. Open browser
    7. Display summary
    8. Wait for shutdown signal
    """
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Print header
    print_header("ASX Stock Screener - Starting Up")

    # Step 1: Check prerequisites
    print("1. Checking prerequisites...")
    check_prerequisites()

    # Step 2: Update Data
    print("\n2. Updating market data...")
    relevant_files = get_relevant_csv_files()
    
    if not relevant_files:
        print_warning("No active stock data found. Performing full initial download...")
    else:
        oldest_file = min(relevant_files, key=lambda f: f.stat().st_mtime)
        age_days = int((time.time() - oldest_file.stat().st_mtime) / 86400)
        if age_days > 0:
            print_info(f"Active stock data is {age_days} day{'s' if age_days != 1 else ''} old. Updating...")
        else:
            print_info("Active stock data is from today. Checking for latest increments...")

    download_data() # Performs fast incremental update for Stocks + Forex

    # Step 2.5: Run screener
    run_screener()

    # Step 3: Start backend
    print("\n3. Starting backend server...")
    start_backend()
    wait_for_backend()

    # Step 4: Start frontend
    print("\n4. Starting frontend server...")
    start_frontend()
    wait_for_frontend()

    # Step 5: Open browser
    print("\n5. Opening browser...")
    open_browser()

    # Step 6: Display summary
    print_startup_summary()

    # Step 7: Keep alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    main()
