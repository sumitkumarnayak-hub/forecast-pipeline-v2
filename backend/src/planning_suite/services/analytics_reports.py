"""Analytics reports — baseline summary, run history, downloads."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import numpy as np

from planning_suite.config import BASELINE_OUTPUTS_FOLDER, PROJECT_ROOT
from planning_suite.core.dataframe import df_to_records, sanitize_for_json
from planning_suite.services.output_validation import find_latest_file


def get_baseline_summary_report(*, limit: int = 500) -> dict:
    folder = Path(BASELINE_OUTPUTS_FOLDER)
    latest = find_latest_file(folder, "Summary_*.xlsx")
    if not latest:
        return {"available": False, "message": "No Summary_*.xlsx found."}

    df = pd.read_excel(latest)
    metrics = {}
    if "Base_Plan (qty)" in df.columns:
        metrics["total_base_plan"] = float(pd.to_numeric(df["Base_Plan (qty)"], errors="coerce").fillna(0).sum())
    if "city_name" in df.columns:
        metrics["cities"] = int(df["city_name"].nunique())
    if "hub_name" in df.columns:
        metrics["hubs"] = int(df["hub_name"].nunique())
    if "SKU Class Prod" in df.columns:
        metrics["sku_classes"] = int(df["SKU Class Prod"].nunique())

    by_cat = None
    if "SKU Class Prod" in df.columns and "Base_Plan (qty)" in df.columns:
        agg = (
            df.groupby("SKU Class Prod")["Base_Plan (qty)"]
            .apply(lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum())
            .reset_index()
            .rename(columns={"Base_Plan (qty)": "total"})
            .sort_values("total", ascending=False)
        )
        by_cat = df_to_records(agg)

    return sanitize_for_json(
        {
            "available": True,
            "file": latest.name,
            "rows": len(df),
            "metrics": metrics,
            "by_category": by_cat,
            "preview_rows": df_to_records(df.head(limit)),
            "columns": df.columns.tolist(),
        }
    )


def get_plan_comparison_report() -> dict:
    folder = Path(BASELINE_OUTPUTS_FOLDER)
    files = sorted(folder.glob("Summary_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
    return {
        "summaries": [
            {"name": f.name, "modified": f.stat().st_mtime, "path": str(f)} for f in files
        ],
        "message": "Select two summary files to compare (use Baseline → Review for full pivot).",
    }


def get_plan_comparison_placeholder() -> dict:
    return get_plan_comparison_report()


def get_actual_vs_plan_report(*, granularity: str = "city_category", limit: int = 200) -> dict:
    """Actual vs plan from 6w rolling data — city/category/hub aggregates."""
    try:
        from planning_suite.services.insights_analytics import load_6w_insights
    except FileNotFoundError as exc:
        return {"available": False, "message": str(exc)}

    df = load_6w_insights()
    if df.empty:
        return {"available": False, "message": "6w dataset is empty."}

    group_map = {
        "city": ["city_name"],
        "category": ["sub_category"],
        "city_category": ["city_name", "sub_category"],
        "city_category_hub": ["city_name", "sub_category", "hub_name"],
        "city_category_hub_day": ["city_name", "sub_category", "hub_name", "dow"],
    }
    keys = group_map.get(granularity, group_map["city_category"])
    missing = [k for k in keys if k not in df.columns]
    if missing:
        return {"available": False, "message": f"Missing columns: {missing}"}

    agg = (
        df.groupby(keys, as_index=False)
        .agg(
            plan_qty=("r7_plan", "sum"),
            actual_qty=("sales", "sum"),
            plan_rev=("r7_plan_rev", "sum"),
            actual_rev=("revenue", "sum"),
        )
    )
    agg["attainment_pct"] = np.where(agg["plan_qty"] > 0, agg["actual_qty"] / agg["plan_qty"] * 100, np.nan)
    agg["rev_gap"] = agg["actual_rev"] - agg["plan_rev"]
    agg["rev_gap_pct"] = np.where(agg["plan_rev"] > 0, (agg["actual_rev"] / agg["plan_rev"] - 1) * 100, np.nan)
    agg["abs_rev_gap"] = agg["rev_gap"].abs()

    total_plan = float(agg["plan_rev"].sum())
    total_actual = float(agg["actual_rev"].sum())
    mape = float((agg["rev_gap_pct"].abs()).mean()) if len(agg) else None
    bias = float(agg["rev_gap_pct"].mean()) if len(agg) else None

    return sanitize_for_json(
        {
            "available": True,
            "granularity": granularity,
            "metrics": {
                "total_plan_rev": total_plan,
                "total_actual_rev": total_actual,
                "forecast_accuracy_pct": (total_actual / total_plan * 100) if total_plan else None,
                "mape_pct": mape,
                "bias_pct": bias,
            },
            "columns": agg.columns.tolist(),
            "rows": df_to_records(agg.sort_values("abs_rev_gap", ascending=False).head(limit)),
        }
    )


def get_actual_vs_plan_summary() -> dict:
    return get_actual_vs_plan_report(granularity="city_category", limit=200)


def list_downloadable_reports() -> list[dict]:
    items = []
    folder = Path(BASELINE_OUTPUTS_FOLDER)
    if folder.is_dir():
        for f in sorted(folder.glob("Summary_*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
            items.append({"type": "baseline_summary", "name": f.name, "path": str(f)})
    hub = find_latest_file(PROJECT_ROOT, "Hub_Dist_Wk*.xlsx")
    if hub:
        items.append({"type": "final_plan", "name": hub.name, "path": str(hub)})
    pq = PROJECT_ROOT / "outputs" / "6w_v3.parquet"
    if pq.is_file():
        items.append({"type": "6w_rolling", "name": pq.name, "path": str(pq)})
    return items
