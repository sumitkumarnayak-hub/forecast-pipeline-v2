"""Auto-Pilot persistence — all runs and logs stored in the database."""
from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd

from planning_suite.db.engine import get_shared_database


def _database() -> Database:
    return get_shared_database()


def load_autopilot_state() -> dict | None:
    """Latest Auto-Pilot run snapshot from pipeline_runs."""
    return _database().get_latest_autopilot_run()


def load_autopilot_history(limit: int = 25) -> pd.DataFrame:
    return _database().get_autopilot_run_history(limit=limit)


def load_autopilot_run(run_id: str) -> dict | None:
    return _database().get_autopilot_run(run_id)


def get_resume_step() -> int | None:
    """
    Zero-based step index to resume the last incomplete Auto-Pilot run.

    Returns None when there is no partial run to resume.
    """
    state = load_autopilot_state()
    if not state or state.get("success"):
        return None
    failed = state.get("failed_step")
    if failed is not None:
        return int(failed)
    completed = state.get("completed_steps") or []
    if completed:
        return len(completed)
    if state.get("status") in ("failed", "running"):
        return 0
    return None


def hydrate_ui_autopilot_from_db() -> dict | None:
    """If the latest DB run did not finish, return state for UI hydration."""
    state = load_autopilot_state()
    if not state or state.get("success"):
        return None
    if state.get("failed_step") is not None or state.get("status") in ("failed", "running"):
        return state
    return None


def save_autopilot_state(
    *,
    run_id: str,
    run_name: str,
    success: bool,
    completed_steps: list[int],
    user_id: int = 1,
    failed_step: int | None = None,
    error: str = "",
    logs: dict[Any, dict[str, Any]] | None = None,
    source: str = "ui",
) -> None:
    """Persist run progress to pipeline_runs.summary_stats."""
    _database().save_autopilot_snapshot(
        run_id=run_id,
        user_id=user_id,
        run_name=run_name,
        source=source,
        success=success,
        completed_steps=completed_steps,
        failed_step=failed_step,
        error=error,
        logs=logs,
    )


def append_autopilot_log(
    run_id: str,
    message: str,
    *,
    level: str = "INFO",
) -> None:
    _database().append_pipeline_run_log(run_id, message, level=level)


def tail_autopilot_log(*, run_id: str | None = None, max_lines: int = 400) -> str:
    rid = run_id
    if not rid:
        state = load_autopilot_state()
        rid = state.get("run_id") if state else None
    if not rid:
        return ""
    return _database().get_pipeline_run_log_text(rid, max_lines=max_lines)


def log_autopilot_step(
    run_id: str,
    step_idx: int,
    step_log: dict[str, Any],
) -> None:
    """Write one completed step to pipeline_step_logs."""
    from planning_suite.automation.optimized_autopilot import AUTOPILOT_STEPS

    if step_idx < 0 or step_idx >= len(AUTOPILOT_STEPS):
        return
    step = AUTOPILOT_STEPS[step_idx]
    failed = bool(step_log.get("error_summary"))
    _database().log_pipeline_step(
        run_id=run_id,
        step_key=step["key"],
        step_name=step["name"],
        step_order=step_idx + 1,
        status="failed" if failed else "completed",
        message=step_log.get("text") or step_log.get("error_summary") or "",
        error_detail=step_log.get("error_detail") or "",
    )


class _DatabaseLogHandler(logging.Handler):
    """Append log records to pipeline_run_log_lines for the active run."""

    def __init__(self, run_id_resolver: Callable[[], str | None], source_tag: str = "") -> None:
        super().__init__()
        self._run_id_resolver = run_id_resolver
        self._tag = f"[{source_tag}] " if source_tag else ""

    def emit(self, record: logging.LogRecord) -> None:
        run_id = self._run_id_resolver()
        if not run_id:
            return
        try:
            msg = self._tag + self.format(record)
            _database().append_pipeline_run_log(run_id, msg, level=record.levelname)
        except Exception:
            self.handleError(record)


def get_ui_autopilot_logger(run_id_resolver: Callable[[], str | None]) -> logging.Logger:
    """Logger that writes UI Auto-Pilot events to the database."""
    logger = logging.getLogger("optimized_autopilot.ui")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = _DatabaseLogHandler(run_id_resolver, source_tag="UI")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


def get_cli_autopilot_logger(run_id_resolver: Callable[[], str | None]) -> logging.Logger:
    """CLI logger: stdout + database."""
    logger = logging.getLogger("optimized_autopilot.cli.db")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    logger.propagate = False

    import sys

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(console)
    logger.addHandler(_DatabaseLogHandler(run_id_resolver, source_tag="CLI"))
    return logger
