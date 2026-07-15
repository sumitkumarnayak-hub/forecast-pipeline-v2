"""New Product Launch router — upload, masters, salience, auto-sync."""
from __future__ import annotations

import io
import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from pydantic import BaseModel

from app.dependencies import get_current_user, require_write, get_db
from core.utils.dataframe import df_to_records

from core.database.engine import Database


router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/cache-status")
def get_npl_cache_status(current_user: dict = Depends(get_current_user)):
    """Expose details of parquet sheets_cache, modification dates, and defined TTLs by scanning cache dir."""
    import time
    import os
    from pathlib import Path
    from core.shared import sheets_cache as sheets_cache

    from app import config as cfg

    
    # Files of interest
    cached_sheets = [
        {"worksheet": "P Master", "category": "demand_planning_masters"},
        {"worksheet": "P-L Master", "category": "demand_planning_masters"},
        {"worksheet": "P-H Master", "category": "demand_planning_masters"},
        {"worksheet": "Hub Mapping", "category": "demand_planning_masters"},
        {"worksheet": "Hub_Changes", "category": "pipeline_params"},
        {"worksheet": "Variables", "category": "pipeline_params"},
        {"worksheet": "Submission_Log", "category": "npl_log"},
        {"worksheet": "Hub level Suggestion", "category": "dp_logics"},
        {"worksheet": "Launch_Output", "category": "npl_log"},
        {"worksheet": "City_Plan", "category": "npl_log"},
        {"worksheet": "Hub_Plan", "category": "npl_log"},
    ]
    
    # Scan the sheets_cache directory for any files matching the worksheet names
    cache_dir = sheets_cache._cache_dir()
    cache_files = list(cache_dir.glob("*.parquet")) if cache_dir.exists() else []
    
    status_list = []
    for s in cached_sheets:
        name = s["worksheet"]
        category = s["category"]
        ttl = sheets_cache.ttl_for_worksheet(name, category)
        
        # Match cache files by suffix matching the normalized worksheet name
        match_suffix = f"_{name.replace(' ', '_')}.parquet"
        active_path = None
        for p in cache_files:
            if p.name.endswith(match_suffix):
                active_path = p
                break
                
        last_updated = "Never Fetched"
        is_fresh = False
        if active_path:
            try:
                mtime = active_path.stat().st_mtime
                age = time.time() - mtime
                is_fresh = age <= ttl
                # Return ISO 8601 UTC so frontend can reformat in user's locale/timezone
                last_updated = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mtime))
            except Exception:
                pass
            
        # Frequency formatting
        if ttl >= 3600:
            freq = f"Every {ttl // 3600} hr(s)"
        else:
            freq = f"Every {ttl // 60} min(s)"
            
        status_list.append({
            "name": name,
            "category": category,
            "last_updated": last_updated,
            "fresh": is_fresh,
            "frequency": freq,
            "ttl": ttl
        })
        
    return {"cache_status": status_list}


@router.get("/info")
def npl_info(current_user: dict = Depends(get_current_user), db: Database = Depends(get_db)):
    """Return sheet URL and last sync timestamp for the NPL page header."""
    from app.config import NEW_PRODUCT_LAUNCH_SHEET_URL, DEMAND_PLANNING_MASTERS_SHEET_URL, NEW_HUB_LAUNCH_SHEET_URL
    import time
    from core.shared import sheets_cache as sheets_cache


    # Resolve local cache modified time for Hub Launch
    cache_path = sheets_cache.cache_path_for_category("new_hub_launch", "ff_input", "A:H")
    cache_last_updated = None
    if cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            cache_last_updated = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mtime))
        except Exception:
            pass

    # Fetch last sync from master_sync_log for ph_master or npl-related types
    last_sync: str | None = None
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text as _text
            row = conn.execute(_text("""
                SELECT sync_date FROM master_sync_log
                WHERE master_type IN ('ph_master_sync', 'npl_auto_sync', 'new_product_launch_sync', 'new_hub_sync')
                ORDER BY sync_date DESC
                LIMIT 1
            """)).fetchone()
            if row and row[0]:
                ts = row[0]
                last_sync = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
    except Exception:
        pass

    return {
        "npl_sheet_url": NEW_PRODUCT_LAUNCH_SHEET_URL or None,
        "new_hub_sheet_url": NEW_HUB_LAUNCH_SHEET_URL or None,
        "ph_master_sheet_url": DEMAND_PLANNING_MASTERS_SHEET_URL or None,
        "last_synced": last_sync,
        "cache_last_updated": cache_last_updated,
    }


@router.post("/upload")
async def upload_npl_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are accepted")

    contents = await file.read()
    try:
        import pandas as pd
        from features.product_launch.core import validate_npl_upload


        df = pd.read_excel(io.BytesIO(contents))
        result = validate_npl_upload(df)
        if not result.get("valid"):
            raise HTTPException(status_code=422, detail=result.get("errors", ["Validation failed"]))
        return {
            "filename": file.filename,
            "rows": len(df),
            "columns": list(df.columns),
            "validation": result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/submissions")
def get_submissions(current_user: dict = Depends(get_current_user)):
    try:
        from core.shared.google_sheets import GoogleSheetsManager

        from app import config as cfg


        gsm = GoogleSheetsManager()
        df = gsm.read_worksheet(cfg.HUB_LEVEL_PLANNING_SHEET_URL, "Launch_Output")
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        return {"rows": df_to_records(df.head(200)), "columns": list(df.columns)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_NPL_CACHE_TTL = 600.0
_NPL_LOG_CACHE_TTL = 90.0


@router.get("/masters/categories")
def npl_categories(current_user: dict = Depends(get_current_user)):
    from core.shared.api_cache import CacheNS, cached

    from features.product_launch import wizard as wiz


    try:
        categories = cached(CacheNS.NPL_WIZARD, "categories", wiz.list_categories, ttl=_NPL_CACHE_TTL)
        return {"categories": categories}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/masters/products")
def npl_products(
    category: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    from core.shared.api_cache import CacheNS, cached

    from features.product_launch.core import get_products_by_category, load_product_master


    try:
        def _products() -> list:
            df = load_product_master()
            return get_products_by_category(df, category)

        products = cached(CacheNS.NPL_WIZARD, f"products:{category}", _products, ttl=_NPL_CACHE_TTL)
        return {"products": products}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/masters/product-ids")
def npl_all_product_ids(current_user: dict = Depends(get_current_user)):
    from core.shared.api_cache import CacheNS, cached

    from features.product_launch import wizard as wiz


    products = cached(CacheNS.NPL_WIZARD, "product_ids", wiz.list_all_product_ids, ttl=_NPL_CACHE_TTL)
    return {"products": products}


@router.get("/salience/cities")
def npl_salience_cities(current_user: dict = Depends(get_current_user)):
    try:
        from features.product_launch.core import get_cities_from_salience, load_salience_source


        sal = load_salience_source()
        return {"cities": get_cities_from_salience(sal)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/salience/hubs")
def npl_salience_hubs(
    city: str = Query(...),
    category: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    try:
        from features.product_launch.core import get_hubs_for_city, load_salience_source


        sal = load_salience_source()
        return {"hubs": get_hubs_for_city(sal, city, category)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class PreviewPhSyncBody(BaseModel):
    product_ids: List[str]


@router.post("/sync-ph/preview")
def npl_preview_ph_sync(
    body: PreviewPhSyncBody,
    current_user: dict = Depends(require_write),
):
    try:
        from features.product_launch.sync import (
            build_new_product_ph_preview,
            load_masters_for_product_sync,
        )
        from core.shared.sheets_session import get_sheets_manager


        gsm = get_sheets_manager()
        p_df, hub_df, ph_df = load_masters_for_product_sync(gsm)
        svc = build_new_product_ph_preview(p_df, hub_df, ph_df, product_ids=body.product_ids)
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ConfirmPhSyncBody(BaseModel):
    rows_to_add: List[dict]
    ph_headers: List[str]
    product_ids: List[str]


@router.post("/sync-ph/confirm")
def npl_confirm_ph_sync(
    body: ConfirmPhSyncBody,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from app.config import DPM_SHEET_KEY
        from core.shared.sheets_session import get_sheets_manager


        gsm = get_sheets_manager()
        ss = gsm.gc.open_by_key(DPM_SHEET_KEY)
        ph_ws = ss.worksheet("P-H Master")
        values = [[r.get(h, "") for h in body.ph_headers] for r in body.rows_to_add]
        gsm.append_rows_to_worksheet(
            "demand_planning_masters",
            "product_hub_master",
            values,
            worksheet=ph_ws,
            value_input_option="RAW",
        )
        user_id = int(current_user["sub"])
        db.log_master_sync(
            {
                "master_type": "ph_master_sync",
                "user_id": user_id,
                "records_synced": len(body.rows_to_add),
                "status": "success",
                "error_message": (
                    f"NPL sync — Product IDs: {', '.join(body.product_ids)} | "
                    f"Rows added: {len(body.rows_to_add)}"
                ),
            }
        )
        return {"detail": f"Successfully added {len(body.rows_to_add)} rows to P-H Master"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class AutoSyncBody(BaseModel):
    product_ids: List[str] = []
    dry_run: bool = False


@router.post("/auto-sync")
def npl_auto_sync(
    body: AutoSyncBody,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from features.product_launch.auto_sync import run_new_product_launch_sync_cli


        user_id = int(current_user["sub"])
        pids = body.product_ids or None
        result = run_new_product_launch_sync_cli(
            user_id=user_id,
            db=db,
            dry_run=body.dry_run,
            product_ids=pids,
        )
        return {
            "success": result.success,
            "products_found": result.products_found,
            "rows_inserted": result.rows_inserted,
            "duplicates_skipped": result.duplicates_skipped,
            "masters_re_synced": result.masters_re_synced,
            "ph_rows_after": result.ph_rows_after,
            "products_synced": result.products_synced,
            "error": result.error,
            "dry_run": body.dry_run,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ConfirmHubSyncBody(BaseModel):
    rows_to_add: List[dict]
    ph_headers: List[str]


@router.get("/sync-new-hub/preview")
def npl_preview_new_hub_sync(
    bypass_cache: bool = Query(False),
    current_user: dict = Depends(require_write),
):
    t0 = time.perf_counter()
    try:
        from core.shared.sheets_session import get_sheets_manager

        from features.final_plan.hub_sync import build_new_hub_sync_preview


        gsm = get_sheets_manager()
        result = build_new_hub_sync_preview(gsm, bypass_cache=bypass_cache)
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("[HubSync] preview completed in %dms bypass_cache=%s", elapsed, bypass_cache)
        result["_elapsed_ms"] = elapsed
        return result
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[HubSync] preview failed in %dms: %s", elapsed, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sync-new-hub/ff-input")
def npl_ff_input_data(
    bypass_cache: bool = Query(False),
    current_user: dict = Depends(require_write),
):
    """
    Returns raw FF Input sheet data rows for display in Hub Launch tab,
    along with a content hash for client-side change detection.
    """
    import hashlib, json
    t0 = time.perf_counter()
    try:
        from core.shared.sheets_session import get_sheets_manager

        from core.shared import sheets_cache as sheets_cache

        from app import config as cfg


        gsm = get_sheets_manager()
        use_cache = not bypass_cache

        ff_df = gsm.read_worksheet_uncached("new_hub_launch", "ff_input", "A:H", use_cache=use_cache)

        if ff_df is None or ff_df.empty:
            raw = gsm.batch_read_worksheets(cfg.NEW_HUB_LAUNCH_SHEET_KEY, [("FF Input", "A:H")])
            data = raw.get("FF Input") or []
            if len(data) >= 2:
                import pandas as pd
                from core.utils.dataframe import clean_sheet_df

                ff_df = clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))

        rows = []
        headers = []
        content_hash = ""
        cache_last_updated = None

        if ff_df is not None and not ff_df.empty:
            ff_df = ff_df.dropna(how="all")
            headers = list(ff_df.columns)
            rows = ff_df.where(ff_df.notna(), "").to_dict(orient="records")
            # Build content hash for change detection
            serialized = json.dumps(rows, sort_keys=True, default=str)
            content_hash = hashlib.sha256(serialized.encode()).hexdigest()

        # Resolve cache mtime for display
        cache_path = sheets_cache.cache_path_for_category("new_hub_launch", "ff_input", "A:H")
        if cache_path.exists():
            try:
                mtime = cache_path.stat().st_mtime
                cache_last_updated = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mtime))
            except Exception:
                pass

        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("[HubSync] ff-input fetched %d rows in %dms", len(rows), elapsed)

        return {
            "rows": rows,
            "headers": headers,
            "row_count": len(rows),
            "content_hash": content_hash,
            "cache_last_updated": cache_last_updated,
            "_elapsed_ms": elapsed,
        }
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[HubSync] ff-input failed in %dms: %s", elapsed, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sync-new-hub/change-status")
def npl_ff_input_change_status(current_user: dict = Depends(get_current_user)):
    """
    Returns the current FF Input change watcher state for frontend polling.
    Frontend should call this every ~30 seconds to detect new changes automatically.
    """
    try:
        from features.product_launch.watcher import get_change_status

        status = get_change_status()
        return {
            "change_detected": status["change_detected"],
            "change_history": status["change_history"],
            "last_checked_at": status["last_checked_at"],
            "watcher_started": status["watcher_started"],
            "poll_interval_seconds": status["poll_interval_seconds"],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sync-new-hub/dismiss-changes")
def npl_dismiss_ff_input_changes(current_user: dict = Depends(require_write)):
    """
    Clears the change_detected flag. Version history is preserved.
    Call this when user clicks Dismiss on the notification banner.
    """
    try:
        from features.product_launch.watcher import dismiss_changes

        dismiss_changes()
        return {"ok": True, "message": "Change notification dismissed. History preserved."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sync-new-hub/confirm")

def npl_confirm_new_hub_sync(
    body: ConfirmHubSyncBody,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    try:
        from app.config import DPM_SHEET_KEY
        from core.shared.sheets_session import get_sheets_manager


        gsm = get_sheets_manager()
        ss = gsm.gc.open_by_key(DPM_SHEET_KEY)
        ph_ws = ss.worksheet("P-H Master")
        values = [[r.get(h, "") for h in body.ph_headers] for r in body.rows_to_add]
        
        if values:
            gsm.append_rows_to_worksheet(
                "demand_planning_masters",
                "product_hub_master",
                values,
                worksheet=ph_ws,
                value_input_option="RAW",
            )
            
        # Warm up cached data asynchronously in a background task
        if values:
            from fastapi import BackgroundTasks
            # We can invoke cache warmups to fetch a fresh dataframe copy in the background
            def warmup_cache():
                try:
                    # Read with use_cache=False to force a reload from Sheets, which auto-overwrites the cached Parquet file
                    gsm.read_worksheet_uncached("demand_planning_masters", "product_hub_master", use_cache=False)
                except Exception:
                    pass
            
            # Start background thread execution to warm up the cache immediately
            import threading
            threading.Thread(target=warmup_cache, daemon=True).start()

        user_id = int(current_user["sub"])
        db.log_master_sync(
            {
                "master_type": "new_hub_sync",
                "user_id": user_id,
                "records_synced": len(body.rows_to_add),
                "status": "success",
                "error_message": f"New Hub Sync: Appended {len(body.rows_to_add)} rows from FF Input sheet configuration.",
            }
        )
        return {
            "success": True,
            "rows_inserted": len(body.rows_to_add),
            "detail": f"Successfully synced {len(body.rows_to_add)} new hub rows to P-H Master.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Wizard (4-stage launch flow) ───────────────────────────────────────────────

class TemplateCityBody(BaseModel):
    cities: List[str]
    category: str
    product_id: str = ""
    product_name: str = ""


class TemplateHubBody(BaseModel):
    cities_hubs: dict[str, List[str]]
    category: str
    product_id: str = ""
    product_name: str = ""


class SplitCityBody(BaseModel):
    city_rows: List[dict]
    forced_hubs: dict[str, List[str]] | None = None


class HubRowsBody(BaseModel):
    hub_rows: List[dict]


class SubmitBody(BaseModel):
    hub_rows: List[dict]
    sub_type: str = "New Launch"
    launch_date: str | None = None
    send_email: bool = True
    plan_level: str | None = None


class StatusBody(BaseModel):
    status: str
    reason: str = ""


@router.get("/wizard/context")
def wizard_context(current_user: dict = Depends(get_current_user)):
    from core.shared.api_cache import CacheNS, cached

    from features.product_launch import wizard as wiz


    return cached(CacheNS.NPL_WIZARD, "context", wiz.wizard_context_payload, ttl=_NPL_CACHE_TTL)


@router.get("/wizard/hubs")
def wizard_hubs(
    city: str,
    category: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    from features.product_launch import wizard as wiz


    return {"hubs": wiz.list_hubs_for_city(city, category)}


@router.post("/wizard/template/city")
def wizard_template_city(body: TemplateCityBody, current_user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    from features.product_launch import wizard as wiz


    data = wiz.city_template_bytes(body.cities, body.category, product_id=body.product_id, product_name=body.product_name)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="city_template_{body.category}.xlsx"'},
    )


@router.post("/wizard/template/hub")
def wizard_template_hub(body: TemplateHubBody, current_user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    from features.product_launch import wizard as wiz


    data = wiz.hub_template_bytes(body.cities_hubs, body.category, product_id=body.product_id, product_name=body.product_name)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="hub_template_{body.category}.xlsx"'},
    )


@router.post("/wizard/parse-city")
async def wizard_parse_city(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
):
    from features.product_launch import wizard as wiz


    t0 = time.perf_counter()
    content = await file.read()
    try:
        result = wiz.parse_city_file(content)
        elapsed = round((time.perf_counter() - t0) * 1000)
        if not result.get("ok"):
            errors = result.get("errors", ["Parse failed"])
            err_str = "; ".join(errors) if isinstance(errors, list) else str(errors)
            logger.warning("[NPL] parse-city failed in %dms: %s", elapsed, err_str)
            raise HTTPException(status_code=422, detail=errors)
        logger.info("[NPL] parse-city OK — %d rows in %dms", result.get("row_count", 0), elapsed)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[NPL] parse-city crashed in %dms", elapsed)
        _fire_step_fail("Parse City File", str(exc), current_user)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wizard/parse-hub")
async def wizard_parse_hub(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
):
    from features.product_launch import wizard as wiz


    t0 = time.perf_counter()
    content = await file.read()
    try:
        result = wiz.parse_hub_file(content)
        elapsed = round((time.perf_counter() - t0) * 1000)
        if not result.get("ok"):
            errors = result.get("errors", ["Parse failed"])
            err_str = "; ".join(errors) if isinstance(errors, list) else str(errors)
            logger.warning("[NPL] parse-hub failed in %dms: %s", elapsed, err_str)
            raise HTTPException(status_code=422, detail=errors)
        logger.info("[NPL] parse-hub OK — %d rows in %dms", result.get("row_count", 0), elapsed)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[NPL] parse-hub crashed in %dms", elapsed)
        _fire_step_fail("Parse Hub File", str(exc), current_user)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wizard/split-city")
def wizard_split_city(body: SplitCityBody, current_user: dict = Depends(require_write)):
    from features.product_launch import wizard as wiz


    t0 = time.perf_counter()
    try:
        result = wiz.split_city_rows(body.city_rows, forced_hubs=body.forced_hubs)
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("[NPL] split-city OK — %d hub rows in %dms", result.get("row_count", 0), elapsed)
        return result
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[NPL] split-city crashed in %dms", elapsed)
        _fire_step_fail("City → Hub Split", str(exc), current_user)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wizard/check-duplicates")
def wizard_check_dupes(
    body: HubRowsBody,
    sub_type: str = "New Launch",
    plan_level: str = "hub",
    current_user: dict = Depends(require_write),
):
    from features.product_launch import wizard as wiz


    t0 = time.perf_counter()
    try:
        result = wiz.check_duplicates(body.hub_rows, sub_type=sub_type, plan_level=plan_level)
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("[NPL] check-duplicates OK — has_dupes=%s in %dms", result.get("has_duplicates"), elapsed)
        return result
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[NPL] check-duplicates crashed in %dms", elapsed)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/wizard/preview-sync")
def wizard_preview_sync(
    body: SubmitBody,
    current_user: dict = Depends(require_write),
):
    from app import config as cfg

    from features.product_launch.core import _open_sheet

    from datetime import datetime

    t0 = time.perf_counter()
    username = current_user.get("email") or current_user.get("username") or current_user.get("full_name") or ""
    try:
        from features.product_launch import wizard as wiz

        # 1. Apply launch dates
        rows = wiz.apply_launch_dates(body.hub_rows, body.launch_date)

        # 2. Aggregate hub rows to city rows for City_Plan sheet
        WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        aggregated_sources = {}
        for source in rows:
            pid = str(source.get("product_id", "")).strip()
            pname = source.get("product_name", "")
            cat = source.get("category", "")
            city = source.get("city_name", "")
            mrp = source.get("MRP", "")
            start_date = source.get("Launch Date", "")
            
            group_key = (body.sub_type, pid, pname, cat, city, mrp, start_date)
            if group_key not in aggregated_sources:
                aggregated_sources[group_key] = {
                    "Submission_Type": body.sub_type,
                    "Product ID": pid,
                    "Product Name": pname,
                    "Category": cat,
                    "City": city,
                    "MRP": mrp,
                    "Start Date": start_date,
                    "Submitted_By": username,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Mon": 0, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0
                }
            for day in WEEKDAYS:
                try:
                    val = int(float(source.get(day, 0) or 0))
                except Exception:
                    val = 0
                aggregated_sources[group_key][day] += val

        # 3. Determine level target tab based on body.plan_level (default to hub check)
        if body.plan_level == "city":
            target_worksheet = "City_Plan"
        elif body.plan_level == "hub":
            target_worksheet = "Hub_Plan"
        else:
            has_hubs = any(str(r.get("hub_name", "")).strip() for r in rows)
            target_worksheet = "Hub_Plan" if has_hubs else "City_Plan"

        plan_sheet = _open_sheet(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY, target_worksheet)
        sheet_sample = plan_sheet.get("A1:AP5")
        header_row_idx = 1
        for idx, r in enumerate(sheet_sample, 1):
            normalized_row = [str(x).strip().upper() for x in r]
            if any(h in normalized_row for h in ["OWNER", "PRODUCT_ID", "PRODUCT ID", "SKU"]):
                header_row_idx = idx
                break
        sheet_headers = [str(h).strip() for h in plan_sheet.row_values(header_row_idx)]
        while sheet_headers and not sheet_headers[-1]:
            sheet_headers.pop()
        columns = list(sheet_headers)

        # 4. Fetch Product Master details map ONCE outside the loop to prevent loading ages
        pm_details_map = _get_product_master_details_map()

        # 5. Build preview rows matching target layout dynamically
        preview_records = []
        update_date = datetime.now().strftime("%Y-%m-%d")
        for source in rows:
            row_source = {
                "Submission_Type": body.sub_type,
                "Product ID": str(source.get("product_id", "")).strip(),
                "Product Name": source.get("product_name", ""),
                "Category": source.get("category", ""),
                "City": source.get("city_name", ""),
                "Hub": str(source.get("hub_name", "")).strip(),
                "MRP": source.get("MRP", ""),
                "Start Date": source.get("Launch Date", ""),
                "Submitted_By": username,
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Mon": source.get("Mon", 0),
                "Tue": source.get("Tue", 0),
                "Wed": source.get("Wed", 0),
                "Thu": source.get("Thu", 0),
                "Fri": source.get("Fri", 0),
                "Sat": source.get("Sat", 0),
                "Sun": source.get("Sun", 0),
                "_owner_email": "",
            }
            if target_worksheet == "Hub_Plan":
                row_vals = _build_hub_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
            else:
                # Group/aggregate logic for City level is pre-grouped if needed, but we build dynamically
                row_vals = _build_city_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
                
            record = {}
            for col_name, val in zip(sheet_headers, row_vals):
                if str(col_name).strip():
                    record[str(col_name).strip()] = val
            preview_records.append(record)

        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("[NPL] preview-sync OK — %d rows in %dms", len(preview_records), elapsed)
        return {"rows": preview_records, "columns": columns, "preview_ms": elapsed}
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[NPL] preview-sync crashed in %dms", elapsed)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/wizard/submit")
def wizard_submit(
    body: SubmitBody,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    from features.product_launch import wizard as wiz

    from datetime import datetime
    from app import config as cfg

    from features.product_launch.core import _open_sheet, update_submission_status


    sync_started = datetime.now().isoformat()
    t0 = time.perf_counter()
    username = current_user.get("email") or current_user.get("username") or current_user.get("full_name") or ""
    user_id = int(current_user["sub"])
    sub_id = ""

    steps_status = {
        "sheets": {"status": "idle", "duration_ms": 0},
        "db": {"status": "idle", "duration_ms": 0},
        "email": {"status": "idle", "detail": ""}
    }

    # Step 1: Sync to Google Sheets (Launch_Output, Submission_Log AND City_Plan directly)
    t_sheets = time.perf_counter()
    try:
        rows = wiz.apply_launch_dates(body.hub_rows, body.launch_date)
        
        # 1.1 Append to Submission_Log and Launch_Output
        result = wiz.submit_hub_rows(
            rows,
            sub_type=body.sub_type,
            username=username,
            user_id=user_id,
            send_email=False,
        )
        sub_id = result.get("submission_id", "")
        product_name = result.get("product_name", "")
        hub_count = result.get("rows", 0)

        # 1.2 Aggregate hub rows to city rows for direct City_Plan sync
        WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        aggregated_sources = {}
        for source in rows:
            pid = str(source.get("product_id", "")).strip()
            pname = source.get("product_name", "")
            cat = source.get("category", "")
            city = source.get("city_name", "")
            mrp = source.get("MRP", "")
            start_date = source.get("Launch Date", "")
            
            group_key = (body.sub_type, pid, pname, cat, city, mrp, start_date)
            if group_key not in aggregated_sources:
                aggregated_sources[group_key] = {
                    "Submission_Type": body.sub_type,
                    "Product ID": pid,
                    "Product Name": pname,
                    "Category": cat,
                    "City": city,
                    "MRP": mrp,
                    "Start Date": start_date,
                    "Submitted_By": username,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Mon": 0, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0
                }
            for day in WEEKDAYS:
                try:
                    val = int(float(source.get(day, 0) or 0))
                except Exception:
                    val = 0
                aggregated_sources[group_key][day] += val

        # 1.3 Determine level target tab based on body.plan_level (default to hub check)
        if body.plan_level == "city":
            target_worksheet = "City_Plan"
        elif body.plan_level == "hub":
            target_worksheet = "Hub_Plan"
        else:
            has_hubs = any(str(r.get("hub_name", "")).strip() for r in rows)
            target_worksheet = "Hub_Plan" if has_hubs else "City_Plan"

        plan_sheet = _open_sheet(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY, target_worksheet)
        sheet_sample = plan_sheet.get("A1:AP5")
        header_row_idx = 1
        for idx, r in enumerate(sheet_sample, 1):
            normalized_row = [str(x).strip().upper() for x in r]
            if any(h in normalized_row for h in ["OWNER", "PRODUCT_ID", "PRODUCT ID", "SKU"]):
                header_row_idx = idx
                break
        sheet_headers = [str(h).strip() for h in plan_sheet.row_values(header_row_idx)]
        # Filter out trailing empty columns
        while sheet_headers and not sheet_headers[-1]:
            sheet_headers.pop()
        
        all_rows = plan_sheet.get_all_values()
        existing_keys = set()
        for row in all_rows[header_row_idx:]:
            if len(row) < len(sheet_headers):
                row = row + [""] * (len(sheet_headers) - len(row))
            if target_worksheet == "Hub_Plan":
                key = _npl_hub_plan_key_dynamic(row, sheet_headers)
            else:
                key = _npl_city_plan_key(row, sheet_headers)
            if key:
                existing_keys.add(key)

        # 1.4 Fetch Product Master details map ONCE outside the loop
        pm_details_map = _get_product_master_details_map()

        values_to_append = []
        update_date = datetime.now().strftime("%Y-%m-%d")
        for source in rows:
            row_source = {
                "Submission_Type": body.sub_type,
                "Product ID": str(source.get("product_id", "")).strip(),
                "Product Name": source.get("product_name", ""),
                "Category": source.get("category", ""),
                "City": source.get("city_name", ""),
                "Hub": str(source.get("hub_name", "")).strip(),
                "MRP": source.get("MRP", ""),
                "Start Date": source.get("Launch Date", ""),
                "Submitted_By": username,
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "Mon": source.get("Mon", 0),
                "Tue": source.get("Tue", 0),
                "Wed": source.get("Wed", 0),
                "Thu": source.get("Thu", 0),
                "Fri": source.get("Fri", 0),
                "Sat": source.get("Sat", 0),
                "Sun": source.get("Sun", 0),
                "_owner_email": current_user.get("email", current_user.get("sub", "")),
            }
            if target_worksheet == "Hub_Plan":
                row_vals = _build_hub_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
                key = _npl_hub_plan_key_dynamic(row_vals, sheet_headers)
            else:
                row_vals = _build_city_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
                key = _npl_city_plan_key(row_vals, sheet_headers)
                
            if key and key in existing_keys:
                continue
            values_to_append.append(row_vals)

        if values_to_append:
            plan_sheet.append_rows(values_to_append, value_input_option="USER_ENTERED", table_range=f"A{header_row_idx}")

        # 1.5 Mark submission status as Approved (or Synced) immediately
        update_submission_status(sub_id, "Approved", "Directly Synced via Wizard")

        steps_status["sheets"] = {
            "status": "success",
            "duration_ms": round((time.perf_counter() - t_sheets) * 1000)
        }
    except Exception as exc:
        steps_status["sheets"] = {
            "status": "error",
            "duration_ms": round((time.perf_counter() - t_sheets) * 1000),
            "error": str(exc)
        }
        _fire_step_fail("Submit to Google Sheets", str(exc), current_user, sub_type=body.sub_type)
        raise HTTPException(status_code=500, detail={
            "message": f"Google Sheets Sync failed: {str(exc)}",
            "steps": steps_status
        })

    # Step 2: Persist to Supabase Database (Auto-Approved status)
    t_db = time.perf_counter()
    try:
        import pandas as pd
        hub_df = pd.DataFrame(rows)
        cities = sorted(hub_df["city_name"].dropna().astype(str).unique().tolist()) if "city_name" in hub_df.columns else []
        product_id = str(hub_df["product_id"].iloc[0]) if "product_id" in hub_df.columns and len(hub_df) else ""
        category = str(hub_df["category"].iloc[0]) if "category" in hub_df.columns and len(hub_df) else ""
        launch_dates = sorted(hub_df["Launch Date"].dropna().astype(str).unique().tolist()) if "Launch Date" in hub_df.columns else []
        start_date = launch_dates[0] if launch_dates else ""

        db.save_npl_submission(
            submission_id=sub_id,
            sub_type=body.sub_type,
            product_id=product_id,
            product_name=product_name,
            category=category,
            cities=cities,
            hub_count=hub_count,
            start_date=start_date,
            submitted_by=username,
            user_id=user_id,
            step_log={
                "submit_ms": round((time.perf_counter() - t0) * 1000),
                "sync_started_at": sync_started,
                "sync_completed_at": datetime.now().isoformat(),
                "sync_duration_ms": round((time.perf_counter() - t0) * 1000),
                "status": "Approved",
                "email_requested": body.send_email,
            },
        )
        db.update_npl_submission_status(sub_id, "Approved", "Directly Synced via Wizard")
        steps_status["db"] = {
            "status": "success",
            "duration_ms": round((time.perf_counter() - t_db) * 1000)
        }
    except Exception as exc:
        steps_status["db"] = {
            "status": "error",
            "duration_ms": round((time.perf_counter() - t_db) * 1000),
            "error": str(exc)
        }
        raise HTTPException(status_code=500, detail={
            "message": f"Database Register failed: {str(exc)}",
            "steps": steps_status
        })

    # Step 3: Trigger Email Notifications
    t_email = time.perf_counter()
    if body.send_email:
        try:
            from core.shared.workflow_notifications import notify_npl_submitted

            background_tasks.add_task(
                notify_npl_submitted,
                sub_id=sub_id,
                sub_type=body.sub_type,
                product_name=product_name,
                product_id=product_id,
                launch_dates=launch_dates,
                cities=cities,
                hub_count=hub_count,
                submitted_by=username,
                user_id=user_id,
                db=db,
            )
            steps_status["email"] = {
                "status": "success",
                "detail": "queued",
                "duration_ms": round((time.perf_counter() - t_email) * 1000)
            }
        except Exception as exc:
            steps_status["email"] = {
                "status": "error",
                "error": str(exc),
                "duration_ms": round((time.perf_counter() - t_email) * 1000)
            }
    else:
        steps_status["email"] = {
            "status": "success",
            "detail": "skipped",
            "duration_ms": 0
        }

    return {
        "submission_id": sub_id,
        "steps": steps_status,
        "rows": hub_count,
        "product_name": product_name,
        "email": {"status": "queued"} if body.send_email else {"status": "skipped"}
    }


@router.get("/submissions/log")
def submissions_log(
    types: str | None = None,
    statuses: str | None = None,
    product_ids: str | None = None,
    submission_id: str | None = None,
    view: str = Query("summary", pattern="^(summary|detail)$"),
    source: str = Query("db", pattern="^(db|sheets)$"),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Get submission log. source=db (default) reads from Supabase npl_submissions (fast).
    source=sheets reads from Google Sheets Submission_Log (legacy/fallback).
    """
    t = [x.strip() for x in types.split(",") if x.strip()] if types else None
    s = [x.strip() for x in statuses.split(",") if x.strip()] if statuses else None
    p = [x.strip() for x in product_ids.split(",") if x.strip()] if product_ids else None

    # Fast DB path (default)
    if source == "db":
        try:
            df = db.get_npl_submissions(
                types=t, statuses=s, product_ids=p, submission_id=submission_id
            )
            if not df.empty:
                return _format_db_submissions(df, view=view)
            # Fall through to Sheets if DB is empty (first-time / not yet migrated)
        except Exception:
            logger.warning("[NPL] DB submissions query failed, falling back to Sheets", exc_info=True)

    # Sheets fallback
    from core.shared.api_cache import CacheNS, cache_invalidate, cached

    from features.product_launch import wizard as wiz


    cache_key = f"log:{view}:{submission_id or ''}:{types or ''}:{statuses or ''}:{product_ids or ''}"

    def _log():
        return wiz.get_submission_log(
            types=t, statuses=s, product_ids=p,
            submission_id=submission_id, view=view,
        )

    return cached(CacheNS.NPL_WIZARD, cache_key, _log, ttl=_NPL_LOG_CACHE_TTL)


@router.patch("/submissions/{submission_id}/status")
def patch_submission_status(
    submission_id: str,
    body: StatusBody,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    from core.security.permissions import can_approve

    from features.product_launch import wizard as wiz


    admin_actions = {"Approved", "Rejected", "Voided"}
    if body.status in admin_actions and not can_approve(current_user.get("role", "")):
        raise HTTPException(status_code=403, detail="Admin approval required")
    try:
        # Update Google Sheets
        wiz.set_submission_status(submission_id, body.status, body.reason)
        # Update Supabase
        db.update_npl_submission_status(submission_id, body.status, body.reason)
        
        append_res = None
        if body.status == "Approved":
            append_res = _append_approved_to_new_product_launch(submission_id)
            
        from core.shared.api_cache import CacheNS, cache_invalidate

        cache_invalidate(CacheNS.NPL_WIZARD)
        username = current_user.get("email") or current_user.get("username") or current_user.get("full_name") or ""
        logger.info("[NPL] submission %s -> %s by user %s", submission_id, body.status, username)
        return {
            "detail": f"Submission {submission_id} -> {body.status}",
            "status": body.status,
            "append": append_res,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Helpers ───────────────────────────────────────────────────────────────────
@router.get("/submissions/{submission_id}/sync-preview")
def preview_submission_sync(
    submission_id: str,
    current_user: dict = Depends(require_write),
):
    from core.security.permissions import can_approve


    if not can_approve(current_user.get("role", "")):
        raise HTTPException(status_code=403, detail="Admin approval required")
    try:
        owner_email = current_user.get("email") or current_user.get("username")
        return _prepare_new_product_launch_sync(submission_id, include_existing_check=True, owner_email=owner_email)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/submissions/{submission_id}/sync")
def sync_submission_to_new_product_launch(
    submission_id: str,
    current_user: dict = Depends(require_write),
):
    from core.security.permissions import can_approve


    if not can_approve(current_user.get("role", "")):
        raise HTTPException(status_code=403, detail="Admin approval required")
    try:
        owner_email = current_user.get("email") or current_user.get("username") or "Demand Planning"
        return _append_approved_to_new_product_launch(submission_id, owner_email=owner_email)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/submissions/{submission_id}/rows")
def get_submission_rows(
    submission_id: str,
    current_user: dict = Depends(require_write),
):
    """
    Return all Submission_Log rows for this submission with their 1-based
    sheet row index attached as _sheet_row_index.  Needed for position-safe
    deletion when duplicate rows exist.
    """
    from features.product_launch.core import get_submission_rows_with_indices

    try:
        rows = get_submission_rows_with_indices(submission_id)
        return {"submission_id": submission_id, "rows": rows}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class DeleteRowsBody(BaseModel):
    row_indices: List[int]
    reason: str


@router.delete("/submissions/{submission_id}/rows")
def delete_submission_rows(
    submission_id: str,
    body: DeleteRowsBody,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    """
    Delete exactly the specified sheet row indices (1-based) from Submission_Log, Launch_Output,
    and City_Plan / Hub_Plan sheets if approved.
    Requires write permission.
    """
    from features.product_launch.core import (
        delete_submission_rows_by_index,
        get_submission_rows_with_indices,
    )
    from core.shared.api_cache import CacheNS, cache_invalidate


    if not body.row_indices:
        raise HTTPException(status_code=400, detail="row_indices must not be empty")
    if not body.reason or not body.reason.strip():
        raise HTTPException(status_code=400, detail="reason must not be empty")

    try:
        deleted_count = delete_submission_rows_by_index(submission_id, body.row_indices, reason=body.reason)

        # Check if any rows remain for this submission — if none, mark DB as Deleted
        remaining = get_submission_rows_with_indices(submission_id)
        username = (
            current_user.get("email")
            or current_user.get("username")
            or current_user.get("full_name")
            or ""
        )
        if not remaining:
            try:
                db.update_npl_submission_status(submission_id, "Deleted", body.reason)
                logger.info(
                    "[NPL] submission %s fully deleted from sheet by %s (Reason: %s)",
                    submission_id, username, body.reason
                )
            except Exception as db_exc:
                logger.warning("[NPL] Could not update DB status to Deleted: %s", db_exc)

        cache_invalidate(CacheNS.NPL_WIZARD)
        logger.info(
            "[NPL] %d row(s) deleted from Submission_Log for %s by %s",
            deleted_count, submission_id, username,
        )
        return {
            "detail": f"Deleted {deleted_count} row(s) from Submission_Log",
            "deleted_count": deleted_count,
            "submission_fully_deleted": not remaining,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class UpdateNotesBody(BaseModel):
    notes: str


@router.put("/submissions/{submission_id}/notes")
def update_submission_notes(
    submission_id: str,
    body: UpdateNotesBody,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update the notes column of a submission in the database."""
    from core.shared.api_cache import CacheNS, cache_invalidate
    db.update_npl_submission_notes(submission_id, body.notes)
    cache_invalidate(CacheNS.NPL_WIZARD)
    return {"status": "success"}


def _fire_step_fail(step_name: str, error: str, current_user: dict, sub_type: str = "New Launch") -> None:
    """Fire a step-failure email in the background (best-effort, never raises)."""
    try:
        from core.shared.workflow_notifications import notify_npl_step_failed

        user_id = int(current_user.get("sub", 0) or 0) or None
        notify_npl_step_failed(
            step_name=step_name,
            error=error,
            sub_type=sub_type,
            user_id=user_id,
        )
    except Exception:
        logger.debug("[NPL] Step-fail email suppressed", exc_info=True)


def _format_db_submissions(df, *, view: str) -> dict:
    """Convert npl_submissions DB rows into the same shape as npl_wizard.get_submission_log()."""
    import json
    from datetime import datetime

    records = []
    for _, row in df.iterrows():
        ts_raw = row.get("timestamp")
        ts_str = ts_raw.isoformat() if hasattr(ts_raw, "isoformat") else str(ts_raw or "")
        city_str = str(row.get("cities") or "")
        city_list = [c.strip() for c in city_str.split(",") if c.strip()]

        # SLA flag
        sla = ""
        status = str(row.get("status") or "")
        if status == "Pending":
            try:
                start = row.get("start_date")
                if start and str(start).strip():
                    if datetime.strptime(str(start).strip()[:10], "%Y-%m-%d").date() < datetime.now().date():
                        sla = "EXPIRED"
            except Exception:
                pass

        records.append({
            "Submission_ID": str(row.get("submission_id") or ""),
            "Submission_Type": str(row.get("sub_type") or ""),
            "Product ID": str(row.get("product_id") or ""),
            "Product Name": str(row.get("product_name") or ""),
            "Category": str(row.get("category") or ""),
            "Cities": (", ".join(city_list[:6]) + (f", …" if len(city_list) > 6 else "")) if view == "summary" else ", ".join(city_list),
            "Hub_Count": int(row.get("hub_count") or 0),
            "City_Count": int(row.get("city_count") or 0),
            "Start Date": str(row.get("start_date") or ""),
            "Status": status,
            "SLA": sla,
            "Rejection_Reason": str(row.get("rejection_reason") or ""),
            "Submitted_By": str(row.get("submitted_by") or ""),
            "Timestamp": ts_str,
            "Notes": str(row.get("notes") or ""),
        })

    summary_cols = [
        "Submission_ID", "Submission_Type", "Product Name", "Start Date",
        "Status", "SLA", "Hub_Count", "City_Count", "Cities", "Submitted_By", "Timestamp", "Notes"
    ]
    detail_cols = [
        "Submission_ID", "Submission_Type", "Product ID", "Product Name",
        "Category", "City_Count", "Cities", "Hub_Count", "Start Date",
        "Status", "SLA", "Rejection_Reason", "Submitted_By", "Timestamp", "Notes"
    ]

    cols = summary_cols if view == "summary" else detail_cols

    # Build filter metadata from all rows
    all_types = sorted({r["Submission_Type"] for r in records if r["Submission_Type"]})
    all_statuses = sorted({r["Status"] for r in records if r["Status"]})
    all_pids = sorted({r["Product ID"] for r in records if r["Product ID"]})

    return {
        "rows": records,
        "columns": cols,
        "filters": {"types": all_types, "statuses": all_statuses, "product_ids": all_pids},
        "view": view,
        "row_count": len(records),
        "source": "db",
    }


HUB_PLAN_COLUMNS = [
    "Owner",
    "Type",
    "Channel",
    "Update Date",
    "Sub Category",
    "PRODUCT_ID",
    "PRODUCT_NAME",
    "Anchor ID",
    "PLU_CODE",
    "city_name",
    "hub_name",
    "UOM",
    "Yield",
    "RM",
    "Meat Ratio (for VA)",
    "Total Shelf Life",
    "Hub Shelf Life",
    "MRP",
    "Change Date",
    "Mon",
    "Tue",
    "Wed",
    "Thu",
    "Fri",
    "Sat",
    "Sun",
    "Planning Confirmation",
    "Production PC",
    "",
    "Submitted_By",
]


def _npl_city_plan_key(row_vals: list, headers: list[str]) -> tuple[str, str, str, str] | None:
    try:
        type_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower() == "type")
        pid_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower().replace("_", "") == "productid")
        city_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower() == "city")
        date_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower() == "change date")
        
        val_type = str(row_vals[type_idx]).strip().lower()
        val_pid = str(row_vals[pid_idx]).strip().lower()
        val_city = str(row_vals[city_idx]).strip().lower()
        val_date = str(row_vals[date_idx]).strip().lower()
        
        if val_type and val_pid and val_city and val_date:
            return (val_type, val_pid, val_city, val_date)
    except Exception:
        pass
    return None


def _format_date_npl(date_val) -> str:
    if not date_val:
        return ""
    if hasattr(date_val, "strftime"):
        return date_val.strftime("%m/%d/%Y")
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(date_val).strip(), fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return str(date_val)


def _get_product_master_details_map() -> dict[str, dict]:
    from app import config as cfg

    from features.product_launch.core import _open_sheet

    import pandas as pd
    
    details_map = {}
    try:
        from features.product_launch.sheet_reads import read_sheet_values_cached

        def _fetch_pm():
            sheet = _open_sheet(cfg.DEMAND_PLANNING_SHEET_ID, "P Master")
            return sheet.get_all_values()
        
        pm_data = read_sheet_values_cached(cfg.DEMAND_PLANNING_SHEET_ID, "P Master", "all", "demand_planning_masters", _fetch_pm)
        if len(pm_data) > 1:
            pm_df = pd.DataFrame(pm_data[1:], columns=pm_data[0])
            for _, row in pm_df.iterrows():
                pid = str(row.get("Product id", "")).strip()
                if pid:
                    details_map[pid] = {
                        "RM": str(row.get("RM", "")).strip() if "RM" in row else "",
                        "UOM": "",
                        "Yield": "",
                        "Total Shelf Life": "",
                        "Hub Shelf Life": "",
                        "PLU_CODE": ""
                    }
    except Exception as e:
        logger.warning(f"Error reading P Master for details: {e}")
        
    return details_map


def _build_city_plan_row_dynamic(source: dict, headers: list[str], update_date: str, pm_details_map: dict | None = None) -> list:
    row = []
    pid = str(source.get("Product ID", "")).strip()
    
    # Use cached map if provided, otherwise fetch dynamically
    if pm_details_map is not None:
        pm_details = pm_details_map.get(pid, {})
    else:
        # Fallback single row fetch
        pm_details = {
            "RM": "", "UOM": "", "Yield": "", "Total Shelf Life": "", "Hub Shelf Life": "", "PLU_CODE": ""
        }
        try:
            from app import config as cfg

            from features.product_launch.core import _open_sheet

            import pandas as pd
            from features.product_launch.sheet_reads import read_sheet_values_cached

            def _fetch_pm():
                sheet = _open_sheet(cfg.DEMAND_PLANNING_SHEET_ID, "P Master")
                return sheet.get_all_values()
            pm_data = read_sheet_values_cached(cfg.DEMAND_PLANNING_SHEET_ID, "P Master", "all", "demand_planning_masters", _fetch_pm)
            if len(pm_data) > 1:
                pm_df = pd.DataFrame(pm_data[1:], columns=pm_data[0])
                pm_row = pm_df[pm_df["Product id"].astype(str).str.strip() == pid]
                if not pm_row.empty and "RM" in pm_row.columns:
                    pm_details["RM"] = str(pm_row["RM"].iloc[0]).strip()
        except Exception:
            pass
            
    for h in headers:
        h_norm = str(h).strip().lower().replace("\n", " ").replace("_", " ")
        if h_norm in ("owner", "owner name"):
            owner = source.get("_owner_email") or source.get("Submitted_By") or "Demand Planning"
            row.append(owner)
        elif h_norm == "type":
            row.append(source.get("Submission_Type", "New Launch"))
        elif h_norm == "channel":
            row.append("App")
        elif h_norm in ("update date", "updated date"):
            row.append(_format_date_npl(update_date))
        elif h_norm in ("sub category", "subcategory"):
            row.append(source.get("Category", ""))
        elif h_norm in ("product id", "sku"):
            row.append(pid)
        elif h_norm in ("product name", "sku name"):
            row.append(source.get("Product Name", ""))
        elif h_norm == "anchor id":
            row.append(pid)
        elif h_norm in ("city", "city name"):
            row.append(source.get("City", ""))
        elif h_norm in ("mrp", "mrp (before kvi discount)"):
            row.append(source.get("MRP", ""))
        elif h_norm == "change date":
            row.append(_format_date_npl(source.get("Start Date", "")))
        elif h_norm == "uom":
            row.append(source.get("UOM", pm_details.get("UOM", "")))
        elif h_norm == "yield":
            row.append(source.get("Yield", pm_details.get("Yield", "")))
        elif h_norm == "rm":
            row.append(source.get("RM", pm_details.get("RM", "")))
        elif h_norm in ("meat ratio (for va)", "meat ratio"):
            row.append(source.get("Meat Ratio (for VA)", "NA"))
        elif h_norm == "total shelf life":
            row.append(source.get("Total Shelf Life", pm_details.get("Total Shelf Life", "")))
        elif h_norm == "hub shelf life":
            row.append(source.get("Hub Shelf Life", pm_details.get("Hub Shelf Life", "")))
        elif h_norm == "plu code":
            row.append(source.get("PLU_CODE", pm_details.get("PLU_CODE", "")))
        elif h_norm == "mon":
            row.append(int(float(source.get("Mon", 0) or 0)))
        elif h_norm == "tue":
            row.append(int(float(source.get("Tue", 0) or 0)))
        elif h_norm == "wed":
            row.append(int(float(source.get("Wed", 0) or 0)))
        elif h_norm == "thu":
            row.append(int(float(source.get("Thu", 0) or 0)))
        elif h_norm == "fri":
            row.append(int(float(source.get("Fri", 0) or 0)))
        elif h_norm == "sat":
            row.append(int(float(source.get("Sat", 0) or 0)))
        elif h_norm == "sun":
            row.append(int(float(source.get("Sun", 0) or 0)))
        elif h_norm in ("planning confirmation", "planning confirm"):
            row.append("Confirmed")
        elif h_norm == "submitted by":
            row.append(source.get("Submitted_By", ""))
        elif h_norm == "owner email":
            row.append(source.get("_owner_email", ""))
        elif h_norm == "submitted at":
            row.append(source.get("Timestamp", ""))
        else:
            row.append("")
    return row


def _prepare_new_product_launch_sync(submission_id: str, *, include_existing_check: bool, owner_email: str | None = None) -> dict:
    """Build the exact City_Plan or Hub_Plan rows for preview or sync."""
    from datetime import datetime
    from app import config as cfg

    from features.product_launch.core import _open_sheet


    if not cfg.NEW_PRODUCT_LAUNCH_SHEET_URL:
        raise RuntimeError("NEW_PRODUCT_LAUNCH_SHEET_URL must be set in .env to append approved NPL rows.")
    if not cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY:
        raise RuntimeError("NEW_PRODUCT_LAUNCH_SHEET_URL does not contain a valid Google Sheet ID.")

    log_sheet = _open_sheet(cfg.HUB_LEVEL_PLANNING_SHEET_KEY, "Submission_Log")
    all_data = log_sheet.get_all_records()
    if not all_data:
        raise RuntimeError("No rows found in Submission_Log.")

    matching_rows = [r for r in all_data if str(r.get("Submission_ID", "")).strip() == str(submission_id)]
    if not matching_rows:
        raise RuntimeError(f"No Submission_Log rows found for {submission_id}.")

    statuses = {str(r.get("Status", "")).strip().lower() for r in matching_rows}
    if statuses != {"approved"}:
        raise RuntimeError("Approve this submission before previewing or syncing it.")

    # Determine sync plan level target tab: if Hub column contains data, target is Hub_Plan, else City_Plan
    has_hubs = any(str(r.get("Hub", "")).strip() for r in matching_rows)
    target_worksheet = "Hub_Plan" if has_hubs else "City_Plan"
    
    plan_sheet = _open_sheet(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY, target_worksheet)
    
    # Locate header row dynamically (row containing OWNER or PRODUCT_ID)
    sheet_sample = plan_sheet.get("A1:AP5")
    header_row_idx = 1
    for idx, r in enumerate(sheet_sample, 1):
        normalized_row = [str(x).strip().upper() for x in r]
        if any(h in normalized_row for h in ["OWNER", "PRODUCT_ID", "PRODUCT ID", "SKU"]):
            header_row_idx = idx
            break
            
    sheet_headers = [str(h).strip() for h in plan_sheet.row_values(header_row_idx)]
    while sheet_headers and not sheet_headers[-1]:
        sheet_headers.pop()
    columns = list(sheet_headers)

    # Pre-build product master details lookups map
    pm_details_map = _get_product_master_details_map()

    existing_keys = set()
    if include_existing_check:
        all_rows = plan_sheet.get_all_values()
        for row in all_rows[header_row_idx:]:
            if len(row) < len(sheet_headers):
                row = row + [""] * (len(sheet_headers) - len(row))
            if target_worksheet == "Hub_Plan":
                key = _npl_hub_plan_key_dynamic(row, sheet_headers)
            else:
                key = _npl_city_plan_key(row, sheet_headers)
            if key:
                existing_keys.add(key)

    values = []
    rows = []
    skipped = 0
    update_date = datetime.now().strftime("%Y-%m-%d")
    
    for source in matching_rows:
        sub_type = source.get("Submission_Type", "New Launch")
        pid = str(source.get("Product ID", "")).strip()
        pname = source.get("Product Name", "")
        cat = source.get("Category", "")
        city = source.get("City", "")
        mrp = source.get("MRP", "")
        start_date = source.get("Start Date", "")
        submitted_by = source.get("Submitted_By", "")
        timestamp = source.get("Timestamp", "")
        
        # Format dates properly
        fmt_start_date = _format_date_npl(start_date)
        fmt_timestamp = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)

        row_source = {
            "Submission_Type": sub_type,
            "Product ID": pid,
            "Product Name": pname,
            "Category": cat,
            "City": city,
            "Hub": str(source.get("Hub", "")).strip(),
            "MRP": mrp,
            "Start Date": fmt_start_date,
            "Submitted_By": submitted_by,
            "Timestamp": fmt_timestamp,
            "Mon": source.get("Mon", 0),
            "Tue": source.get("Tue", 0),
            "Wed": source.get("Wed", 0),
            "Thu": source.get("Thu", 0),
            "Fri": source.get("Fri", 0),
            "Sat": source.get("Sat", 0),
            "Sun": source.get("Sun", 0),
            "_owner_email": owner_email or source.get("Submitted_By") or source.get("_owner_email", ""),
        }

        if target_worksheet == "Hub_Plan":
            row_vals = _build_hub_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
            key = _npl_hub_plan_key_dynamic(row_vals, sheet_headers)
        else:
            row_vals = _build_city_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
            key = _npl_city_plan_key(row_vals, sheet_headers)
            
        if key and key in existing_keys:
            skipped += 1
            continue
            
        values.append(row_vals)
        rows.append(dict(zip(columns, row_vals)))
        if key:
            existing_keys.add(key)

    return {
        "status": "ready",
        "spreadsheet_key": cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY,
        "worksheet": target_worksheet,
        "columns": columns,
        "rows": rows,
        "values": values,
        "rows_to_append": len(values),
        "rows_skipped": skipped,
        "matched_rows": len(matching_rows),
        "header_row_idx": header_row_idx,
    }


def _append_approved_to_new_product_launch(submission_id: str, owner_email: str | None = None) -> dict:
    """Append approved Submission_Log rows to the env-configured NPL City_Plan or Hub_Plan sheet."""
    from app import config as cfg

    from features.product_launch.core import _open_sheet


    prepared = _prepare_new_product_launch_sync(submission_id, include_existing_check=True, owner_email=owner_email)
    values = prepared.pop("values", [])
    target_worksheet = prepared["worksheet"]
    header_row_idx = prepared.get("header_row_idx", 1)
    
    if values:
        plan_sheet = _open_sheet(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY, target_worksheet)
        plan_sheet.append_rows(values, value_input_option="USER_ENTERED", table_range=f"A{header_row_idx}")

    logger.info(
        "[NPL] approval sync complete for %s: appended=%d skipped=%d target=%s!%s",
        submission_id,
        len(values),
        prepared["rows_skipped"],
        cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY,
        target_worksheet,
    )
    return {
        "status": "success",
        "worksheet": target_worksheet,
        "rows_appended": len(values),
        "rows_skipped": prepared["rows_skipped"],
        "matched_rows": prepared["matched_rows"],
    }


def _build_hub_plan_row_dynamic(source: dict, headers: list[str], update_date: str, pm_details_map: dict | None = None) -> list:
    row = []
    pid = str(source.get("Product ID", "")).strip()
    
    # Use cached map if provided
    pm_details = pm_details_map.get(pid, {}) if pm_details_map is not None else {}
    
    for h in headers:
        h_norm = str(h).strip().lower().replace("\n", " ").replace("_", " ")
        if h_norm in ("owner", "owner name"):
            owner = source.get("_owner_email") or source.get("Submitted_By") or "Demand Planning"
            row.append(owner)
        elif h_norm == "type":
            row.append(source.get("Submission_Type", "New Launch"))
        elif h_norm == "channel":
            row.append("App")
        elif h_norm in ("update date", "updated date"):
            row.append(_format_date_npl(update_date))
        elif h_norm in ("sub category", "subcategory"):
            row.append(source.get("Category", ""))
        elif h_norm in ("product id", "sku", "product_id"):
            row.append(pid)
        elif h_norm in ("product name", "sku name", "product_name"):
            row.append(source.get("Product Name", ""))
        elif h_norm == "anchor id":
            row.append(pid)
        elif h_norm in ("city", "city name"):
            # If both city and hub_name exist as headers, "city" should get City, and "hub name" should get Hub.
            # However, in some headers "city" can refer to either, so we check carefully.
            row.append(source.get("City", ""))
        elif h_norm in ("hub name", "hub_name", "hub"):
            row.append(source.get("Hub", ""))
        elif h_norm in ("mrp", "mrp (before kvi discount)"):
            row.append(source.get("MRP", ""))
        elif h_norm == "change date":
            row.append(_format_date_npl(source.get("Start Date", "")))
        elif h_norm == "uom":
            row.append(source.get("UOM", pm_details.get("UOM", "")))
        elif h_norm == "yield":
            row.append(source.get("Yield", pm_details.get("Yield", "")))
        elif h_norm == "rm":
            row.append(source.get("RM", pm_details.get("RM", "")))
        elif h_norm in ("meat ratio (for va)", "meat ratio"):
            row.append(source.get("Meat Ratio (for VA)", "NA"))
        elif h_norm == "total shelf life":
            row.append(source.get("Total Shelf Life", pm_details.get("Total Shelf Life", "")))
        elif h_norm == "hub shelf life":
            row.append(source.get("Hub Shelf Life", pm_details.get("Hub Shelf Life", "")))
        elif h_norm == "plu code":
            row.append(source.get("PLU_CODE", pm_details.get("PLU_CODE", "")))
        elif h_norm == "mon":
            row.append(int(float(source.get("Mon", 0) or 0)))
        elif h_norm == "tue":
            row.append(int(float(source.get("Tue", 0) or 0)))
        elif h_norm == "wed":
            row.append(int(float(source.get("Wed", 0) or 0)))
        elif h_norm == "thu":
            row.append(int(float(source.get("Thu", 0) or 0)))
        elif h_norm == "fri":
            row.append(int(float(source.get("Fri", 0) or 0)))
        elif h_norm == "sat":
            row.append(int(float(source.get("Sat", 0) or 0)))
        elif h_norm == "sun":
            row.append(int(float(source.get("Sun", 0) or 0)))
        elif h_norm in ("planning confirmation", "planning confirm"):
            row.append("Confirmed")
        elif h_norm == "submitted by":
            row.append(source.get("Submitted_By", ""))
        elif h_norm == "owner email":
            row.append(source.get("_owner_email", ""))
        elif h_norm == "submitted at":
            row.append(source.get("Timestamp", ""))
        else:
            row.append("")
    return row


def _normalize_hub_plan_headers(headers: list[str]) -> list[str]:
    columns = [str(h) for h in (headers or [])]
    if len(columns) < len(HUB_PLAN_COLUMNS):
        columns = columns + HUB_PLAN_COLUMNS[len(columns):]
    if len(columns) > len(HUB_PLAN_COLUMNS):
        return columns[:len(HUB_PLAN_COLUMNS)]
    return columns or HUB_PLAN_COLUMNS


def _npl_hub_plan_key(row: list) -> tuple[str, str, str, str, str] | None:
    """Natural duplicate key for Hub_Plan rows based on the current sheet layout."""
    if len(row) <= 18:
        return None
    values = [row[1], row[5], row[9], row[10], row[18]]
    key = tuple(str(v).strip().lower() for v in values)
    return key if all(key) else None


def _npl_hub_plan_key_from_b_to_s(row: list) -> tuple[str, str, str, str, str] | None:
    if len(row) <= 17:
        return None
    values = [row[0], row[4], row[8], row[9], row[17]]
    key = tuple(str(v).strip().lower() for v in values)
    return key if all(key) else None


def _npl_hub_plan_key_dynamic(row_vals: list, headers: list[str]) -> tuple[str, str, str, str, str] | None:
    try:
        type_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower() == "type")
        pid_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower().replace("_", "") == "productid")
        city_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower() == "city")
        hub_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower().replace("_", "") == "hubname")
        date_idx = next(i for i, h in enumerate(headers) if str(h).strip().lower() == "change date")
        
        val_type = str(row_vals[type_idx]).strip().lower()
        val_pid = str(row_vals[pid_idx]).strip().lower()
        val_city = str(row_vals[city_idx]).strip().lower()
        val_hub = str(row_vals[hub_idx]).strip().lower()
        val_date = str(row_vals[date_idx]).strip().lower()
        
        if val_type and val_pid and val_city and val_hub and val_date:
            return (val_type, val_pid, val_city, val_hub, val_date)
    except Exception:
        pass
    return None
