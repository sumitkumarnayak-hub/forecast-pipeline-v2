"""
City revenue trend charts — same logic as Streamlit reporting.city_revenue_trends.
Returns chart-ready series for the Next.js dashboard (recharts).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from features.dashboard.analytics_6w import read_6w_columns, resolve_6w_read_path

from features.dashboard.cache import cache_key, get_cached, mtime_key


DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CHART_COLORS = [
    "#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854",
    "#ffd92f", "#e5c494", "#b3b3b3", "#1b9e77", "#d95f02",
]


def _load_6w_city_agg_raw() -> pd.DataFrame:
    """City-level aggregates from 6w rolling data (mirrors reporting._load_6w_city_agg)."""
    cols = (
        "city_name", "sub_category", "process_dt",
        "revenue", "sales", "corrected_sales", "r7_plan_rev",
    )
    df = read_6w_columns(cols)
    df["process_dt"] = pd.to_datetime(df["process_dt"], errors="coerce")
    df = df.dropna(subset=["process_dt"])
    city_df = (
        df.groupby(["city_name", "sub_category", "process_dt"], as_index=False)
        .agg(
            revenue=("revenue", "sum"),
            sales=("sales", "sum"),
            corrected_sales=("corrected_sales", "sum"),
            plan_rev=("r7_plan_rev", "sum"),
        )
    )
    city_df["date"] = city_df["process_dt"].dt.date
    city_df["day_of_week"] = city_df["process_dt"].dt.strftime("%a")
    iso = city_df["process_dt"].dt.isocalendar()
    city_df["iso_week"] = iso.week.astype(int)
    city_df["iso_year"] = iso.year.astype(int)
    city_df["week_label"] = (
        city_df["iso_year"].astype(str) + "-W"
        + city_df["iso_week"].astype(str).str.zfill(2)
    )
    return city_df


def load_6w_city_agg() -> pd.DataFrame:
    path = resolve_6w_read_path()
    key = cache_key("6w", "city_agg", path, mtime_key(path))
    return get_cached(key, _load_6w_city_agg_raw)


def build_revenue_trends(
    cities: list[str] | None = None,
    categories: list[str] | None = None,
    days: list[str] | None = None,
    dod_view: str = "City",
    wow_view: str = "City",
) -> dict[str, Any]:
    path = resolve_6w_read_path()
    city_key = ",".join(sorted(cities or []))
    cat_key = ",".join(sorted(categories or []))
    day_key = ",".join(sorted(days or []))
    key = cache_key(
        "6w", "trends", path, mtime_key(path),
        city_key, cat_key, day_key, dod_view, wow_view,
    )
    return get_cached(
        key,
        lambda: _build_revenue_trends_raw(cities, categories, days, dod_view, wow_view),
    )


def _sort_x_values(values: list, x_col: str) -> list:
    """Chronological dates and ISO week labels — not lexicographic strings."""
    unique = list(dict.fromkeys(values))
    if x_col == "week_label":
        def _week_key(w: object) -> tuple[int, int]:
            parts = str(w).split("-W", 1)
            if len(parts) != 2:
                return (0, 0)
            try:
                return (int(parts[0]), int(parts[1]))
            except ValueError:
                return (0, 0)
        return sorted(unique, key=_week_key)
    if x_col == "date":
        return sorted(unique, key=lambda x: pd.Timestamp(x))
    return sorted(unique, key=lambda x: str(x))


def _format_x_value(x_raw: object, x_col: str) -> str:
    """Stable x keys for chart point lookup (date-only, no time component)."""
    if x_col in ("date", "process_dt"):
        try:
            return pd.Timestamp(x_raw).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
    if hasattr(x_raw, "isoformat") and not isinstance(x_raw, str):
        iso = x_raw.isoformat()
        if x_col in ("date", "process_dt") and "T" in iso:
            return iso.split("T", 1)[0]
        return iso
    return str(x_raw)


def _series_payload(
    agg: pd.DataFrame,
    group_col: str,
    x_col: str,
    title: str,
    x_label: str,
    *,
    x_order: list | None = None,
) -> dict[str, Any]:
    """Build multi-series line chart data: solid actual + dashed plan per group."""
    groups = sorted(agg[group_col].dropna().unique().tolist())
    raw_x = agg[x_col].dropna().unique().tolist()
    x_values = x_order if x_order is not None else _sort_x_values(raw_x, x_col)

    series: list[dict[str, Any]] = []
    for i, gval in enumerate(groups):
        color = CHART_COLORS[i % len(CHART_COLORS)]
        gdf = agg[agg[group_col] == gval].sort_values(x_col)
        points = []
        for _, row in gdf.iterrows():
            x_raw = row[x_col]
            x = _format_x_value(x_raw, x_col)
            points.append({
                "x": x,
                "actual": float(row["revenue"]) if pd.notna(row["revenue"]) else None,
                "plan": float(row["plan_rev"]) if pd.notna(row["plan_rev"]) else None,
            })
        series.append({
            "group": str(gval),
            "color": color,
            "points": points,
        })

    return {
        "title": title,
        "x_label": x_label,
        "x_values": [_format_x_value(v, x_col) for v in x_values],
        "series": series,
    }


def _build_revenue_trends_raw(
    cities: list[str] | None = None,
    categories: list[str] | None = None,
    days: list[str] | None = None,
    dod_view: str = "City",
    wow_view: str = "City",
) -> dict[str, Any]:
    """Day-on-day and week-on-week revenue trends (last 10 ISO weeks)."""
    df = load_6w_city_agg()
    if df.empty:
        return {"empty": True, "message": "No data found in the 6-week rolling file."}

    all_cities = sorted(df["city_name"].dropna().unique().tolist())
    all_cats = sorted(df["sub_category"].dropna().unique().tolist())

    sel_cities = cities if cities else all_cities[:3]
    sel_cats = categories or []
    sel_days = days or []

    week_meta = (
        df[["iso_year", "iso_week", "week_label"]]
        .drop_duplicates()
        .sort_values(["iso_year", "iso_week"])
    )
    last_10_weeks = week_meta.tail(10)["week_label"].tolist()

    # ── Day-on-day ────────────────────────────────────────────────────────
    fdf = df[df["week_label"].isin(last_10_weeks)].copy()
    if sel_cities:
        fdf = fdf[fdf["city_name"].isin(sel_cities)]
    if sel_cats:
        fdf = fdf[fdf["sub_category"].isin(sel_cats)]
    if sel_days:
        fdf = fdf[fdf["day_of_week"].isin(sel_days)]

    dod_chart: dict[str, Any] | None = None
    dod_table: list[dict] = []

    if not fdf.empty:
        if dod_view == "City":
            agg = (
                fdf.groupby(["date", "city_name"], as_index=False)
                .agg(revenue=("revenue", "sum"), plan_rev=("plan_rev", "sum"))
            )
            dod_chart = _series_payload(agg, "city_name", "date", "Day-on-Day Revenue by City", "Date")
        elif dod_view == "Category":
            agg = (
                fdf.groupby(["date", "sub_category"], as_index=False)
                .agg(revenue=("revenue", "sum"), plan_rev=("plan_rev", "sum"))
            )
            dod_chart = _series_payload(agg, "sub_category", "date", "Day-on-Day Revenue by Category", "Date")
        else:
            agg = (
                fdf.groupby(["date", "city_name", "sub_category"], as_index=False)
                .agg(revenue=("revenue", "sum"), plan_rev=("plan_rev", "sum"))
            )
            agg["label"] = agg["city_name"] + " · " + agg["sub_category"]
            dod_chart = _series_payload(agg, "label", "date", "Day-on-Day Revenue by City × Category", "Date")

        tbl = (
            fdf.groupby(["date", "day_of_week", "city_name", "sub_category"], as_index=False)
            .agg(Revenue=("revenue", "sum"), Plan_Revenue=("plan_rev", "sum"))
            .sort_values(["date", "city_name", "sub_category"])
        )
        dod_table = [
            {
                "Date": str(r["date"]),
                "Day": r["day_of_week"],
                "City": r["city_name"],
                "Category": r["sub_category"],
                "Actual Revenue": f"₹{r['Revenue']:,.0f}",
                "Plan Revenue": f"₹{r['Plan_Revenue']:,.0f}",
            }
            for _, r in tbl.iterrows()
        ]

    # ── Week-on-week ──────────────────────────────────────────────────────
    wdf = df[df["week_label"].isin(last_10_weeks)].copy()
    if sel_cities:
        wdf = wdf[wdf["city_name"].isin(sel_cities)]
    if sel_cats:
        wdf = wdf[wdf["sub_category"].isin(sel_cats)]

    latest_week = last_10_weeks[-1] if last_10_weeks else None
    latest_metrics: dict[str, Any] | None = None
    if latest_week and not wdf.empty:
        lw_df = wdf[wdf["week_label"] == latest_week]
        lw_rev = float(lw_df["revenue"].sum())
        lw_plan = float(lw_df["plan_rev"].sum())
        pct_diff = ((lw_rev - lw_plan) / lw_plan * 100) if lw_plan else 0
        latest_metrics = {
            "latest_week": latest_week,
            "actual_revenue": lw_rev,
            "plan_revenue": lw_plan,
            "pct_vs_plan": pct_diff,
        }

    wow_chart: dict[str, Any] | None = None
    wow_table: list[dict] = []

    if not wdf.empty:
        if wow_view == "City":
            wagg = (
                wdf.groupby(["week_label", "city_name"], as_index=False)
                .agg(revenue=("revenue", "sum"), plan_rev=("plan_rev", "sum"))
            )
            wagg["week_label"] = pd.Categorical(wagg["week_label"], categories=last_10_weeks, ordered=True)
            wagg = wagg.sort_values("week_label")
            wow_chart = _series_payload(
                wagg, "city_name", "week_label", "Week-on-Week Revenue by City", "Week",
                x_order=last_10_weeks,
            )
        elif wow_view == "Category":
            wagg = (
                wdf.groupby(["week_label", "sub_category"], as_index=False)
                .agg(revenue=("revenue", "sum"), plan_rev=("plan_rev", "sum"))
            )
            wagg["week_label"] = pd.Categorical(wagg["week_label"], categories=last_10_weeks, ordered=True)
            wagg = wagg.sort_values("week_label")
            wow_chart = _series_payload(
                wagg, "sub_category", "week_label", "Week-on-Week Revenue by Category", "Week",
                x_order=last_10_weeks,
            )
        else:
            wagg = (
                wdf.groupby(["week_label", "city_name", "sub_category"], as_index=False)
                .agg(revenue=("revenue", "sum"), plan_rev=("plan_rev", "sum"))
            )
            wagg["week_label"] = pd.Categorical(wagg["week_label"], categories=last_10_weeks, ordered=True)
            wagg = wagg.sort_values("week_label")
            wagg["label"] = wagg["city_name"] + " · " + wagg["sub_category"]
            wow_chart = _series_payload(
                wagg, "label", "week_label", "Week-on-Week Revenue by City × Category", "Week",
                x_order=last_10_weeks,
            )

        tbl_wow = (
            wdf.groupby(["week_label", "city_name", "sub_category"], as_index=False)
            .agg(Revenue=("revenue", "sum"), Plan_Revenue=("plan_rev", "sum"))
            .sort_values(["week_label", "city_name", "sub_category"])
        )
        wow_table = [
            {
                "Week": r["week_label"],
                "City": r["city_name"],
                "Category": r["sub_category"],
                "Actual Revenue": f"₹{r['Revenue']:,.0f}",
                "Plan Revenue": f"₹{r['Plan_Revenue']:,.0f}",
            }
            for _, r in tbl_wow.iterrows()
        ]

    return {
        "empty": False,
        "filters": {
            "all_cities": all_cities,
            "all_categories": all_cats,
            "all_days": DAY_ORDER,
            "last_10_weeks": last_10_weeks,
        },
        "day_on_day": {
            "chart": dod_chart,
            "table": dod_table,
            "empty": fdf.empty,
        },
        "week_on_week": {
            "chart": wow_chart,
            "table": wow_table,
            "latest_metrics": latest_metrics,
            "empty": wdf.empty,
        },
    }
