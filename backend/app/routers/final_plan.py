"""Final Plan router — sync adhoc/inventory inputs, run, history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

from app.deps import get_current_user, require_write, get_db
from planning_suite.db.engine import Database

router = APIRouter()


@router.get("/status")
def final_plan_status(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    from planning_suite.services.pipeline_state import is_baseline_approved
    approved = is_baseline_approved()
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            latest = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file
                    FROM final_plan_runs ORDER BY run_date DESC LIMIT 1
                """)
            ).fetchone()
        latest_dict = dict(latest._mapping) if latest else None
    except Exception:
        latest_dict = None
    return {"baseline_approved": approved, "latest_run": latest_dict}


@router.get("/runs")
def get_final_plan_runs(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT fpr.run_id, fpr.run_name, fpr.status, fpr.run_date,
                           fpr.output_file, fpr.validation_status, fpr.approved_at,
                           u.full_name as approved_by_name
                    FROM final_plan_runs fpr
                    LEFT JOIN users u ON u.id = fpr.approved_by
                    ORDER BY fpr.run_date DESC LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []


@router.post("/sync-adhoc")
def sync_adhoc(
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    """Sync Adhoc adjustment files from Google Sheets → local Excel."""
    try:
        from planning_suite.services.final_plan_sync import sync_adhoc_from_sheet
        sync_adhoc_from_sheet()
        return {"detail": "Adhoc sync complete"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync-inventory")
def sync_inventory(
    current_user: dict = Depends(require_write),
):
    """Sync inventory buffer logic from Google Sheets → local Excel."""
    try:
        from planning_suite.services.final_plan_sync import sync_inventory_from_sheet
        sync_inventory_from_sheet()
        return {"detail": "Inventory sync complete"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config")
def get_final_plan_config(current_user: dict = Depends(get_current_user)):
    from planning_suite import config as cfg
    return {
        "ff_inputs_folder": cfg.FF_INPUTS_FOLDER,
        "ff_inv_logic_folder": cfg.FF_INV_LOGIC_FOLDER,
        "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
        "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
    }
