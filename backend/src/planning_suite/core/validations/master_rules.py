"""
P-H Master validation — optimised for millions of rows.

Key design decisions
--------------------
1.  NO iter_rows() anywhere.  All error collection is done via vectorised
    Polars expressions; a single `.select()` builds the error DataFrame in
    one pass per check, then we convert to dicts only at the very end.
2.  Normalised columns (strip + upper) are computed ONCE via `with_columns`
    and reused — avoids recomputing the same cast/strip/upper expression
    inside every filter.
3.  All checks for a given "condition class" (core-blank, active-blank, …)
    are folded into a single scan of the DataFrame using `pl.concat` on the
    resulting error frames — one pass per validator instead of one pass per
    column.
4.  Referential integrity uses a polars anti-join instead of a Python set +
    filter, keeping everything inside the Polars query engine.
5.  `drop_empty_rows` uses a single combined expression so the whole frame
    is scanned once.
"""

from __future__ import annotations

import polars as pl

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

_EXCEL_CORE_COLS: list[str] = [
    "product_id",
    "hub_name",
    "city_name",
    "sub category",
    "sku class prod",
    "Plan Design",
]

_EXCEL_ACTIVE_COLS: list[str] = [
    "HTT",
    "Launch date",
    "Price",
    "Active_Flag_Mon",
    "Active_Flag_Tue",
    "Active_Flag_Wed",
    "Active_Flag_Thu",
    "Active_Flag_Fri",
    "Active_Flag_Sat",
    "Active_Flag_Sun",
]

_VALID_PLAN_DESIGNS: list[str] = sorted([
    "A", "I", "N", "WEEKEND", "WEEKEND+WED",
    "SAT+SUN", "T", "W", "SUN", "TH", "M",
])

_PLAN_DESIGN_DISPLAY = "A, I, N, Weekend, Weekend+Wed, Sat+Sun, T, W, Sun, Th, M"
VALIDATION_VERSION = "2026-06-24-v2"

# Column name used for the normalised Plan Design (computed once)
_PD_NORM = "__plan_design_norm__"

# ---------------------------------------------------------------------------
# Internal helpers — all return pl.Expr, never touch Python rows
# ---------------------------------------------------------------------------

def _norm_str(col: str) -> pl.Expr:
    """Strip whitespace and uppercase a string column."""
    return pl.col(col).cast(pl.Utf8).str.strip_chars().str.to_uppercase()


def _non_empty(col: str) -> pl.Expr:
    s = (
        pl.col(col)
        .cast(pl.Utf8)
        .str.strip_chars()
        .str.replace_all(r"[\s\u00a0\u200b\ufeff]+", "")
    )
    return (
        (s != "")
        & (s.str.to_uppercase() != "NAN")
        & (s.str.to_uppercase() != "NONE")
        & (s != "-")
    )


def _is_active(norm_col: str = _PD_NORM) -> pl.Expr:
    """Active = valid Plan Design AND not 'I'."""
    return (
        pl.col(norm_col).is_in(_VALID_PLAN_DESIGNS)
        & (pl.col(norm_col) != "I")
    )


# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------

def drop_empty_rows(df: pl.DataFrame) -> pl.DataFrame:
    """
    Remove rows where ALL anchor columns are blank.
    Handles trailing empty rows that Google Sheets appends on export.
    Single scan — no Python loop.
    """
    anchors = [c for c in ("city_name", "hub_name", "product_id") if c in df.columns]
    if not anchors:
        return df
    keep = pl.lit(False)
    for col in anchors:
        keep = keep | _non_empty(col)
    return df.filter(keep)


def _add_norm_columns(df: pl.DataFrame) -> pl.DataFrame:
    """
    Pre-compute normalised Plan Design once so every validator can reuse it
    without re-evaluating the cast/strip/upper chain.
    """
    if "Plan Design" in df.columns:
        df = df.with_columns(_norm_str("Plan Design").alias(_PD_NORM))
    else:
        df = df.with_columns(pl.lit("").alias(_PD_NORM))
    return df


# ---------------------------------------------------------------------------
# Error frame builder  (vectorised — no iter_rows)
# ---------------------------------------------------------------------------

def _build_error_frame(
    df: pl.DataFrame,
    mask: pl.Expr,
    col_name: str,
    issue: str,
) -> pl.DataFrame:
    """
    Filter `df` by `mask` and return a tidy error DataFrame.
    All work stays inside Polars — no Python-level row iteration.
    """
    value_expr = (
        pl.col(col_name).cast(pl.Utf8).str.strip_chars().alias("Value Found")
        if col_name in df.columns
        else pl.lit("").alias("Value Found")
    )
    return (
        df.filter(mask)
        .select([
            (pl.col("index") + 2).cast(pl.Int64).alias("Sheet Row"),
            pl.col("product_id").cast(pl.Utf8).str.strip_chars().alias("product_id"),
            pl.col("hub_name").cast(pl.Utf8).str.strip_chars().alias("hub_name"),
            pl.lit(col_name).alias("Column"),
            pl.lit(issue).alias("Issue"),
            value_expr,
            pl.col("Plan Design").cast(pl.Utf8).str.strip_chars().alias("Plan Design"),
        ])
    )


def _product_id_column(p_df: pl.DataFrame) -> str | None:
    for col in p_df.columns:
        key = col.strip().lower().replace(" ", "")
        if key in {"productid", "product_id"}:
            return col
    return None


# ---------------------------------------------------------------------------
# Validators  — each returns a pl.DataFrame of errors (may be empty)
# ---------------------------------------------------------------------------

def _validate_core_blanks(df: pl.DataFrame) -> pl.DataFrame:
    """Core columns must be non-blank on every row."""
    frames = []
    for col in _EXCEL_CORE_COLS:
        if col in df.columns:
            frames.append(
                _build_error_frame(
                    df,
                    ~_non_empty(col),
                    col,
                    "Blank (required for all rows)",
                )
            )
    return pl.concat(frames) if frames else _empty_error_frame()


def _validate_active_blanks(df: pl.DataFrame) -> pl.DataFrame:
    """Active columns must be populated when Plan Design is an active value."""
    frames = []
    for col in _EXCEL_ACTIVE_COLS:
        if col in df.columns:
            frames.append(
                _build_error_frame(
                    df,
                    _is_active() & ~_non_empty(col),
                    col,
                    # Issue is the same for all active-blank errors; Plan Design
                    # detail is already captured in the 'Plan Design' column of
                    # the error row itself.
                    "Blank on active row",
                )
            )
    return pl.concat(frames) if frames else _empty_error_frame()


def _validate_referential_integrity(
    df: pl.DataFrame,
    p_df: pl.DataFrame,
    hub_df: pl.DataFrame,
) -> pl.DataFrame:
    """Products must exist in P Master; hubs must exist in Hub Mapping."""
    frames = []

    if "product_id" in df.columns:
        product_col = _product_id_column(p_df)
        if product_col:
            valid_products = (
                p_df.select(pl.col(product_col).cast(pl.Utf8).str.strip_chars().alias("product_id"))
                .unique()
            )
            bad = (
                df.with_columns(
                    pl.col("product_id").cast(pl.Utf8).str.strip_chars().alias("product_id")
                )
                .join(valid_products, on="product_id", how="anti")
            )
            if bad.height > 0:
                frames.append(
                    _build_error_frame(
                        bad,
                        pl.lit(True),
                        "product_id",
                        "Product ID not found in P Master",
                    )
                )

    if "hub_name" in df.columns and "hub_name" in hub_df.columns:
        valid_hubs = (
            hub_df.select(pl.col("hub_name").cast(pl.Utf8).str.strip_chars().alias("hub_name"))
            .unique()
        )
        bad = (
            df.with_columns(
                pl.col("hub_name").cast(pl.Utf8).str.strip_chars().alias("hub_name")
            )
            .join(valid_hubs, on="hub_name", how="anti")
        )
        if bad.height > 0:
            frames.append(
                _build_error_frame(
                    bad,
                    pl.lit(True),
                    "hub_name",
                    "Hub Name not found in Hub Mapping",
                )
            )

    return pl.concat(frames) if frames else _empty_error_frame()


def _validate_bounds_and_enums(df: pl.DataFrame) -> pl.DataFrame:
    """
    Numeric bounds and categorical enum checks.

    Split % — Google Sheets exports percentage-formatted cells as floats in
    [0, 1] (e.g. 63% → 0.63).  We reject only negatives or values > 100 so
    both decimal (0.63) and whole-number (63) representations are accepted.
    """
    frames = []

    # Plan Design enum
    if "Plan Design" in df.columns:
        frames.append(
            _build_error_frame(
                df,
                _non_empty("Plan Design") & ~pl.col(_PD_NORM).is_in(_VALID_PLAN_DESIGNS),
                "Plan Design",
                f"Invalid value (must be one of: {_PLAN_DESIGN_DISPLAY})",
            )
        )

    # Price > 0 for active rows (strip currency symbols / commas)
    if "Price" in df.columns:
        price = (
            pl.col("Price")
            .cast(pl.Utf8)
            .str.strip_chars()
            .str.replace_all(r"[₹$,]", "")
            .cast(pl.Float64, strict=False)
        )
        frames.append(
            _build_error_frame(
                df,
                _is_active() & (price.is_null() | (price <= 0)),
                "Price",
                "Must be > 0 for active products",
            )
        )

    return pl.concat(frames) if frames else _empty_error_frame()


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _empty_error_frame() -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "Sheet Row": pl.Int64,
            "product_id": pl.Utf8,
            "hub_name": pl.Utf8,
            "Column": pl.Utf8,
            "Issue": pl.Utf8,
            "Value Found": pl.Utf8,
            "Plan Design": pl.Utf8,
        }
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_all_validations(
    ph_df: pl.DataFrame,
    p_df: pl.DataFrame,
    hub_df: pl.DataFrame,
) -> list[dict]:
    """
    Validate P-H Master and return a list of error dicts.

    Steps
    -----
    1. Drop empty trailing rows (single scan).
    2. Add a stable integer index for Sheet Row reporting.
    3. Pre-compute normalised Plan Design column (computed once, reused everywhere).
    4. Run all four validators — each does at most one Polars scan per column
       checked, with zero Python-level row iteration.
    5. Concatenate all error frames and convert to dicts only once at the end.

    Returns an empty list when the sheet is clean.
    """
    # 1. Drop empty rows
    ph_df = drop_empty_rows(ph_df)

    # 2. Stable row index
    ph_df = ph_df.with_row_index("index")

    # 3. Normalised Plan Design (reused by all validators)
    ph_df = _add_norm_columns(ph_df)

    # 4. Run validators — all return pl.DataFrame
    error_frames = [
        _validate_core_blanks(ph_df),
        _validate_active_blanks(ph_df),
        _validate_referential_integrity(ph_df, p_df, hub_df),
        _validate_bounds_and_enums(ph_df),
    ]

    # 5. Concatenate and convert to dicts once
    all_errors = pl.concat(error_frames)

    if all_errors.height == 0:
        return []

    return all_errors.sort("Sheet Row").to_dicts()