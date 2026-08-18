"""
Fast local I/O helpers for the optimized baseline engine.

- Single open for Product_Masters (P Master + P-H Master)
- Single read for Percentile with in-memory column slices
- Parquet sidecars for DP Logics tables (written during config sync)
- Engine path prefers fresh parquet sidecars (Phase B2)
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TypedDict

import pandas as pd
from core.shared.drive_client import upload_df_to_drive, download_df_from_drive
from app.config import get_pipeline_drive_folder_id
import logging

logger = logging.getLogger(__name__)

def get_dp_logics_folder_id() -> str:
    folder = get_pipeline_drive_folder_id()
    if not folder:
        # Fallback to the explicit ID used for Festive Upload if env var missing
        return "17mYoNPGhmhw4MlZoE24gWG2onA9WmFya"
    return folder

P_MASTER_SHEET = "P Master"
P_MASTER_READ_RANGE = ""
PH_MASTER_SHEET = "P-H Master"

PERCENTILE_AD_PARQUET = "percentile_AD.parquet"
PERCENTILE_JK_PARQUET = "percentile_JK.parquet"
PERCENTILE_OR_PARQUET = "percentile_OR.parquet"
P_MASTER_PARQUET = "p_master.parquet"
PH_MASTER_PARQUET = "ph_master.parquet"


class PercentileSlices(TypedDict):
    percentile: pd.DataFrame
    override_hub: pd.DataFrame
    override_hub_sku_day: pd.DataFrame


# sidecar_exists_and_fresh removed completely.


def product_masters_sidecar_dir(excel_path: str | Path) -> Path:
    return Path(excel_path).parent / ".parquet_cache"


def write_percentile_engine_sidecars(
    folder: str | Path,
    full: pd.DataFrame | None = None,
) -> dict[str, Path]:
    """Write Percentile A:D, J:K, O:R slices as engine sidecars."""
    folder = Path(folder)
    xlsx = dp_logics_xlsx_path(folder, "Percentile")
    if full is None:
        if not xlsx.exists():
            raise FileNotFoundError(f"Percentile workbook not found: {xlsx}")
        full = pd.read_excel(xlsx)
    slices = percentile_slices_from_frame(full)
    paths = {
        "percentile": folder / PERCENTILE_AD_PARQUET,
        "override_hub": folder / PERCENTILE_JK_PARQUET,
        "override_hub_sku_day": folder / PERCENTILE_OR_PARQUET,
    }
    folder_id = get_dp_logics_folder_id()
    
    # Cast object columns to strings to avoid PyArrow mixed-type crashes
    for key in slices:
        out_df = slices[key].copy()
        for col in out_df.columns:
            if out_df[col].dtype == 'object':
                out_df[col] = out_df[col].apply(lambda x: str(x) if pd.notnull(x) else x)
        slices[key] = out_df

    upload_df_to_drive(slices["percentile"], PERCENTILE_AD_PARQUET, folder_id)
    upload_df_to_drive(slices["override_hub"], PERCENTILE_JK_PARQUET, folder_id)
    upload_df_to_drive(slices["override_hub_sku_day"], PERCENTILE_OR_PARQUET, folder_id)
    
    return paths


def write_product_master_engine_sidecars(excel_path: str | Path) -> tuple[Path, Path]:
    """Build p_master / ph_master parquet sidecars next to Product_Masters.xlsx."""
    excel_path = Path(excel_path)
    p_df, ph_df = load_product_masters_sheets(excel_path)
    out_dir = product_masters_sidecar_dir(excel_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    p_path = out_dir / P_MASTER_PARQUET
    ph_path = out_dir / PH_MASTER_PARQUET
    folder_id = get_dp_logics_folder_id()

    # Cast object columns to strings to avoid PyArrow mixed-type crashes
    for df in (p_df, ph_df):
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].apply(lambda x: str(x) if pd.notnull(x) else x)

    upload_df_to_drive(p_df, P_MASTER_PARQUET, folder_id)
    upload_df_to_drive(ph_df, PH_MASTER_PARQUET, folder_id)
    return p_path, ph_path


def refresh_all_engine_sidecars(
    dp_logics_folder: str | Path,
    masters_xlsx: str | Path,
) -> dict[str, str]:
    """
    Regenerate engine parquet sidecars after Step 1 (masters) or Step 4 (DP Logics).
    Used by Auto-Pilot and manual Configure Parameters sync.
    """
    folder = Path(dp_logics_folder)
    masters_xlsx = Path(masters_xlsx)
    status: dict[str, str] = {}

    if masters_xlsx.exists():
        write_product_master_engine_sidecars(masters_xlsx)
        status["product_masters"] = "ok"

    percentile_xlsx = dp_logics_xlsx_path(folder, "Percentile")
    if percentile_xlsx.exists():
        write_percentile_engine_sidecars(folder)
        status["percentile_slices"] = "ok"

    for table in ("City_Cat", "Avl_Flag", "SellThroughFactor", "City_drops"):
        try:
            read_dp_logics_table_engine(folder, table)
            status[table] = "ok"
        except FileNotFoundError:
            status[table] = "missing"

    return status


def load_product_masters_sheets_engine(excel_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Engine read: strictly download from Google Drive."""
    folder_id = get_dp_logics_folder_id()
    try:
        p_df = download_df_from_drive(P_MASTER_PARQUET, folder_id)
        ph_df = download_df_from_drive(PH_MASTER_PARQUET, folder_id)
        return p_df, ph_df
    except FileNotFoundError:
        # Rebuild if not in drive
        write_product_master_engine_sidecars(excel_path)
        p_df = download_df_from_drive(P_MASTER_PARQUET, folder_id)
        ph_df = download_df_from_drive(PH_MASTER_PARQUET, folder_id)
        return p_df, ph_df


def load_product_masters_sheets(excel_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read P Master and P-H Master from one Excel file open."""
    path = Path(excel_path)
    if not path.exists():
        raise FileNotFoundError(f"Product masters not found: {path}")
    with pd.ExcelFile(path) as book:
        p_master = pd.read_excel(book, sheet_name=P_MASTER_SHEET)
        ph_master = pd.read_excel(book, sheet_name=PH_MASTER_SHEET)
    return p_master, ph_master


def percentile_slices_from_frame(full: pd.DataFrame) -> PercentileSlices:
    """
    Slice Percentile worksheet columns in memory (same ranges as legacy usecols).

    A:D  -> base percentile
    J:K  -> hub override
    O:R  -> hub × SKU × day override
    """
    if full.shape[1] < 18:
        full = full.copy()
        for i in range(full.shape[1], 18):
            full[f"__pad_col_{i}"] = None

    percentile = full.iloc[:, 0:4].copy()
    percentile.columns = list(full.columns[0:4])

    override_hub = full.iloc[:, 9:11].copy()
    override_hub.columns = list(full.columns[9:11])

    override_hub_sku_day = full.iloc[:, 14:18].copy()
    override_hub_sku_day.columns = list(full.columns[14:18])

    return PercentileSlices(
        percentile=percentile.dropna(how="all"),
        override_hub=override_hub.dropna(how="all"),
        override_hub_sku_day=override_hub_sku_day.dropna(how="all"),
    )


def load_percentile_slices(folder: str | Path) -> PercentileSlices:
    """Load Percentile table once (parquet sidecar or xlsx) and return slices."""
    return percentile_slices_from_frame(read_dp_logics_table(folder, "Percentile"))


def dp_logics_parquet_path(folder: str | Path, table_name: str) -> Path:
    return Path(folder) / f"{table_name}.parquet"


def dp_logics_xlsx_path(folder: str | Path, table_name: str) -> Path:
    return Path(folder) / f"{table_name}.xlsx"


def write_dp_logics_parquet_sidecar(df: pd.DataFrame, xlsx_path: str | Path) -> Path:
    """Upload a DP Logics table directly to Google Drive as Parquet."""
    folder_id = get_dp_logics_folder_id()
    pq_path = Path(xlsx_path).with_suffix(".parquet")
    filename = pq_path.name
    
    # Prevent PyArrow mixed-type crashes by coercing object columns to strings
    out_df = df.copy()
    for col in out_df.columns:
        if out_df[col].dtype == 'object':
            out_df[col] = out_df[col].apply(lambda x: str(x) if pd.notnull(x) else x)
            
    try:
        upload_df_to_drive(out_df, filename, folder_id)
        logger.info(f"Uploaded {filename} to Google Drive")
    except Exception as e:
        logger.error(f"Failed to upload {filename} to Google Drive: {e}")
        raise
        
    return pq_path


def read_dp_logics_table(folder: str | Path, table_name: str) -> pd.DataFrame:
    """
    Read a DP Logics table from the synced parquet (preferred) or xlsx fallback.

    Parquet sidecars are refreshed after each xlsx read but are not preferred over xlsx,
    so a stale sidecar cannot mask an updated workbook.
    """
    folder = Path(folder)
    xlsx = dp_logics_xlsx_path(folder, table_name)
    parquet = dp_logics_parquet_path(folder, table_name)

    if parquet.exists():
        return pd.read_parquet(parquet)

    if xlsx.exists():
        df = pd.read_excel(xlsx)
        try:
            write_dp_logics_parquet_sidecar(df, xlsx)
        except Exception:
            pass
        return df

    raise FileNotFoundError(f"DP Logics table not found: {xlsx} (or {parquet})")


def read_dp_logics_table_engine(folder: str | Path, table_name: str) -> pd.DataFrame:
    """Baseline engine path: strictly download from Google Drive."""
    folder_id = get_dp_logics_folder_id()
    filename = f"{table_name}.parquet"
    try:
        logger.info(f"Downloading {filename} from Google Drive...")
        return download_df_from_drive(filename, folder_id)
    except FileNotFoundError:
        raise FileNotFoundError(f"DP Logics table '{filename}' not found in Google Drive folder {folder_id}")


def load_percentile_slices_engine(folder: str | Path) -> PercentileSlices:
    """Load Percentile slices from Google Drive, rebuild if missing."""
    folder_id = get_dp_logics_folder_id()
    try:
        return PercentileSlices(
            percentile=download_df_from_drive(PERCENTILE_AD_PARQUET, folder_id),
            override_hub=download_df_from_drive(PERCENTILE_JK_PARQUET, folder_id),
            override_hub_sku_day=download_df_from_drive(PERCENTILE_OR_PARQUET, folder_id),
        )
    except FileNotFoundError:
        folder = Path(folder)
        xlsx = dp_logics_xlsx_path(folder, "Percentile")
        if xlsx.exists():
            full = pd.read_excel(xlsx)
        else:
            full = read_dp_logics_table(folder, "Percentile")
        slices = percentile_slices_from_frame(full)
        write_percentile_engine_sidecars(folder, full)
        return slices


def avl_flag_subcat_cat_df(avl_flag_full: pd.DataFrame) -> pd.DataFrame:
    """Sub-category / Cat / HTT mapping (columns H:J fallback matches legacy usecols)."""
    needed = ["sub category", "Cat", "HTT"]
    if all(c in avl_flag_full.columns for c in needed):
        return avl_flag_full[needed].drop_duplicates()
    if avl_flag_full.shape[1] >= 10:
        out = avl_flag_full.iloc[:, 7:10].copy()
        out.columns = list(avl_flag_full.columns[7:10])
        return out.drop_duplicates()
    raise KeyError(
        "Avl_Flag missing sub category/Cat/HTT columns. "
        f"Available: {avl_flag_full.columns.tolist()}"
    )


def _find_p_master_column(columns, *candidates: str) -> str | None:
    lookup = {str(c).strip().lower(): c for c in columns}
    for cand in candidates:
        hit = lookup.get(cand.strip().lower())
        if hit:
            return hit
    return None


def prepare_p_master_for_enrichment(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Normalize P Master for SKU enrichment: clean headers, unique product_id rows.

    Duplicate product ids cause pandas map() to raise:
    "Reindexing only valid with uniquely valued Index objects".
    """
    from core.utils.dataframe import clean_sheet_df


    if df is None or df.empty:
        return df, 0

    out = clean_sheet_df(df.copy())
    id_col = _find_p_master_column(out.columns, "product id", "product_id")
    if not id_col:
        raise KeyError("P Master missing product id column")

    out = out.rename(columns={id_col: "product_id"})
    out["product_id"] = out["product_id"].astype(str).str.strip()
    out = out[out["product_id"].ne("") & out["product_id"].ne("nan")]
    dup_count = int(out["product_id"].duplicated().sum())
    out = out.drop_duplicates(subset=["product_id"], keep="first")
    return out, dup_count


def p_master_enrichment_maps(
    df: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series, int]:
    """Return SKU / name / category lookup Series keyed by product_id."""
    prepared, dup_count = prepare_p_master_for_enrichment(df)
    sku_col = _find_p_master_column(prepared.columns, "SKU Class Prod", "sku class prod")
    name_col = _find_p_master_column(prepared.columns, "Product Name", "product_name")
    cat_col = _find_p_master_column(
        prepared.columns, "Sub-category", "Sub category", "sub-category",
    )
    missing = [
        label for label, col in (
            ("SKU Class Prod", sku_col),
            ("Product Name", name_col),
            ("Sub-category", cat_col),
        )
        if not col
    ]
    if missing:
        raise KeyError(f"P Master missing columns: {', '.join(missing)}")

    indexed = prepared.set_index("product_id")
    return indexed[sku_col], indexed[name_col], indexed[cat_col], dup_count
