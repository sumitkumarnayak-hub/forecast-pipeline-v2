"""Week-level raw actuals parquet cache helpers (Auto-Pilot + manual baseline)."""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Callable

import pandas as pd


def iso_week_for_date(value: date | datetime | pd.Timestamp) -> int:
    ts = pd.to_datetime(value)
    return int(ts.isocalendar().week)


def week_parquet_path(iso_week: int, folder: str) -> str:
    return os.path.join(folder, f"Raw_Actuals_Wk{iso_week}.parquet")


def load_cached_week_parquet(iso_week: int, folder: str) -> pd.DataFrame | None:
    path = week_parquet_path(iso_week, folder)
    if not os.path.isfile(path) or os.path.getsize(path) <= 0:
        return None
    try:
        df = pd.read_parquet(path)
    except Exception:
        return None
    return df if df is not None and not df.empty else None


def resolve_raw_actuals_for_week(
    start_date: date | datetime | pd.Timestamp,
    folder: str,
    fetch_fn: Callable[[], pd.DataFrame | None],
    *,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame | None, int, bool]:
    """
    Load raw actuals for the ISO week of ``start_date``.

    Returns ``(dataframe, iso_week, from_cache)``.
    """
    iso_week = iso_week_for_date(start_date)
    if not force_refresh:
        cached = load_cached_week_parquet(iso_week, folder)
        if cached is not None:
            return cached, iso_week, True
    df = fetch_fn()
    return df, iso_week, False


def write_week_parquet(df: pd.DataFrame, iso_week: int, folder: str) -> str:
    os.makedirs(folder, exist_ok=True)
    path = week_parquet_path(iso_week, folder)
    df.to_parquet(path, index=False)
    return path
