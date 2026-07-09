"""
New Hub Launch Service

Clones active product configurations from a source reference hub to a newly launched
hub inside the P-H Master sheet, with support for batch preview calculations from FF Input.
"""
from __future__ import annotations
import pandas as pd
from typing import Dict, Any, List, Tuple
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.core.dataframe import clean_sheet_df, df_to_records, sanitize_for_json

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

def build_new_hub_sync_preview(sheets: GoogleSheetsManager, bypass_cache: bool = False) -> Dict[str, Any]:
    """
    Reads 'FF Input' tab from NEW_HUB_LAUNCH_SHEET_KEY and matches against P-H Master & Hub Mapping.
    Returns preview summary and rows to be added.
    """
    use_cache = not bypass_cache
    # 1. Read worksheets using cached TTL methods matching SHEETS_CONFIG keys for global Parquet caching
    hub_df = sheets.read_worksheet_uncached("demand_planning_masters", "hub_mapping", HUB_MASTER_READ_RANGE, use_cache=use_cache)
    ph_df = sheets.read_worksheet_uncached("demand_planning_masters", "product_hub_master", PH_MASTER_READ_RANGE, use_cache=use_cache)
    ff_df = sheets.read_worksheet_uncached("new_hub_launch", "ff_input", "A:H", use_cache=use_cache)

    if ff_df is None or ff_df.empty:
        # Fallback to direct read if cache read failed
        from planning_suite.config import NEW_HUB_LAUNCH_SHEET_KEY
        raw = sheets.batch_read_worksheets(NEW_HUB_LAUNCH_SHEET_KEY, [("FF Input", "A:H")])
        data = raw.get("FF Input") or []
        if len(data) >= 2:
            ff_df = clean_sheet_df(pd.DataFrame(data[1:], columns=data[0]))

    if hub_df is None or hub_df.empty or ph_df is None or ph_df.empty or ff_df is None or ff_df.empty:
        raise ValueError("Could not read Hub Mapping, P-H Master, or FF Input sheet configuration.")

    # Retrieve canonical headers
    ph_headers = list(ph_df.columns)
    hub_headers = list(hub_df.columns)
    ff_headers = list(ff_df.columns)

    # Normalize column names
    ph_cols = _col_map(ph_df.columns)
    hub_col = _actual(ph_cols, "hub_name")
    prod_id_col = _actual(ph_cols, "product_id")

    ff_cols = _col_map(ff_df.columns)
    ff_hub_col = _actual(ff_cols, "hub_name")
    ff_source_col = _actual(ff_cols, "source_hub")

    # Extract new hub mapping pairs
    mappings: List[Tuple[str, str]] = []
    seen_pairs = set()
    for _, row in ff_df.iterrows():
        nh = str(row.get(ff_hub_col, "")).strip()
        sh = str(row.get(ff_source_col, "")).strip()
        if not nh or not sh:
            continue
        pair = (nh, sh)
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            mappings.append(pair)

    if not mappings:
        raise ValueError("No valid Hub_name/Source_Hub pairs found in FF Input sheet tab.")

    # Validate Hub Mapping rows
    unique_new_hubs = sorted({p[0] for p in mappings})
    validation_errors = validate_new_hub_mapping_rows(hub_df, unique_new_hubs)

    h_cols = _col_map(hub_df.columns)
    h_hub_col = _actual(h_cols, "hub_name")
    h_col_map = build_column_mapping(ph_headers, hub_headers)

    hub_lookup = {}
    for _, r in hub_df.iterrows():
        name = str(r.get(h_hub_col, "")).strip()
        if name:
            hub_lookup[name] = r

    # Pre-build lookup map for source hub rows in O(N) time
    source_hubs_set = {sh.lower() for nh, sh in mappings}
    source_rows_by_hub = {}
    for _, r in ph_df.iterrows():
        sh_val = str(r.get(hub_col, "")).strip().lower()
        if sh_val in source_hubs_set:
            source_rows_by_hub.setdefault(sh_val, []).append(r)

    # Build existing keys to prevent duplicates using set lookup
    existing_keys = set(zip(
        ph_df[prod_id_col].astype(str).str.strip(),
        ph_df[hub_col].astype(str).str.strip().str.lower()
    ))

    preview_rows = []
    mapping_report = []
    total_inserted = 0
    total_skipped = 0

    for new_hub, source_hub in mappings:
        source_rows = source_rows_by_hub.get(source_hub.lower(), [])
        if not source_rows:
            mapping_report.append({
                "new_hub": new_hub,
                "source_hub": source_hub,
                "status": "error",
                "message": f"Source hub '{source_hub}' has no rows in P-H Master",
            })
            continue

        new_hub_data = hub_lookup.get(new_hub)
        inserted_for_pair = 0
        skipped_for_pair = 0

        for src in source_rows:
            cloned = {h: src.get(h, "") for h in ph_headers}
            
            # Map Hub Mapping columns (city, tier, region, etc.)
            if new_hub_data is not None and h_col_map:
                for ph_col, h_col in h_col_map.items():
                    cloned[ph_col] = str(new_hub_data.get(h_col, "")).strip()

            # Set new Hub ID & Name identity
            cloned[hub_col] = new_hub
            pid = str(cloned.get(prod_id_col, "")).strip()
            
            if (pid, new_hub.lower()) in existing_keys:
                skipped_for_pair += 1
                total_skipped += 1
                continue

            existing_keys.add((pid, new_hub.lower()))
            inserted_for_pair += 1
            total_inserted += 1
            preview_rows.append(cloned)

        mapping_report.append({
            "new_hub": new_hub,
            "source_hub": source_hub,
            "status": "ok",
            "rows_inserted": inserted_for_pair,
            "duplicates_skipped": skipped_for_pair,
        })

    # 4. Resolve cache modified timestamp for user info tracking
    import os
    import time
    from planning_suite.services import sheets_cache
    cache_path = sheets_cache.cache_path_for_category("new_hub_launch", "ff_input", "A:H")
    
    last_updated = None
    if cache_path.exists():
        try:
            mtime = cache_path.stat().st_mtime
            # Return ISO format string for Javascript parsing
            last_updated = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(mtime))
        except Exception:
            pass

    return sanitize_for_json({
        "success": True,
        "validation_errors": validation_errors,
        "rows_to_add": preview_rows,
        "ph_headers": ph_headers,
        "duplicates_skipped": total_skipped,
        "mapping_report": mapping_report,
        "total_to_insert": total_inserted,
        "cache_last_updated": last_updated,
    })

def clone_from_source_hub_mapping(
    sheets: GoogleSheetsManager,
    new_hub: str,
    source_hub: str,
) -> Dict[str, Any]:
    """Legacy individual new hub launcher sync logic."""
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
