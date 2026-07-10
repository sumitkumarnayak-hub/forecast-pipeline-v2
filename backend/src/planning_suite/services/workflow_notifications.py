"""High-level workflow email alerts (baseline, final plan, pipeline, launch)."""
from __future__ import annotations

import html
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from planning_suite.config import is_smtp_configured
from planning_suite.db.engine import Database
from planning_suite.services.email_service import (
    build_email_html,
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
            intro="The automated 6-step pipeline finished successfully.",
            fields={
                "Run": f"<code>{_esc(run_id)}</code>",
                "Name": _esc(run_name),
                "Status": "Completed",
            },
            action="Open Planning Suite → <strong>Baseline</strong> (Auto-Pilot tab) to review the run log.",
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
        intro=f"The automated pipeline stopped at <strong>{step_label}</strong>.",
        fields={
            "Run": f"<code>{_esc(run_id)}</code>",
            "Name": _esc(run_name),
            "Status": "Failed",
            "Failed step": step_label,
        },
        error_block=error_detail,
        action="Open Planning Suite → <strong>Baseline</strong> and click <strong>Try again</strong>.",
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
                "Run": f"<code>{_esc(run_id)}</code>",
                "Name": _esc(run_name),
                "Status": "Completed — awaiting approval",
            },
            action="Open Planning Suite → <strong>Baseline</strong> → Manual workflow → "
            "<strong>Approve</strong>.",
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
        intro="The baseline generation script did not complete successfully.",
        fields={
            "Run": f"<code>{_esc(run_id)}</code>",
            "Name": _esc(run_name),
            "Status": "Failed",
        },
        error_block=error_detail,
        action="Open Planning Suite → <strong>Baseline</strong> to review logs and re-run.",
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
            "Run": f"<code>{_esc(run_id)}</code>",
            "Name": _esc(run_name),
            "Approved by": _esc(approver_name or approver_id or "—"),
        },
        action="Open Planning Suite → <strong>Final Plan</strong> to sync inputs and run.",
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
                "Run": f"<code>{_esc(run_id)}</code>",
                "Name": _esc(run_name),
                "Output": _esc(output_file or "—"),
            },
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
        intro="The final plan script did not complete successfully.",
        fields={
            "Run": f"<code>{_esc(run_id)}</code>",
            "Name": _esc(run_name),
            "Status": "Failed",
        },
        error_block=error_detail,
        action="Open Planning Suite → <strong>Final Plan</strong> to review inputs and re-run.",
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
        "Run": f"<code>{_esc(run_id)}</code>",
        "Result": _esc(status.upper()),
        "Passed": f"{passed}/{total}",
        "Failed steps": _esc(", ".join(failed_steps) if failed_steps else "—"),
        "Manual steps": str(manual),
    }

    if status == "failed":
        headline = "Pipeline audit — blockers found"
        intro = "One or more pipeline checks failed. The weekly flow cannot proceed until fixed."
        action = "Open Planning Suite → <strong>Baseline</strong> for details."
    else:
        headline = "Pipeline audit — manual action required"
        intro = "Pipeline checks passed partially. Some steps need human action (e.g. approval)."
        action = "Open Planning Suite → <strong>Baseline</strong> and complete manual steps."
        if needs_approval:
            action += " Baseline may need <strong>admin approval</strong>."

    html_body = build_email_html(
        headline=headline,
        intro=intro,
        fields=fields,
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
            fields={"Pipeline run": f"<code>{_esc(run_id)}</code>"},
            action="Open <strong>Baseline</strong> → Manual workflow → Approve.",
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
        error_block = issues_text if issues_text else ""
        if error_block:
            intro += " Warnings were recorded — see details below."
    else:
        headline = "Validation failed"
        intro = "A data validation check found errors that need review."
        subject = f"[Planning Suite] Validation FAILED — {validation_type}"
        error_block = issues_text or "Validation failed (no detail recorded)."

    html_body = build_email_html(
        headline=headline,
        intro=intro,
        fields={
            "Run / ref": f"<code>{_esc(run_id)}</code>",
            "Type": _esc(validation_type.replace("_", " ").title()),
            "Result": "Pass" if passed else "Fail",
        },
        error_block=error_block if not passed or issues_text else "",
        action="Open Planning Suite → <strong>Validation</strong> to review and re-run checks.",
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

    if passed:
        headline = f"Master Data Sync Success — {master_type.replace('_', ' ').title()}"
        intro = f"The master data sync for {master_type} completed successfully."
        subject = f"[Planning Suite] Master Sync SUCCESS — {master_type}"
    else:
        headline = f"Master Data Sync Failure — {master_type.replace('_', ' ').title()}"
        intro = f"The master data sync for {master_type} failed."
        subject = f"[Planning Suite] Master Sync FAILED — {master_type}"

    html_body = build_email_html(
        headline=headline,
        intro=intro,
        fields={
            "Master Type": _esc(master_type.replace("_", " ").title()),
            "Records Synced": str(records_synced),
            "Status": "Success" if passed else "Fail",
        },
        error_block=error_message if not passed else "",
        action="Open Planning Suite → <strong>Master Data Management</strong> to view sync history.",
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
        headline=f"NPL step failed — {step_name}",
        intro=(
            f"A <strong>{_esc(sub_type)}</strong> launch wizard step failed "
            "and could not complete. A planner may need to retry."
        ),
        fields={
            "Step": _esc(step_name),
            "Launch type": _esc(sub_type),
            "Product": _esc(product_name) if product_name else "—",
        },
        error_block=error[:2000],
        action=(
            "Open Planning Suite → <strong>Product Launch</strong> and retry "
            "the failed step. If the error persists, check the backend logs."
        ),
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
        "Submission ID": f"<code>{_esc(sub_id)}</code>",
        "Launch Type": _esc(sub_type),
        "Product": _esc(product_name),
        "Product ID": _esc(product_id) if product_id else "—",
        "Cities": _esc(cities_label) if cities_label else "—",
        "Hub rows": str(hub_count),
        "Launch date(s)": _esc(date_label),
        "Submitted by": _esc(submitted_by) if submitted_by else "System",
    }

    # Pass pre-compiled HTML to build_email_html since build_email_html escapes intro
    success_html = build_email_html(
        headline="New launch plan synced to Masters",
        intro=f"A {sub_type} plan was successfully synced to the Google Sheet. Please update the master lists worksheets to reflect the new configs.",
        fields=fields,
        action=f"Open Planning Suite → <strong>Product Launch → Submission History</strong> to track status.",
    )
    success_result = _safe_operational_send(
        event="npl_submitted",
        category="launch_planner",
        subject=f"[Planning Suite] Sync Completed: Update Masters — {product_name} ({sub_type})",
        html_body=success_html,
        triggered_by_user_id=user_id,
        metadata={"sub_id": sub_id, "sub_type": sub_type},
        db=db,
    )

    approval_html = build_email_html(
        headline="Launch plan synced to Masters - Update required",
        intro=f"A new {sub_type} plan has been synced to target master sheets. Action Required: Please update the master worksheets to complete the launch setup.",
        fields=fields,
        action="Please update the master worksheets (P-H Master / Hub Mapping) as required.",
    )
    approval_result = _safe_operational_send(
        event="npl_approval_needed",
        category="launch_admin",
        subject=f"[Planning Suite] Sync Completed: Update Masters — {product_name} ({sub_type})",
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

def notify_ff_input_changed(version_entry: dict) -> NotifyResult:
    """
    Send an immediate email when the FF Input sheet changes are detected.
    version_entry = { detected_at, summary, diff: {added, removed, modified}, headers, ... }
    Uses a rich HTML email styled like Google Sheets version history.
    """
    import html as _html

    diff    = version_entry.get("diff", {})
    summary = version_entry.get("summary", "changes detected")
    det_at  = version_entry.get("detected_at", "")
    headers = version_entry.get("headers", [])
    before  = version_entry.get("row_count_before", 0)
    after   = version_entry.get("row_count_after", 0)

    # Format IST timestamp
    try:
        from datetime import datetime, timezone, timedelta
        IST = timezone(timedelta(hours=5, minutes=30))
        dt  = datetime.fromisoformat(det_at.replace("Z", "+00:00")).astimezone(IST)
        ts_str = dt.strftime("%d %b %Y, %I:%M:%S %p IST")
    except Exception:
        ts_str = det_at

    def _th(cols: list[str]) -> str:
        ths = "".join(
            f"<th style='padding:6px 10px;background:#F1F5F9;border:1px solid #E2E8F0;"
            f"font-size:11px;text-transform:uppercase;color:#64748B;white-space:nowrap;'>"
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
                    f"<span style='background:#FEF08A;border-radius:2px;padding:1px 3px;'>"
                    f"<del style='color:#EF4444;'>{old}</del>"
                    f" → <strong>{val}</strong></span>"
                )
            else:
                cell_html = val
            cells.append(
                f"<td style='padding:5px 10px;border:1px solid #E2E8F0;"
                f"background:{bg};color:{text};font-size:12px;'>{cell_html}</td>"
            )
        return "<tr>" + "".join(cells) + "</tr>"

    def _table_section(title: str, rows_html: str, cols: list[str], accent: str) -> str:
        if not rows_html:
            return ""
        return f"""
        <div style='margin-bottom:16px;'>
          <p style='margin:0 0 6px 0;font-weight:700;font-size:13px;color:{accent};'>{title}</p>
          <div style='overflow-x:auto;'>
            <table style='border-collapse:collapse;width:100%;font-family:Inter,monospace;'>
              {_th(cols)}
              {rows_html}
            </table>
          </div>
        </div>"""

    # Build row HTML for each change type
    added_html   = "".join(_row_html(r, headers, "#F0FDF4", "#166534")          for r in diff.get("added", []))
    removed_html = "".join(_row_html(r, headers, "#FEF2F2", "#991B1B")          for r in diff.get("removed", []))
    modified_html = "".join(
        _row_html(m["row"], headers, "#FFFBEB", "#92400E",
                  changed_cells=m["changed_cells"],
                  before_vals=m["before"])
        for m in diff.get("modified", [])
    )

    table_html = (
        _table_section(f"+ Added ({len(diff.get('added', []))}) rows",   added_html,    headers, "#16A34A")
        + _table_section(f"✕ Removed ({len(diff.get('removed', []))}) rows", removed_html,  headers, "#DC2626")
        + _table_section(f"~ Modified ({len(diff.get('modified', []))}) rows", modified_html, headers, "#D97706")
    )

    if not table_html.strip():
        table_html = "<p style='color:#64748B;'>No row-level diff available.</p>"

    html_body = f"""
    <div style='font-family:Inter,Segoe UI,sans-serif;max-width:680px;color:#0F172A;'>
      <div style='background:#1E293B;padding:16px 20px;border-radius:8px 8px 0 0;'>
        <h2 style='margin:0;font-size:1.1rem;color:#F8FAFC;'>
          📋 FF Input Sheet — Changes Detected
        </h2>
        <p style='margin:4px 0 0 0;font-size:0.8rem;color:#94A3B8;'>{ts_str}</p>
      </div>
      <div style='padding:16px 20px;border:1px solid #E2E8F0;border-top:none;border-radius:0 0 8px 8px;'>
        <p style='margin:0 0 12px 0;'>
          The <strong>FF Input</strong> tab of the New Hub Launch sheet has been updated.
          <strong>Please update the Master sheets accordingly.</strong>
        </p>
        <table style='border-collapse:collapse;margin:0 0 16px 0;'>
          <tr>
            <td style='padding:4px 10px 4px 0;color:#64748B;font-size:12px;font-weight:600;'>Summary</td>
            <td style='padding:4px 0;font-size:12px;font-weight:700;color:#0F172A;'>{_html.escape(summary)}</td>
          </tr>
          <tr>
            <td style='padding:4px 10px 4px 0;color:#64748B;font-size:12px;font-weight:600;'>Row count</td>
            <td style='padding:4px 0;font-size:12px;color:#475569;'>{before} → {after}</td>
          </tr>
          <tr>
            <td style='padding:4px 10px 4px 0;color:#64748B;font-size:12px;font-weight:600;'>Detected at</td>
            <td style='padding:4px 0;font-size:12px;color:#475569;'>{ts_str}</td>
          </tr>
        </table>
        <div style='margin-bottom:8px;'>
          <strong style='font-size:13px;'>Change Details:</strong>
          <p style='margin:4px 0 0 0;font-size:11px;color:#64748B;'>
            🟢 Green = added &nbsp;|&nbsp; 🔴 Red = removed &nbsp;|&nbsp; 🟡 Yellow = modified cell (old → new)
          </p>
        </div>
        {table_html}
        <p style='margin-top:16px;padding:12px;background:#EFF6FF;border-radius:8px;
                  border-left:4px solid #2563EB;font-size:12px;'>
          <strong>Action required:</strong> Open Planning Suite → <strong>Hub Launch</strong>
          and click <strong>Fetch &amp; Preview Sync Mappings</strong> to review the updated
          configuration before syncing to P-H Master.
        </p>
        <p style='margin-top:16px;font-size:11px;color:#94A3B8;'>
          Planning Suite · FF Input Change Watcher · {ts_str}
        </p>
      </div>
    </div>"""

    return _safe_operational_send(
        event="ff_input_changed",
        category="general",
        subject=f"[Hub Launch] FF Input sheet updated — {summary} ({ts_str})",
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
