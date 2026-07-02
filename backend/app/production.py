"""Production startup checks and safe error messaging."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def is_production() -> bool:
    return os.getenv("APP_ENV", "development").strip().lower() in {"production", "prod"}


def validate_production_environment() -> list[str]:
    """Return warnings; raise on blocking misconfiguration."""
    warnings: list[str] = []
    if not is_production():
        return warnings

    from planning_suite.config import get_auth_secret

    get_auth_secret()

    if not os.getenv("DATABASE_URL", "").strip():
        warnings.append("DATABASE_URL is not set — SQLite fallback is not recommended in production")

    if not os.getenv("GOOGLE_CREDENTIALS_PATH", "").strip():
        warnings.append("GOOGLE_CREDENTIALS_PATH is not set — Google Sheets features will fail")

    cookie_secure = os.getenv("AUTH_COOKIE_SECURE", "true").lower() == "true"
    if not cookie_secure:
        warnings.append("AUTH_COOKIE_SECURE should be true in production (HTTPS)")

    for msg in warnings:
        logger.warning("Production config: %s", msg)

    return warnings


def public_error_detail(exc: Exception) -> str:
    """Avoid leaking stack traces or paths to API clients in production."""
    if is_production():
        return "An internal error occurred. Contact your administrator with the request ID."
    return str(exc)
