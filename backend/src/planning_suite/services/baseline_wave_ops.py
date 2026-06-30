"""Wave A baseline operations — comparison, bulk pull, previous baseline, approve hub view."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from planning_suite.config import (
    BASELINE_OUTPUTS_FOLDER,
    DP_LOGICS_FOLDER,
    DP_LOGICS_SHEET_KEY,
    FF_MASTERS_XLSX,
    OUTPUT_PATH,
    PROJECT_ROOT,
    RAW_ACTUALS_FOLDER,
)
from planning_suite.core.dataframe import df_to_records, sanitize_for_json
from planning_suite.services.helpers import normalize_base_plan_columns
from planning_suite.services.sheets_session import get_sheets_manager

HUB_SUGGESTION_CACHE = OUTPUT_PATH / "hub_suggestion_latest.parquet"
RV_CACHE_DIR = OUTPUT_PATH / "rv_cache"
PREV_BASELINE_LATEST = OUTPUT_PATH / "prev_baseline_latest.parquet"
HUB_WS_NAME = "Hub level Suggestion"
HUBS_TO_EXCLUDE = ["INDORE", "KKD", "RAIPUR", "NAGDRM", "VDR"]
DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

COMPARISON_VIEW_KEYS = {
    "city-day": "v1",
    "city-cat-day": "v2",
    "hub-cat-day": "v3",
    "hub-day": "v4",
}


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    lower = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        hit = lower.get(cand.strip().lower())
        if hit:
            return hit
    return None


def get_bulk_week_plan() -> list[dict[str, Any]]:
    """Preview of 10 historical weeks for bulk pull (Streamlit parity)."""
    repo_weeks = set()
    if os.path.isdir(RAW_ACTUALS_FOLDER):
        for f in os.listdir(RAW_ACTUALS_FOLDER):
            if f.startswith("Raw_Actuals_Wk") and (f.endswith(".parquet") or f.endswith(".xlsx")):
                wk = f.replace("Raw_Actuals_Wk", "").replace(".parquet", "").replace(".xlsx", "")
                try:
                    repo_weeks.add(int(wk))
                except ValueError:
                    pass

    today = pd.Timestamp.today().normalize()
    rows: list[dict[str, Any]] = []
    for i in range(1, 11):
        week_end = today - timedelta(days=int(today.weekday()) + 1) - timedelta(weeks=i - 1)
        week_start = week_end - timedelta(days=6)
        iso_wk = int(week_start.isocalendar().week)
        rows.append(
            {
                "iso_week": iso_wk,
                "start_date": str(week_start.date()),
                "end_date": str(week_end.date()),
                "already_saved": iso_wk in repo_weeks,
            }
        )
    return rows


def run_bulk_pull(*, also_save_csv: bool = False) -> dict[str, Any]:
    """Pull past 10 weeks from RDS cache into repository parquets."""
    from planning_suite.services.baseline_manual import _generator, _silent_streamlit

    os.makedirs(RAW_ACTUALS_FOLDER, exist_ok=True)
    gen = _generator()
    results: list[dict[str, Any]] = []

    with _silent_streamlit():
        full_df = gen._load_rds_cached()

    plan = get_bulk_week_plan()
    for entry in plan:
        iso_wk = entry["iso_week"]
        wk_start = pd.Timestamp(entry["start_date"])
        wk_end = pd.Timestamp(entry["end_date"])

        week_df = full_df[
            (full_df["process_dt"] >= wk_start)
            & (full_df["process_dt"] <= wk_end)
            & (~full_df["hub_name"].isin(HUBS_TO_EXCLUDE))
        ].copy()

        if all(c in week_df.columns for c in ["flag", "instances", "group_flag", "group_instances", "r7_inv"]):
            week_df["plan_sum"] = week_df.groupby(["hub_name", "process_dt", "product_id"])["r7_inv"].transform("sum")
            week_df["simple_flag_when_SP_0"] = np.where(
                week_df["plan_sum"] == 0, week_df["group_flag"], week_df["flag"]
            )
            week_df["simple_instances_when_SP_0"] = np.where(
                week_df["plan_sum"] == 0, week_df["group_instances"], week_df["instances"]
            )
            week_df["simple_group_flag_when_SP_0"] = week_df["group_flag"]
            week_df["simple_group_instances_when_SP_0"] = week_df["group_instances"]
            week_df["week"] = week_df["process_dt"].dt.isocalendar().week.astype(int)
            week_df["day"] = week_df["process_dt"].dt.strftime("%a")
            week_df.drop(columns=["plan_sum"], inplace=True)

        with _silent_streamlit():
            liq_wk = gen._fetch_liquidation_data(pd.Timestamp(wk_start), pd.Timestamp(wk_end))
        if not liq_wk.empty:
            week_df["product_id"] = week_df["product_id"].astype(str)
            week_df = week_df.merge(liq_wk, on=["hub_name", "product_id", "process_dt"], how="left")
            week_df["packets_sold"] = pd.to_numeric(week_df["packets_sold"], errors="coerce").fillna(0)
        else:
            week_df["packets_sold"] = 0
        week_df["final_sales"] = np.maximum(week_df["sales"] - week_df["packets_sold"], 0)

        if "hub_name" in week_df.columns:
            mask = week_df["hub_name"].astype(str).str.upper().str.startswith(("PAW", "OFF"))
            week_df = week_df[~mask].copy()
        dedup_keys = [c for c in ["hub_name", "product_id", "process_dt"] if c in week_df.columns]
        if dedup_keys:
            week_df = week_df.drop_duplicates(subset=dedup_keys, keep="first").reset_index(drop=True)

        week_file = os.path.join(RAW_ACTUALS_FOLDER, f"Raw_Actuals_Wk{iso_wk}.parquet")
        existed = os.path.exists(week_file)
        week_df.to_parquet(week_file, index=False)
        if also_save_csv:
            week_df.to_csv(os.path.join(RAW_ACTUALS_FOLDER, f"Raw_Actuals_Wk{iso_wk}.csv"), index=False)

        results.append(
            {
                "iso_week": iso_wk,
                "rows": len(week_df),
                "status": "overwritten" if existed else "saved",
                "csv": also_save_csv,
            }
        )

    return sanitize_for_json({"weeks_pulled": len(results), "results": results})


def fetch_previous_baseline(
    *,
    target_week: int | None = None,
    target_year: int | None = None,
) -> dict[str, Any]:
    """Fetch previous baseline from RDS cache and write prev_baseline_latest.parquet."""
    from planning_suite.services.baseline_manual import _generator, _silent_streamlit

    gsm = get_sheets_manager()
    params = gsm.read_pipeline_params()
    now = datetime.now()
    tw = int(target_week or params.get("target_week") or now.isocalendar().week)
    ty = int(target_year or params.get("target_year") or now.year)

    gen = _generator()
    with _silent_streamlit():
        df = gen._fetch_previous_baseline(tw, ty)

    if df is None or df.empty:
        raise ValueError(f"No previous baseline data for week {tw}" + (f" / {ty}" if target_year else ""))

    df = normalize_base_plan_columns(df)
    if "BasePlan" not in df.columns:
        raise ValueError(f"Previous baseline has no BasePlan column. Columns: {df.columns.tolist()}")

    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    cache_dir = OUTPUT_PATH / "prev_baseline_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    week_cache = cache_dir / f"prev_baseline_wk{tw}_yr{ty}.parquet"
    df.to_parquet(week_cache, index=False)
    df.to_parquet(PREV_BASELINE_LATEST, index=False)

    return sanitize_for_json(
        {
            "target_week": tw,
            "target_year": ty,
            "rows": len(df),
            "products": int(df["product_id"].nunique()) if "product_id" in df.columns else None,
            "hubs": int(df["hub_name"].nunique()) if "hub_name" in df.columns else None,
            "base_plan_sum": float(df["BasePlan"].sum()) if "BasePlan" in df.columns else None,
            "path": str(PREV_BASELINE_LATEST),
            "preview_rows": df_to_records(df.head(50)),
            "columns": df.columns.tolist(),
        }
    )


def _build_all_comparison_views() -> dict[str, Any]:
    from planning_suite.services.baseline_comparison import (
        CITY_ALIASES,
        CURRENT_VALUE_ALIASES,
        DAY_COLUMN_ALIASES,
        HUB_ALIASES,
        PREVIOUS_VALUE_ALIASES,
        SKU_ALIASES,
        build_comparison_view,
        find_column,
        resolve_hub_suggestion_previous,
        resolve_latest_summary,
    )

    cache_dir = PROJECT_ROOT / "outputs" / "cmp_cache"
    sum_df, sum_name, _ = resolve_latest_summary(BASELINE_OUTPUTS_FOLDER, cache_dir=cache_dir)
    log_df, log_source, log_path = resolve_hub_suggestion_previous(
        log_folder=DP_LOGICS_FOLDER, cache_dir=cache_dir
    )
    log_label = os.path.basename(log_path) if log_path else log_source

    s_city = find_column(sum_df, CITY_ALIASES)
    s_hub = find_column(sum_df, HUB_ALIASES)
    s_cat = find_column(sum_df, SKU_ALIASES)
    s_day = find_column(sum_df, DAY_COLUMN_ALIASES)
    s_fp = find_column(sum_df, CURRENT_VALUE_ALIASES)
    l_city = find_column(log_df, CITY_ALIASES)
    l_hub = find_column(log_df, HUB_ALIASES)
    l_cat = find_column(log_df, ["sku class prod", *SKU_ALIASES])
    l_day = find_column(log_df, DAY_COLUMN_ALIASES)
    l_bp = find_column(log_df, PREVIOUS_VALUE_ALIASES)

    views = {
        "v1": build_comparison_view(sum_df, log_df, s_fp, l_bp, [s_city, s_day], [l_city, l_day], ["City", "Day"])
        if s_city and l_city
        else None,
        "v2": build_comparison_view(
            sum_df, log_df, s_fp, l_bp, [s_city, s_cat, s_day], [l_city, l_cat, l_day], ["City", "Category", "Day"]
        )
        if s_city and l_city and s_cat and l_cat
        else None,
        "v3": build_comparison_view(
            sum_df, log_df, s_fp, l_bp, [s_hub, s_cat, s_day], [l_hub, l_cat, l_day], ["Hub", "Category", "Day"]
        )
        if s_cat and l_cat
        else None,
        "v4": build_comparison_view(sum_df, log_df, s_fp, l_bp, [s_hub, s_day], [l_hub, l_day], ["Hub", "Day"]),
    }

    RV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for key, frame in views.items():
        if frame is not None:
            frame.to_parquet(RV_CACHE_DIR / f"{key}.parquet", index=False)

    return {
        "current_file": sum_name,
        "previous_file": log_label,
        "views": views,
    }


def load_baseline_comparison(*, view: str = "city-day", refresh: bool = False) -> dict[str, Any]:
    """Return one comparison view (loads and caches all four on refresh)."""
    view_key = COMPARISON_VIEW_KEYS.get(view)
    if not view_key:
        raise ValueError(f"Unknown comparison view: {view}")

    path = RV_CACHE_DIR / f"{view_key}.parquet"
    if refresh or not path.is_file():
        bundle = _build_all_comparison_views()
    else:
        bundle = {
            "current_file": None,
            "previous_file": None,
            "views": {view_key: pd.read_parquet(path)},
        }
        meta_path = RV_CACHE_DIR / "meta.json"
        if meta_path.is_file():
            import json

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            bundle["current_file"] = meta.get("current_file")
            bundle["previous_file"] = meta.get("previous_file")

    if refresh:
        import json

        RV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (RV_CACHE_DIR / "meta.json").write_text(
            json.dumps(
                {"current_file": bundle.get("current_file"), "previous_file": bundle.get("previous_file")},
                indent=2,
            ),
            encoding="utf-8",
        )

    frame = bundle["views"].get(view_key)
    if frame is None:
        full = _build_all_comparison_views() if not refresh else bundle
        frame = full["views"].get(view_key)
    if frame is None:
        raise ValueError(f"Comparison view '{view}' could not be built — check summary and hub log files.")

    return sanitize_for_json(
        {
            "view": view,
            "current_file": bundle.get("current_file"),
            "previous_file": bundle.get("previous_file"),
            "columns": frame.columns.tolist(),
            "rows": df_to_records(frame),
            "row_count": len(frame),
        }
    )


def load_hub_suggestion_for_approve(
    *,
    refresh: bool = False,
    city_filter: str = "All",
    sku_filter: str = "All",
) -> dict[str, Any]:
    """Load Hub level Suggestion and return metrics + Mon–Sun pivot."""
    df: pd.DataFrame | None = None
    source = "cache"

    if not refresh and HUB_SUGGESTION_CACHE.is_file():
        try:
            df = pd.read_parquet(HUB_SUGGESTION_CACHE)
        except Exception:
            df = None

    if df is None or refresh:
        gsm = get_sheets_manager()
        ws = gsm.gc.open_by_key(DP_LOGICS_SHEET_KEY).worksheet(HUB_WS_NAME)
        raw = ws.get_all_values()
        if len(raw) < 2:
            raise ValueError("Hub level Suggestion sheet is empty — run baseline first.")
        df = pd.DataFrame(raw[1:], columns=raw[0])
        df.columns = [str(c).strip() for c in df.columns]
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        df.to_parquet(HUB_SUGGESTION_CACHE, index=False)
        source = "google_sheets"

    city_col = _find_col(df, ["city_name", "city"])
    hub_col = _find_col(df, ["hub_name", "hub"])
    sku_col = _find_col(df, ["sku class prod", "SKU Class Prod", "sku_class_prod", "category"])
    day_col = _find_col(df, ["day"])
    bp_col = _find_col(df, ["Base_plan", "base_plan", "base plan", "BasePlan"])
    if not all([hub_col, sku_col, day_col, bp_col]):
        raise ValueError(f"Sheet missing required columns. Found: {df.columns.tolist()}")

    work = df.copy()
    work[bp_col] = pd.to_numeric(work[bp_col], errors="coerce").fillna(0)
    grp_col = city_col if city_col else hub_col
    grp_label = "City" if city_col else "Hub"

    if city_filter != "All" and grp_col:
        work = work[work[grp_col].astype(str) == city_filter]
    if sku_filter != "All":
        work = work[work[sku_col].astype(str) == sku_filter]

    pivot_idx = [c for c in [city_col, hub_col, sku_col] if c]
    agg = work.groupby(pivot_idx + [day_col], as_index=False)[bp_col].sum()
    pivot = (
        agg.pivot_table(index=pivot_idx, columns=day_col, values=bp_col, aggfunc="sum", fill_value=0)
        .reset_index()
        if not agg.empty
        else pd.DataFrame()
    )
    if not pivot.empty:
        pivot.columns.name = None
        day_cols = [d for d in DAY_ORDER if d in pivot.columns]
        extra = [d for d in pivot.columns if d not in pivot_idx and d not in day_cols]
        pivot = pivot[pivot_idx + day_cols + extra]
        num_cols = day_cols + extra
        pivot["Total"] = pivot[num_cols].sum(axis=1)
        day_totals = {d: int(pivot[d].sum()) for d in day_cols}
    else:
        day_totals = {}

    filters = {
        "group_label": grp_label,
        "cities": ["All"] + sorted(df[grp_col].dropna().astype(str).unique().tolist()) if grp_col else ["All"],
        "sku_classes": ["All"] + sorted(df[sku_col].dropna().astype(str).unique().tolist()),
    }

    return sanitize_for_json(
        {
            "source": source,
            "row_count": len(work),
            "total_rows": len(df),
            "metrics": {
                "total_base_plan": int(df[bp_col].sum()),
                "unique_groups": int(df[grp_col].nunique()) if grp_col else 0,
                "sku_classes": int(df[sku_col].nunique()),
                "hubs": int(df[hub_col].nunique()),
            },
            "filters": filters,
            "day_totals": day_totals,
            "pivot_columns": pivot.columns.tolist() if not pivot.empty else [],
            "pivot_rows": df_to_records(pivot),
        }
    )


HUB_SKU_CMP_CACHE = OUTPUT_PATH / "cmp_baseline_latest.parquet"


def load_hub_sku_day_comparison(*, refresh: bool = False, write_sheet: bool = False) -> dict[str, Any]:
    """Hub × SKU × Day previous vs current — Streamlit 'Load Comparison' parity."""
    from planning_suite.services.baseline_comparison import (
        build_hub_sku_day_comparison,
        resolve_hub_suggestion_previous,
        resolve_latest_summary,
    )

    if not refresh and HUB_SKU_CMP_CACHE.is_file():
        cmp_df = pd.read_parquet(HUB_SKU_CMP_CACHE)
        meta_path = RV_CACHE_DIR / "meta.json"
        current_file = previous_file = None
        if meta_path.is_file():
            import json

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            current_file = meta.get("current_file")
            previous_file = meta.get("previous_file")
    else:
        _CMP_CACHE_DIR = str(RV_CACHE_DIR)
        sum_df, sum_name, _ = resolve_latest_summary(BASELINE_OUTPUTS_FOLDER, cache_dir=_CMP_CACHE_DIR)
        log_df, log_source, log_path = resolve_hub_suggestion_previous(
            log_folder=DP_LOGICS_FOLDER, cache_dir=_CMP_CACHE_DIR
        )
        cmp_df = build_hub_sku_day_comparison(sum_df, log_df)
        OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
        cmp_df.to_parquet(HUB_SKU_CMP_CACHE, index=False)
        current_file = sum_name
        previous_file = os.path.basename(log_path) if log_path else log_source

    prev_tot = int(cmp_df["Previous Baseline"].sum()) if not cmp_df.empty else 0
    curr_tot = int(cmp_df["Current Baseline"].sum()) if not cmp_df.empty else 0
    pct_tot = round((curr_tot - prev_tot) / prev_tot * 100, 1) if prev_tot else 0

    sheet_status: dict[str, Any] = {"attempted": False}
    if write_sheet and not cmp_df.empty:
        sheet_status["attempted"] = True
        try:
            from planning_suite.config import VALIDATION_SHEET_URL
            from planning_suite.services.google_sheets import GoogleSheetsManager
            from gspread_dataframe import set_with_dataframe
            import gspread

            gsm = GoogleSheetsManager()
            vss = gsm.gc.open_by_url(VALIDATION_SHEET_URL)
            try:
                vws = vss.worksheet("Baseline")
            except gspread.exceptions.WorksheetNotFound:
                vws = vss.add_worksheet(title="Baseline", rows=max(len(cmp_df) + 100, 500), cols=10)
            vws.clear()
            set_with_dataframe(vws, cmp_df)
            sheet_status["success"] = True
        except Exception as exc:
            sheet_status["success"] = False
            sheet_status["error"] = str(exc)

    return sanitize_for_json(
        {
            "current_file": current_file,
            "previous_file": previous_file,
            "columns": cmp_df.columns.tolist(),
            "rows": df_to_records(cmp_df),
            "row_count": len(cmp_df),
            "metrics": {
                "previous_total": prev_tot,
                "current_total": curr_tot,
                "overall_delta_pct": pct_tot,
            },
            "sheet_write": sheet_status,
        }
    )

