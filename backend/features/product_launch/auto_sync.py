"""
Headless new product launch sync — P Master → P-H Master (Product new-product-sync).
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field

from app.config import PROJECT_ROOT
from core.database.engine import Database

from features.product_launch.sync import (
    ProductLaunchSyncResult,
    run_new_product_launch_sync,
)


@dataclass
class NewProductLaunchResult:
    """Alias for automation runners (matches prior NewHubLaunchResult shape)."""
    success: bool
    products_found: int = 0
    rows_inserted: int = 0
    duplicates_skipped: int = 0
    masters_re_synced: bool = False
    ph_rows_after: int = 0
    products_synced: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def exit_code(self) -> int:
        return 0 if self.success else 1

    @classmethod
    def from_sync(cls, r: ProductLaunchSyncResult) -> NewProductLaunchResult:
        return cls(
            success=r.success,
            products_found=r.products_found,
            rows_inserted=r.rows_inserted,
            duplicates_skipped=r.duplicates_skipped,
            masters_re_synced=r.masters_re_synced,
            ph_rows_after=r.ph_rows_after,
            products_synced=r.products_synced,
            error=r.error,
        )


def run_new_product_launch_sync_cli(
    user_id: int | None = None,
    *,
    db: Database | None = None,
    dry_run: bool = False,
    re_sync_masters: bool = True,
    product_ids: list[str] | None = None,
    sheets=None,
) -> NewProductLaunchResult:
    inner = run_new_product_launch_sync(
        user_id,
        db=db,
        product_ids=product_ids,
        dry_run=dry_run,
        re_sync_masters=re_sync_masters,
        sheets=sheets,
    )
    return NewProductLaunchResult.from_sync(inner)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync new products from P Master to P-H Master (all active hubs).",
    )
    parser.add_argument("--user-id", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write.")
    parser.add_argument("--no-resync", action="store_true", help="Skip Product_Masters.xlsx re-sync.")
    parser.add_argument(
        "--product-ids",
        default="",
        help="Comma-separated product IDs (default: auto-discover new products in P Master).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    src = PROJECT_ROOT / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    pids = [x.strip() for x in args.product_ids.split(",") if x.strip()] or None
    result = run_new_product_launch_sync_cli(
        user_id=args.user_id,
        dry_run=args.dry_run,
        re_sync_masters=not args.no_resync,
        product_ids=pids,
    )
    if result.products_found == 0:
        print("No new products to sync — all P Master SKUs already exist in P-H Master.")
    elif result.success:
        print(
            f"New product launch sync OK: {result.rows_inserted} row(s) inserted "
            f"for {len(result.products_synced)} product(s), "
            f"{result.duplicates_skipped} duplicate(s) skipped."
        )
        if result.masters_re_synced:
            print(f"Product_Masters.xlsx refreshed ({result.ph_rows_after:,} P-H rows).")
    else:
        print(f"Failed: {result.error}", file=sys.stderr)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
