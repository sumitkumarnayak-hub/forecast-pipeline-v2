"""Hub Launch API routes for FF Automation Hub_Mapping (mirrors FF Input feature set)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, require_write
from core.database.models import AuditLog

logger = logging.getLogger(__name__)


class AppendHubMappingRowBody(BaseModel):
    row: dict


def _normalize_hub_mapping_row(raw: dict) -> dict:
    canonical_map = {
        "hub_id": ["hub_id", "hub id", "hubid"],
        "hub_name": ["hub_name", "hub name", "hubname", "hub"],
        "city_id": ["city_id", "city id", "cityid"],
        "city_name": ["city_name", "city name", "cityname", "city"],
        "status": ["status", "plan flag", "hub_active", "hub active", "active"],
    }
    normalized: dict[str, str] = {}
    for key, val in raw.items():
        k_clean = str(key).strip().lower().replace("_", " ")
        matched = False
        for canonical_key, aliases in canonical_map.items():
            alias_norm = [a.lower().replace("_", " ") for a in aliases]
            if k_clean == canonical_key.replace("_", " ") or k_clean in alias_norm:
                normalized[canonical_key] = str(val).strip()
                matched = True
                break
        if not matched:
            normalized[str(key).strip()] = str(val).strip()
    return normalized


def _validate_hub_mapping_row(normalized: dict) -> dict:
    class HubMappingPydanticRow(BaseModel):
        hub_id: str = Field(..., min_length=1)
        hub_name: str = Field(..., min_length=1)
        city_id: str = Field(..., min_length=1)
        city_name: str = Field(..., min_length=1)
        status: str = Field(..., min_length=1)

        @field_validator("hub_id", "city_id")
        @classmethod
        def validate_numeric_id(cls, v: str) -> str:
            v_str = str(v).strip()
            if not re.match(r"^\d+$", v_str):
                raise ValueError("ID fields must contain only digits")
            return v_str

        @field_validator("status")
        @classmethod
        def validate_status(cls, v: str) -> str:
            v_str = str(v).strip().upper()
            if v_str in {"A", "I", "1", "0", "ACTIVE", "INACTIVE"}:
                if v_str in {"1", "ACTIVE", "A"}:
                    return "A"
                if v_str in {"0", "INACTIVE", "I"}:
                    return "I"
                return v_str
            raise ValueError("Status must be A/I (or 1/0)")

    obj = HubMappingPydanticRow(**normalized)
    return {
        "hub_id": obj.hub_id,
        "hub_name": obj.hub_name,
        "city_id": obj.city_id,
        "city_name": obj.city_name,
        "status": obj.status,
    }


def hub_mapping_data(*, bypass_cache: bool, fetch_actual_drive_last_update) -> dict:
    import hashlib as _hashlib

    from features.product_launch.ff_masters import fetch_hub_mapping_snapshot, invalidate_hub_mapping_cache
    from features.product_launch.watcher import _hub_mapping_state, _poll_hub_mapping_once

    t0 = time.perf_counter()
    try:
        if bypass_cache:
            invalidate_hub_mapping_cache()
            try:
                _poll_hub_mapping_once()
            except Exception as poll_exc:
                logger.warning("[HubSync] hub-mapping poll skipped: %s", poll_exc)

        # Always load from sheet snapshot (A:E, blanks stripped) — not stale watcher cache
        all_rows, headers = fetch_hub_mapping_snapshot(bypass_cache=bypass_cache)
        if all_rows:
            _hub_mapping_state["last_known_rows"] = all_rows
            _hub_mapping_state["last_known_hash"] = _hashlib.sha256(
                json.dumps(all_rows, sort_keys=True, default=str).encode()
            ).hexdigest()

        rows = all_rows
        total_row_count = len(rows)

        content_hash = ""
        if rows:
            serialized = json.dumps(rows, sort_keys=True, default=str)
            content_hash = hashlib.sha256(serialized.encode()).hexdigest()

        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.info("[HubSync] hub-mapping served %d rows (A:E) in %dms", len(rows), elapsed)

        return {
            "rows": rows,
            "headers": headers,
            "row_count": len(rows),
            "total_row_count": total_row_count,
            "content_hash": content_hash,
            "cache_last_updated": _hub_mapping_state.get("last_checked_at"),
            "_elapsed_ms": elapsed,
        }
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.exception("[HubSync] hub-mapping failed in %dms: %s", elapsed, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def hub_mapping_change_status() -> dict:
    from features.product_launch.watcher import get_hub_mapping_change_status

    status = get_hub_mapping_change_status()
    return {
        "change_detected": status["change_detected"],
        "change_history": status["change_history"],
        "last_checked_at": status["last_checked_at"],
        "watcher_started": status["watcher_started"],
        "poll_interval_seconds": status["poll_interval_seconds"],
    }


def dismiss_hub_mapping_changes() -> dict:
    from features.product_launch.watcher import dismiss_hub_mapping_changes as _dismiss

    _dismiss()
    return {"ok": True, "message": "Change notification dismissed. History preserved."}


def portal_sheet_last_update(
    *,
    audit_action: str,
    sheet_key: str,
    fetch_actual_drive_last_update,
) -> dict:
    """Return last update; portal append audit log (logged-in user) takes precedence over Drive metadata."""
    from core.database.engine import get_shared_database

    db = get_shared_database()
    try:
        with Session(db.engine) as session:
            db_entry = (
                session.query(AuditLog)
                .filter(AuditLog.action == audit_action)
                .order_by(AuditLog.ts.desc())
                .first()
            )

        if db_entry and db_entry.user_id:
            return {
                "ts": db_entry.ts.isoformat() if db_entry.ts else None,
                "user_id": db_entry.user_id,
            }

        drive = fetch_actual_drive_last_update(sheet_key)
        if drive.get("ts") or drive.get("user_id"):
            return drive
        return {"ts": None, "user_id": None}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def hub_mapping_last_update(*, fetch_actual_drive_last_update, sheet_key: str) -> dict:
    return portal_sheet_last_update(
        audit_action="append_hub_mapping",
        sheet_key=sheet_key,
        fetch_actual_drive_last_update=fetch_actual_drive_last_update,
    )


def append_hub_mapping_row(body: AppendHubMappingRowBody, current_user: dict) -> dict:
    from core.database.engine import get_shared_database
    from features.product_launch.ff_masters import (
        append_hub_mapping_row as _sheet_append,
        fetch_hub_mapping_snapshot,
    )
    from features.product_launch.watcher import _hub_mapping_state, _rows_hash

    t0 = time.perf_counter()
    try:
        normalized = _normalize_hub_mapping_row(body.row)
        validated_row = _validate_hub_mapping_row(normalized)
    except Exception as err:
        raise HTTPException(status_code=400, detail=f"Validation failed: {err}") from err

    all_rows, headers = fetch_hub_mapping_snapshot(bypass_cache=True)
    if not headers:
        headers = list(validated_row.keys())

    row_values: list[str] = []
    for h in headers:
        h_clean = h.strip().lower().replace("_", " ")
        val = ""
        for k, v in validated_row.items():
            k_clean = k.lower().replace("_", " ")
            if k_clean == h_clean or k.lower() == h_clean:
                val = v
                break
        row_values.append(str(val).strip())

    _sheet_append(row_values)

    try:
        new_row_dict = {h: row_values[i] if i < len(row_values) else "" for i, h in enumerate(headers)}
        row_count_before = len(_hub_mapping_state.get("last_known_rows") or [])
        _hub_mapping_state["last_known_rows"] = ( _hub_mapping_state.get("last_known_rows") or [] ) + [new_row_dict]
        _hub_mapping_state["last_known_hash"] = _rows_hash(_hub_mapping_state["last_known_rows"])

        db = get_shared_database()
        version_id = f"v{int(time.time())}"
        detected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        summary = f"+1 row added manually: {validated_row.get('hub_name', '')}"
        diff = {
            "added": [new_row_dict],
            "removed": [],
            "modified": [],
            "unchanged_count": row_count_before,
        }
        db.save_hub_mapping_version(
            version_id=version_id,
            detected_at=detected_at,
            summary=summary,
            diff=diff,
            row_count_before=row_count_before,
            row_count_after=row_count_before + 1,
            headers=headers,
        )
    except Exception as cache_err:
        logger.warning("[HubMapping] Failed to update watcher cache or DB version: %s", cache_err)

    username = current_user.get("email") or current_user.get("username") or current_user.get("full_name") or "system"
    try:
        db = get_shared_database()
        with Session(db.engine) as session:
            session.add(
                AuditLog(
                    id=str(uuid.uuid4()),
                    sync_run_id=None,
                    action="append_hub_mapping",
                    user_id=username,
                    sheet_name="Hub_Mapping",
                    rows_affected=1,
                    status="success",
                    ts=datetime.now(timezone.utc),
                )
            )
            session.commit()
    except Exception as db_exc:
        logger.warning("[HubMapping] Failed to write audit log: %s", db_exc)

    elapsed = round((time.perf_counter() - t0) * 1000)
    logger.info(
        "[HubMapping] Appended hub=%s city=%s by %s in %dms",
        validated_row.get("hub_name", ""),
        validated_row.get("city_name", ""),
        username,
        elapsed,
    )
    return {
        "ok": True,
        "hub_name": validated_row.get("hub_name", ""),
        "city_name": validated_row.get("city_name", ""),
        "headers": headers,
        "added_by": username,
        "elapsed_ms": elapsed,
    }
