"""
Base Sheet Sync — FastAPI router.

Endpoints:
  GET  /list          → list configured sheets (includes last sync log)
  POST /{sheet_key}/sync  → export sheet → parquet → Drive (enqueued)
  GET  /tasks/{task_id} → status check of background enqueued tasks
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import require_admin
from features.base_sheets import service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/list")
def list_base_sheets(user: dict = Depends(require_admin)):
    """Return metadata and last sync run for all configured base sheets."""
    try:
        return service.list_sheets()
    except Exception as exc:
        logger.exception("Failed to list base sheets")
        raise HTTPException(status_code=500, detail=f"Failed to list sheets: {exc}")


@router.post("/{sheet_key}/sync")
def sync_base_sheet(sheet_key: str, user: dict = Depends(require_admin)):
    """
    Sync a base sheet to parquet → Drive storage, enqueued in the background.
    """
    from sqlalchemy.orm import Session
    from core.queue.driver import PostgresQueueDriver
    from core.database.engine import get_shared_database

    db = get_shared_database()
    user_id = int(user.get("sub", 1))
    
    try:
        with Session(db.engine) as session:
            driver = PostgresQueueDriver(session)
            task_id = driver.enqueue(
                "base_sheets.sync",
                payload={"sheet_key": sheet_key, "user_id": user_id}
            )
            
        return {
            "status": "queued",
            "task_id": task_id,
            "detail": f"Synchronization for sheet '{sheet_key}' enqueued successfully in background.",
        }
    except Exception as exc:
        logger.exception("Failed to enqueue sync for sheet '%s'", sheet_key)
        raise HTTPException(status_code=500, detail=f"Failed to queue sync task: {exc}")


@router.get("/tasks/{task_id}")
def get_task_status(task_id: str, user: dict = Depends(require_admin)):
    """
    Get the status of a background queue sync task.
    """
    from sqlalchemy.orm import Session
    from core.database.engine import get_shared_database
    from core.database.models import QueueJob

    db = get_shared_database()
    with Session(db.engine) as session:
        job = session.query(QueueJob).filter_by(id=task_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Task not found")
        return {
            "id": job.id,
            "task_name": job.task_name,
            "status": job.status,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
