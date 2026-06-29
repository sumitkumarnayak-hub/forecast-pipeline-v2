"""Validation router — output validation using Pandera schemas."""
from __future__ import annotations

import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.deps import get_current_user, require_write

router = APIRouter()


@router.post("/validate-baseline-output")
async def validate_baseline_output(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
):
    """
    Validate a baseline summary Excel against the Pandera schema
    (same as Streamlit validation.py page).
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files accepted")

    contents = await file.read()
    try:
        import pandas as pd
        from planning_suite.services.output_validation import validate_baseline_summary
        df = pd.read_excel(io.BytesIO(contents))
        result = validate_baseline_summary(df)
        return {
            "filename": file.filename,
            "rows": len(df),
            "columns": list(df.columns),
            "validation": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/validation-logs")
def get_validation_logs(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Return recent validation logs from DB."""
    try:
        from planning_suite.db.engine import Database
        db = Database()
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT id, sync_date, master_type, status, error_message
                    FROM master_sync_log
                    WHERE status IN ('failed', 'warning')
                    ORDER BY sync_date DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        return []
