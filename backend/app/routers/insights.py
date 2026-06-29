"""Insights router — availability loss, city trends, 6w data."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_current_user

router = APIRouter()


@router.get("/availability-loss")
def get_availability_loss(
    limit: int = 500,
    current_user: dict = Depends(get_current_user),
):
    """Fetch availability-loss data from Google Sheets."""
    try:
        from planning_suite.services.google_sheets import GoogleSheetsManager
        from planning_suite import config as cfg
        gsm = GoogleSheetsManager()
        df = gsm.read_worksheet(cfg.AVAILABILITY_LOSS_SHEET_URL, "Avail Led Rev Loss")
        if df is None or df.empty:
            return {"rows": [], "columns": []}
        return {
            "rows": df.head(limit).to_dict(orient="records"),
            "columns": list(df.columns),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/6w-summary")
def get_6w_summary(
    current_user: dict = Depends(get_current_user),
):
    """Return a lightweight summary of the 6-week rolling parquet if available."""
    import os
    from planning_suite import config as cfg
    parquet_path = os.path.join("outputs", "6w_v3.parquet")
    if not os.path.exists(parquet_path):
        return {"available": False}
    try:
        import polars as pl
        df = pl.read_parquet(parquet_path, n_rows=5)
        return {
            "available": True,
            "columns": df.columns,
            "sample_rows": df.to_dicts(),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}
