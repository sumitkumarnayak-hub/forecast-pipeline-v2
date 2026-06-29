"""Transparent Excel-to-Parquet caching utility for high-performance calculations."""
from __future__ import annotations

import os
from pathlib import Path
import pandas as pd
import polars as pl


def get_parquet_cache(source_excel_path: str | Path, sheet_name: str | int = 0) -> pd.DataFrame:
    """
    Load an Excel file into a pandas DataFrame.
    If a cached Parquet version exists and is newer than the Excel file, it reads the Parquet file.
    Otherwise, it reads the Excel file, caches it to Parquet, and returns the DataFrame.
    """
    src_path = Path(source_excel_path)
    if not src_path.exists():
        raise FileNotFoundError(f"Source file not found: {src_path}")

    # Define cache directory inside outputs/cache
    cache_dir = Path("outputs/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    clean_sheet_name = str(sheet_name).replace(" ", "_").lower()
    cache_file = cache_dir / f"{src_path.stem}_{clean_sheet_name}.parquet"

    # Rebuild cache if cache file does not exist, or is older than the source file
    rebuild = True
    if cache_file.exists():
        src_mtime = src_path.stat().st_mtime
        cache_mtime = cache_file.stat().st_mtime
        if cache_mtime > src_mtime:
            rebuild = False

    if rebuild:
        # Load from Excel
        df = pd.read_excel(src_path, sheet_name=sheet_name)

        # Sanitize object columns for Parquet serialization compatibility
        df_for_parquet = df.copy()
        for col in df_for_parquet.columns:
            if df_for_parquet[col].dtype == object:
                # Fill null values and convert to string to avoid serialization errors
                df_for_parquet[col] = df_for_parquet[col].astype(str).str.strip()
                df_for_parquet[col] = df_for_parquet[col].replace({"nan": "", "None": ""})

        # Save to Parquet
        df_for_parquet.to_parquet(cache_file, index=False)
        return df
    else:
        # Load from cached Parquet file instantly
        return pd.read_parquet(cache_file)


def get_polars_cache(source_excel_path: str | Path, sheet_name: str | int = 0) -> pl.DataFrame:
    """
    Load an Excel file directly into a Polars DataFrame using the Parquet cache.
    """
    df_pd = get_parquet_cache(source_excel_path, sheet_name)
    return pl.from_pandas(df_pd)
