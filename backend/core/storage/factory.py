"""Storage backend factory — switch via STORAGE_BACKEND env."""
from __future__ import annotations

import os
from functools import lru_cache

from core.storage.base import StorageBackend

from core.storage.drive import DriveStorageBackend

from core.storage.local import LocalStorageBackend

from core.storage.supabase import SupabaseStorageBackend



def storage_backend_name() -> str:
    return os.getenv("STORAGE_BACKEND", "local").strip().lower() or "local"


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """
    Return the active storage backend.

    STORAGE_BACKEND:
      - local   (default) — files stay on disk paths from .env
      - supabase — sync to Supabase Storage bucket (see sync.py)
      - drive   — sync to Google Drive folder (PIPELINE_DRIVE_FOLDER_URL)
    """
    name = storage_backend_name()
    if name == "local":
        return LocalStorageBackend()
    if name == "supabase":
        from app import config as cfg


        url = cfg.get_supabase_url()
        key = cfg.get_supabase_service_role_key()
        bucket = cfg.get_supabase_storage_bucket()
        if not url or not key:
            raise RuntimeError(
                "STORAGE_BACKEND=supabase requires SUPABASE_URL (or DATABASE_URL with project ref) "
                "and SUPABASE_SERVICE_ROLE_KEY in backend/.env"
            )
        return SupabaseStorageBackend(url=url, service_role_key=key, bucket=bucket)
    if name == "drive":
        from app import config as cfg


        folder_id = cfg.get_pipeline_drive_folder_id()
        if not folder_id:
            raise RuntimeError(
                "STORAGE_BACKEND=drive requires PIPELINE_DRIVE_FOLDER_URL "
                "(Google Drive folder URL shared with the service account)"
            )
        return DriveStorageBackend(
            root_folder_id=folder_id,
            credentials_path=cfg.GOOGLE_CREDENTIALS_PATH,
            impersonate_email=cfg.get_google_drive_impersonate_email(),
        )
    raise ValueError(f"Unknown STORAGE_BACKEND={name!r}. Use local, supabase, or drive.")


def reset_storage_cache() -> None:
    get_storage.cache_clear()
