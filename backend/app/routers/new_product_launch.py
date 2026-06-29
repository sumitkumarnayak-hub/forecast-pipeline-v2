"""New Product Launch router — upload & validate Excel, submission log."""
from __future__ import annotations

import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from app.deps import get_current_user, require_write, get_db
from planning_suite.db.engine import Database

router = APIRouter()


@router.post("/upload")
async def upload_npl_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    """
    Upload a New Product Launch Excel workbook.
    Validates with Pandera schema (same as Streamlit page).
    """
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files are accepted")

    contents = await file.read()
    try:
        import pandas as pd
        from planning_suite.features.new_product_launch import validate_npl_upload
        df = pd.read_excel(io.BytesIO(contents))
        result = validate_npl_upload(df)
        return {
            "filename": file.filename,
            "rows": len(df),
            "columns": list(df.columns),
            "validation": result,
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/submissions")
def get_submissions(
    current_user: dict = Depends(get_current_user),
):
    """Fetch launch submissions from Google Sheets (Launch_Output tab)."""
    try:
        from planning_suite.services.google_sheets import GoogleSheetsManager
        from planning_suite import config as cfg
        gsm = GoogleSheetsManager()
        df = gsm.read_worksheet(cfg.HUB_LEVEL_PLANNING_SHEET_URL, "Launch_Output")
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        return {"rows": df.head(200).to_dict(orient="records"), "columns": list(df.columns)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
