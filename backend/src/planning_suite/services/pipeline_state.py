"""Pipeline approval and readiness checks."""
from __future__ import annotations

import json
import os
from pathlib import Path


from planning_suite.config import BASELINE_APPROVAL_JSON, OUTPUT_PATH
from planning_suite.db.engine import Database


def _read_approval_json() -> dict | None:
    path = Path(BASELINE_APPROVAL_JSON)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def is_baseline_approved() -> bool:
    """True if baseline approval exists on disk or in Supabase/SQLite."""
    saved = _read_approval_json()
    if saved and saved.get("approved"):
        return True

    try:
        db = Database()
        with db.engine.connect() as conn:
            from sqlalchemy import text

            count = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM baseline_runs
                    WHERE validation_status = 'approved'
                    """
                )
            ).scalar()
            return bool(count and count > 0)
    except Exception:
        return False


def is_baseline_approved_cached() -> bool:
    """Cached baseline approval check for routing."""
    return is_baseline_approved()


def clear_baseline_approval_cache() -> None:
    """Invalidate cached approval state (call after approve/revoke)."""
    pass

def get_baseline_approval_info() -> dict:
    saved = _read_approval_json() or {}
    return {
        "approved": is_baseline_approved(),
        "approved_at": saved.get("approved_at", ""),
        "approved_by": saved.get("approved_by", ""),
    }

def approve_baseline(db, approved_by: int) -> None:
    with db.engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(
            text("""
                UPDATE baseline_runs 
                SET validation_status = 'approved',
                    approved_at = CURRENT_TIMESTAMP,
                    approved_by = :user_id
                WHERE run_id = (
                    SELECT run_id FROM baseline_runs 
                    ORDER BY run_date DESC LIMIT 1
                )
            """),
            {"user_id": approved_by}
        )
    clear_baseline_approval_cache()

def reject_baseline(db) -> None:
    with db.engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(
            text("""
                UPDATE baseline_runs 
                SET validation_status = 'rejected',
                    approved_at = NULL,
                    approved_by = NULL
                WHERE run_id = (
                    SELECT run_id FROM baseline_runs 
                    ORDER BY run_date DESC LIMIT 1
                )
            """)
        )
    clear_baseline_approval_cache()


def baseline_outputs_folder() -> Path:
    return Path(OUTPUT_PATH)
