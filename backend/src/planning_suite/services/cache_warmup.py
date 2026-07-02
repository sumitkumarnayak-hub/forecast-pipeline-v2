"""Background cache warm-up on API startup (NPL Google Sheets → parquet)."""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


def start_cache_warmup() -> None:
    """Pre-load NPL sheet caches in a daemon thread so first user request is fast."""
    if os.getenv("DISABLE_CACHE_WARMUP", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Cache warm-up disabled (DISABLE_CACHE_WARMUP)")
        return

    delay = max(0, int(os.getenv("CACHE_WARMUP_DELAY_SECONDS", "30")))

    def _warm() -> None:
        try:
            if delay:
                logger.info("NPL cache warm-up scheduled in %ss (API requests get priority)", delay)
                time.sleep(delay)
            logger.info("Starting background NPL sheet cache warm-up")
            from planning_suite.features.new_product_launch import (
                load_log,
                load_product_master,
                load_salience_source,
            )

            load_product_master()
            load_log()
            load_salience_source()
            logger.info("NPL sheet cache warm-up complete")
        except Exception as exc:
            logger.warning("NPL sheet cache warm-up failed: %s", exc)

    threading.Thread(target=_warm, daemon=True, name="npl-cache-warmup").start()
