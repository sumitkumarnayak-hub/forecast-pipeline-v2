"""HttpOnly JWT cookie helpers for browser sessions."""
from __future__ import annotations

import os

from fastapi import Response

AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "ps_auth").strip() or "ps_auth"
IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"
COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "true" if IS_PRODUCTION else "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax")
COOKIE_DAYS = float(os.getenv("AUTH_COOKIE_DAYS", "7"))


def set_auth_cookie(response: Response, token: str, *, remember_me: bool = True) -> None:
    max_age = int(COOKIE_DAYS * 86400) if remember_me else 86400
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,  # type: ignore[arg-type]
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,  # type: ignore[arg-type]
    )
