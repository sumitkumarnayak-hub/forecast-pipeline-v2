"""
Logical object keys for pipeline artifacts.

Keys are backend-neutral (used in Supabase bucket, future Drive, etc.).
`resolve_local_path` maps a key to the on-disk path from .env (unchanged for local mode).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator


def _cfg():
    from planning_suite import config as cfg

    return cfg


def registered_artifacts() -> list[tuple[str, str]]:
    """All logical keys and target local paths (file may not exist yet)."""
    cfg = _cfg()
    from planning_suite.services.baseline_manual import DP_LOGICS_WORKSHEETS

    specs: list[tuple[str, str]] = [
        ("masters/Product_Masters.xlsx", str(Path(cfg.FF_MASTERS_XLSX).resolve())),
    ]

    for ws in DP_LOGICS_WORKSHEETS:
        specs.append((f"dp_logics/{ws}.xlsx", str((Path(cfg.DP_LOGICS_FOLDER) / f"{ws}.xlsx").resolve())))
        specs.append((f"dp_logics/{ws}.parquet", str((Path(cfg.DP_LOGICS_FOLDER) / f"{ws}.parquet").resolve())))

    for name in (
        "active_dataset.parquet",
        "active_dataset_meta.json",
        "rds_cache.parquet",
        "prev_baseline_latest.parquet",
        "hub_suggestion_latest.parquet",
        "baseline_approval.json",
    ):
        specs.append((f"outputs/{name}", str((Path(cfg.OUTPUT_PATH) / name).resolve())))

    raw_dir = Path(cfg.RAW_ACTUALS_FOLDER)
    if raw_dir.is_dir():
        for f in sorted(raw_dir.glob("*.parquet")):
            specs.append((f"raw_actuals/{f.name}", str(f.resolve())))

    out_dir = Path(cfg.BASELINE_OUTPUTS_FOLDER)
    if out_dir.is_dir():
        for f in sorted(out_dir.glob("Summary_*.xlsx")):
            specs.append((f"baseline_outputs/{f.name}", str(f.resolve())))

    ff = Path(cfg.FF_INPUTS_FOLDER)
    for name in (
        "Festive.xlsx",
        "Adhoc_Adjustment.xlsx",
        "Adhoc_Adjustment_City_Product.xlsx",
        "Adhoc_Adjustment_Hub.xlsx",
        "City_Mapping.xlsx",
    ):
        specs.append((f"ff_inputs/{name}", str((ff / name).resolve())))

    inv = Path(cfg.FF_INV_LOGIC_FOLDER)
    if inv.is_dir():
        for f in sorted(inv.glob("*.xlsx")):
            specs.append((f"inv_logic/{f.name}", str(f.resolve())))

    if cfg.RDS_6W_PATH:
        specs.append(("analytics/6w_v3.rds", str(Path(cfg.RDS_6W_PATH).resolve())))

    return specs


def iter_artifact_specs() -> list[tuple[str, str]]:
    """Return (object_key, local_path) for files that exist on disk."""
    return [(k, p) for k, p in registered_artifacts() if Path(p).is_file()]


def iter_artifact_keys() -> list[str]:
    return [k for k, _ in registered_artifacts()]


def artifact_local_paths() -> dict[str, str]:
    return dict(registered_artifacts())


def resolve_local_path(key: str) -> Path:
    """Map logical key → canonical local path (from env layout)."""
    cfg = _cfg()
    key = key.lstrip("/").replace("\\", "/")

    if key == "masters/Product_Masters.xlsx":
        return Path(cfg.FF_MASTERS_XLSX)

    if key.startswith("dp_logics/"):
        name = key.split("/", 1)[1]
        return Path(cfg.DP_LOGICS_FOLDER) / name

    if key.startswith("outputs/"):
        name = key.split("/", 1)[1]
        return Path(cfg.OUTPUT_PATH) / name

    if key.startswith("raw_actuals/"):
        name = key.split("/", 1)[1]
        return Path(cfg.RAW_ACTUALS_FOLDER) / name

    if key.startswith("baseline_outputs/"):
        name = key.split("/", 1)[1]
        return Path(cfg.BASELINE_OUTPUTS_FOLDER) / name

    if key.startswith("ff_inputs/"):
        name = key.split("/", 1)[1]
        return Path(cfg.FF_INPUTS_FOLDER) / name

    if key.startswith("inv_logic/"):
        name = key.split("/", 1)[1]
        return Path(cfg.FF_INV_LOGIC_FOLDER) / name

    if key == "analytics/6w_v3.rds":
        return Path(cfg.RDS_6W_PATH)

    return Path(cfg.OUTPUT_PATH) / key.replace("/", os.sep)
