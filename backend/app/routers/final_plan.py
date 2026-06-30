"""Final Plan router — sync adhoc/inventory inputs, run, history."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File

from app.deps import get_current_user, require_write, get_db
from planning_suite.db.engine import Database

router = APIRouter()


def _fetch_runs(db: Database, limit: int = 20) -> list[dict]:
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


def _fetch_latest_run(db: Database) -> dict | None:
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text

            latest = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file
                    FROM final_plan_runs ORDER BY run_date DESC LIMIT 1
                """)
            ).fetchone()
        return dict(latest._mapping) if latest else None
    except Exception:
        return None


@router.get("/bootstrap")
def final_plan_bootstrap(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Single payload for Final Plan page — status, inputs, previews, history."""
    from planning_suite import config as cfg
    from planning_suite.services.final_plan_engine import (
        get_latest_output_preview,
        load_hub_suggestions_preview,
    )
    from planning_suite.services.final_plan_inputs import (
        get_inputs_status,
        load_city_mapping_preview,
    )
    from planning_suite.services.pipeline_state import is_baseline_approved

    return {
        "baseline_approved": is_baseline_approved(),
        "latest_run": _fetch_latest_run(db),
        "runs": _fetch_runs(db, limit=20),
        "config": {
            "ff_inputs_folder": cfg.FF_INPUTS_FOLDER,
            "ff_inv_logic_folder": cfg.FF_INV_LOGIC_FOLDER,
            "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
            "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
        },
        "inputs": get_inputs_status(),
        "city_mapping": load_city_mapping_preview(limit=150),
        "hub_suggestions": load_hub_suggestions_preview(limit=150),
        "latest_output": get_latest_output_preview(limit=50),
    }


@router.get("/status")
def final_plan_status(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    from planning_suite.services.pipeline_state import is_baseline_approved

    return {"baseline_approved": is_baseline_approved(), "latest_run": _fetch_latest_run(db)}


@router.get("/inputs-status")
def final_plan_inputs_status(current_user: dict = Depends(get_current_user)):
    from planning_suite.services.final_plan_inputs import get_inputs_status

    return get_inputs_status()


@router.get("/city-mapping")
def final_plan_city_mapping(
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    from planning_suite.services.final_plan_inputs import load_city_mapping_preview

    return load_city_mapping_preview(limit=limit)


@router.post("/sync-city-mapping")
def sync_city_mapping(current_user: dict = Depends(require_write)):
    """Export City_Mapping worksheet → FF_INPUTS_FOLDER/City_Mapping.xlsx."""
    try:
        from planning_suite.services.final_plan_inputs import sync_city_mapping_to_folder

        return sync_city_mapping_to_folder()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sync-festive")
def sync_festive(current_user: dict = Depends(require_write)):
    """Ensure Festive.xlsx exists (template if missing)."""
    try:
        from planning_suite.services.final_plan_inputs import sync_festive_placeholder_from_sheet

        return sync_festive_placeholder_from_sheet()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/upload-input")
async def upload_final_plan_input(
    kind: str = Query(..., description="festive | adhoc | adhoc_city_product | adhoc_hub | city_mapping"),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files (.xlsx) are accepted.")
    content = await file.read()
    try:
        from planning_suite.services.final_plan_inputs import save_uploaded_input

        return save_uploaded_input(kind=kind, content=content, filename=file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs")
def get_final_plan_runs(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    return _fetch_runs(db, limit=limit)


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


@router.post("/run")
def run_final_plan(
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    user_id = int(current_user["sub"])
    try:
        from planning_suite.services.final_plan_engine import run_final_plan_engine

        return run_final_plan_engine(user_id=user_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/latest-output")
def latest_final_plan_output(
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    from planning_suite.services.final_plan_engine import get_latest_output_preview

    return get_latest_output_preview(limit=limit)


@router.get("/hub-suggestions")
def hub_suggestions_preview(
    limit: int = 200,
    current_user: dict = Depends(get_current_user),
):
    from planning_suite.services.final_plan_engine import load_hub_suggestions_preview

    return load_hub_suggestions_preview(limit=limit)


@router.post("/sync-inv-buffer")
def sync_inv_buffer(current_user: dict = Depends(require_write)):
    """Sync inventory buffer worksheets to local Excel."""
    try:
        from pathlib import Path
        import pandas as pd
        from planning_suite.config import INV_LOGICS_SHEET_KEY, FF_INV_LOGIC_FOLDER
        from planning_suite.core.dataframe import clean_sheet_df
        from planning_suite.services.sheets_session import get_sheets_manager

        gsm = get_sheets_manager()
        ss = gsm.gc.open_by_key(INV_LOGICS_SHEET_KEY)
        out_dir = Path(FF_INV_LOGIC_FOLDER)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for ws in ss.worksheets():
            data = ws.get_all_values()
            if not data:
                continue
            df = pd.DataFrame(data[1:], columns=data[0])
            df = clean_sheet_df(df)
            out_path = out_dir / f"{ws.title}.xlsx"
            with pd.ExcelWriter(str(out_path), engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name=ws.title[:30], index=False)
            written.append(ws.title)
        return {"detail": f"Synced {len(written)} inventory buffer tabs", "files": written}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
