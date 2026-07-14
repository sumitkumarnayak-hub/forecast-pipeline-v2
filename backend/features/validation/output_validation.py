"""Validate baseline and final plan output files using Pandera."""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pandera as pa
from pandera.errors import SchemaErrors


def _result(valid: bool, errors: list[str], warnings: list[str], stats: dict | None = None) -> dict:
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "stats": stats or {},
    }


# Pandera Schema for Baseline Summary validation
BASELINE_SUMMARY_SCHEMA = pa.DataFrameSchema(
    columns={
        "city_name": pa.Column(nullable=False),
        "hub_name": pa.Column(nullable=False),
        "sub category": pa.Column(nullable=False),
        "SKU Class Prod": pa.Column(required=True),
        "day": pa.Column(required=True),
        "sugg_plan": pa.Column(required=True),
        "Base_Plan (qty)": pa.Column(required=True),
    },
    strict=False,
)


def validate_baseline_summary_df(df: pd.DataFrame) -> dict:
    """Validate an in-memory baseline summary DataFrame using Pandera."""
    errors: list[str] = []
    warnings: list[str] = []

    if df.empty:
        return _result(False, ["DataFrame is empty"], warnings)

    try:
        BASELINE_SUMMARY_SCHEMA.validate(df, lazy=True)
    except SchemaErrors as err:
        for _, row in err.failure_cases.iterrows():
            failure_type = row["check"]
            col = row["column"]
            if failure_type == "column_in_dataframe":
                errors.append(f"Missing expected columns: {col}")
            elif failure_type == "not_nullable":
                null_count = int(df[col].isna().sum()) if col in df.columns else 0
                errors.append(f"Found {null_count} null values in {col}")
            else:
                errors.append(f"Column '{col}' failed check: {failure_type}")

    # Fix naming/error messages compatibility
    # If any expected columns were missing, the original format was "Missing expected columns: col1, col2"
    # Let's map it back to match the original message formatting if any columns are missing
    expected_cols = ["city_name", "hub_name", "sub category", "SKU Class Prod", "day", "sugg_plan", "Base_Plan (qty)"]
    missing_cols = [col for col in expected_cols if col not in df.columns]
    if missing_cols:
        # Clear specific Pandera "Missing expected columns" errors to avoid duplication and return the original format
        errors = [e for e in errors if "Missing expected columns" not in e]
        errors.append(f"Missing expected columns: {', '.join(missing_cols)}")

    if "sugg_plan" in df.columns:
        negative_plan = (pd.to_numeric(df["sugg_plan"], errors="coerce") < 0).sum()
        if negative_plan > 0:
            warnings.append(f"Found {negative_plan} negative values in sugg_plan")

    # Format errors to be a clean, sorted, unique list
    errors = sorted(list(set(errors)))

    stats = {"rows": len(df), "columns": len(df.columns)}
    return _result(len(errors) == 0, errors, warnings, stats)


def validate_baseline_output(file_path: str | Path) -> dict:
    """Validate a baseline Summary_*.xlsx file."""
    errors: list[str] = []
    warnings: list[str] = []
    path = Path(file_path)

    if not path.exists():
        return _result(False, [f"File not found: {path}"], warnings)

    try:
        xls = pd.ExcelFile(path)
    except Exception as exc:
        return _result(False, [f"Cannot read Excel file: {exc}"], warnings)

    if not xls.sheet_names:
        errors.append("Workbook has no sheets")

    df = pd.read_excel(path, sheet_name=0)
    summary = validate_baseline_summary_df(df)
    errors.extend(summary["errors"])
    warnings.extend(summary["warnings"])

    if not df.empty:
        # Pandera schema check for extra columns
        extra_schema = pa.DataFrameSchema(
            columns={
                "hub_name": pa.Column(nullable=False, required=False),
                "product_id": pa.Column(nullable=False, required=False),
            },
            strict=False,
        )
        try:
            extra_schema.validate(df, lazy=True)
        except SchemaErrors as err:
            for _, row in err.failure_cases.iterrows():
                col = row["column"]
                if row["check"] == "not_nullable":
                    errors.append(f"Null values found in column '{col}'")

        numeric_cols = [c for c in df.columns if "plan" in c.lower() or "Plan" in c]
        if numeric_cols:
            total = pd.to_numeric(df[numeric_cols[0]], errors="coerce").fillna(0).sum()
            if total == 0:
                warnings.append(f"Total in '{numeric_cols[0]}' is zero")

    errors = sorted(list(set(errors)))
    stats = {
        "rows": len(df) if not df.empty else 0,
        "sheets": xls.sheet_names,
        **summary.get("stats", {}),
    }
    return _result(len(errors) == 0, errors, warnings, stats)


def validate_final_plan_output(file_path: str | Path) -> dict:
    """Validate a Hub_Dist_*.xlsx file."""
    errors: list[str] = []
    warnings: list[str] = []
    path = Path(file_path)

    if not path.exists():
        return _result(False, [f"File not found: {path}"], warnings)

    try:
        xls = pd.ExcelFile(path)
    except Exception as exc:
        return _result(False, [f"Cannot read Excel file: {exc}"], warnings)

    if len(xls.sheet_names) < 1:
        errors.append("Expected at least one sheet")

    df = pd.read_excel(path, sheet_name=0)
    if df.empty:
        errors.append("First sheet is empty")
    else:
        hub_col = next((c for c in df.columns if str(c).lower() in ("hub_name", "hub")), None)
        sku_col = next(
            (c for c in df.columns if "product" in str(c).lower() or "sku" in str(c).lower()),
            None,
        )
        dynamic_cols = {}
        if hub_col:
            dynamic_cols[hub_col] = pa.Column(nullable=False)
        if sku_col:
            dynamic_cols[sku_col] = pa.Column(nullable=False)

        if dynamic_cols:
            try:
                pa.DataFrameSchema(dynamic_cols, strict=False).validate(df, lazy=True)
            except SchemaErrors as err:
                for _, row in err.failure_cases.iterrows():
                    col = row["column"]
                    errors.append(f"Null values in '{col}'")

    errors = sorted(list(set(errors)))
    stats = {"rows": len(df) if not df.empty else 0, "sheets": xls.sheet_names}
    return _result(len(errors) == 0, errors, warnings, stats)


def find_latest_file(folder: Path, pattern: str) -> Path | None:
    if not folder.exists():
        return None
    files = sorted(folder.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

