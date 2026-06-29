"""Weekly forecast pipeline — step definitions, checks, and flow run logging."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from planning_suite.config import (
    FF_INPUTS_FOLDER,
    FF_INV_LOGIC_FOLDER,
    FF_MASTERS_XLSX,
    OUTPUT_PATH,
    PROJECT_ROOT,
)
from planning_suite.db.engine import Database
from planning_suite.services.helpers import generate_run_id
from planning_suite.services.pipeline_state import is_baseline_approved

ACTIVE_DATASET = OUTPUT_PATH / "active_dataset.parquet"
FESTIVE_PATH = Path(FF_INPUTS_FOLDER) / "Festive.xlsx"
INV_BUFFER_PATH = Path(FF_INV_LOGIC_FOLDER) / "Inv_buffer.xlsx"


@dataclass(frozen=True)
class PipelineStepDef:
    key: str
    label: str
    description: str
    nav_page: str | None
    order: int


@dataclass
class StepCheckResult:
    status: str  # passed | failed | manual
    message: str
    error_detail: str = ""


PIPELINE_STEPS: tuple[PipelineStepDef, ...] = (
    PipelineStepDef(
        "masters_ready",
        "Master data ready",
        "Product_Masters.xlsx exists with P Master, P-H Master, and Hub Mapping tabs.",
        "Master Data",
        1,
    ),
    PipelineStepDef(
        "raw_data_loaded",
        "Raw data loaded",
        "Working dataset built at outputs/active_dataset.parquet.",
        "Baseline Generation",
        2,
    ),
    PipelineStepDef(
        "baseline_completed",
        "Baseline generated",
        "Latest baseline run completed successfully (see Run History).",
        "Baseline Generation",
        3,
    ),
    PipelineStepDef(
        "baseline_approved",
        "Baseline approved",
        "Baseline approved by admin — Final Plan unlocked.",
        "Baseline Generation",
        4,
    ),
    PipelineStepDef(
        "ff_inputs_ready",
        "Final Plan inputs ready",
        "Festive file, adhoc inputs, and inventory logic files on disk.",
        "Final Plan",
        5,
    ),
    PipelineStepDef(
        "final_plan_completed",
        "Final Plan generated",
        "Latest final plan run completed successfully.",
        "Final Plan",
        6,
    ),
    PipelineStepDef(
        "hub_dist_output",
        "Hub distribution output",
        "Hub_Dist workbook produced for the forecast week.",
        "Final Plan",
        7,
    ),
)


def _check_masters_excel() -> StepCheckResult:
    path = Path(FF_MASTERS_XLSX)
    if not path.exists():
        return StepCheckResult(
            "failed",
            "Product_Masters.xlsx not found.",
            f"Expected at: {path}",
        )
    try:
        tabs = set(pd.ExcelFile(path).sheet_names)
        missing = sorted({"P Master", "P-H Master", "Hub Mapping"} - tabs)
        if missing:
            return StepCheckResult(
                "failed",
                f"Missing Excel tabs: {', '.join(missing)}",
                "Sync masters from Master Data → Sync Masters to Excel.",
            )
        return StepCheckResult("passed", f"Product_Masters.xlsx ready ({path.name}).")
    except Exception as exc:
        return StepCheckResult("failed", "Cannot read Product_Masters.xlsx.", str(exc))


def _check_raw_data() -> StepCheckResult:
    if ACTIVE_DATASET.exists():
        return StepCheckResult("passed", f"Active dataset found ({ACTIVE_DATASET.name}).")
    return StepCheckResult(
        "failed",
        "No active dataset — load raw data first.",
        f"Expected: {ACTIVE_DATASET}",
    )


def _check_baseline_completed(db: Database) -> StepCheckResult:
    with db.engine.connect() as conn:
        from sqlalchemy import text

        row = conn.execute(
            text("""
                SELECT run_id, status, run_date
                FROM baseline_runs
                WHERE status = 'completed'
                ORDER BY run_date DESC
                LIMIT 1
            """)
        ).fetchone()
    if row:
        return StepCheckResult(
            "passed",
            f"Latest completed baseline: {row[0]} ({row[2]}).",
        )
    return StepCheckResult(
        "manual",
        "No completed baseline run in history.",
        "Go to Baseline Generation → Generate Baseline and run to completion.",
    )


def _check_baseline_approved() -> StepCheckResult:
    if is_baseline_approved():
        return StepCheckResult("passed", "Baseline is approved — Final Plan is unlocked.")
    return StepCheckResult(
        "manual",
        "Baseline not approved yet.",
        "Complete baseline review, then admin must Approve Baseline.",
    )


def _check_ff_inputs() -> StepCheckResult:
    missing: list[str] = []
    if not FESTIVE_PATH.exists():
        missing.append("Festive.xlsx")
    adhoc = Path(FF_INPUTS_FOLDER) / "Adhoc_Adjustment.xlsx"
    if not adhoc.exists():
        missing.append("Adhoc_Adjustment.xlsx")
    if not INV_BUFFER_PATH.exists():
        missing.append("Inv_buffer.xlsx")
    inv_folder = Path(FF_INV_LOGIC_FOLDER)
    if not inv_folder.exists() or not any(inv_folder.glob("*.xlsx")):
        missing.append("Inv_logic/*.xlsx files")
    if missing:
        return StepCheckResult(
            "failed",
            f"Missing Final Plan inputs: {', '.join(missing)}",
            "Open Final Plan → Inputs and sync/upload each input group.",
        )
    return StepCheckResult("passed", "Core Final Plan input files found on disk.")


def _check_final_plan_completed(db: Database) -> StepCheckResult:
    with db.engine.connect() as conn:
        from sqlalchemy import text

        row = conn.execute(
            text("""
                SELECT run_id, status, output_file, run_date
                FROM final_plan_runs
                WHERE status = 'completed'
                ORDER BY run_date DESC
                LIMIT 1
            """)
        ).fetchone()
    if row:
        out = row[2] or "(no file recorded)"
        return StepCheckResult(
            "passed",
            f"Latest completed final plan: {row[0]} → {out}",
        )
    return StepCheckResult(
        "manual",
        "No completed final plan run in history.",
        "Go to Final Plan → Run after all inputs are ready.",
    )


def _check_hub_dist_output() -> StepCheckResult:
    candidates = sorted(
        Path(PROJECT_ROOT).glob("Hub_Dist_Wk*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        latest = candidates[0]
        mtime = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        return StepCheckResult(
            "passed",
            f"Latest output: {latest.name} (modified {mtime}).",
        )
    return StepCheckResult(
        "failed",
        "No Hub_Dist_Wk*.xlsx found in project root.",
        "Run Final Plan generation to produce the hub distribution workbook.",
    )


STEP_CHECKERS: dict[str, Callable[[Database], StepCheckResult]] = {
    "masters_ready": lambda _db: _check_masters_excel(),
    "raw_data_loaded": lambda _db: _check_raw_data(),
    "baseline_completed": _check_baseline_completed,
    "baseline_approved": lambda _db: _check_baseline_approved(),
    "ff_inputs_ready": lambda _db: _check_ff_inputs(),
    "final_plan_completed": _check_final_plan_completed,
    "hub_dist_output": lambda _db: _check_hub_dist_output(),
}


def evaluate_step(step_key: str, db: Database) -> StepCheckResult:
    checker = STEP_CHECKERS.get(step_key)
    if not checker:
        return StepCheckResult("failed", f"Unknown step: {step_key}")
    return checker(db)


def evaluate_all_steps(db: Database) -> list[dict]:
    """Live evaluation of all steps (no DB write)."""
    rows = []
    for step in PIPELINE_STEPS:
        result = evaluate_step(step.key, db)
        rows.append({
            "step_key": step.key,
            "step_name": step.label,
            "step_order": step.order,
            "description": step.description,
            "nav_page": step.nav_page,
            "status": result.status,
            "message": result.message,
            "error_detail": result.error_detail,
        })
    return rows


def run_pipeline_flow(db: Database, user_id: int) -> str:
    """
    Run a full pipeline audit: check every step, log to DB, return run_id.

    Does not auto-run baseline/final plan scripts — records current state only.
    """
    run_id = generate_run_id("PIPELINE")
    db.create_pipeline_run(run_id, user_id)

    passed = failed = manual = 0
    failed_steps: list[str] = []
    manual_steps: list[str] = []

    for step in PIPELINE_STEPS:
        db.update_pipeline_run(run_id, current_step=step.key, status="running")
        result = evaluate_step(step.key, db)
        db.log_pipeline_step(
            run_id=run_id,
            step_key=step.key,
            step_name=step.label,
            step_order=step.order,
            status=result.status,
            message=result.message,
            error_detail=result.error_detail,
        )

        if result.status == "passed":
            passed += 1
        elif result.status == "failed":
            failed += 1
            failed_steps.append(step.label)
        else:
            manual += 1
            manual_steps.append(step.label)

    if failed:
        final_status = "failed"
    elif manual:
        final_status = "partial"
    else:
        final_status = "completed"

    summary = {
        "passed": passed,
        "failed": failed,
        "manual": manual,
        "total_steps": len(PIPELINE_STEPS),
        "failed_steps": failed_steps,
        "manual_steps": manual_steps,
    }
    db.complete_pipeline_run(run_id, status=final_status, summary_stats=summary)

    from planning_suite.services.workflow_notifications import notify_pipeline_audit_finished

    notify_pipeline_audit_finished(
        run_id=run_id,
        status=final_status,
        summary=summary,
        user_id=user_id,
        db=db,
    )
    return run_id


def get_pipeline_summary(db: Database) -> dict | None:
    """Latest pipeline run + step rows for dashboard / flow page."""
    run = db.get_latest_pipeline_run()
    if not run:
        return None
    steps = db.get_pipeline_steps(run["run_id"])
    return {"run": run, "steps": steps}


def status_icon(status: str) -> str:
    return {
        "passed": "✅",
        "completed": "✅",
        "failed": "❌",
        "manual": "⏸️",
        "partial": "⚠️",
        "running": "🔄",
        "pending": "⬜",
    }.get(status, "⬜")


def status_color(status: str) -> str:
    return {
        "passed": "#15803D",
        "completed": "#15803D",
        "failed": "#DC2626",
        "manual": "#D97706",
        "partial": "#D97706",
        "running": "#2563EB",
        "pending": "#64748B",
    }.get(status, "#64748B")
