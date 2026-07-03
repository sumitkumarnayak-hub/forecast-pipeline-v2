"""Headless manual baseline operations — FastAPI / Next.js (no Streamlit)."""
from __future__ import annotations

import copy
import glob
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from planning_suite.config import (
    BASELINE_OUTPUTS_FOLDER,
    DP_LOGICS_FOLDER,
    DP_LOGICS_SHEET_URL,
    FF_MASTERS_XLSX,
    OUTPUT_PATH,
    PROJECT_ROOT,
    RAW_ACTUALS_FOLDER,
)
from planning_suite.core.dataframe import df_to_records, sanitize_for_json
from planning_suite.db.engine import Database
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.services.helpers import generate_run_id
from planning_suite.services.pipeline_flow import ACTIVE_DATASET
from planning_suite.services.raw_actuals_cache import (
    resolve_raw_actuals_for_week,
    write_week_parquet,
)
from planning_suite.services.sheets_session import get_sheets_manager
from planning_suite.services.workflow_notifications import (
    format_error_from_parameters,
    notify_baseline_run_finished,
)

FINAL_COLS = [
    "process_dt",
    "Sub-category",
    "week",
    "day",
    "product_id",
    "product_name",
    "sku class prod",
    "city_name",
    "hub_name",
    "sales",
    "final_sales",
    "simple_flag_when_SP_0",
    "simple_instances_when_SP_0",
    "simple_group_flag_when_SP_0",
    "simple_group_instances_when_SP_0",
]

DP_LOGICS_WORKSHEETS = [
    "City_Cat",
    "SellThroughFactor",
    "City_drops",
    "Percentile",
    "Avl_Flag",
]

ACTIVE_DATASET_META = OUTPUT_PATH / "active_dataset_meta.json"


def _engine():
    from planning_suite.services.baseline_engine import get_baseline_engine

    return get_baseline_engine(sheets=get_sheets_manager())


def _save_active_meta(*, rows: int, weeks: list[int], source: str, columns: list[str]) -> None:
    import json

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    ACTIVE_DATASET_META.write_text(
        json.dumps(
            {
                "rows": rows,
                "weeks": weeks,
                "source": source,
                "columns": columns,
                "updated_at": datetime.utcnow().isoformat(),
            }
        ),
        encoding="utf-8",
    )


def _load_active_meta() -> dict[str, Any]:
    import json

    if not ACTIVE_DATASET_META.is_file():
        return {}
    try:
        return json.loads(ACTIVE_DATASET_META.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_repository_status(*, lite: bool = True) -> dict[str, Any]:
    """Week files on disk. ``lite=True`` lists weeks from filenames only (fast)."""
    folder = RAW_ACTUALS_FOLDER
    rows: list[dict[str, Any]] = []
    saved_weeks: list[int] = []

    if os.path.isdir(folder):
        all_files = os.listdir(folder)
        parquet_files = sorted(
            f for f in all_files if f.startswith("Raw_Actuals_Wk") and f.endswith(".parquet")
        )
        xlsx_files = sorted(
            f for f in all_files if f.startswith("Raw_Actuals_Wk") and f.endswith(".xlsx")
        )
        parquet_weeks = {
            int(f.replace("Raw_Actuals_Wk", "").replace(".parquet", "")) for f in parquet_files
        }
        xlsx_only = [
            f
            for f in xlsx_files
            if int(f.replace("Raw_Actuals_Wk", "").replace(".xlsx", "")) not in parquet_weeks
        ]
        saved_week_files = parquet_files + xlsx_only
        saved_weeks = sorted(
            int(f.replace("Raw_Actuals_Wk", "").replace(".parquet", "").replace(".xlsx", ""))
            for f in saved_week_files
        )

        for f in saved_week_files:
            wk = int(f.replace("Raw_Actuals_Wk", "").replace(".parquet", "").replace(".xlsx", ""))
            fmt = "parquet" if f.endswith(".parquet") else "xlsx"
            if lite:
                rows.append(
                    {
                        "week": wk,
                        "week_label": f"Wk {wk}",
                        "rows": None,
                        "total_sales": None,
                        "total_net_sales": None,
                        "format": fmt,
                    }
                )
                continue

            fpath = os.path.join(folder, f)
            try:
                if f.endswith(".parquet"):
                    cols = pd.read_parquet(fpath).columns.tolist()
                    read_cols = [c for c in ["sales", "final_sales"] if c in cols]
                    wk_df = (
                        pd.read_parquet(fpath, columns=read_cols)
                        if read_cols
                        else pd.read_parquet(fpath, columns=["sales"])
                    )
                else:
                    preview = pd.read_excel(fpath, nrows=0).columns.tolist()
                    read_cols = [c for c in ["sales", "final_sales"] if c in preview]
                    wk_df = pd.read_excel(fpath, usecols=read_cols if read_cols else None)
                sales_col = (
                    "sales"
                    if "sales" in wk_df.columns
                    else ("Sales (qty)" if "Sales (qty)" in wk_df.columns else None)
                )
                total_sales = float(wk_df[sales_col].sum()) if sales_col else None
                total_net = (
                    float(wk_df["final_sales"].sum()) if "final_sales" in wk_df.columns else 0
                )
                rows.append(
                    {
                        "week": wk,
                        "week_label": f"Wk {wk}",
                        "rows": len(wk_df),
                        "total_sales": total_sales,
                        "total_net_sales": total_net,
                        "format": fmt,
                    }
                )
            except Exception:
                rows.append(
                    {
                        "week": wk,
                        "week_label": f"Wk {wk}",
                        "rows": None,
                        "total_sales": None,
                        "total_net_sales": None,
                        "format": fmt,
                    }
                )

    return sanitize_for_json(
        {
            "folder": folder,
            "weeks": saved_weeks,
            "summary_rows": rows,
            "empty": not saved_weeks,
        }
    )


def get_active_dataset_status(*, include_preview: bool = False) -> dict[str, Any]:
    path = str(ACTIVE_DATASET)
    exists = ACTIVE_DATASET.is_file()
    meta = _load_active_meta()
    rows = meta.get("rows")
    weeks = meta.get("weeks") or []
    source = meta.get("source", "")

    if exists and rows is None:
        try:
            meta_df = pd.read_parquet(path)
            if "week" in meta_df.columns:
                weeks = sorted(
                    pd.to_numeric(meta_df["week"], errors="coerce").dropna().astype(int).unique().tolist()
                )
            rows = len(meta_df)
            source = source or "active_dataset.parquet"
        except Exception:
            pass

    preview: list[dict] = []
    if include_preview and exists:
        try:
            preview_df = pd.read_parquet(path).head(100)
            preview = df_to_records(preview_df)
        except Exception:
            preview = []

    return sanitize_for_json(
        {
            "exists": exists,
            "path": path,
            "rows": rows,
            "weeks": weeks,
            "source": source,
            "columns": meta.get("columns") or [],
            "preview_rows": preview,
        }
    )


_DATES_CACHE = OUTPUT_PATH / "pipeline_dates_cache.json"
_DATES_CACHE_TTL_SEC = 300


def get_date_defaults(*, force_refresh: bool = False) -> dict[str, str]:
    if not force_refresh and _DATES_CACHE.is_file():
        try:
            payload = json.loads(_DATES_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("cached_at", 0)) < _DATES_CACHE_TTL_SEC:
                return {
                    "start_date": str(payload["start_date"])[:10],
                    "end_date": str(payload["end_date"])[:10],
                }
        except Exception:
            pass

    gsm = get_sheets_manager()
    params = gsm.read_pipeline_params()
    today = pd.Timestamp.today().normalize()
    start = params.get("start_date") or (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = params.get("end_date") or (today - timedelta(days=1)).strftime("%Y-%m-%d")
    result = {"start_date": str(start)[:10], "end_date": str(end)[:10]}
    try:
        _DATES_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _DATES_CACHE.write_text(
            json.dumps({**result, "cached_at": time.time()}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    return result


def save_date_range(start_date: str, end_date: str) -> None:
    gsm = get_sheets_manager()
    gsm.write_pipeline_params({"start_date": start_date, "end_date": end_date})
    try:
        _DATES_CACHE.parent.mkdir(parents=True, exist_ok=True)
        _DATES_CACHE.write_text(
            json.dumps(
                {
                    "start_date": start_date[:10],
                    "end_date": end_date[:10],
                    "cached_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def fetch_raw_data(
    *,
    start_date: str,
    end_date: str,
    also_save_csv: bool = False,
    use_cached_week: bool = True,
) -> dict[str, Any]:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    days = (end - start).days + 1
    if days > 7:
        raise ValueError(f"Selected range is {days} days — maximum is 7 days (1 week).")
    if start > end:
        raise ValueError("Start date must be before end date.")

    iso_week = int(start.isocalendar().week)
    folder = RAW_ACTUALS_FOLDER
    engine = _engine()

    def _fetch():
        return engine.fetch_raw_data_from_rds(
            start, end, sheets_manager=engine.sheets_manager
        )

    df, iso_week, from_cache = resolve_raw_actuals_for_week(
        start,
        folder,
        _fetch,
        force_refresh=not use_cached_week,
    )

    if df is None or df.empty:
        raise ValueError("No data found for the selected date range in the RDS file.")

    os.makedirs(folder, exist_ok=True)
    week_file = os.path.join(folder, f"Raw_Actuals_Wk{iso_week}.parquet")
    already_exists = os.path.exists(week_file)
    if not from_cache:
        write_week_parquet(df, iso_week, folder)
    elif not already_exists:
        write_week_parquet(df, iso_week, folder)

    csv_path = None
    if also_save_csv:
        csv_path = os.path.join(folder, f"Raw_Actuals_Wk{iso_week}.csv")
        df.to_csv(csv_path, index=False)

    return {
        "iso_week": iso_week,
        "rows": len(df),
        "from_cache": from_cache,
        "overwritten": already_exists and not from_cache,
        "parquet_path": week_file,
        "csv_path": csv_path,
    }


def load_weeks_into_active_dataset(weeks: list[int]) -> dict[str, Any]:
    if not weeks:
        raise ValueError("Select at least one week.")

    folder = RAW_ACTUALS_FOLDER
    all_dfs: list[pd.DataFrame] = []

    for wk in sorted(weeks):
        parquet_path = os.path.join(folder, f"Raw_Actuals_Wk{wk}.parquet")
        xlsx_path = os.path.join(folder, f"Raw_Actuals_Wk{wk}.xlsx")
        if os.path.exists(parquet_path):
            wk_df = pd.read_parquet(parquet_path)
        elif os.path.exists(xlsx_path):
            wk_df = pd.read_excel(xlsx_path)
        else:
            continue
        if "final_sales" not in wk_df.columns:
            wk_df["final_sales"] = 0
        cols_present = [c for c in FINAL_COLS if c in wk_df.columns]
        all_dfs.append(wk_df[cols_present])

    if not all_dfs:
        raise ValueError("No week files found for the selected weeks.")

    combined = pd.concat(all_dfs, ignore_index=True)

    if "hub_name" in combined.columns:
        mask = combined["hub_name"].astype(str).str.upper().str.startswith(("PAW", "OFF"))
        combined = combined[~mask].reset_index(drop=True)

    dedup_keys = [c for c in ["hub_name", "product_id", "process_dt"] if c in combined.columns]
    if dedup_keys:
        combined = combined.drop_duplicates(subset=dedup_keys, keep="first").reset_index(drop=True)

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(ACTIVE_DATASET, index=False)

    loaded_weeks = sorted(weeks)
    source = f"Repository Wk {', '.join(str(w) for w in loaded_weeks)}"
    _save_active_meta(
        rows=len(combined),
        weeks=loaded_weeks,
        source=source,
        columns=combined.columns.tolist(),
    )

    return {
        "rows": len(combined),
        "columns": len(combined.columns),
        "weeks": loaded_weeks,
        "source": source,
        "path": str(ACTIVE_DATASET),
    }


def get_pipeline_params() -> dict[str, Any]:
    gsm = get_sheets_manager()
    params = gsm.read_pipeline_params()
    active = get_active_dataset_status()
    dp_status = []
    os.makedirs(DP_LOGICS_FOLDER, exist_ok=True)
    for ws in DP_LOGICS_WORKSHEETS:
        fpath = os.path.join(DP_LOGICS_FOLDER, f"{ws}.xlsx")
        if os.path.exists(fpath):
            mtime = pd.Timestamp(os.path.getmtime(fpath), unit="s").strftime("%Y-%m-%d %H:%M")
            dp_status.append({"worksheet": ws, "status": "saved", "last_updated": mtime})
        else:
            dp_status.append({"worksheet": ws, "status": "not_synced", "last_updated": None})

    return sanitize_for_json(
        {
            "params": params,
            "active_dataset_ready": active.get("exists", False),
            "dp_logics_sheet_url": DP_LOGICS_SHEET_URL,
            "dp_logics_folder": DP_LOGICS_FOLDER,
            "dp_worksheets_status": dp_status,
        }
    )


def save_pipeline_params(updates: dict[str, Any]) -> dict[str, Any]:
    gsm = get_sheets_manager()
    gsm.write_pipeline_params(updates)
    return gsm.read_pipeline_params()


def sync_dp_logics() -> dict[str, Any]:
    from planning_suite.services.baseline_io import refresh_all_engine_sidecars

    gsm = get_sheets_manager()
    os.makedirs(DP_LOGICS_FOLDER, exist_ok=True)
    sync_results = gsm.sync_dp_logics_worksheets_to_folder(
        DP_LOGICS_FOLDER,
        DP_LOGICS_WORKSHEETS,
        allow_local_fallback=False,
    )
    sidecars = refresh_all_engine_sidecars(DP_LOGICS_FOLDER, FF_MASTERS_XLSX)
    return sanitize_for_json({"sync_results": sync_results, "sidecars": sidecars})


def list_summary_files() -> list[dict[str, str]]:
    folder = BASELINE_OUTPUTS_FOLDER
    if not os.path.isdir(folder):
        return []
    files = sorted(
        [f for f in os.listdir(folder) if f.startswith("Summary_") and f.endswith(".xlsx")],
        key=lambda f: os.path.getmtime(os.path.join(folder, f)),
        reverse=True,
    )
    return [
        {
            "name": f,
            "path": os.path.join(folder, f),
            "modified": datetime.fromtimestamp(os.path.getmtime(os.path.join(folder, f))).isoformat(),
        }
        for f in files[:20]
    ]


def get_generate_preflight() -> dict[str, Any]:
    """Pre-run checklist — mirrors Streamlit warnings before baseline engine."""
    active = get_active_dataset_status()
    gsm = get_sheets_manager()
    params = gsm.read_pipeline_params() or {}
    os.makedirs(DP_LOGICS_FOLDER, exist_ok=True)

    missing_dp = [
        ws
        for ws in DP_LOGICS_WORKSHEETS
        if not os.path.exists(os.path.join(DP_LOGICS_FOLDER, f"{ws}.xlsx"))
    ]
    masters_ok = os.path.isfile(FF_MASTERS_XLSX)
    tw = int(params.get("target_week") or datetime.now().isocalendar().week)
    ty = int(params.get("target_year") or datetime.now().year)

    checks = [
        {
            "id": "active_dataset",
            "label": "Active raw dataset loaded (Step 1)",
            "ok": bool(active.get("exists")),
            "detail": (
                f"{int(active.get('rows') or 0):,} rows"
                if active.get("exists")
                else "Load selected weeks under Baseline → Load Raw Data"
            ),
        },
        {
            "id": "dp_logics",
            "label": "DP Logics worksheets synced (Step 2)",
            "ok": len(missing_dp) == 0,
            "detail": (
                "All worksheets present locally"
                if not missing_dp
                else f"Missing: {', '.join(missing_dp)} — sync under Configure"
            ),
        },
        {
            "id": "ff_masters",
            "label": "Product_Masters.xlsx on disk",
            "ok": masters_ok,
            "detail": str(FF_MASTERS_XLSX) if masters_ok else "Run Master Data sync first",
        },
        {
            "id": "params",
            "label": "Pipeline target week configured",
            "ok": bool(params),
            "detail": f"Wk {tw} · {ty}" if params else "Pipeline params sheet unreadable",
        },
    ]
    return sanitize_for_json(
        {
            "checks": checks,
            "ready": all(c["ok"] for c in checks),
            "target_week": tw,
            "target_year": ty,
        }
    )


def get_generate_context() -> dict[str, Any]:
    active = get_active_dataset_status()
    gsm = get_sheets_manager()
    params = gsm.read_pipeline_params()
    preflight = get_generate_preflight()
    return sanitize_for_json(
        {
            "active_dataset": active,
            "params_configured": bool(params),
            "target_week": int(params.get("target_week") or datetime.now().isocalendar().week),
            "target_year": int(params.get("target_year") or datetime.now().year),
            "summaries": list_summary_files(),
            "script_path": str(PROJECT_ROOT / "scripts" / "optimized_baseline_avail_correction.py"),
            "preflight": preflight,
        }
    )


def run_baseline_engine(*, user_id: int, target_week: int | None = None, target_year: int | None = None) -> dict[str, Any]:
    active = get_active_dataset_status()
    if not active.get("exists"):
        raise ValueError("Active dataset not found. Load selected weeks in step 1 first.")

    gsm = get_sheets_manager()
    params = gsm.read_pipeline_params()
    tw = target_week or int(params.get("target_week") or datetime.now().isocalendar().week)
    ty = target_year or int(params.get("target_year") or datetime.now().year)

    if target_week is not None or target_year is not None:
        gsm.write_pipeline_params({"target_week": tw, "target_year": ty})

    _env = copy.copy(os.environ)
    _env["PYTHONIOENCODING"] = "utf-8"
    _env["PYTHONUTF8"] = "1"

    from planning_suite.services.demo_filter_dataset import prepare_demo_filter_dataset
    from planning_suite.services.demo_filter_store import get_demo_filter

    _demo = get_demo_filter(user_id)
    _active_ds, _env, filter_error, _demo_info = prepare_demo_filter_dataset(
        _env,
        demo_city=_demo.city,
        demo_hubs=_demo.hubs,
    )
    if filter_error:
        raise ValueError(filter_error)

    run_id = generate_run_id("BL")
    run_name = f"Baseline Wk{tw} {ty}"
    db = Database()
    db.save_baseline_run(
        {
            "run_id": run_id,
            "run_name": run_name,
            "user_id": user_id,
            "status": "running",
            "raw_data_file": active.get("source") or str(ACTIVE_DATASET),
            "parameters": params,
        }
    )

    script_path = str(PROJECT_ROOT / "scripts" / "optimized_baseline_avail_correction.py")
    _env["BASELINE_USE_ACTIVE_DATASET"] = "1"
    _env["BASELINE_ACTIVE_DATASET_PATH"] = _active_ds
    _env["PROJECT_ROOT"] = str(PROJECT_ROOT)

    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
            env=_env,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode == 0:
            folder = BASELINE_OUTPUTS_FOLDER
            saved = (
                sorted(
                    [f for f in os.listdir(folder) if f.startswith("Summary_") and f.endswith(".xlsx")],
                    key=lambda f: os.path.getmtime(os.path.join(folder, f)),
                    reverse=True,
                )
                if os.path.isdir(folder)
                else []
            )
            latest = saved[0] if saved else None
            output_path = os.path.join(folder, latest) if latest else ""
            db.update_baseline_run(
                run_id,
                status="completed",
                output_file=output_path,
                summary_stats={"week": tw, "year": ty},
            )
            notify_baseline_run_finished(
                run_id=run_id,
                run_name=run_name,
                status="completed",
                user_id=user_id,
                db=db,
            )
            return {
                "run_id": run_id,
                "status": "completed",
                "output_file": output_path,
                "stdout_tail": stdout[-4000:],
            }

        fail_params = {"stderr": stderr[-2000:], "stdout_tail": stdout[-2000:]}
        db.update_baseline_run(run_id, status="failed", parameters=fail_params)
        notify_baseline_run_finished(
            run_id=run_id,
            run_name=run_name,
            status="failed",
            user_id=user_id,
            error_detail=format_error_from_parameters(fail_params),
            db=db,
        )
        raise RuntimeError(stderr[-2000:] or "Baseline script failed")

    except subprocess.TimeoutExpired:
        db.update_baseline_run(run_id, status="failed", parameters={"error": "timeout_60min"})
        notify_baseline_run_finished(
            run_id=run_id,
            run_name=run_name,
            status="failed",
            user_id=user_id,
            error_detail="Script timed out after 60 minutes.",
            db=db,
        )
        raise RuntimeError("Baseline script timed out after 60 minutes.")
    except RuntimeError:
        raise
    except Exception as exc:
        db.update_baseline_run(run_id, status="failed", parameters={"error": str(exc)})
        notify_baseline_run_finished(
            run_id=run_id,
            run_name=run_name,
            status="failed",
            user_id=user_id,
            error_detail=str(exc),
            db=db,
        )
        raise


def preview_latest_summary(*, limit: int = 500) -> dict[str, Any]:
    folder = BASELINE_OUTPUTS_FOLDER
    if not os.path.isdir(folder):
        return {"available": False, "rows": []}
    candidates = sorted(
        glob.glob(os.path.join(folder, "Summary_*.xlsx")),
        key=os.path.getmtime,
        reverse=True,
    )
    if not candidates:
        return {"available": False, "rows": []}
    path = candidates[0]
    df = pd.read_excel(path, nrows=limit)
    return sanitize_for_json(
        {
            "available": True,
            "file": os.path.basename(path),
            "path": path,
            "columns": df.columns.tolist(),
            "rows": df_to_records(df),
        }
    )
