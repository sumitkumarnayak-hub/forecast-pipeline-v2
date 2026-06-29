"""Shared Google Sheets manager for a pipeline run or Streamlit session."""
from __future__ import annotations

from planning_suite.services.google_sheets import GoogleSheetsManager

SESSION_KEY = "_shared_sheets_manager"
_cli_manager: GoogleSheetsManager | None = None


def get_sheets_manager(*, reuse: bool = True) -> GoogleSheetsManager:
    """Return the active shared manager, or create one (Streamlit session or CLI)."""
    active = get_active_sheets_manager()
    if reuse and active is not None:
        return active
    try:

        if reuse and SESSION_KEY in st.session_state:
            return st.session_state[SESSION_KEY]
        mgr = GoogleSheetsManager()
        if reuse:
            st.session_state[SESSION_KEY] = mgr
        return mgr
    except Exception:
        global _cli_manager
        if reuse and _cli_manager is not None:
            return _cli_manager
        _cli_manager = GoogleSheetsManager()
        return _cli_manager


def get_active_sheets_manager() -> GoogleSheetsManager | None:
    """Return the pipeline-scoped manager when a run is in progress."""
    global _cli_manager
    if _cli_manager is not None:
        return _cli_manager
    try:

        return st.session_state.get(SESSION_KEY)
    except Exception:
        return None


def begin_pipeline_sheets_session() -> GoogleSheetsManager:
    """Start a new shared Sheets session (Auto-Pilot CLI/UI)."""
    global _cli_manager
    _cli_manager = GoogleSheetsManager()
    try:

        st.session_state[SESSION_KEY] = _cli_manager
    except Exception:
        pass
    return _cli_manager


def end_pipeline_sheets_session() -> None:
    """Clear the shared Sheets session after a pipeline run."""
    global _cli_manager
    _cli_manager = None
    try:

        st.session_state.pop(SESSION_KEY, None)
    except Exception:
        pass
