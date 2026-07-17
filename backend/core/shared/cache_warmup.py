"""Background cache warm-up on API startup (NPL Google Sheets → parquet)."""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)


def start_cache_warmup() -> None:
    """Pre-load FF Automation master caches in a daemon thread so first user request is fast."""
    if os.getenv("DISABLE_CACHE_WARMUP", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("Cache warm-up disabled (DISABLE_CACHE_WARMUP)")
        return

    delay = max(0, int(os.getenv("CACHE_WARMUP_DELAY_SECONDS", "2")))

    def _warm() -> None:
        try:
            if delay:
                logger.info("Cache warm-up scheduled in %ss (API requests get priority)", delay)
                time.sleep(delay)
            logger.info("Starting background FF Automation sheet cache warm-up")

            from features.product_launch.core import (
                load_log,
                load_product_master,
                load_salience_source,
                get_categories,
                get_cities_from_salience,
                get_earliest_monday,
            )
            from features.product_launch.ff_masters import (
                load_hub_mapping_df,
                load_ph_master_df,
                SPREADSHEET_KEY,
                HUB_MAPPING_TAB,
                HUB_MAPPING_RANGE,
                PH_MASTER_TAB,
                PH_MASTER_RANGE,
            )
            from core.shared.google_sheets import GoogleSheetsManager

            master = load_product_master()
            load_log()
            sal = load_salience_source()
            load_hub_mapping_df()
            try:
                load_ph_master_df()
            except Exception as ph_exc:
                logger.debug("P-H Master warm-up skipped: %s", ph_exc)

            try:
                from core.shared.api_cache import CacheNS, cache_set
                from core.utils.dataframe import sanitize_for_json

                categories = get_categories(master)
                cities = get_cities_from_salience(sal)

                pid_col = next((c for c in ["Product id", "Product ID", "product_id"] if c in master.columns), None)
                name_col = next((c for c in ["Product Name", "product_name", "Anchor Name"] if c in master.columns), None)
                cat_col = next((c for c in ["sub_category", "Sub-category", "Sub category", "category"] if c in master.columns), None)

                products = []
                if pid_col:
                    for _, row in master.iterrows():
                        pid = str(row.get(pid_col, "")).strip()
                        if not pid:
                            continue
                        products.append({
                            "product_id": pid,
                            "product_name": str(row.get(name_col, "")).strip() if name_col else "",
                            "category": str(row.get(cat_col, "")).strip() if cat_col else "",
                        })
                    products = sorted(products, key=lambda r: r["product_id"])

                payload = {
                    "categories": categories,
                    "cities": cities,
                    "earliest_launch_date": str(get_earliest_monday()),
                    "products": products,
                }
                cache_set(
                    CacheNS.NPL_WIZARD,
                    "combined_bootstrap_v3",
                    sanitize_for_json(payload),
                    ttl=1800.0,
                )
                logger.info("Background cache warm-up populated combined_bootstrap_v3 API cache successfully")
            except Exception as ex:
                logger.warning("Background cache warm-up failed to pre-warm combined_bootstrap_v3 API cache: %s", ex)

            logger.info("FF Automation Product Launch sheet cache warm-up complete")
        except Exception as exc:
            logger.warning("Sheet cache warm-up failed: %s", exc)

    threading.Thread(target=_warm, daemon=True, name="npl-cache-warmup").start()
