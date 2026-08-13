"""
Base Sheet Sync — service layer.

Reads / syncs Google Sheets defined in BASE_SHEETS_REGISTRY.
Each sheet can be synced as a parquet file to Google Drive.

Performance Optimisations:
  - gspread client cached as a module-level singleton (no repeated OAuth round-trips)
  - list_sheets() uses a single batched SQL query for all last-sync records
  - _open_worksheet() skips worksheets() iteration when gid is unknown; falls back gracefully
  - sync uses write_bytes() with an in-memory BytesIO buffer — no disk I/O
"""
from __future__ import annotations

import io
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import BASE_SHEETS_REGISTRY, OUTPUT_PATH
from core.utils.dataframe import clean_sheet_df

logger = logging.getLogger(__name__)

# ── ✏️  EDITABLE: Drive storage config for base sheet parquet files ───────────
#
# To change where parquet files are stored, update ONLY this block.
# No other code in this file needs to change.
#
#   DRIVE_FOLDER_ID  — the Google Drive folder ID shown in the URL:
#                      drive.google.com/drive/folders/<FOLDER_ID>
#
#   DRIVE_SUBFOLDER  — subfolder created inside DRIVE_FOLDER_ID.
#                      Set to "" to store directly at the root folder.
#
#   DRIVE_FILENAME_TEMPLATE — Python format string for the parquet filename.
#                             Available vars: {sheet_key}, {date}  (YYYYMMDD).
#
DRIVE_STORAGE_CONFIG: dict[str, str] = {
    "DRIVE_FOLDER_ID":          "0AKKX6JjhUdibUk9PVA",        # ← root Drive folder ID
    "DRIVE_SUBFOLDER":          "base_sheet_baseline",          # ← subfolder name
    "DRIVE_FILENAME_TEMPLATE":  "{sheet_key}_{date}.parquet",   # ← parquet filename pattern
}

# ─────────────────────────────────────────────────────────────────────────────

# ── Module-level gspread client singleton ────────────────────────────────────

_gc_lock = threading.Lock()
_gc_client = None
_gc_client_expiry = 0.0   # Unix timestamp after which to refresh (token TTL ~1h)


def _get_gspread_client():
    """
    Return a module-level cached gspread client.
    Rebuilds after 50 minutes to stay inside the 1-hour OAuth token TTL.
    Thread-safe via a lock.
    """
    import time
    import gspread

    global _gc_client, _gc_client_expiry

    with _gc_lock:
        if _gc_client is None or time.monotonic() > _gc_client_expiry:
            from core.shared.google_credentials import load_service_account_credentials
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = load_service_account_credentials(scope)
            _gc_client = gspread.authorize(creds)
            _gc_client_expiry = time.monotonic() + 50 * 60  # 50 min
            logger.debug("gspread client rebuilt (OAuth refresh)")

    return _gc_client


def _open_worksheet(gc, sheet_url: str, gid: int | None):
    """
    Open the target worksheet as efficiently as possible.

    If gid is None → use sheet1 (single API call via open_by_url).
    If gid is provided → open spreadsheet then find matching tab;
      avoids fetching worksheets() list by trying to open directly first.
    """
    spreadsheet = gc.open_by_url(sheet_url)

    if gid is None:
        return spreadsheet.sheet1, spreadsheet

    # Try to get the worksheet directly by gid (O(n) over tabs but only metadata)
    for ws in spreadsheet.worksheets():
        if ws.id == gid:
            return ws, spreadsheet

    logger.warning("gid=%d not found in spreadsheet, falling back to first sheet", gid)
    return spreadsheet.sheet1, spreadsheet


# ── Public service functions ──────────────────────────────────────────────────

def list_sheets() -> list[dict[str, Any]]:
    """
    Return metadata + last sync run for all configured base sheets.
    Uses a SINGLE batched DB query (one round-trip regardless of sheet count).
    """
    from sqlalchemy import text
    from core.database.engine import get_shared_database

    keys = list(BASE_SHEETS_REGISTRY.keys())

    # Build step_name list for the IN clause
    step_names = [f"base_sheet_sync:{k}" for k in keys]

    # Supabase / Postgres: fetch the most-recent sync_run per step_name in one query
    batch_query = """
        SELECT DISTINCT ON (r.step_name)
            r.step_name,
            r.started_at,
            r.finished_at,
            r.status,
            u.full_name,
            u.email
        FROM sync_run r
        LEFT JOIN users u ON CAST(u.id AS TEXT) = r.triggered_by
        WHERE r.step_name = ANY(:step_names)
        ORDER BY r.step_name, r.started_at DESC
    """

    # SQLite-compatible fallback (no DISTINCT ON)
    sqlite_query = """
        SELECT r.step_name, r.started_at, r.finished_at, r.status,
               u.full_name, u.email
        FROM sync_run r
        LEFT JOIN users u ON CAST(u.id AS TEXT) = r.triggered_by
        WHERE r.step_name IN ({placeholders})
        AND r.started_at = (
            SELECT MAX(r2.started_at)
            FROM sync_run r2
            WHERE r2.step_name = r.step_name
        )
    """.format(placeholders=",".join([f":sn{i}" for i in range(len(step_names))]))

    db = get_shared_database()
    last_sync_map: dict[str, dict] = {}

    try:
        with db.engine.connect() as conn:
            if db.backend == "postgresql":
                import psycopg2.extras  # noqa – just ensure it's available
                res = conn.execute(text(batch_query), {"step_names": step_names})
            else:
                params = {f"sn{i}": sn for i, sn in enumerate(step_names)}
                res = conn.execute(text(sqlite_query), params)

            for row in res.mappings():
                last_sync_map[row["step_name"]] = {
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
                    "status": row["status"],
                    "full_name": row["full_name"] or "System",
                    "email": row["email"] or "",
                }
    except Exception as exc:
        logger.warning("Failed to batch-fetch sync history: %s", exc)

    result = []
    for key, info in BASE_SHEETS_REGISTRY.items():
        if not info.get("url"):
            continue
        step_name = f"base_sheet_sync:{key}"
        result.append({
            "key": key,
            "label": info["label"],
            "url": info["url"],
            "group": info.get("group", ""),
            "has_gid": info.get("gid") is not None,
            "last_sync": last_sync_map.get(step_name),
        })
    return result


def read_sheet_data(sheet_key: str) -> pd.DataFrame:
    """
    Read all data from a base sheet.
    Uses sheets_throttle to respect API quotas.
    """
    info = BASE_SHEETS_REGISTRY.get(sheet_key)
    if not info or not info.get("url"):
        raise ValueError(f"Unknown or unconfigured base sheet: {sheet_key}")

    from core.shared.sheets_throttle import sheets_slot

    gc = _get_gspread_client()
    with sheets_slot():
        ws, _ = _open_worksheet(gc, info["url"], info.get("gid"))
        data = ws.get_all_values()

    if not data or len(data) < 1:
        return pd.DataFrame()

    headers = data[0]
    rows = data[1:] if len(data) > 1 else []
    df = pd.DataFrame(rows, columns=headers)
    return clean_sheet_df(df)


def get_sync_history(sheet_key: str, limit: int = 5) -> list[dict[str, Any]]:
    """Fetch the recent sync run history for a base sheet."""
    from sqlalchemy import text
    from core.database.engine import get_shared_database

    db = get_shared_database()
    step_name = f"base_sheet_sync:{sheet_key}"

    query = """
        SELECT r.started_at, r.finished_at, r.status, u.full_name, u.email
        FROM sync_run r
        LEFT JOIN users u ON CAST(u.id AS TEXT) = r.triggered_by
        WHERE r.step_name = :step_name
        ORDER BY r.started_at DESC
        LIMIT :limit
    """
    results = []
    with db.engine.connect() as conn:
        res = conn.execute(text(query), {"step_name": step_name, "limit": limit})
        for row in res.mappings():
            results.append({
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "finished_at": row["finished_at"].isoformat() if row["finished_at"] else None,
                "status": row["status"],
                "full_name": row["full_name"] or "System",
                "email": row["email"] or "",
            })
    return results


def sync_sheet_to_parquet(sheet_key: str, user_id: int) -> dict[str, Any]:
    """
    Sync a base sheet to parquet:
    1. Read the full Google Sheet.
    2. Serialise to parquet in-memory (BytesIO — no disk I/O).
    3. Stream the buffer directly to Google Drive via write_bytes().
    4. Create audit log via SyncVersioning.
    """
    info = BASE_SHEETS_REGISTRY.get(sheet_key)
    if not info or not info.get("url"):
        raise ValueError(f"Unknown or unconfigured base sheet: {sheet_key}")

    # 1. Read sheet data
    logger.info("Reading base sheet '%s' for sync…", info["label"])
    df = read_sheet_data(sheet_key)
    if df.empty:
        raise ValueError(f"Sheet '{info['label']}' is empty — nothing to sync")

    total_rows = len(df)

    # 2. Write parquet to in-memory buffer (no disk touch)
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    parquet_bytes = buf.getvalue()
    file_size_kb = round(len(parquet_bytes) / 1024, 1)
    logger.info(
        "Serialised '%s' to parquet in memory: %d rows, %.1f KB",
        info["label"], total_rows, file_size_kb,
    )

    # 3. Stream directly to Google Drive (no local file written)
    import app.config as cfg
    from core.storage.drive import DriveStorageBackend

    _cfg = DRIVE_STORAGE_CONFIG
    storage = DriveStorageBackend(
        root_folder_id=_cfg["DRIVE_FOLDER_ID"],
        credentials_path=cfg.GOOGLE_CREDENTIALS_PATH,
        impersonate_email=cfg.get_google_drive_impersonate_email(),
    )
    date_str = datetime.now().strftime("%Y%m%d")
    filename = _cfg["DRIVE_FILENAME_TEMPLATE"].format(sheet_key=sheet_key, date=date_str)
    subfolder = _cfg["DRIVE_SUBFOLDER"]
    drive_key = f"{subfolder}/{filename}" if subfolder else filename
    storage.write_bytes(drive_key, parquet_bytes, content_type="application/octet-stream")
    logger.info("Uploaded '%s' → Drive: %s", info["label"], drive_key)

    # 4. Audit log
    audit_id = _create_audit_log(sheet_key, user_id, total_rows, file_size_kb, drive_uploaded=True)

    return {
        "sheet_key": sheet_key,
        "label": info["label"],
        "rows_synced": total_rows,
        "columns": list(df.columns),
        "file_size_kb": file_size_kb,
        "drive_uploaded": True,
        "drive_key": drive_key,
        "audit_id": audit_id,
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def _create_audit_log(
    sheet_key: str,
    user_id: int,
    row_count: int,
    file_size_kb: float,
    drive_uploaded: bool,
) -> str | None:
    """Create an audit log entry for a base sheet sync in Supabase sync_run."""
    try:
        from core.shared.sync_versioning import SyncVersioning
        from core.database.engine import get_shared_database

        db = get_shared_database()
        versioning = SyncVersioning(db)

        info = BASE_SHEETS_REGISTRY[sheet_key]
        run_id = versioning.start_run(
            step_name=f"base_sheet_sync:{sheet_key}",
            triggered_by=str(user_id),
        )
        versioning.audit(
            run_id,
            "sync",
            "success",
            sheet_name=info["label"],
            rows_affected=row_count,
            user_id=str(user_id),
        )
        versioning.finish_run(run_id, "success")
        logger.info("Audit log created for '%s' sync: run_id=%s", info["label"], run_id)
        return run_id
    except Exception as exc:
        logger.warning("Failed to create audit log: %s", exc)
        return None
