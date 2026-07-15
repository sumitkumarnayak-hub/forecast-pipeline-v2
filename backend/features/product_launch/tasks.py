import logging
from typing import Dict, Any

from core.database.engine import SessionLocal
from core.shared.workflow_notifications import notify_npl_submitted
# Note: In the future, we can import Google Sheets sync methods here as well.
# from core.shared.google_sheets import ...

logger = logging.getLogger(__name__)

def handle_npl_email(payload: Dict[str, Any]):
    """
    Queue handler for sending NPL submission emails.
    """
    logger.info(f"Processing email for NPL submission: {payload.get('sub_id')}")
    # Re-establish DB session if needed by the mailer
    with SessionLocal() as db:
        notify_npl_submitted(
            sub_id=payload.get("sub_id"),
            sub_type=payload.get("sub_type"),
            product_name=payload.get("product_name"),
            product_id=payload.get("product_id"),
            launch_dates=payload.get("launch_dates"),
            cities=payload.get("cities"),
            hub_count=payload.get("hub_count"),
            submitted_by=payload.get("submitted_by"),
            user_id=payload.get("user_id"),
            db=db,
        )

def handle_npl_sheets_sync(payload: Dict[str, Any]):
    """
    Queue handler for sinking NPL to Google Sheets.
    """
    sub_id = payload.get("submission_id")
    action = payload.get("action", "append")
    owner_email = payload.get("owner_email")
    logger.info(f"Processing sheets sync for {sub_id} with action {action}")
    
    if action == "append":
        from features.product_launch.router import _append_approved_to_new_product_launch
        _append_approved_to_new_product_launch(sub_id, owner_email=owner_email)
    else:
        logger.warning(f"Unknown sheets sync action: {action}")

def handle_delete_submission_rows(payload: dict):
    from features.product_launch.core import delete_submission_rows_by_index, get_submission_rows_with_indices
    from core.database.engine import get_shared_database
    
    sub_id = payload["submission_id"]
    row_indices = payload["row_indices"]
    reason = payload["reason"]
    username = payload["username"]
    
    logger.info(f"[WORKER] Deleting {len(row_indices)} rows from {sub_id}")
    delete_submission_rows_by_index(sub_id, row_indices, reason=reason)
    
    remaining = get_submission_rows_with_indices(sub_id)
    if not remaining:
        try:
            db = get_shared_database()
            db.update_npl_submission_status(sub_id, "Deleted", reason)
            logger.info(f"[WORKER] Marked {sub_id} as Deleted in DB.")
        except Exception as e:
            logger.error(f"[WORKER] Failed to mark {sub_id} as Deleted: {e}")

def handle_ph_sync(payload: dict):
    from app.config import DPM_SHEET_KEY
    from core.shared.sheets_session import get_sheets_manager
    from core.database.engine import get_shared_database

    rows_to_add = payload["rows_to_add"]
    ph_headers = payload["ph_headers"]
    product_ids = payload.get("product_ids", [])
    user_id = payload["user_id"]
    
    logger.info(f"[WORKER] Running P-H Master sync for {len(rows_to_add)} rows")
    gsm = get_sheets_manager()
    ss = gsm.gc.open_by_key(DPM_SHEET_KEY)
    ph_ws = ss.worksheet("P-H Master")
    values = [[r.get(h, "") for h in ph_headers] for r in rows_to_add]
    
    if values:
        gsm.append_rows_to_worksheet(
            "demand_planning_masters",
            "product_hub_master",
            values,
            worksheet=ph_ws,
            value_input_option="RAW",
        )
        # Warmup cache
        try:
            gsm.read_worksheet_uncached("demand_planning_masters", "product_hub_master", use_cache=False)
        except Exception as e:
            logger.warning(f"[WORKER] Cache warmup failed: {e}")
            
    db = get_shared_database()
    db.log_master_sync({
        "master_type": "ph_master_sync" if product_ids else "new_hub_sync",
        "user_id": user_id,
        "records_synced": len(rows_to_add),
        "status": "success",
        "error_message": f"Sync: Appended {len(rows_to_add)} rows via worker.",
    })
    logger.info("[WORKER] Sync successful")

def register_npl_tasks(worker):
    """
    Registers NPL background tasks with the queue worker.
    """
    worker.register("npl.send_email", handle_npl_email)
    worker.register("npl.sheets_sync", handle_npl_sheets_sync)
    worker.register("npl.delete_submission_rows", handle_delete_submission_rows)
    worker.register("npl.ph_sync", handle_ph_sync)
    worker.register("npl.new_hub_sync", handle_ph_sync) # same logic for now
    # We can add more specific targets like:
    # worker.register("npl.expansion", handle_expansion_sync)
    # worker.register("npl.replacement", handle_replacement_sync)
    # worker.register("npl.history_delete", handle_history_delete)
