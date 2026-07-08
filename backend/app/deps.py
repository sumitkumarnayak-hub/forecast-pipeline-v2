"""
Shared FastAPI dependencies: JWT auth guard, DB instance.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth_cookies import AUTH_COOKIE_NAME
from planning_suite.db.engine import Database, get_shared_database

_bearer = HTTPBearer(auto_error=False)

SECRET = os.getenv("AUTH_SECRET_KEY", "dev-insecure-auth-key-change-before-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = float(os.getenv("AUTH_COOKIE_DAYS", "7"))


def get_db() -> Database:
    """Shared DB singleton — one engine per process (required for autopilot + cache coherence)."""
    return get_shared_database()


# ── Token helpers ──────────────────────────────────────────────────────────────

def create_access_token(user: dict, remember_me: bool = True) -> str:
    expire_days = TOKEN_EXPIRE_DAYS if remember_me else 1
    payload = {
        "sub": str(user["id"]),
        "role": user["role"],
        "full_name": user.get("full_name", ""),
        "email": user.get("email", ""),
        "exp": datetime.now(timezone.utc) + timedelta(days=expire_days),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def _extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str | None:
    if credentials and credentials.credentials:
        return credentials.credentials
    cookie = request.cookies.get(AUTH_COOKIE_NAME)
    if cookie:
        return cookie
    return None


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return decode_token(token)


def require_write(user: dict = Depends(get_current_user)) -> dict:
    from planning_suite.core.permissions import can_write
    if not can_write(user.get("role", "")):
        raise HTTPException(status_code=403, detail="Write permission required")
    return user


def require_approve(user: dict = Depends(get_current_user)) -> dict:
    from planning_suite.core.permissions import can_approve
    if not can_approve(user.get("role", "")):
        raise HTTPException(status_code=403, detail="Approve permission required")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin permission required")
    return user
