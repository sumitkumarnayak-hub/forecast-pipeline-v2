"""Role-based page access and action permissions."""
from __future__ import annotations

from app.config import USER_ROLES

VIEWER_PAGES: frozenset[str] = frozenset({
    "Dashboard",
    "Master Data",
    "Analytics",
    "Settings",
})

PRODUCT_PAGES: frozenset[str] = frozenset({
    "Product Launch",
    "Settings",
})

PAGE_AUTO_PILOT = "Auto-Pilot"
PAGE_LOAD_RAW_DATA = "1. Load Raw Data"
PAGE_CONFIGURE_PARAMS = "2. Configure Parameters"
PAGE_GENERATE_BASELINE = "3. Generate Baseline"
PAGE_REVIEW_BASELINE = "4. Review & Validate"
PAGE_APPROVE_BASELINE = "5. Approve Baseline"

MANUAL_BASELINE_PAGES: list[str] = [
    PAGE_LOAD_RAW_DATA,
    PAGE_CONFIGURE_PARAMS,
    PAGE_GENERATE_BASELINE,
    PAGE_REVIEW_BASELINE,
    PAGE_APPROVE_BASELINE,
]

PAGE_ORDER: list[str] = [
    "Dashboard",
    PAGE_AUTO_PILOT,
    *MANUAL_BASELINE_PAGES,
    "Master Data",
    "Product Launch",
    "Final Plan",
    "Validation",
    "Analytics",
    "Settings",
]

ALL_PAGES: frozenset[str] = frozenset(PAGE_ORDER)

DEFAULT_PREFERENCES: dict = {
    "email_notifications": True,
    "auto_sync_masters": False,
    "preview_rows": 100,
}


def get_preview_rows(user_id: int | None = None) -> int:
    """Return the user's preferred dataframe preview row count."""
    if user_id is not None:
        try:
            from core.database.engine import Database


            stored = Database().get_user_preferences(user_id)
            if stored.get("preview_rows") is not None:
                return max(10, min(1000, int(stored["preview_rows"])))
        except Exception:
            pass
    return int(DEFAULT_PREFERENCES["preview_rows"])


def role_permissions(role: str) -> list[str]:
    return USER_ROLES.get(role or "", [])


def can_read(role: str) -> bool:
    return "read" in role_permissions(role)


def can_write(role: str) -> bool:
    return "write" in role_permissions(role)


def can_approve(role: str) -> bool:
    return "approve" in role_permissions(role)


def is_admin(role: str) -> bool:
    return role == "admin"


def can_manage_email_recipients(role: str) -> bool:
    return is_admin(role)


def allowed_pages(role: str) -> list[str]:
    if role == "product":
        return [page for page in PAGE_ORDER if page in PRODUCT_PAGES]
    if role in {"admin", "planner"}:
        return list(PAGE_ORDER)
    return [page for page in PAGE_ORDER if page in VIEWER_PAGES]


def can_access_page(role: str, page: str) -> bool:
    return page in allowed_pages(role)


def require_page_access(user: dict, page: str) -> None:
    """Streamlit UI guard — no-op outside Streamlit."""
    role = user.get("role", "")
    if can_access_page(role, page):
        return
    try:
        import streamlit as st
        st.error(
            f"Your role (**{role.title()}**) does not have access to **{page}**. "
            "Contact an administrator if you need elevated access."
        )
        st.stop()
    except Exception:
        raise PermissionError(f"Access denied to {page} for role {role}")


def require_write(user: dict, action: str = "perform this action") -> None:
    if can_write(user.get("role", "")):
        return
    try:
        import streamlit as st
        st.error(f"You don't have permission to {action}. Viewers have read-only access.")
        st.stop()
    except Exception:
        raise PermissionError(action)


def require_approve(user: dict) -> None:
    if can_approve(user.get("role", "")):
        return
    try:
        import streamlit as st
        st.error("Only administrators can approve baselines.")
        st.stop()
    except Exception:
        raise PermissionError("approve")
