"""TTL parquet cache for Google Sheets reads (Auto-Pilot + manual flows)."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pandas as pd

from planning_suite.core.dataframe import clean_sheet_df


def _cache_dir() -> Path:
    """Writable cache dir — uses OUTPUT_PATH (/app/data/outputs on cloud)."""
    from planning_suite.config import OUTPUT_PATH

    path = OUTPUT_PATH / "sheets_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path

# Seconds — override via env (e.g. SHEETS_CACHE_TTL_MASTERS=1800)
def _ttl(name: str, default: int) -> int:
    key = f"SHEETS_CACHE_TTL_{name.upper().replace(' ', '_')}"
    raw = os.getenv(key, "").strip()
    if raw.isdigit():
        return int(raw)
    return default


DEFAULT_TTL_SECONDS: dict[str, int] = {
    "P Master": _ttl("masters", 1800),
    "P-L Master": _ttl("masters", 1800),
    "P-H Master": _ttl("masters", 1800),
    "Hub Mapping": _ttl("masters", 1800),
    "HTT Mapping": _ttl("masters", 1800),
    "Hub_Changes": _ttl("pipeline_params", 300),
    "Variables": _ttl("pipeline_params", 300),
    "Submission_Log": _ttl("npl_log", 300),
    "Hub level Suggestion": _ttl("dp_logics", 1800),
    "Launch_Output": _ttl("npl_log", 300),
}

WORKSHEET_TTL_BY_CATEGORY: dict[str, int] = {
    "demand_planning_masters": _ttl("masters", 1800),
    "pipeline_params": _ttl("pipeline_params", 300),
    "hub_level_planning": _ttl("dp_logics", 1800),
}


def _slug(*parts: str) -> str:
    raw = ":".join(str(p) for p in parts if p is not None)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def cache_path(
    spreadsheet_key: str,
    worksheet_name: str,
    range_notation: str = "",
) -> Path:
    name = worksheet_name.replace(" ", "_")
    return _cache_dir() / f"{_slug(spreadsheet_key, worksheet_name, range_notation)}_{name}.parquet"


def cache_path_for_category(
    sheet_category: str,
    worksheet_key: str,
    range_notation: str = "",
) -> Path:
    return _cache_dir() / f"{_slug(sheet_category, worksheet_key, range_notation)}_{worksheet_key}.parquet"


def ttl_for_worksheet(worksheet_name: str, sheet_category: str | None = None) -> int:
    if worksheet_name in DEFAULT_TTL_SECONDS:
        return DEFAULT_TTL_SECONDS[worksheet_name]
    if sheet_category and sheet_category in WORKSHEET_TTL_BY_CATEGORY:
        return WORKSHEET_TTL_BY_CATEGORY[sheet_category]
    return _ttl("default", 600)


def get_cached_df(path: Path, ttl_seconds: int) -> pd.DataFrame | None:
    if not path.exists():
        return None
    age = time.time() - path.stat().st_mtime
    if age > ttl_seconds:
        return None
    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def store_cached_df(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def raw_to_df(data: list) -> pd.DataFrame:
    if not data or len(data) < 2:
        return pd.DataFrame()
    return clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))
