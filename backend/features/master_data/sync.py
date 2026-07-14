"""
Headless Demand Planning master sync — Sheets → validate → FF_MASTERS_XLSX.

Uses the same read order, validation rules, and Excel sheet layout as
``MasterDataManager._sync_masters_to_excel`` (output is unchanged).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from app.config import FF_MASTERS_XLSX, OUTPUT_PATH, PROJECT_ROOT
from core.utils.dataframe import clean_sheet_df

from features.validation.rules import VALIDATION_VERSION
from features.validation.runner import run_master_data_validations
from core.database.engine import Database, get_shared_database


ProgressCallback = Callable[[str, float], None]

_STATE_FILE = OUTPUT_PATH / "master_sync_state.json"


def _noop_progress(_message: str, _pct: float) -> None:
    return None


def _record_versioning_failure(
    versioning,
    sync_run_id: str | None,
    *,
    user_id: int,
    action: str,
    message: str,
    sheet_name: str | None = None,
) -> None:
    if not sync_run_id or versioning is None:
        return
    try:
        versioning.audit(
            sync_run_id,
            action,
            "failed",
            user_id=str(user_id),
            sheet_name=sheet_name,
        )
        versioning.finish_run(sync_run_id, "failed", error_msg=message)
    except Exception:
        pass


def _record_versioning_success(
    versioning,
    sync_run_id: str | None,
    *,
    user_id: int,
    p_df: pd.DataFrame,
    ph_df: pd.DataFrame,
    htt_df: pd.DataFrame,
    hub_df: pd.DataFrame,
) -> None:
    if not sync_run_id or versioning is None:
        return
    try:
        versioning.audit(
            sync_run_id,
            "validate",
            "success",
            user_id=str(user_id),
            rows_affected=len(ph_df),
        )
        versioning.save_master_snapshots(
            sync_run_id,
            p_df=p_df,
            ph_df=ph_df,
            htt_df=htt_df,
            hub_df=hub_df,
            user_id=str(user_id),
        )
        versioning.audit(
            sync_run_id,
            "write",
            "success",
            user_id=str(user_id),
            rows_affected=len(ph_df),
        )
        versioning.finish_run(sync_run_id, "success")
    except Exception:
        pass


def _progress_print(message: str) -> None:
    print(message, flush=True)


@dataclass
class MasterSyncResult:
    success: bool
    excel_path: str = ""
    p_rows: int = 0
    ph_rows: int = 0
    htt_rows: int = 0
    hub_rows: int = 0
    blank_rows_removed: int = 0
    file_size_kb: float = 0
    validation_errors: list[dict] = field(default_factory=list)
    error: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1


def _excel_writer_engine() -> str:
    from features.master_data.excel import get_excel_writer_engine


    return get_excel_writer_engine()


def read_demand_planning_masters_from_sheets(
    *,
    progress: ProgressCallback | None = None,
    sheets_manager=None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Read P Master, HTT Mapping, Hub Mapping, P-H Master (parallel batch read)."""
    from core.shared.google_sheets import GoogleSheetsManager

    from core.shared.sheets_session import get_active_sheets_manager


    report = progress or _noop_progress
    report("Connecting to Google Sheets…", 0.05)
    sheets = sheets_manager or get_active_sheets_manager() or GoogleSheetsManager()
    p_df, htt_df, hub_df, ph_df = sheets.read_demand_planning_masters_parallel(progress=report)
    report("All sheets loaded", 0.75)
    return p_df, htt_df, hub_df, ph_df


def write_masters_excel(
    excel_path: str | Path,
    p_df: pd.DataFrame,
    ph_df: pd.DataFrame,
    htt_df: pd.DataFrame,
    hub_df: pd.DataFrame,
    *,
    progress: ProgressCallback | None = None,
) -> float:
    """Write the four master sheets to Excel (same names and order as UI sync)."""
    report = progress or _noop_progress
    out_path = Path(excel_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report("Writing Excel file…", 0.80)
    with pd.ExcelWriter(str(out_path), engine=_excel_writer_engine()) as writer:
        report("Writing P Master sheet…", 0.83)
        p_df.to_excel(writer, sheet_name="P Master", index=False)
        report("Writing P-H Master sheet…", 0.88)
        ph_df.to_excel(writer, sheet_name="P-H Master", index=False)
        report("Writing HTT & Hub Mapping sheets…", 0.95)
        htt_df.to_excel(writer, sheet_name="HTT", index=False)
        hub_df.to_excel(writer, sheet_name="Hub Mapping", index=False)

    report("Excel write complete", 1.0)
    return round(out_path.stat().st_size / 1024, 1)


def _load_masters_from_local_excel(excel_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame] | None:
    """Load the four master sheets from an on-disk Product_Masters.xlsx."""
    path = Path(excel_path)
    if not path.is_file() or path.stat().st_size < 4096:
        return None
    try:
        xl = pd.ExcelFile(path)
        sheets = {name.strip(): name for name in xl.sheet_names}

        def _read(tab: str) -> pd.DataFrame:
            actual = sheets.get(tab)
            if not actual:
                return pd.DataFrame()
            return clean_sheet_df(pd.read_excel(xl, sheet_name=actual))

        return (
            _read("P Master"),
            _read("HTT"),
            _read("Hub Mapping"),
            _read("P-H Master"),
        )
    except Exception:
        return None


def _fresh_masters_skip_hours() -> float | None:
    raw = os.getenv("AUTOPILOT_SKIP_FRESH_MASTERS_HOURS", "").strip()
    if not raw:
        return None
    try:
        hours = float(raw)
        return hours if hours > 0 else None
    except ValueError:
        return None


def run_master_data_excel_sync(
    excel_path: str | Path | None = None,
    user_id: int | None = None,
    *,
    db: Database | None = None,
    validate_only: bool = False,
    progress: ProgressCallback | None = None,
    sheets_manager=None,
) -> MasterSyncResult:
    """
    Sync Demand Planning masters from Google Sheets to the backend Excel file.

    Validation and Excel layout match ``MasterDataManager._sync_masters_to_excel``.
    """
    _ensure_project_cwd()
    excel_path = str(excel_path or FF_MASTERS_XLSX)
    user_id = user_id if user_id is not None else int(os.getenv("AUTOPILOT_USER_ID", "1"))
    db = db or get_shared_database()
    result = MasterSyncResult(success=False, excel_path=excel_path)
    sync_run_id: str | None = None
    versioning = None

    try:
        from core.shared.sync_versioning import SyncVersioning


        versioning = SyncVersioning(db)
        sync_run_id = versioning.start_run(
            step_name="master_sync",
            triggered_by=str(user_id),
        )
    except Exception:
        pass

    try:
        skip_hours = _fresh_masters_skip_hours()
        loaded_local = False
        if skip_hours is not None:
            age_h = (time.time() - Path(excel_path).stat().st_mtime) / 3600 if Path(excel_path).is_file() else 999
            if age_h <= skip_hours:
                local = _load_masters_from_local_excel(excel_path)
                if local is not None:
                    p_df, htt_df, hub_df, ph_df = local
                    loaded_local = True
                    if progress:
                        progress(f"Using fresh local masters ({age_h:.1f}h old) — skipped Sheets read", 0.75)

        if not loaded_local:
            p_df, htt_df, hub_df, ph_df = read_demand_planning_masters_from_sheets(
                progress=progress,
                sheets_manager=sheets_manager,
            )
    except Exception as exc:
        result.error = f"Could not read from Google Sheets: {exc}"
        _record_versioning_failure(
            versioning,
            sync_run_id,
            user_id=user_id,
            action="read",
            message=result.error,
        )
        return result

    result.p_rows = len(p_df)
    result.ph_rows = len(ph_df)
    result.htt_rows = len(htt_df)
    result.hub_rows = len(hub_df)
    result.blank_rows_removed = int(ph_df.attrs.get("blank_rows_removed", 0))

    if ph_df.empty:
        result.error = "P-H Master is empty. Nothing to export."
        db.log_master_sync({
            "master_type": "excel_export",
            "user_id": user_id,
            "records_synced": 0,
            "status": "failed",
            "error_message": result.error,
        })
        _record_versioning_failure(
            versioning,
            sync_run_id,
            user_id=user_id,
            action="validate",
            message=result.error,
            sheet_name="P-H Master",
        )
        return result

    validation_errors = run_master_data_validations(ph_df, p_df, hub_df)
    if validation_errors:
        result.validation_errors = validation_errors
        result.error = (
            f"P-H Master has {len(validation_errors)} validation errors — export blocked "
            f"(rules: {VALIDATION_VERSION})."
        )
        db.log_master_sync({
            "master_type": "excel_export",
            "user_id": user_id,
            "records_synced": 0,
            "status": "failed_validation",
            "error_message": result.error,
        })
        _record_versioning_failure(
            versioning,
            sync_run_id,
            user_id=user_id,
            action="validate",
            message=result.error,
            sheet_name="P-H Master",
        )
        return result

    if validate_only:
        result.success = True
        return result

    try:
        result.file_size_kb = write_masters_excel(
            excel_path, p_df, ph_df, htt_df, hub_df, progress=progress
        )
    except PermissionError:
        result.error = (
            "Permission denied — Product_Masters.xlsx is open in Excel. "
            "Close the file and retry."
        )
        return result
    except Exception as exc:
        result.error = f"Failed to write Excel: {exc}"
        db.log_master_sync({
            "master_type": "excel_export",
            "user_id": user_id,
            "records_synced": 0,
            "status": "failed",
            "error_message": str(exc),
        })
        _record_versioning_failure(
            versioning,
            sync_run_id,
            user_id=user_id,
            action="write",
            message=str(exc),
        )
        return result

    db.log_master_sync({
        "master_type": "excel_export",
        "user_id": user_id,
        "records_synced": len(ph_df),
        "status": "success",
        "error_message": (
            f"P Master: {len(p_df)} | P-H Master: {len(ph_df)} | "
            f"HTT: {len(htt_df)} | Hub Mapping: {len(hub_df)} | "
            f"File: {excel_path}"
        ),
    })
    try:
        from features.baseline.io import write_product_master_engine_sidecars

        write_product_master_engine_sidecars(excel_path)
    except Exception:
        pass
    _record_versioning_success(
        versioning,
        sync_run_id,
        user_id=user_id,
        p_df=p_df,
        ph_df=ph_df,
        htt_df=htt_df,
        hub_df=hub_df,
    )
    result.success = True
    try:
        from core.shared.api_cache import CacheNS, cache_invalidate


        cache_invalidate(CacheNS.MASTER_SHEET)
    except Exception:
        pass
    return result


def run_master_data_sync(
    *,
    db: Database | None = None,
    user_id: int | None = None,
    excel_path: str | Path | None = None,
    validate_only: bool = False,
) -> dict:
    """API-friendly wrapper around ``run_master_data_excel_sync``."""
    result = run_master_data_excel_sync(
        excel_path=excel_path,
        user_id=user_id,
        db=db,
        validate_only=validate_only,
    )
    return {
        "success": result.success,
        "excel_path": result.excel_path,
        "p_rows": result.p_rows,
        "ph_rows": result.ph_rows,
        "htt_rows": result.htt_rows,
        "hub_rows": result.hub_rows,
        "blank_rows_removed": result.blank_rows_removed,
        "file_size_kb": result.file_size_kb,
        "error": result.error,
        "validation_errors": result.validation_errors,
    }


def _ensure_project_cwd() -> None:
    os.chdir(PROJECT_ROOT)


def _save_state(result: MasterSyncResult) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "success": result.success,
        "excel_path": result.excel_path,
        "p_rows": result.p_rows,
        "ph_rows": result.ph_rows,
        "htt_rows": result.htt_rows,
        "hub_rows": result.hub_rows,
        "blank_rows_removed": result.blank_rows_removed,
        "file_size_kb": result.file_size_kb,
        "error": result.error,
        "validation_error_count": len(result.validation_errors),
    }
    _STATE_FILE.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _configure_logging(log_file: str | None, verbose: bool) -> logging.Logger:
    level = logging.DEBUG if verbose else logging.INFO
    logger = logging.getLogger("master_data_sync")
    logger.handlers.clear()
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    return logger


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Demand Planning masters from Google Sheets to FF_MASTERS_XLSX.",
    )
    parser.add_argument("--excel-path", default=None, help=f"Override Excel path (default: FF_MASTERS_XLSX).")
    parser.add_argument("--user-id", type=int, default=None, help="User ID for sync audit log.")
    parser.add_argument("--validate-only", action="store_true", help="Validate only; do not write Excel.")
    parser.add_argument("--log-file", default=None, help="Optional log file path.")
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_project_cwd()
    src = PROJECT_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    args = build_arg_parser().parse_args(argv)
    logger = _configure_logging(args.log_file, args.verbose)

    def _cli_progress(message: str, pct: float) -> None:
        logger.info("[%3.0f%%] %s", pct * 100, message)

    _progress_print("=" * 60)
    _progress_print("MASTER DATA SYNC — STARTED")
    _progress_print(f"Target: {args.excel_path or FF_MASTERS_XLSX}")
    _progress_print(f"Validation rules: {VALIDATION_VERSION}")
    if args.validate_only:
        _progress_print("Mode: validate-only (no Excel write)")
    _progress_print("=" * 60)

    result = run_master_data_excel_sync(
        excel_path=args.excel_path,
        user_id=args.user_id,
        validate_only=args.validate_only,
        progress=_cli_progress,
    )
    _save_state(result)

    if result.success:
        _progress_print(
            f"[OK] P={result.p_rows:,} P-H={result.ph_rows:,} "
            f"HTT={result.htt_rows:,} Hub={result.hub_rows:,}"
        )
        if not args.validate_only:
            _progress_print(f"[OK] Excel written ({result.file_size_kb:,} KB): {result.excel_path}")
        if result.blank_rows_removed:
            _progress_print(f"[INFO] Blank rows removed from P-H: {result.blank_rows_removed:,}")
        _progress_print("MASTER DATA SYNC — SUCCESS")
        return 0

    _progress_print(f"[FAILED] {result.error}")
    if result.validation_errors:
        _progress_print(f"[FAILED] Validation errors: {len(result.validation_errors):,}")
    _progress_print("MASTER DATA SYNC — FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
