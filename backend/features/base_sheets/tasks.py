import logging
from typing import Dict, Any
from features.base_sheets import service

logger = logging.getLogger(__name__)


def handle_base_sheets_sync(payload: Dict[str, Any]) -> None:
    """
    Queue handler for base sheets synchronization to Drive.
    """
    sheet_key = payload["sheet_key"]
    user_id = payload["user_id"]
    logger.info("Background queue syncing base sheet: %s for user: %s", sheet_key, user_id)
    service.sync_sheet_to_parquet(sheet_key, user_id=user_id)


def register_base_sheets_tasks(worker) -> None:
    """
    Registers base sheets tasks with the queue worker.
    """
    worker.register("base_sheets.sync", handle_base_sheets_sync)
