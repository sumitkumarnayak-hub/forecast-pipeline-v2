"""Shared Google Sheets manager for a pipeline run or API process."""
from __future__ import annotations

from planning_suite.services.google_sheets import GoogleSheetsManager

SESSION_KEY = "_shared_sheets_manager"
_cli_manager: GoogleSheetsManager | None = None


def get_sheets_manager(*, reuse: bool = True) -> GoogleSheetsManager:
    """Return the active shared manager, or create one."""
    active = get_active_sheets_manager()
    if reuse and active is not None:
        return active
    global _cli_manager
    _cli_manager = GoogleSheetsManager()
    return _cli_manager


def get_active_sheets_manager() -> GoogleSheetsManager | None:
    """Return the pipeline-scoped manager when a run is in progress."""
    return _cli_manager


def begin_pipeline_sheets_session() -> GoogleSheetsManager:
    """Start a new shared Sheets session (Auto-Pilot CLI/UI)."""
    from planning_suite.services.sheets_throttle import begin_pipeline_throttle

    begin_pipeline_throttle()
    global _cli_manager
    _cli_manager = GoogleSheetsManager()
    return _cli_manager


def end_pipeline_sheets_session() -> None:
    """Clear the shared Sheets session after a pipeline run."""
    from planning_suite.services.sheets_throttle import end_pipeline_throttle

    global _cli_manager
    _cli_manager = None
    end_pipeline_throttle()
