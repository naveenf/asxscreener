"""
Configuration Module

Application settings and configuration.
"""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Project paths
    PROJECT_ROOT: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = PROJECT_ROOT / "data"
    RAW_DATA_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
    METADATA_DIR: Path = DATA_DIR / "metadata"

    # Indicator settings
    ADX_PERIOD: int = 14
    ADX_THRESHOLD: float = 30.0
    SMA_PERIOD: int = 200

    # Trading parameters
    PROFIT_TARGET: float = 0.15  # 15%

    # Data settings
    MIN_HISTORY_DAYS: int = 365
    UPDATE_INTERVAL_MINUTES: int = 240  # 4 hours

    # API settings
    API_TITLE: str = "ASX Stock Screener API"
    API_DESCRIPTION: str = "ADX/DI based stock screening for ASX"
    API_VERSION: str = "1.0.0"
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"


# Global settings instance
settings = Settings()
