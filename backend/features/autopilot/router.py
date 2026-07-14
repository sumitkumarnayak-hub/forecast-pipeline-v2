"""
Auto-Pilot router — 6-step pipeline with DB-backed state and SSE progress.
"""
from __future__ import annotations

import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, AsyncGenerator

_BOOTSTRAP_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="autopilot-bootstrap")

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, require_write, get_db
from features.autopilot.state import (
    get_resume_step,
    load_autopilot_history,
    load_autopilot_run,
    load_autopilot_state,
    tail_autopilot_log,
)
from features.autopilot.ui_config import AUTOPILOT_STEPS_UI, output_paths_reference

from features.autopilot.ui_config import AUTOPILOT_STEPS

from features.autopilot.optimized import run_optimized_autopilot

from core.utils.dataframe import df_to_records, sanitize_for_json

from core.security.permissions import can_write

from core.database.engine import Database

from core.shared.api_cache import CacheNS, cached, cache_get, cache_invalidate, cache_set

from core.shared.helpers import generate_run_id


router = APIRouter()

# run_id -> thread bookkeeping
_ACTIVE: dict[str, dict[str, Any]] = {}
_RUN_START_LOCK = threading.Lock()


def _any_run_in_progress() -> bool:
    return any(v.get("status") == "running" for v in _ACTIVE.values())


class RunRequest(BaseModel):
    action: str = Field(default="run", description="run | resume | retry | restart")
    from_step: int | None = None
    run_id: str | None = None


def _step_rows_from_state(state: dict | None, steps_config: list[dict]) -> list[dict]:
    logs = {}
    if state:
        raw = state.get("logs") or {}
        logs = {int(k): v for k, v in raw.items() if str(k).isdigit()}

    completed = set(state.get("completed_steps") or []) if state else set()
    failed_step = state.get("failed_step") if state else None
    status = state.get("status") if state else "idle"
    running = bool(
        state
        and state.get("run_id")
        and _ACTIVE.get(state["run_id"], {}).get("status") == "running"
    )

    rows: list[dict] = []
    all_done = bool(state and state.get("success"))
    for idx, cfg in enumerate(steps_config):
        if all_done or idx in completed:
            vis = "done"
        elif failed_step is not None and idx == failed_step:
            vis = "failed"
        elif running and idx == len(completed):
            vis = "running"
        elif idx > len(completed) and failed_step is None and not running:
            vis = "queued"
        elif idx > (failed_step if failed_step is not None else len(completed)):
            vis = "queued"
        else:
            vis = "ready"

        entry = logs.get(idx) or {}
        detail = entry.get("text") or entry.get("error_summary") or ""
        rows.append({
            "index": idx,
            "key": AUTOPILOT_STEPS[idx]["key"] if idx < len(AUTOPILOT_STEPS) else cfg.get("key", ""),
            "name": cfg.get("name", ""),
            "icon": cfg.get("icon", "•"),
            "status": vis,
            "detail": detail[:200],
        })
    return rows


def _ui_status(state: dict | None, *, running_ids: set[str]) -> str:
    if not state:
        return "idle"
    rid = state.get("run_id")
    if rid and rid in running_ids:
        return "running"
    if state.get("success"):
        return "success"
    if state.get("failed_step") is not None or state.get("status") == "failed":
        return "failed"
    if state.get("status") == "running":
        return "failed"
    if state.get("completed_steps"):
        return "running"
    return "idle"


def _resume_step_from_state(state: dict | None) -> int | None:
    if not state or state.get("success"):
        return None
    failed = state.get("failed_step")
    if failed is not None:
        return int(failed)
    completed = state.get("completed_steps") or []
    if completed:
        return len(completed)
    if state.get("status") in ("failed", "running"):
        return 0
    return None


def _step_index_from_state(state: dict | None, total: int) -> int:
    resume_step = _resume_step_from_state(state)
    ui_status = _ui_status(state, running_ids=set(_ACTIVE.keys()))
    step_idx = 0
    if state:
        if state.get("success"):
            step_idx = total
        elif state.get("failed_step") is not None:
            step_idx = int(state["failed_step"])
        elif state.get("completed_steps"):
            step_idx = len(state["completed_steps"])
        if resume_step is not None and ui_status == "idle":
            step_idx = resume_step
    return step_idx


def _progress_from_state(state: dict | None, total: int) -> int:
    if state and state.get("success"):
        return 100
    step_idx = _step_index_from_state(state, total)
    return int(min(100, round(step_idx / total * 100))) if total else 0


def _default_step_rows(steps_config: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for idx, cfg in enumerate(steps_config):
        rows.append({
            "index": idx,
            "key": AUTOPILOT_STEPS[idx]["key"] if idx < len(AUTOPILOT_STEPS) else cfg.get("key", ""),
            "name": cfg.get("name", ""),
            "icon": cfg.get("icon", "•"),
            "status": "ready",
            "detail": "",
        })
    return rows


def _build_bootstrap(
    user: dict,
    db: Database,
    *,
    state: dict | None = None,
    state_pending: bool = False,
    state_error: str = "",
) -> dict[str, Any]:
    role = user.get("role", "viewer")
    read_only = not can_write(role)
    steps_config = AUTOPILOT_STEPS_UI
    paths_ref = output_paths_reference()
    running_ids = set(_ACTIVE.keys())

    resume_step = _resume_step_from_state(state)
    ui_status = _ui_status(state, running_ids=running_ids)
    total = len(steps_config)
    step_idx = 0
    if state:
        if state.get("success"):
            step_idx = total
        elif state.get("failed_step") is not None:
            step_idx = int(state["failed_step"])
        elif state.get("completed_steps"):
            step_idx = len(state["completed_steps"])
        if resume_step is not None and ui_status == "idle":
            step_idx = resume_step

    pct = 100 if (state and state.get("success")) else (
        int(min(100, round(step_idx / total * 100))) if total else 0
    )

    from app import config as cfg


    payload: dict[str, Any] = {
        "read_only": read_only,
        "steps_config": steps_config,
        "autopilot_steps": AUTOPILOT_STEPS,
        "output_paths_reference": paths_ref,
        "output_paths": {
            "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
            "raw_actuals_folder": cfg.RAW_ACTUALS_FOLDER,
            "dp_logics_folder": cfg.DP_LOGICS_FOLDER,
            "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
            "pipeline_params_sheet_url": cfg.PIPELINE_PARAMS_SHEET_URL,
            "outputs_dir": str(cfg.OUTPUT_PATH),
        },
        "state": state,
        "ui_status": ui_status,
        "resume_step": resume_step,
        "step_idx": step_idx,
        "progress_pct": pct,
        "step_rows": _step_rows_from_state(state, steps_config) if state else _default_step_rows(steps_config),
        "run_log": "",
        "state_pending": state_pending,
    }
    if state_error:
        payload["state_error"] = state_error
    return sanitize_for_json(payload)
def _run_thread(run_id: str, user_id: int, from_step: int, run_name: str) -> None:
    try:
        result = run_optimized_autopilot(
            from_step=from_step,
            user_id=user_id,
            run_id=run_id,
            run_name=run_name,
            source="ui",
        )
        _ACTIVE[run_id] = {
            "status": "completed" if result.success else "failed",
            "error": result.error,
            "user_id": user_id,
        }
    except Exception as exc:
        _ACTIVE[run_id] = {"status": "failed", "error": str(exc), "user_id": user_id}
    finally:
        cache_invalidate(CacheNS.AUTOPILOT_BOOTSTRAP)
        cache_invalidate(CacheNS.AUTOPILOT_HISTORY)
        cache_invalidate(CacheNS.AUTOPILOT_MANUAL_SYNC)

        def _cleanup() -> None:
            entry = _ACTIVE.get(run_id)
            if entry and entry.get("status") != "running":
                _ACTIVE.pop(run_id, None)
        threading.Timer(300.0, _cleanup).start()


@router.get("/bootstrap")
def autopilot_bootstrap(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    refresh: bool = Query(False, description="Bypass short-lived bootstrap cache"),
):
    """Static Auto-Pilot shell (steps, paths, permissions) — no database calls."""
    user_key = str(current_user.get("sub", "anon"))
    cache_key = f"static:{user_key}"

    if not refresh:
        cached = cache_get(CacheNS.AUTOPILOT_BOOTSTRAP, cache_key)
        if cached is not None:
            return cached

    payload = _build_bootstrap(current_user, db, state=None)
    cache_set(CacheNS.AUTOPILOT_BOOTSTRAP, cache_key, payload, ttl=120.0)
    return payload


@router.get("/bootstrap/static")
def autopilot_bootstrap_static(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Alias for static bootstrap — instant first paint."""
    return _build_bootstrap(current_user, db, state=None)


@router.get("/manual-sync")
def manual_autopilot_sync(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    refresh: bool = Query(False, description="Bypass short-lived manual-sync cache"),
):
    """
    Detect which Auto-Pilot steps were completed via manual workflow (files + DB).
    Returns contiguous completed prefix and suggested ``from_step`` for the next run.
    """
    from features.autopilot.sync import detect_manual_autopilot_progress


    def _build() -> dict[str, Any]:
        return detect_manual_autopilot_progress(db)

    return cached(
        CacheNS.AUTOPILOT_MANUAL_SYNC,
        "global",
        _build,
        ttl=25.0,
        skip_cache=refresh,
    )


@router.get("/history")
def autopilot_history(
    limit: int = Query(30, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    refresh: bool = Query(False),
):
    cache_key = f"limit={limit}"
    if not refresh:
        cached = cache_get(CacheNS.AUTOPILOT_HISTORY, cache_key)
        if cached is not None:
            return cached

    df = load_autopilot_history(limit=limit)
    if df.empty:
        return {"rows": []}
    display = df.copy()
    if "started_at" in display.columns:
        display["started_at"] = display["started_at"].astype(str)
    if "completed_at" in display.columns:
        display["completed_at"] = display["completed_at"].astype(str)
    display = display.rename(columns={
        "run_id": "Run ID",
        "run_name": "Name",
        "status": "Status",
        "source": "Source",
        "username": "User",
        "started_at": "Started",
        "completed_at": "Completed",
        "steps_done": "Steps",
    })
    cols = [c for c in [
        "Run ID", "Name", "Status", "Steps", "User", "Started", "Completed", "Source",
    ] if c in display.columns]
    result = {"rows": df_to_records(display[cols])}
    if not _any_run_in_progress():
        cache_set(CacheNS.AUTOPILOT_HISTORY, cache_key, result, ttl=15.0)
    return result


@router.get("/runs/{run_id}/log")
def autopilot_run_log(run_id: str, current_user: dict = Depends(get_current_user)):
    text = tail_autopilot_log(run_id=run_id)
    return {"run_id": run_id, "log_text": text}


@router.get("/runs/{run_id}")
def autopilot_run_detail(run_id: str, current_user: dict = Depends(get_current_user)):
    detail = load_autopilot_run(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Run not found")
    return sanitize_for_json(detail)


@router.post("/run")
def start_autopilot(
    body: RunRequest,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    """Start or resume Auto-Pilot in a background thread. Returns run_id for SSE."""
    user_id = int(current_user["sub"])
    action = (body.action or "run").lower()
    state = load_autopilot_state()

    if action == "restart":
        from_step = 0
        run_id = generate_run_id("AUTOPILOT")
        run_name = "Auto-Pilot"
    elif action == "resume":
        resume = get_resume_step()
        if resume is None:
            raise HTTPException(status_code=400, detail="No partial run to resume")
        from_step = body.from_step if body.from_step is not None else resume
        run_id = body.run_id or (state.get("run_id") if state else None) or generate_run_id("AUTOPILOT")
        run_name = (state.get("run_name") if state else None) or "Auto-Pilot"
    elif action == "retry":
        if state is None or state.get("failed_step") is None:
            raise HTTPException(status_code=400, detail="No failed step to retry")
        from_step = int(state["failed_step"])
        run_id = body.run_id or state.get("run_id") or generate_run_id("AUTOPILOT")
        run_name = state.get("run_name") or "Auto-Pilot"
    else:
        from_step = body.from_step or 0
        run_id = generate_run_id("AUTOPILOT")
        run_name = "Auto-Pilot"

    if run_id in _ACTIVE and _ACTIVE[run_id].get("status") == "running":
        raise HTTPException(status_code=409, detail="Run already in progress")

    with _RUN_START_LOCK:
        # Drop stale in-memory locks when DB already recorded a terminal state
        for rid in list(_ACTIVE):
            if _ACTIVE[rid].get("status") != "running":
                continue
            detail = load_autopilot_run(rid)
            if detail and (
                detail.get("success")
                or detail.get("failed_step") is not None
                or detail.get("status") in ("completed", "failed")
            ):
                _ACTIVE.pop(rid, None)

        if _any_run_in_progress():
            raise HTTPException(
                status_code=409,
                detail="Another Auto-Pilot run is already in progress. Wait for it to finish.",
            )
        _ACTIVE[run_id] = {"status": "running", "user_id": user_id}
        cache_invalidate(CacheNS.AUTOPILOT_BOOTSTRAP)
        cache_invalidate(CacheNS.AUTOPILOT_HISTORY)
        cache_invalidate(CacheNS.AUTOPILOT_MANUAL_SYNC)

    db.ensure_autopilot_run(run_id, user_id, run_name=run_name, source="ui")

    t = threading.Thread(
        target=_run_thread,
        args=(run_id, user_id, from_step, run_name),
        daemon=True,
    )
    t.start()
    return {"run_id": run_id, "from_step": from_step, "action": action}


@router.get("/state")
def get_autopilot_state(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    refresh: bool = Query(False),
):
    """Latest Auto-Pilot run snapshot — may be slow; call after static bootstrap."""
    cache_key = "run-state"
    if not refresh and not _any_run_in_progress():
        cached = cache_get(CacheNS.AUTOPILOT_BOOTSTRAP, cache_key)
        if cached is not None:
            return cached

    try:
        future = _BOOTSTRAP_POOL.submit(load_autopilot_state)
        state = future.result(timeout=10.0)
    except FuturesTimeout:
        raise HTTPException(status_code=504, detail="Run state load timed out — try again")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    running_ids = set(_ACTIVE.keys())
    result = sanitize_for_json({
        "state": state,
        "ui_status": _ui_status(state, running_ids=running_ids),
        "resume_step": _resume_step_from_state(state),
        "step_rows": _step_rows_from_state(state, AUTOPILOT_STEPS_UI),
        "step_idx": _step_index_from_state(state, len(AUTOPILOT_STEPS_UI)),
        "progress_pct": _progress_from_state(state, len(AUTOPILOT_STEPS_UI)),
    })
    if not _any_run_in_progress():
        cache_set(CacheNS.AUTOPILOT_BOOTSTRAP, cache_key, result, ttl=5.0)
    return result


@router.get("/output-paths")
def get_output_paths(current_user: dict = Depends(get_current_user)):
    from app import config as cfg

    return {
        "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
        "raw_actuals_folder": cfg.RAW_ACTUALS_FOLDER,
        "dp_logics_folder": cfg.DP_LOGICS_FOLDER,
        "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
        "pipeline_params_sheet_url": cfg.PIPELINE_PARAMS_SHEET_URL,
        "outputs_dir": str(cfg.OUTPUT_PATH),
    }


def _step_sse_payload(step_idx: int, step_log: dict, *, failed: bool = False) -> dict:
    """Build SSE step payload with Streamlit-parity detail (text, metrics, warning)."""
    step = AUTOPILOT_STEPS[step_idx] if step_idx < len(AUTOPILOT_STEPS) else {"key": "", "name": ""}
    metrics = step_log.get("metrics") or {}
    metric_lines = [f"{k}: {v}" for k, v in metrics.items()]
    warning = step_log.get("warning") or ""
    if failed:
        message = step_log.get("error_summary") or step_log.get("text") or "Failed"
        return {
            "event": "step",
            "index": step_idx,
            "key": step["key"],
            "label": step["name"],
            "status": "failed",
            "message": message,
            "error": step_log.get("error_detail", ""),
            "metrics": metrics,
            "metric_lines": metric_lines,
            "warning": warning,
        }
    message = step_log.get("text") or "Done"
    return {
        "event": "step",
        "index": step_idx,
        "key": step["key"],
        "label": step["name"],
        "status": "completed",
        "message": message,
        "metrics": metrics,
        "metric_lines": metric_lines,
        "warning": warning,
    }


async def _sse_generator(run_id: str, db: Database) -> AsyncGenerator[str, None]:
    """Poll DB for run progress — mirrors Streamlit step-by-step reruns."""
    last_completed = -1
    last_log_len = 0
    idle_ticks = 0

    while True:
        detail = load_autopilot_run(run_id)
        active = _ACTIVE.get(run_id, {})
        running = active.get("status") == "running"

        if not detail and not running:
            yield f"data: {json.dumps({'event': 'error', 'detail': 'Run not found'})}\n\n"
            return

        if detail:
            completed = detail.get("completed_steps") or []
            failed = detail.get("failed_step")
            logs = detail.get("logs") or {}

            if len(completed) > last_completed:
                for idx in range(last_completed + 1, len(completed)):
                    step_log = logs.get(str(idx)) or logs.get(idx) or {}
                    yield f"data: {json.dumps(_step_sse_payload(idx, step_log))}\n\n"
                last_completed = len(completed) - 1

            if failed is not None:
                step_log = logs.get(str(failed)) or logs.get(failed) or {}
                yield f"data: {json.dumps(_step_sse_payload(failed, step_log, failed=True))}\n\n"
                yield f"data: {json.dumps({'event': 'failed', 'error': detail.get('error') or step_log.get('error_summary', '')})}\n\n"
                return

            log_text = detail.get("log_text") or tail_autopilot_log(run_id=run_id)
            if len(log_text) > last_log_len:
                yield f"data: {json.dumps({'event': 'log', 'text': log_text})}\n\n"
                last_log_len = len(log_text)

            if detail.get("success") or detail.get("status") == "completed":
                yield f"data: {json.dumps({'event': 'completed'})}\n\n"
                return

        if not running and run_id not in _ACTIVE:
            if detail and detail.get("status") in ("completed", "failed"):
                if detail.get("status") == "failed":
                    yield f"data: {json.dumps({'event': 'failed', 'error': detail.get('error', '')})}\n\n"
                else:
                    yield f"data: {json.dumps({'event': 'completed'})}\n\n"
                return
            idle_ticks += 1
            if idle_ticks > 240:
                yield f"data: {json.dumps({'event': 'error', 'detail': 'Stream timeout'})}\n\n"
                return

        await asyncio.sleep(0.5)


@router.get("/stream/{run_id}")
async def stream_autopilot(
    run_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """SSE — subscribe to real-time Auto-Pilot progress (cookie auth, same-origin)."""
    _ = current_user
    return StreamingResponse(
        _sse_generator(run_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# Legacy task_id endpoints (redirect to run_id)
@router.get("/status/{task_id}")
def get_task_status(task_id: str, current_user: dict = Depends(get_current_user)):
    detail = load_autopilot_run(task_id)
    if not detail:
        active = _ACTIVE.get(task_id)
        if not active:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"status": active.get("status"), "steps": [], "error": active.get("error", "")}
    return {
        "status": "completed" if detail.get("success") else (
            "failed" if detail.get("failed_step") is not None else "running"
        ),
        "steps": [],
        "error": detail.get("error", ""),
    }
