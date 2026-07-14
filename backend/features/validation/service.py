"""Validation bootstrap and master validation orchestration."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.config import BASELINE_OUTPUTS_FOLDER, PROJECT_ROOT
from core.utils.dataframe import clean_sheet_df, sanitize_for_json

from features.validation.output_validation import find_latest_file

from features.validation.history import get_validation_history

from features.validation.input import INPUT_TYPES



MASTER_OPTIONS = [
    {"id": "product_hub_master", "label": "P-H Master (full rules)", "sheet": "product_hub_master"},
    {"id": "product_master", "label": "Product Master", "sheet": "product_master"},
    {"id": "hub_mapping", "label": "Hub Mapping", "sheet": "hub_mapping"},
    {"id": "hub_changes", "label": "Hub Changes", "sheet": "hub_changes"},
]


def _output_file_meta(folder: Path, pattern: str) -> dict[str, Any]:
    latest = find_latest_file(folder, pattern)
    if not latest:
        return {"available": False}
    stat = latest.stat()
    return {
        "available": True,
        "file": latest.name,
        "path": str(latest),
        "modified": stat.st_mtime,
        "size_bytes": stat.st_size,
    }


def get_validation_logics() -> dict[str, Any]:
    from features.validation.rules import (
        VALIDATION_VERSION,
        _EXCEL_ACTIVE_COLS,
        _EXCEL_CORE_COLS,
        _VALID_PLAN_DESIGNS,
    )

    return {
        "validation_version": VALIDATION_VERSION,
        "baseline_schema": [
            "city_name", "hub_name", "sub category", "SKU Class Prod", "day", "sugg_plan", "Base_Plan (qty)",
        ],
        "ph_core_columns": _EXCEL_CORE_COLS,
        "ph_active_columns": _EXCEL_ACTIVE_COLS,
        "valid_plan_designs": _VALID_PLAN_DESIGNS,
        "input_types": INPUT_TYPES,
        "master_options": MASTER_OPTIONS,
        "rules": [
            "P-H Master: non-blank core columns for active rows",
            "Plan Design must be one of allowed values",
            "Referential integrity: product_id in P Master, hub in Hub Master",
            "Baseline Summary: required columns + non-negative plan values",
            "Final Plan Hub_Dist: hub and product columns non-null",
            "Input uploads: Pandera schemas per data type",
        ],
    }


def get_validation_bootstrap(*, user_id: int) -> dict[str, Any]:
    return sanitize_for_json(
        {
            "logics": get_validation_logics(),
            "outputs": {
                "baseline": _output_file_meta(Path(BASELINE_OUTPUTS_FOLDER), "Summary_*.xlsx"),
                "final_plan": _output_file_meta(Path(PROJECT_ROOT), "Hub_Dist_Wk*.xlsx"),
            },
            "history_count": len(get_validation_history(user_id=user_id, limit=100)),
        }
    )


def _load_master_sheet(sheet_key: str) -> pd.DataFrame:
    from core.shared.sheets_session import get_sheets_manager


    gsm = get_sheets_manager()
    if sheet_key == "hub_changes":
        raw = gsm.read_worksheet_uncached("hub_level_planning", "hub_changes")
        if raw is None:
            return pd.DataFrame()
        clean_sheet_df(raw)
        return raw

    range_map = {
        "product_master": "A:K",
        "product_hub_master": "A:AX",
        "hub_mapping": "A:F",
    }
    rng = range_map.get(sheet_key, "A:Z")
    df = gsm.read_worksheet_to_df("demand_planning_masters", sheet_key, rng)
    if df is None:
        return pd.DataFrame()
    clean_sheet_df(df)
    return df


def validate_master_by_id(master_id: str) -> dict[str, Any]:
    from features.validation.rules import VALIDATION_VERSION
    from features.validation.runner import run_master_data_validations
    from features.validation.input import validate_input_dataframe


    opt = next((m for m in MASTER_OPTIONS if m["id"] == master_id), None)
    if not opt:
        raise ValueError(f"Unknown master: {master_id}")

    if master_id == "product_hub_master":
        p_df = _load_master_sheet("product_master")
        ph_df = _load_master_sheet("product_hub_master")
        hub_df = _load_master_sheet("hub_mapping")
        errors = run_master_data_validations(ph_df, p_df, hub_df)
        err_msgs = [f"{e.get('rule', 'rule')}: {e.get('message', e)}" for e in errors]
        return {
            "master_id": master_id,
            "validation_version": VALIDATION_VERSION,
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "errors": err_msgs[:200],
            "warnings": [],
            "stats": {
                "ph_rows": len(ph_df),
                "product_rows": len(p_df),
                "hub_rows": len(hub_df),
                "duplicates": int(ph_df.duplicated().sum()) if not ph_df.empty else 0,
                "missing_values": int(ph_df.isna().sum().sum()) if not ph_df.empty else 0,
            },
        }

    df = _load_master_sheet(opt["sheet"])
    if master_id == "hub_changes":
        result = validate_input_dataframe(df, "hub_changes")
        return {
            "master_id": master_id,
            "validation_version": VALIDATION_VERSION,
            "valid": result["valid"],
            "error_count": len(result.get("errors", [])),
            "errors": result.get("errors", []),
            "warnings": result.get("warnings", []),
            "stats": _df_stats(df),
        }

    errors: list[str] = []
    if df.empty:
        errors.append("DataFrame is empty — sync masters first")
    else:
        if "product_id" in df.columns and df["product_id"].isna().any():
            errors.append(f"Found {int(df['product_id'].isna().sum())} null product_id values")
        if "hub_name" in df.columns and df["hub_name"].isna().any():
            errors.append(f"Found {int(df['hub_name'].isna().sum())} null hub_name values")

    return {
        "master_id": master_id,
        "validation_version": VALIDATION_VERSION,
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors,
        "warnings": [],
        "stats": _df_stats(df),
    }


def _df_stats(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {"rows": 0, "columns": 0, "duplicates": 0, "missing_values": 0}
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "duplicates": int(df.duplicated().sum()),
        "missing_values": int(df.isna().sum().sum()),
    }
