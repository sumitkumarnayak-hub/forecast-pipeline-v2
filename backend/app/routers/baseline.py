"""Baseline router — manual steps 1–5, config, runs, approve/reject."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import get_current_user, require_write, require_approve, get_db
from planning_suite.core.dataframe import sanitize_for_json
from planning_suite.db.engine import Database
from planning_suite.services import baseline_manual as manual
from planning_suite.services import baseline_wave_ops as wave
from planning_suite.services.api_cache import CacheNS, cached, cache_invalidate
from planning_suite.services.pipeline_state import (
    is_baseline_approved,
    approve_baseline,
    reject_baseline,
)

router = APIRouter()


def _invalidate_baseline_cache() -> None:
    cache_invalidate(CacheNS.BASELINE_REPO)
    cache_invalidate(CacheNS.BASELINE_ACTIVE)
    cache_invalidate(CacheNS.BASELINE_PARAMS)


class DateRangeBody(BaseModel):
    start_date: str
    end_date: str


class FetchRawBody(DateRangeBody):
    also_save_csv: bool = False
    use_cached_week: bool = True


class LoadWeeksBody(BaseModel):
    weeks: list[int] = Field(min_length=1)


class ParamsBody(BaseModel):
    use_clustering: bool | None = None
    remove_outliers: bool | None = None
    apply_hub_changes: bool | None = None
    use_availability: bool | None = None
    use_stf: bool | None = None
    use_percentile: bool | None = None
    weeks_back: int | None = None
    avail_threshold: float | None = None
    target_week: int | None = None
    target_year: int | None = None


class RunBaselineBody(BaseModel):
    target_week: int | None = None
    target_year: int | None = None


class FetchPreviousBody(BaseModel):
    target_week: int | None = None
    target_year: int | None = None


class BulkPullBody(BaseModel):
    also_save_csv: bool = False


@router.get("/status")
def get_baseline_status(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
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

    return {
        "approved": approved,
        "latest_run": latest_dict,
        "active_dataset": manual.get_active_dataset_status(),
    }


@router.get("/raw-data/status")
def raw_data_status(
    current_user: dict = Depends(get_current_user),
    refresh: bool = Query(False),
    details: bool = Query(False, description="Include per-week row counts (slower)"),
):
    cache_key = f"raw-status:{'details' if details else 'lite'}"

    def factory() -> dict:
        return {
            "repository": manual.get_repository_status(lite=not details),
            "active_dataset": manual.get_active_dataset_status(include_preview=details),
            "dates": manual.get_date_defaults(force_refresh=refresh),
        }

    return cached(
        CacheNS.BASELINE_REPO,
        cache_key,
        factory,
        ttl=60.0 if not details else 30.0,
        skip_cache=refresh,
    )


@router.get("/raw-data/status/details")
def raw_data_status_details(current_user: dict = Depends(get_current_user)):
    """Full repository stats — use after lite status for row/sales totals."""
    return {
        "repository": manual.get_repository_status(lite=False),
        "active_dataset": manual.get_active_dataset_status(include_preview=True),
    }


@router.post("/raw-data/dates")
def save_raw_dates(
    body: DateRangeBody,
    current_user: dict = Depends(require_write),
):
    try:
        manual.save_date_range(body.start_date, body.end_date)
        _invalidate_baseline_cache()
        return {"detail": "Dates saved to Pipeline Params sheet", "dates": body.model_dump()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/raw-data/fetch")
def fetch_raw_data(
    body: FetchRawBody,
    current_user: dict = Depends(require_write),
):
    try:
        result = manual.fetch_raw_data(
            start_date=body.start_date,
            end_date=body.end_date,
            also_save_csv=body.also_save_csv,
            use_cached_week=body.use_cached_week,
        )
        _invalidate_baseline_cache()
        return sanitize_for_json(
            {
                "detail": f"Week {result['iso_week']} saved ({result['rows']:,} rows)",
                **result,
                "repository": manual.get_repository_status(),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/raw-data/bulk-plan")
def bulk_week_plan(current_user: dict = Depends(get_current_user)):
    return wave.get_bulk_week_plan()


@router.post("/raw-data/bulk-pull")
def bulk_pull_raw_data(
    body: BulkPullBody,
    current_user: dict = Depends(require_write),
):
    try:
        result = wave.run_bulk_pull(also_save_csv=body.also_save_csv)
        _invalidate_baseline_cache()
        return sanitize_for_json(
            {
                "detail": f"Bulk pull complete — {result['weeks_pulled']} week(s)",
                **result,
                "repository": manual.get_repository_status(),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/raw-data/load-weeks")
def load_weeks(
    body: LoadWeeksBody,
    current_user: dict = Depends(require_write),
):
    try:
        result = manual.load_weeks_into_active_dataset(body.weeks)
        _invalidate_baseline_cache()
        return sanitize_for_json(
            {
                "detail": f"Loaded {result['rows']:,} rows from {len(result['weeks'])} week(s)",
                **result,
                "active_dataset": manual.get_active_dataset_status(),
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/params")
def get_params(
    current_user: dict = Depends(get_current_user),
    refresh: bool = Query(False),
):
    return cached(
        CacheNS.BASELINE_PARAMS,
        "pipeline-params",
        manual.get_pipeline_params,
        ttl=30.0,
        skip_cache=refresh,
    )


@router.post("/params")
def save_params(
    body: ParamsBody,
    current_user: dict = Depends(require_write),
):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No parameters to save")
    try:
        saved = manual.save_pipeline_params(updates)
        _invalidate_baseline_cache()
        return {"detail": "Parameters saved to Google Sheet", "params": saved}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sync-dp-logics")
def sync_dp_logics(current_user: dict = Depends(require_write)):
    try:
        result = manual.sync_dp_logics()
        _invalidate_baseline_cache()
        return {"detail": "DP Logics worksheets synced", **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/generate/context")
def generate_context(current_user: dict = Depends(get_current_user)):
    return manual.get_generate_context()


@router.get("/generate/preflight")
def generate_preflight(current_user: dict = Depends(get_current_user)):
    return manual.get_generate_preflight()


@router.post("/generate/fetch-previous-baseline")
def fetch_previous_baseline(
    body: FetchPreviousBody,
    current_user: dict = Depends(require_write),
):
    try:
        return wave.fetch_previous_baseline(
            target_week=body.target_week,
            target_year=body.target_year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/generate/run")
def run_baseline(
    body: RunBaselineBody,
    current_user: dict = Depends(require_write),
):
    user_id = int(current_user["sub"])
    try:
        result = manual.run_baseline_engine(
            user_id=user_id,
            target_week=body.target_week,
            target_year=body.target_year,
        )
        _invalidate_baseline_cache()
        return sanitize_for_json({"detail": "Baseline completed", **result})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/review/latest-summary")
def review_latest_summary(
    limit: int = 500,
    current_user: dict = Depends(get_current_user),
):
    return manual.preview_latest_summary(limit=limit)


@router.get("/review/comparison")
def review_comparison(
    view: str = Query("city-day", description="city-day | city-cat-day | hub-cat-day | hub-day"),
    refresh: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    try:
        return wave.load_baseline_comparison(view=view, refresh=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/review/hub-sku-comparison")
def review_hub_sku_comparison(
    refresh: bool = Query(False),
    write_sheet: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    try:
        return wave.load_hub_sku_day_comparison(refresh=refresh, write_sheet=write_sheet)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/approve/hub-suggestion")
def approve_hub_suggestion(
    refresh: bool = Query(False),
    city_filter: str = Query("All"),
    sku_filter: str = Query("All"),
    current_user: dict = Depends(get_current_user),
):
    try:
        return wave.load_hub_suggestion_for_approve(
            refresh=refresh,
            city_filter=city_filter,
            sku_filter=sku_filter,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/reject")
def reject_baseline_run(
    current_user: dict = Depends(require_approve),
    db: Database = Depends(get_db),
):
    try:
        reject_baseline(db=db)
        return {"detail": "Baseline rejected."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/config")
def get_baseline_config(current_user: dict = Depends(get_current_user)):
    from planning_suite import config as cfg

    return {
        "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
        "raw_actuals_folder": cfg.RAW_ACTUALS_FOLDER,
        "dp_logics_folder": cfg.DP_LOGICS_FOLDER,
        "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
        "pipeline_params_sheet_url": cfg.PIPELINE_PARAMS_SHEET_URL,
    }
