#!/usr/bin/env python3
"""
ASX Stock Screener - Cloud VM Startup Script

Starts the backend (FastAPI/Uvicorn) for the production deployment. Unlike
start.py (local dev), this does not start a frontend dev server or open a
browser — the frontend is a static build served separately by Caddy (see
/etc/caddy/Caddyfile), and this VM is headless.

Re-execs itself with the backend venv's Python if not already running under
it, so `python3 start_vm.py` works directly without a prior `source
backend/venv/bin/activate`.

Usage:
    python3 start_vm.py
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = PROJECT_ROOT / "backend"
VENV_PYTHON = BACKEND_DIR / "venv" / "bin" / "python3"
PORT = 8000

if not VENV_PYTHON.exists():
    print(f"Venv not found at {VENV_PYTHON} — run: python3 -m venv backend/venv "
          f"&& backend/venv/bin/pip install -r backend/requirements.txt")
    sys.exit(1)

if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve())])

os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

import uvicorn

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT)
