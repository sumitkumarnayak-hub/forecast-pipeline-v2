"""New Product Launch router — upload, masters, salience, auto-sync."""
from __future__ import annotations

import io
import logging
import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.deps import get_current_user, require_write, get_db
from planning_suite.core.dataframe import df_to_records
from planning_suite.db.engine import Database

router = APIRouter()
logger = logging.getLogger(__name__)


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
        from planning_suite.features.new_product_launch import validate_npl_upload

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
        from planning_suite.services.google_sheets import GoogleSheetsManager
        from planning_suite import config as cfg

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
    from planning_suite.services.api_cache import CacheNS, cached
    from planning_suite.services import npl_wizard as wiz

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
    from planning_suite.services.api_cache import CacheNS, cached
    from planning_suite.features.new_product_launch import get_products_by_category, load_product_master

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
    from planning_suite.services.api_cache import CacheNS, cached
    from planning_suite.services import npl_wizard as wiz

    products = cached(CacheNS.NPL_WIZARD, "product_ids", wiz.list_all_product_ids, ttl=_NPL_CACHE_TTL)
    return {"products": products}


@router.get("/salience/cities")
def npl_salience_cities(current_user: dict = Depends(get_current_user)):
    try:
        from planning_suite.features.new_product_launch import get_cities_from_salience, load_salience_source

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
        from planning_suite.features.new_product_launch import get_hubs_for_city, load_salience_source

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
        from planning_suite.services.product_launch_sync import (
            build_new_product_ph_preview,
            load_masters_for_product_sync,
        )
        from planning_suite.services.sheets_session import get_sheets_manager

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
        from planning_suite.config import DPM_SHEET_KEY
        from planning_suite.services.sheets_session import get_sheets_manager

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
        from planning_suite.automation.new_product_launch_sync import run_new_product_launch_sync_cli

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


class StatusBody(BaseModel):
    status: str
    reason: str = ""


@router.get("/wizard/context")
def wizard_context(current_user: dict = Depends(get_current_user)):
    from planning_suite.services.api_cache import CacheNS, cached
    from planning_suite.services import npl_wizard as wiz

    return cached(CacheNS.NPL_WIZARD, "context", wiz.wizard_context_payload, ttl=_NPL_CACHE_TTL)


@router.get("/wizard/hubs")
def wizard_hubs(
    city: str,
    category: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    from planning_suite.services import npl_wizard as wiz

    return {"hubs": wiz.list_hubs_for_city(city, category)}


@router.post("/wizard/template/city")
def wizard_template_city(body: TemplateCityBody, current_user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    from planning_suite.services import npl_wizard as wiz

    data = wiz.city_template_bytes(body.cities, body.category, product_id=body.product_id, product_name=body.product_name)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="city_template_{body.category}.xlsx"'},
    )


@router.post("/wizard/template/hub")
def wizard_template_hub(body: TemplateHubBody, current_user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    from planning_suite.services import npl_wizard as wiz

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
    from planning_suite.services import npl_wizard as wiz

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
    from planning_suite.services import npl_wizard as wiz

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
    from planning_suite.services import npl_wizard as wiz

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
    from planning_suite.services import npl_wizard as wiz

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


@router.post("/wizard/submit")
def wizard_submit(
    body: SubmitBody,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    from planning_suite.services import npl_wizard as wiz

    t0 = time.perf_counter()
    username = current_user.get("username", "")
    user_id = int(current_user["sub"])
    sub_id = ""
    history_saved = False
    history_error = ""

    try:
        rows = wiz.apply_launch_dates(body.hub_rows, body.launch_date)
        result = wiz.submit_hub_rows(
            rows,
            sub_type=body.sub_type,
            username=username,
            user_id=user_id,
            send_email=False,  # We send our own richer email below
        )
        elapsed = round((time.perf_counter() - t0) * 1000)
        sub_id = result.get("submission_id", "")
        product_name = result.get("product_name", "")
        hub_count = result.get("rows", 0)

        # Collect metadata from submitted rows for DB/email
        import pandas as pd
        hub_df = pd.DataFrame(rows)
        cities = sorted(hub_df["city_name"].dropna().astype(str).unique().tolist()) if "city_name" in hub_df.columns else []
        product_id = str(hub_df["product_id"].iloc[0]) if "product_id" in hub_df.columns and len(hub_df) else ""
        category = str(hub_df["category"].iloc[0]) if "category" in hub_df.columns and len(hub_df) else ""
        launch_dates = sorted(hub_df["Launch Date"].dropna().astype(str).unique().tolist()) if "Launch Date" in hub_df.columns else []
        start_date = launch_dates[0] if launch_dates else ""

        logger.info(
            "[NPL] submit OK — sub_id=%s sub_type=%s product=%s %d hubs %d cities in %dms",
            sub_id, body.sub_type, product_name, hub_count, len(cities), elapsed,
        )

        # Persist to Supabase (best-effort, never blocks the response)
        try:
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
                    "submit_ms": elapsed,
                    "status": "submitted",
                    "email_requested": body.send_email,
                },
            )
            db.update_npl_submission_status(sub_id, "Submitted")
            history_saved = True
        except Exception as history_exc:
            history_error = str(history_exc)
            logger.exception("[NPL] failed to persist submission %s to DB", sub_id)

        # Send success + approval emails
        if body.send_email:
            from planning_suite.services.workflow_notifications import notify_npl_submitted
            email_result = notify_npl_submitted(
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
        else:
            email_result = {"skipped": True, "reason": "send_email=false"}

        result["email"] = email_result
        result["history"] = {"saved": history_saved, "status": "Submitted" if history_saved else "Pending", "error": history_error}
        return result

    except HTTPException:
        raise
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[NPL] submit crashed in %dms", elapsed)
        if sub_id:
            try:
                db.update_npl_submission_status(sub_id, "Failed", str(exc))
            except Exception:
                logger.debug("[NPL] status update on submit failure suppressed", exc_info=True)
        _fire_step_fail("Submit to Google Sheets", str(exc), current_user, sub_type=body.sub_type)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    from planning_suite.services.api_cache import CacheNS, cache_invalidate, cached
    from planning_suite.services import npl_wizard as wiz

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
    from planning_suite.core.permissions import can_approve
    from planning_suite.services import npl_wizard as wiz

    admin_actions = {"Approved", "Rejected", "Voided"}
    if body.status in admin_actions and not can_approve(current_user.get("role", "")):
        raise HTTPException(status_code=403, detail="Admin approval required")
    try:
        # Update Google Sheets
        wiz.set_submission_status(submission_id, body.status, body.reason)
        # Update Supabase
        db.update_npl_submission_status(submission_id, body.status, body.reason)

        from planning_suite.services.api_cache import CacheNS, cache_invalidate
        cache_invalidate(CacheNS.NPL_WIZARD)
        logger.info("[NPL] submission %s → %s by user %s", submission_id, body.status, current_user.get("username"))
        return {"detail": f"Submission {submission_id} → {body.status}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fire_step_fail(step_name: str, error: str, current_user: dict, sub_type: str = "New Launch") -> None:
    """Fire a step-failure email in the background (best-effort, never raises)."""
    try:
        from planning_suite.services.workflow_notifications import notify_npl_step_failed
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
            "Cities": ", ".join(city_list[:6]) + (f", …" if len(city_list) > 6 else ""),
            "Hub_Count": int(row.get("hub_count") or 0),
            "City_Count": int(row.get("city_count") or 0),
            "Start Date": str(row.get("start_date") or ""),
            "Status": status,
            "SLA": sla,
            "Rejection_Reason": str(row.get("rejection_reason") or ""),
            "Submitted_By": str(row.get("submitted_by") or ""),
            "Timestamp": ts_str,
        })

    summary_cols = [
        "Submission_ID", "Submission_Type", "Product Name", "Start Date",
        "Status", "SLA", "Hub_Count", "City_Count", "Cities", "Submitted_By", "Timestamp",
    ]
    detail_cols = [
        "Submission_ID", "Submission_Type", "Product ID", "Product Name",
        "Category", "City_Count", "Cities", "Hub_Count", "Start Date",
        "Status", "SLA", "Rejection_Reason", "Submitted_By", "Timestamp",
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



