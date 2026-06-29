"""Role-based page access and action permissions."""
from __future__ import annotations


from planning_suite.config import USER_ROLES

VIEWER_PAGES: frozenset[str] = frozenset({
    "Dashboard",
    "Master Data",
    "Analytics",
    "Settings",
})

PAGE_ORDER: list[str] = [
    "Dashboard",
    "Baseline",
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
    prefs = st.session_state.get("user_preferences")
    if isinstance(prefs, dict) and prefs.get("preview_rows") is not None:
        return max(10, min(1000, int(prefs["preview_rows"])))
    if user_id is not None:
        try:
            from planning_suite.db.engine import Database

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
    if role in {"admin", "planner"}:
        return list(PAGE_ORDER)
    return [page for page in PAGE_ORDER if page in VIEWER_PAGES]


def can_access_page(role: str, page: str) -> bool:
    return page in allowed_pages(role)


def require_page_access(user: dict, page: str) -> None:
    """Stop rendering if the user's role cannot open this page."""
    role = user.get("role", "")
    if can_access_page(role, page):
        return
    st.error(
        f"Your role (**{role.title()}**) does not have access to **{page}**. "
        "Contact an administrator if you need elevated access."
    )
    if st.button("Go to Master Data", type="primary", key=f"perm_redirect_{page}"):
        st.session_state["main_nav"] = "Master Data"
        st.rerun()
    st.stop()


def require_write(user: dict, action: str = "perform this action") -> None:
    if can_write(user.get("role", "")):
        return
    st.error(f"You don't have permission to {action}. Viewers have read-only access.")
    st.stop()


def require_approve(user: dict) -> None:
    if can_approve(user.get("role", "")):
        return
    st.error("Only administrators can approve baselines.")
    st.stop()
