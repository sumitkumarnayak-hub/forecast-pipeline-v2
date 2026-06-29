"""Send email via SMTP (Redmail) and log every attempt to Supabase/SQLite."""
from __future__ import annotations

import html
from typing import Any

from planning_suite.config import get_smtp_config, is_smtp_configured
from planning_suite.db.engine import Database
from planning_suite.services.audit_context import get_audit_session_id

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


def build_email_html(
    *,
    headline: str,
    intro: str,
    fields: dict[str, str] | None = None,
    error_block: str = "",
    action: str = "",
) -> str:
    """Consistent HTML layout for operational emails."""
    from datetime import datetime

    def _esc(value: Any) -> str:
        return html.escape(str(value)) if value is not None else ""

    rows = []
    for label, val in (fields or {}).items():
        rows.append(
            f"<tr><td style='padding:6px 12px 6px 0;color:#64748B;font-weight:600;"
            f"vertical-align:top;white-space:nowrap;'>{_esc(label)}</td>"
            f"<td style='padding:6px 0;'>{val}</td></tr>"
        )
    table = (
        f"<table style='border-collapse:collapse;margin:12px 0;'>{''.join(rows)}</table>"
        if rows
        else ""
    )
    err = (
        f"<pre style='background:#FEF2F2;border:1px solid #FECACA;border-radius:6px;"
        f"padding:10px;font-size:12px;white-space:pre-wrap;max-height:240px;"
        f"overflow:auto;'>{_esc(error_block[:3000])}</pre>"
        if error_block
        else ""
    )
    action_html = (
        f"<p style='margin-top:16px;padding:12px;background:#EFF6FF;border-radius:8px;"
        f"border-left:4px solid #2563EB;'>{action}</p>"
        if action
        else ""
    )
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""
    <div style="font-family:Inter,Segoe UI,sans-serif;max-width:640px;color:#0F172A;">
      <h2 style="margin:0 0 8px 0;font-size:1.25rem;">{_esc(headline)}</h2>
      <p style="margin:0 0 8px 0;color:#475569;">{_esc(intro)}</p>
      {table}
      {err}
      {action_html}
      <p style="margin-top:20px;font-size:0.8rem;color:#94A3B8;">
        Planning Suite · {_esc(ts)}
      </p>
    </div>
    """


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

    cfg = get_smtp_config()
    try:
        sender = _get_sender()
        sender.send(
            subject=subject,
            sender=cfg["from_address"],
            receivers=clean,
            html=html_body,
        )
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

    safe_user = html.escape(username or "user")
    safe_msg = html.escape(custom_message.strip()) if custom_message.strip() else ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cfg = get_smtp_config()
    from_addr = html.escape(cfg.get("from_address") or "")

    body_parts = [
        "<p>This is a <strong>test email</strong> from Planning Suite.</p>",
        "<p>If you received this, SMTP is working and mail is being delivered.</p>",
        "<ul>",
        f"<li><strong>Sent at:</strong> {now}</li>",
        f"<li><strong>Triggered by:</strong> {safe_user}</li>",
        f"<li><strong>From:</strong> {from_addr}</li>",
        "</ul>",
    ]
    if safe_msg:
        body_parts.append(f"<p><strong>Your message:</strong><br>{safe_msg}</p>")
    body_parts.append(
        "<p style='color:#64748B;font-size:0.9em;'>Check spam/junk if you do not see this in inbox.</p>"
    )
    html_body = "\n".join(body_parts)

    subject = f"Planning Suite — test email ({now})"
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
        intro=f"Please update master systems for this launch.",
        fields={
            "Product": html.escape(product_name),
            "Type": html.escape(sub_type),
            "Launch date(s)": html.escape(dates_str),
            "Submission ID": f"<code>{safe_id}</code>",
        },
    )
    admin_html = build_email_html(
        headline=f"Approval required — {sub_type}",
        intro="A new launch submission needs admin review.",
        fields={
            "Product": html.escape(product_name),
            "Type": html.escape(sub_type),
            "Launch date(s)": html.escape(dates_str),
            "Submission ID": f"<code>{safe_id}</code>",
        },
        action="Open Planning Suite → <strong>New Product Launch</strong> → Submission History.",
    )

    meta = {"submission_id": sub_id, "submission_type": sub_type, "product_name": product_name}
    planner_result = send_email(
        category="launch_planner",
        subject=f"[Planning Suite] New {sub_type} — {product_name}",
        html_body=planner_html,
        triggered_by_user_id=triggered_by_user_id,
        metadata={**meta, "audience": "planner"},
        db=db,
    )
    admin_result = send_email(
        category="launch_admin",
        subject=f"[Planning Suite] Approval required — {sub_type}: {product_name}",
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
