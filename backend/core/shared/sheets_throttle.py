"""Limit concurrent Google Sheets API calls so the API stays responsive."""

from __future__ import annotations



import os

import threading

from contextlib import contextmanager



_TIMEOUT = float(os.getenv("SHEETS_SLOT_TIMEOUT_SECONDS", "90"))

_lock = threading.RLock()

_pipeline_mode = False

_sem: threading.BoundedSemaphore | None = None

_sem_limit = 0





def _api_max_concurrent() -> int:

    return max(1, int(os.getenv("SHEETS_MAX_CONCURRENT", "2")))





def _pipeline_max_concurrent() -> int:

    return max(2, int(os.getenv("PIPELINE_SHEETS_MAX_CONCURRENT", "8")))





def _ensure_semaphore() -> threading.BoundedSemaphore:

    global _sem, _sem_limit

    limit = _pipeline_max_concurrent() if _pipeline_mode else _api_max_concurrent()

    if _sem is None or _sem_limit != limit:

        _sem = threading.BoundedSemaphore(limit)

        _sem_limit = limit

    return _sem





def begin_pipeline_throttle() -> None:

    """Auto-Pilot / CLI pipeline runs — allow more parallel Sheets I/O."""

    global _pipeline_mode, _sem, _sem_limit

    with _lock:

        _pipeline_mode = True

        _sem = None

        _sem_limit = 0





def end_pipeline_throttle() -> None:

    global _pipeline_mode, _sem, _sem_limit

    with _lock:

        _pipeline_mode = False

        _sem = None

        _sem_limit = 0





def in_pipeline_mode() -> bool:

    return _pipeline_mode





@contextmanager

def sheets_slot(*, bypass: bool = False):

    """Acquire a slot before gspread I/O (skipped in pipeline mode or when bypass=True)."""

    if bypass or _pipeline_mode:

        yield

        return

    sem = _ensure_semaphore()

    if not sem.acquire(timeout=_TIMEOUT):

        raise TimeoutError(

            "Google Sheets is busy (too many concurrent reads). "

            "Wait a moment and click Refresh."

        )

    try:

        yield

    finally:

        sem.release()


