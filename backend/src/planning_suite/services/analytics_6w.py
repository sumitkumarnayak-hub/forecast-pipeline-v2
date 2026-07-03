"""Shared 6-week rolling data loaders for Dashboard, Insights, and Reports."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Iterable

import numpy as np
import pandas as pd
import polars as pl

from planning_suite.config import OUTPUT_PATH, PLANNING_DRIVE_ROOT, RDS_6W_PATH, get_storage_backend_name

OUTPUT_RDS_CACHE = str(OUTPUT_PATH / "rds_cache.parquet")
OUTPUT_6W_PARQUET = str(OUTPUT_PATH / "6w_v3.parquet")


def _use_planning_drive_mount() -> bool:
    """Local Google Drive for Desktop mount — not used on Render/shared Drive storage."""
    if get_storage_backend_name() in {"drive", "supabase"}:
        return False
    root = (PLANNING_DRIVE_ROOT or "").strip()
    if not root or root.startswith("/var/"):
        return False
    return os.path.isdir(root)


def drive_csv_path() -> str:
    root = PLANNING_DRIVE_ROOT or ""
    return os.path.join(
        root,
        "Planning Team",
        "25. Planning_Database",
        "01_all_day_reporting",
        "04_6w_rolling_data",
        "6w_v3.csv",
    )


def drive_parquet_path() -> str:
    return drive_csv_path().replace(".csv", ".parquet")


def describe_missing_6w_sources() -> str:
    backend = get_storage_backend_name()
    if backend in {"drive", "supabase"}:
        return (
            "No 6-week data file found.\n\n"
            f"Expected `{OUTPUT_RDS_CACHE}` (synced from shared Drive key `outputs/rds_cache.parquet`).\n"
            "- Upload it once from your machine: `cd backend && python scripts/push_pipeline_storage.py`\n"
            "- Ensure your backend (Hugging Face Space or Render) has `STORAGE_BACKEND=drive` "
            "and `PIPELINE_DRIVE_FOLDER_URL` set.\n"
            "- Restart the service so startup pulls artifacts from shared Drive, or use "
            "Settings → Sync storage (admin)."
        )
    rds = RDS_6W_PATH or "(not set in .env)"
    drive = drive_csv_path()
    return (
        "No 6-week data file found.\n\n"
        f"- Set **`RDS_6W_PATH`** (currently `{rds}`) and load raw data once in "
        "**1. Load Raw Data** to build `outputs/rds_cache.parquet`, or\n"
        f"- Mount Google Drive and ensure **`PLANNING_DRIVE_ROOT`** points at the CSV:\n"
        f"  `{drive}` (or `.parquet` beside it)"
    )


def _ensure_rds_parquet_cache() -> str | None:
    """Build rds_cache.parquet from RDS when missing or stale."""
    if not RDS_6W_PATH or not os.path.exists(RDS_6W_PATH):
        return None
    OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
    cache = OUTPUT_RDS_CACHE
    try:
        if os.path.exists(cache) and os.path.getmtime(cache) >= os.path.getmtime(RDS_6W_PATH):
            return cache
    except OSError:
        pass
    try:
        import pyreadr

        result = pyreadr.read_r(RDS_6W_PATH)
        df = next(iter(result.values()))
        df.to_parquet(cache, index=False)
        return cache
    except Exception:
        return None


def resolve_6w_read_path(*, allow_rds_build: bool = False) -> str:
    """Pick the fastest available 6w source (parquet preferred).

    ``allow_rds_build=False`` (default) avoids blocking API requests on a slow
    pyreadr conversion — that build belongs on **Load Raw Data**, not dashboard bootstrap.
    """
    candidates: list[str] = []
    if os.path.exists(OUTPUT_6W_PARQUET):
        candidates.append(OUTPUT_6W_PARQUET)
    if os.path.exists(OUTPUT_RDS_CACHE):
        candidates.append(OUTPUT_RDS_CACHE)
    if _use_planning_drive_mount():
        dp = drive_parquet_path()
        if os.path.exists(dp):
            candidates.append(dp)
    if allow_rds_build:
        built = _ensure_rds_parquet_cache()
        if built and built not in candidates:
            candidates.append(built)
    if _use_planning_drive_mount():
        dc = drive_csv_path()
        if os.path.exists(dc):
            candidates.append(dc)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(describe_missing_6w_sources())


def build_rds_parquet_cache() -> str | None:
    """Explicit RDS → parquet build (Load Raw Data / admin). May take several minutes."""
    return _ensure_rds_parquet_cache()


def _parquet_columns(path: str) -> set[str]:
    try:
        return set(pl.scan_parquet(path).collect_schema().names())
    except Exception:
        return set()


def _csv_columns(path: str) -> set[str]:
    try:
        return set(pl.read_csv(path, n_rows=0).columns)
    except Exception:
        return set()


_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "sub_category": ("Sub-category", "sub category"),
    "product_name": ("product name", "Product_name"),
}


def _resolve_file_column(file_cols: set[str], canonical: str) -> str | None:
    if canonical in file_cols:
        return canonical
    for alt in _COLUMN_ALIASES.get(canonical, ()):
        if alt in file_cols:
            return alt
    return None


def _normalize_column_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Rename alias columns to canonical names."""
    out = df.copy()
    rename = {}
    for canonical, alts in _COLUMN_ALIASES.items():
        if canonical in out.columns:
            continue
        for alt in alts:
            if alt in out.columns:
                rename[alt] = canonical
                break
    if rename:
        out = out.rename(columns=rename)
    return out


def _read_columns(path: str, cols: Iterable[str]) -> pd.DataFrame:
    want = list(cols)
    if path.endswith(".parquet"):
        file_cols = _parquet_columns(path)
        read_cols: list[str] = []
        rename: dict[str, str] = {}
        for c in want:
            resolved = _resolve_file_column(file_cols, c)
            if resolved:
                read_cols.append(resolved)
                if resolved != c:
                    rename[resolved] = c
        if not read_cols:
            raise ValueError(f"None of the requested columns exist in {path}")
        df = pl.read_parquet(path, columns=read_cols).to_pandas()
        if rename:
            df = df.rename(columns=rename)
    else:
        file_cols = _csv_columns(path)
        read_cols = []
        rename = {}
        for c in want:
            resolved = _resolve_file_column(file_cols, c)
            if resolved:
                read_cols.append(resolved)
                if resolved != c:
                    rename[resolved] = c
        if not read_cols:
            raise ValueError(f"None of the requested columns exist in {path}")
        df = pl.read_csv(path, columns=read_cols, ignore_errors=True).to_pandas()
        if rename:
            df = df.rename(columns=rename)

    for c in want:
        if c not in df.columns:
            df[c] = np.nan
    return _normalize_column_aliases(df[want])


@lru_cache(maxsize=8)
def read_6w_columns(cols: tuple[str, ...]) -> pd.DataFrame:
    """Column-pruned read from the best available 6w parquet/CSV/RDS cache."""
    path = resolve_6w_read_path()
    return _read_columns(path, cols)


def add_iso_week_columns(df: pd.DataFrame, date_col: str = "process_dt") -> pd.DataFrame:
    """Attach iso_year, iso_week, week_label, dow from a datetime column."""
    out = df.copy()
    out[date_col] = pd.to_datetime(out[date_col], errors="coerce")
    out = out.dropna(subset=[date_col])
    iso = out[date_col].dt.isocalendar()
    out["iso_year"] = iso.year.astype(int)
    out["iso_week"] = iso.week.astype(int)
    out["week_label"] = (
        out["iso_year"].astype(str) + "-W" + out["iso_week"].astype(str).str.zfill(2)
    )
    out["dow"] = out[date_col].dt.strftime("%a")
    return out
