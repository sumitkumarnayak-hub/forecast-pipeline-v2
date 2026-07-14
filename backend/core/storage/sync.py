"""Pull/push pipeline artifacts between local disk and remote storage."""
from __future__ import annotations

import logging

from core.storage.artifacts import artifact_local_paths, iter_artifact_specs, registered_artifacts

from core.storage.factory import get_storage, storage_backend_name


logger = logging.getLogger(__name__)

# Minimum artifacts for dashboard + master-data APIs on cloud deploy
_STARTUP_ARTIFACT_KEYS = (
    "outputs/rds_cache.parquet",
    "analytics/6w_v3.rds",
    "masters/Product_Masters.xlsx",
    "outputs/active_dataset.parquet",
    "outputs/active_dataset_meta.json",
)


def push_all_artifacts(*, only_existing: bool = True) -> dict[str, str]:
    """
    Upload local pipeline files to remote storage.
    Returns {key: status} where status is uploaded | skipped | failed:...
    """
    backend = get_storage()
    if backend.name == "local":
        return {k: "skipped (local backend)" for k in artifact_local_paths()}

    results: dict[str, str] = {}
    for key, local in registered_artifacts():
        try:
            if only_existing and not __import__("pathlib").Path(local).is_file():
                results[key] = "skipped (missing)"
                continue
            if backend.sync_local_to_remote(key, local):
                results[key] = "uploaded"
            else:
                results[key] = "skipped (missing)"
        except Exception as exc:
            logger.warning("Upload failed for %s: %s", key, exc)
            results[key] = f"failed: {exc}"
    return results


def pull_all_artifacts(*, skip_existing: bool = True) -> dict[str, str]:
    """
    Download remote objects to canonical local paths.
    Returns {key: status}.
    """
    from pathlib import Path

    backend = get_storage()
    if backend.name == "local":
        return {k: "skipped (local backend)" for k in artifact_local_paths()}

    results: dict[str, str] = {}
    for key, local in registered_artifacts():
        try:
            local_p = Path(local)
            if skip_existing and local_p.is_file():
                results[key] = "skipped (local exists)"
                continue
            if backend.sync_remote_to_local(key, local):
                results[key] = "downloaded"
            else:
                results[key] = "skipped (not in remote)"
        except Exception as exc:
            logger.warning("Download failed for %s: %s", key, exc)
            results[key] = f"failed: {exc}"
    return results


def pull_startup_artifacts(*, skip_existing: bool = True) -> dict[str, str]:
    """Download critical files for dashboard and master-data APIs."""
    from pathlib import Path

    from core.storage.artifacts import resolve_local_path


    backend = get_storage()
    if backend.name == "local":
        return {k: "skipped (local backend)" for k in _STARTUP_ARTIFACT_KEYS}

    results: dict[str, str] = {}
    for key in _STARTUP_ARTIFACT_KEYS:
        try:
            local = str(resolve_local_path(key))
            local_p = Path(local)
            local_p.parent.mkdir(parents=True, exist_ok=True)
            if skip_existing and local_p.is_file():
                results[key] = "skipped (local exists)"
                continue
            if backend.sync_remote_to_local(key, local):
                results[key] = "downloaded"
            else:
                results[key] = "skipped (not in remote)"
        except Exception as exc:
            logger.warning("Startup download failed for %s: %s", key, exc)
            results[key] = f"failed: {exc}"
    return results


def sync_before_pipeline() -> None:
    """Called at Auto-Pilot start when using remote storage."""
    if storage_backend_name() == "local":
        return
    logger.info("Pulling pipeline artifacts from %s storage…", storage_backend_name())
    summary = pull_all_artifacts(skip_existing=False)
    uploaded = sum(1 for v in summary.values() if v == "downloaded")
    logger.info("Storage pull complete: %s file(s) downloaded", uploaded)


def sync_after_pipeline() -> None:
    """Called after Auto-Pilot completes when using remote storage."""
    if storage_backend_name() == "local":
        return
    logger.info("Pushing pipeline artifacts to %s storage…", storage_backend_name())
    summary = push_all_artifacts(only_existing=True)
    uploaded = sum(1 for v in summary.values() if v == "uploaded")
    logger.info("Storage push complete: %s file(s) uploaded", uploaded)
