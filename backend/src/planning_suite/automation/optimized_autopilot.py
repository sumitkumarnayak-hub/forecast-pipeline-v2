"""
Headless Optimized Baseline Auto-Pilot runner.

Mirrors the Streamlit Auto-Pilot (6 steps) for CLI and task-scheduler use:
  1. Master Data Sync & Validation → Product_Masters.xlsx
  2. New Product Launch → P-H Master sync (new-product-sync)
  3. Pull raw actuals → active Parquet dataset
  4. Sync DP Logics worksheets to local Excel
  5. Ensure previous baseline cache + run baseline engine
  6. Send success email notification

Usage (from repo root):
  python scripts/run_optimized_autopilot.py
  python scripts/run_optimized_autopilot.py --from-step 2
  python scripts/run_optimized_autopilot.py --user-id 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from planning_suite.config import PROJECT_ROOT
from planning_suite.db.engine import Database
from planning_suite.services.helpers import generate_run_id
from planning_suite.services.sheets_session import (
    begin_pipeline_sheets_session,
    end_pipeline_sheets_session,
)
from planning_suite.services.workflow_notifications import (
    notify_autopilot_run_finished,
    notify_baseline_run_finished,
)
from planning_suite.automation.autopilot_state import (
    get_cli_autopilot_logger,
    log_autopilot_step,
    save_autopilot_state,
)
from planning_suite.automation.autopilot_ui_config import AUTOPILOT_STEPS

_ACTIVE_RUN_ID: str | None = None


def _progress_print(message: str) -> None:
    """Stdout progress line (flush for schedulers / piped logs)."""
    print(message, flush=True)


def _progress_label(step_idx: int, total: int) -> str:
    pct = int(round((step_idx + 1) / total * 100))
    return f"{pct}% ({step_idx + 1}/{total})"


def _configure_logging(log_file: str | None = None, verbose: bool = False) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("optimized_autopilot")
    logger.handlers.clear()
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    return logger


def _ensure_project_cwd() -> None:
    os.chdir(PROJECT_ROOT)


@dataclass
class AutopilotRunResult:
    success: bool
    run_id: str
    run_name: str
    completed_steps: list[int] = field(default_factory=list)
    failed_step: int | None = None
    error: str = ""
    logs: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1


class OptimizedAutopilotRunner:
    """Run the Optimized Baseline Auto-Pilot outside Streamlit."""

    def __init__(
        self,
        *,
        user_id: int | None = None,
        db: Database | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.user_id = user_id if user_id is not None else int(os.getenv("AUTOPILOT_USER_ID", "1"))
        self.db = db or Database()
        self.logger = logger or _configure_logging()

    def _generator(self):
        from planning_suite.ui.pages.optimized_baseline import OptimizedBaselineGenerator

        return OptimizedBaselineGenerator()

    def _save_state(self, result: AutopilotRunResult, *, source: str = "cli") -> None:
        save_autopilot_state(
            run_id=result.run_id,
            run_name=result.run_name,
            user_id=self.user_id,
            success=result.success,
            completed_steps=result.completed_steps,
            failed_step=result.failed_step,
            error=result.error,
            logs=result.logs,
            source=source,
        )

    def run(
        self,
        *,
        from_step: int = 0,
        to_step: int | None = None,
        run_id: str | None = None,
        run_name: str | None = None,
        notify_on_success: bool = True,
        notify_on_failure: bool = True,
        source: str = "cli",
    ) -> AutopilotRunResult:
        _ensure_project_cwd()

        total = len(AUTOPILOT_STEPS)
        if to_step is None:
            to_step = total - 1
        if not (0 <= from_step <= to_step < total):
            raise ValueError(f"Invalid step range: from_step={from_step}, to_step={to_step}, total={total}")

        run_id = run_id or generate_run_id("AUTOPILOT")
        run_name = run_name or f"Auto-Pilot CLI {datetime.now():%Y-%m-%d %H:%M}"

        self._run_source = source

        global _ACTIVE_RUN_ID
        _ACTIVE_RUN_ID = run_id
        self.logger = get_cli_autopilot_logger(lambda: _ACTIVE_RUN_ID)

        result = AutopilotRunResult(
            success=False,
            run_id=run_id,
            run_name=run_name,
        )
        generator = self._generator()
        sheets = begin_pipeline_sheets_session()

        from planning_suite.storage.sync import sync_before_pipeline

        try:
            sync_before_pipeline()
        except Exception as sync_exc:
            self.logger.warning("Pipeline storage sync before run failed: %s", sync_exc)

        self.db.ensure_autopilot_run(run_id, self.user_id, run_name=run_name, source=source)
        self._save_state(result, source=source)

        steps_in_run = to_step - from_step + 1
        self.logger.info("Starting Optimized Baseline Auto-Pilot")
        self.logger.info("Run ID: %s", run_id)
        self.logger.info("Run name: %s", run_name)
        self.logger.info("Steps %s → %s (of %s)", from_step + 1, to_step + 1, total)

        _progress_print("=" * 60)
        _progress_print("OPTIMIZED BASELINE AUTO-PILOT — STARTED")
        _progress_print(f"Run ID   : {run_id}")
        _progress_print(f"Run name : {run_name}")
        _progress_print(f"Progress : 0% (0/{total}) — preparing pipeline")
        _progress_print(f"Steps    : {from_step + 1} to {to_step + 1} ({steps_in_run} step(s) this run)")
        _progress_print("=" * 60)

        try:
            for run_offset, step_idx in enumerate(range(from_step, to_step + 1)):
                step = AUTOPILOT_STEPS[step_idx]
                progress = _progress_label(step_idx, total)
                run_progress = int(round((run_offset + 1) / steps_in_run * 100))

                self.logger.info("--- %s ---", step["name"])
                self.logger.info("%s", step["desc"])
                _progress_print(
                    f"[PROGRESS] {progress} | run {run_progress}% "
                    f"— {step['name']} — STARTED"
                )
                _progress_print(f"           {step['desc']}")

                if step_idx == 5 and not notify_on_success:
                    self.logger.info("Skipping notification step (--skip-notify).")
                    _progress_print(f"[PROGRESS] {progress} — {step['name']} — SKIPPED (--skip-notify)")
                    result.completed_steps.append(step_idx)
                    result.logs[step_idx] = {"text": "Notification skipped."}
                    continue

                try:
                    step_log = generator._opt_pilot_execute_step(
                        step_idx,
                        self.user_id,
                        run_id=run_id,
                        run_name=run_name,
                        sheets_manager=sheets,
                    )
                    result.logs[step_idx] = step_log
                    result.completed_steps.append(step_idx)
                    log_autopilot_step(run_id, step_idx, step_log)
                    metrics = step_log.get("metrics") or {}
                    if metrics.get("Run name"):
                        run_name = str(metrics["Run name"])
                        result.run_name = run_name
                    self.logger.info("Completed: %s", step_log.get("text", "OK"))
                    _progress_print(
                        f"[PROGRESS] {progress} | run {run_progress}% "
                        f"— {step['name']} — COMPLETED"
                    )
                    _progress_print(f"           {step_log.get('text', 'OK')}")
                    if metrics:
                        for key, value in metrics.items():
                            self.logger.info("  %s: %s", key, value)
                            _progress_print(f"           • {key}: {value}")
                    warning = step_log.get("warning")
                    if warning:
                        self.logger.warning(warning)
                        _progress_print(f"           ⚠ {warning}")
                except Exception as exc:
                    result.failed_step = step_idx
                    result.error = str(exc)
                    detail = traceback.format_exc()
                    result.logs[step_idx] = {
                        "error_summary": str(exc),
                        "error_detail": detail,
                    }
                    log_autopilot_step(run_id, step_idx, result.logs[step_idx])
                    self.logger.error("Failed at %s: %s", step["name"], exc)
                    self.logger.debug(detail)
                    _progress_print(
                        f"[PROGRESS] {progress} | run {run_progress}% "
                        f"— {step['name']} — FAILED"
                    )
                    _progress_print(f"           Error: {exc}")

                    if notify_on_failure:
                        try:
                            mail = notify_autopilot_run_finished(
                                run_id=run_id,
                                run_name=run_name,
                                status="failed",
                                user_id=self.user_id,
                                error_detail=f"{exc}\n\n{detail}",
                                failed_step=step_idx,
                                step_name=step["name"],
                                db=self.db,
                            )
                            if mail.sent:
                                self.logger.info("Failure notification email sent.")
                                _progress_print("           Failure notification email sent.")
                            else:
                                self.logger.warning(
                                    "Failure notification not sent: %s", mail.detail
                                )
                                _progress_print(
                                    f"           Failure notification not sent: {mail.detail}"
                                )
                        except Exception as notify_exc:
                            self.logger.warning("Could not send failure notification: %s", notify_exc)
                            _progress_print(f"           Could not send failure email: {notify_exc}")

                    _progress_print("=" * 60)
                    _progress_print(f"AUTO-PILOT — FAILED at {progress}")
                    _progress_print("=" * 60)
                    self._save_state(result, source=self._run_source)
                    return result

            result.success = True
            final_progress = _progress_label(to_step, total)
            self.logger.info("Auto-Pilot finished successfully.")
            _progress_print("=" * 60)
            _progress_print(f"[PROGRESS] {final_progress} — ALL STEPS COMPLETED")
            _progress_print("AUTO-PILOT — SUCCESS")
            _progress_print("=" * 60)
            self._save_state(result, source=self._run_source)
            return result
        finally:
            try:
                from planning_suite.storage.sync import sync_after_pipeline

                sync_after_pipeline()
            except Exception as sync_exc:
                self.logger.warning("Pipeline storage sync after run failed: %s", sync_exc)
            end_pipeline_sheets_session()


def run_optimized_autopilot(
    *,
    from_step: int = 0,
    to_step: int | None = None,
    user_id: int | None = None,
    log_file: str | None = None,
    verbose: bool = False,
    skip_notify: bool = False,
    notify_on_failure: bool = True,
    run_id: str | None = None,
    run_name: str | None = None,
    source: str = "cli",
) -> AutopilotRunResult:
    runner = OptimizedAutopilotRunner(user_id=user_id)
    result = runner.run(
        from_step=from_step,
        to_step=to_step,
        run_id=run_id,
        run_name=run_name,
        notify_on_success=not skip_notify,
        notify_on_failure=notify_on_failure,
        source=source,
    )
    if log_file and result.run_id:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            Database().get_pipeline_run_log_text(result.run_id),
            encoding="utf-8",
        )
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Optimized Baseline Auto-Pilot from the command line (task-scheduler friendly).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_optimized_autopilot.py
  python scripts/run_optimized_autopilot.py --from-step 2
  python scripts/run_optimized_autopilot.py --user-id 1
  python scripts/run_optimized_autopilot.py --list-steps

Runs and logs are stored in the database (pipeline_runs, pipeline_step_logs, pipeline_run_log_lines).

Windows Task Scheduler:
  Program:  .venv\\Scripts\\python.exe
  Args:     scripts\\run_optimized_autopilot.py
  Start in: C:\\path\\to\\forecast-pipeline-new-codebase
        """.strip(),
    )
    parser.add_argument(
        "--from-step",
        type=int,
        default=0,
        metavar="N",
        help="Zero-based step index to start from (0–5). Use after a partial failure to resume.",
    )
    parser.add_argument(
        "--to-step",
        type=int,
        default=None,
        metavar="N",
        help="Zero-based step index to end at (inclusive). Default: last step.",
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="User ID for email notifications (default: AUTOPILOT_USER_ID env or 1).",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional: export this run's DB log lines to a text file after completion.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "--skip-notify",
        action="store_true",
        help="Skip the success email notification step (step 6).",
    )
    parser.add_argument(
        "--no-fail-notify",
        action="store_true",
        help="Do not send email on failure.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional fixed run ID (default: auto-generated).",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Optional display name for logs and emails.",
    )
    parser.add_argument(
        "--list-steps",
        action="store_true",
        help="Print step list and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_project_cwd()
    src = PROJECT_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_steps:
        for i, step in enumerate(AUTOPILOT_STEPS):
            print(f"{i}: {step['name']} — {step['desc']}")
        return 0

    result = run_optimized_autopilot(
        from_step=args.from_step,
        to_step=args.to_step,
        user_id=args.user_id,
        log_file=args.log_file,
        verbose=args.verbose,
        skip_notify=args.skip_notify,
        notify_on_failure=not args.no_fail_notify,
        run_id=args.run_id,
        run_name=args.run_name,
    )
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
