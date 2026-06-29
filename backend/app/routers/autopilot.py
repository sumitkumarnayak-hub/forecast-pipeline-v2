"""
Auto-Pilot router — 6-step pipeline with Server-Sent Events streaming.
The frontend subscribes to /api/autopilot/stream/{task_id} to get
real-time step progress, mirroring the Streamlit st.progress() UI.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.deps import get_current_user, require_write, get_db
from planning_suite.db.engine import Database

router = APIRouter()

# In-memory task registry {task_id: {"status": str, "steps": list, "error": str}}
_TASKS: dict[str, dict] = {}

STEP_LABELS = [
    ("master_sync",      "Master Data Sync & Validation"),
    ("new_hub_launch",   "New Hub Launch (P-H Master)"),
    ("pull_raw_data",    "Pull Raw Data"),
    ("sync_config",      "Sync Config Parameters"),
    ("run_engine",       "Run Baseline Engine"),
    ("notify",           "Email Notification"),
]


def _run_autopilot_sync(task_id: str, from_step: int, user_id: int, db: Database):
    """Run the 6-step autopilot synchronously in a thread (no event loop)."""
    task = _TASKS[task_id]
    task["status"] = "running"
    task["steps"] = []

    try:
        from planning_suite.automation.optimized_autopilot import run_autopilot
        
        def step_callback(step_idx: int, step_key: str, status: str, message: str, error: str = ""):
            task["steps"].append({
                "index": step_idx,
                "key": step_key,
                "label": STEP_LABELS[step_idx][1] if step_idx < len(STEP_LABELS) else step_key,
                "status": status,
                "message": message,
                "error": error,
            })

        run_autopilot(
            db=db,
            user_id=user_id,
            from_step=from_step,
            step_callback=step_callback,
        )
        task["status"] = "completed"
    except Exception as exc:
        task["status"] = "failed"
        task["error"] = str(exc)


@router.post("/run")
def start_autopilot(
    from_step: int = 0,
    current_user: dict = Depends(require_write),
    db: Database = Depends(get_db),
):
    """Start the 6-step Auto-Pilot in the background and return a task_id."""
    import threading
    task_id = str(uuid.uuid4())
    user_id = int(current_user["sub"])
    _TASKS[task_id] = {"status": "pending", "steps": [], "error": ""}

    t = threading.Thread(
        target=_run_autopilot_sync,
        args=(task_id, from_step, user_id, db),
        daemon=True,
    )
    t.start()
    return {"task_id": task_id}


@router.get("/status/{task_id}")
def get_task_status(task_id: str, current_user: dict = Depends(get_current_user)):
    task = _TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def _sse_generator(task_id: str) -> AsyncGenerator[str, None]:
    """Yield SSE events as the task progresses."""
    last_step_count = 0
    while True:
        task = _TASKS.get(task_id)
        if not task:
            yield f"data: {json.dumps({'event': 'error', 'detail': 'Task not found'})}\n\n"
            return

        steps = task.get("steps", [])
        # Stream any new step updates
        if len(steps) > last_step_count:
            for step in steps[last_step_count:]:
                yield f"data: {json.dumps({'event': 'step', **step})}\n\n"
            last_step_count = len(steps)

        status = task.get("status")
        if status == "completed":
            yield f"data: {json.dumps({'event': 'completed'})}\n\n"
            return
        if status == "failed":
            yield f"data: {json.dumps({'event': 'failed', 'error': task.get('error', '')})}\n\n"
            return

        await asyncio.sleep(0.5)


@router.get("/stream/{task_id}")
async def stream_autopilot(task_id: str):
    """SSE endpoint — subscribe to get real-time step progress."""
    return StreamingResponse(
        _sse_generator(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/state")
def get_autopilot_state(current_user: dict = Depends(get_current_user)):
    """Return the last persisted autopilot_state.json."""
    import os, json as _json
    state_file = os.path.join("outputs", "autopilot_state.json")
    if not os.path.exists(state_file):
        return {}
    try:
        with open(state_file) as f:
            return _json.load(f)
    except Exception:
        return {}


@router.get("/output-paths")
def get_output_paths(current_user: dict = Depends(get_current_user)):
    """Return the env-derived output path config for the UI panel."""
    from planning_suite import config as cfg
    return {
        "ff_masters_xlsx": cfg.FF_MASTERS_XLSX,
        "raw_actuals_folder": cfg.RAW_ACTUALS_FOLDER,
        "dp_logics_folder": cfg.DP_LOGICS_FOLDER,
        "baseline_outputs_folder": cfg.BASELINE_OUTPUTS_FOLDER,
        "pipeline_params_sheet_url": cfg.PIPELINE_PARAMS_SHEET_URL,
        "outputs_dir": str(cfg.OUTPUT_PATH),
    }
