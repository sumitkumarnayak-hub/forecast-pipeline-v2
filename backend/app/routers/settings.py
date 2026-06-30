"""Settings router — bootstrap, preferences, email recipients, session metadata."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.deps import get_current_user, require_admin, get_db
from planning_suite.db.engine import Database

router = APIRouter()


def _request_headers(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.headers.items()}


@router.get("/bootstrap")
def settings_bootstrap(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    from planning_suite.services.settings_service import get_settings_bootstrap

    user_id = int(current_user["sub"])
    return get_settings_bootstrap(
        user_id=user_id,
        role=str(current_user.get("role") or ""),
        db=db,
        request_headers=_request_headers(request),
        token_exp=current_user.get("exp"),
    )


@router.get("/env-status")
def get_env_status(current_user: dict = Depends(get_current_user)):
    """Return which .env variables are set (values redacted)."""
    from planning_suite.services.settings_service import _env_status

    return _env_status()


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
    return db.get_user_preferences(user_id) or {}


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
        prefs = db.get_user_preferences(user_id)
        prefs.update(updates)
        db.save_user_preferences(user_id, prefs)
        return {"detail": "Preferences updated", "updated": updates}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Session metadata ───────────────────────────────────────────────────────────

@router.get("/session")
def get_session(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    from planning_suite.services.settings_service import get_session_payload

    user_id = int(current_user["sub"])
    return get_session_payload(
        user_id=user_id,
        db=db,
        request_headers=_request_headers(request),
        token_exp=current_user.get("exp"),
    )


class ClientInfoBody(BaseModel):
    client_info: dict[str, str] = Field(default_factory=dict)


@router.post("/session/system-details")
def save_system_details(
    body: ClientInfoBody,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    from planning_suite.services.settings_service import save_session_system_details

    user_id = int(current_user["sub"])
    try:
        return save_session_system_details(
            user_id=user_id,
            client_info=body.client_info,
            db=db,
            request_headers=_request_headers(request),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Email recipients (admin only) ──────────────────────────────────────────────

@router.get("/email-recipients")
def list_email_recipients(
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    from planning_suite.services.settings_service import _list_recipients

    try:
        return _list_recipients(db)
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
        db.create_email_recipient(
            email=body.email,
            display_name=body.display_name or body.email,
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


class RecipientPatch(BaseModel):
    enabled: Optional[bool] = None
    display_name: Optional[str] = None
    email: Optional[str] = None
    category: Optional[str] = None


@router.patch("/email-recipients/{recipient_id}")
def patch_email_recipient(
    recipient_id: int,
    body: RecipientPatch,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"detail": "No changes"}
    try:
        db.update_email_recipient(recipient_id, **updates)
        return {"detail": "Recipient updated", "updated": updates}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/email-log")
def get_email_log(
    limit: int = 50,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    from planning_suite.services.settings_service import _email_log_rows

    try:
        return {"rows": _email_log_rows(db, limit=min(max(limit, 1), 200))}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class TestEmailBody(BaseModel):
    recipient_id: Optional[int] = None
    to_email: Optional[str] = None
    message: str = ""


@router.post("/test-email")
def send_test_email_endpoint(
    body: TestEmailBody,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    from planning_suite.services.email_service import send_test_email
    from sqlalchemy import text

    user_id = int(current_user["sub"])
    to: list[str] = []

    if body.recipient_id:
        with db.engine.connect() as conn:
            row = conn.execute(
                text("SELECT email FROM email_notification_recipients WHERE id = :id"),
                {"id": body.recipient_id},
            ).fetchone()
        if row and row._mapping.get("email"):
            to = [row._mapping["email"]]
        else:
            raise HTTPException(status_code=404, detail="Recipient not found")
    elif body.to_email:
        to = [body.to_email.strip()]
    else:
        with db.engine.connect() as conn:
            row = conn.execute(
                text("SELECT email FROM users WHERE id = :id"),
                {"id": user_id},
            ).fetchone()
        if row and row._mapping.get("email"):
            to = [row._mapping["email"]]

    if not to:
        raise HTTPException(
            status_code=400,
            detail="No recipient email — pick a recipient, provide to_email, or set user email",
        )

    result = send_test_email(
        to_addresses=to,
        triggered_by_user_id=user_id,
        username=current_user.get("username", ""),
        custom_message=body.message,
        db=db,
    )
    if not result.get("ok"):
        status = result.get("status", "")
        err = result.get("error", "Send failed")
        if status == "skipped" and "not configured" in err.lower():
            raise HTTPException(status_code=400, detail=err)
        raise HTTPException(status_code=500, detail=err)
    return result
