"""
New product launch sync — P Master → P-H Master (Product ph_master_automation new-product-sync).

For each product in P Master that is not yet present in P-H Master, append one row
per active hub (Hub_active = A) with Plan Design = I.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd

from core.utils.dataframe import clean_sheet_df

from core.shared.google_sheets import GoogleSheetsManager


P_MASTER_READ_RANGE = "A:K"
PH_MASTER_READ_RANGE = "A:AX"
HUB_MASTER_READ_RANGE = "A:E"

P_MASTER_REQUIRED_COLS = [
    "Product id", "Sub-category", "SKU Class Prod", "Anchor ID", "Anchor Name", "Cut Classification",
]
HUB_MAPPING_REQUIRED_COLS = ["hub_name", "city_name", "status"]
PH_MASTER_REQUIRED_COLS = ["product_id", "hub_name", "city_name", "Plan Design"]
P_MASTER_NONEMPTY_FIELDS = ["Product id", "Sub-category", "SKU Class Prod"]

PH_FROM_P_MASTER = {
    "sub category": "Sub-category",
    "sku class prod": "SKU Class Prod",
    "product_id": "Product id",
    "Anchor ID": "Anchor ID",
    "Anchor Name": "Anchor Name",
    "Cut Classification": "Cut Classification",
}


def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in str(text).strip() if ch.isalnum())


def _col_map(columns) -> dict[str, str]:
    return {_normalize(c): c for c in columns}


def _actual(norm_map: dict[str, str], wanted: str) -> str:
    return norm_map.get(_normalize(wanted), wanted)


@dataclass
class ProductLaunchPreview:
    product_ids: list[str] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    not_in_p_master: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
    already_exists: list[dict] = field(default_factory=list)
    rows_to_add: list[dict] = field(default_factory=list)
    ph_headers: list[str] = field(default_factory=list)
    active_hub_count: int = 0
    new_products_discovered: list[str] = field(default_factory=list)

    @property
    def ready_to_write(self) -> bool:
        return (
            not self.schema_errors
            and not self.validation_errors
            and bool(self.rows_to_add)
        )


@dataclass
class ProductLaunchSyncResult:
    success: bool
    products_found: int = 0
    products_synced: list[str] = field(default_factory=list)
    rows_inserted: int = 0
    duplicates_skipped: int = 0
    masters_re_synced: bool = False
    ph_rows_after: int = 0
    preview: ProductLaunchPreview | None = None
    error: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1


def discover_new_product_ids(p_df: pd.DataFrame, ph_df: pd.DataFrame) -> list[str]:
    """Products in P Master with no row yet in P-H Master (Product new-product-sync)."""
    p_cols = _col_map(p_df.columns)
    ph_cols = _col_map(ph_df.columns)
    p_id_col = _actual(p_cols, "Product id")
    ph_pid_col = _actual(ph_cols, "product_id")

    all_p_ids = [
        str(v).strip()
        for v in p_df[p_id_col].dropna().unique()
        if str(v).strip()
    ]
    existing = {
        str(v).strip()
        for v in ph_df[ph_pid_col].dropna().unique()
        if str(v).strip()
    }
    return sorted(p for p in all_p_ids if p not in existing)


def build_new_product_ph_preview(
    p_df: pd.DataFrame,
    hub_df: pd.DataFrame,
    ph_df: pd.DataFrame,
    product_ids: Sequence[str] | None = None,
) -> ProductLaunchPreview:
    """Build rows to append; no writes."""
    preview = ProductLaunchPreview()
    p_df = clean_sheet_df(p_df)
    hub_df = clean_sheet_df(hub_df)
    ph_df = clean_sheet_df(ph_df)

    for col in P_MASTER_REQUIRED_COLS:
        if col not in p_df.columns:
            preview.schema_errors.append(f"P Master is missing column: {col}")
    for col in HUB_MAPPING_REQUIRED_COLS:
        if col not in hub_df.columns:
            preview.schema_errors.append(f"Hub Mapping is missing column: {col}")
    for col in PH_MASTER_REQUIRED_COLS:
        if col not in ph_df.columns:
            preview.schema_errors.append(f"P-H Master is missing column: {col}")
    if preview.schema_errors:
        return preview

    p_cols = _col_map(p_df.columns)
    ph_cols = _col_map(ph_df.columns)
    p_id_col = "Product id"
    hub_name_col = "hub_name"
    city_name_col = "city_name"
    hub_active_col = "status"

    if product_ids:
        requested = [str(x).strip() for x in product_ids if str(x).strip()]
    else:
        requested = discover_new_product_ids(p_df, ph_df)
        preview.new_products_discovered = list(requested)

    preview.product_ids = requested
    if not requested:
        return preview

    all_p_ids = set(p_df[p_id_col].astype(str).str.strip())
    preview.not_in_p_master = [pid for pid in requested if pid not in all_p_ids]
    valid_pids = [pid for pid in requested if pid in all_p_ids]
    if not valid_pids:
        return preview

    for pid in valid_pids:
        p_row = p_df[p_df[p_id_col].astype(str).str.strip() == pid].iloc[0]
        for field in P_MASTER_NONEMPTY_FIELDS:
            actual_field = _actual(p_cols, field)
            if str(p_row.get(actual_field, "")).strip() == "":
                preview.validation_errors.append(
                    f"Product {pid}: '{field}' is blank in P Master — fill it before syncing."
                )

    active_hubs = hub_df[
        (hub_df[hub_active_col].astype(str).str.strip().str.upper() == "A")
        & (hub_df[hub_name_col].astype(str).str.strip() != "")
    ].copy()
    preview.active_hub_count = len(active_hubs)
    if active_hubs.empty:
        preview.validation_errors.append("No active hubs with a valid hub_name found in Hub Mapping.")

    ph_headers = ph_df.columns.tolist()
    preview.ph_headers = ph_headers
    ph_pid_col = _actual(ph_cols, "product_id")
    ph_hub_col = _actual(ph_cols, "hub_name")

    pid_vals = ph_df[ph_pid_col].astype(str).str.strip()
    hub_vals = ph_df[ph_hub_col].astype(str).str.strip()
    valid_mask = (pid_vals != "") & (hub_vals != "")
    existing_pairs = set(zip(pid_vals[valid_mask], hub_vals[valid_mask]))

    hub_name_col_actual = hub_name_col
    city_name_col_actual = city_name_col

    for pid in valid_pids:
        p_row = p_df[p_df[p_id_col].astype(str).str.strip() == pid].iloc[0]
        for hub_row in active_hubs.itertuples(index=False):
            hub_name = str(getattr(hub_row, hub_name_col_actual, "")).strip()
            city_name = str(getattr(hub_row, city_name_col_actual, "")).strip()
            if (pid, hub_name) in existing_pairs:
                preview.already_exists.append({
                    "product_id": pid,
                    "city_name": city_name,
                    "hub_name": hub_name,
                })
                continue

            new_row = {h: "" for h in ph_headers}
            new_row[_actual(ph_cols, "city_name")] = city_name
            new_row[_actual(ph_cols, "hub_name")] = hub_name
            new_row[_actual(ph_cols, "product_id")] = pid
            for ph_col, p_col in PH_FROM_P_MASTER.items():
                ph_actual = _actual(ph_cols, ph_col)
                p_actual = _actual(p_cols, p_col)
                if ph_actual in new_row:
                    new_row[ph_actual] = str(p_row.get(p_actual, "")).strip()
            new_row[_actual(ph_cols, "Plan Design")] = "I"
            preview.rows_to_add.append(new_row)
            existing_pairs.add((pid, hub_name))

    return preview


def load_masters_for_product_sync(sheets: GoogleSheetsManager) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from core.utils.dataframe import clean_sheet_df
    from features.product_launch.ff_masters import (
        load_hub_mapping_df,
        load_ph_master_df,
        load_p_master_df,
        load_product_master_df,
    )

    p_df = clean_sheet_df(load_p_master_df())
    if p_df.empty:
        p_df = clean_sheet_df(load_product_master_df())
    hub_df = clean_sheet_df(load_hub_mapping_df())
    ph_df = clean_sheet_df(load_ph_master_df())
    if p_df is None or hub_df is None or ph_df is None:
        raise RuntimeError("Could not load P Master, Hub Mapping, or P-H Master from FF Automation worksheet.")
    return p_df, hub_df, ph_df


def write_ph_rows(sheets: GoogleSheetsManager, rows: list[dict], ph_headers: list[str]) -> None:
    if not rows:
        return
    values = [[r.get(h, "") for h in ph_headers] for r in rows]
    sheets.append_rows_to_worksheet(
        "ff_automation",
        "product_hub_master",
        values,
    )

def run_new_product_launch_sync(
    user_id: int | None = None,
    *,
    sheets: GoogleSheetsManager | None = None,
    product_ids: Sequence[str] | None = None,
    dry_run: bool = False,
    re_sync_masters: bool = True,
    db=None,
) -> ProductLaunchSyncResult:
    """
    Sync new products from P Master to P-H Master (all active hubs).

    When ``product_ids`` is None, auto-discovers products not yet in P-H Master
    (same as Product ``ph_master_automation.py new-product-sync``).
    """
    from app.config import FF_MASTERS_XLSX
    from core.database.engine import Database


    sheets = sheets or GoogleSheetsManager()
    result = ProductLaunchSyncResult(success=True)

    try:
        p_df, hub_df, ph_df = load_masters_for_product_sync(sheets)
    except Exception as exc:
        return ProductLaunchSyncResult(success=False, error=str(exc))

    preview = build_new_product_ph_preview(p_df, hub_df, ph_df, product_ids=product_ids)
    result.preview = preview
    result.products_found = len(preview.product_ids)
    result.products_synced = list(preview.product_ids)
    result.duplicates_skipped = len(preview.already_exists)

    if preview.schema_errors:
        result.success = False
        result.error = "; ".join(preview.schema_errors)
        return result
    if preview.validation_errors:
        result.success = False
        result.error = "; ".join(preview.validation_errors[:5])
        return result
    if not preview.rows_to_add:
        return result

    if dry_run:
        result.rows_inserted = len(preview.rows_to_add)
        return result

    try:
        write_ph_rows(sheets, preview.rows_to_add, preview.ph_headers)
        result.rows_inserted = len(preview.rows_to_add)
    except Exception as exc:
        return ProductLaunchSyncResult(success=False, error=f"P-H Master write failed: {exc}")

    if re_sync_masters and result.rows_inserted > 0:
        from features.master_data.sync import run_master_data_excel_sync


        sync = run_master_data_excel_sync(
            FF_MASTERS_XLSX, user_id or 1, db=db or Database(), sheets_manager=sheets,
        )
        result.masters_re_synced = sync.success
        result.ph_rows_after = sync.ph_rows
        if not sync.success:
            result.success = False
            result.error = sync.error or "Master re-sync failed after P-H write."

    return result
