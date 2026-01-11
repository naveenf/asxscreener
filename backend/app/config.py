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
    ADX_THRESHOLD: float = 30.0  # OPTIMAL: Early trend entry
    SMA_PERIOD: int = 200

    # Trading parameters
    PROFIT_TARGET: float = 0.15  # 15% profit target

    # Volume filter settings
    VOLUME_FILTER_ENABLED: bool = False  # OPTIMAL: Disabled
    VOLUME_MULTIPLIER: float = 1.5  # Volume must be > 1.5x SMA(20)
    VOLUME_PERIOD: int = 20

    # ATR (volatility) filter settings
    ATR_FILTER_ENABLED: bool = True  # OPTIMAL: Enabled
    ATR_MIN_PCT: float = 2.5  # OPTIMAL: 2.5% minimum volatility
    ATR_PERIOD: int = 14

    # Mean Reversion strategy settings
    MEAN_REVERSION_ENABLED: bool = True
    RSI_THRESHOLD: float = 30.0  # RSI must be < 30 for entry
    RSI_PERIOD: int = 14
    BB_PERIOD: int = 20  # Bollinger Bands period
    BB_STD_DEV: float = 2.0  # Bollinger Bands standard deviations
    MEAN_REVERSION_PROFIT_TARGET: float = 0.20  # 20% profit target
    MEAN_REVERSION_STOP_LOSS: float = 0.07      # 7% stop loss
    MEAN_REVERSION_TIME_LIMIT: int = 90         # 90 days max hold
    TREND_FOLLOWING_STOP_LOSS: float = 0.10     # 10% hard stop
    TREND_FOLLOWING_TIME_LIMIT: int = 90        # 90 days max hold

    # Data settings
    MIN_HISTORY_DAYS: int = 365
    UPDATE_INTERVAL_MINUTES: int = 240  # 4 hours

    # API settings
    API_TITLE: str = "ASX Stock Screener API"
    API_DESCRIPTION: str = "ADX/DI based stock screening for ASX"
    API_VERSION: str = "1.0.0"
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]
    
    # Auth settings
    GOOGLE_CLIENT_ID: str = ""  # Required for frontend-driven auth

    # OANDA settings
    OANDA_ACCESS_TOKEN: str = ""
    OANDA_ENV: str = "live"

    # Email Settings
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = ""

    class Config:
        # Use absolute path to project root for .env
        env_file = Path(__file__).parent.parent.parent / ".env"


# Global settings instance
settings = Settings()
