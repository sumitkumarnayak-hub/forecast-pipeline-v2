"""
Supabase / SQLite sync versioning — snapshots, audit log, write queue.

Snapshots store zlib-compressed parquet blobs so master data can be restored
without re-running the pipeline (rollback UI is Phase C).
"""
from __future__ import annotations

import io
import json
import logging
import uuid
import zlib
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from planning_suite.db.engine import Database

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def compress_dataframe_parquet(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return zlib.compress(buf.getvalue(), level=6)


def decompress_dataframe_parquet(blob: bytes) -> pd.DataFrame:
    return pd.read_parquet(io.BytesIO(zlib.decompress(blob)))


class SyncVersioning:
    """Record sync runs, parquet snapshots, and audit events."""

    def __init__(self, db: Database | None = None):
        self.db = db or Database()

    def start_run(self, *, step_name: str, triggered_by: str) -> str:
        run_id = str(uuid.uuid4())
        with self.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sync_run (id, started_at, triggered_by, step_name, status)
                    VALUES (:id, :started_at, :triggered_by, :step_name, 'running')
                    """
                ),
                {
                    "id": run_id,
                    "started_at": _utcnow(),
                    "triggered_by": str(triggered_by),
                    "step_name": step_name,
                },
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        status: str,
        *,
        error_msg: str | None = None,
    ) -> None:
        with self.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE sync_run
                    SET finished_at = :finished_at, status = :status, error_msg = :error_msg
                    WHERE id = :id
                    """
                ),
                {
                    "id": run_id,
                    "finished_at": _utcnow(),
                    "status": status,
                    "error_msg": error_msg,
                },
            )

    def audit(
        self,
        run_id: str,
        action: str,
        status: str,
        *,
        sheet_name: str | None = None,
        rows_affected: int | None = None,
        user_id: str | None = None,
    ) -> None:
        with self.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO audit_log (
                        id, sync_run_id, action, user_id, sheet_name,
                        rows_affected, status, ts
                    )
                    VALUES (
                        :id, :sync_run_id, :action, :user_id, :sheet_name,
                        :rows_affected, :status, :ts
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sync_run_id": run_id,
                    "action": action,
                    "user_id": user_id,
                    "sheet_name": sheet_name,
                    "rows_affected": rows_affected,
                    "status": status,
                    "ts": _utcnow(),
                },
            )

    def save_snapshot(
        self,
        run_id: str,
        sheet_name: str,
        df: pd.DataFrame,
        *,
        user_id: str | None = None,
    ) -> None:
        blob = compress_dataframe_parquet(df)
        with self.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sync_snapshot (
                        id, sync_run_id, sheet_name, snapshot_parquet,
                        row_count, created_at, user_id
                    )
                    VALUES (
                        :id, :sync_run_id, :sheet_name, :snapshot_parquet,
                        :row_count, :created_at, :user_id
                    )
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sync_run_id": run_id,
                    "sheet_name": sheet_name,
                    "snapshot_parquet": blob,
                    "row_count": len(df),
                    "created_at": _utcnow(),
                    "user_id": user_id,
                },
            )

    def save_master_snapshots(
        self,
        run_id: str,
        *,
        p_df: pd.DataFrame,
        ph_df: pd.DataFrame,
        htt_df: pd.DataFrame,
        hub_df: pd.DataFrame,
        user_id: str | None = None,
    ) -> None:
        for name, frame in (
            ("P Master", p_df),
            ("P-H Master", ph_df),
            ("HTT", htt_df),
            ("Hub Mapping", hub_df),
        ):
            self.save_snapshot(run_id, name, frame, user_id=user_id)

    def enqueue_write(
        self,
        sheet_name: str,
        payload: list[dict[str, Any]] | dict[str, Any],
    ) -> str:
        queue_id = str(uuid.uuid4())
        with self.db.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO write_queue (id, sheet_name, payload, status, created_at)
                    VALUES (:id, :sheet_name, :payload, 'pending', :created_at)
                    """
                ),
                {
                    "id": queue_id,
                    "sheet_name": sheet_name,
                    "payload": json.dumps(payload, default=str),
                    "created_at": _utcnow(),
                },
            )
        return queue_id

    def list_runs(self, *, step_name: str | None = None, limit: int = 50) -> list[dict]:
        query = """
            SELECT id, started_at, finished_at, triggered_by, step_name, status, error_msg
            FROM sync_run
        """
        params: dict[str, Any] = {"limit": limit}
        if step_name:
            query += " WHERE step_name = :step_name"
            params["step_name"] = step_name
        query += " ORDER BY started_at DESC LIMIT :limit"

        with self.db.engine.connect() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [dict(r) for r in rows]

    def load_snapshot(self, run_id: str, sheet_name: str) -> pd.DataFrame | None:
        with self.db.engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT snapshot_parquet FROM sync_snapshot
                    WHERE sync_run_id = :run_id AND sheet_name = :sheet_name
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"run_id": run_id, "sheet_name": sheet_name},
            ).first()
        if not row or not row[0]:
            return None
        return decompress_dataframe_parquet(row[0])


# Snapshot sheet label → demand_planning_masters worksheet key
MASTER_SNAPSHOT_RESTORE_MAP: dict[str, str] = {
    "P Master": "product_master",
    "P-H Master": "product_hub_master",
    "HTT": "htt_mapping",
    "Hub Mapping": "hub_mapping",
}


def list_snapshot_meta(db: Database | None, run_id: str) -> list[dict]:
    """Sheet names and row counts stored for a sync run."""
    database = db or Database()
    with database.engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT sheet_name, row_count, created_at
                FROM sync_snapshot
                WHERE sync_run_id = :run_id
                ORDER BY sheet_name
                """
            ),
            {"run_id": run_id},
        ).mappings().all()
    return [dict(r) for r in rows]


def restore_master_snapshots_to_sheets(
    sheets_manager,
    source_run_id: str,
    *,
    user_id: str | int,
    db: Database | None = None,
) -> dict[str, str]:
    """
    Restore all master snapshots from a prior sync_run to Google Sheets.

    Writes audit rows with action=rollback and updates local Product_Masters.xlsx.
    """
    from planning_suite.automation.master_data_sync import write_masters_excel
    from planning_suite.config import FF_MASTERS_XLSX

    versioning = SyncVersioning(db)
    rollback_run_id = versioning.start_run(
        step_name="master_rollback",
        triggered_by=str(user_id),
    )
    results: dict[str, str] = {}
    frames: dict[str, pd.DataFrame] = {}

    try:
        for sheet_name, worksheet_key in MASTER_SNAPSHOT_RESTORE_MAP.items():
            df = versioning.load_snapshot(source_run_id, sheet_name)
            if df is None or df.empty:
                results[sheet_name] = "missing"
                continue
            ok = sheets_manager.write_df_to_worksheet(
                "demand_planning_masters",
                worksheet_key,
                df,
                clear_first=True,
                quiet=True,
            )
            results[sheet_name] = "ok" if ok else "failed"
            frames[sheet_name] = df
            versioning.audit(
                rollback_run_id,
                "rollback",
                "success" if ok else "failed",
                sheet_name=sheet_name,
                rows_affected=len(df),
                user_id=str(user_id),
            )

        restored = [n for n, s in results.items() if s == "ok"]
        if len(restored) == len(MASTER_SNAPSHOT_RESTORE_MAP):
            write_masters_excel(
                FF_MASTERS_XLSX,
                frames["P Master"],
                frames["P-H Master"],
                frames["HTT"],
                frames["Hub Mapping"],
            )
            try:
                from planning_suite.services.baseline_io import write_product_master_engine_sidecars
                write_product_master_engine_sidecars(FF_MASTERS_XLSX)
            except Exception:
                pass

        all_ok = bool(results) and all(
            results.get(name) == "ok" for name in MASTER_SNAPSHOT_RESTORE_MAP
        )
        versioning.finish_run(
            rollback_run_id,
            "success" if all_ok else "failed",
            error_msg=None if all_ok else "One or more sheets failed to restore",
        )
        return results
    except Exception as exc:
        versioning.finish_run(rollback_run_id, "failed", error_msg=str(exc))
        raise
