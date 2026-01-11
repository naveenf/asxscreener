"""
FastAPI Application

Main application entry point for the ASX Stock Screener API.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

from .api.routes import router
from .config import settings
from .services.forex_screener import ForexScreener

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

async def scheduled_forex_refresh():
    """Background task to refresh forex data every 15 minutes."""
    try:
        logger.info("Starting scheduled forex refresh...")
        ForexScreener.run_orchestrated_refresh(
            project_root=settings.PROJECT_ROOT,
            data_dir=settings.DATA_DIR / "forex_raw",
            config_path=settings.METADATA_DIR / "forex_pairs.json",
            output_path=settings.PROCESSED_DATA_DIR / "forex_signals.json"
        )
        logger.info("Scheduled forex refresh completed successfully.")
    except Exception as e:
        logger.error(f"Scheduled forex refresh failed: {e}")

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    # Add scheduled tasks
    scheduler.add_job(scheduled_forex_refresh, 'interval', minutes=15)
    scheduler.start()
    logger.info("Background scheduler started (Forex refresh every 15m).")

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
