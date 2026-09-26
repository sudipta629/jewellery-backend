"""
app/config.py

Configuration classes for different environments.

Values are read from environment variables so that no secrets are
ever hard-coded.  A .env file is loaded automatically by python-dotenv
(via run.py) before the app starts.
"""

import os
from datetime import timedelta


def _parse_duration(value: str | None, default: timedelta) -> timedelta:
    """
    Parse a human-friendly duration string into a timedelta.

    Supported suffixes:
        m  → minutes  (e.g. "15m")
        h  → hours    (e.g. "2h")
        d  → days     (e.g. "30d")

    Falls back to *default* if the value is None, empty, or unparseable.

    Examples:
        _parse_duration("15m", timedelta(minutes=15))  -> timedelta(minutes=15)
        _parse_duration("30d", timedelta(days=30))     -> timedelta(days=30)
        _parse_duration(None,  timedelta(minutes=15))  -> timedelta(minutes=15)
    """
    if not value:
        return default
    value = value.strip()
    try:
        if value.endswith("m"):
            return timedelta(minutes=int(value[:-1]))
        if value.endswith("h"):
            return timedelta(hours=int(value[:-1]))
        if value.endswith("d"):
            return timedelta(days=int(value[:-1]))
        # plain integer treated as seconds
        return timedelta(seconds=int(value))
    except (ValueError, TypeError):
        return default


class BaseConfig:
    """
    Settings shared across ALL environments.
    Child classes override only what differs.
    """

    # ── Flask core ────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")

    # ── Database ──────────────────────────────────────────────────────────────
    # DATABASE_URL is read from .env (e.g. postgresql+psycopg://user:pass@host/db)
    # Render and other platforms often provide 'postgres://' or 'postgresql://'
    # We must replace it with 'postgresql+psycopg://' to use our installed driver.
    _raw_db_url = os.environ.get("DATABASE_URL", "")
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif _raw_db_url.startswith("postgresql://"):
        _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
        
    DATABASE_URL: str = _raw_db_url

    # Flask-SQLAlchemy reads SQLALCHEMY_DATABASE_URI — we map DATABASE_URL to it.
    SQLALCHEMY_DATABASE_URI: str = _raw_db_url

    # Disable the SQLAlchemy event system for objects that are not tracked.
    # This saves memory and prevents a deprecation warning.
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # ── JWT ───────────────────────────────────────────────────────────────────
    # NEVER hard-code the JWT secret — always read from environment.
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "change-me-in-production")

    # Access token lifetime (default: 15 minutes)
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = _parse_duration(
        os.environ.get("JWT_ACCESS_TOKEN_EXPIRES"), timedelta(minutes=15)
    )

    # Refresh token lifetime (default: 30 days)
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = _parse_duration(
        os.environ.get("JWT_REFRESH_TOKEN_EXPIRES"), timedelta(days=30)
    )

    # ── OTP ───────────────────────────────────────────────────────────────────
    # How long (in minutes) a generated OTP is valid.
    OTP_EXPIRY_MINUTES: int = int(os.environ.get("OTP_EXPIRY_MINUTES", "5"))

    # Maximum incorrect verification attempts before OTP is locked.
    OTP_MAX_ATTEMPTS: int = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))

    # ── CORS ──────────────────────────────────────────────────────────────────
    # The URL of the React frontend.  '*' allows any origin during development.
    FRONTEND_URL: str = os.environ.get("FRONTEND_URL", "*")

    # ── Rate Limiting (Flask-Limiter) ───────────────────────────────────────────
    # Storage backend: "memory://" for single-process dev/test,
    # or "redis://localhost:6379" for multi-worker production.
    RATELIMIT_STORAGE_URI: str = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # Enable/disable rate limiting globally.
    # Set to False in tests so pytest is never blocked by limits.
    RATELIMIT_ENABLED: bool = True

    # Default limits applied to ALL endpoints unless overridden at route level.
    # Empty list = no default limit; each sensitive route sets its own.
    RATELIMIT_DEFAULT: list = []

    # ── JSON output ───────────────────────────────────────────────────────────
    JSON_SORT_KEYS: bool = False


class DevelopmentConfig(BaseConfig):
    """Development environment — debug mode on, verbose errors."""

    DEBUG: bool = True
    TESTING: bool = False


class TestingConfig(BaseConfig):
    """Testing environment — used by pytest."""

    DEBUG: bool = True
    TESTING: bool = True

    # Use a separate in-memory SQLite DB for tests so that the real
    # PostgreSQL database is never touched during the test suite.
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"

    # Use a fixed, predictable JWT secret so test tokens are reproducible.
    JWT_SECRET_KEY: str = "test-jwt-secret-do-not-use-in-production"

    # Short-lived tokens for test speed — override env vars.
    JWT_ACCESS_TOKEN_EXPIRES: timedelta = timedelta(minutes=5)
    JWT_REFRESH_TOKEN_EXPIRES: timedelta = timedelta(days=1)

    # Short OTP expiry for testing expiration scenarios.
    OTP_EXPIRY_MINUTES: int = 5
    OTP_MAX_ATTEMPTS: int = 5

    # Disable rate limiting in tests so pytest is never blocked by per-IP limits.
    RATELIMIT_ENABLED: bool = False


class ProductionConfig(BaseConfig):
    """
    Production environment — debug off, strict secret validation.
    Flask will raise an error at startup if SECRET_KEY or JWT_SECRET_KEY
    are still the default placeholder values.
    """

    DEBUG: bool = False
    TESTING: bool = False

    def __init__(self) -> None:
        if self.SECRET_KEY == "change-me-in-production":
            raise ValueError(
                "SECRET_KEY must be set to a strong random value in production. "
                "Set the SECRET_KEY environment variable before starting the server."
            )
        if self.JWT_SECRET_KEY == "change-me-in-production":
            raise ValueError(
                "JWT_SECRET_KEY must be set to a strong random value in production. "
                "Set the JWT_SECRET_KEY environment variable before starting the server."
            )


# ── Config registry ───────────────────────────────────────────────────────────
_CONFIG_MAP: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(config_name: str = None) -> type[BaseConfig]:
    """
    Return the configuration class that matches *config_name*.

    If *config_name* is None, the FLASK_ENV environment variable is used.
    Falls back to DevelopmentConfig when the value is unrecognised.

    Args:
        config_name: One of 'development', 'testing', or 'production'.

    Returns:
        The matching configuration class (not an instance).
    """
    name = (config_name or os.environ.get("FLASK_ENV", "development")).lower()
    return _CONFIG_MAP.get(name, DevelopmentConfig)
