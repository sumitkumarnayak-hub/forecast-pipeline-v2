"""In-memory validation run history (per user, server session)."""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

_MAX_PER_USER = 100
_LOCK = threading.RLock()
_STORE: dict[int, list[dict[str, Any]]] = {}


def append_validation_run(
    *,
    user_id: int,
    username: str,
    run_id: str,
    validation_type: str,
    passed: bool,
    errors_found: list[str] | None = None,
    filename: str | None = None,
    stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "validation_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "validation_type": validation_type,
        "passed": passed,
        "run_id": run_id,
        "username": username,
        "errors_found": errors_found or [],
        "filename": filename,
        "stats": stats or {},
    }
    with _LOCK:
        history = _STORE.setdefault(user_id, [])
        history.insert(0, row)
        _STORE[user_id] = history[:_MAX_PER_USER]
    return row


def get_validation_history(*, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        rows = list(_STORE.get(user_id, [])[:limit])
    out = []
    for r in rows:
        entry = dict(r)
        errs = entry.get("errors_found") or []
        if isinstance(errs, list):
            entry["errors_display"] = "; ".join(str(e) for e in errs[:8])
            if len(errs) > 8:
                entry["errors_display"] += f" … (+{len(errs) - 8} more)"
        else:
            entry["errors_display"] = str(errs)
        entry["passed_label"] = "Pass" if entry.get("passed") else "Fail"
        out.append(entry)
    return out


def clear_validation_history(*, user_id: int) -> None:
    with _LOCK:
        _STORE.pop(user_id, None)
