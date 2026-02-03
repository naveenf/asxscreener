"""
FastAPI Application

Main application entry point for the ASX Stock Screener API.
"""

# ASX Stock Screener API - Main Application
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
import time
import pandas as pd

# Global Pandas Configuration to silence FutureWarnings
pd.set_option('future.no_silent_downcasting', True)

from .api.routes import router
from .config import settings
from .services.tasks import run_forex_refresh_task, run_stock_refresh_task

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("asx_api")

# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION
)

# Initialize scheduler
scheduler = AsyncIOScheduler()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and their duration."""
    start_time = time.time()
    response = await call_next(request)
    process_time = (time.time() - start_time) * 1000
    
    logger.info(
        f"Request: {request.method} {request.url.path} "
        f"- Status: {response.status_code} - Time: {process_time:.2f}ms"
    )
    return response

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    # Add scheduled tasks
    
    # 1. High-Frequency Sniper Refresh (Every 5 minutes, offset by 1m)
    # This runs for 5m strategy assets only (Silver, BCO) on the in-between intervals
    scheduler.add_job(run_forex_refresh_task, 'cron', minute='6,11,21,26,36,41,51,56', args=['sniper'])
    
    # 2. General Forex Refresh (Every 15 minutes - Full Universe)
    # Run at minutes 1, 16, 31, 46 past the hour to capture closed 15m/1h candles for all pairs
    scheduler.add_job(run_forex_refresh_task, 'cron', minute='1,16,31,46', args=['dynamic'])
    
    # 3. Stock Refresh: Run daily at 18:00 AEST
    scheduler.add_job(run_stock_refresh_task, 'cron', hour=18, minute=0)
    
    scheduler.start()
    logger.info("Background scheduler started (Forex every 15m, Stocks daily at 18:00).")

@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    scheduler.shutdown()
    logger.info("Background scheduler shut down.")

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "ASX Stock Screener API",
        "version": settings.API_VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}