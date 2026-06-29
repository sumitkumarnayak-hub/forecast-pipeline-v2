"""Dashboard router — pipeline flow status + recent runs."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends

from app.deps import get_current_user, get_db
from planning_suite.db.engine import Database
from planning_suite.services import pipeline_flow as pf

router = APIRouter()


@router.get("/pipeline-flow")
def get_pipeline_flow(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Live evaluation of all 7 pipeline steps (no DB write)."""
    steps = pf.evaluate_all_steps(db)
    summary = pf.get_pipeline_summary(db)
    return {
        "steps": steps,
        "latest_run": summary,
    }


@router.post("/pipeline-flow/run")
def run_pipeline_audit(
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Trigger a full pipeline audit and log it to DB."""
    user_id = int(current_user["sub"])
    run_id = pf.run_pipeline_flow(db, user_id)
    return {"run_id": run_id, "detail": "Pipeline audit complete"}


@router.get("/baseline-runs")
def get_baseline_runs(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Recent baseline run history."""
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file,
                           validation_status, approved_at
                    FROM baseline_runs
                    ORDER BY run_date DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        return []


@router.get("/final-plan-runs")
def get_final_plan_runs(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Recent final plan run history."""
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file,
                           validation_status, approved_at
                    FROM final_plan_runs
                    ORDER BY run_date DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        return []


@router.get("/email-log")
def get_email_log(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT id, sent_at, email_type, subject, recipients,
                           status, error_message
                    FROM email_log
                    ORDER BY sent_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []
