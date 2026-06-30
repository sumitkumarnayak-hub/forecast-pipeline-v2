"""Apply admin demo city/hub filters to active_dataset before baseline runs."""
from __future__ import annotations

import copy
import os
from typing import Any

import pandas as pd

from planning_suite.services.demo_filter_store import DemoFilterState, demo_filter_active


def prepare_demo_filter_dataset(
    base_env: dict[str, Any],
    *,
    demo_city: str = "All Cities",
    demo_hubs: list[str] | None = None,
) -> tuple[str, dict[str, Any], str | None, dict[str, Any]]:
    """
    Returns (active_dataset_path, updated_env, error_message, info_dict).
    """
    _env = copy.copy(base_env)
    _demo_city_run = demo_city or "All Cities"
    _demo_hubs_run = demo_hubs or []
    _base_ds = os.path.abspath(os.path.join("outputs", "active_dataset.parquet"))
    _active_ds = _base_ds
    info: dict[str, Any] = {"active": False, "rows": None, "description": ""}

    if not demo_filter_active(DemoFilterState(city=_demo_city_run, hubs=_demo_hubs_run)):
        return _active_ds, _env, None, info

    info["active"] = True
    info["city"] = _demo_city_run
    info["hubs"] = _demo_hubs_run

    try:
        _full_df = pd.read_parquet(_base_ds)
        _filtered_df = _full_df.copy()

        if _demo_city_run and _demo_city_run != "All Cities":
            if "city_name" not in _filtered_df.columns:
                info["city_skipped"] = True
            else:
                _filtered_df = _filtered_df[
                    _filtered_df["city_name"] == _demo_city_run
                ].reset_index(drop=True)
                if _filtered_df.empty:
                    _cities = sorted(_full_df["city_name"].unique().tolist())
                    return _active_ds, _env, (
                        f"No rows for city {_demo_city_run}. Available cities: {_cities}"
                    ), info
                _env["BASELINE_DEMO_CITY"] = _demo_city_run

        if _demo_hubs_run:
            if "hub_name" not in _filtered_df.columns:
                info["hub_skipped"] = True
            else:
                _pre_hub_count = len(_filtered_df)
                _filtered_df = _filtered_df[
                    _filtered_df["hub_name"].isin(_demo_hubs_run)
                ].reset_index(drop=True)
                if _filtered_df.empty:
                    _avail_hubs = sorted(_full_df["hub_name"].unique().tolist())
                    return _active_ds, _env, (
                        f"No rows for selected hub(s) {_demo_hubs_run} "
                        f"(after city filter). Available hubs: {_avail_hubs}"
                    ), info
                info["hub_filter"] = f"{_pre_hub_count:,} → {len(_filtered_df):,} rows"

        _city_part = (
            _demo_city_run.replace(" ", "_")
            if _demo_city_run != "All Cities" else "AllCities"
        )
        _hub_part = (
            "_".join(sorted(_demo_hubs_run))[:50] if _demo_hubs_run else "AllHubs"
        )
        _demo_ds = os.path.abspath(
            os.path.join("outputs", f"active_dataset_demo_{_city_part}_{_hub_part}.parquet")
        )
        _filtered_df.to_parquet(_demo_ds, index=False)
        _active_ds = _demo_ds

        _filter_desc = _demo_city_run if _demo_city_run != "All Cities" else "All Cities"
        if _demo_hubs_run:
            _filter_desc += f" · {len(_demo_hubs_run)} hub(s)"
        info["rows"] = len(_filtered_df)
        info["description"] = _filter_desc
        info["dataset_path"] = _demo_ds
    except Exception as exc:
        info["error"] = str(exc)
        return _active_ds, _env, f"Could not apply demo filter: {exc}", info

    return _active_ds, _env, None, info
