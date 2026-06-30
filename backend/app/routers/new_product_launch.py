"""New Product Launch router — upload, masters, salience, auto-sync."""
from __future__ import annotations

import io
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.deps import get_current_user, require_write, get_db
from planning_suite.core.dataframe import df_to_records
from planning_suite.db.engine import Database

router = APIRouter()


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

    content = await file.read()
    result = wiz.parse_city_file(content)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("errors", ["Parse failed"]))
    return result


@router.post("/wizard/parse-hub")
async def wizard_parse_hub(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
):
    from planning_suite.services import npl_wizard as wiz

    content = await file.read()
    result = wiz.parse_hub_file(content)
    if not result.get("ok"):
        raise HTTPException(status_code=422, detail=result.get("errors", ["Parse failed"]))
    return result


@router.post("/wizard/split-city")
def wizard_split_city(body: SplitCityBody, current_user: dict = Depends(require_write)):
    from planning_suite.services import npl_wizard as wiz

    return wiz.split_city_rows(body.city_rows, forced_hubs=body.forced_hubs)


@router.post("/wizard/check-duplicates")
def wizard_check_dupes(
    body: HubRowsBody,
    sub_type: str = "New Launch",
    plan_level: str = "hub",
    current_user: dict = Depends(require_write),
):
    from planning_suite.services import npl_wizard as wiz

    return wiz.check_duplicates(body.hub_rows, sub_type=sub_type, plan_level=plan_level)


@router.post("/wizard/submit")
def wizard_submit(body: SubmitBody, current_user: dict = Depends(require_write)):
    from planning_suite.services import npl_wizard as wiz

    rows = wiz.apply_launch_dates(body.hub_rows, body.launch_date)
    username = current_user.get("username", "")
    user_id = int(current_user["sub"])
    return wiz.submit_hub_rows(
        rows,
        sub_type=body.sub_type,
        username=username,
        user_id=user_id,
        send_email=body.send_email,
    )


@router.get("/submissions/log")
def submissions_log(
    types: str | None = None,
    statuses: str | None = None,
    product_ids: str | None = None,
    submission_id: str | None = None,
    view: str = Query("summary", pattern="^(summary|detail)$"),
    current_user: dict = Depends(get_current_user),
):
    from planning_suite.services import npl_wizard as wiz
    from planning_suite.services.api_cache import CacheNS, cache_invalidate, cached

    t = [x.strip() for x in types.split(",") if x.strip()] if types else None
    s = [x.strip() for x in statuses.split(",") if x.strip()] if statuses else None
    p = [x.strip() for x in product_ids.split(",") if x.strip()] if product_ids else None
    cache_key = f"log:{view}:{submission_id or ''}:{types or ''}:{statuses or ''}:{product_ids or ''}"

    def _log():
        return wiz.get_submission_log(
            types=t,
            statuses=s,
            product_ids=p,
            submission_id=submission_id,
            view=view,
        )

    return cached(CacheNS.NPL_WIZARD, cache_key, _log, ttl=_NPL_LOG_CACHE_TTL)


@router.patch("/submissions/{submission_id}/status")
def patch_submission_status(
    submission_id: str,
    body: StatusBody,
    current_user: dict = Depends(require_write),
):
    from planning_suite.core.permissions import can_approve
    from planning_suite.services import npl_wizard as wiz

    admin_actions = {"Approved", "Rejected", "Voided"}
    if body.status in admin_actions and not can_approve(current_user.get("role", "")):
        raise HTTPException(status_code=403, detail="Admin approval required")
    try:
        wiz.set_submission_status(submission_id, body.status, body.reason)
        from planning_suite.services.api_cache import CacheNS, cache_invalidate

        cache_invalidate(CacheNS.NPL_WIZARD)
        return {"detail": f"Submission {submission_id} → {body.status}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
