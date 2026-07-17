"""FF Automation worksheet — sole Google Sheets source for Product Launch masters."""
from __future__ import annotations

import logging

import pandas as pd
from google.oauth2.service_account import Credentials
import gspread

from app.config import FF_AUTOMATION_SHEET_KEY, GOOGLE_CREDENTIALS_PATH

logger = logging.getLogger(__name__)

SHEET_CATEGORY = "ff_automation"
SPREADSHEET_KEY = FF_AUTOMATION_SHEET_KEY

PRODUCT_MASTER_TAB = "P Master"
PL_MASTER_TAB = "P-L Master"
HUB_MAPPING_TAB = "Hub_Mapping"
HUB_MAPPING_ALT_TAB = "Hub Mapping"
PH_MASTER_TAB = "P-H Master"

PRODUCT_MASTER_RANGE = "A:K"
HUB_MAPPING_RANGE = "A:F"
PH_MASTER_RANGE = "A:AX"
PL_MASTER_RANGE = "A:Z"
WIZARD_MASTER_TAB = PL_MASTER_TAB
WIZARD_MASTER_RANGE = PL_MASTER_RANGE


def _canon(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.loc[:, ~df.columns.duplicated(keep="first")].copy()
    rename = {}
    for col in df.columns:
        key = _canon(str(col))
        if key == "subcategory":
            rename[col] = "sub_category"
        elif key == "productid":
            rename[col] = "Product id"
        elif key == "cityname":
            rename[col] = "city_name"
        elif key == "city":
            rename[col] = "city_name"
        elif key == "hubname":
            rename[col] = "hub_name"
    if rename:
        df = df.rename(columns=rename)
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def _resolve_col(df: pd.DataFrame, *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
    lookup = {_canon(c): c for c in df.columns}
    for candidate in candidates:
        hit = lookup.get(_canon(candidate))
        if hit:
            return hit
    return None


def _get_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_PATH, scopes=scopes)
    return gspread.authorize(creds)


def _open_sheet(spreadsheet_id: str, sheet_name: str):
    client = _get_client()
    sh = client.open_by_key(spreadsheet_id)
    return sh.worksheet(sheet_name)


def _fetch_sheet_values(tab_name: str, range_notation: str, *, alternates: list[str] | None = None) -> list[list[str]]:
    names = [tab_name]
    if alternates:
        names.extend(n for n in alternates if n not in names)
    last_exc: Exception | None = None
    for name in names:
        try:
            sheet = _open_sheet(SPREADSHEET_KEY, name)
            return sheet.get_values(range_notation) if range_notation else sheet.get_all_values()
        except Exception as exc:
            last_exc = exc
            logger.debug("FF Automation tab %r unavailable: %s", name, exc)
    if last_exc:
        raise last_exc
    return []


def read_ff_sheet_cached(
    tab_name: str,
    range_notation: str,
    *,
    alternates: list[str] | None = None,
) -> list[list[str]]:
    from features.product_launch.sheet_reads import read_sheet_values_cached

    def _fetch():
        return _fetch_sheet_values(tab_name, range_notation, alternates=alternates)

    return read_sheet_values_cached(
        SPREADSHEET_KEY,
        tab_name,
        range_notation,
        sheet_category=SHEET_CATEGORY,
        fetcher=_fetch,
    )


def _values_to_df(data: list[list[str]]) -> pd.DataFrame:
    if len(data) < 2:
        return pd.DataFrame()
    headers = data[0]
    num_cols = len(headers)
    cleaned_rows = []
    for row in data[1:]:
        if len(row) < num_cols:
            cleaned_rows.append(row + [""] * (num_cols - len(row)))
        elif len(row) > num_cols:
            cleaned_rows.append(row[:num_cols])
        else:
            cleaned_rows.append(row)
    return _normalize_columns(pd.DataFrame(cleaned_rows, columns=headers))


def load_product_master_df() -> pd.DataFrame:
    """Wizard product/category source — P-L Master on FF Automation worksheet."""
    data = read_ff_sheet_cached(WIZARD_MASTER_TAB, WIZARD_MASTER_RANGE)
    df = _values_to_df(data)
    if df.empty:
        return df

    for col in df.columns:
        if "order" in str(col).lower() and "type" in str(col).lower():
            df = df[df[col].astype(str).str.strip().str.upper() == "E"]
            break

    pid_col = _resolve_col(df, "Product id", "Product ID", "product_id")
    if pid_col:
        df = df.drop_duplicates(subset=[pid_col])
    return df


def load_p_master_df() -> pd.DataFrame:
    """Optional P Master tab (used by P-H sync when present)."""
    try:
        data = read_ff_sheet_cached(PRODUCT_MASTER_TAB, PRODUCT_MASTER_RANGE, alternates=[])
    except Exception as exc:
        logger.warning("P Master tab unavailable on FF Automation sheet: %s", exc)
        return pd.DataFrame()
    df = _values_to_df(data)
    if df.empty:
        return df
    pid_col = _resolve_col(df, "Product id", "Product ID", "product_id")
    if pid_col:
        df = df.drop_duplicates(subset=[pid_col])
    return df


def load_hub_mapping_df() -> pd.DataFrame:
    try:
        data = read_ff_sheet_cached(
            HUB_MAPPING_TAB,
            HUB_MAPPING_RANGE,
            alternates=[HUB_MAPPING_ALT_TAB],
        )
    except Exception as exc:
        logger.warning("Failed to load Hub Mapping from FF Automation: %s", exc)
        return pd.DataFrame()
    return _values_to_df(data)


def load_ph_master_df() -> pd.DataFrame:
    try:
        data = read_ff_sheet_cached(PH_MASTER_TAB, PH_MASTER_RANGE)
    except Exception as exc:
        logger.warning("P-H Master tab unavailable on FF Automation sheet: %s", exc)
        return pd.DataFrame()
    return _values_to_df(data)


def hub_mapping_as_catalog(hub_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Normalize Hub Mapping rows to city/hub catalog used by the wizard."""
    df = hub_df if hub_df is not None else load_hub_mapping_df()
    if df.empty:
        return pd.DataFrame(columns=["city_name", "hub_name", "Plan Flag"])

    out = df.copy()
    city_col = _resolve_col(out, "city_name", "City Name", "city")
    hub_col = _resolve_col(out, "hub_name", "Hub Name", "hub")
    status_col = _resolve_col(out, "status", "Status", "Plan Flag", "hub_active")
    if city_col:
        out["city_name"] = out[city_col].astype(str).str.strip()
    if hub_col:
        out["hub_name"] = out[hub_col].astype(str).str.strip()
    if status_col:
        out["Plan Flag"] = out[status_col].apply(
            lambda x: "A" if str(x).strip().upper() in {"A", "1"} else "I"
        )
    else:
        out["Plan Flag"] = "A"
    keep = [c for c in ["city_name", "hub_name", "Plan Flag"] if c in out.columns]
    return out[keep].dropna(how="all") if keep else pd.DataFrame()
