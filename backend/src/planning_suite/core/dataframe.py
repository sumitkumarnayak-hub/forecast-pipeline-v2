"""Shared pandas DataFrame utilities."""
import pandas as pd


def drop_completely_blank_rows(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    Remove rows where every cell is empty, whitespace, or null.
    Returns (cleaned DataFrame, number of rows removed).
    """
    if df.empty:
        return df, 0

    str_df = df.fillna("").astype(str).apply(lambda series: series.str.strip())
    blank_mask = (str_df == "").all(axis=1)
    removed = int(blank_mask.sum())
    if removed == 0:
        return df, 0
    return df.loc[~blank_mask].reset_index(drop=True), removed


def clean_sheet_df(df: pd.DataFrame, *, drop_blank_rows: bool = True) -> pd.DataFrame:
    """
    Clean a DataFrame loaded from Google Sheets:
    - Reset index so Polars conversion is safe
    - Strip whitespace from column headers
    - Drop columns with empty/blank headers (trailing empty columns from Sheets)
    - Deduplicate column names by appending _2, _3, ... suffixes
    - Drop completely blank rows (optional, on by default)
    """
    if df.empty:
        return df

    df = df.reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, df.columns != ""]

    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 1
            new_cols.append(col)
    df.columns = new_cols

    blank_rows_removed = 0
    if drop_blank_rows:
        df, blank_rows_removed = drop_completely_blank_rows(df)

    df.attrs["blank_rows_removed"] = blank_rows_removed
    return df
