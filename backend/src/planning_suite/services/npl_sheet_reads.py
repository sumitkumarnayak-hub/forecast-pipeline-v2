"""Parquet-cached Google Sheet reads for Product Launch (avoids repeated gspread calls)."""
from __future__ import annotations

from planning_suite.services import sheets_cache


def invalidate_npl_sheet_cache(
    spreadsheet_id: str,
    sheet_name: str,
    range_notation: str = "",
) -> None:
    path = sheets_cache.cache_path(spreadsheet_id, sheet_name, range_notation)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass


def read_sheet_values_cached(
    spreadsheet_id: str,
    sheet_name: str,
    range_notation: str,
    *,
    sheet_category: str | None = None,
    fetcher,
) -> list[list[str]]:
    """Return raw A1 grid values; ``fetcher`` is a zero-arg callable returning list[list[str]]."""
    path = sheets_cache.cache_path(spreadsheet_id, sheet_name, range_notation)
    ttl = sheets_cache.ttl_for_worksheet(sheet_name, sheet_category)
    cached = sheets_cache.get_cached_df(path, ttl)
    if cached is not None and "_sheet_values_json" in cached.columns:
        import json

        try:
            return json.loads(str(cached["_sheet_values_json"].iloc[0]))
        except Exception:
            pass

    data = fetcher() or []
    import json
    import pandas as pd

    sheets_cache.store_cached_df(
        path,
        pd.DataFrame({"_sheet_values_json": [json.dumps(data)]}),
    )
    return data
