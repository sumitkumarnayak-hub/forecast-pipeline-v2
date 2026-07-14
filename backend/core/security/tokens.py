"""HMAC signing for opaque auth session cookies."""
from __future__ import annotations

import hashlib
import hmac

from app.config import get_auth_secret


def sign_session_token(session_id: str) -> str:
    """Return ``session_id.signature`` for storage in the browser cookie."""
    secret = get_auth_secret().encode("utf-8")
    digest = hmac.new(secret, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{session_id}.{digest}"


def verify_session_token(token: str | None) -> str | None:
    """Verify cookie token and return the raw session id, or None if invalid."""
    if not token or token.count(".") != 1:
        return None
    session_id, sig = token.split(".", 1)
    secret = get_auth_secret().encode("utf-8")
    expected = hmac.new(secret, session_id.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return session_id
