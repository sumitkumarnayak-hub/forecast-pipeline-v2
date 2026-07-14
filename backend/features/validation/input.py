"""Input data validation — Pandera schemas (Streamlit validation.py parity)."""
from __future__ import annotations

import io
from typing import Any

import pandas as pd
import pandera as pa
from pandera.errors import SchemaErrors

RAW_SALES_SCHEMA = pa.DataFrameSchema(
    columns={
        "process_dt": pa.Column(required=True),
        "product_id": pa.Column(nullable=False, required=True),
        "hub_name": pa.Column(nullable=False, required=True),
        "city_name": pa.Column(required=True),
        "Sales (qty)": pa.Column(required=True),
        "sub category": pa.Column(required=True),
        "day": pa.Column(required=True),
    },
    strict=False,
)

HUB_CHANGES_SCHEMA = pa.DataFrameSchema(
    columns={
        "Type": pa.Column(str, checks=pa.Check.isin(["New Hub", "KML Remapping"]), required=True),
        "Hub_name": pa.Column(str, required=True),
        "Source_Hub": pa.Column(str, required=True),
        "Percentage": pa.Column(float, checks=pa.Check.in_range(0, 100), required=True, coerce=True),
        "Start_date": pa.Column(str, required=True),
        "End_date": pa.Column(str, required=True),
    },
    strict=False,
)

OUTLIER_DAYS_SCHEMA = pa.DataFrameSchema(
    columns={
        "city_name": pa.Column(required=True),
        "sub category": pa.Column(required=True),
        "process_dt": pa.Column(required=True),
        "Outlier_Flag": pa.Column(required=True),
    },
    strict=False,
)

PERCENTILE_SCHEMA = pa.DataFrameSchema(
    columns={
        "city_name": pa.Column(required=True),
        "sub category": pa.Column(required=True),
        "day": pa.Column(required=True),
        "Percentile": pa.Column(float, checks=pa.Check.in_range(0, 1), required=True, coerce=True),
    },
    strict=False,
)

INPUT_TYPES = [
    {"id": "raw_data", "label": "Raw Sales Data"},
    {"id": "hub_changes", "label": "Hub Changes"},
    {"id": "outlier", "label": "Outlier Days"},
    {"id": "percentile", "label": "Percentile Data"},
]


def read_uploaded_table(content: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(content)
    if filename.lower().endswith(".csv"):
        return pd.read_csv(buf)
    return pd.read_excel(buf)


def _validate_raw_data(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_cols = [
        "process_dt", "product_id", "hub_name", "city_name",
        "Sales (qty)", "sub category", "day",
    ]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")
        return errors, warnings

    try:
        RAW_SALES_SCHEMA.validate(df, lazy=True)
    except SchemaErrors as err:
        for _, row in err.failure_cases.iterrows():
            col = row["column"]
            check = row["check"]
            if col == "product_id" and check == "not_nullable":
                errors.append(f"Found {int(df['product_id'].isna().sum())} null product IDs")
            elif col == "hub_name" and check == "not_nullable":
                errors.append(f"Found {int(df['hub_name'].isna().sum())} null hub names")

    if "Sales (qty)" in df.columns:
        sales_col = pd.to_numeric(df["Sales (qty)"], errors="coerce")
        neg = int((sales_col < 0).sum())
        if neg > 0:
            warnings.append(f"Found {neg} records with negative sales")

    if "process_dt" in df.columns:
        parsed = pd.to_datetime(df["process_dt"], errors="coerce")
        if parsed.isna().any():
            errors.append("Invalid date format in process_dt: contains non-parseable values")

    return sorted(set(errors)), sorted(set(warnings))


def _validate_hub_changes(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_cols = ["Type", "Hub_name", "Source_Hub", "Percentage", "Start_date", "End_date"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")
        return errors, warnings

    try:
        HUB_CHANGES_SCHEMA.validate(df, lazy=True)
    except SchemaErrors:
        invalid_vals = df[~df["Type"].isin(["New Hub", "KML Remapping"])]["Type"].unique().tolist()
        if invalid_vals:
            errors.append(f"Invalid Type values found: {invalid_vals}")
        pct_col = pd.to_numeric(df["Percentage"], errors="coerce")
        invalid_pct = int(((pct_col < 0) | (pct_col > 100)).sum())
        if invalid_pct:
            errors.append(f"Invalid percentages found (must be 0-100): {invalid_pct} rows")

    try:
        start_dates = pd.to_datetime(df["Start_date"], errors="coerce")
        end_dates = pd.to_datetime(df["End_date"], errors="coerce")
        if start_dates.isna().any() or end_dates.isna().any():
            errors.append("Date validation error: invalid or non-parseable dates")
        else:
            invalid_dates = int((start_dates > end_dates).sum())
            if invalid_dates:
                warnings.append(f"Found {invalid_dates} rows where Start_date > End_date")
    except Exception as exc:
        errors.append(f"Date validation error: {exc}")

    return sorted(set(errors)), sorted(set(warnings))


def _validate_outlier_data(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_cols = ["city_name", "sub category", "process_dt", "Outlier_Flag"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")
        return errors, warnings

    try:
        OUTLIER_DAYS_SCHEMA.validate(df, lazy=True)
    except SchemaErrors:
        pass

    if "Outlier_Flag" in df.columns:
        unique_flags = df["Outlier_Flag"].unique()
        if not all(flag in [0, 1, "0", "1"] for flag in unique_flags if pd.notna(flag)):
            warnings.append("Outlier_Flag should only contain 0 or 1")

    return sorted(set(errors)), sorted(set(warnings))


def _validate_percentile_data(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_cols = ["city_name", "sub category", "day", "Percentile"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {', '.join(missing_cols)}")
        return errors, warnings

    try:
        PERCENTILE_SCHEMA.validate(df, lazy=True)
    except SchemaErrors:
        pct_col = pd.to_numeric(df["Percentile"], errors="coerce")
        invalid_pct = int(((pct_col < 0) | (pct_col > 1)).sum())
        if invalid_pct:
            errors.append(f"Invalid percentiles found (must be 0-1): {invalid_pct} rows")

    return sorted(set(errors)), sorted(set(warnings))


def validate_input_dataframe(df: pd.DataFrame, data_type: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {"valid": False, "errors": ["DataFrame is empty or None"], "warnings": [], "rows": 0, "columns": 0}

    validators = {
        "raw_data": _validate_raw_data,
        "hub_changes": _validate_hub_changes,
        "outlier": _validate_outlier_data,
        "percentile": _validate_percentile_data,
    }
    fn = validators.get(data_type)
    if not fn:
        return {"valid": False, "errors": [f"Unknown data type: {data_type}"], "warnings": [], "rows": len(df), "columns": len(df.columns)}

    errors, warnings = fn(df)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "rows": len(df),
        "columns": len(df.columns),
        "preview_columns": df.columns.tolist()[:20],
    }
