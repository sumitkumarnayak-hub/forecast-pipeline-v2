"""Settings router — env status, user preferences, email recipients."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.deps import get_current_user, require_admin, get_db
from planning_suite.db.engine import Database

router = APIRouter()


@router.get("/env-status")
def get_env_status(current_user: dict = Depends(get_current_user)):
    """Return which .env variables are set (values redacted)."""
    from planning_suite import config as cfg
    return {
        "app_env": cfg.APP_ENV,
        "is_production": cfg.IS_PRODUCTION,
        "database_backend": cfg.get_database_backend(),
        "smtp_configured": cfg.is_smtp_configured(),
        "google_credentials_path": cfg.GOOGLE_CREDENTIALS_PATH,
        "pipeline_params_sheet_url": cfg.PIPELINE_PARAMS_SHEET_URL,
    }


class PreferenceUpdate(BaseModel):
    email_notifications: Optional[bool] = None
    auto_sync_masters: Optional[bool] = None
    preview_rows: Optional[int] = None


@router.get("/preferences")
def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    user_id = int(current_user["sub"])
    prefs = db.get_user_preferences(user_id) or {}
    return prefs


@router.post("/preferences")
def update_preferences(
    body: PreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    user_id = int(current_user["sub"])
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"detail": "No changes"}
    try:
        db.update_user_preferences(user_id, **updates)
        return {"detail": "Preferences updated", "updated": updates}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Email recipients (admin only) ──────────────────────────────────────────────

@router.get("/email-recipients")
def list_email_recipients(
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT id, email, display_name, category, enabled, created_at
                    FROM email_notification_recipients
                    ORDER BY category, display_name
                """)
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class RecipientCreate(BaseModel):
    email: str
    display_name: Optional[str] = None
    category: str
    enabled: bool = True


@router.post("/email-recipients")
def add_email_recipient(
    body: RecipientCreate,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    user_id = int(current_user["sub"])
    try:
        db.add_email_recipient(
            email=body.email,
            display_name=body.display_name,
            category=body.category,
            enabled=body.enabled,
            created_by=user_id,
        )
        return {"detail": f"Recipient {body.email} added"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/email-recipients/{recipient_id}")
def delete_email_recipient(
    recipient_id: int,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    try:
        db.delete_email_recipient(recipient_id)
        return {"detail": "Recipient deleted"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
