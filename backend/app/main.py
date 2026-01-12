"""
FastAPI Application

Main application entry point for the ASX Stock Screener API.
"""

# ASX Stock Screener API - Main Application
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

from .api.routes import router
from .config import settings
from .services.tasks import run_forex_refresh_task, run_stock_refresh_task

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION
)

# Initialize scheduler
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    # Add scheduled tasks
    
    # 1. Forex Refresh: Run at minutes 1, 16, 31, 46 past the hour
    scheduler.add_job(run_forex_refresh_task, 'cron', minute='1,16,31,46', args=['dynamic'])
    
    # 2. Stock Refresh: Run daily at 18:00 AEST (8:00 UTC approximately, but scheduler uses local time by default if not specified)
    # Market closes at 17:00 AEST.
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