"""Send email via SMTP (Redmail) and log every attempt to Supabase/SQLite."""
from __future__ import annotations

import html
from typing import Any

from app.config import get_smtp_config, is_smtp_configured
from core.database.engine import Database

from core.shared.audit_context import get_audit_session_id


# Categories for notification recipient list (admin CRUD)
RECIPIENT_CATEGORIES: dict[str, str] = {
    "all": "All notifications",
    "approval": "Approval required (baseline)",
    "launch_planner": "New launch — planners",
    "launch_admin": "New launch — admin approval",
    "pipeline": "Pipeline & run failures",
    "validation": "Validation results",
    "general": "General notifications",
}

# Labels for email_log.email_type (includes non-recipient types)
NOTIFICATION_CATEGORIES: dict[str, str] = {
    **RECIPIENT_CATEGORIES,
    "test": "Test message",
}

_sender: Any | None = None


def _get_sender():
    """Lazy singleton EmailSender from Redmail."""
    global _sender
    if _sender is not None:
        return _sender

    from redmail import EmailSender

    cfg = get_smtp_config()
    kwargs: dict[str, Any] = {
        "host": cfg["host"],
        "port": cfg["port"],
        "username": cfg["username"],
        "password": cfg["password"],
    }
    if cfg["use_tls"]:
        kwargs["use_starttls"] = True
    _sender = EmailSender(**kwargs)
    return _sender


def smtp_status_message() -> str:
    if not is_smtp_configured():
        return (
            "Email is not configured. Set **FROM_EMAIL** and **FROM_EMAIL_APP_PASSWORD** in `.env`, "
            "then restart Streamlit."
        )
    cfg = get_smtp_config()
    return f"SMTP ready — sending as **{cfg['from_address']}** via `{cfg['host']}:{cfg['port']}`"


def _esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


_VARIANT_STYLES = {
    "default": {"accent": "#0071E3", "badge_bg": "#E8F1FD", "badge_text": "#0071E3", "icon": "●"},
    "success": {"accent": "#34C759", "badge_bg": "#E8F8ED", "badge_text": "#248A3D", "icon": "✓"},
    "warning": {"accent": "#FF9500", "badge_bg": "#FFF4E5", "badge_text": "#C93400", "icon": "!"},
    "error": {"accent": "#FF3B30", "badge_bg": "#FFEBEA", "badge_text": "#D70015", "icon": "✕"},
}


def build_master_links_card(*, title: str = "Update these master sheets") -> str:
    """Apple-style action card with links to common planning worksheets."""
    links = [
        ("P Master", "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit"),
        ("P-L Master", "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit"),
        ("Hub Mapping", "https://docs.google.com/spreadsheets/d/19-s1HaHtiJj7Ko65A88yxxS9SMpZGecfw9dSfXk-jqA/edit?gid=272986515#gid=272986515"),
        ("Pricing", "https://docs.google.com/spreadsheets/d/1OjV5oPzNgrgQVplkGKIdZIWX1ZOxt6UzVviktXgAyEI"),
        ("Pan India", "https://docs.google.com/spreadsheets/d/1clylbzZgy_XADJXHGs8ADJFirRsS7FnsujZGC3vKFAQ/edit"),
    ]
    rows = "".join(
        f"""<tr>
          <td style="padding:10px 0;border-bottom:1px solid #F2F2F7;font-size:14px;color:#1D1D1F;font-weight:500;">{_esc(label)}</td>
          <td style="padding:10px 0;border-bottom:1px solid #F2F2F7;text-align:right;">
            <a href="{_esc(url)}" style="color:#0071E3;text-decoration:none;font-size:14px;font-weight:500;">Open sheet →</a>
          </td>
        </tr>"""
        for label, url in links
    )
    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0 0 0;">
      <tr>
        <td style="background:#FAFAFC;border:1px solid #E8E8ED;border-radius:14px;padding:18px 20px;">
          <p style="margin:0 0 12px 0;font-size:13px;font-weight:600;color:#86868B;letter-spacing:0.02em;text-transform:uppercase;">{_esc(title)}</p>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{rows}</table>
        </td>
      </tr>
    </table>"""


def build_email_html(
    *,
    headline: str,
    intro: str,
    fields: dict[str, str] | None = None,
    error_block: str = "",
    info_block: str = "",
    action: str = "",
    variant: str = "default",
    badge: str = "",
    extra_html: str = "",
) -> str:
    """Apple-inspired light HTML layout for operational emails."""
    from datetime import datetime

    style = _VARIANT_STYLES.get(variant, _VARIANT_STYLES["default"])
    accent = style["accent"]
    ts = datetime.now().strftime("%d %b %Y · %I:%M %p")

    field_rows = []
    for label, val in (fields or {}).items():
        field_rows.append(
            f"""<tr>
              <td style="padding:11px 0;width:38%;vertical-align:top;font-size:14px;color:#86868B;font-weight:500;">{_esc(label)}</td>
              <td style="padding:11px 0;vertical-align:top;font-size:14px;color:#1D1D1F;line-height:1.45;">{val}</td>
            </tr>"""
        )
    details_table = (
        f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0 0 0;">
          <tr><td style="background:#FAFAFC;border:1px solid #E8E8ED;border-radius:14px;padding:6px 20px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(field_rows)}</table>
          </td></tr>
        </table>"""
        if field_rows
        else ""
    )

    badge_html = ""
    if badge:
        badge_html = (
            f'<span style="display:inline-block;margin-left:8px;padding:4px 10px;border-radius:999px;'
            f'background:{style["badge_bg"]};color:{style["badge_text"]};font-size:11px;font-weight:600;'
            f'letter-spacing:0.03em;vertical-align:middle;">{_esc(badge)}</span>'
        )

    error_html = ""
    if error_block:
        error_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0 0 0;">
          <tr><td style="background:#FFF5F5;border:1px solid #FFD6D6;border-radius:12px;padding:14px 16px;">
            <p style="margin:0 0 6px 0;font-size:12px;font-weight:600;color:#D70015;letter-spacing:0.02em;text-transform:uppercase;">What went wrong</p>
            <p style="margin:0;font-size:13px;color:#1D1D1F;line-height:1.55;white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;">{_esc(error_block[:3000])}</p>
          </td></tr>
        </table>"""

    info_html = ""
    if info_block:
        info_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0 0 0;">
          <tr><td style="background:#FFFCF2;border:1px solid #FFE8B3;border-radius:12px;padding:14px 16px;">
            <p style="margin:0 0 6px 0;font-size:12px;font-weight:600;color:#C93400;letter-spacing:0.02em;text-transform:uppercase;">Notes</p>
            <p style="margin:0;font-size:13px;color:#1D1D1F;line-height:1.55;white-space:pre-wrap;">{_esc(info_block[:3000])}</p>
          </td></tr>
        </table>"""

    action_html = ""
    if action:
        action_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:22px 0 0 0;">
          <tr><td style="background:#F5F9FF;border:1px solid #D6E8FF;border-radius:12px;padding:14px 16px;">
            <p style="margin:0;font-size:14px;color:#1D1D1F;line-height:1.55;">{action}</p>
          </td></tr>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light" />
  <title>{_esc(headline)}</title>
</head>
<body style="margin:0;padding:0;background:#F5F5F7;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#F5F5F7;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border-radius:18px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.06);">
          <tr>
            <td style="padding:28px 32px 0 32px;">
              <p style="margin:0 0 20px 0;font-size:13px;font-weight:600;color:#86868B;letter-spacing:-0.01em;">
                Planning workbench{badge_html}
              </p>
              <h1 style="margin:0;font-size:26px;font-weight:600;color:#1D1D1F;letter-spacing:-0.03em;line-height:1.2;">{_esc(headline)}</h1>
              <p style="margin:14px 0 0 0;font-size:16px;color:#515154;line-height:1.55;">{_esc(intro)}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:0 32px 28px 32px;">
              {details_table}
              {info_html}
              {error_html}
              {extra_html}
              {action_html}
            </td>
          </tr>
          <tr>
            <td style="padding:18px 32px 24px 32px;border-top:1px solid #F2F2F7;">
              <p style="margin:0;font-size:12px;color:#AEAEB2;line-height:1.5;">
                This is an automated message from Planning workbench.<br />
                {_esc(ts)}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_sheet_change_email(
    *,
    headline: str,
    intro: str,
    summary: str,
    detected_at: str,
    row_count_before: int,
    row_count_after: int,
    diff_table_html: str,
    action: str,
    badge: str = "Sheet update",
) -> str:
    """Light-themed email for sheet watcher diff notifications."""
    extra = f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0 0 0;">
      <tr><td style="background:#FAFAFC;border:1px solid #E8E8ED;border-radius:14px;padding:16px 18px;">
        <p style="margin:0 0 10px 0;font-size:13px;font-weight:600;color:#86868B;letter-spacing:0.02em;text-transform:uppercase;">Change summary</p>
        <p style="margin:0 0 6px 0;font-size:14px;color:#1D1D1F;"><strong>Summary:</strong> {_esc(summary)}</p>
        <p style="margin:0 0 6px 0;font-size:14px;color:#1D1D1F;"><strong>Rows:</strong> {row_count_before} → {row_count_after}</p>
        <p style="margin:0;font-size:14px;color:#1D1D1F;"><strong>Detected:</strong> {_esc(detected_at)}</p>
      </td></tr>
    </table>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:16px 0 0 0;">
      <tr><td style="background:#FFFFFF;border:1px solid #E8E8ED;border-radius:14px;padding:14px 16px;overflow-x:auto;">
        <p style="margin:0 0 10px 0;font-size:13px;font-weight:600;color:#86868B;letter-spacing:0.02em;text-transform:uppercase;">Changed rows</p>
        <p style="margin:0 0 12px 0;font-size:12px;color:#86868B;">Green = added · Red = removed · Yellow highlight = modified values</p>
        {diff_table_html or '<p style="margin:0;font-size:14px;color:#86868B;">No row-level diff available.</p>'}
      </td></tr>
    </table>
    {build_master_links_card(title="Recommended master updates")}
    """
    return build_email_html(
        headline=headline,
        intro=intro,
        variant="warning",
        badge=badge,
        extra_html=extra,
        action=action,
    )


def get_recipient_emails(
    db: Database | None,
    category: str,
    *,
    enabled_only: bool = True,
) -> list[str]:
    """Recipients for a category plus anyone on the **all** list."""
    db = db or Database()
    specific = db.get_email_recipients(category=category, enabled_only=enabled_only)
    universal = db.get_email_recipients(category="all", enabled_only=enabled_only)
    emails = [r["email"] for r in specific + universal if r.get("email")]
    return list(dict.fromkeys(emails))


def _log_email_attempt(
    db: Database,
    *,
    email_type: str,
    subject: str,
    recipients: list[str],
    status: str,
    error_message: str = "",
    body_preview: str = "",
    triggered_by_user_id: int | None = None,
    metadata: dict | None = None,
) -> int | None:
    return db.log_email(
        {
            "email_type": email_type,
            "subject": subject,
            "recipients": recipients,
            "status": status,
            "error_message": error_message,
            "body_preview": body_preview[:2000] if body_preview else "",
            "triggered_by_user_id": triggered_by_user_id,
            "session_id": get_audit_session_id(),
            "metadata": metadata or {},
        }
    )


def _get_nextjs_mail_url() -> str:
    import os
    explicit = os.getenv("NEXTJS_EMAIL_URL", "").strip()
    if explicit:
        return explicit
    origins = os.getenv("CORS_ORIGINS", "").strip().split(",")
    for origin in origins:
        origin = origin.strip().rstrip("/")
        if origin:
            if "vercel.app" in origin:
                return f"{origin}/api/send-email"
    for origin in origins:
        origin = origin.strip().rstrip("/")
        if "localhost" in origin or "127.0.0.1" in origin:
            return f"{origin}/api/send-email"
    return "https://forecast-pipeline-v2-frontend-nu.vercel.app/api/send-email"


def send_to_addresses(
    *,
    recipients: list[str],
    subject: str,
    html_body: str,
    email_type: str = "general",
    triggered_by_user_id: int | None = None,
    metadata: dict | None = None,
    db: Database | None = None,
) -> dict:
    """
    Send to explicit addresses (no category lookup). Always writes email_log row.

    Returns {"ok": bool, "status": str, "recipients": list, "log_id": int|None, "error": str}
    """
    db = db or Database()
    clean = list(dict.fromkeys(
        e.strip().lower() for e in recipients if e and "@" in str(e).strip()
    ))
    plain_preview = html_body[:500]

    if not clean:
        log_id = _log_email_attempt(
            db,
            email_type=email_type,
            subject=subject,
            recipients=[],
            status="skipped",
            error_message="No valid recipient addresses.",
            body_preview=plain_preview,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata,
        )
        return {
            "ok": False,
            "status": "skipped",
            "recipients": [],
            "log_id": log_id,
            "error": "Enter at least one valid email address.",
        }

    if not is_smtp_configured():
        log_id = _log_email_attempt(
            db,
            email_type=email_type,
            subject=subject,
            recipients=clean,
            status="skipped",
            error_message="Email not configured in .env",
            body_preview=plain_preview,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata,
        )
        return {
            "ok": False,
            "status": "skipped",
            "recipients": clean,
            "log_id": log_id,
            "error": "Email not configured.",
        }

    # Try sending via Next.js server actions endpoint first to bypass Hugging Face firewall
    import os
    import requests
    url = _get_nextjs_mail_url()
    secret = os.getenv("AUTH_SECRET_KEY", "dev-insecure-auth-key-change-before-production").strip()
    nextjs_success = False
    nextjs_error = ""

    try:
        resp = requests.post(
            url,
            json={
                "to": clean,
                "subject": subject,
                "html": html_body,
                "secret": secret
            },
            timeout=12.0
        )
        if resp.status_code == 200:
            nextjs_success = True
        else:
            nextjs_error = f"Next.js returned status {resp.status_code}: {resp.text}"
    except Exception as e:
        nextjs_error = str(e)

    if nextjs_success:
        try:
            log_id = _log_email_attempt(
                db,
                email_type=email_type,
                subject=subject,
                recipients=clean,
                status="sent",
                body_preview=plain_preview,
                triggered_by_user_id=triggered_by_user_id,
                metadata=metadata,
            )
            return {
                "ok": True,
                "status": "sent",
                "recipients": clean,
                "log_id": log_id,
                "error": "",
            }
        except Exception:
            pass

    # Fallback to direct SMTP (Redmail) if Next.js server is not reachable
    cfg = get_smtp_config()
    import socket
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(15.0)
    try:
        sender = _get_sender()
        sender.send(
            subject=subject,
            sender=cfg["from_address"],
            receivers=clean,
            html=html_body,
        )
    except Exception as exc:
        full_error = f"Next.js API failed ({nextjs_error}). SMTP failed ({exc})."
        log_id = _log_email_attempt(
            db,
            email_type=email_type,
            subject=subject,
            recipients=clean,
            status="failed",
            error_message=full_error,
            body_preview=plain_preview,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata,
        )
        return {
            "ok": False,
            "status": "failed",
            "recipients": clean,
            "log_id": log_id,
            "error": full_error,
        }
    finally:
        socket.setdefaulttimeout(old_timeout)

    try:
        log_id = _log_email_attempt(
            db,
            email_type=email_type,
            subject=subject,
            recipients=clean,
            status="sent",
            body_preview=plain_preview,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata,
        )
        return {
            "ok": True,
            "status": "sent",
            "recipients": clean,
            "log_id": log_id,
            "error": "",
        }
    except Exception as exc:
        log_id = _log_email_attempt(
            db,
            email_type=email_type,
            subject=subject,
            recipients=clean,
            status="failed",
            error_message=str(exc),
            body_preview=plain_preview,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata,
        )
        return {
            "ok": False,
            "status": "failed",
            "recipients": clean,
            "log_id": log_id,
            "error": str(exc),
        }


def send_email(
    *,
    category: str,
    subject: str,
    html_body: str,
    triggered_by_user_id: int | None = None,
    metadata: dict | None = None,
    db: Database | None = None,
) -> dict:
    """
    Send to all enabled recipients for `category`. Always writes email_log row.

    Returns {"ok": bool, "status": str, "recipients": list, "log_id": int|None, "error": str}
    """
    db = db or Database()
    recipients = get_recipient_emails(db, category)
    plain_preview = html_body[:500]

    if not recipients:
        log_id = _log_email_attempt(
            db,
            email_type=category,
            subject=subject,
            recipients=[],
            status="skipped",
            error_message=f"No enabled recipients for category '{category}'.",
            body_preview=plain_preview,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata,
        )
        return {
            "ok": False,
            "status": "skipped",
            "recipients": [],
            "log_id": log_id,
            "error": "No recipients configured for this notification type.",
        }

    return send_to_addresses(
        recipients=recipients,
        subject=subject,
        html_body=html_body,
        email_type=category,
        triggered_by_user_id=triggered_by_user_id,
        metadata=metadata,
        db=db,
    )


def send_test_email(
    *,
    to_addresses: list[str],
    triggered_by_user_id: int | None = None,
    username: str = "",
    custom_message: str = "",
    db: Database | None = None,
) -> dict:
    """Send a test message to verify SMTP setup and inbox delivery."""
    from datetime import datetime

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg = get_smtp_config()
    from_addr = html.escape(cfg.get("from_address") or "")

    body_html = build_email_html(
        headline="Test email delivered",
        intro="Your SMTP configuration is working. If you can read this message, notifications will reach your inbox.",
        fields={
            "Sent at": now,
            "Triggered by": username or "user",
            "From address": from_addr,
            **({"Your note": custom_message.strip()} if custom_message.strip() else {}),
        },
        variant="success",
        badge="Test",
        action="You can safely ignore this message, or use Settings → Notifications to manage recipients.",
    )

    subject = f"Planning workbench — test email ({now})"
    return send_to_addresses(
        recipients=to_addresses,
        subject=subject,
        html_body=html_body,
        email_type="test",
        triggered_by_user_id=triggered_by_user_id,
        metadata={"test": True, "username": username, "custom_message": custom_message[:200]},
        db=db,
    )


def send_launch_notifications(
    *,
    sub_id: str,
    sub_type: str,
    product_name: str,
    launch_dates: list[str],
    triggered_by_user_id: int | None = None,
    db: Database | None = None,
) -> dict:
    """Send planner + admin emails for a new product launch submission."""
    db = db or Database()
    dates_str = ", ".join(launch_dates) if launch_dates else "—"
    safe_id = html.escape(sub_id)

    planner_html = build_email_html(
        headline=f"New {sub_type}",
        intro="A launch plan was submitted. Please update the master worksheets so downstream planning stays in sync.",
        fields={
            "Product": html.escape(product_name),
            "Type": html.escape(sub_type),
            "Launch date(s)": html.escape(dates_str),
            "Submission ID": f"<span style='font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;color:#1D1D1F;'>{safe_id}</span>",
        },
        variant="success",
        badge="Planner",
        extra_html=build_master_links_card(),
    )
    admin_html = build_email_html(
        headline=f"Review required — {sub_type}",
        intro="A new launch submission needs your review and master sheet updates before it can go live.",
        fields={
            "Product": html.escape(product_name),
            "Type": html.escape(sub_type),
            "Launch date(s)": html.escape(dates_str),
            "Submission ID": f"<span style='font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;color:#1D1D1F;'>{safe_id}</span>",
        },
        variant="warning",
        badge="Admin",
        extra_html=build_master_links_card(),
        action="Open <strong>Planning workbench → Product Launch → Submission History</strong> to review and approve.",
    )

    meta = {"submission_id": sub_id, "submission_type": sub_type, "product_name": product_name}
    planner_result = send_email(
        category="launch_planner",
        subject=f"[Planning workbench] New {sub_type} — {product_name}",
        html_body=planner_html,
        triggered_by_user_id=triggered_by_user_id,
        metadata={**meta, "audience": "planner"},
        db=db,
    )
    admin_result = send_email(
        category="launch_admin",
        subject=f"[Planning workbench] Approval required — {sub_type}: {product_name}",
        html_body=admin_html,
        triggered_by_user_id=triggered_by_user_id,
        metadata={**meta, "audience": "admin"},
        db=db,
    )
    return {
        "planner": planner_result,
        "admin": admin_result,
        "ok": planner_result.get("status") == "sent" and admin_result.get("status") == "sent",
    }


def send_welcome_email(
    *,
    email: str,
    username: str,
    full_name: str,
    role: str,
    db: Database | None = None,
) -> dict:
    """Send welcome email to a newly created user."""
    from datetime import datetime

    safe_name = html.escape(full_name)
    safe_username = html.escape(username)
    safe_role = html.escape(role)

    body_html = build_email_html(
        headline="Welcome to Planning workbench",
        intro=f"Hi {safe_name}, your account is ready. Sign in with the credentials below.",
        fields={
            "Username": safe_username,
            "Role": safe_role,
        },
        variant="success",
        badge="Account",
        action=(
            "Open the "
            "<a href='https://forecast-pipeline-v2-frontend-nu.vercel.app/login' "
            "style='color:#0071E3;text-decoration:none;font-weight:600;'>Planning workbench login page</a> "
            "to get started."
        ),
    )

    return send_to_addresses(
        recipients=[email],
        subject=f"[Planning workbench] Account Created — Welcome {safe_name}!",
        html_body=body_html,
        email_type="general",
        db=db,
    )
