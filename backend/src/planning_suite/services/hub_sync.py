"""
New Hub Launch Service

Clones active product configurations from a source reference hub to a newly launched
hub inside the P-H Master sheet.
"""
from __future__ import annotations
import pandas as pd
from typing import Dict, Any, List, Tuple
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.core.dataframe import clean_sheet_df

P_MASTER_READ_RANGE = "A:K"
PH_MASTER_READ_RANGE = "A:AX"
HUB_MASTER_READ_RANGE = "A:F"

def _normalize(text: str) -> str:
    return "".join(ch.lower() for ch in str(text).strip() if ch.isalnum())

def _col_map(columns) -> dict[str, str]:
    return {_normalize(c): c for c in columns}

def _actual(norm_map: dict[str, str], wanted: str) -> str:
    return norm_map.get(_normalize(wanted), wanted)

def validate_new_hub_mapping_rows(hub_df: pd.DataFrame, unique_new_hubs: List[str]) -> List[str]:
    """Verify that each new hub has a row configured in Hub Mapping."""
    errors = []
    if hub_df.empty:
        errors.append("Hub Mapping tab is empty.")
        return errors
        
    hub_cols = _col_map(hub_df.columns)
    hub_name_col = _actual(hub_cols, "hub_name")
    
    existing_hubs = {str(val).strip().lower() for val in hub_df[hub_name_col].dropna()}
    for hub in unique_new_hubs:
        if hub.lower() not in existing_hubs:
            errors.append(f"Hub Mapping missing row for new hub '{hub}'.")
    return errors

def build_column_mapping(ph_headers: List[str], h_headers: List[str]) -> Dict[str, str]:
    """Build key lookup map for matching columns between P-H Master and Hub Mapping."""
    source_lookup = {_normalize(h): h for h in h_headers}
    mapping = {}
    for th in ph_headers:
        match = source_lookup.get(_normalize(th))
        if match:
            mapping[th] = match
    return mapping

def clone_from_source_hub_mapping(
    sheets: GoogleSheetsManager,
    new_hub: str,
    source_hub: str,
) -> Dict[str, Any]:
    from planning_suite.config import DEMAND_PLANNING_SHEET_ID
    
    # 1. Fetch P-H Master and Hub Mapping worksheets
    raw = sheets.batch_read_worksheets(
        DEMAND_PLANNING_SHEET_ID,
        [
            ("Hub Mapping", HUB_MASTER_READ_RANGE),
            ("P-H Master", PH_MASTER_READ_RANGE),
        ],
    )
    
    def _to_df(name: str) -> pd.DataFrame:
        data = raw.get(name) or []
        if not data or len(data) < 2:
            return pd.DataFrame()
        return clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))
        
    hub_df = _to_df("Hub Mapping")
    ph_df = _to_df("P-H Master")
    
    if hub_df.empty or ph_df.empty:
        raise ValueError("Could not read Hub Mapping or P-H Master sheets data.")
        
    ph_headers = raw["P-H Master"][0]
    hub_headers = raw["Hub Mapping"][0]
    
    # 2. Get columns
    ph_cols = _col_map(ph_df.columns)
    hub_col = _actual(ph_cols, "hub_name")
    
    # 3. Check Hub Mapping presence
    validation_errors = validate_new_hub_mapping_rows(hub_df, [new_hub])
    if validation_errors:
        raise ValueError(validation_errors[0])
        
    # Build Hub lookup map
    h_cols = _col_map(hub_df.columns)
    h_hub_col = _actual(h_cols, "hub_name")
    h_col_map = build_column_mapping(ph_headers, hub_headers)
    
    hub_lookup = {}
    for _, r in hub_df.iterrows():
        name = str(r.get(h_hub_col, "")).strip()
        if name:
            hub_lookup[name] = r
            
    # 4. Filter source hub rows
    source_rows = [r for _, r in ph_df.iterrows() if str(r.get(hub_col, "")).strip().lower() == source_hub.strip().lower()]
    if not source_rows:
        raise ValueError(f"Source reference hub '{source_hub}' has no mapping rows in P-H Master.")
        
    # Get existing pairs to prevent duplicates
    existing_pairs = {
        (str(r.get(_actual(ph_cols, "product_id"), "")).strip(), str(r.get(hub_col, "")).strip().lower())
        for _, r in ph_df.iterrows()
    }
    
    new_hub_data = hub_lookup.get(new_hub, {})
    inserts: List[List[str]] = []
    skipped = 0
    
    for src in source_rows:
        cloned = {h: src.get(h, "") for h in ph_headers}
        
        # Clone relevant columns from Hub Mapping row details (e.g. city name, region, Tier)
        if new_hub_data is not None and h_col_map:
            for ph_col, h_col in h_col_map.items():
                cloned[ph_col] = str(new_hub_data.get(h_col, "")).strip()
                
        # Assign new hub identity
        cloned[hub_col] = new_hub
        
        pid = str(cloned.get(_actual(ph_cols, "product_id"), "")).strip()
        if (pid, new_hub.lower()) in existing_pairs:
            skipped += 1
            continue
            
        inserts.append([cloned.get(h, "") for h in ph_headers])
        existing_pairs.add((pid, new_hub.lower()))
        
    # 5. Append to P-H Master sheet
    if inserts:
        ss = sheets.gc.open_by_key(DEMAND_PLANNING_SHEET_ID)
        ph_ws = ss.worksheet("P-H Master")
        sheets.append_rows_to_worksheet(
            "demand_planning_masters",
            "product_hub_master",
            inserts,
            worksheet=ph_ws,
            value_input_option="RAW",
        )
        
    return {
        "success": True,
        "rows_inserted": len(inserts),
        "duplicates_skipped": skipped,
        "status": "success",
    }
