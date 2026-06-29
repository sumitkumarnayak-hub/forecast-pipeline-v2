"""Resolve auth session id for audit columns on manual / user-triggered logs."""
from __future__ import annotations


def get_audit_session_id() -> str | None:
    """
    Return auth_sessions.session_id for the current browser session.

    Requires the user to have signed in with persistent session (Keep me signed in).
    """
    try:
        from planning_suite.core.session_store import get_current_session_id

        return get_current_session_id()
    except Exception:
        return None
