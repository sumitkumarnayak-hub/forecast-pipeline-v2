"""High-level workflow email alerts (baseline, final plan, pipeline, launch)."""
from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import is_smtp_configured
from core.database.engine import Database

from core.shared.email import (
    build_email_html,
    build_master_links_card,
    build_sheet_change_email,
    get_recipient_emails,
    send_email,
    send_launch_notifications,
)

logger = logging.getLogger(__name__)


@dataclass
class NotifyResult:
    event: str
    sent: bool = False
    skipped: bool = False
    failed: bool = False
    detail: str = ""
    sub_results: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.sent and not self.failed


def _esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


def _mono(value: Any) -> str:
    return (
        f"<span style='font-family:ui-monospace,SFMono-Regular,Menlo,monospace;"
        f"font-size:13px;color:#1D1D1F;'>{_esc(value)}</span>"
    )



def category_has_recipients(category: str, db: Database | None = None) -> bool:
    db = db or Database()
    return bool(get_recipient_emails(db, category))


def operational_alerts_possible(db: Database | None = None) -> bool:
    if not is_smtp_configured():
        return False
    db = db or Database()
    for cat in ("pipeline", "approval", "validation", "general", "all"):
        if category_has_recipients(cat, db):
            return True
    return False


def user_wants_notifications(user_id: int | None, db: Database | None = None) -> bool:
    if not user_id:
        return True
    db = db or Database()
    prefs = db.get_user_preferences(user_id)
    return bool(prefs.get("email_notifications", True))


def _merge_result(target: NotifyResult, send_result: dict) -> None:
    target.sub_results.append(send_result)
    status = send_result.get("status", "")
    if status == "sent":
        target.sent = True
    elif status == "skipped":
        target.skipped = True
        if not target.detail:
            target.detail = send_result.get("error", "skipped")
    elif status == "failed":
        target.failed = True
        target.detail = send_result.get("error", "send failed")


def _safe_operational_send(
    *,
    event: str,
    category: str,
    subject: str,
    html_body: str,
    triggered_by_user_id: int | None,
    metadata: dict | None = None,
    db: Database | None = None,
) -> NotifyResult:
    result = NotifyResult(event=event)
    db = db or Database()

    if not is_smtp_configured():
        result.skipped = True
        result.detail = "SMTP not configured (FROM_EMAIL / FROM_EMAIL_APP_PASSWORD)."
        return result

    if not category_has_recipients(category, db):
        result.skipped = True
        result.detail = f"No enabled recipients for category '{category}'."
        return result

    try:
        send_result = send_email(
            category=category,
            subject=subject,
            html_body=html_body,
            triggered_by_user_id=triggered_by_user_id,
            metadata=metadata or {},
            db=db,
        )
        _merge_result(result, send_result)
    except Exception as exc:
        logger.exception("Email notification failed: %s", event)
        result.failed = True
        result.detail = str(exc)

    return result


def notify_autopilot_run_finished(
    *,
    run_id: str,
    run_name: str,
    status: str,
    user_id: int | None = None,
    error_detail: str = "",
    failed_step: int | None = None,
    step_name: str = "",
    db: Database | None = None,
) -> NotifyResult:
    """Email when Baseline Auto-Pilot completes or fails."""
    db = db or Database()
    meta = {
        "run_id": run_id,
        "run_name": run_name,
        "status": status,
        "run_type": "autopilot",
        "failed_step": failed_step,
        "step_name": step_name,
    }

    if status == "completed":
        html_body = build_email_html(
            headline="Pipeline completed",
            intro="The automated 6-step pipeline finished successfully. You can review the run log when ready.",
            fields={
                "Run": _mono(run_id),
                "Name": _esc(run_name),
                "Status": "Completed",
            },
            variant="success",
            badge="Pipeline",
            action="Open <strong>Planning Suite → Baseline → Auto-Pilot</strong> to review the run log.",
        )
        return _safe_operational_send(
            event="autopilot_completed",
            category="pipeline",
            subject=f"[Planning Suite] Pipeline completed — {run_name}",
            html_body=html_body,
            triggered_by_user_id=user_id,
            metadata=meta,
            db=db,
        )

    step_label = (
        f"Step {int(failed_step) + 1}: {_esc(step_name)}"
        if failed_step is not None and step_name
        else (f"Step {int(failed_step) + 1}" if failed_step is not None else "Unknown step")
    )
    html_body = build_email_html(
        headline="Pipeline failed",
        intro=f"The automated pipeline stopped at {step_label}. Review the error below and retry when fixed.",
        fields={
            "Run": _mono(run_id),
            "Name": _esc(run_name),
            "Status": "Failed",
            "Failed step": step_label,
        },
        error_block=error_detail,
        variant="error",
        badge="Pipeline",
        action="Open <strong>Planning Suite → Baseline</strong> and click <strong>Try again</strong>.",
    )
    return _safe_operational_send(
        event="autopilot_failed",
        category="pipeline",
        subject=f"[Planning Suite] Pipeline FAILED — {run_name}",
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata=meta,
        db=db,
    )


def notify_baseline_run_finished(
    *,
    run_id: str,
    run_name: str,
    status: str,
    user_id: int | None = None,
    error_detail: str = "",
    db: Database | None = None,
) -> NotifyResult:
    """Email on baseline completed (approval needed) or failed."""
    db = db or Database()
    meta = {"run_id": run_id, "run_name": run_name, "status": status}

    if status == "completed":
        html_body = build_email_html(
            headline="Baseline ready for approval",
            intro="A baseline run finished successfully and needs admin approval before Final Plan.",
            fields={
                "Run": _mono(run_id),
                "Name": _esc(run_name),
                "Status": "Completed — awaiting approval",
            },
            variant="warning",
            badge="Approval",
            action="Open <strong>Planning Suite → Baseline → Manual workflow</strong> and click <strong>Approve</strong>.",
        )
        return _safe_operational_send(
            event="baseline_completed",
            category="approval",
            subject=f"[Planning Suite] Baseline ready for approval — {run_name}",
            html_body=html_body,
            triggered_by_user_id=user_id,
            metadata=meta,
            db=db,
        )

    html_body = build_email_html(
        headline="Baseline run failed",
        intro="The baseline generation script did not complete successfully. Review the error below and re-run when fixed.",
        fields={
            "Run": _mono(run_id),
            "Name": _esc(run_name),
            "Status": "Failed",
        },
        error_block=error_detail,
        variant="error",
        badge="Baseline",
        action="Open <strong>Planning Suite → Baseline</strong> to review logs and re-run.",
    )
    return _safe_operational_send(
        event="baseline_failed",
        category="pipeline",
        subject=f"[Planning Suite] Baseline FAILED — {run_name}",
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata=meta,
        db=db,
    )


def notify_baseline_approved(
    *,
    run_id: str,
    run_name: str,
    approver_id: int | None = None,
    approver_name: str = "",
    db: Database | None = None,
) -> NotifyResult:
    """Email when admin approves baseline — Final Plan is unlocked."""
    html_body = build_email_html(
        headline="Baseline approved",
        intro="Baseline has been approved. Final Plan generation is now unlocked.",
        fields={
            "Run": _mono(run_id),
            "Name": _esc(run_name),
            "Approved by": _esc(approver_name or approver_id or "—"),
        },
        variant="success",
        badge="Approved",
        action="Open <strong>Planning Suite → Final Plan</strong> to sync inputs and run.",
    )
    return _safe_operational_send(
        event="baseline_approved",
        category="general",
        subject=f"[Planning Suite] Baseline approved — {run_name}",
        html_body=html_body,
        triggered_by_user_id=approver_id,
        metadata={"run_id": run_id, "run_name": run_name},
        db=db,
    )


def notify_final_plan_run_finished(
    *,
    run_id: str,
    run_name: str,
    status: str,
    user_id: int | None = None,
    output_file: str = "",
    error_detail: str = "",
    db: Database | None = None,
) -> NotifyResult:
    """Email on final plan failure (and optional success info)."""
    db = db or Database()
    meta = {"run_id": run_id, "run_name": run_name, "status": status}

    if status == "completed":
        html_body = build_email_html(
            headline="Final Plan completed",
            intro="The final plan / hub distribution run finished successfully.",
            fields={
                "Run": _mono(run_id),
                "Name": _esc(run_name),
                "Output": _esc(output_file or "—"),
            },
            variant="success",
            badge="Final Plan",
        )
        return _safe_operational_send(
            event="final_plan_completed",
            category="general",
            subject=f"[Planning Suite] Final Plan completed — {run_name}",
            html_body=html_body,
            triggered_by_user_id=user_id,
            metadata=meta,
            db=db,
        )

    html_body = build_email_html(
        headline="Final Plan run failed",
        intro="The final plan script did not complete successfully. Review the error below and re-run when fixed.",
        fields={
            "Run": _mono(run_id),
            "Name": _esc(run_name),
            "Status": "Failed",
        },
        error_block=error_detail,
        variant="error",
        badge="Final Plan",
        action="Open <strong>Planning Suite → Final Plan</strong> to review inputs and re-run.",
    )
    return _safe_operational_send(
        event="final_plan_failed",
        category="pipeline",
        subject=f"[Planning Suite] Final Plan FAILED — {run_name}",
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata=meta,
        db=db,
    )


def notify_pipeline_audit_finished(
    *,
    run_id: str,
    status: str,
    summary: dict,
    user_id: int | None = None,
    db: Database | None = None,
) -> NotifyResult:
    """Email when pipeline audit fails, is partial, or has manual/approval blockers."""
    db = db or Database()

    if status == "completed":
        return NotifyResult(event="pipeline_completed", skipped=True, detail="All steps passed.")

    failed_steps = summary.get("failed_steps") or []
    manual = int(summary.get("manual", 0))
    passed = int(summary.get("passed", 0))
    total = int(summary.get("total_steps", 0))

    needs_approval = manual > 0 and any(
        "approv" in str(s).lower() for s in (summary.get("manual_steps") or [])
    )

    fields = {
        "Run": _mono(run_id),
        "Result": _esc(status.upper()),
        "Passed": f"{passed}/{total}",
        "Failed steps": _esc(", ".join(failed_steps) if failed_steps else "—"),
        "Manual steps": str(manual),
    }

    if status == "failed":
        headline = "Pipeline audit — blockers found"
        intro = "One or more pipeline checks failed. The weekly flow cannot proceed until fixed."
        action = "Open <strong>Planning Suite → Baseline</strong> for details."
        variant = "error"
        badge = "Audit"
    else:
        headline = "Pipeline audit — manual action required"
        intro = "Pipeline checks passed partially. Some steps need human action (e.g. approval)."
        action = "Open <strong>Planning Suite → Baseline</strong> and complete manual steps."
        if needs_approval:
            action += " Baseline may need <strong>admin approval</strong>."
        variant = "warning"
        badge = "Action needed"

    html_body = build_email_html(
        headline=headline,
        intro=intro,
        fields=fields,
        variant=variant,
        badge=badge,
        action=action,
    )

    result = _safe_operational_send(
        event="pipeline_audit",
        category="pipeline",
        subject=f"[Planning Suite] Pipeline audit {status.upper()} — {run_id}",
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata={"run_id": run_id, "summary": summary},
        db=db,
    )

    if needs_approval and category_has_recipients("approval", db):
        approval_html = build_email_html(
            headline="Baseline approval may be required",
            intro="The pipeline audit flagged baseline approval as a manual step.",
            fields={"Pipeline run": _mono(run_id)},
            variant="warning",
            badge="Approval",
            action="Open <strong>Planning Suite → Baseline → Manual workflow</strong> and click <strong>Approve</strong>.",
        )
        approval_result = _safe_operational_send(
            event="pipeline_approval_hint",
            category="approval",
            subject=f"[Planning Suite] Approval may be required — pipeline {run_id}",
            html_body=approval_html,
            triggered_by_user_id=user_id,
            metadata={"run_id": run_id, "source": "pipeline_audit"},
            db=db,
        )
        if approval_result.sent:
            result.sent = True
        result.sub_results.extend(approval_result.sub_results)

    return result


def notify_launch_submission(
    *,
    sub_id: str,
    sub_type: str,
    product_name: str,
    launch_dates: list[str],
    user_id: int | None = None,
    db: Database | None = None,
) -> dict:
    """
    Launch emails respecting user preference. Returns send_launch_notifications payload.
    """
    db = db or Database()
    if user_id and not user_wants_notifications(user_id, db):
        return {
            "ok": False,
            "skipped": True,
            "reason": "User disabled email notifications in Settings.",
            "planner": {"status": "skipped"},
            "admin": {"status": "skipped"},
        }

    if not is_smtp_configured():
        return {
            "ok": False,
            "skipped": True,
            "reason": "SMTP not configured.",
            "planner": {"status": "skipped"},
            "admin": {"status": "skipped"},
        }

    try:
        return send_launch_notifications(
            sub_id=sub_id,
            sub_type=sub_type,
            product_name=product_name,
            launch_dates=launch_dates,
            triggered_by_user_id=user_id,
            db=db,
        )
    except Exception as exc:
        logger.exception("Launch notification failed")
        return {
            "ok": False,
            "failed": True,
            "reason": str(exc),
            "planner": {"status": "failed", "error": str(exc)},
            "admin": {"status": "failed", "error": str(exc)},
        }


def _format_validation_issues(errors_found: Any) -> str:
    if not errors_found:
        return ""
    if isinstance(errors_found, list):
        return "\n".join(f"• {item}" for item in errors_found)[:3000]
    if isinstance(errors_found, str):
        try:
            parsed = json.loads(errors_found)
            if isinstance(parsed, list):
                return "\n".join(f"• {item}" for item in parsed)[:3000]
        except Exception:
            pass
        return errors_found[:3000]
    return str(errors_found)[:3000]


def notify_validation_result(
    *,
    run_id: str,
    validation_type: str,
    passed: bool,
    errors_found: Any = None,
    user_id: int | None = None,
    db: Database | None = None,
) -> NotifyResult:
    """Email after a validation run (pass or fail) — category: validation."""
    db = db or Database()
    issues_text = _format_validation_issues(errors_found)
    meta = {
        "run_id": run_id,
        "validation_type": validation_type,
        "passed": passed,
    }

    if passed:
        headline = "Validation passed"
        intro = "A data validation check completed with no blocking errors."
        subject = f"[Planning Suite] Validation PASSED — {validation_type}"
        variant = "success"
        badge = "Validation"
        error_block = ""
        info_block = issues_text if issues_text else ""
        if info_block:
            intro += " Some warnings were recorded — see notes below."
    else:
        headline = "Validation failed"
        intro = "A data validation check found errors that need review."
        subject = f"[Planning Suite] Validation FAILED — {validation_type}"
        variant = "error"
        badge = "Validation"
        error_block = issues_text or "Validation failed (no detail recorded)."
        info_block = ""

    html_body = build_email_html(
        headline=headline,
        intro=intro,
        fields={
            "Run / ref": _mono(run_id),
            "Type": _esc(validation_type.replace("_", " ").title()),
            "Result": "Pass" if passed else "Fail",
        },
        error_block=error_block,
        info_block=info_block,
        variant=variant,
        badge=badge,
        action="Open <strong>Planning Suite → Validation</strong> to review and re-run checks.",
    )
    return _safe_operational_send(
        event="validation_pass" if passed else "validation_fail",
        category="validation",
        subject=subject,
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata=meta,
        db=db,
    )


def format_error_from_parameters(parameters: Any) -> str:
    """Extract readable error text from baseline run parameters JSON."""
    if not parameters:
        return ""
    if isinstance(parameters, str):
        try:
            parameters = json.loads(parameters)
        except Exception:
            return parameters[:2000]
    if not isinstance(parameters, dict):
        return str(parameters)[:2000]
    parts = []
    for key in ("error", "stderr", "stdout_tail"):
        if parameters.get(key):
            parts.append(f"{key}:\n{parameters[key]}")
    return "\n\n".join(parts)[:3000]


def format_final_plan_error(summary_stats: Any) -> str:
    if not summary_stats:
        return ""
    if isinstance(summary_stats, str):
        try:
            summary_stats = json.loads(summary_stats)
        except Exception:
            return summary_stats[:2000]
    if not isinstance(summary_stats, dict):
        return str(summary_stats)[:2000]
    parts = []
    if summary_stats.get("exit_code") is not None:
        parts.append(f"exit_code: {summary_stats['exit_code']}")
    if summary_stats.get("error"):
        parts.append(str(summary_stats["error"]))
    if summary_stats.get("log_tail"):
        parts.append(str(summary_stats["log_tail"]))
    return "\n".join(parts)[:3000]


def notify_master_sync_result(
    *,
    master_type: str,
    passed: bool,
    records_synced: int = 0,
    error_message: str = "",
    user_id: int | None = None,
    db: Database | None = None,
) -> NotifyResult:
    """Email after a master data sync/write run (pass or fail) — category: general."""
    db = db or Database()
    meta = {
        "master_type": master_type,
        "passed": passed,
        "records_synced": records_synced,
    }

    label = master_type.replace("_", " ").title()
    if passed:
        headline = f"Master sync completed — {label}"
        intro = f"The {label} master data sync finished successfully."
        subject = f"[Planning Suite] Master Sync SUCCESS — {master_type}"
        variant = "success"
        badge = "Master sync"
    else:
        headline = f"Master sync failed — {label}"
        intro = f"The {label} master data sync could not complete. Review the error below."
        subject = f"[Planning Suite] Master Sync FAILED — {master_type}"
        variant = "error"
        badge = "Master sync"

    html_body = build_email_html(
        headline=headline,
        intro=intro,
        fields={
            "Master type": _esc(label),
            "Records synced": str(records_synced),
            "Status": "Success" if passed else "Failed",
        },
        error_block=error_message if not passed else "",
        variant=variant,
        badge=badge,
        action="Open <strong>Planning Suite → Master Data Management</strong> to view sync history.",
    )
    return _safe_operational_send(
        event="master_sync_success" if passed else "master_sync_fail",
        category="general",
        subject=subject,
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata=meta,
        db=db,
    )


def notify_npl_step_failed(
    *,
    step_name: str,
    error: str,
    sub_type: str = "New Launch",
    product_name: str = "",
    user_id: int | None = None,
    db: Database | None = None,
) -> NotifyResult:
    """Send a failure alert when any NPL wizard step crashes."""
    db = db or Database()
    meta = {"step_name": step_name, "sub_type": sub_type, "error": error[:500]}
    html_body = build_email_html(
        headline=f"Wizard step failed — {step_name}",
        intro=(
            f"The {sub_type} launch wizard could not complete this step. "
            "Retry from Product Launch, or contact the planning team if it keeps failing."
        ),
        fields={
            "Step": _esc(step_name),
            "Launch type": _esc(sub_type),
            "Product": _esc(product_name) if product_name else "—",
        },
        error_block=error[:2000],
        variant="error",
        badge="Product Launch",
        action="Open <strong>Planning Suite → Product Launch</strong> and retry the failed step.",
    )
    return _safe_operational_send(
        event="npl_step_failed",
        category="pipeline",
        subject=f"[Planning Suite] NPL step FAILED — {step_name} ({sub_type})",
        html_body=html_body,
        triggered_by_user_id=user_id,
        metadata=meta,
        db=db,
    )


def notify_npl_submitted(
    *,
    sub_id: str,
    sub_type: str,
    product_name: str,
    product_id: str = "",
    launch_dates: list[str],
    cities: list[str] | None = None,
    hub_count: int = 0,
    submitted_by: str = "",
    user_id: int | None = None,
    db: Database | None = None,
) -> dict:
    """
    Two emails after a successful NPL submit:
      1. Success  → 'general' category  (submission confirmed)
      2. Approval → 'approval' category (admin action needed)
    Returns a combined dict with both statuses.
    """
    db = db or Database()

    if user_id and not user_wants_notifications(user_id, db):
        return {
            "ok": False, "skipped": True,
            "reason": "User disabled email notifications.",
            "success": {"status": "skipped"}, "approval": {"status": "skipped"},
        }
    if not is_smtp_configured():
        return {
            "ok": False, "skipped": True,
            "reason": "SMTP not configured.",
            "success": {"status": "skipped"}, "approval": {"status": "skipped"},
        }

    city_list = cities or []
    date_label = ", ".join(launch_dates) if launch_dates else "—"
    cities_label = ", ".join(city_list[:8])
    if len(city_list) > 8:
        cities_label += f", … (+{len(city_list) - 8} more)"

    fields = {
        "Submission ID": _mono(sub_id),
        "Launch Type": _esc(sub_type),
        "Product": _esc(product_name),
        "Product ID": _esc(product_id) if product_id else "—",
        "Cities": _esc(cities_label) if cities_label else "—",
        "Hub rows": str(hub_count),
        "Launch date(s)": _esc(date_label),
        "Submitted by": _esc(submitted_by) if submitted_by else "System",
    }

    # Build master update card once
    master_card = build_master_links_card()

    success_html = build_email_html(
        headline="Launch plan synced",
        intro="Your plan was written to the target Google Sheet. Update the master worksheets so the launch is reflected everywhere.",
        fields=fields,
        variant="success",
        badge="Synced",
        extra_html=master_card,
        action="Open <strong>Planning Suite → Product Launch → Submission History</strong> to track status.",
    )
    success_result = _safe_operational_send(
        event="npl_submitted",
        category="launch_planner",
        subject=f"[Planning Suite] Launch synced — update masters for {product_name} ({sub_type})",
        html_body=success_html,
        triggered_by_user_id=user_id,
        metadata={"sub_id": sub_id, "sub_type": sub_type},
        db=db,
    )

    approval_html = build_email_html(
        headline="Master updates needed",
        intro="A launch plan was synced successfully. Please complete the master worksheet updates to finish setup.",
        fields=fields,
        variant="warning",
        badge="Action needed",
        extra_html=master_card,
        action="Review the linked master sheets and update P Master, P-L Master, and Hub Mapping as required.",
    )
    approval_result = _safe_operational_send(
        event="npl_approval_needed",
        category="launch_admin",
        subject=f"[Planning Suite] Action needed — update masters for {product_name} ({sub_type})",
        html_body=approval_html,
        triggered_by_user_id=user_id,
        metadata={"sub_id": sub_id, "sub_type": sub_type},
        db=db,
    )

    return {
        "ok": success_result.sent or approval_result.sent,
        "success": {
            "status": "sent" if success_result.sent else ("skipped" if success_result.skipped else "failed"),
            "detail": success_result.detail,
        },
        "approval": {
            "status": "sent" if approval_result.sent else ("skipped" if approval_result.skipped else "failed"),
            "detail": approval_result.detail,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Hub Launch: FF Input Sheet Change Notification
# ─────────────────────────────────────────────────────────────────────────────

def _format_ist_timestamp(det_at: str) -> str:
    try:
        from datetime import datetime, timezone, timedelta
        ist = timezone(timedelta(hours=5, minutes=30))
        dt = datetime.fromisoformat(det_at.replace("Z", "+00:00")).astimezone(ist)
        return dt.strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return det_at


def _build_sheet_diff_table_html(diff: dict, headers: list[str]) -> str:
    import html as _html

    def _th(cols: list[str]) -> str:
        ths = "".join(
            f"<th style='padding:8px 10px;background:#F5F5F7;border-bottom:1px solid #E8E8ED;"
            f"font-size:11px;text-transform:uppercase;color:#86868B;white-space:nowrap;font-weight:600;'>"
            f"{_html.escape(c)}</th>"
            for c in cols
        )
        return f"<tr>{ths}</tr>"

    def _row_html(row: dict, cols: list[str], bg: str, text: str,
                  changed_cells: list[str] | None = None,
                  before_vals: dict | None = None) -> str:
        cells = []
        for c in cols:
            val = _html.escape(str(row.get(c, "")).strip())
            if changed_cells and c in changed_cells and before_vals:
                old = _html.escape(str(before_vals.get(c, "")).strip())
                cell_html = (
                    f"<span style='background:#FFF8E1;border-radius:6px;padding:2px 4px;'>"
                    f"<span style='color:#AEAEB2;text-decoration:line-through;'>{old}</span>"
                    f" <span style='color:#1D1D1F;font-weight:600;'>{val}</span></span>"
                )
            else:
                cell_html = val
            cells.append(
                f"<td style='padding:8px 10px;border-bottom:1px solid #F2F2F7;"
                f"background:{bg};color:{text};font-size:12px;'>{cell_html}</td>"
            )
        return "<tr>" + "".join(cells) + "</tr>"

    def _table_section(title: str, rows_html: str, cols: list[str]) -> str:
        if not rows_html:
            return ""
        return f"""
        <div style='margin-bottom:14px;'>
          <p style='margin:0 0 8px 0;font-weight:600;font-size:13px;color:#1D1D1F;'>{title}</p>
          <table style='border-collapse:collapse;width:100%;'>
            {_th(cols)}
            {rows_html}
          </table>
        </div>"""

    added_html = "".join(_row_html(r, headers, "#F3FBF5", "#1D1D1F") for r in diff.get("added", []))
    removed_html = "".join(_row_html(r, headers, "#FFF5F5", "#1D1D1F") for r in diff.get("removed", []))
    modified_html = "".join(
        _row_html(
            m["row"], headers, "#FFFCF2", "#1D1D1F",
            changed_cells=m["changed_cells"],
            before_vals=m["before"],
        )
        for m in diff.get("modified", [])
    )
    return (
        _table_section(f"Added ({len(diff.get('added', []))})", added_html, headers)
        + _table_section(f"Removed ({len(diff.get('removed', []))})", removed_html, headers)
        + _table_section(f"Modified ({len(diff.get('modified', []))})", modified_html, headers)
    )


def notify_ff_input_changed(version_entry: dict) -> NotifyResult:
    """
    Send an immediate email when the FF Input sheet changes are detected.
    """
    diff = version_entry.get("diff", {})
    summary = version_entry.get("summary", "changes detected")
    det_at = version_entry.get("detected_at", "")
    headers = version_entry.get("headers", [])
    before = version_entry.get("row_count_before", 0)
    after = version_entry.get("row_count_after", 0)
    ts_str = _format_ist_timestamp(det_at)

    html_body = build_sheet_change_email(
        headline="FF Input sheet updated",
        intro="The FF Input tab on the New Hub Launch sheet changed. Review the diff below and update master sheets before syncing.",
        summary=summary,
        detected_at=ts_str,
        row_count_before=before,
        row_count_after=after,
        diff_table_html=_build_sheet_diff_table_html(diff, headers),
        badge="Hub Launch",
        action="Open <strong>Planning Suite → Hub Launch</strong> and run <strong>Fetch & Preview Sync Mappings</strong> before syncing to P-H Master.",
    )

    return _safe_operational_send(
        event="ff_input_changed",
        category="general",
        subject=f"[Hub Launch] FF Input updated — {summary}",
        html_body=html_body,
        triggered_by_user_id=None,
        metadata={
            "summary": summary,
            "detected_at": det_at,
            "added_count": len(diff.get("added", [])),
            "removed_count": len(diff.get("removed", [])),
            "modified_count": len(diff.get("modified", [])),
        },
    )


def notify_hub_sku_master_changed(version_entry: dict) -> NotifyResult:
    """Send an immediate email when the Hub SKU Master sheet changes are detected."""
    diff = version_entry.get("diff", {})
    summary = version_entry.get("summary", "changes detected")
    det_at = version_entry.get("detected_at", "")
    headers = version_entry.get("headers", [])
    before = version_entry.get("row_count_before", 0)
    after = version_entry.get("row_count_after", 0)
    ts_str = _format_ist_timestamp(det_at)

    html_body = build_sheet_change_email(
        headline="Hub SKU Master updated",
        intro="The Hub SKU Master sheet changed. Review the diff below and confirm downstream planning sheets are still correct.",
        summary=summary,
        detected_at=ts_str,
        row_count_before=before,
        row_count_after=after,
        diff_table_html=_build_sheet_diff_table_html(diff, headers),
        badge="Hub SKU",
        action="Open <strong>Planning Suite → Hub Launch</strong> to review the updated Hub SKU Master configuration.",
    )

    return _safe_operational_send(
        event="hub_sku_master_changed",
        category="general",
        subject=f"[Hub Launch] Hub SKU Master updated — {summary}",
        html_body=html_body,
        triggered_by_user_id=None,
        metadata={
            "summary": summary,
            "detected_at": det_at,
            "added_count": len(diff.get("added", [])),
            "removed_count": len(diff.get("removed", [])),
            "modified_count": len(diff.get("modified", [])),
        },
    )
