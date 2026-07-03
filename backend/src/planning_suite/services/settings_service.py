"""Settings bootstrap, session metadata, and email log helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from planning_suite import config as cfg
from planning_suite.core.dataframe import sanitize_for_json
from planning_suite.db.engine import Database
from planning_suite.services.email_service import RECIPIENT_CATEGORIES
from planning_suite.services.system_details import collect_system_details_api, _server_details


def _parse_system_details(raw: str | None) -> dict[str, Any] | None:
    if not raw or not str(raw).strip():
        return None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"raw": str(raw)}


def _env_status() -> dict[str, Any]:
    return {
        "app_env": cfg.APP_ENV,
        "is_production": cfg.IS_PRODUCTION,
        "database_backend": cfg.get_database_backend(),
        "smtp_configured": cfg.is_smtp_configured(),
        "google_credentials_path": bool(cfg.GOOGLE_CREDENTIALS_PATH),
        "pipeline_params_sheet_url": bool(cfg.PIPELINE_PARAMS_SHEET_URL),
        "storage_backend": cfg.get_storage_backend_name(),
        "drive_folder_configured": bool(cfg.get_pipeline_drive_folder_id()),
    }


def _list_recipients(db: Database) -> list[dict[str, Any]]:
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


def _email_log_rows(db: Database, limit: int = 50) -> list[dict[str, Any]]:
    df = db.get_email_log(limit=limit)
    if df is None or df.empty:
        return []
    return sanitize_for_json(df.to_dict(orient="records"))


def get_session_payload(
    *,
    user_id: int,
    db: Database,
    request_headers: dict[str, str] | None = None,
    token_exp: int | float | None = None,
) -> dict[str, Any]:
    """Live server details + stored auth session metadata."""
    row = db.get_latest_auth_session_for_user(user_id)
    live_server = _server_details()
    live_server["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    if request_headers:
        from planning_suite.services.system_details import _request_headers_details

        live_server.update(_request_headers_details(request_headers))

    payload: dict[str, Any] = {
        "has_session": row is not None,
        "session_id": row["session_id"][:8] + "…" if row else None,
        "session_created_at": str(row["created_at"]) if row and row.get("created_at") else None,
        "session_expires_at": str(row["expires_at"]) if row and row.get("expires_at") else None,
        "stored_system_details": _parse_system_details(row.get("system_details") if row else None),
        "live_server_details": live_server,
        "token_expires_at": (
            datetime.fromtimestamp(token_exp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            if token_exp
            else None
        ),
    }
    return payload


def save_session_system_details(
    *,
    user_id: int,
    client_info: dict[str, str] | None,
    db: Database,
    request_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Persist merged client + server metadata on the user's auth session."""
    payload = collect_system_details_api(client_info=client_info, request_headers=request_headers)
    row = db.get_latest_auth_session_for_user(user_id)
    if row:
        ok = db.update_auth_session_system_details(row["session_id"], payload)
        session_id = row["session_id"]
    else:
        session_id = db.create_auth_session(user_id, system_details=payload)
        ok = bool(session_id)
    return {
        "saved": ok,
        "session_id": session_id[:8] + "…" if session_id else None,
        "system_details": _parse_system_details(payload),
    }


def get_settings_bootstrap(
    *,
    user_id: int,
    role: str,
    db: Database,
    request_headers: dict[str, str] | None = None,
    token_exp: int | float | None = None,
) -> dict[str, Any]:
    user = db.get_user_by_id(user_id) or {}
    prefs = db.get_user_preferences(user_id)
    is_admin = role == "admin"

    bootstrap: dict[str, Any] = {
        "profile": {
            "id": user.get("id"),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "email": user.get("email"),
            "role": user.get("role"),
        },
        "preferences": prefs,
        "env": _env_status(),
        "recipient_categories": RECIPIENT_CATEGORIES,
        "session": get_session_payload(
            user_id=user_id,
            db=db,
            request_headers=request_headers,
            token_exp=token_exp,
        ),
        "about": {
            "app_name": "Planning Suite",
            "api_version": "2.0.0",
            "database_backend": cfg.get_database_backend(),
            "environment": cfg.APP_ENV,
        },
    }

    if is_admin:
        bootstrap["recipients"] = _list_recipients(db)
        bootstrap["email_log"] = _email_log_rows(db, limit=50)
    else:
        bootstrap["recipients"] = []
        bootstrap["email_log"] = []

    return bootstrap
