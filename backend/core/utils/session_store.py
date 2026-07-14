"""Browser cookie + DB session persistence for auth across page refreshes."""
from __future__ import annotations

import json
from urllib.parse import unquote

import extra_streamlit_components as stx

from app.config import AUTH_COOKIE_DAYS, AUTH_COOKIE_NAME
from core.security.tokens import sign_session_token, verify_session_token

from core.shared.system_details import collect_system_details


COOKIE_MANAGER_KEY = "ps_cookie_manager"
_COOKIE_MANAGER_REF = "_ps_cookie_manager_ref"
_BOOTSTRAP_KEY = "_auth_cookie_bootstrap_attempts"
_PENDING_COOKIE_KEY = "_write_auth_cookie"


def mount_cookie_manager() -> stx.CookieManager:
    """Mount the cookie component once per run (must run before auth checks)."""
    if _COOKIE_MANAGER_REF not in st.session_state:
        st.session_state[_COOKIE_MANAGER_REF] = stx.CookieManager(key=COOKIE_MANAGER_KEY)
    return st.session_state[_COOKIE_MANAGER_REF]


def _normalize_cookie_value(value: str | None) -> str | None:
    if not value:
        return None
    return unquote(str(value).strip()) or None


def _read_cookie_value() -> str | None:
    """Read auth session id from HTTP cookies or the cookie component."""
    try:
        token = _normalize_cookie_value(st.context.cookies.get(AUTH_COOKIE_NAME))
        if token:
            return token
    except Exception:
        pass

    cm = mount_cookie_manager()
    try:
        all_cookies = cm.get_all() or {}
        token = _normalize_cookie_value(all_cookies.get(AUTH_COOKIE_NAME))
        if token:
            return token
    except Exception:
        pass

    return _normalize_cookie_value(cm.get(AUTH_COOKIE_NAME))


def _write_browser_cookie(session_id: str) -> None:
    """Persist session id in the browser (parent document + CookieManager)."""
    max_age = int(AUTH_COOKIE_DAYS * 86400)
    cookie_name = AUTH_COOKIE_NAME
    components.html(
        f"""
        <script>
        (function() {{
            var name = {json.dumps(cookie_name)};
            var value = {json.dumps(session_id)};
            var maxAge = {max_age};
            var cookie = name + "=" + encodeURIComponent(value)
                + "; path=/; max-age=" + maxAge + "; SameSite=Lax";
            try {{ window.parent.document.cookie = cookie; }} catch (e) {{}}
            try {{ document.cookie = cookie; }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )
    mount_cookie_manager().set(
        cookie_name,
        session_id,
        path="/",
        max_age=max_age,
        same_site="lax",
    )


def _clear_browser_cookie() -> None:
    """Remove auth cookie from the browser."""
    cookie_name = AUTH_COOKIE_NAME
    components.html(
        f"""
        <script>
        (function() {{
            var name = {json.dumps(cookie_name)};
            var cookie = name + "=; path=/; max-age=0; SameSite=Lax";
            try {{ window.parent.document.cookie = cookie; }} catch (e) {{}}
            try {{ document.cookie = cookie; }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )
    try:
        mount_cookie_manager().delete(cookie_name)
    except KeyError:
        pass


def flush_pending_auth_cookie() -> None:
    """Write a queued session cookie on the run after login."""
    session_id = st.session_state.pop(_PENDING_COOKIE_KEY, None)
    if session_id:
        _write_browser_cookie(session_id)


def get_current_session_id() -> str | None:
    """Return the raw DB session id from the signed auth cookie, if any."""
    return verify_session_token(_read_cookie_value())


def backfill_current_session_system_details(db) -> bool:
    """
    If the active auth_sessions row has NULL/empty system_details, update it.
    Runs once per Streamlit session after login.
    """
    if st.session_state.get("_system_details_backfilled"):
        return False

    session_id = get_current_session_id()
    if not session_id:
        return False

    row = db.get_auth_session(session_id)
    if not row:
        return False

    existing = row.get("system_details")
    if existing and str(existing).strip() not in ("", "null", "{}"):
        st.session_state["_system_details_backfilled"] = True
        return False

    from core.shared.system_details import collect_system_details, inject_client_system_info_cookie


    inject_client_system_info_cookie()
    payload = collect_system_details()
    ok = db.update_auth_session_system_details(session_id, payload)
    if ok:
        print(
            f"[auth_sessions] backfilled system_details for session_id={session_id[:8]}… "
            f"chars={len(payload)}",
            flush=True,
        )
        st.session_state["_system_details_backfilled"] = True
    return ok


def persist_auth_cookie(db, user: dict, *, system_details: str | None = None) -> str:
    """Create a DB session and persist its signed id in the browser."""
    payload = (system_details or collect_system_details()).strip()
    if not payload:
        payload = collect_system_details()
    print(
        f"[auth_sessions] persist_auth_cookie user={user.get('username')} "
        f"payload_chars={len(payload)}",
        flush=True,
    )
    session_id = db.create_auth_session(
        user["id"],
        days=AUTH_COOKIE_DAYS,
        system_details=payload,
    )
    signed = sign_session_token(session_id)
    st.session_state[_PENDING_COOKIE_KEY] = signed
    _write_browser_cookie(signed)
    return signed


def clear_auth_cookie(db) -> None:
    """Remove browser cookie and invalidate the DB session."""
    token = _read_cookie_value()
    session_id = verify_session_token(token)
    if session_id:
        db.delete_auth_session(session_id)
    st.session_state.pop(_PENDING_COOKIE_KEY, None)
    _clear_browser_cookie()


def try_restore_user(db) -> dict | None:
    """Restore authenticated user from cookie + DB session."""
    if st.session_state.get("authenticated"):
        return st.session_state.get("user")

    session_id = verify_session_token(_read_cookie_value())
    if not session_id:
        _clear_browser_cookie()
        return None

    user = db.get_user_by_session(session_id)
    if user:
        return user

    _clear_browser_cookie()
    return None


def restore_auth_session(db) -> bool:
    """
    Restore auth after refresh. Returns True when authenticated.

    CookieManager can lag one render on hard refresh; allow up to two
    bootstrap reruns before showing the login page.
    """
    if st.session_state.get("authenticated"):
        return True

    mount_cookie_manager()
    user = try_restore_user(db)
    if user:
        st.session_state.authenticated = True
        st.session_state.user = user
        st.session_state.pop(_BOOTSTRAP_KEY, None)
        return True

    attempts = int(st.session_state.get(_BOOTSTRAP_KEY, 0))
    if attempts < 2:
        st.session_state[_BOOTSTRAP_KEY] = attempts + 1
        st.rerun()

    return False
