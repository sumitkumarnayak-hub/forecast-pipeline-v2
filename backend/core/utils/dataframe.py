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
    - Drop columns with empty/blank headers (trailing empty columns from Sheets)
    - Deduplicate column names by appending _2, _3, ... suffixes
    - Drop completely blank rows (optional, on by default)
    """
    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, df.columns != ""]

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
