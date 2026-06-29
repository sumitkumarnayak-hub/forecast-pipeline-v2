"""Master Data router — sync, history, hub changes, and sheets operations."""
from __future__ import annotations

import traceback
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd

from app.deps import get_current_user, require_write, get_db
from planning_suite.db.engine import Database
from planning_suite.services.sheets_session import get_sheets_manager
from planning_suite.core.dataframe import clean_sheet_df

router = APIRouter()


# ── Sheets Reading ─────────────────────────────────────────────────────────────

@router.get("/p-master")
def get_p_master(current_user: dict = Depends(get_current_user)):
    try:
        gsm = get_sheets_manager()
        df = gsm.read_worksheet_to_df("demand_planning_masters", "product_master", "A:K")
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        df = clean_sheet_df(df)
        return {"rows": df.to_dict(orient="records"), "columns": list(df.columns)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ph-master")
def get_ph_master(current_user: dict = Depends(get_current_user)):
    try:
        gsm = get_sheets_manager()
        df = gsm.read_worksheet_to_df("demand_planning_masters", "product_hub_master", "A:AX")
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        df = clean_sheet_df(df)
        return {"rows": df.to_dict(orient="records"), "columns": list(df.columns)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/hub-master")
def get_hub_master(current_user: dict = Depends(get_current_user)):
    try:
        gsm = get_sheets_manager()
        df = gsm.read_worksheet_to_df("demand_planning_masters", "hub_mapping", "A:F")
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        df = clean_sheet_df(df)
        return {"rows": df.to_dict(orient="records"), "columns": list(df.columns)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/inventory-buffer")
def get_inventory_buffer(current_user: dict = Depends(get_current_user)):
    try:
        from planning_suite.config import INV_LOGICS_SHEET_KEY
        gsm = get_sheets_manager()
        ss = gsm.gc.open_by_key(INV_LOGICS_SHEET_KEY)
        worksheets = ss.worksheets()
        result = {}
        order = []
        for ws in worksheets:
            order.append(ws.title)
            # Fetch worksheet data manually to avoid cached read
            data = ws.get_all_values()
            if data and len(data) > 0:
                df = pd.DataFrame(data[1:], columns=data[0])
                df = clean_sheet_df(df)
                result[ws.title] = df.to_dict(orient="records")
            else:
                result[ws.title] = []
        return {"tabs": result, "order": order}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync-inventory-excel")
def sync_inventory_excel(
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from pathlib import Path
        from planning_suite.config import INV_LOGICS_SHEET_KEY, FF_INV_LOGIC_FOLDER
        gsm = get_sheets_manager()
        ss = gsm.gc.open_by_key(INV_LOGICS_SHEET_KEY)
        out_dir = Path(FF_INV_LOGIC_FOLDER)
        out_dir.mkdir(parents=True, exist_ok=True)

        written = []
        total_rows = 0
        user_id = int(current_user["sub"])

        for ws in ss.worksheets():
            data = ws.get_all_values()
            if not data:
                continue
            df = pd.DataFrame(data[1:], columns=data[0])
            df = clean_sheet_df(df)
            total_rows += len(df)

            fname = f"{ws.title}.xlsx"
            out_path = out_dir / fname
            with pd.ExcelWriter(str(out_path), engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=ws.title[:30], index=False)
            written.append(ws.title)

        db.log_master_sync({
            "master_type": "inventory_buffer_excel",
            "user_id": user_id,
            "records_synced": total_rows,
            "status": "success",
            "error_message": f"{len(written)} files → {out_dir}",
        })
        return {"detail": f"Synced {len(written)} worksheets to Excel", "files": written}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Preview & Sync P-H Master ──────────────────────────────────────────────────

class PreviewSyncPayload(BaseModel):
    product_ids: List[str]


@router.post("/preview-ph-sync")
def preview_ph_sync(
    payload: PreviewSyncPayload,
    current_user: dict = Depends(require_write),
):
    try:
        from planning_suite.services.product_launch_sync import (
            build_new_product_ph_preview,
            load_masters_for_product_sync,
        )
        gsm = get_sheets_manager()
        p_df, hub_df, ph_df = load_masters_for_product_sync(gsm)
        svc = build_new_product_ph_preview(p_df, hub_df, ph_df, product_ids=payload.product_ids)
        return {
            "product_ids": svc.product_ids,
            "schema_errors": svc.schema_errors,
            "not_in_p_master": svc.not_in_p_master,
            "validation_errors": svc.validation_errors,
            "already_exists": svc.already_exists,
            "rows_to_add": svc.rows_to_add,
            "ph_headers": svc.ph_headers,
            "active_hub_count": svc.active_hub_count,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class ConfirmSyncPayload(BaseModel):
    rows_to_add: List[dict]
    ph_headers: List[str]
    product_ids: List[str]


@router.post("/confirm-ph-sync")
def confirm_ph_sync(
    payload: ConfirmSyncPayload,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from planning_suite.config import DPM_SHEET_KEY
        gsm = get_sheets_manager()
        ss = gsm.gc.open_by_key(DPM_SHEET_KEY)
        ph_ws = ss.worksheet("P-H Master")

        current_row_count = len(ph_ws.get_all_values()) - 1
        values = [[r.get(h, "") for h in payload.ph_headers] for r in payload.rows_to_add]

        gsm.append_rows_to_worksheet(
            "demand_planning_masters",
            "product_hub_master",
            values,
            worksheet=ph_ws,
            value_input_option="RAW",
        )

        user_id = int(current_user["sub"])
        db.log_master_sync({
            "master_type": "ph_master_sync",
            "user_id": user_id,
            "records_synced": len(payload.rows_to_add),
            "status": "success",
            "error_message": (
                f"Product IDs: {', '.join(payload.product_ids)} | "
                f"Rows added: {len(payload.rows_to_add)}"
            ),
        })
        return {"detail": f"Successfully added {len(payload.rows_to_add)} rows"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Snapshot Rollback ─────────────────────────────────────────────────────────

@router.get("/snapshot-runs")
def list_snapshot_runs(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    try:
        from planning_suite.services.sync_versioning import SyncVersioning
        versioning = SyncVersioning(db)
        runs = versioning.list_runs(step_name="master_sync", limit=30)
        success_runs = [r for r in runs if r.get("status") == "success"]
        return success_runs
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class RestoreSnapshotPayload(BaseModel):
    run_id: str


@router.post("/restore-snapshot")
def restore_snapshot(
    payload: RestoreSnapshotPayload,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from planning_suite.services.sync_versioning import restore_master_snapshots_to_sheets, list_snapshot_meta
        gsm = get_sheets_manager()
        user_id = int(current_user["sub"])

        meta = list_snapshot_meta(db, payload.run_id)
        results = restore_master_snapshots_to_sheets(
            gsm,
            payload.run_id,
            user_id=user_id,
            db=db,
        )
        failed = [k for k, v in results.items() if v == "failed"]
        missing = [k for k, v in results.items() if v == "missing"]

        if failed or missing:
            raise HTTPException(status_code=400, detail=f"Restore incomplete — failed: {failed}; missing: {missing}")

        db.log_master_sync({
            "master_type": "snapshot_rollback",
            "user_id": user_id,
            "records_synced": sum(m.get("row_count") or 0 for m in meta),
            "status": "success",
            "error_message": f"Restored from sync_run {payload.run_id}",
        })
        return {"detail": "Snapshot restored successfully"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Sync history ───────────────────────────────────────────────────────────────

@router.get("/sync-history")
def get_sync_history(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT msl.id, msl.sync_date, msl.master_type,
                           msl.records_synced, msl.status, msl.error_message,
                           u.full_name as synced_by
                     FROM master_sync_log msl
                     LEFT JOIN users u ON u.id = msl.user_id
                     ORDER BY msl.sync_date DESC
                     LIMIT :limit
                 """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        return []


# ── Master sync trigger ────────────────────────────────────────────────────────

@router.post("/sync")
def trigger_master_sync(
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from planning_suite.automation.master_data_sync import run_master_data_sync
        user_id = int(current_user["sub"])
        result = run_master_data_sync(db=db, user_id=user_id)
        return {"detail": "Master sync complete", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Hub Changes ────────────────────────────────────────────────────────────────

@router.get("/hub-changes")
def get_hub_changes(current_user: dict = Depends(get_current_user)):
    try:
        from planning_suite.services.hub_launch_sync import load_hub_changes_for_baseline
        df = load_hub_changes_for_baseline()
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        return {"rows": df.to_dict(orient="records"), "columns": list(df.columns)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class HubChangesPayload(BaseModel):
    rows: List[dict]


@router.post("/hub-changes")
def save_hub_changes(
    payload: HubChangesPayload,
    current_user: dict = Depends(require_write),
):
    try:
        import pandas as pd
        from planning_suite.services.hub_launch_sync import save_hub_changes_to_sheet
        df = pd.DataFrame(payload.rows)
        save_hub_changes_to_sheet(df)
        return {"detail": "Hub changes saved"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Users (admin only) ────────────────────────────────────────────────────────

@router.get("/users")
def list_users(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("SELECT id, username, full_name, email, role, created_at, last_login FROM users ORDER BY id")
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
