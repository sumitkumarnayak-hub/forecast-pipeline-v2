"""Settings router — bootstrap, preferences, email recipients, session metadata."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, require_admin, get_db
from core.database.engine import Database


router = APIRouter()


def _request_headers(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.headers.items()}


@router.get("/bootstrap")
def settings_bootstrap(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    from features.settings.service import get_settings_bootstrap


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
    from features.settings.service import _env_status


    return _env_status()


@router.get("/queue/status")
def get_queue_status(
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Return status of background queue jobs for admin monitoring."""
    from sqlalchemy.orm import Session
    from core.database.models import QueueJob
    
    try:
        with Session(db.engine) as session:
            # Get counts grouped by status
            jobs = session.query(QueueJob).order_by(QueueJob.created_at.desc()).limit(100).all()
            
            pending_count = sum(1 for j in jobs if j.status == 'pending')
            processing_count = sum(1 for j in jobs if j.status == 'processing')
            failed_count = sum(1 for j in jobs if j.status == 'failed')
            completed_count = sum(1 for j in jobs if j.status == 'completed')
            
            return {
                "stats": {
                    "pending": pending_count,
                    "processing": processing_count,
                    "failed": failed_count,
                    "completed": completed_count,
                    "total": len(jobs)
                },
                "recent_jobs": [
                    {
                        "id": j.id,
                        "task_name": j.task_name,
                        "status": j.status,
                        "created_at": j.created_at.isoformat() if j.created_at else None,
                        "locked_at": j.locked_at.isoformat() if j.locked_at else None,
                        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                        "retries": j.retries,
                        "error_message": j.error_message
                    }
                    for j in jobs
                ]
            }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



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
    from features.settings.service import get_session_payload


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
    from features.settings.service import save_session_system_details


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
    from features.settings.service import _list_recipients


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
    from features.settings.service import _email_log_rows


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
    from core.shared.email import send_test_email

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

    username = current_user.get("email") or current_user.get("username") or current_user.get("full_name") or ""
    result = send_test_email(
        to_addresses=to,
        triggered_by_user_id=user_id,
        username=username,
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


# ── User management (admin only) ────────────────────────────────────────────────

@router.get("/users")
def list_users_admin(
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    from sqlalchemy import text
    try:
        users = db.list_users_admin()
        with db.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT email, category, enabled FROM email_notification_recipients")
            ).fetchall()
        
        subs = {}
        for r in rows:
            email_key = str(r[0]).strip().lower()
            if r[2]:  # enabled
                if email_key not in subs:
                    subs[email_key] = []
                subs[email_key].append(r[1])
        
        for u in users:
            email_key = str(u.get("email") or "").strip().lower()
            u["notification_categories"] = subs.get(email_key, [])
            
        return {"users": users}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class UserCreate(BaseModel):
    password: str
    full_name: Optional[str] = None
    email: str
    role: str = "planner"
    notification_categories: list[str] = Field(default_factory=list)


def sync_user_notification_categories(db: Database, email: str, display_name: str, categories: list[str], enabled: bool = True):
    from sqlalchemy import text
    email_clean = email.strip().lower()
    with db.engine.begin() as conn:
        if categories:
            conn.execute(
                text("DELETE FROM email_notification_recipients WHERE LOWER(email) = :email AND category NOT IN :categories"),
                {"email": email_clean, "categories": tuple(categories)}
            )
        else:
            conn.execute(
                text("DELETE FROM email_notification_recipients WHERE LOWER(email) = :email"),
                {"email": email_clean}
            )
        
        for cat in categories:
            count = conn.execute(
                text("SELECT COUNT(*) FROM email_notification_recipients WHERE LOWER(email) = :email AND category = :category"),
                {"email": email_clean, "category": cat}
            ).scalar()
            if count == 0:
                conn.execute(
                    text("""
                        INSERT INTO email_notification_recipients (email, display_name, category, enabled)
                        VALUES (:email, :display_name, :category, :enabled)
                    """),
                    {"email": email_clean, "display_name": display_name or email_clean, "category": cat, "enabled": enabled}
                )
            else:
                conn.execute(
                    text("UPDATE email_notification_recipients SET display_name = :display_name, enabled = :enabled WHERE LOWER(email) = :email AND category = :category"),
                    {"email": email_clean, "display_name": display_name or email_clean, "category": cat, "enabled": enabled}
                )


@router.post("/users")
def create_user_admin(
    body: UserCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    try:
        user = db.create_user(
            password=body.password,
            full_name=body.full_name,
            email=body.email,
            role=body.role,
        )
        
        sync_user_notification_categories(
            db,
            email=body.email,
            display_name=body.full_name or body.email,
            categories=body.notification_categories,
            enabled=True
        )
        
        if body.email and str(body.email).strip():
            from core.shared.email import send_welcome_email

            background_tasks.add_task(
                send_welcome_email,
                email=body.email.strip(),
                username=body.email.strip(),
                full_name=body.full_name or body.email,
                role=body.role,
                db=db,
            )

        return {"detail": f"User {body.email} created", "user": user}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    notification_categories: Optional[list[str]] = None


@router.patch("/users/{user_id}")
def update_user_admin(
    user_id: int,
    body: UserUpdate,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    notification_cats = updates.pop("notification_categories", None)
    try:
        user_before = db.get_user_by_id(user_id, include_inactive=True)
        if not user_before:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = db.update_user(user_id, **updates)
        target_email = user.get("email")
        if target_email:
            old_email = user_before.get("email")
            if old_email and old_email.strip().lower() != target_email.strip().lower():
                from sqlalchemy import text
                with db.engine.begin() as conn:
                    conn.execute(
                        text("UPDATE email_notification_recipients SET email = :new_email WHERE LOWER(email) = :old_email"),
                        {"new_email": target_email.strip().lower(), "old_email": old_email.strip().lower()}
                    )
            
            # Synchronize active status updates with notification recipients
            is_active_updated = updates.get("is_active")
            if is_active_updated is not None:
                from sqlalchemy import text
                with db.engine.begin() as conn:
                    conn.execute(
                        text("UPDATE email_notification_recipients SET enabled = :enabled WHERE LOWER(email) = :email"),
                        {"enabled": bool(is_active_updated), "email": target_email.strip().lower()}
                    )
            
            if notification_cats is not None:
                sync_user_notification_categories(
                    db,
                    email=target_email,
                    display_name=user.get("full_name") or target_email,
                    categories=notification_cats,
                    enabled=updates.get("is_active", True)
                )
        return {"detail": "User updated", "user": user}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class PasswordReset(BaseModel):
    password: str


@router.post("/users/{user_id}/reset-password")
def reset_user_password_admin(
    user_id: int,
    body: PasswordReset,
    current_user: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    try:
        db.reset_user_password(user_id, body.password)
        return {"detail": "Password reset"}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Pipeline storage (admin) ───────────────────────────────────────────────────

@router.get("/storage/status")
def storage_status(
    current_user: dict = Depends(require_admin),
):
    """Artifact sync status for cloud deploy troubleshooting."""
    from core.shared.storage_status import get_storage_status


    return get_storage_status(check_remote=True)


@router.post("/storage/pull")
def storage_pull(
    current_user: dict = Depends(require_admin),
):
    """Re-download startup artifacts from Google Drive / Supabase without restart."""
    from core.storage.factory import storage_backend_name

    from core.storage.sync import pull_startup_artifacts


    if storage_backend_name() == "local":
        raise HTTPException(
            status_code=400,
            detail="STORAGE_BACKEND=local — nothing to pull. Set STORAGE_BACKEND=drive on cloud.",
        )
    try:
        summary = pull_startup_artifacts(skip_existing=False)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    pulled = [k for k, v in summary.items() if v == "downloaded"]
    return {"detail": f"Pulled {len(pulled)} file(s)", "summary": summary}
