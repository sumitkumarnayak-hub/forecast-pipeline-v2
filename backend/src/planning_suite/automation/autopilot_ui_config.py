"""Static Auto-Pilot UI config — no Streamlit / OptimizedBaselineGenerator import."""
from __future__ import annotations

import os

from planning_suite import config as cfg

AUTOPILOT_STEPS_UI: list[dict[str, str]] = [
    {
        "name": "Step 1: Master Data Sync & Validation",
        "desc": "Read Google Sheets masters, run Polars validation, export to Product_Masters.xlsx.",
        "icon": "clipboard",
    },
    {
        "name": "Step 2: New Product Launch (P-H Master)",
        "desc": "Auto-discover new products in P Master and append P-H Master rows for all active hubs.",
        "icon": "rocket",
    },
    {
        "name": "Step 3: Pull Raw Data",
        "desc": "Fetch the latest week of raw actuals from RDS cache and update the active Parquet dataset.",
        "icon": "download",
    },
    {
        "name": "Step 4: Sync Config Parameters",
        "desc": "Sync DP Logics worksheets (City_Cat, STF, Percentile, Avl_Flag, etc.) to local Excel.",
        "icon": "settings",
    },
    {
        "name": "Step 5: Run Baseline Engine",
        "desc": "Execute optimized_baseline_avail_correction.py on the active dataset.",
        "icon": "calculator",
    },
    {
        "name": "Step 6: Email Notification",
        "desc": "Send success notification when all prior steps complete.",
        "icon": "mail",
    },
]


def output_paths_reference() -> list[dict[str, str]]:
    return [
        {"step": "Step 1", "label": "Product Masters Excel", "path": cfg.FF_MASTERS_XLSX},
        {"step": "Step 2", "label": "P-H Master (new products)", "path": cfg.DEMAND_PLANNING_MASTERS_SHEET_URL},
        {"step": "Step 3", "label": "Raw actuals folder", "path": cfg.RAW_ACTUALS_FOLDER},
        {
            "step": "Step 3",
            "label": "Active dataset",
            "path": os.path.abspath(os.path.join("outputs", "active_dataset.parquet")),
        },
        {"step": "Step 4", "label": "DP Logics folder", "path": cfg.DP_LOGICS_FOLDER},
        {"step": "Step 5", "label": "Baseline outputs folder", "path": cfg.BASELINE_OUTPUTS_FOLDER},
        {"step": "Step 5", "label": "Hub level Suggestion", "path": cfg.DP_LOGICS_SHEET_URL},
        {"step": "Step 5", "label": "Validation sheet", "path": cfg.VALIDATION_SHEET_URL},
    ]
