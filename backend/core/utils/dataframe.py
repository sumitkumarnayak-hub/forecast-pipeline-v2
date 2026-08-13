"""Shared pandas DataFrame utilities."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


def sanitize_for_json(obj: Any) -> Any:
    """Make nested structures JSON-safe (NaN/Inf → null, numpy scalars → native)."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.isoformat()
    try:
        if obj is pd.NA or pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return obj


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Export DataFrame rows for REST responses without NaN JSON errors."""
    if df.empty:
        return []
    return sanitize_for_json(df.to_dict(orient="records"))


def drop_completely_blank_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Remove rows where every cell is empty, whitespace, or null.
    Returns (cleaned DataFrame, number of rows removed).
    """
    if df.empty:
        return df, 0

    str_df = df.fillna("").astype(str).apply(lambda series: series.str.strip())
    blank_mask = (str_df == "").all(axis=1)
    removed = int(blank_mask.sum())
    if removed == 0:
        return df, 0
    return df.loc[~blank_mask].reset_index(drop=True), removed


def clean_sheet_df(df: pd.DataFrame, *, drop_blank_rows: bool = True) -> pd.DataFrame:
    """
    Clean a DataFrame loaded from Google Sheets:
    - Reset index so Polars conversion is safe
    - Strip whitespace from column headers
    - Drop columns with empty/blank headers ONLY if they are also completely blank in data rows
    - Assign Unnamed_ prefix to remaining columns with empty headers
    - Deduplicate column names by appending _2, _3, ... suffixes
    - Drop completely blank rows (optional, on by default)
    """
    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]

    # Drop columns with empty headers ONLY if they are also completely blank in data rows
    keep_cols = []
    for i, col in enumerate(df.columns):
        if col != "":
            keep_cols.append(True)
        else:
            col_series = df.iloc[:, i]
            has_data = col_series.fillna("").astype(str).str.strip().ne("").any()
            keep_cols.append(has_data)
    df = df.loc[:, keep_cols]

    # Assign safe Unnamed names to remaining blank header columns
    df.columns = [c if c != "" else f"Unnamed_{i}" for i, c in enumerate(df.columns)]

    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 1
            new_cols.append(col)
    df.columns = new_cols

    blank_rows_removed = 0
    if drop_blank_rows:
        df, blank_rows_removed = drop_completely_blank_rows(df)

    df.attrs["blank_rows_removed"] = blank_rows_removed
    return df


def split_adhoc_adjustment(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split the combined Adhoc Adjustment raw dataframe into:
    - A:D (index 0:4) city x subcat x date level adhoc adjustment
    - H:K (index 7:11) city x product_id x date level adhoc adjustment
    Both are cleaned and blank rows are dropped.
    """
    # Slice 1: A:D (columns 0 to 4)
    df_ad_raw = df_raw.iloc[:, 0:4].copy()
    df_ad = clean_sheet_df(df_ad_raw)

    # Slice 2: H:K (columns 7 to 11)
    df_hk = pd.DataFrame()
    if df_raw.shape[1] >= 11:
        df_hk_raw = df_raw.iloc[:, 7:11].copy()
        df_hk = clean_sheet_df(df_hk_raw)

    return df_ad, df_hk
