"""Per-user admin demo city/hub filter (replaces Streamlit session_state)."""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

_lock = Lock()
_filters: dict[int, "DemoFilterState"] = {}


@dataclass
class DemoFilterState:
    city: str = "All Cities"
    hubs: list[str] = field(default_factory=list)


def get_demo_filter(user_id: int) -> DemoFilterState:
    with _lock:
        return _filters.get(user_id) or DemoFilterState()


def set_demo_filter(user_id: int, *, city: str | None = None, hubs: list[str] | None = None) -> DemoFilterState:
    with _lock:
        state = _filters.setdefault(user_id, DemoFilterState())
        if city is not None:
            state.city = city.strip() or "All Cities"
        if hubs is not None:
            state.hubs = [h.strip() for h in hubs if h and str(h).strip()]
        return DemoFilterState(city=state.city, hubs=list(state.hubs))


def clear_demo_filter(user_id: int) -> None:
    with _lock:
        _filters.pop(user_id, None)


def demo_filter_active(state: DemoFilterState | None = None) -> bool:
    if state is None:
        return False
    return (state.city and state.city != "All Cities") or bool(state.hubs)
