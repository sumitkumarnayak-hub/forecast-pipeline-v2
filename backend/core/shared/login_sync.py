"""User preferences helpers for the FastAPI API (no Streamlit session state)."""
from __future__ import annotations

from core.database.engine import Database



def load_user_preferences(user_id: int, db: Database | None = None) -> dict:
    """Load user preferences from the database."""
    db = db or Database()
    return db.get_user_preferences(user_id) or {}
