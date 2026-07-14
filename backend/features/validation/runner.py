import pandas as pd
from core.utils.dataframe import clean_sheet_df

from features.validation.rules import run_all_validations


def run_master_data_validations(ph_df: pd.DataFrame, p_df: pd.DataFrame, hub_df: pd.DataFrame) -> list[dict]:
    """
    Executes all validation rules against the Master Data sheets.
    Converts to polars for ultra-fast vectorized checks.
    Returns a list of error dictionaries.
    """
    import polars as pl

    ph_df = clean_sheet_df(ph_df)
    if ph_df.empty:
        return []

    p_df = clean_sheet_df(p_df)
    hub_df = clean_sheet_df(hub_df)

    pl_ph = pl.from_pandas(ph_df)
    pl_p = pl.from_pandas(p_df)
    pl_hub = pl.from_pandas(hub_df)

    return run_all_validations(pl_ph, pl_p, pl_hub)
