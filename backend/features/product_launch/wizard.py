"""Headless New Product Launch wizard — Streamlit page_type1/2/3 parity."""
from __future__ import annotations

import io
import os
from datetime import date, datetime
from typing import Any

import pandas as pd

from core.utils.dataframe import df_to_records, sanitize_for_json

from features.product_launch.core import (
    WEEKDAYS,
    _submit_hub_df,
    build_city_template,
    build_hub_template,
    check_duplicates_city,
    check_duplicates_hub,
    get_categories,
    get_cities_from_salience,
    get_earliest_monday,
    get_hubs_for_city,
    get_product_id,
    get_product_info,
    get_products_by_category,
    load_hub_salience,
    load_log,
    load_product_master,
    parse_city_upload,
    parse_hub_upload,
    split_city_to_hubs,
    update_submission_status,
)


def wizard_context_payload() -> dict[str, Any]:
    """Single sheet pass for categories + cities (avoids duplicate master/salience loads)."""
    master = load_product_master()
    sal = load_hub_salience()
    return sanitize_for_json(
        {
            "categories": get_categories(master),
            "cities": get_cities_from_salience(sal),
            "earliest_launch_date": str(get_earliest_monday()),
        }
    )


def list_categories() -> list[str]:
    return get_categories(load_product_master())


def list_cities() -> list[str]:
    sal = load_hub_salience()
    return get_cities_from_salience(sal)


def list_hubs_for_city(city: str, category: str | None = None) -> list[str]:
    sal = load_hub_salience()
    return get_hubs_for_city(sal, city, category)


def city_template_bytes(
    cities: list[str],
    category: str,
    *,
    product_id: str = "",
    product_name: str = "",
    mrp: str = "",
    sub_type: str = "New Launch",
    old_product_id: str = "",
    old_product_name: str = "",
    replacement_percentage: str = "",
) -> bytes:
    return build_city_template(
        cities, category, product_id, product_name, mrp,
        sub_type=sub_type,
        old_product_id=old_product_id,
        old_product_name=old_product_name,
        replacement_percentage=replacement_percentage,
    )


def hub_template_bytes(
    cities_hubs: dict[str, list[str]],
    category: str,
    *,
    product_id: str = "",
    product_name: str = "",
    mrp: str = "",
    sub_type: str = "New Launch",
    old_product_id: str = "",
    old_product_name: str = "",
    replacement_percentage: str = "",
) -> bytes:
    return build_hub_template(
        cities_hubs, category, product_id, product_name, mrp,
        sub_type=sub_type,
        old_product_id=old_product_id,
        old_product_name=old_product_name,
        replacement_percentage=replacement_percentage,
    )


def parse_city_file(content: bytes) -> dict[str, Any]:
    df, errors = parse_city_upload(io.BytesIO(content))
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "rows": df_to_records(df), "columns": df.columns.tolist(), "row_count": len(df)}


def parse_hub_file(content: bytes) -> dict[str, Any]:
    df, errors = parse_hub_upload(io.BytesIO(content))
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "rows": df_to_records(df), "columns": df.columns.tolist(), "row_count": len(df)}


def split_city_rows(
    city_rows: list[dict],
    *,
    forced_hubs: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    sal = load_hub_salience()
    city_df = pd.DataFrame(city_rows)
    hub_df, zero_sal = split_city_to_hubs(city_df, sal, forced_hubs=forced_hubs)
    return sanitize_for_json(
        {
            "hub_rows": df_to_records(hub_df),
            "columns": hub_df.columns.tolist(),
            "zero_salience": zero_sal,
            "row_count": len(hub_df),
        }
    )


def check_duplicates(
    hub_rows: list[dict],
    *,
    sub_type: str,
    plan_level: str = "hub",
) -> dict[str, Any]:
    log_df = load_log()
    hub_df = pd.DataFrame(hub_rows)
    if plan_level == "city":
        cities = hub_df["city_name"].astype(str).unique().tolist() if "city_name" in hub_df.columns else []
        pid = str(hub_df["product_id"].iloc[0]) if "product_id" in hub_df.columns and len(hub_df) else ""
        dupes = check_duplicates_city(log_df, sub_type, pid, cities)
    else:
        dupes = check_duplicates_hub(log_df, sub_type, hub_df)
    if dupes is None or dupes.empty:
        return {"has_duplicates": False}
    return {"has_duplicates": True, "existing_rows": df_to_records(dupes)}


def apply_launch_dates(hub_rows: list[dict], launch_date: str | None = None) -> list[dict]:
    """Attach Launch Date column — single date or per-row 'launch_date' key."""
    min_date = get_earliest_monday()
    out = []
    for row in hub_rows:
        r = dict(row)
        ld = r.pop("launch_date", None) or launch_date or str(min_date)
        r["Launch Date"] = ld
        out.append(r)
    return out


def _product_name_from_hub_df(hub_df: pd.DataFrame) -> str:
    for col in ("product_name", "Product Name", "Anchor Name"):
        if col in hub_df.columns and len(hub_df):
            val = hub_df[col].iloc[0]
            if pd.notna(val) and str(val).strip():
                return str(val).strip()
    return "Product"


def submit_hub_rows(
    hub_rows: list[dict],
    *,
    sub_type: str,
    username: str,
    user_id: int | None = None,
    send_email: bool = True,
    status: str = "Pending",
    rejection_reason: str = "",
) -> dict[str, Any]:
    hub_df = pd.DataFrame(hub_rows)
    if "Launch Date" not in hub_df.columns:
        hub_df = pd.DataFrame(apply_launch_dates(hub_rows))
    sub_id = _submit_hub_df(
        hub_df,
        sub_type,
        username=username,
        status=status,
        rejection_reason=rejection_reason,
    )

    payload: dict[str, Any] = {
        "submission_id": sub_id,
        "rows": len(hub_df),
        "product_name": _product_name_from_hub_df(hub_df),
    }
    if send_email:
        dates: list[str] = []
        if "Launch Date" in hub_df.columns:
            dates = sorted(hub_df["Launch Date"].dropna().astype(str).unique().tolist())
        from core.shared.workflow_notifications import notify_launch_submission


        payload["email"] = notify_launch_submission(
            sub_id=sub_id,
            sub_type=sub_type,
            product_name=payload["product_name"],
            launch_dates=dates,
            user_id=user_id,
        )
    return payload


def preview_hub_rows(
    hub_rows: list[dict],
    *,
    sub_type: str,
    username: str,
    launch_date: str | None = None,
) -> list[dict]:
    """Preview the exact columns and rows that would be appended to Submission_Log."""
    import uuid
    from datetime import datetime
    from features.product_launch.core import WEEKDAYS, gen_sub_id, _sanitize


    hub_df = pd.DataFrame(hub_rows)
    if "Launch Date" not in hub_df.columns:
        hub_df = pd.DataFrame(apply_launch_dates(hub_rows, launch_date))
    
    df = hub_df.copy()

    # Rename to sheet canonical column names
    df = df.rename(columns={
        "city_name":    "City",
        "hub_name":     "Hub",
        "product_id":   "Product ID",
        "product_name": "Product Name",
        "category":     "Category",
        "Launch Date":  "Start Date",
    })

    # Convert Start Date to string
    if "Start Date" in df.columns:
        df["Start Date"] = df["Start Date"].apply(
            lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)
        )
    else:
        df["Start Date"] = ""

    for day in WEEKDAYS:
        if day not in df.columns:
            df[day] = 0
    df[WEEKDAYS] = df[WEEKDAYS].fillna(0).astype(int)

    from features.product_launch.core import _parse_percent_to_decimal, _optional_str
    pct_cols = ["Yield", "Replacement Percentage", "replacement_percentage"]
    for col in pct_cols:
        if col in df.columns:
            df[col] = df[col].apply(_parse_percent_to_decimal)
    for col in ["Meat Ratio", "Meat Ratio (for VA)", "UOM", "RM", "Total Shelf Life", "Hub Shelf Life", "PLU Code", "PLU_CODE"]:
        if col in df.columns:
            df[col] = df[col].apply(_optional_str)

    submitted_by = username or ""
    sub_id = gen_sub_id(sub_type)
    df["Timestamp"]        = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df["Submission_ID"]    = sub_id
    df["Submission_Type"]  = sub_type
    df["Status"]           = "Pending"
    df["Rejection_Reason"] = ""
    df["Submitted_By"]     = submitted_by

    log_cols = ["Timestamp", "Submission_ID", "Submission_Type",
                "Product ID", "Product Name", "Category",
                "City", "Hub", "MRP", "Start Date",
                "Status", "Rejection_Reason", "Submitted_By",
                "Old Product ID", "Old Product Name", "Replacement Percentage"] + WEEKDAYS + [
                "PLU Code", "PLU_CODE", "UOM", "Yield", "RM", "Meat Ratio", "Meat Ratio (for VA)", "Total Shelf Life", "Hub Shelf Life"]
    
    log_df = df[[c for c in log_cols if c in df.columns]]
    return df_to_records(_sanitize(log_df))



def list_all_product_ids() -> list[dict[str, str]]:
    """All P-L Master rows from FF Automation for Expansion product picker."""
    master = load_product_master()
    pid_col = next((c for c in ["Product id", "Product ID", "product_id"] if c in master.columns), None)
    name_col = next(
        (c for c in ["Product Name", "product_name", "Anchor Name"] if c in master.columns),
        None,
    )
    cat_col = next((c for c in ["sub_category", "Sub-category", "Sub category", "category"] if c in master.columns), None)
    if not pid_col:
        return []
    out: list[dict[str, str]] = []
    for _, row in master.iterrows():
        pid = str(row.get(pid_col, "")).strip()
        if not pid:
            continue
        out.append(
            {
                "product_id": pid,
                "product_name": str(row.get(name_col, "")).strip() if name_col else "",
                "category": str(row.get(cat_col, "")).strip() if cat_col else "",
            }
        )
    return sorted(out, key=lambda r: r["product_id"])


def get_submission_log(
    *,
    types: list[str] | None = None,
    statuses: list[str] | None = None,
    product_ids: list[str] | None = None,
    submission_id: str | None = None,
    view: str = "summary",
) -> dict[str, Any]:
    df = load_log()
    if df.empty:
        return {"rows": [], "columns": [], "filters": {}, "view": view, "row_count": 0}

    work = df.copy()
    if types and "Submission_Type" in work.columns:
        work = work[work["Submission_Type"].isin(types)]
    if statuses and "Status" in work.columns:
        work = work[work["Status"].isin(statuses)]
    if product_ids and "Product ID" in work.columns:
        work = work[work["Product ID"].isin(product_ids)]
    if submission_id and "Submission_ID" in work.columns:
        work = work[work["Submission_ID"].astype(str) == str(submission_id)]

    # SLA flags (Streamlit parity)
    now = datetime.now()
    if "Timestamp" in work.columns and "Start Date" in work.columns:
        work["SLA"] = ""
        for idx, row in work[work.get("Status", pd.Series(dtype=str)) == "Pending"].iterrows():
            try:
                ts = pd.to_datetime(row["Timestamp"])
                launch = pd.to_datetime(row["Start Date"]).date()
                if launch < now.date():
                    work.at[idx, "Status"] = "Expired"
                    work.at[idx, "SLA"] = "EXPIRED"
                elif (now - ts).total_seconds() / 3600 > 48:
                    work.at[idx, "SLA"] = "OVERDUE"
            except Exception:
                pass

    def _uniq_nonempty(col: str) -> list[str]:
        if col not in df.columns:
            return []
        return sorted({str(v).strip() for v in df[col].dropna().tolist() if str(v).strip()})

    filters = {
        "types": _uniq_nonempty("Submission_Type"),
        "statuses": _uniq_nonempty("Status"),
        "product_ids": _uniq_nonempty("Product ID"),
    }

    if view == "summary" and not submission_id and "Submission_ID" in work.columns:
        summary_cols = [
            "Submission_ID",
            "Submission_Type",
            "Product Name",
            "Start Date",
            "Status",
            "SLA",
            "Hub_Count",
            "City_Count",
            "Cities",
            "Submitted_By",
            "Timestamp",
        ]
        rows: list[dict[str, Any]] = []
        for sid, grp in work.groupby("Submission_ID", sort=False):
            first = grp.iloc[0]
            sla_vals = [str(v) for v in grp["SLA"].tolist()] if "SLA" in grp.columns else []
            sla = "EXPIRED" if "EXPIRED" in sla_vals else ("OVERDUE" if "OVERDUE" in sla_vals else "")
            cities = sorted({str(c).strip() for c in grp["City"].dropna() if str(c).strip()}) if "City" in grp.columns else []
            city_label = ", ".join(cities[:6])
            if len(cities) > 6:
                city_label = f"{city_label}, …"
            rows.append(
                {
                    "Submission_ID": sid,
                    "Submission_Type": first.get("Submission_Type", ""),
                    "Product Name": first.get("Product Name", ""),
                    "Start Date": first.get("Start Date", ""),
                    "Status": first.get("Status", ""),
                    "SLA": sla,
                    "Hub_Count": len(grp),
                    "City_Count": len(cities),
                    "Cities": city_label,
                    "Submitted_By": first.get("Submitted_By", ""),
                    "Timestamp": first.get("Timestamp", ""),
                }
            )
        return sanitize_for_json(
            {
                "rows": rows,
                "columns": summary_cols,
                "filters": filters,
                "view": "summary",
                "row_count": len(rows),
            }
        )

    disp_cols = [
        c
        for c in [
            "Submission_ID",
            "Submission_Type",
            "Product ID",
            "Product Name",
            "City",
            "Hub",
            "Start Date",
            "Status",
            "SLA",
            "Rejection_Reason",
            "Submitted_By",
            "Timestamp",
        ]
        if c in work.columns
    ]
    return sanitize_for_json(
        {
            "rows": df_to_records(work[disp_cols] if disp_cols else work),
            "columns": disp_cols or work.columns.tolist(),
            "filters": filters,
            "view": "detail",
            "row_count": len(work),
        }
    )


def set_submission_status(submission_id: str, status: str, reason: str = "") -> None:
    update_submission_status(submission_id, status, reason)


def expansion_context(category: str, product_id: str) -> dict[str, Any]:
    master = load_product_master()
    info = get_product_info(master, product_id)
    return sanitize_for_json(
        {
            "product_id": product_id,
            "category": category,
            "product_info": info,
            "cities": list_cities(),
        }
    )


def replacement_context(old_product_id: str, new_product_id: str) -> dict[str, Any]:
    master = load_product_master()
    return sanitize_for_json(
        {
            "old": get_product_info(master, old_product_id),
            "new": get_product_info(master, new_product_id),
            "cities": list_cities(),
        }
    )
