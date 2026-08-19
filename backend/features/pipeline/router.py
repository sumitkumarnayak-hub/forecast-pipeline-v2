"""
Pipeline Execution API routes — log retrieval and manual/Airflow execution triggers.
"""
import uuid
import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.database.engine import Database, get_shared_database
from core.utils.dataframe import sanitize_for_json
from features.auth.dependencies import get_current_user, require_write

router = APIRouter()


@router.get("/runs")
def get_pipeline_execution_runs(
    limit: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Retrieve history of pipeline runs (Airflow, GitHub Actions, Portal UI, CLI)."""
    db = get_shared_database()
    logs = db.get_pipeline_execution_logs(limit=limit)
    return sanitize_for_json({"runs": logs})


@router.get("/runs/{run_id}/log")
def get_pipeline_execution_log_detail(
    run_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Fetch detailed log and step statuses for a specific run."""
    db = get_shared_database()
    detail = db.get_pipeline_execution_log_detail(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Pipeline run '{run_id}' not found")
    return sanitize_for_json(detail)


@router.post("/run")
def trigger_pipeline_run(
    background_tasks: BackgroundTasks,
    triggered_by: str = "Portal UI",
    current_user: dict = Depends(require_write),
):
    """Trigger the 3-step pipeline execution (raw_data_6w -> baseline_parquet -> ff_hub_automation)."""
    from pipeline.pipeline import run_pipeline

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"PIPE_{timestamp}_{uuid.uuid4().hex[:6]}"

    db = get_shared_database()
    db.save_pipeline_execution_log(
        run_id=run_id,
        triggered_by=triggered_by,
        status="queued",
        session_id=str(current_user.get("sub") or ""),
    )

    def _bg_runner():
        run_pipeline(triggered_by=triggered_by, run_id=run_id)

    background_tasks.add_task(_bg_runner)
    return sanitize_for_json({"run_id": run_id, "status": "queued", "detail": "Pipeline execution queued"})
