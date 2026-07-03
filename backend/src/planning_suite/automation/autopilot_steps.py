"""Headless Auto-Pilot step runner — no Streamlit."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta

import pandas as pd

from planning_suite.config import (
    BASELINE_OUTPUTS_FOLDER,
    DP_LOGICS_FOLDER,
    FF_MASTERS_XLSX,
    OUTPUT_PATH,
    PROJECT_ROOT,
    RAW_ACTUALS_FOLDER,
)
from planning_suite.db.engine import Database
from planning_suite.services.baseline_engine import BaselineEngine, get_baseline_engine
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.services.helpers import generate_run_id
from planning_suite.services.raw_actuals_cache import resolve_raw_actuals_for_week, write_week_parquet
from planning_suite.services.workflow_notifications import notify_autopilot_run_finished

DP_LOGICS_WORKSHEET_NAMES = [
    "City_Cat",
    "SellThroughFactor",
    "City_drops",
    "Percentile",
    "Avl_Flag",
]

ACTIVE_DATASET_PATH = OUTPUT_PATH / "active_dataset.parquet"
PREV_BASELINE_LATEST = OUTPUT_PATH / "prev_baseline_latest.parquet"


def _latest_baseline_summary_path() -> str | None:
    if not os.path.isdir(BASELINE_OUTPUTS_FOLDER):
        return None
    candidates = sorted(
        [
            f
            for f in os.listdir(BASELINE_OUTPUTS_FOLDER)
            if f.startswith("Summary_") and f.endswith(".xlsx")
        ],
        key=lambda f: os.path.getmtime(os.path.join(BASELINE_OUTPUTS_FOLDER, f)),
        reverse=True,
    )
    return os.path.join(BASELINE_OUTPUTS_FOLDER, candidates[0]) if candidates else None


def ensure_previous_baseline_for_engine(engine: BaselineEngine) -> str:
    """Ensure prev_baseline_latest.parquet exists with BasePlan column."""
    from planning_suite.services.helpers import normalize_base_plan_columns

    latest_path = str(PREV_BASELINE_LATEST)
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

    if os.path.exists(latest_path):
        cached = normalize_base_plan_columns(pd.read_parquet(latest_path))
        if "BasePlan" in cached.columns and not cached.empty:
            if "BasePlan" not in pd.read_parquet(latest_path).columns:
                cached.to_parquet(latest_path, index=False)
            return latest_path

    sheets_manager = engine.sheets_manager
    params = sheets_manager.read_pipeline_params()
    now = datetime.now()
    try:
        target_week = int(params.get("target_week", now.isocalendar()[1]))
    except (TypeError, ValueError):
        target_week = now.isocalendar()[1]
    try:
        target_year = int(params.get("target_year", now.year))
    except (TypeError, ValueError):
        target_year = now.year

    prev_baseline = engine.fetch_previous_baseline(target_week, target_year)
    if prev_baseline is None or prev_baseline.empty:
        raise ValueError(
            f"Previous baseline not found for Week {target_week} / {target_year}. "
            "Check RDS cache and pipeline target_week/target_year parameters."
        )

    prev_baseline = normalize_base_plan_columns(prev_baseline)
    if "BasePlan" not in prev_baseline.columns:
        raise ValueError(
            "Previous baseline loaded but has no BasePlan column. "
            f"Available columns: {prev_baseline.columns.tolist()}"
        )

    cache_dir = OUTPUT_PATH / "prev_baseline_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    week_cache = cache_dir / f"prev_baseline_wk{target_week}_yr{target_year}.parquet"
    prev_baseline.to_parquet(week_cache, index=False)
    prev_baseline.to_parquet(latest_path, index=False)
    return latest_path


def execute_autopilot_step(
    step_idx: int,
    user_id: int,
    *,
    run_id: str | None = None,
    run_name: str | None = None,
    sheets_manager: GoogleSheetsManager | None = None,
    db: Database | None = None,
    engine: BaselineEngine | None = None,
) -> dict:
    """Run a single Auto-Pilot step. Returns a log dict."""
    sheets = sheets_manager or get_baseline_engine().sheets_manager
    eng = engine or get_baseline_engine(sheets=sheets)
    database = db or eng.db

    pilot_run_id = run_id or generate_run_id()
    pilot_run_name = run_name or "Auto-Pilot Pipeline"

    if step_idx == 0:
        from planning_suite.automation.master_data_sync import run_master_data_excel_sync
        from planning_suite.core.validations.master_rules import VALIDATION_VERSION

        result = run_master_data_excel_sync(
            FF_MASTERS_XLSX, user_id, db=database, sheets_manager=sheets
        )
        if result.validation_errors:
            raise RuntimeError(
                f"Master sync blocked: {len(result.validation_errors)} validation error(s) "
                f"({VALIDATION_VERSION})."
            )
        if not result.success:
            raise RuntimeError(result.error or "Master data sync failed.")
        return {
            "text": "Google Sheets synced successfully to Excel backend. All rules passed.",
            "metrics": {
                "P Master Rows": result.p_rows,
                "P-H Master Rows": result.ph_rows,
                "HTT Rows": result.htt_rows,
                "Hub Mapping Rows": result.hub_rows,
                "Excel path": result.excel_path,
                "File size (KB)": result.file_size_kb,
                "Validation Status": "All checks passed",
            },
        }

    if step_idx == 1:
        from planning_suite.automation.new_product_launch_sync import run_new_product_launch_sync_cli

        result = run_new_product_launch_sync_cli(user_id, db=database, sheets=sheets)
        if not result.success:
            raise RuntimeError(result.error or "New product launch sync failed.")
        metrics = {
            "New products": result.products_found,
            "P-H rows inserted": result.rows_inserted,
            "Duplicates skipped": result.duplicates_skipped,
        }
        if result.masters_re_synced:
            metrics["P-H rows after re-sync"] = result.ph_rows_after
        if result.products_synced:
            metrics["Product IDs"] = ", ".join(result.products_synced[:10])
        if result.products_found == 0:
            return {"text": "No new products in P Master — step skipped.", "metrics": metrics}
        return {
            "text": (
                f"New product P-H Master sync complete "
                f"({result.rows_inserted} row(s) for {len(result.products_synced)} product(s))."
            ),
            "metrics": metrics,
        }

    if step_idx == 2:
        end_date = pd.to_datetime("today").normalize() - timedelta(days=1)
        start_date = end_date - timedelta(days=6)

        def _fetch() -> pd.DataFrame | None:
            return eng.fetch_raw_data_from_rds(
                start_date, end_date, product_parity=True, sheets_manager=sheets
            )

        df, iso_week, from_cache = resolve_raw_actuals_for_week(
            start_date, RAW_ACTUALS_FOLDER, _fetch
        )
        week_run_name = f"Auto-Pilot Wk{iso_week}"
        pilot_run_name = week_run_name

        if df is None or df.empty:
            raise ValueError("Failed to fetch raw actuals from RDS.")

        if not from_cache:
            write_week_parquet(df, iso_week, RAW_ACTUALS_FOLDER)

        dedup_keys = [c for c in ["hub_name", "product_id", "process_dt"] if c in df.columns]
        if dedup_keys:
            df = df.drop_duplicates(subset=dedup_keys, keep="first").reset_index(drop=True)

        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        df.to_parquet(ACTIVE_DATASET_PATH, index=False)

        cache_note = " (cached parquet — skipped RDS pull)" if from_cache else ""
        return {
            "text": f"Raw actuals loaded and active dataset updated{cache_note}.",
            "metrics": {
                "Week": iso_week,
                "Run name": week_run_name,
                "Rows": len(df),
                "Start": str(start_date.date()),
                "End": str(end_date.date()),
                "Active dataset": str(ACTIVE_DATASET_PATH),
                "Source": "cache" if from_cache else "RDS",
            },
        }

    if step_idx == 3:
        os.makedirs(DP_LOGICS_FOLDER, exist_ok=True)
        skip_dp = os.getenv("AUTOPILOT_SKIP_DP_SHEETS_IF_FRESH_HOURS", "").strip()
        max_local = float(skip_dp) if skip_dp else None
        sync_results = sheets.sync_dp_logics_worksheets_to_folder(
            DP_LOGICS_FOLDER,
            DP_LOGICS_WORKSHEET_NAMES,
            allow_local_fallback=True,
            parallel=True,
            max_local_age_hours=max_local,
        )
        local_used = [ws for ws, info in sync_results.items() if info.get("status") == "local"]
        metrics = {
            ws: f"{info.get('rows', 0):,} rows ({info.get('source', '')})"
            for ws, info in sync_results.items()
        }
        log = {"text": "Configuration worksheets synced.", "metrics": metrics}
        if local_used:
            log["warning"] = (
                "Google Sheets unavailable — used local files for: " + ", ".join(local_used)
            )
        from planning_suite.services.baseline_io import refresh_all_engine_sidecars

        sidecar_status = refresh_all_engine_sidecars(DP_LOGICS_FOLDER, FF_MASTERS_XLSX)
        if sidecar_status:
            log.setdefault("metrics", {}).update(
                {f"Sidecar {k}": v for k, v in sidecar_status.items()}
            )
        return log

    if step_idx == 4:
        ensure_previous_baseline_for_engine(eng)
        script_path = str(PROJECT_ROOT / "scripts" / "optimized_baseline_avail_correction.py")
        env = os.environ.copy()
        env["BASELINE_USE_ACTIVE_DATASET"] = "1"
        env["BASELINE_ACTIVE_DATASET_PATH"] = str(ACTIVE_DATASET_PATH)
        env["PROJECT_ROOT"] = str(PROJECT_ROOT)
        pipeline_params = sheets.read_pipeline_params()
        apply_hub = pipeline_params.get("apply_hub_changes", True)
        env["BASELINE_APPLY_HUB_CHANGES"] = "1" if apply_hub else "0"
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=1200,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(
                f"Engine failed with code {result.returncode}:\n{detail[-8000:]}"
            )
        stdout = (result.stdout or "").strip()
        summary_path = None
        for line in stdout.splitlines():
            if "Summary saved to:" in line:
                summary_path = line.split("Summary saved to:", 1)[1].strip()
                break
        if not summary_path:
            summary_path = _latest_baseline_summary_path()
        return {
            "text": "Baseline engine completed successfully.",
            "metrics": {
                "Script": script_path,
                "Exit code": 0,
                "Summary file": summary_path or "(not found — check BASELINE_OUTPUTS_FOLDER)",
            },
        }

    if step_idx == 5:
        notify_autopilot_run_finished(
            run_id=pilot_run_id,
            run_name=pilot_run_name,
            status="completed",
            user_id=user_id,
            db=database,
        )
        return {"text": "Success notification sent."}

    raise ValueError(f"Unknown Auto-Pilot step index: {step_idx}")
