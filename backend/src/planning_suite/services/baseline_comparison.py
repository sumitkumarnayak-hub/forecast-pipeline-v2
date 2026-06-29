"""Helpers for baseline review / previous-vs-current comparison."""
from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import polars as pl

from planning_suite.config import BASELINE_OUTPUTS_FOLDER, DP_LOGICS_FOLDER, DP_LOGICS_SHEET_URL, PROJECT_ROOT

HUB_LOG_PREFIX = "Hub_level_Suggestion_log_"
HUB_SHEET_TAB = "Hub level Suggestion"
SUMMARY_PREFIX = "Summary_"
_XLSX_PK = b"PK\x03\x04"
_MIN_XLSX_BYTES = 512

DAY_COLUMN_ALIASES = [
    "day_x", "day_y", "day", "day_name", "Day_name",
    "delivery_day", "order_day", "weekday", "week_day", "day_of_week", "dow",
]
CURRENT_VALUE_ALIASES = ["Final_Plan", "final_plan", "base_plan", "Base_plan", "forecast", "plan"]
PREVIOUS_VALUE_ALIASES = ["Base_plan", "base_plan", "base plan", "BasePlan"]
HUB_ALIASES = ["hub_name", "hub"]
SKU_ALIASES = ["SKU Class Prod", "sku class prod", "sku_class_prod", "category"]
CITY_ALIASES = ["city_name", "city"]


def is_valid_xlsx_file(path: str | Path) -> bool:
    """Reject empty, truncated, or non-zip files masquerading as .xlsx."""
    p = Path(path)
    if not p.is_file():
        return False
    if p.stat().st_size < _MIN_XLSX_BYTES:
        return False
    try:
        with p.open("rb") as fh:
            return fh.read(4) == _XLSX_PK
    except OSError:
        return False


def list_matching_files_newest_first(
    directory: str | Path,
    prefix: str,
    *,
    suffix: str = ".xlsx",
) -> list[Path]:
    folder = Path(directory)
    if not folder.is_dir():
        return []
    files = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.name.startswith(prefix) and p.name.endswith(suffix)
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def list_matching_files_across_dirs(
    directories: list[Path],
    prefix: str,
    *,
    suffix: str = ".xlsx",
) -> list[Path]:
    seen: set[str] = set()
    files: list[Path] = []
    for folder in directories:
        for path in list_matching_files_newest_first(folder, prefix, suffix=suffix):
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                files.append(path)
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def hub_log_search_dirs(primary_folder: str | Path | None = None) -> list[Path]:
    """Directories that may contain Hub_level_Suggestion_log_*.xlsx exports."""
    candidates = [
        primary_folder,
        DP_LOGICS_FOLDER,
        PROJECT_ROOT / "outputs" / "dp_logics",
        PROJECT_ROOT / "data" / "dp_logics",
    ]
    seen: set[str] = set()
    dirs: list[Path] = []
    for item in candidates:
        if not item:
            continue
        path = Path(item).resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.is_dir():
            dirs.append(path)
    return dirs


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Case-insensitive column lookup."""
    lower_candidates = [c.lower() for c in candidates]
    for col in df.columns:
        if str(col).strip().lower() in lower_candidates:
            return col
    return None


def _parquet_cache_path(xlsx_path: Path, cache_dir: Path) -> Path:
    safe = xlsx_path.name.replace(" ", "_")
    return cache_dir / f"{safe}.parquet"


def load_workbook_with_cache(
    xlsx_path: str | Path,
    cache_dir: str | Path,
    *,
    preloaded: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Load an Excel workbook using a parquet side-cache when the source file is valid.
    Skips corrupt xlsx (BadZipFile) so callers can try the next candidate file.
    """
    path = Path(xlsx_path)
    cache_root = Path(cache_dir)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_path = _parquet_cache_path(path, cache_root)

    if preloaded is not None:
        df = preloaded.copy()
    elif cache_path.exists() and path.exists() and cache_path.stat().st_mtime >= path.stat().st_mtime:
        df = pd.read_parquet(cache_path)
    else:
        if not is_valid_xlsx_file(path):
            raise zipfile.BadZipFile(f"Not a valid Excel file: {path.name}")
        df = pd.read_excel(path)
        df.columns = [str(c).strip() for c in df.columns]
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str)
        try:
            df.to_parquet(cache_path, index=False)
        except Exception:
            pass
        return df

    df.columns = [str(c).strip() for c in df.columns]
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str)
    try:
        df.to_parquet(cache_path, index=False)
    except Exception:
        pass
    return df


def _try_load_candidates(
    candidates: list[Path],
    cache_dir: Path,
    *,
    label: str,
) -> tuple[pd.DataFrame, str, str]:
    errors: list[str] = []
    for path in candidates:
        if not is_valid_xlsx_file(path):
            errors.append(f"{path.name}: not a valid .xlsx (skipped)")
            continue
        try:
            df = load_workbook_with_cache(path, cache_dir)
            return df, path.name, str(path)
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
            continue
    detail = "; ".join(errors[:5])
    raise FileNotFoundError(f"No readable {label} file found. Attempts: {detail}")


def resolve_latest_summary(
    summary_folder: str | Path | None = None,
    *,
    cache_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, str, str]:
    """Load newest readable Summary_*.xlsx baseline output."""
    folder = Path(summary_folder or BASELINE_OUTPUTS_FOLDER)
    cache_root = Path(cache_dir or PROJECT_ROOT / "outputs" / "cmp_cache")
    candidates = list_matching_files_newest_first(folder, SUMMARY_PREFIX)
    if not candidates:
        raise FileNotFoundError(
            f"No {SUMMARY_PREFIX}*.xlsx found in {folder}. Run the baseline engine first."
        )
    return _try_load_candidates(candidates, cache_root, label="Summary")


def _load_hub_sheet_from_google(sheets_manager) -> pd.DataFrame:
    spreadsheet = sheets_manager.gc.open_by_url(DP_LOGICS_SHEET_URL)
    worksheet = spreadsheet.worksheet(HUB_SHEET_TAB)
    values = worksheet.get_all_values()
    if len(values) < 2:
        raise ValueError(f"'{HUB_SHEET_TAB}' worksheet is empty.")
    df = pd.DataFrame(values[1:], columns=values[0])
    df.columns = [str(c).strip() for c in df.columns]
    return df


def resolve_hub_suggestion_previous(
    *,
    log_folder: str | Path | None = None,
    sheets_manager=None,
    cache_snapshot: bool = True,
    cache_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, str, str | None]:
    """
    Load previous hub-level baseline for comparison.

    Resolution order (same intent as the original baseline script):
      1. Newest readable local ``Hub_level_Suggestion_log_*.xlsx``
      2. Live ``Hub level Suggestion`` Google Sheet snapshot (cached locally when missing log)
    """
    log_folder = Path(log_folder or DP_LOGICS_FOLDER)
    cache_root = Path(cache_dir or PROJECT_ROOT / "outputs" / "cmp_cache")
    candidates = list_matching_files_across_dirs(
        hub_log_search_dirs(log_folder),
        HUB_LOG_PREFIX,
    )
    if candidates:
        try:
            df, name, path = _try_load_candidates(candidates, cache_root, label="Hub log")
            return df, f"Hub log file: {name}", path
        except FileNotFoundError:
            pass

    if sheets_manager is None:
        from planning_suite.services.google_sheets import GoogleSheetsManager

        sheets_manager = GoogleSheetsManager()

    df = _load_hub_sheet_from_google(sheets_manager)
    source = f"Google Sheet tab: {HUB_SHEET_TAB}"
    cached_path: str | None = None
    if cache_snapshot:
        log_folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cached_path = str(log_folder / f"{HUB_LOG_PREFIX}{stamp}.xlsx")
        df.to_excel(cached_path, index=False)
        source = f"{source} (cached to {Path(cached_path).name})"
    return df, source, cached_path


def _aggregate_keys_pl(
    df: pd.DataFrame,
    key_cols: list[str | None],
    value_col: str,
    value_name: str,
    rename_map: dict[str, str],
) -> pl.DataFrame:
    """Group-by sum on string-normalised keys (same maths as pandas review flow)."""
    valid_pairs = [(src, rename_map[src]) for src in key_cols if src]
    if not valid_pairs:
        raise ValueError(f"No key columns resolved for aggregation → {value_name}")
    src_keys = [src for src, _ in valid_pairs]
    out_keys = [dst for _, dst in valid_pairs]

    exprs = [
        pl.col(src).cast(pl.Utf8).str.strip_chars().alias(dst)
        for src, dst in valid_pairs
    ]
    exprs.append(
        pl.col(value_col).cast(pl.Float64, strict=False).fill_null(0).alias(value_name)
    )
    return (
        pl.from_pandas(df)
        .select(exprs)
        .group_by(out_keys)
        .agg(pl.col(value_name).sum())
    )


def build_hub_sku_day_comparison(
    sum_df: pd.DataFrame,
    log_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Hub × SKU Class Prod × Day comparison (Previous vs Current).

    Same structure and maths as the original Streamlit review_baseline flow.
    """
    s_hub = find_column(sum_df, HUB_ALIASES)
    s_sku = find_column(sum_df, SKU_ALIASES)
    s_day = find_column(sum_df, DAY_COLUMN_ALIASES)
    s_fp = find_column(sum_df, CURRENT_VALUE_ALIASES)
    l_hub = find_column(log_df, HUB_ALIASES)
    l_sku = find_column(log_df, ["sku class prod", *SKU_ALIASES])
    l_day = find_column(log_df, DAY_COLUMN_ALIASES)
    l_bp = find_column(log_df, PREVIOUS_VALUE_ALIASES)

    if not all([s_hub, s_sku, s_day, s_fp]):
        missing = [n for n, v in [
            ("hub_name", s_hub), ("SKU Class Prod", s_sku), ("day", s_day), ("Final_Plan", s_fp),
        ] if not v]
        raise ValueError(f"Summary file missing columns: {missing}")
    if not all([l_hub, l_sku, l_day, l_bp]):
        raise ValueError(f"Hub log file missing columns. Available: {log_df.columns.tolist()}")

    rename = {s_hub: "Hub", s_sku: "SKU Class Prod", s_day: "Day"}
    curr = _aggregate_keys_pl(sum_df, [s_hub, s_sku, s_day], s_fp, "Current Baseline", rename)
    prev = _aggregate_keys_pl(
        log_df, [l_hub, l_sku, l_day], l_bp, "Previous Baseline",
        {l_hub: "Hub", l_sku: "SKU Class Prod", l_day: "Day"},
    )

    cmp_pl = (
        prev.join(curr, on=["Hub", "SKU Class Prod", "Day"], how="full", coalesce=True)
        .with_columns([
            pl.col("Previous Baseline").fill_null(0).round(0).cast(pl.Int64),
            pl.col("Current Baseline").fill_null(0).round(0).cast(pl.Int64),
        ])
        .with_columns(
            pl.when(pl.col("Previous Baseline") != 0)
            .then(
                ((pl.col("Current Baseline") - pl.col("Previous Baseline"))
                 / pl.col("Previous Baseline") * 100).round(1)
            )
            .otherwise(None)
            .alias("Delta %")
        )
        .sort(["Hub", "SKU Class Prod", "Day"])
    )
    return cmp_pl.to_pandas()


def build_comparison_view(
    curr_df: pd.DataFrame,
    prev_df: pd.DataFrame,
    curr_val: str,
    prev_val: str,
    curr_keys: list[str | None],
    prev_keys: list[str | None],
    display_names: list[str],
) -> pd.DataFrame | None:
    """Multi-level comparison view — same maths as original _rv_build_view."""
    valid_curr = [(k, n) for k, n in zip(curr_keys, display_names) if k]
    valid_prev = [(k, n) for k, n in zip(prev_keys, display_names) if k]
    if not valid_curr or not valid_prev:
        return None

    curr_rename = {src: dst for src, dst in valid_curr}
    prev_rename = {src: dst for src, dst in valid_prev}
    out_keys = [dst for _, dst in valid_curr]

    curr = _aggregate_keys_pl(
        curr_df, [k for k, _ in valid_curr], curr_val, "Current Baseline", curr_rename
    )
    prev = _aggregate_keys_pl(
        prev_df, [k for k, _ in valid_prev], prev_val, "Previous Baseline", prev_rename
    )

    merged = (
        prev.join(curr, on=out_keys, how="full", coalesce=True)
        .with_columns([
            pl.col("Previous Baseline").fill_null(0).round(0).cast(pl.Int64),
            pl.col("Current Baseline").fill_null(0).round(0).cast(pl.Int64),
        ])
        .with_columns(
            (pl.col("Current Baseline") - pl.col("Previous Baseline")).alias("Delta"),
        )
        .with_columns(
            pl.when(pl.col("Previous Baseline") != 0)
            .then(
                ((pl.col("Current Baseline") - pl.col("Previous Baseline"))
                 / pl.col("Previous Baseline") * 100).round(1)
            )
            .otherwise(None)
            .alias("Delta %")
        )
    )
    return merged.to_pandas()
