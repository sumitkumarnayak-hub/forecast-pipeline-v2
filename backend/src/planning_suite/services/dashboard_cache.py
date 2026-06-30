"""Process-wide TTL cache for dashboard 6w aggregates (shared across users)."""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable

_TTL_SECONDS = int(os.getenv("DASHBOARD_CACHE_TTL", "3600"))
_LOCK = threading.RLock()
_STORE: dict[str, tuple[float, Any]] = {}


def get_cached(key: str, factory: Callable[[], Any]) -> Any:
    now = time.monotonic()
    with _LOCK:
        hit = _STORE.get(key)
        if hit is not None:
            ts, value = hit
            if now - ts < _TTL_SECONDS:
                return value
        value = factory()
        _STORE[key] = (now, value)
        return value


def cache_key(prefix: str, *parts: str) -> str:
    return prefix + ":" + ":".join(parts)


def mtime_key(path: str) -> str:
    try:
        return str(int(os.path.getmtime(path)))
    except OSError:
        return "0"
