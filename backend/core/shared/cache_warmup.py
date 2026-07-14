"""Background cache warm-up on API startup (NPL Google Sheets → parquet)."""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


def start_cache_warmup() -> None:
    """Pre-load NPL and Hub Launch sheet caches in a daemon thread so first user request is fast."""
    if os.getenv("DISABLE_CACHE_WARMUP", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Cache warm-up disabled (DISABLE_CACHE_WARMUP)")
        return

    # Use a small startup delay (e.g. 5 seconds) in production to warm up caches immediately
    delay = max(0, int(os.getenv("CACHE_WARMUP_DELAY_SECONDS", "5")))

    def _warm() -> None:
        try:
            if delay:
                logger.info("Cache warm-up scheduled in %ss (API requests get priority)", delay)
                time.sleep(delay)
            logger.info("Starting background NPL & Hub Launch sheet cache warm-up")
            
            # 1. Warm up NPL worksheets
            from features.product_launch.core import (
                load_log,
                load_product_master,
                load_salience_source,
            )
            load_product_master()
            load_log()
            load_salience_source()
            
            # 2. Warm up Hub Launch worksheets
            from core.shared.google_sheets import GoogleSheetsManager

            from features.final_plan.hub_sync import HUB_MASTER_READ_RANGE, PH_MASTER_READ_RANGE

            sheets = GoogleSheetsManager()
            
            # Pre-warm hub mapping sheets cache
            sheets.read_worksheet_uncached("demand_planning_masters", "hub_mapping", HUB_MASTER_READ_RANGE, use_cache=True)
            # Pre-warm heavy P-H master sheets cache
            sheets.read_worksheet_uncached("demand_planning_masters", "product_hub_master", PH_MASTER_READ_RANGE, use_cache=True)
            # Pre-warm FF input configurations cache
            sheets.read_worksheet_uncached("new_hub_launch", "ff_input", "A:H", use_cache=True)

            logger.info("NPL & Hub Launch sheet cache warm-up complete")
        except Exception as exc:
            logger.warning("Sheet cache warm-up failed: %s", exc)

    threading.Thread(target=_warm, daemon=True, name="npl-cache-warmup").start()
