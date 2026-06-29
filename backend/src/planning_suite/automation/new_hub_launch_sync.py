"""
Headless new hub launch sync — Hub_Changes (pipeline params) → P-H Master clone → optional Excel re-sync.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from planning_suite.config import FF_MASTERS_XLSX, PIPELINE_PARAMS_SHEET_URL, PROJECT_ROOT
from planning_suite.db.engine import Database
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.services.hub_launch_sync import (
    clone_ph_master_from_hub_mappings,
    extract_hub_launch_mappings,
    normalize_hub_changes_df,
)


@dataclass
class NewHubLaunchResult:
    success: bool
    mappings_found: int = 0
    rows_inserted: int = 0
    duplicates_skipped: int = 0
    masters_re_synced: bool = False
    ph_rows_after: int = 0
    mapping_report: list = field(default_factory=list)
    error: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1


def run_new_hub_launch_sync(
    user_id: int | None = None,
    *,
    db: Database | None = None,
    dry_run: bool = False,
    re_sync_masters: bool = True,
) -> NewHubLaunchResult:
    """Read Hub_Changes from pipeline params, clone P-H Master rows, optionally refresh Excel."""
    if not PIPELINE_PARAMS_SHEET_URL:
        return NewHubLaunchResult(success=False, error="PIPELINE_PARAMS_SHEET_URL is not set in .env")

    sheets = GoogleSheetsManager()
    sheets.ensure_pipeline_params_hub_changes_tab()
    hub_df = normalize_hub_changes_df(sheets.read_hub_changes_table())
    mappings = extract_hub_launch_mappings(hub_df)

    result = NewHubLaunchResult(success=True, mappings_found=len(mappings))
    if not mappings:
        return result

    clone = clone_ph_master_from_hub_mappings(sheets, mappings, dry_run=dry_run)
    result.mapping_report = clone.mapping_report
    result.rows_inserted = clone.rows_inserted
    result.duplicates_skipped = clone.duplicates_skipped

    if not clone.success:
        result.success = False
        result.error = "; ".join(clone.validation_errors)
        return result

    if re_sync_masters and clone.rows_inserted > 0 and not dry_run:
        from planning_suite.automation.master_data_sync import run_master_data_excel_sync

        sync = run_master_data_excel_sync(FF_MASTERS_XLSX, user_id or 1, db=db or Database())
        result.masters_re_synced = sync.success
        result.ph_rows_after = sync.ph_rows
        if not sync.success:
            result.success = False
            result.error = sync.error or "Master re-sync failed after P-H clone."

    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync new hub P-H Master rows from Hub_Changes tab.")
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write to Sheets.")
    parser.add_argument("--no-resync", action="store_true", help="Skip Product_Masters.xlsx re-sync.")
    return parser


def main(argv: list[str] | None = None) -> int:
    src = PROJECT_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    result = run_new_hub_launch_sync(
        user_id=args.user_id,
        dry_run=args.dry_run,
        re_sync_masters=not args.no_resync,
    )
    if result.mappings_found == 0:
        print("No New Hub mappings in Hub_Changes tab — nothing to do.")
    elif result.success:
        print(
            f"New hub launch sync OK: {result.rows_inserted} row(s) inserted, "
            f"{result.duplicates_skipped} duplicate(s) skipped."
        )
        if result.masters_re_synced:
            print(f"Product_Masters.xlsx refreshed ({result.ph_rows_after:,} P-H rows).")
    else:
        print(f"Failed: {result.error}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
