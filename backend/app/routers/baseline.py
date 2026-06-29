"""Baseline router — config, run history, approve/reject."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.deps import get_current_user, require_write, require_approve, get_db
from planning_suite.db.engine import Database
from planning_suite.services.pipeline_state import (
    is_baseline_approved,
    approve_baseline,
    reject_baseline,
)

router = APIRouter()


@router.get("/status")
def get_baseline_status(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Return current baseline approval state + latest run."""
    approved = is_baseline_approved()
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            latest = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file,
                           validation_status, approved_at, approved_by
                    FROM baseline_runs ORDER BY run_date DESC LIMIT 1
                """)
            ).fetchone()
        latest_dict = dict(latest._mapping) if latest else None
    except Exception:
        latest_dict = None

    return {"approved": approved, "latest_run": latest_dict}


@router.get("/runs")
def get_baseline_runs(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT br.run_id, br.run_name, br.status, br.run_date,
                           br.output_file, br.validation_status, br.approved_at,
                           u.full_name as approved_by_name
                    FROM baseline_runs br
                    LEFT JOIN users u ON u.id = br.approved_by
                    ORDER BY br.run_date DESC LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


@router.post("/approve")
def approve_baseline_run(
    current_user: dict = Depends(require_approve),
    db: Database = Depends(get_db),
):
    user_id = int(current_user["sub"])
    try:
        approve_baseline(db=db, approved_by=user_id)
        return {"detail": "Baseline approved. Final Plan unlocked."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/reject")
def reject_baseline_run(
    current_user: dict = Depends(require_approve),
    db: Database = Depends(get_db),
):
    try:
        reject_baseline(db=db)
        return {"detail": "Baseline rejected."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config")
def get_baseline_config(current_user: dict = Depends(get_current_user)):
    """Return env-derived path config for the baseline page UI."""
    from planning_suite import config as cfg
    return {
        "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
        "raw_actuals_folder": cfg.RAW_ACTUALS_FOLDER,
        "dp_logics_folder": cfg.DP_LOGICS_FOLDER,
        "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
        "pipeline_params_sheet_url": cfg.PIPELINE_PARAMS_SHEET_URL,
    }
