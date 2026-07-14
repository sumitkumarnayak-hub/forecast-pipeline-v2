"""Programmatic sidebar navigation (safe with keyed main_nav radio)."""
from __future__ import annotations

import streamlit as st

NAV_PENDING_KEY = "_main_nav_pending"


def request_main_nav(page: str) -> None:
    """Schedule sidebar navigation on the next run."""
    st.session_state[NAV_PENDING_KEY] = page
    st.rerun()


def apply_pending_nav(pages: list[str], legacy_aliases: dict[str, str] | None = None) -> None:
    """Apply a pending nav target before the main_nav widget is created."""
    pending = st.session_state.pop(NAV_PENDING_KEY, None)
    if not pending:
        return
    aliases = legacy_aliases or {}
    target = aliases.get(pending, pending)
    if target in pages:
        st.session_state["main_nav"] = target
