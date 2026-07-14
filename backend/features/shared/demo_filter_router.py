"""Admin demo city/hub filter for baseline runs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import get_current_user, require_admin, get_db
from core.database.engine import Database

from core.shared.demo_filter_store import (
    clear_demo_filter,
    demo_filter_active,
    get_demo_filter,
    set_demo_filter,
)

router = APIRouter()


def _cities_and_hubs(db: Database) -> tuple[list[str], list[str]]:
    """Best-effort city/hub lists from active dataset or master data."""
    import os

    import pandas as pd

    cities: list[str] = []
    hubs: list[str] = []
    path = os.path.abspath(os.path.join("outputs", "active_dataset.parquet"))
    if os.path.isfile(path):
        try:
            df = pd.read_parquet(path, columns=["city_name", "hub_name"])
            if "city_name" in df.columns:
                cities = sorted(df["city_name"].dropna().astype(str).unique().tolist())
            if "hub_name" in df.columns:
                hubs = sorted(df["hub_name"].dropna().astype(str).unique().tolist())
        except Exception:
            pass
    if not cities or not hubs:
        try:
            from core.shared.google_sheets import get_sheets_manager


            gsm = get_sheets_manager()
            ph = gsm.sync_master_data("product_master")
            if ph is not None and not ph.empty:
                for col, target in (("city_name", cities), ("hub_name", hubs)):
                    if col in ph.columns:
                        vals = sorted(ph[col].dropna().astype(str).unique().tolist())
                        if col == "city_name":
                            cities = vals
                        else:
                            hubs = vals
        except Exception:
            pass
    return cities, hubs


@router.get("")
def get_filter(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    user_id = int(current_user["sub"])
    state = get_demo_filter(user_id)
    cities, hubs = _cities_and_hubs(db)
    return {
        "city": state.city,
        "hubs": state.hubs,
        "active": demo_filter_active(state),
        "cities": ["All Cities", *cities],
        "available_hubs": hubs,
        "is_admin": current_user.get("role") == "admin",
    }


class DemoFilterBody(BaseModel):
    city: str = "All Cities"
    hubs: list[str] = []


@router.post("")
def update_filter(
    body: DemoFilterBody,
    current_user: dict = Depends(get_current_user),
):
    user_id = int(current_user["sub"])
    state = set_demo_filter(user_id, city=body.city, hubs=body.hubs)
    return {
        "city": state.city,
        "hubs": state.hubs,
        "active": demo_filter_active(state),
        "detail": "Demo filter updated",
    }


@router.delete("")
def reset_filter(current_user: dict = Depends(get_current_user)):
    user_id = int(current_user["sub"])
    clear_demo_filter(user_id)
    return {"detail": "Demo filter cleared", "active": False}
