"""
FF Input Sheet Change Watcher
==============================
Runs as a daemon thread on FastAPI startup. Polls the 'FF Input' tab of the
New Hub Launch Google Sheet every N seconds (default 45). On any change it:

  1. Computes a structured diff (added / removed / modified rows with cell-level detail).
  2. Appends a VersionEntry to the rolling change_history (max 20 kept in memory).
  3. Fires an email immediately via workflow_notifications.notify_ff_input_changed().
  4. Sets change_detected = True so the frontend poll endpoint can surface it instantly.

The diff engine uses `hub_name + "|" + source_hub` as a composite row key.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory state (process-local, reset on restart) ─────────────────────────
_state: dict[str, Any] = {
    "last_known_hash": None,
    "last_known_rows": [],        # list[dict]  — latest snapshot
    "change_detected": False,
    "last_checked_at": None,      # ISO 8601 UTC string
    "watcher_started": False,
    "change_history": [],         # list[VersionEntry dict] — newest first, max 20
    "poll_interval_seconds": 45,
}

_MAX_HISTORY = 20
_KEY_COLS = ("hub_name", "source_hub", "Hub_name", "Source_Hub")  # case-insensitive fallback

# ── Row key resolution ─────────────────────────────────────────────────────────

def _row_key(row: dict, headers: list[str]) -> str:
    """Build a composite key from hub_name + source_hub (case-insensitive header lookup)."""
    hub_col = next((h for h in headers if h.strip().lower() == "hub_name"), None)
    src_col = next((h for h in headers if h.strip().lower() == "source_hub"), None)
    hub_val = str(row.get(hub_col or "", "") or "").strip()
    src_val = str(row.get(src_col or "", "") or "").strip()
    return f"{hub_val.lower()}|{src_val.lower()}"


def _rows_hash(rows: list[dict]) -> str:
    serialized = json.dumps(
        [dict(sorted((k, str(v)) for k, v in r.items())) for r in rows],
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


# ── Diff engine ────────────────────────────────────────────────────────────────

def compute_diff(
    old_rows: list[dict],
    new_rows: list[dict],
    headers: list[str] | None = None,
) -> dict:
    """
    Returns a structured diff between two row snapshots:
      {
        added:    [row_dict, ...],
        removed:  [row_dict, ...],
        modified: [{ key, before: {col: val}, after: {col: val}, changed_cells: [col] }, ...],
        unchanged_count: int,
      }
    """
    if not headers:
        headers = list({k for r in old_rows + new_rows for k in r.keys()})

    old_by_key = {_row_key(r, headers): r for r in old_rows}
    new_by_key = {_row_key(r, headers): r for r in new_rows}

    added_keys   = set(new_by_key) - set(old_by_key)
    removed_keys = set(old_by_key) - set(new_by_key)
    common_keys  = set(old_by_key) & set(new_by_key)

    added   = [new_by_key[k] for k in added_keys]
    removed = [old_by_key[k] for k in removed_keys]

    modified = []
    unchanged_count = 0
    for key in common_keys:
        old_row = old_by_key[key]
        new_row = new_by_key[key]
        changed_cells = [
            col for col in set(list(old_row.keys()) + list(new_row.keys()))
            if str(old_row.get(col, "")).strip() != str(new_row.get(col, "")).strip()
        ]
        if changed_cells:
            modified.append({
                "key": key,
                "before": {c: str(old_row.get(c, "")).strip() for c in changed_cells},
                "after":  {c: str(new_row.get(c, "")).strip() for c in changed_cells},
                "row":    new_row,
                "changed_cells": changed_cells,
            })
        else:
            unchanged_count += 1

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged_count": unchanged_count,
    }


def _diff_summary(diff: dict) -> str:
    parts = []
    if diff["added"]:
        parts.append(f"{len(diff['added'])} added")
    if diff["removed"]:
        parts.append(f"{len(diff['removed'])} removed")
    if diff["modified"]:
        parts.append(f"{len(diff['modified'])} modified")
    return ", ".join(parts) if parts else "no changes"


# ── State accessors ────────────────────────────────────────────────────────────

def get_change_status() -> dict:
    """Return current watcher state — called by API endpoint."""
    from planning_suite.db.engine import get_shared_database
    db = get_shared_database()
    
    db_status = db.get_latest_hub_launch_status()
    db_history = db.get_hub_launch_versions(limit=_MAX_HISTORY)
    
    return {
        "change_detected": db_status.get("change_detected", False),
        "change_history":  db_history,
        "last_checked_at": _state["last_checked_at"],
        "watcher_started": _state["watcher_started"],
        "poll_interval_seconds": _state["poll_interval_seconds"],
    }


def dismiss_changes() -> None:
    """Clear the change_detected flag (history persists)."""
    from planning_suite.db.engine import get_shared_database
    db = get_shared_database()
    db.dismiss_hub_launch_alerts()
    _state["change_detected"] = False


# ── Background poll loop ───────────────────────────────────────────────────────

def _poll_once() -> None:
    """Single poll: fetch FF Input, compare hash, emit diff + email on change."""
    t0 = time.perf_counter()
    try:
        from planning_suite.services.sheets_session import get_sheets_manager

        gsm = get_sheets_manager()
        # Always bypass cache for the watcher — we WANT the live sheet data
        ff_df = gsm.read_worksheet_uncached("new_hub_launch", "ff_input", "A:H", use_cache=False)

        if ff_df is None or ff_df.empty:
            # Fallback: direct batch read
            from planning_suite import config as cfg
            raw = gsm.batch_read_worksheets(cfg.NEW_HUB_LAUNCH_SHEET_KEY, [("FF Input", "A:H")])
            data = raw.get("FF Input") or []
            if len(data) >= 2:
                import pandas as pd
                from planning_suite.core.dataframe import clean_sheet_df
                ff_df = clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))

        if ff_df is None or ff_df.empty:
            logger.debug("[FFWatcher] FF Input sheet is empty or unreadable — skipping diff")
            return

        ff_df = ff_df.dropna(how="all")
        headers = list(ff_df.columns)
        new_rows: list[dict] = ff_df.where(ff_df.notna(), "").to_dict(orient="records")
        new_hash = _rows_hash(new_rows)

        elapsed = round((time.perf_counter() - t0) * 1000)
        _state["last_checked_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if _state["last_known_hash"] is None:
            # First run — initialise baseline, don't fire email
            _state["last_known_hash"] = new_hash
            _state["last_known_rows"] = new_rows
            logger.info("[FFWatcher] Baseline snapshot stored — %d rows (%dms)", len(new_rows), elapsed)
            return

        if new_hash == _state["last_known_hash"]:
            logger.debug("[FFWatcher] No change detected (%dms)", elapsed)
            return

        # ── Change detected ────────────────────────────────────────────────────
        diff = compute_diff(_state["last_known_rows"], new_rows, headers)
        summary = _diff_summary(diff)
        detected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        version_id = f"v{int(time.time())}"

        version_entry = {
            "version_id": version_id,
            "detected_at": detected_at,
            "summary": summary,
            "diff": diff,
            "row_count_before": len(_state["last_known_rows"]),
            "row_count_after": len(new_rows),
            "headers": headers,
        }

        # Persist version entry to database for shared session persistence
        try:
            from planning_suite.db.engine import get_shared_database
            db = get_shared_database()
            db.save_hub_launch_version(
                version_id=version_id,
                detected_at=detected_at,
                summary=summary,
                diff=diff,
                row_count_before=len(_state["last_known_rows"]),
                row_count_after=len(new_rows),
                headers=headers
            )
        except Exception as e:
            logger.warning("[FFWatcher] Failed to persist change version in DB: %s", e)

        # Prepend (newest first), keep max 20 as in-memory backup
        _state["change_history"] = ([version_entry] + _state["change_history"])[:_MAX_HISTORY]
        _state["change_detected"] = True
        _state["last_known_hash"] = new_hash
        _state["last_known_rows"] = new_rows

        logger.info(
            "[FFWatcher] Change detected in FF Input: %s — firing email (%dms)",
            summary, elapsed,
        )

        # ── Fire email immediately in a short-lived thread ─────────────────────
        threading.Thread(
            target=_send_change_email,
            args=(version_entry,),
            daemon=True,
            name="ff-watcher-email",
        ).start()

    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000)
        logger.warning("[FFWatcher] Poll failed in %dms: %s", elapsed, exc)


def _send_change_email(version_entry: dict) -> None:
    """Fire email notification for a detected FF Input change."""
    try:
        from planning_suite.services.workflow_notifications import notify_ff_input_changed
        notify_ff_input_changed(version_entry)
    except Exception as exc:
        logger.error("[FFWatcher] Email send failed: %s", exc)


def _poll_loop(interval_seconds: int) -> None:
    """Infinite daemon loop — runs forever, polls every `interval_seconds`."""
    logger.info("[FFWatcher] Started — polling every %ds", interval_seconds)
    _state["watcher_started"] = True
    _state["poll_interval_seconds"] = interval_seconds

    # First poll after a short startup delay (let app finish init)
    time.sleep(10)
    _poll_once()

    while True:
        time.sleep(interval_seconds)
        _poll_once()


# ── Public entry point ─────────────────────────────────────────────────────────

def start_ff_input_watcher(interval_seconds: int = 45) -> None:
    """Start the background FF Input watcher daemon thread (call once at startup)."""
    import os
    if os.getenv("DISABLE_FF_WATCHER", "").strip().lower() in {"1", "true", "yes"}:
        logger.info("[FFWatcher] Disabled via DISABLE_FF_WATCHER env var")
        return

    if _state["watcher_started"]:
        logger.warning("[FFWatcher] Already running — skipping duplicate start")
        return

    t = threading.Thread(
        target=_poll_loop,
        args=(interval_seconds,),
        daemon=True,
        name="ff-input-watcher",
    )
    t.start()
