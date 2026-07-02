"""Simple in-memory rate limiting for auth endpoints."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_attempts: dict[str, list[float]] = defaultdict(list)

WINDOW_SECONDS = int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "900"))  # 15 min
MAX_ATTEMPTS = int(os.getenv("LOGIN_RATE_MAX_ATTEMPTS", "10"))


def _prune(key: str, now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    _attempts[key] = [t for t in _attempts[key] if t > cutoff]
    if not _attempts[key]:
        del _attempts[key]


def check_login_allowed(client_key: str) -> bool:
    """Return False when too many failed attempts in the sliding window."""
    now = time.time()
    with _lock:
        _prune(client_key, now)
        return len(_attempts.get(client_key, [])) < MAX_ATTEMPTS


def record_login_failure(client_key: str) -> None:
    now = time.time()
    with _lock:
        _prune(client_key, now)
        _attempts[client_key].append(now)


def clear_login_attempts(client_key: str) -> None:
    with _lock:
        _attempts.pop(client_key, None)
