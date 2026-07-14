#!/usr/bin/env python3
"""
Sync local pipeline artifacts with remote storage (Google Drive or Supabase).

Usage (from backend/):
  set STORAGE_BACKEND=drive
  set PIPELINE_DRIVE_FOLDER_URL=https://drive.google.com/drive/folders/YOUR_FOLDER_ID
  python scripts/push_pipeline_storage.py

Pull from remote to local:
  python scripts/push_pipeline_storage.py --pull
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC = BACKEND_DIR / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

os.chdir(BACKEND_DIR.parent)


def _drive_folder_label() -> str:
    from app import config as config


    if config.get_pipeline_drive_folder_url():
        return config.get_pipeline_drive_folder_url()
    folder_id = config.get_pipeline_drive_folder_id()
    if folder_id:
        return f"PLANNING_DRIVE_ROOT → {folder_id}"
    return "(set PIPELINE_DRIVE_FOLDER_URL or PLANNING_DRIVE_ROOT)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync pipeline files with remote storage.")
    parser.add_argument("--pull", action="store_true", help="Download remote → local paths")
    parser.add_argument("--push", action="store_true", help="Upload local → remote (default)")
    parser.add_argument("--dry-run", action="store_true", help="List files that would be synced (no upload)")
    args = parser.parse_args()

    from app import config as config

    from core.storage.factory import reset_storage_cache, get_storage, storage_backend_name

    from core.storage.sync import pull_all_artifacts, push_all_artifacts


    reset_storage_cache()
    backend_name = storage_backend_name()

    if args.dry_run:
        from core.storage.artifacts import iter_artifact_specs


        specs = iter_artifact_specs()
        total = sum(Path(p).stat().st_size for _, p in specs)
        print(f"Storage backend: {backend_name}")
        if backend_name == "drive":
            print(f"Drive folder:    {_drive_folder_label()}")
        elif backend_name == "supabase":
            print(f"Supabase URL:    {config.get_supabase_url() or '(set SUPABASE_URL)'}")
            print(f"Bucket:          {config.get_supabase_storage_bucket()}")
        print(f"{len(specs)} file(s) on disk ({total / 1024 / 1024:.1f} MB) — would upload:")
        for key, local in specs:
            mb = Path(local).stat().st_size / 1024 / 1024
            print(f"  {key}  ({mb:.1f} MB)")
        return 0

    if backend_name == "supabase" and not config.get_supabase_service_role_key():
        print(
            "ERROR: STORAGE_BACKEND=supabase requires SUPABASE_SERVICE_ROLE_KEY in backend/.env\n"
            "Get it from: Supabase Dashboard → Project Settings → API → service_role",
            file=sys.stderr,
        )
        return 1

    if backend_name == "drive" and not config.get_pipeline_drive_folder_id():
        print(
            "ERROR: STORAGE_BACKEND=drive requires PIPELINE_DRIVE_FOLDER_URL in backend/.env\n"
            "Example: https://drive.google.com/drive/folders/YOUR_FOLDER_ID\n"
            "Or set PLANNING_DRIVE_ROOT to a Google Drive for Desktop shortcut path.\n"
            "Share the folder with your service account email (Editor).",
            file=sys.stderr,
        )
        return 1

    backend = get_storage()
    print(f"Storage backend: {backend.name}")
    if backend_name == "drive":
        print(f"Drive folder:    {_drive_folder_label()}")
    elif backend_name == "supabase":
        print(f"Supabase URL:    {config.get_supabase_url()}")
        print(f"Bucket:          {config.get_supabase_storage_bucket()}")
    print()

    if args.pull:
        results = pull_all_artifacts(skip_existing=False)
        action = "downloaded"
    else:
        results = push_all_artifacts(only_existing=True)
        action = "uploaded"

    ok = sum(1 for v in results.values() if v in ("uploaded", "downloaded"))
    skip = sum(1 for v in results.values() if v.startswith("skipped"))
    fail = sum(1 for v in results.values() if v.startswith("failed"))

    for key, status in sorted(results.items()):
        print(f"  {key}: {status}")

    print()
    print(f"Done — {ok} {action}, {skip} skipped, {fail} failed")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
