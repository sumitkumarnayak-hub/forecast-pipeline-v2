"""Collect client and server metadata for auth session audit logs."""
from __future__ import annotations

import getpass
import json
import os
import platform
import socket
from datetime import datetime, timezone
from urllib.parse import unquote


CLIENT_INFO_COOKIE = "ps_sys_info"


def inject_client_system_info_cookie() -> None:
    """Write browser/OS hints to a cookie (call on login page, outside st.form)."""

    components.html(
        f"""
        <script>
        (function() {{
            var name = {json.dumps(CLIENT_INFO_COOKIE)};
            var info = {{
                browser_user_agent: navigator.userAgent || "",
                browser_platform: navigator.platform || "",
                browser_language: navigator.language || "",
                screen_resolution: (window.screen ? window.screen.width + "x" + window.screen.height : ""),
                client_timezone: (Intl.DateTimeFormat().resolvedOptions().timeZone || ""),
                client_timestamp: new Date().toISOString()
            }};
            var value = encodeURIComponent(JSON.stringify(info));
            var cookie = name + "=" + value + "; path=/; max-age=86400; SameSite=Lax";
            try {{ window.parent.document.cookie = cookie; }} catch (e) {{}}
            try {{ document.cookie = cookie; }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
        width=0,
    )


def _read_client_info_cookie() -> dict[str, str]:
    """Parse client metadata written by inject_client_system_info_cookie()."""
    raw: str | None = None

    try:
        raw = st.context.cookies.get(CLIENT_INFO_COOKIE)
    except Exception:
        pass

    if not raw:
        try:
            from planning_suite.core.session_store import mount_cookie_manager

            cookies = mount_cookie_manager().get_all() or {}
            raw = cookies.get(CLIENT_INFO_COOKIE)
        except Exception:
            pass

    if not raw:
        return {}

    try:
        parsed = json.loads(unquote(str(raw)))
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items() if v is not None and str(v).strip()}
    except Exception:
        pass
    return {}


def _server_details() -> dict[str, str]:
    """Metadata from the machine running Streamlit (reliable without st.context)."""
    details: dict[str, str] = {}

    for key, getter in (
        ("server_hostname", lambda: socket.gethostname()),
        ("server_platform", lambda: platform.platform()),
        ("server_python", lambda: platform.python_version()),
        ("os_user", lambda: getpass.getuser()),
    ):
        try:
            value = getter()
            if value:
                details[key] = str(value)
        except Exception:
            pass

    for env_key, label in (
        ("COMPUTERNAME", "computer_name"),
        ("USERNAME", "windows_username"),
        ("USERDOMAIN", "user_domain"),
    ):
        value = os.environ.get(env_key, "").strip()
        if value:
            details[label] = value

    return details


def _streamlit_context_details() -> dict[str, str]:
    """Best-effort request metadata from Streamlit (may be empty inside st.form)."""
    details: dict[str, str] = {}

    try:
        ctx = st.context
        for attr, label in (
            ("ip_address", "ip_address"),
            ("locale", "locale"),
            ("timezone", "timezone"),
            ("url", "url"),
        ):
            value = getattr(ctx, attr, None)
            if value:
                details[label] = str(value)
    except Exception:
        pass

    try:
        headers = st.context.headers
        for header_key, label in (
            ("User-Agent", "user_agent"),
            ("user-agent", "user_agent"),
            ("Host", "host"),
            ("host", "host"),
            ("X-Forwarded-For", "forwarded_for"),
            ("x-forwarded-for", "forwarded_for"),
            ("Accept-Language", "accept_language"),
            ("accept-language", "accept_language"),
        ):
            if label in details:
                continue
            value = headers.get(header_key)
            if value:
                details[label] = str(value)
    except Exception:
        pass

    return details


def _request_headers_details(headers: dict[str, str] | None) -> dict[str, str]:
    """Best-effort request metadata from HTTP headers (FastAPI / reverse proxy)."""
    if not headers:
        return {}
    details: dict[str, str] = {}
    normalized = {str(k).lower(): str(v) for k, v in headers.items() if v}
    for header_key, label in (
        ("user-agent", "user_agent"),
        ("host", "host"),
        ("x-forwarded-for", "forwarded_for"),
        ("accept-language", "accept_language"),
    ):
        value = normalized.get(header_key)
        if value:
            details[label] = value
    return details


def collect_system_details_api(
    *,
    client_info: dict[str, str] | None = None,
    request_headers: dict[str, str] | None = None,
) -> str:
    """
    Build environment JSON for the Next.js API (no Streamlit dependency).
    """
    details: dict[str, str] = {}
    details.update(_server_details())
    details.update(_request_headers_details(request_headers))

    for key, value in (client_info or {}).items():
        if value is not None and str(value).strip():
            details[f"client_{key}" if not key.startswith("client_") else key] = str(value)

    details["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return json.dumps(details, ensure_ascii=False)


def collect_system_details(*, client_info: dict[str, str] | None = None) -> str:
    """
    Build a JSON snapshot of the environment at login time.

    Used to distinguish shared department accounts by IP, browser, PC name, etc.
    Always returns non-empty JSON.
    """
    details: dict[str, str] = {}
    details.update(_server_details())
    details.update(_streamlit_context_details())

    merged_client = dict(client_info or {})
    merged_client.update(_read_client_info_cookie())
    for key, value in merged_client.items():
        details[f"client_{key}" if not key.startswith("client_") else key] = value

    details["captured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return json.dumps(details, ensure_ascii=False)


def cache_login_system_details() -> str:
    """Collect and cache details on the login page (outside form submit)."""
    payload = collect_system_details()
    st.session_state["_login_system_details"] = payload
    return payload


def get_cached_login_system_details() -> str:
    """Return login details, re-reading client cookie when the form is submitted."""
    payload = collect_system_details()
    st.session_state["_login_system_details"] = payload
    return payload
