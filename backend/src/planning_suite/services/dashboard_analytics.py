"""
Dashboard weekly analytics — same computations as Streamlit reporting.display_dashboard_page.
Returns JSON-serializable structures for the Next.js UI.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from planning_suite.services.analytics_6w import add_iso_week_columns, read_6w_columns, resolve_6w_read_path
from planning_suite.services.dashboard_cache import cache_key, get_cached, mtime_key


def _pct(plan: pd.Series, base: pd.Series) -> np.ndarray:
    return np.where(base > 0, (plan / base - 1) * 100, np.nan)


def _date_order(df: pd.DataFrame) -> list[str]:
    return (
        df[["process_dt", "Date"]]
        .drop_duplicates()
        .sort_values("process_dt")["Date"]
        .tolist()
    )


def _pivot_to_table(pivot_df: pd.DataFrame, label_col: str) -> dict[str, Any]:
    """Convert a pivot dataframe to { label_col, columns, rows } with raw float values."""
    if pivot_df.empty:
        return {"label_col": label_col, "columns": [label_col], "rows": []}
    cols = [label_col] + [c for c in pivot_df.columns if c != label_col]
    rows: list[dict[str, Any]] = []
    for rec in pivot_df[cols].to_dict(orient="records"):
        entry: dict[str, Any] = {}
        for c in cols:
            v = rec.get(c)
            if c == label_col:
                entry[c] = str(v) if pd.notna(v) else ""
            elif pd.isna(v):
                entry[c] = None
            else:
                entry[c] = float(v)
        rows.append(entry)
    return {"label_col": label_col, "columns": cols, "rows": rows}


def _format_table_display(rows: list[dict], money_cols: set[str] | None = None) -> list[dict]:
    """Format numeric columns for display tables (new hubs/products)."""
    money_cols = money_cols or set()
    out = []
    for row in rows:
        formatted = {}
        for k, v in row.items():
            if k in money_cols and isinstance(v, (int, float)) and not pd.isna(v):
                formatted[k] = f"₹{v:,.0f}"
            elif isinstance(v, float) and not pd.isna(v):
                formatted[k] = f"{v:,.0f}"
            else:
                formatted[k] = v
        out.append(formatted)
    return out


def _load_6w_full_data_raw() -> pd.DataFrame:
    """Hub×product level 6w data for dashboard analytics (mirrors reporting._load_6w_full_data)."""
    cols = (
        "city_name", "hub_name", "product_id", "product_name",
        "sub_category", "process_dt",
        "r7_plan", "r7_plan_rev", "r7_inv", "BasePlan", "BaseRev",
    )
    df = read_6w_columns(cols)
    return add_iso_week_columns(df)


def load_6w_full_data() -> pd.DataFrame:
    """Cached 6w hub×product frame — shared across users until source file mtime changes."""
    path = resolve_6w_read_path()
    key = cache_key("6w", "full", path, mtime_key(path))
    return get_cached(key, _load_6w_full_data_raw)


def list_available_weeks() -> dict[str, Any]:
    """ISO week labels available in the 6w dataset."""
    path = resolve_6w_read_path()
    key = cache_key("6w", "weeks", path, mtime_key(path))
    return get_cached(key, _list_available_weeks_raw)


def _list_available_weeks_raw() -> dict[str, Any]:
    df = load_6w_full_data()
    if df.empty:
        return {"weeks": [], "default_week": None}
    week_meta = (
        df[["iso_year", "iso_week", "week_label"]]
        .drop_duplicates()
        .sort_values(["iso_year", "iso_week"])
        .reset_index(drop=True)
    )
    weeks = week_meta["week_label"].tolist()
    return {"weeks": weeks, "default_week": weeks[-1] if weeks else None}


def build_week_analytics(week_label: str) -> dict[str, Any]:
    """Cached weekly dashboard payload — same logic as Streamlit display_dashboard_page."""
    path = resolve_6w_read_path()
    key = cache_key("6w", "analytics", path, mtime_key(path), week_label)
    return get_cached(key, lambda: _build_week_analytics_raw(week_label))


def _build_week_analytics_raw(week_label: str) -> dict[str, Any]:
    df = load_6w_full_data()
    if df.empty:
        return {"empty": True, "message": "No data found in the 6-week rolling file."}

    week_meta = (
        df[["iso_year", "iso_week", "week_label"]]
        .drop_duplicates()
        .sort_values(["iso_year", "iso_week"])
        .reset_index(drop=True)
    )
    all_week_labels = week_meta["week_label"].tolist()

    if week_label not in all_week_labels:
        week_label = all_week_labels[-1]

    sel_idx = all_week_labels.index(week_label)
    sel_df = df[df["week_label"] == week_label]

    prev_week_label = all_week_labels[sel_idx - 1] if sel_idx > 0 else None
    prev_df = df[df["week_label"] == prev_week_label] if prev_week_label else pd.DataFrame()
    prev_available = not prev_df.empty

    w_start = sel_df["process_dt"].min().strftime("%d %b")
    w_end = sel_df["process_dt"].max().strftime("%d %b %Y")

    kpis = {
        "total_plan_qty": float(sel_df["r7_plan"].sum()),
        "total_plan_rev": float(sel_df["r7_plan_rev"].sum()),
        "n_cities": int(sel_df["city_name"].nunique()),
        "n_hubs": int(sel_df["hub_name"].nunique()),
        "n_skus": int(sel_df["product_id"].nunique()),
    }

    # ── Plan / Baseline Delta % — City × Date ─────────────────────────────
    cd = (
        sel_df.groupby(["city_name", "process_dt"], as_index=False)
        .agg(plan_rev=("r7_plan_rev", "sum"), base_rev=("BaseRev", "sum"))
    )
    cd["Delta"] = _pct(cd["plan_rev"], cd["base_rev"])
    cd["Date"] = pd.to_datetime(cd["process_dt"]).dt.strftime("%d %b")
    ordered_dates = _date_order(cd)
    pivot_cd = (
        cd.dropna(subset=["Delta"])
        .pivot(index="city_name", columns="Date", values="Delta")
        .reindex(columns=[d for d in ordered_dates if d in cd["Date"].unique()])
        .reset_index()
        .rename(columns={"city_name": "City"})
    )
    pivot_cd.columns.name = None
    delta_city_date = _pivot_to_table(pivot_cd, "City")

    # ── City × Category × Date ────────────────────────────────────────────
    ccd = (
        sel_df.groupby(["city_name", "sub_category", "process_dt"], as_index=False)
        .agg(plan_rev=("r7_plan_rev", "sum"), base_rev=("BaseRev", "sum"))
    )
    ccd["Delta"] = _pct(ccd["plan_rev"], ccd["base_rev"])
    ccd["Date"] = pd.to_datetime(ccd["process_dt"]).dt.strftime("%d %b")
    ccd["Row"] = ccd["city_name"] + "  ·  " + ccd["sub_category"]
    ordered_dates2 = _date_order(ccd)
    pivot_ccd = (
        ccd.dropna(subset=["Delta"])
        .pivot(index="Row", columns="Date", values="Delta")
        .reindex(columns=[d for d in ordered_dates2 if d in ccd["Date"].unique()])
        .sort_index()
        .reset_index()
        .rename(columns={"Row": "City · Category"})
    )
    pivot_ccd.columns.name = None
    delta_city_cat_date = _pivot_to_table(pivot_ccd, "City · Category")

    # ── Inventory Buffer ──────────────────────────────────────────────────
    cc_buf = (
        sel_df.groupby(["city_name", "sub_category"], as_index=False)
        .agg(r7=("r7_plan", "sum"), inv=("r7_inv", "sum"))
    )
    cc_buf["pct"] = np.where(
        cc_buf["r7"] > 0,
        (cc_buf["inv"] / cc_buf["r7"] - 1) * 100,
        np.nan,
    )
    pivot_buf = (
        cc_buf.dropna(subset=["pct"])
        .pivot(index="city_name", columns="sub_category", values="pct")
    )
    inventory_buffer: dict[str, Any] = {"available": not pivot_buf.empty}
    if not pivot_buf.empty:
        z = pivot_buf.values.tolist()
        z_clean = [[None if (isinstance(v, float) and np.isnan(v)) else float(v) for v in row] for row in z]
        inventory_buffer.update({
            "cities": pivot_buf.index.tolist(),
            "categories": pivot_buf.columns.tolist(),
            "values": z_clean,
        })

    # ── New Hubs & Products ───────────────────────────────────────────────
    new_additions: dict[str, Any] = {
        "prev_available": prev_available,
        "prev_week_label": prev_week_label,
        "new_hubs": [],
        "new_products": {"by_product": [], "by_city": [], "by_category": []},
        "new_hub_count": 0,
        "new_product_count": 0,
    }

    if prev_available:
        sel_hubs = set(sel_df["hub_name"].dropna().unique())
        prev_hubs = set(prev_df["hub_name"].dropna().unique())
        new_hub_names = sel_hubs - prev_hubs

        prev_prods = set(prev_df["product_id"].dropna().unique())
        prod_plan = sel_df.groupby("product_id", as_index=False)["r7_plan"].sum()
        new_prod_ids = set(
            prod_plan[
                ~prod_plan["product_id"].isin(prev_prods)
                & (prod_plan["r7_plan"] > 0)
            ]["product_id"].tolist()
        )

        new_additions["new_hub_count"] = len(new_hub_names)
        new_additions["new_product_count"] = len(new_prod_ids)

        if new_hub_names:
            hub_tbl = (
                sel_df[sel_df["hub_name"].isin(new_hub_names)]
                .groupby(["hub_name", "city_name"], as_index=False)
                .agg(Plan_Rev=("r7_plan_rev", "sum"), Plan_Qty=("r7_plan", "sum"))
                .sort_values("Plan_Rev", ascending=False)
            )
            hub_rows = hub_tbl.rename(columns={
                "hub_name": "Hub", "city_name": "City",
                "Plan_Rev": "Plan Revenue", "Plan_Qty": "Plan Qty",
            }).to_dict(orient="records")
            new_additions["new_hubs"] = _format_table_display(hub_rows, {"Plan Revenue"})

        new_prod_base = sel_df[sel_df["product_id"].isin(new_prod_ids)]
        if not new_prod_base.empty:
            prod_tbl = (
                new_prod_base
                .groupby(["product_name", "sub_category"], as_index=False)
                .agg(Plan_Rev=("r7_plan_rev", "sum"), Plan_Qty=("r7_plan", "sum"))
                .sort_values("Plan_Rev", ascending=False)
            )
            prod_rows = prod_tbl.rename(columns={
                "product_name": "Product", "sub_category": "Category",
                "Plan_Rev": "Plan Revenue", "Plan_Qty": "Plan Qty",
            }).to_dict(orient="records")
            new_additions["new_products"]["by_product"] = _format_table_display(prod_rows, {"Plan Revenue"})

            city_tbl = (
                new_prod_base
                .groupby(["city_name", "product_name"], as_index=False)
                .agg(Plan_Rev=("r7_plan_rev", "sum"), Plan_Qty=("r7_plan", "sum"))
                .sort_values(["city_name", "Plan_Rev"], ascending=[True, False])
            )
            city_rows = city_tbl.rename(columns={
                "city_name": "City", "product_name": "Product",
                "Plan_Rev": "Plan Revenue", "Plan_Qty": "Plan Qty",
            }).to_dict(orient="records")
            new_additions["new_products"]["by_city"] = _format_table_display(city_rows, {"Plan Revenue"})

            cat_tbl = (
                new_prod_base
                .groupby(["sub_category", "product_name"], as_index=False)
                .agg(Plan_Rev=("r7_plan_rev", "sum"), Plan_Qty=("r7_plan", "sum"))
                .sort_values(["sub_category", "Plan_Rev"], ascending=[True, False])
            )
            cat_rows = cat_tbl.rename(columns={
                "sub_category": "Category", "product_name": "Product",
                "Plan_Rev": "Plan Revenue", "Plan_Qty": "Plan Qty",
            }).to_dict(orient="records")
            new_additions["new_products"]["by_category"] = _format_table_display(cat_rows, {"Plan Revenue"})

    return {
        "empty": False,
        "week_label": week_label,
        "week_range": {"start": w_start, "end": w_end},
        "prev_week_label": prev_week_label,
        "prev_available": prev_available,
        "kpis": kpis,
        "delta_city_date": delta_city_date,
        "delta_city_cat_date": delta_city_cat_date,
        "inventory_buffer": inventory_buffer,
        "new_additions": new_additions,
    }
