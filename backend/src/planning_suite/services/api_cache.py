"""Thread-safe TTL cache for API read endpoints (multi-user safe for read-heavy paths)."""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class CacheNS(str, Enum):
    AUTOPILOT_BOOTSTRAP = "autopilot_bootstrap"
    AUTOPILOT_HISTORY = "autopilot_history"
    MASTER_SHEET = "master_sheet"
    BASELINE_REPO = "baseline_repo"
    BASELINE_ACTIVE = "baseline_active"
    BASELINE_PARAMS = "baseline_params"
    BASELINE_STATUS = "baseline_status"
    DASHBOARD = "dashboard"
    USER_PROFILE = "user_profile"
    NPL_WIZARD = "npl_wizard"


_lock = threading.RLock()
_store: dict[str, tuple[float, Any]] = {}


def _full_key(ns: CacheNS, key: str) -> str:
    return f"{ns.value}:{key}"


def cache_get(ns: CacheNS, key: str) -> Any | None:
    full = _full_key(ns, key)
    now = time.monotonic()
    with _lock:
        entry = _store.get(full)
        if not entry:
            return None
        expires_at, value = entry
        if now > expires_at:
            _store.pop(full, None)
            return None
        return value


def cache_set(ns: CacheNS, key: str, value: Any, *, ttl: float = 30.0) -> None:
    full = _full_key(ns, key)
    with _lock:
        _store[full] = (time.monotonic() + max(0.5, ttl), value)


def cache_invalidate(ns: CacheNS, key: str | None = None) -> None:
    with _lock:
        if key is None:
            prefix = f"{ns.value}:"
            for k in list(_store):
                if k.startswith(prefix):
                    _store.pop(k, None)
        else:
            _store.pop(_full_key(ns, key), None)


def cached(
    ns: CacheNS,
    key: str,
    factory: Callable[[], T],
    *,
    ttl: float = 30.0,
    skip_cache: bool = False,
) -> T:
    if not skip_cache:
        hit = cache_get(ns, key)
        if hit is not None:
            return hit
    value = factory()
    if not skip_cache:
        cache_set(ns, key, value, ttl=ttl)
    return value
