"""Insights analytics — JSON payloads for Analytics → Insights (Streamlit parity)."""
from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from app.config import AVAILABILITY_LOSS_SHEET_URL
from core.utils.dataframe import df_to_records, sanitize_for_json

from features.dashboard.analytics_6w import add_iso_week_columns, describe_missing_6w_sources, read_6w_columns, resolve_6w_read_path

from features.dashboard.analytics import list_available_weeks

from features.dashboard.cache import cache_key, get_cached, mtime_key


INSIGHTS_6W_COLS = (
    "city_name", "hub_name", "product_id", "product_name",
    "sub_category", "process_dt",
    "sales", "revenue", "corrected_sales",
    "r7_plan", "r7_plan_rev", "r7_inv", "BasePlan", "BaseRev",
    "flag", "instances",
    "wastage_qty_Quality", "wastage_qty_Expiry",
    "wastage_val_Quality", "wastage_val_Expiry",
    "price",
)


def _parse_gsheet_date_series(raw: pd.Series) -> pd.Series:
    if raw is None or len(raw) == 0:
        return pd.Series(dtype="datetime64[ns]")
    s = raw.copy()
    if pd.api.types.is_datetime64_any_dtype(s):
        return pd.to_datetime(s, errors="coerce").dt.normalize()
    strv = (
        s.astype(str)
        .str.replace("\xa0", " ", regex=False)
        .str.strip()
        .replace({"nan": np.nan, "NaT": np.nan, "None": np.nan, "": np.nan})
    )
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    num = pd.to_numeric(strv, errors="coerce")
    looks_serial = strv.str.fullmatch(r"-?\d+(\.\d+)?", na=False) & num.notna()
    serial = looks_serial & (num > 20000) & (num < 150000)
    if serial.any():
        out.loc[serial] = pd.to_datetime(num[serial], unit="D", origin="1899-12-30", errors="coerce")
    text = (~serial) & strv.notna()
    if text.any():
        t = strv[text]
        parsed = pd.to_datetime(t, errors="coerce", format="mixed", dayfirst=True)
        ambig = parsed.isna() & t.notna()
        if ambig.any():
            parsed.loc[ambig] = pd.to_datetime(t[ambig], errors="coerce", format="mixed", dayfirst=False)
        still = parsed.isna() & t.notna()
        if still.any():
            parsed.loc[still] = pd.to_datetime(t[still], errors="coerce")
        out.loc[text] = parsed
    return pd.to_datetime(out, errors="coerce").dt.normalize()


def _load_6w_insights_raw() -> pd.DataFrame:
    df = read_6w_columns(INSIGHTS_6W_COLS)
    df["process_dt"] = pd.to_datetime(df["process_dt"], errors="coerce")
    df = df.dropna(subset=["process_dt"])
    num_cols = [
        "sales", "revenue", "corrected_sales", "r7_plan", "r7_plan_rev",
        "r7_inv", "BasePlan", "BaseRev", "flag", "instances",
        "wastage_qty_Quality", "wastage_qty_Expiry",
        "wastage_val_Quality", "wastage_val_Expiry", "price",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    iso = df["process_dt"].dt.isocalendar()
    df["iso_year"] = iso["year"].astype(int)
    df["iso_week"] = iso["week"].astype(int)
    df["week_label"] = df["iso_year"].astype(str) + "-W" + df["iso_week"].astype(str).str.zfill(2)
    df["dow"] = df["process_dt"].dt.strftime("%a")
    df["total_wastage_val"] = df["wastage_val_Quality"] + df["wastage_val_Expiry"]
    df["total_wastage_qty"] = df["wastage_qty_Quality"] + df["wastage_qty_Expiry"]
    df["attainment_pct"] = np.where(df["r7_plan"] > 0, df["sales"] / df["r7_plan"] * 100, np.nan)
    df["avail_pct"] = np.where(df["instances"] > 0, df["flag"] / df["instances"] * 100, np.nan)
    return df


def load_6w_insights() -> pd.DataFrame:
    path = resolve_6w_read_path()
    key = cache_key("insights", "6w_raw", path, mtime_key(path))
    return get_cached(key, _load_6w_insights_raw)


def _build_hub_city_map() -> pd.DataFrame:
    df = load_6w_insights()
    return (
        df.sort_values("process_dt")
        .drop_duplicates("hub_name", keep="last")[["hub_name", "city_name"]]
        .reset_index(drop=True)
    )


def load_loss_sheet() -> pd.DataFrame:
    path_key = AVAILABILITY_LOSS_SHEET_URL or "none"
    key = cache_key("insights", "loss_sheet", path_key)
    return get_cached(key, _load_loss_sheet_raw)


def _load_loss_sheet_raw() -> pd.DataFrame:
    if not AVAILABILITY_LOSS_SHEET_URL:
        return pd.DataFrame()
    from core.shared.sheets_session import get_sheets_manager


    gsm = get_sheets_manager()
    raw = gsm.read_worksheet_uncached("availability_loss", "avail_led_rev_loss")
    if raw is None or raw.empty:
        return pd.DataFrame()

    raw = raw.rename(columns={c: c.strip() for c in raw.columns})
    for c in list(raw.columns):
        if str(c).strip().lower() == "date" and c != "Date":
            raw = raw.rename(columns={c: "Date"})
            break

    rename = {
        "Hub Name": "hub_name",
        "Category": "category",
        "Date": "process_dt",
        "Delivered qty plan today": "delivered_qty_plan_today",
        "avoidable": "loss_qty_avoidable",
        "unavoidable": "loss_qty_unavoidable",
        "Sum of Delivered plan today": "delivered_plan_qty",
        "New Demand Loss": "demand_loss_rev",
        "New Supply Loss": "supply_loss_rev",
        "Total rev Loss": "total_loss_rev",
    }
    rename = {k: v for k, v in rename.items() if k in raw.columns}
    df = raw.rename(columns=rename).copy()
    if "process_dt" not in df.columns:
        return pd.DataFrame()

    df["process_dt"] = _parse_gsheet_date_series(df["process_dt"])
    df = df.dropna(subset=["process_dt"])
    num_cols = [
        "delivered_qty_plan_today", "loss_qty_avoidable", "loss_qty_unavoidable",
        "delivered_plan_qty", "demand_loss_rev", "supply_loss_rev", "total_loss_rev",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = (
                df[c].astype(str)
                .str.replace(",", "", regex=False)
                .str.replace("₹", "", regex=False)
                .str.strip()
                .replace("", np.nan)
                .astype(float)
            )
        else:
            df[c] = 0.0

    df["loss_qty_total"] = df["loss_qty_avoidable"].fillna(0) + df["loss_qty_unavoidable"].fillna(0)
    df["total_loss_rev"] = df["total_loss_rev"].fillna(
        df["demand_loss_rev"].fillna(0) + df["supply_loss_rev"].fillna(0)
    )
    iso = df["process_dt"].dt.isocalendar()
    df["iso_year"] = iso["year"].astype(int)
    df["iso_week"] = iso["week"].astype(int)
    df["week_label"] = df["iso_year"].astype(str) + "-W" + df["iso_week"].astype(str).str.zfill(2)
    df["dow"] = df["process_dt"].dt.strftime("%a")
    for c in ("hub_name", "category"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    df = df[~(
        (df["demand_loss_rev"].fillna(0) == 0)
        & (df["supply_loss_rev"].fillna(0) == 0)
        & (df["total_loss_rev"].fillna(0) == 0)
        & (df["loss_qty_total"].fillna(0) == 0)
    )].reset_index(drop=True)

    hc = _build_hub_city_map()
    return df.merge(hc, on="hub_name", how="left")


def get_insights_bootstrap() -> dict[str, Any]:
    try:
        df = load_6w_insights()
    except FileNotFoundError as exc:
        return {"empty": True, "message": str(exc)}

    meta = list_available_weeks()
    cities = sorted(df["city_name"].dropna().unique().tolist())
    return sanitize_for_json(
        {
            "empty": False,
            "weeks": meta.get("weeks", []),
            "default_week": meta.get("default_week"),
            "cities": cities,
            "insight_views": [
                {"id": "executive", "label": "Executive Summary"},
                {"id": "revenue_loss", "label": "Revenue Loss"},
                {"id": "attainment", "label": "Attainment (OA / UA)"},
                {"id": "wastage", "label": "Wastage"},
                {"id": "hub_health", "label": "Hub Health 360"},
            ],
            "loss_sub_views": [
                {"id": "loss_theatre", "label": "Loss Theatre"},
                {"id": "city_category", "label": "City × Category"},
                {"id": "hub_rca", "label": "Hub × Category RCA"},
                {"id": "avoidable_pareto", "label": "Avoidable vs Unavoidable"},
                {"id": "category_severity", "label": "Category Severity"},
            ],
            "attainment_sub_views": [
                {"id": "leaderboard", "label": "Leaderboard"},
                {"id": "consistency", "label": "Consistency Heatmap"},
                {"id": "quadrant", "label": "Attainment Quadrant"},
                {"id": "category", "label": "Category Deep-Dive"},
                {"id": "trend", "label": "Trend by Segment"},
            ],
            "wastage_sub_views": [
                {"id": "volume_matrix", "label": "Volume × Category"},
                {"id": "hotspots", "label": "Hotspots"},
                {"id": "trend", "label": "Wastage Trend"},
                {"id": "quality_expiry", "label": "Quality vs Expiry"},
            ],
        }
    )


def _prepare_context(week: str, cities: list[str] | None) -> dict[str, Any]:
    df_raw = load_6w_insights()
    week_meta = (
        df_raw[["iso_year", "iso_week", "week_label"]]
        .drop_duplicates()
        .sort_values(["iso_year", "iso_week"])
    )
    week_options = week_meta["week_label"].tolist()
    if week not in week_options:
        week = week_options[-1] if week_options else week

    week_df = df_raw[df_raw["week_label"] == week].copy()
    active_hubs = week_df.groupby("hub_name")["r7_plan"].sum().loc[lambda s: s > 0].index
    active_skus = week_df.groupby("product_id")["r7_plan"].sum().loc[lambda s: s > 0].index
    df6 = week_df[week_df["hub_name"].isin(active_hubs) & week_df["product_id"].isin(active_skus)].copy()
    if cities:
        df6 = df6[df6["city_name"].isin(cities)]

    df_loss = pd.DataFrame()
    loss_note = ""
    if not week_df.empty:
        df_loss_full = load_loss_sheet()
        if not df_loss_full.empty:
            if "week_label" in df_loss_full.columns:
                wl = df_loss_full[df_loss_full["week_label"] == week].copy()
                if not wl.empty:
                    df_loss = wl
                    loss_note = f"Loss data: ISO week {week} · {len(df_loss):,} rows"
            if df_loss.empty:
                wk_lo = pd.Timestamp(week_df["process_dt"].min()).normalize()
                wk_hi = pd.Timestamp(week_df["process_dt"].max()).normalize()
                dnorm = df_loss_full["process_dt"].dt.normalize()
                scoped = df_loss_full[(dnorm >= wk_lo) & (dnorm <= wk_hi)].copy()
                if not scoped.empty:
                    df_loss = scoped
                    loss_note = f"Loss data: {wk_lo.date()} → {wk_hi.date()} ({len(df_loss):,} rows)"
            if cities and not df_loss.empty and "city_name" in df_loss.columns:
                df_loss = df_loss[df_loss["city_name"].isin(cities)]

    wk_start = df6["process_dt"].min().strftime("%d %b") if not df6.empty else "—"
    wk_end = df6["process_dt"].max().strftime("%d %b %Y") if not df6.empty else "—"

    return {
        "week": week,
        "week_range": {"start": wk_start, "end": wk_end},
        "active_hubs": int(df6["hub_name"].nunique()) if not df6.empty else 0,
        "active_skus": int(df6["product_id"].nunique()) if not df6.empty else 0,
        "loss_note": loss_note,
        "df6": df6,
        "df_loss": df_loss,
        "week_df": week_df,
    }


def _dt_str(v) -> str:
    if pd.isna(v):
        return ""
    if isinstance(v, (pd.Timestamp, date)):
        return pd.Timestamp(v).strftime("%Y-%m-%d")
    return str(v)


def build_insights_view(
    *,
    insight_view: str,
    week: str,
    cities: list[str] | None = None,
    sub_view: str | None = None,
    oa_thr: int = 120,
    ua_thr: int = 80,
    min_plan: int = 500,
    top_n: int = 20,
    granularity: str = "Daily",
    loss_categories: list[str] | None = None,
    pareto_dim: str = "Hub",
    category_focus: str | None = None,
    min_wastage: int = 500,
) -> dict[str, Any]:
    try:
        ctx = _prepare_context(week, cities)
    except FileNotFoundError as exc:
        return {"empty": True, "message": describe_missing_6w_sources() if "6-week" in str(exc) else str(exc)}

    df6 = ctx["df6"]
    df_loss = ctx["df_loss"]
    base = {
        "empty": df6.empty,
        "week": ctx["week"],
        "week_range": ctx["week_range"],
        "active_hubs": ctx["active_hubs"],
        "active_skus": ctx["active_skus"],
        "loss_note": ctx["loss_note"],
        "insight_view": insight_view,
        "sub_view": sub_view,
    }
    if df6.empty and insight_view not in ("revenue_loss",):
        return {**base, "message": "No 6w data after filters."}

    builders = {
        "executive": lambda: _view_executive(df6, df_loss),
        "revenue_loss": lambda: _view_revenue_loss(df_loss, sub_view or "loss_theatre", granularity, loss_categories, top_n, pareto_dim, category_focus),
        "attainment": lambda: _view_attainment(df6, sub_view or "leaderboard", oa_thr, ua_thr, min_plan, top_n),
        "wastage": lambda: _view_wastage(df6, sub_view or "volume_matrix", top_n, min_wastage),
        "hub_health": lambda: _view_hub_health(df6, df_loss, min_plan),
    }
    fn = builders.get(insight_view)
    if not fn:
        return {**base, "message": f"Unknown insight view: {insight_view}"}
    payload = fn()
    return sanitize_for_json({**base, **payload})


def _view_executive(df6: pd.DataFrame, df_loss: pd.DataFrame) -> dict[str, Any]:
    tot_plan_qty = float(df6["r7_plan"].sum())
    tot_plan_rev = float(df6["r7_plan_rev"].sum())
    tot_actual_rev = float(df6["revenue"].sum())
    tot_sales = float(df6["sales"].sum())
    attainment = tot_sales / tot_plan_qty * 100 if tot_plan_qty else None
    avail = float(df6["flag"].sum() / df6["instances"].sum() * 100) if df6["instances"].sum() else None
    tot_wastage = float(df6["total_wastage_val"].sum())
    wastage_pct = tot_wastage / tot_actual_rev * 100 if tot_actual_rev else None

    if not df_loss.empty:
        tot_demand = float(df_loss["demand_loss_rev"].sum())
        tot_supply = float(df_loss["supply_loss_rev"].sum())
        tot_rev_loss = float(df_loss["total_loss_rev"].sum())
    else:
        tot_demand = tot_supply = tot_rev_loss = None

    daily6 = (
        df6.groupby("process_dt", as_index=False)
        .agg(plan_rev=("r7_plan_rev", "sum"), actual_rev=("revenue", "sum"), wastage=("total_wastage_val", "sum"))
        .sort_values("process_dt")
    )
    daily_plan_actual = [
        {"date": _dt_str(r.process_dt), "plan_rev": float(r.plan_rev), "actual_rev": float(r.actual_rev)}
        for r in daily6.itertuples()
    ]
    daily_wastage = [{"date": _dt_str(r.process_dt), "wastage": float(r.wastage)} for r in daily6.itertuples()]

    daily_loss = []
    if not df_loss.empty:
        dl = (
            df_loss.groupby("process_dt", as_index=False)
            .agg(demand=("demand_loss_rev", "sum"), supply=("supply_loss_rev", "sum"), total=("total_loss_rev", "sum"))
            .sort_values("process_dt")
        )
        daily_loss = [
            {"date": _dt_str(r.process_dt), "demand": float(r.demand), "supply": float(r.supply), "total": float(r.total)}
            for r in dl.itertuples()
        ]

    city_stats = (
        df6.groupby("city_name", as_index=False)
        .agg(plan_rev=("r7_plan_rev", "sum"), actual=("revenue", "sum"), plan_qty=("r7_plan", "sum"), sales_qty=("sales", "sum"))
    )
    city_stats["attainment"] = np.where(city_stats["plan_qty"] > 0, city_stats["sales_qty"] / city_stats["plan_qty"] * 100, np.nan)
    city_top = city_stats.sort_values("plan_rev", ascending=False).head(10)

    return {
        "kpis": {
            "plan_revenue": tot_plan_rev,
            "actual_revenue": tot_actual_rev,
            "plan_qty": tot_plan_qty,
            "sales_qty": tot_sales,
            "attainment_pct": attainment,
            "availability_pct": avail,
            "total_rev_loss": tot_rev_loss,
            "demand_loss": tot_demand,
            "supply_loss": tot_supply,
            "total_wastage": tot_wastage,
            "wastage_pct_of_rev": wastage_pct,
        },
        "daily_plan_actual": daily_plan_actual,
        "daily_loss": daily_loss,
        "daily_wastage": daily_wastage,
        "city_leaderboard": df_to_records(city_top),
    }


def _filter_loss(df_loss: pd.DataFrame, categories: list[str] | None) -> pd.DataFrame:
    flt = df_loss.copy()
    if categories:
        flt = flt[flt["category"].isin(categories)]
    return flt


def _view_revenue_loss(
    df_loss: pd.DataFrame,
    sub_view: str,
    granularity: str,
    categories: list[str] | None,
    top_n: int,
    pareto_dim: str,
    category_focus: str | None,
) -> dict[str, Any]:
    if df_loss.empty:
        return {"empty": True, "message": "No availability-led revenue loss data for this week."}

    flt = _filter_loss(df_loss, categories)
    if flt.empty:
        return {"empty": True, "message": "No loss data after filters."}

    if sub_view == "loss_theatre":
        key_col = "week_label" if granularity == "Weekly" else "process_dt"
        agg = (
            flt.groupby(key_col, as_index=False)
            .agg(demand=("demand_loss_rev", "sum"), supply=("supply_loss_rev", "sum"), total=("total_loss_rev", "sum"))
            .sort_values(key_col)
        )
        agg["supply_share"] = np.where(agg["total"] > 0, agg["supply"] / agg["total"] * 100, np.nan)
        rows = []
        for r in agg.itertuples():
            label = r.week_label if key_col == "week_label" else _dt_str(r.process_dt)
            rows.append({
                "label": label,
                "demand": float(r.demand),
                "supply": float(r.supply),
                "total": float(r.total),
                "supply_share_pct": float(r.supply_share) if pd.notna(r.supply_share) else None,
            })
        return {"loss_theatre": rows, "granularity": granularity, "total_loss": float(agg["total"].sum())}

    if sub_view == "city_category":
        if "city_name" not in flt.columns or flt["city_name"].isna().all():
            return {"empty": True, "message": "City dimension unavailable on loss sheet."}
        tree = (
            flt.groupby(["city_name", "category"], as_index=False)
            .agg(total=("total_loss_rev", "sum"), demand=("demand_loss_rev", "sum"), supply=("supply_loss_rev", "sum"))
            .query("total > 0")
            .sort_values("total", ascending=False)
        )
        city_tot = (
            flt.groupby("city_name", as_index=False)
            .agg(total=("total_loss_rev", "sum"))
            .sort_values("total", ascending=False)
        )
        return {
            "city_category_rows": df_to_records(tree.head(200)),
            "city_waterfall": df_to_records(city_tot.head(15)),
            "grand_total": float(city_tot["total"].sum()),
        }

    if sub_view == "hub_rca":
        top_hubs = (
            flt.groupby("hub_name")["total_loss_rev"].sum()
            .sort_values(ascending=False).head(top_n).index.tolist()
        )
        view = flt[flt["hub_name"].isin(top_hubs)]
        mat = (
            view.groupby(["hub_name", "category"], as_index=False)
            .agg(total=("total_loss_rev", "sum"), demand=("demand_loss_rev", "sum"), supply=("supply_loss_rev", "sum"))
        )
        mat["demand_share"] = np.where(mat["total"] > 0, mat["demand"] / mat["total"] * 100, np.nan)
        piv_total = mat.pivot(index="hub_name", columns="category", values="total").reindex(index=top_hubs).fillna(0)
        piv_share = mat.pivot(index="hub_name", columns="category", values="demand_share").reindex(index=top_hubs)
        action = mat.sort_values("total", ascending=False).head(30)
        return {
            "severity_heatmap": {
                "rows": piv_total.index.tolist(),
                "columns": piv_total.columns.tolist(),
                "values": piv_total.values.tolist(),
            },
            "demand_share_heatmap": {
                "rows": piv_share.index.tolist(),
                "columns": piv_share.columns.tolist(),
                "values": [[None if pd.isna(v) else float(v) for v in row] for row in piv_share.values],
            },
            "action_table": df_to_records(action),
        }

    if sub_view == "avoidable_pareto":
        col = "hub_name" if pareto_dim == "Hub" else "category"
        agg = (
            flt.groupby(col, as_index=False)
            .agg(avoid=("loss_qty_avoidable", "sum"), unavoid=("loss_qty_unavoidable", "sum"))
        )
        agg["total"] = agg["avoid"] + agg["unavoid"]
        agg = agg[agg["total"] > 0].sort_values("avoid", ascending=False).head(top_n)
        agg["cum_pct"] = agg["avoid"].cumsum() / agg["avoid"].sum() * 100 if agg["avoid"].sum() else 0
        tot_av = float(flt["loss_qty_avoidable"].sum())
        tot_un = float(flt["loss_qty_unavoidable"].sum())
        share = tot_av / (tot_av + tot_un) * 100 if (tot_av + tot_un) else None
        return {
            "pareto_rows": df_to_records(agg),
            "kpis": {"avoidable_qty": tot_av, "unavoidable_qty": tot_un, "avoidable_share_pct": share},
            "pareto_dim": pareto_dim,
        }

    if sub_view == "category_severity":
        cats = sorted(flt["category"].dropna().unique().tolist())
        focus = category_focus or (cats[0] if cats else None)
        if not focus:
            return {"empty": True, "message": "No categories in loss data."}
        cat_df = flt[flt["category"] == focus]
        daily = (
            cat_df.groupby("process_dt", as_index=False)
            .agg(demand=("demand_loss_rev", "sum"), supply=("supply_loss_rev", "sum"), total=("total_loss_rev", "sum"), deliv=("delivered_plan_qty", "sum"))
            .sort_values("process_dt")
        )
        hubs = (
            cat_df.groupby("hub_name", as_index=False)
            .agg(total=("total_loss_rev", "sum"), demand=("demand_loss_rev", "sum"), supply=("supply_loss_rev", "sum"))
            .sort_values("total", ascending=False).head(15)
        )
        return {
            "categories": cats,
            "category_focus": focus,
            "daily_loss": df_to_records(daily),
            "top_hubs": df_to_records(hubs),
        }

    return {"empty": True, "message": f"Unknown loss sub-view: {sub_view}"}


def _view_attainment(
    df6: pd.DataFrame,
    sub_view: str,
    oa_thr: int,
    ua_thr: int,
    min_plan: int,
    top_n: int,
) -> dict[str, Any]:
    if sub_view == "leaderboard":
        hub_agg = (
            df6.groupby(["hub_name", "city_name"], as_index=False)
            .agg(plan=("r7_plan", "sum"), actual=("sales", "sum"), rev=("revenue", "sum"), plan_rev=("r7_plan_rev", "sum"))
        )
        hub_agg["attainment"] = np.where(hub_agg["plan"] > 0, hub_agg["actual"] / hub_agg["plan"] * 100, np.nan)
        hub_agg["delta_rev"] = hub_agg["rev"] - hub_agg["plan_rev"]
        qual = hub_agg[hub_agg["plan"] >= min_plan].dropna(subset=["attainment"])
        oa = qual[qual["attainment"] >= oa_thr].sort_values("attainment", ascending=False).head(top_n)
        ua = qual[qual["attainment"] <= ua_thr].sort_values("attainment", ascending=True).head(top_n)
        city_agg = (
            df6.groupby("city_name", as_index=False)
            .agg(plan=("r7_plan", "sum"), actual=("sales", "sum"), rev=("revenue", "sum"), plan_rev=("r7_plan_rev", "sum"), hubs=("hub_name", "nunique"))
        )
        city_agg["attainment"] = np.where(city_agg["plan"] > 0, city_agg["actual"] / city_agg["plan"] * 100, np.nan)
        city_agg = city_agg.dropna().sort_values("attainment", ascending=True)
        return {
            "oa_threshold": oa_thr,
            "ua_threshold": ua_thr,
            "kpis": {
                "over_attaining": len(oa),
                "under_attaining": len(ua),
                "on_plan": len(qual) - len(oa) - len(ua),
            },
            "oa_hubs": df_to_records(oa),
            "ua_hubs": df_to_records(ua),
            "city_roll_up": df_to_records(city_agg),
        }

    if sub_view == "consistency":
        hub_daily = (
            df6.groupby(["hub_name", "process_dt"], as_index=False)
            .agg(plan=("r7_plan", "sum"), act=("sales", "sum"))
        )
        hub_daily["attainment"] = np.where(hub_daily["plan"] > 0, hub_daily["act"] / hub_daily["plan"] * 100, np.nan)
        med = hub_daily.dropna().groupby("hub_name")["attainment"].median().sort_values()
        n = min(top_n, len(med))
        selected = pd.concat([med.head(n // 2), med.tail(n - n // 2)]).index.tolist()
        pivot = (
            hub_daily[hub_daily["hub_name"].isin(selected)]
            .pivot(index="hub_name", columns="process_dt", values="attainment")
            .reindex(index=selected)
        )
        pivot = pivot.reindex(columns=sorted(pivot.columns))
        col_labels = [_dt_str(c) for c in pivot.columns]
        return {
            "heatmap": {
                "rows": pivot.index.tolist(),
                "columns": col_labels,
                "values": [[None if pd.isna(v) else float(v) for v in row] for row in pivot.values],
            },
            "oa_threshold": oa_thr,
            "ua_threshold": ua_thr,
        }

    if sub_view == "quadrant":
        hub = (
            df6.groupby(["hub_name", "city_name"], as_index=False)
            .agg(plan=("r7_plan", "sum"), actual=("sales", "sum"), rev=("revenue", "sum"), plan_rev=("r7_plan_rev", "sum"))
        )
        hub = hub[hub["plan"] >= min_plan]
        hub["attainment"] = np.where(hub["plan"] > 0, hub["actual"] / hub["plan"] * 100, np.nan)
        hub["rev_gap"] = hub["rev"] - hub["plan_rev"]
        hub = hub.dropna(subset=["attainment"])
        return {"scatter": df_to_records(hub), "oa_threshold": oa_thr, "ua_threshold": ua_thr}

    if sub_view == "category":
        cat = (
            df6.groupby("sub_category", as_index=False)
            .agg(plan=("r7_plan", "sum"), actual=("sales", "sum"), rev=("revenue", "sum"), plan_rev=("r7_plan_rev", "sum"))
        )
        cat["attainment"] = np.where(cat["plan"] > 0, cat["actual"] / cat["plan"] * 100, np.nan)
        cat = cat.sort_values("attainment")
        return {"category_rows": df_to_records(cat), "oa_threshold": oa_thr, "ua_threshold": ua_thr}

    if sub_view == "trend":
        hub_daily = (
            df6.groupby(["process_dt", "hub_name"], as_index=False)
            .agg(plan=("r7_plan", "sum"), act=("sales", "sum"))
        )
        hub_daily["attainment"] = np.where(hub_daily["plan"] > 0, hub_daily["act"] / hub_daily["plan"] * 100, np.nan)
        hub_daily["band"] = np.select(
            [hub_daily["attainment"] <= ua_thr, hub_daily["attainment"] >= oa_thr],
            ["Under (UA)", "Over (OA)"],
            default="On-plan",
        )
        share = (
            hub_daily.groupby(["process_dt", "band"], as_index=False)
            .size()
            .rename(columns={"size": "count"})
        )
        totals = share.groupby("process_dt")["count"].transform("sum")
        share["pct"] = share["count"] / totals * 100
        return {
            "band_trend": [
                {"date": _dt_str(r.process_dt), "band": r.band, "pct": float(r.pct)}
                for r in share.itertuples()
            ],
            "oa_threshold": oa_thr,
            "ua_threshold": ua_thr,
        }

    return {"empty": True, "message": f"Unknown attainment sub-view: {sub_view}"}


def _view_wastage(df6: pd.DataFrame, sub_view: str, top_n: int, min_wastage: int) -> dict[str, Any]:
    if sub_view == "volume_matrix":
        hp = (
            df6.groupby(["hub_name", "product_id", "sub_category"], as_index=False)
            .agg(plan=("r7_plan", "sum"), wastage_val=("total_wastage_val", "sum"), wastage_qty=("total_wastage_qty", "sum"), rev=("revenue", "sum"))
        )
        hp = hp[hp["plan"] > 0]
        if hp.empty:
            return {"empty": True, "message": "No plan>0 rows."}
        try:
            hp["vol_bucket"] = pd.qcut(
                hp["plan"], q=4,
                labels=["Q1 Low", "Q2 Mid-Low", "Q3 Mid-High", "Q4 Very High"],
                duplicates="drop",
            ).astype(str)
        except ValueError:
            hp["vol_bucket"] = "All"
        mat = (
            hp.groupby(["vol_bucket", "sub_category"], as_index=False)
            .agg(wastage=("wastage_val", "sum"), plan=("plan", "sum"), rev=("rev", "sum"))
        )
        mat["wastage_pct"] = np.where(mat["rev"] > 0, mat["wastage"] / mat["rev"] * 100, np.nan)
        piv_val = mat.pivot(index="vol_bucket", columns="sub_category", values="wastage").fillna(0)
        piv_pct = mat.pivot(index="vol_bucket", columns="sub_category", values="wastage_pct")
        b_tot = (
            hp.groupby("vol_bucket", as_index=False)
            .agg(plan=("plan", "sum"), wastage=("wastage_val", "sum"), wastage_qty=("wastage_qty", "sum"), rev=("rev", "sum"))
            .sort_values("vol_bucket")
        )
        b_tot["wastage_pct_of_rev"] = np.where(b_tot["rev"] > 0, b_tot["wastage"] / b_tot["rev"] * 100, np.nan)
        return {
            "absolute_heatmap": {
                "rows": piv_val.index.astype(str).tolist(),
                "columns": piv_val.columns.tolist(),
                "values": piv_val.values.tolist(),
            },
            "pct_heatmap": {
                "rows": piv_pct.index.astype(str).tolist(),
                "columns": piv_pct.columns.tolist(),
                "values": [[None if pd.isna(v) else float(v) for v in row] for row in piv_pct.values],
            },
            "bucket_totals": df_to_records(b_tot),
        }

    if sub_view == "hotspots":
        hub_waste = (
            df6.groupby("hub_name")["total_wastage_val"].sum()
            .sort_values(ascending=False).head(top_n).index.tolist()
        )
        view = df6[df6["hub_name"].isin(hub_waste)]
        mat = (
            view.groupby(["hub_name", "sub_category"], as_index=False)
            .agg(wastage=("total_wastage_val", "sum"), rev=("revenue", "sum"), qty=("total_wastage_qty", "sum"))
        )
        mat = mat[mat["wastage"] >= min_wastage]
        mat["wastage_pct"] = np.where(mat["rev"] > 0, mat["wastage"] / mat["rev"] * 100, np.nan)
        piv = mat.pivot(index="hub_name", columns="sub_category", values="wastage").reindex(index=hub_waste).fillna(0)
        action = mat.sort_values("wastage", ascending=False).head(40)
        return {
            "heatmap": {
                "rows": piv.index.tolist(),
                "columns": piv.columns.tolist(),
                "values": piv.values.tolist(),
            },
            "action_table": df_to_records(action),
        }

    if sub_view == "trend":
        daily = (
            df6.groupby("process_dt", as_index=False)
            .agg(wastage=("total_wastage_val", "sum"), rev=("revenue", "sum"), qty=("total_wastage_qty", "sum"))
            .sort_values("process_dt")
        )
        daily["wastage_pct"] = np.where(daily["rev"] > 0, daily["wastage"] / daily["rev"] * 100, np.nan)
        wk_cat = (
            df6.groupby(["week_label", "sub_category"], as_index=False)
            .agg(wastage=("total_wastage_val", "sum"))
        )
        return {
            "daily_trend": df_to_records(daily),
            "weekly_by_category": df_to_records(wk_cat),
        }

    if sub_view == "quality_expiry":
        cat = (
            df6.groupby("sub_category", as_index=False)
            .agg(quality=("wastage_val_Quality", "sum"), expiry=("wastage_val_Expiry", "sum"), rev=("revenue", "sum"))
        )
        cat["total"] = cat["quality"] + cat["expiry"]
        cat = cat[cat["total"] > 0].sort_values("total")
        cat["quality_share_pct"] = cat["quality"] / cat["total"] * 100
        return {"category_split": df_to_records(cat)}

    return {"empty": True, "message": f"Unknown wastage sub-view: {sub_view}"}


def _view_hub_health(df6: pd.DataFrame, df_loss: pd.DataFrame, min_plan: int) -> dict[str, Any]:
    hub = (
        df6.groupby(["hub_name", "city_name"], as_index=False)
        .agg(plan=("r7_plan", "sum"), actual=("sales", "sum"), rev=("revenue", "sum"), plan_rev=("r7_plan_rev", "sum"), wastage=("total_wastage_val", "sum"))
    )
    hub["attainment"] = np.where(hub["plan"] > 0, hub["actual"] / hub["plan"] * 100, np.nan)
    hub["wastage_pct"] = np.where(hub["rev"] > 0, hub["wastage"] / hub["rev"] * 100, np.nan)
    if not df_loss.empty:
        loss = df_loss.groupby("hub_name", as_index=False)["total_loss_rev"].sum()
        hub = hub.merge(loss, on="hub_name", how="left")
    else:
        hub["total_loss_rev"] = 0.0
    hub["total_loss_rev"] = hub["total_loss_rev"].fillna(0)
    hub["loss_pct"] = np.where(
        (hub["rev"] + hub["total_loss_rev"]) > 0,
        hub["total_loss_rev"] / (hub["rev"] + hub["total_loss_rev"]) * 100,
        np.nan,
    )
    hub = hub[hub["plan"] >= min_plan].dropna(subset=["attainment", "wastage_pct"])
    hub = hub.sort_values("plan_rev", ascending=False)
    return {"hubs": df_to_records(hub), "min_plan": min_plan}
