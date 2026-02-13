
import os
import sys
from pathlib import Path

# Add backend to sys.path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.append(str(backend_path))

# Set up environment (minimal)
os.environ["PYTHONPATH"] = str(backend_path)

from app.services.tasks import run_forex_refresh_task

if __name__ == "__main__":
    mode = 'dynamic'
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    
    print(f"Triggering manual forex refresh task (mode: {mode})...")
    run_forex_refresh_task(mode=mode)
    print("Refresh task completed.")
