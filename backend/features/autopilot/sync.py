"""Detect Auto-Pilot step completion from manual workflow artifacts (fast, parallel)."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from features.autopilot.ui_config import AUTOPILOT_STEPS

from app.config import DP_LOGICS_FOLDER, FF_MASTERS_XLSX, OUTPUT_PATH
from core.database.engine import Database

from features.baseline.manual import DP_LOGICS_WORKSHEETS


ACTIVE_DATASET = OUTPUT_PATH / "active_dataset.parquet"
_FRESH_DAYS = int(os.getenv("MANUAL_SYNC_FRESH_DAYS", "21"))


@dataclass(frozen=True)
class StepProbe:
    index: int
    key: str
    detected: bool
    confidence: str  # high | medium | low
    message: str
    evidence: str = ""


def _mtime_age_days(path: Path) -> float | None:
    try:
        if not path.is_file():
            return None
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return (datetime.now(timezone.utc) - mtime).total_seconds() / 86400
    except OSError:
        return None


def _fresh_enough(path: Path, *, max_days: int = _FRESH_DAYS) -> bool:
    age = _mtime_age_days(path)
    return age is not None and age <= max_days


def _probe_master_sync() -> StepProbe:
    idx, key = 0, "master_sync"
    path = Path(FF_MASTERS_XLSX)
    if not path.is_file() or path.stat().st_size < 4096:
        return StepProbe(idx, key, False, "low", "Product_Masters.xlsx not found or empty.", str(path))

    verify_tabs = os.getenv("MANUAL_SYNC_VERIFY_TABS", "").strip().lower() in {"1", "true", "yes"}
    if not verify_tabs:
        fresh = _fresh_enough(path)
        kb = path.stat().st_size // 1024
        msg = f"Product_Masters.xlsx found ({kb} KB)."
        if not fresh:
            msg += " File may be stale — consider re-syncing masters."
        return StepProbe(idx, key, True, "high" if fresh else "medium", msg, str(path))

    try:
        import pandas as pd

        tabs = set(pd.ExcelFile(path).sheet_names)
        required = {"P Master", "P-H Master", "Hub Mapping"}
        missing = sorted(required - tabs)
        if missing:
            return StepProbe(
                idx,
                key,
                False,
                "medium",
                f"Masters file exists but missing tabs: {', '.join(missing)}.",
                path.name,
            )
        fresh = _fresh_enough(path)
        msg = f"Product_Masters.xlsx ready ({len(tabs)} tabs)."
        if not fresh:
            msg += " File may be stale — consider re-syncing masters."
        return StepProbe(idx, key, True, "high" if fresh else "medium", msg, str(path))
    except Exception as exc:
        return StepProbe(
            idx,
            key,
            path.stat().st_size > 4096,
            "medium",
            "Masters Excel found (could not read tabs).",
            str(exc)[:120],
        )


def _probe_new_product_launch(db: Database) -> StepProbe:
    idx, key = 1, "new_product_launch"
    try:
        from sqlalchemy import text

        with db.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT master_type, sync_date, status
                    FROM master_sync_log
                    WHERE status = 'success'
                      AND (
                        LOWER(COALESCE(master_type, '')) LIKE '%ph%'
                        OR LOWER(COALESCE(master_type, '')) LIKE '%product%launch%'
                        OR LOWER(COALESCE(master_type, '')) LIKE '%npl%'
                      )
                    ORDER BY sync_date DESC
                    LIMIT 1
                """)
            ).fetchone()
        if row:
            mtype = row._mapping.get("master_type") or "sync"
            when = row._mapping.get("sync_date")
            return StepProbe(
                idx,
                key,
                True,
                "high",
                f"Recent P-H / launch sync logged ({mtype}).",
                str(when) if when else "",
            )
    except Exception:
        pass

    masters = Path(FF_MASTERS_XLSX)
    if masters.is_file() and _fresh_enough(masters):
        return StepProbe(
            idx,
            key,
            False,
            "low",
            "Masters present but no recent P-H sync in history — run Product Launch sync if needed.",
            "",
        )
    return StepProbe(
        idx,
        key,
        False,
        "low",
        "No successful P-H / new-product sync found in master sync history.",
        "Master Data or Product Launch → Sync to P-H Master",
    )


def _probe_pull_raw_data() -> StepProbe:
    idx, key = 2, "pull_raw_data"
    if not ACTIVE_DATASET.is_file() or ACTIVE_DATASET.stat().st_size < 128:
        return StepProbe(
            idx,
            key,
            False,
            "low",
            "Active dataset not built yet.",
            str(ACTIVE_DATASET),
        )
    fresh = _fresh_enough(ACTIVE_DATASET)
    meta_path = OUTPUT_PATH / "active_dataset_meta.json"
    extra = ""
    if meta_path.is_file():
        try:
            import json

            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            weeks = meta.get("weeks") or []
            if weeks:
                extra = f" Weeks: {weeks[-3:] if len(weeks) > 3 else weeks}."
        except Exception:
            pass
    msg = f"active_dataset.parquet found ({ACTIVE_DATASET.stat().st_size // 1024} KB).{extra}"
    if not fresh:
        msg += " Dataset may be stale — re-run Load Raw Data if this is a new week."
    return StepProbe(idx, key, True, "high" if fresh else "medium", msg, str(ACTIVE_DATASET))


def _probe_sync_config() -> StepProbe:
    idx, key = 3, "sync_config"
    folder = Path(DP_LOGICS_FOLDER)
    if not folder.is_dir():
        return StepProbe(idx, key, False, "low", "DP Logics folder not found.", str(folder))
    missing = [ws for ws in DP_LOGICS_WORKSHEETS if not (folder / f"{ws}.xlsx").is_file()]
    if missing:
        return StepProbe(
            idx,
            key,
            False,
            "low",
            f"Missing DP Logics files: {', '.join(missing)}.",
            str(folder),
        )
    ages = [_mtime_age_days(folder / f"{ws}.xlsx") for ws in DP_LOGICS_WORKSHEETS]
    stale = [DP_LOGICS_WORKSHEETS[i] for i, a in enumerate(ages) if a is None or a > _FRESH_DAYS]
    fresh = not stale
    msg = f"All {len(DP_LOGICS_WORKSHEETS)} DP Logics worksheets on disk."
    if stale:
        msg += f" Stale: {', '.join(stale)}."
    return StepProbe(idx, key, True, "high" if fresh else "medium", msg, str(folder))


def _probe_run_engine(db: Database) -> StepProbe:
    idx, key = 4, "run_engine"
    from core.shared.pipeline_flow import _check_baseline_completed


    result = _check_baseline_completed(db)
    detected = result.status == "passed"
    return StepProbe(
        idx,
        key,
        detected,
        "high" if detected else "low",
        result.message,
        result.error_detail or "",
    )


def _probe_notify(db: Database) -> StepProbe:
    idx, key = 5, "notify"
    try:
        from sqlalchemy import text

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        with db.engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT subject, sent_at, status
                    FROM email_log
                    WHERE status = 'sent'
                      AND (
                        LOWER(COALESCE(email_type, '')) LIKE '%autopilot%'
                        OR LOWER(COALESCE(subject, '')) LIKE '%auto-pilot%'
                        OR LOWER(COALESCE(subject, '')) LIKE '%baseline%complete%'
                      )
                      AND sent_at >= :cutoff
                    ORDER BY sent_at DESC
                    LIMIT 1
                """),
                {"cutoff": cutoff},
            ).fetchone()
        if row:
            return StepProbe(
                idx,
                key,
                True,
                "medium",
                "Recent pipeline notification email sent.",
                str(row._mapping.get("sent_at") or ""),
            )
    except Exception:
        pass
    return StepProbe(
        idx,
        key,
        False,
        "low",
        "No recent notification email detected (optional step).",
        "",
    )


def _contiguous_completed(probes: list[StepProbe]) -> list[int]:
    """Longest prefix of steps 0..n-1 all detected (step 6 optional — does not block prefix)."""
    completed: list[int] = []
    for probe in probes:
        if probe.index == 5:
            break
        if probe.detected:
            completed.append(probe.index)
        else:
            break
    return completed


def detect_manual_autopilot_progress(db: Database) -> dict[str, Any]:
    """Run all step probes in parallel; return UI-ready payload."""
    probes: list[StepProbe | None] = [None] * len(AUTOPILOT_STEPS)

    def _run(fn, *args):
        return fn(*args)

    tasks = {
        0: (_probe_master_sync, ()),
        1: (_probe_new_product_launch, (db,)),
        2: (_probe_pull_raw_data, ()),
        3: (_probe_sync_config, ()),
        4: (_probe_run_engine, (db,)),
        5: (_probe_notify, (db,)),
    }

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="manual-sync") as pool:
        futures = {pool.submit(_run, fn, *args): idx for idx, (fn, args) in tasks.items()}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                probes[idx] = fut.result()
            except Exception as exc:
                probes[idx] = StepProbe(
                    idx,
                    AUTOPILOT_STEPS[idx]["key"],
                    False,
                    "low",
                    "Check failed.",
                    str(exc)[:160],
                )

    ordered = sorted([p for p in probes if p is not None], key=lambda p: p.index)
    completed = _contiguous_completed(ordered)
    suggested = len(completed)
    if suggested >= len(AUTOPILOT_STEPS):
        suggested = len(AUTOPILOT_STEPS) - 1

    step_payload = [
        {
            "index": p.index,
            "key": p.key,
            "name": AUTOPILOT_STEPS[p.index]["name"],
            "detected": p.detected,
            "confidence": p.confidence,
            "message": p.message,
            "evidence": p.evidence,
        }
        for p in ordered
    ]

    summary = (
        f"Detected {len(completed)} manual step(s) complete."
        if completed
        else "No manual progress detected — start from step 1."
    )
    if completed and suggested < len(AUTOPILOT_STEPS):
        summary += f" Suggested start: step {suggested + 1}."

    return {
        "completed_steps": completed,
        "suggested_from_step": suggested,
        "steps": step_payload,
        "summary": summary,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
