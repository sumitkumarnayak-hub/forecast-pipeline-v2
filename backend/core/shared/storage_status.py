"""Storage diagnostics for cloud deploy troubleshooting."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from core.shared.cloud_paths import is_cloud_deploy
from core.storage.sync import _STARTUP_ARTIFACT_KEYS



def _artifact_row(key: str) -> dict[str, Any]:
    from core.storage.artifacts import resolve_local_path


    local = resolve_local_path(key)
    return {
        "key": key,
        "local_path": str(local),
        "exists": local.is_file(),
        "size_bytes": local.stat().st_size if local.is_file() else None,
    }


def get_storage_status(*, check_remote: bool = False) -> dict[str, Any]:
    """Return storage backend config and startup artifact presence."""
    from app import config as config

    from core.storage.factory import storage_backend_name


    backend = storage_backend_name()
    folder_url = config.get_pipeline_drive_folder_url()
    folder_id = config.get_pipeline_drive_folder_id()

    status: dict[str, Any] = {
        "storage_backend": backend,
        "cloud_deploy": is_cloud_deploy(),
        "drive_folder_configured": bool(folder_id),
        "drive_folder_url_set": bool(folder_url),
        "google_credentials_configured": bool(
            os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
            or os.getenv("GOOGLE_CREDENTIALS_PATH", "").strip()
        ),
        "artifacts": [_artifact_row(key) for key in _STARTUP_ARTIFACT_KEYS],
    }

    if backend == "local" and is_cloud_deploy():
        status["warning"] = (
            "STORAGE_BACKEND=local on a cloud host — pipeline files are not synced from "
            "Google Drive. Set STORAGE_BACKEND=drive and PIPELINE_DRIVE_FOLDER_URL on "
            "your Hugging Face Space / Render service, then restart."
        )
    elif backend == "drive" and not folder_id:
        status["warning"] = (
            "STORAGE_BACKEND=drive but PIPELINE_DRIVE_FOLDER_URL is missing — "
            "artifact sync is disabled."
        )
    elif backend == "drive" and not status["google_credentials_configured"]:
        status["warning"] = (
            "STORAGE_BACKEND=drive but GOOGLE_CREDENTIALS_JSON is not set — "
            "Drive sync will fail."
        )

    missing = [a["key"] for a in status["artifacts"] if not a["exists"]]
    if missing:
        status["missing_artifacts"] = missing

    if check_remote and backend in {"drive", "supabase"}:
        try:
            from core.storage.factory import get_storage


            store = get_storage()
            remote: dict[str, bool] = {}
            for key in _STARTUP_ARTIFACT_KEYS:
                try:
                    remote[key] = store.exists(key)
                except Exception:
                    remote[key] = False
            status["remote_artifacts"] = remote
            if backend == "drive":
                status["drive_reachable"] = True
        except Exception as exc:
            status["drive_reachable"] = False
            status["remote_check_error"] = str(exc)

    return status
