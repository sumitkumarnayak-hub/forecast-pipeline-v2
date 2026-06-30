"""Master Data router — sync, history, hub changes, and sheets operations."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import pandas as pd

from app.deps import get_current_user, require_write, get_db
from planning_suite.db.engine import Database
from planning_suite.services.sheets_session import get_sheets_manager
from planning_suite.core.dataframe import clean_sheet_df, df_to_records
from planning_suite.services.api_cache import CacheNS, cached, cache_invalidate

router = APIRouter()

_SHEET_TTL = 60.0
_DEFAULT_PREVIEW_ROWS = 3000
_MAX_PREVIEW_ROWS = 10_000


def _read_master_worksheet(
    worksheet_key: str,
    range_notation: str,
    *,
    cache_key: str,
    refresh: bool = False,
    limit: int | None = None,
) -> dict:
    preview_limit = limit if limit is not None else _DEFAULT_PREVIEW_ROWS
    preview_limit = max(100, min(int(preview_limit), _MAX_PREVIEW_ROWS))

    def factory() -> dict:
        gsm = get_sheets_manager()
        df = gsm.read_worksheet_to_df("demand_planning_masters", worksheet_key, range_notation)
        if df is None:
            raise HTTPException(
                status_code=503,
                detail=f"Could not read {worksheet_key} from Google Sheets — check credentials and network.",
            )
        if df.empty:
            return {"rows": [], "columns": [], "total_rows": 0, "truncated": False}
        df = clean_sheet_df(df)
        total = len(df)
        if total > preview_limit:
            df = df.head(preview_limit)
        return {
            "rows": df_to_records(df),
            "columns": list(df.columns),
            "total_rows": total,
            "truncated": total > preview_limit,
            "preview_limit": preview_limit,
        }

    try:
        return cached(
            CacheNS.MASTER_SHEET,
            f"{cache_key}:limit={preview_limit}",
            factory,
            ttl=_SHEET_TTL,
            skip_cache=refresh,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

# ── Sheets Reading ─────────────────────────────────────────────────────────────

@router.get("/p-master")
def get_p_master(
    current_user: dict = Depends(get_current_user),
    refresh: bool = Query(False),
    limit: int = Query(_DEFAULT_PREVIEW_ROWS, ge=100, le=_MAX_PREVIEW_ROWS),
):
    return _read_master_worksheet(
        "product_master", "A:K", cache_key="p-master", refresh=refresh, limit=limit
    )


@router.get("/ph-master")
def get_ph_master(
    current_user: dict = Depends(get_current_user),
    refresh: bool = Query(False),
    limit: int = Query(_DEFAULT_PREVIEW_ROWS, ge=100, le=_MAX_PREVIEW_ROWS),
):
    return _read_master_worksheet(
        "product_hub_master", "A:AX", cache_key="ph-master", refresh=refresh, limit=limit
    )


@router.get("/hub-master")
def get_hub_master(
    current_user: dict = Depends(get_current_user),
    refresh: bool = Query(False),
    limit: int = Query(_DEFAULT_PREVIEW_ROWS, ge=100, le=_MAX_PREVIEW_ROWS),
):
    return _read_master_worksheet(
        "hub_mapping", "A:F", cache_key="hub-master", refresh=refresh, limit=limit
    )


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
                result[ws.title] = df_to_records(df)
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
        cache_invalidate(CacheNS.MASTER_SHEET)
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
        cache_invalidate(CacheNS.MASTER_SHEET)
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

LEGACY_MASTER_TYPES = {
    "cluster_mapping": "Cluster mapping",
    "avl_flag": "Availability flag",
    "outlier": "Outlier",
    "city_drops": "City drops",
    "percentile": "Percentile",
    "hub_sku_master": "Hub SKU master",
    "sell_through": "Sell through",
    "hub_changes": "Hub changes",
}


@router.get("/legacy-sync-types")
def list_legacy_sync_types(current_user: dict = Depends(get_current_user)):
    return [{"id": k, "label": v} for k, v in LEGACY_MASTER_TYPES.items()]


@router.post("/sync-legacy/{master_type}")
def sync_legacy_master(
    master_type: str,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    if master_type not in LEGACY_MASTER_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown master type: {master_type}")
    try:
        gsm = get_sheets_manager()
        df = gsm.sync_master_data(master_type)
        row_count = len(df) if df is not None else 0
        user_id = int(current_user["sub"])
        db.log_master_sync({
            "master_type": master_type,
            "user_id": user_id,
            "records_synced": row_count,
            "status": "success" if df is not None else "empty",
        })
        return {
            "detail": f"{LEGACY_MASTER_TYPES[master_type]} synced",
            "master_type": master_type,
            "row_count": row_count,
            "columns": list(df.columns) if df is not None and not df.empty else [],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/sync")
def trigger_master_sync(
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from planning_suite.automation.master_data_sync import run_master_data_sync
        user_id = int(current_user["sub"])
        result = run_master_data_sync(db=db, user_id=user_id)
        if not result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=result.get("error") or "Master sync failed",
            )
        return {"detail": "Master sync complete", "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Hub Changes ────────────────────────────────────────────────────────────────

@router.get("/hub-changes")
def get_hub_changes(current_user: dict = Depends(get_current_user)):
    try:
        from planning_suite.services.hub_launch_sync import load_hub_changes_for_baseline
        gsm = get_sheets_manager()
        df = load_hub_changes_for_baseline(gsm)
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        return {"rows": df_to_records(df), "columns": list(df.columns)}
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
        gsm = get_sheets_manager()
        df = pd.DataFrame(payload.rows)
        gsm.write_hub_changes(df)
        return {"detail": "Hub changes saved"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/new-hub-sync/preview")
def preview_new_hub_sync(current_user: dict = Depends(get_current_user)):
    """Dry-run P-H Master clone for New Hub rows in Hub_Changes tab."""
    try:
        from planning_suite.core.dataframe import sanitize_for_json
        from planning_suite.services.hub_launch_sync import (
            clone_ph_master_from_hub_mappings,
            extract_hub_launch_mappings,
            normalize_hub_changes_df,
        )
        from planning_suite.services.sheets_session import get_sheets_manager

        gsm = get_sheets_manager()
        gsm.ensure_pipeline_params_hub_changes_tab()
        hub_df = normalize_hub_changes_df(gsm.read_hub_changes_table())
        mappings = extract_hub_launch_mappings(hub_df)
        if not mappings:
            return {
                "ok": True,
                "mappings_found": 0,
                "message": "No New Hub rows in Hub Changes — nothing to sync.",
                "rows_to_insert": 0,
                "duplicates_skipped": 0,
                "validation_errors": [],
                "mapping_report": [],
                "mappings": [],
            }

        clone = clone_ph_master_from_hub_mappings(gsm, mappings, dry_run=True)
        return sanitize_for_json(
            {
                "ok": clone.success,
                "mappings_found": len(mappings),
                "mappings": [
                    {"new_hub": m.new_hub, "source_hub": m.source_hub} for m in mappings
                ],
                "rows_to_insert": clone.rows_inserted,
                "duplicates_skipped": clone.duplicates_skipped,
                "validation_errors": clone.validation_errors,
                "mapping_report": clone.mapping_report,
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/new-hub-sync/confirm")
def confirm_new_hub_sync(
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    """Apply new hub P-H Master clone + optional Excel re-sync."""
    try:
        from planning_suite.automation.new_hub_launch_sync import run_new_hub_launch_sync

        user_id = int(current_user["sub"])
        result = run_new_hub_launch_sync(user_id=user_id, db=db, dry_run=False)
        if not result.success:
            raise HTTPException(status_code=400, detail=result.error or "New hub sync failed")
        return {
            "detail": (
                f"New hub sync complete — {result.rows_inserted} row(s) inserted, "
                f"{result.duplicates_skipped} duplicate(s) skipped"
            ),
            "mappings_found": result.mappings_found,
            "rows_inserted": result.rows_inserted,
            "duplicates_skipped": result.duplicates_skipped,
            "masters_re_synced": result.masters_re_synced,
            "mapping_report": result.mapping_report,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
