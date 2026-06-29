# %%
import sys
import os
import re
from functools import reduce
from datetime import datetime as _datetime
import os as _os

# Force UTF-8 output on Windows — reconfigure can fail on a captured pipe, so wrap safely
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import pyreadr
import pandas as pd
import numpy as np
from gspread_dataframe import set_with_dataframe

# %%
# =============================================================================
# LOAD RAW ACTUALS — Read directly from parquet repository (built by Streamlit app)
# =============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
_src = os.path.join(PROJECT_ROOT, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from planning_suite.config import (
    CLUSTER_MASTER_SHEET_URL,
    DP_LOGICS_SHEET_URL,
    HUB_LEVEL_PLANNING_SHEET_URL,
    NEW_HUB_LAUNCH_SHEET_URL,
    PIPELINE_PARAMS_HUB_CHANGES_TAB,
    VALIDATION_SHEET_URL,
    RAW_ACTUALS_FOLDER,
    FF_MASTERS_XLSX,
    DP_LOGICS_FOLDER,
    BASELINE_OUTPUTS_FOLDER,
)
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.services.helpers import normalize_base_plan_columns
from planning_suite.services.baseline_io import (
    avl_flag_subcat_cat_df,
    load_percentile_slices_engine,
    load_product_masters_sheets_engine,
    read_dp_logics_table_engine,
)

REPOSITORY_FOLDER = RAW_ACTUALS_FOLDER
ACTIVE_DATASET_PATH = os.environ.get(
    "BASELINE_ACTIVE_DATASET_PATH",
    os.path.join(PROJECT_ROOT, "outputs", "active_dataset.parquet")
)
USE_ACTIVE_ONLY = os.environ.get("BASELINE_USE_ACTIVE_DATASET", "0") == "1"

# %%
# In app mode, consume only UI-selected weeks from active_dataset.parquet.
# In standalone mode, keep legacy behavior (load all repository week files).
if USE_ACTIVE_ONLY:
    if not os.path.exists(ACTIVE_DATASET_PATH):
        raise FileNotFoundError(
            f"BASELINE_USE_ACTIVE_DATASET=1 but active dataset not found: {ACTIVE_DATASET_PATH}"
        )
    main_df = pd.read_parquet(ACTIVE_DATASET_PATH)
    all_week_files = [f"active_dataset.parquet ({ACTIVE_DATASET_PATH})"]
    print(f"[INFO] Using UI-selected weeks only from: {ACTIVE_DATASET_PATH}")
else:
    # Load all parquet week files and combine (fall back to xlsx if no parquet)
    parquet_files = sorted([f for f in os.listdir(REPOSITORY_FOLDER) if f.startswith("Raw_Actuals_Wk") and f.endswith(".parquet")])
    xlsx_files    = sorted([f for f in os.listdir(REPOSITORY_FOLDER) if f.startswith("Raw_Actuals_Wk") and f.endswith(".xlsx")])
    parquet_weeks = {int(f.replace("Raw_Actuals_Wk","").replace(".parquet","")) for f in parquet_files}
    all_week_files = parquet_files + [f for f in xlsx_files if int(f.replace("Raw_Actuals_Wk","").replace(".xlsx","")) not in parquet_weeks]

    if not all_week_files:
        raise FileNotFoundError(f"No week files found in: {REPOSITORY_FOLDER}")

    def _load_week_file(f):
        fpath = os.path.join(REPOSITORY_FOLDER, f)
        return pd.read_parquet(fpath) if f.endswith(".parquet") else pd.read_excel(fpath)

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=min(len(all_week_files), 8)) as _exe:
        all_dfs = list(_exe.map(_load_week_file, all_week_files))

    main_df = pd.concat(all_dfs, ignore_index=True)

# %%
# Drop rows where product_id is blank (only what's available before P Master mapping)
before = len(main_df)
main_df = main_df[main_df["product_id"].notna() & (main_df["product_id"].astype(str).str.strip() != "")]
print(f"Rows dropped (blank product_id): {before - len(main_df)}")

# Deduplicate immediately after raw load at hub × product_id × process_dt level.
_raw_dedup_keys = [c for c in ["hub_name", "product_id", "process_dt"] if c in main_df.columns]
if len(_raw_dedup_keys) == 3:
    main_df["process_dt"] = pd.to_datetime(main_df["process_dt"], errors="coerce")
    _before_raw_dedup = len(main_df)
    main_df = main_df.drop_duplicates(subset=_raw_dedup_keys, keep="first").reset_index(drop=True)
    _removed_raw_dupes = _before_raw_dedup - len(main_df)
    print(f"Rows dropped (raw duplicates hub×product_id×process_dt): {_removed_raw_dupes}")
else:
    print(f"[WARN] Raw dedup skipped — missing keys: {[k for k in ['hub_name', 'product_id', 'process_dt'] if k not in main_df.columns]}")

# %%
# =============================================================================
# MAP Sub-category FROM P MASTER (source of truth)
# Sub-category and sku class prod come from here, so map BEFORE filtering blanks
# =============================================================================
_P_MASTER_PATH = FF_MASTERS_XLSX
_p_master_raw, _ph_master_raw = load_product_masters_sheets_engine(_P_MASTER_PATH)
print(f"Product_Masters.xlsx columns: {_p_master_raw.columns.tolist()}")

# Detect column names flexibly
_id_col  = next((c for c in _p_master_raw.columns if c.strip().lower() == "product id"), None)
_cat_col = next((c for c in _p_master_raw.columns if "sub" in c.lower() and "cat" in c.lower()), None)
_sku_col = next((c for c in _p_master_raw.columns if "sku" in c.lower()), None)

print(f"Detected — id: '{_id_col}' | sub-category: '{_cat_col}' | sku: '{_sku_col}'")

_p_master = _p_master_raw[[c for c in [_id_col, _cat_col, _sku_col] if c]].copy()
_p_master = _p_master.rename(columns={_id_col: "product_id", _cat_col: "_pmaster_subcat", _sku_col: "_pmaster_sku"})
_p_master = _p_master.dropna(subset=["product_id"]).drop_duplicates(subset=["product_id"])

main_df = main_df.merge(_p_master, on="product_id", how="left")
_mapped = main_df["_pmaster_subcat"].notna().sum()
_not_mapped = main_df["_pmaster_subcat"].isna().sum()

# Override Sub-category and sku class prod with P Master values
main_df["Sub-category"] = main_df["_pmaster_subcat"].fillna(main_df.get("Sub-category", pd.NA))
main_df["sku class prod"] = main_df["_pmaster_sku"].fillna(main_df.get("sku class prod", pd.NA))
main_df.drop(columns=["_pmaster_subcat", "_pmaster_sku"], inplace=True)
print(f"Sub-category mapped from P Master: {_mapped} rows | Not found in P Master: {_not_mapped} rows")

# %%
# Now filter blank Sub-category and sku class prod (after P Master mapping)
before2 = len(main_df)
main_df = main_df[main_df["Sub-category"].notna() & (main_df["Sub-category"].astype(str).str.strip() != "")]
main_df = main_df[main_df["sku class prod"].notna() & (main_df["sku class prod"].astype(str).str.strip() != "")]
print(f"Rows dropped (blank Sub-category / sku class prod after mapping): {before2 - len(main_df)}")

# Reset index after all filtering — prevents NaN/index-mismatch errors in all
# subsequent merge, transform, and loc operations throughout this script
main_df = main_df.reset_index(drop=True)

print(f"main_df columns: {main_df.columns.tolist()}")

# Derive 'week' from process_dt if not already present
if "week" not in main_df.columns:
    main_df["process_dt"] = pd.to_datetime(main_df["process_dt"], errors="coerce")
    main_df["week"] = main_df["process_dt"].dt.isocalendar().week.astype(int)
    print("'week' column derived from process_dt")

if "day" not in main_df.columns:
    main_df["process_dt"] = pd.to_datetime(main_df["process_dt"], errors="coerce")
    main_df["day"] = main_df["process_dt"].dt.strftime("%a")
    print("'day' column derived from process_dt")

# %%
# Derive simple_flag / simple_instances columns if missing (bulk-pulled parquet files
# contain raw RDS columns: flag, instances, group_flag, group_instances, r7_inv)
_REQUIRED_FLAGS = [
    "simple_flag_when_SP_0", "simple_instances_when_SP_0",
    "simple_grp_flag_when_SP_0", "simple_grp_instances_when_SP_0"
]

if "simple_flag_when_SP_0" not in main_df.columns:
    if all(c in main_df.columns for c in ["flag", "instances", "group_flag", "group_instances", "r7_inv"]):
        # Derive from raw RDS columns
        main_df["plan_sum"] = main_df.groupby(
            ["hub_name", "process_dt", "product_id"]
        )["r7_inv"].transform("sum")
        main_df["simple_flag_when_SP_0"]          = np.where(main_df["plan_sum"] == 0, main_df["group_flag"],      main_df["flag"])
        main_df["simple_instances_when_SP_0"]     = np.where(main_df["plan_sum"] == 0, main_df["group_instances"], main_df["instances"])
        main_df["simple_grp_flag_when_SP_0"]      = main_df["group_flag"]
        main_df["simple_grp_instances_when_SP_0"] = main_df["group_instances"]
        main_df.drop(columns=["plan_sum"], inplace=True)
        print("Derived simple_flag / simple_instances from raw RDS columns")
    elif all(c in main_df.columns for c in ["simple_flag_when_SP_0",
                                             "simple_instances_when_SP_0",
                                             "simple_group_flag_when_SP_0",
                                             "simple_group_instances_when_SP_0"]):
        pass  # already present with group naming — rename block below handles it
    else:
        # Parquet files are missing these columns entirely — print available columns and zero-fill
        print(f"WARNING: simple_flag columns not found. Available columns: {main_df.columns.tolist()}")
        print("Zero-filling simple_flag / simple_instances columns. Re-pull raw data for accurate values.")
        for _col in _REQUIRED_FLAGS:
            if _col not in main_df.columns:
                main_df[_col] = 0

# Rename columns from parquet/P-Master naming -> Baseline script naming convention
# Product baseline uses raw sales; Auto-Pilot may supply liquidation-adjusted final_sales.
if "final_sales" in main_df.columns:
    main_df["sales"] = main_df["final_sales"]
    print("[INFO] Using final_sales (liquidation-adjusted) as Sales (qty) for baseline calculation.")
elif "sales" in main_df.columns:
    print("[INFO] Using sales column as Sales (qty) (Product-style raw actuals).")
else:
    main_df["sales"] = 0
    print("[WARN] No sales/final_sales column — defaulting Sales (qty) to 0.")

_col_renames = {
    "sales":                              "Sales (qty)",
    "Sub-category":                       "sub category",
    "sku class prod":                     "SKU Class Prod",
    "week":                               "Week",
    "simple_group_flag_when_SP_0":        "simple_grp_flag_when_SP_0",
    "simple_group_instances_when_SP_0":   "simple_grp_instances_when_SP_0",
}
main_df.rename(columns={k: v for k, v in _col_renames.items() if k in main_df.columns}, inplace=True)
print(f"Columns after rename: {main_df.columns.tolist()}")

weeks_available = sorted(main_df["Week"].unique().tolist())
print(f"Files loaded: {all_week_files}")
print(f"Weeks available: {weeks_available} | Total rows: {len(main_df)}")


# %%
sheets_manager = GoogleSheetsManager()
spreadsheet = sheets_manager.gc.open_by_url(CLUSTER_MASTER_SHEET_URL)

# Select the specific sheet/tab by its name
worksheet = spreadsheet.worksheet("Cluster phase 2")

# Get all values from
data = worksheet.get("A:H")


# %%
cluster_mapping_df = pd.DataFrame(data[1:], columns=data[0])

# %%
cluster_mapping_df["Cluster_Flag"] = cluster_mapping_df["Cluster_Flag"].astype(int)
cluster_mapping_df = cluster_mapping_df[cluster_mapping_df["Cluster_Flag"] == 1]



# %%
agg_cols = [
    "Sales (qty)",
    "simple_flag_when_SP_0", "simple_instances_when_SP_0",
    "simple_grp_flag_when_SP_0", "simple_grp_instances_when_SP_0"
]

# %%
df = main_df.merge(
    cluster_mapping_df[["product_id", "Mother_hubid", "MotherHub_name", "childHub_name"]],
    left_on=["product_id", "hub_name"],
    right_on=["product_id", "childHub_name"],
    how="left"
)

# %%
child_rows = df[~df["MotherHub_name"].isna()].copy()

# %%
cols_to_multiply = [
    "simple_flag_when_SP_0",
    "simple_instances_when_SP_0",
    "simple_grp_flag_when_SP_0",
    "simple_grp_instances_when_SP_0"
]

for col in cols_to_multiply:
    valid_mask = child_rows[col].notna() & child_rows["Sales (qty)"].notna()

    # Case 1: Sales > 0 -> multiply by Sales
    mask_sales_pos = valid_mask & (child_rows["Sales (qty)"] > 0)
    child_rows.loc[mask_sales_pos, col] = (
        child_rows.loc[mask_sales_pos, col] * child_rows.loc[mask_sales_pos, "Sales (qty)"]
    )

    # Case 2: Sales == 0 -> multiply by 1 only for specific columns
    if col in ["simple_grp_instances_when_SP_0", "simple_instances_when_SP_0"]:
        mask_sales_zero = valid_mask & (child_rows["Sales (qty)"] == 0)
        child_rows.loc[mask_sales_zero, col] = (
            child_rows.loc[mask_sales_zero, col] * 1
        )


# %%
mother_agg = (
    child_rows.groupby(
        ["process_dt", "product_id", "MotherHub_name"],
        as_index=False
    )[agg_cols].sum()
)

# %%
mother_agg_subset = mother_agg.rename(columns={
    "MotherHub_name": "hub_name",
    "Mother_hubid": "hub_id"
})[["process_dt", "hub_name", "product_id"] + agg_cols].copy()

# %%
mother_agg_subset = mother_agg_subset.rename(columns={
    "Sales (qty)": "Agg_sale_mother_hub",
    "simple_flag_when_SP_0": "Agg_simple_flag",
    "simple_instances_when_SP_0": "Agg_simple_instances",
    "simple_grp_flag_when_SP_0": "Agg_simple_grp_flag",
    "simple_grp_instances_when_SP_0": "Agg_simple_grp_instances"
})

# %%
key_cols = ["process_dt", "hub_name", "product_id"]

# Create an indicator to mark rows that exist in child_rows
main_df["is_child"] = main_df[key_cols].merge(
    child_rows[key_cols].drop_duplicates(),
    on=key_cols,
    how="left",
    indicator=True
)["_merge"].eq("both").fillna(False).values

# Now set 0 only for those true child rows
main_df.loc[main_df["is_child"], agg_cols] = 0




# %%
# (Optional) Drop the helper column after use
main_df.drop(columns=["is_child"], inplace=True)

# %%
final_df = main_df.merge(
    mother_agg_subset,
    on=["process_dt", "hub_name", "product_id"],
    how="left"
)

# %%
mask = final_df["Agg_sale_mother_hub"].notna()

cols_to_multiply = [
    "simple_flag_when_SP_0",
    "simple_instances_when_SP_0",
    "simple_grp_flag_when_SP_0",
    "simple_grp_instances_when_SP_0"
]

for col in cols_to_multiply:
    valid_mask = mask & final_df[col].notna() & final_df["Sales (qty)"].notna()

    # Case 1: Sales > 0 -> multiply by actual sales
    mask_sales_pos = valid_mask & (final_df["Sales (qty)"] > 0)
    final_df.loc[mask_sales_pos, col] = (
        final_df.loc[mask_sales_pos, col] * final_df.loc[mask_sales_pos, "Sales (qty)"]
    )

    # Case 2: Sales == 0 -> multiply by 1 for simple_flag and simple_instances only
    if col in ["simple_grp_instances_when_SP_0", "simple_instances_when_SP_0"]:
        mask_sales_zero = valid_mask & (final_df["Sales (qty)"] == 0)
        final_df.loc[mask_sales_zero, col] = (
            final_df.loc[mask_sales_zero, col] * 1
        )


# %%
for col in ["Agg_sale_mother_hub", "Agg_simple_flag", "Agg_simple_instances",
            "Agg_simple_grp_flag", "Agg_simple_grp_instances"]:
    final_df[col] = final_df[col].fillna(0)


# %%
final_df["Sales (qty)"] += final_df["Agg_sale_mother_hub"]
final_df["simple_flag_when_SP_0"] += final_df["Agg_simple_flag"]
final_df["simple_instances_when_SP_0"] += final_df["Agg_simple_instances"]
final_df["simple_grp_flag_when_SP_0"] += final_df["Agg_simple_grp_flag"]
final_df["simple_grp_instances_when_SP_0"] += final_df["Agg_simple_grp_instances"]

# # Drop helper columns
# final_df = final_df.drop(columns=[
#     "Agg_sale_mother_hub", "Agg_simple_flag", "Agg_simple_instances",
#     "Agg_simple_grp_flag", "Agg_simple_grp_instances",
#     "Unnamed: 19", "Unnamed: 20"
# ], errors="ignore")

# %%
# Drop helper columns
final_df = final_df.drop(columns=[
    "Agg_sale_mother_hub", "Agg_simple_flag", "Agg_simple_instances",
    "Agg_simple_grp_flag", "Agg_simple_grp_instances",
    "Unnamed: 19", "Unnamed: 20"
], errors="ignore")

# reuse existing client (no need to re-authorize)
spreadsheet = sheets_manager.gc.open_by_url(HUB_LEVEL_PLANNING_SHEET_URL)

# Select the specific sheet/tab by its name
worksheet = spreadsheet.worksheet("Avl_Flag")

# Get all values from
data = worksheet.get("A:F")


# %%
avl_flag_df = pd.DataFrame(data[1:], columns=data[0])

# %%
merged_df = final_df.merge(
    avl_flag_df[['product_id', 'Avl Flag']],
    how='left',
    on='product_id'
)

#%%
# merged_df.to_clipboard()  # disabled for speed

# %%
merged_df['Avl Flag'] = merged_df['Avl Flag'].astype(int)

# %%
_avl1 = merged_df['Avl Flag'] == 1
merged_df['simple_avail_num'] = np.where(_avl1, merged_df['simple_flag_when_SP_0'],     merged_df['simple_grp_flag_when_SP_0'])
merged_df['simple_avail_den'] = np.where(_avl1, merged_df['simple_instances_when_SP_0'], merged_df['simple_grp_instances_when_SP_0'])


# %%
merged_df['simple_avail_num'] = merged_df['simple_avail_num'].fillna(0)

# %%
merged_df['simple_avail_den'] = merged_df['simple_avail_den'].fillna(0)

# %%
merged_df['simple_availability'] = (
    merged_df['simple_avail_num']
    .div(merged_df['simple_avail_den'].replace(0, np.nan))
    .fillna(0)
    * 100
)


# %%
merged_df['simple_availability'] = merged_df['simple_availability'].fillna(0)

# %%
# merged_df.to_csv("Hub_level_plan.csv", index=False)  # disabled for speed


# %%
# =============================================================================
# HUB CHANGES PROCESSING (NEW HUB LAUNCH & KML REMAPPING)
# =============================================================================
"""
This section processes hub changes from a single consolidated sheet "Hub_Changes".
It handles two types of operations:

1. NEW HUB LAUNCH:
   - Creates virtual history by replicating line items from source hub(s)
   - If multiple sources: Uses first source hub's line items, adds volumes from others
   - Transfers volume TO new hub (creates new records)
   - REDUCES volume FROM source hub(s) by the percentage

2. KML REMAPPING:
   - NO virtual history creation
   - ONLY modifies volumes in existing records
   - Adds volume to target hub
   - Reduces volume from source hub

Date Logic:
- If Start_date == End_date: Modifies all sales BEFORE End_date
- If Start_date != End_date: Modifies sales BETWEEN Start_date and End_date
"""

# -----------------------------------------------------------------------------
# Load Hub Changes Data (pipeline params Hub_Changes tab; legacy FF Input fallback)
# -----------------------------------------------------------------------------
required_cols = ['city_name','Type', 'Hub_name', 'Source_Hub', 'Hub_id', 'Percentage', 'Start_date', 'End_date']
_apply_hub = os.getenv("BASELINE_APPLY_HUB_CHANGES", "1").strip().lower() not in ("0", "false", "no", "n")

if _apply_hub:
    from planning_suite.services.hub_launch_sync import load_hub_changes_for_baseline
    hub_changes_df = load_hub_changes_for_baseline(sheets_manager)
    print(f"Hub changes source: pipeline params ({PIPELINE_PARAMS_HUB_CHANGES_TAB})")
else:
    hub_changes_df = pd.DataFrame(columns=required_cols)
    print("Hub changes skipped (BASELINE_APPLY_HUB_CHANGES=0)")

# Display the data
print("Hub Changes Data:")
print(hub_changes_df)
# hub_changes_df.to_clipboard()  # disabled for speed



# %%
missing_cols = [col for col in required_cols if col not in hub_changes_df.columns]


if missing_cols:
    raise ValueError(f"Missing required columns in Hub_Changes sheet: {missing_cols}")

# Convert all numeric-looking columns in merged_df
num_cols = ["Sales (qty)", "simple_avail_num", "simple_avail_den"]

for col in num_cols:
    if col in merged_df.columns:
        merged_df[col] = pd.to_numeric(merged_df[col], errors="coerce")

# Convert date columns in hub_changes_df
hub_changes_df['Start_date'] = pd.to_datetime(hub_changes_df['Start_date'], errors='coerce')
hub_changes_df['End_date'] = pd.to_datetime(hub_changes_df['End_date'], errors='coerce')

# Convert percentage to numeric (already in decimal format: 0.36 not 36%)
# Do NOT divide by 100 since input is already decimal
hub_changes_df['Percentage'] = pd.to_numeric(hub_changes_df['Percentage'], errors='coerce')

# Validate that Type column has valid values
valid_types = ['New Hub', 'KML Remapping']
invalid_types = hub_changes_df[~hub_changes_df['Type'].isin(valid_types)]['Type'].unique()
if len(invalid_types) > 0:
    print(f"Warning: Invalid Type values found: {invalid_types}. Valid values are: {valid_types}")
    hub_changes_df = hub_changes_df[hub_changes_df['Type'].isin(valid_types)]

print(f"\nData types converted successfully")
print(f"Date range in data: {merged_df['process_dt'].min()} to {merged_df['process_dt'].max()}")

# %%
# -----------------------------------------------------------------------------
# Separate by Type
# -----------------------------------------------------------------------------
new_hub_changes = hub_changes_df[hub_changes_df['Type'] == 'New Hub'].copy()
kml_remapping_changes = hub_changes_df[hub_changes_df['Type'] == 'KML Remapping'].copy()

print(f"New Hub records: {len(new_hub_changes)}")
print(f"KML Remapping records: {len(kml_remapping_changes)}")

# %%
# =============================================================================
# PROCESS NEW HUB LAUNCHES
# =============================================================================

virtual_history_list = []

# -----------------------------------------------------------------------------
# VALIDATION: Check New Hubs and handle existing data
# -----------------------------------------------------------------------------
new_hub_names = new_hub_changes['Hub_name'].unique()

print("Validating New Hubs:")
for hub in new_hub_names:
    existing_records = merged_df[merged_df['hub_name'] == hub]
    
    if len(existing_records) > 0:
        # Get the End_date for this hub (launch date)
        hub_info = new_hub_changes[new_hub_changes['Hub_name'] == hub].iloc[0]
        launch_date = hub_info['End_date']
        
        # Check if hub has data BEFORE launch date (conflict with virtual history)
        pre_launch_records = existing_records[existing_records['process_dt'] < launch_date]
        post_launch_records = existing_records[existing_records['process_dt'] >= launch_date]
        
        if len(pre_launch_records) > 0:
            pre_launch_volume = pre_launch_records['Sales (qty)'].sum()
            
            # Ignore pre-launch data - remove it from merged_df
            print(f"  ⚠️ {hub} has {len(pre_launch_records):,} records BEFORE launch date {launch_date.date()}")
            print(f"     Pre-launch volume: {pre_launch_volume:.2f}")
            print(f"     ➜ Ignoring pre-launch data (will be replaced with virtual history)")
            
            # Remove pre-launch records for this hub from merged_df
            merged_df = merged_df[~((merged_df['hub_name'] == hub) & (merged_df['process_dt'] < launch_date))]
            
            if len(post_launch_records) > 0:
                print(f"  [OK] {hub} has {len(post_launch_records):,} real records after launch date {launch_date.date()}")
            print(f"    Will create virtual history for dates < {launch_date.date()}")
        else:
            # Hub has data AFTER launch date - this is OK (real post-launch data)
            print(f"  [OK] {hub} has {len(post_launch_records):,} real records after launch date {launch_date.date()}")
            print(f"    Will create virtual history for dates < {launch_date.date()}")
    else:
        print(f"  [OK] {hub} is truly new (no existing data)")

print()

# -----------------------------------------------------------------------------
# Create Virtual History for New Hubs
# -----------------------------------------------------------------------------
# Group by target hub (Hub_name) to handle multiple source hubs
for target_hub, group in new_hub_changes.groupby('Hub_name'):
    print(f"\nProcessing New Hub: {target_hub}")
    
    # Sort by order of appearance to ensure first source hub is processed first
    group = group.reset_index(drop=True)
    
    for idx, row in group.iterrows():
        source_hub = row['Source_Hub']
        percentage = row['Percentage']
        start_date = row['Start_date']
        end_date = row['End_date']
        
        print(f"  Source: {source_hub}, Transfer: {percentage*100:.1f}% (decimal: {percentage})")
        
        # ---------------------------------------------------------------------
        # Determine date filter based on start_date and end_date
        # ---------------------------------------------------------------------
        if pd.notna(start_date) and pd.notna(end_date):
            if start_date == end_date:
                # Modify all sales BEFORE end_date
                date_mask = merged_df['process_dt'] < end_date
            else:
                # Modify sales BETWEEN start_date and end_date (inclusive)
                date_mask = (merged_df['process_dt'] >= start_date) & (merged_df['process_dt'] <= end_date)
        else:
            # If dates are missing, process all historical data
            date_mask = merged_df['process_dt'].notna()
        
        # Filter source hub data with date condition
        source_data = merged_df[
            (merged_df['hub_name'] == source_hub) & date_mask
        ].copy()
        
        if source_data.empty:
            print(f"    ⚠️  Warning: No data found for source hub {source_hub}")
            continue
        
        # Show source hub details
        source_volume_before = source_data['Sales (qty)'].sum()
        source_records = len(source_data)
        print(f"    Source data: {source_records:,} records, Volume: {source_volume_before:.2f}")
        
        # ---------------------------------------------------------------------
        # Create Virtual History
        # ---------------------------------------------------------------------
        if idx == 0:
            # FIRST source hub: Replicate ALL line items
            virtual_history_hub = source_data.copy()
            
            # Scale volumes by percentage
            volume_before_scaling = virtual_history_hub['Sales (qty)'].sum()
            scale_cols = ["Sales (qty)"]
            for col in scale_cols:
                if col in virtual_history_hub.columns:
                    virtual_history_hub[col] = virtual_history_hub[col] * percentage
            
            volume_after_scaling = virtual_history_hub['Sales (qty)'].sum()
            
            # Update hub_name to target hub
            virtual_history_hub['hub_name'] = target_hub
            
            virtual_history_list.append(virtual_history_hub)
            print(f"    [OK] Created {len(virtual_history_hub):,} virtual history records for {target_hub}")
            print(f"      Volume calculation: {volume_before_scaling:.2f} × {percentage} = {volume_after_scaling:.2f}")
            print(f"    [OK] Volume transferred to {target_hub}: {volume_after_scaling:.2f}")
            
        else:
            # SUBSEQUENT source hubs: Only add volumes for MATCHING products
            # Find products that already exist in virtual history for this target hub
            existing_virtual = pd.concat(virtual_history_list) if virtual_history_list else pd.DataFrame()
            
            if not existing_virtual.empty:
                matching_products = existing_virtual[
                    existing_virtual['hub_name'] == target_hub
                ]['product_id'].unique()
                
                # Filter for matching products only
                matching_source_data = source_data[
                    source_data['product_id'].isin(matching_products)
                ].copy()
                
                if not matching_source_data.empty:
                    volume_before_scaling = matching_source_data['Sales (qty)'].sum()
                    
                    # Scale volumes
                    for col in ["Sales (qty)"]:
                        if col in matching_source_data.columns:
                            matching_source_data[col] = matching_source_data[col] * percentage
                    
                    volume_after_scaling = matching_source_data['Sales (qty)'].sum()
                    
                    # Update hub_name
                    matching_source_data['hub_name'] = target_hub
                    
                    virtual_history_list.append(matching_source_data)
                    print(f"    [OK] Added volumes for {len(matching_source_data):,} matching product records")
                    print(f"      Volume calculation: {volume_before_scaling:.2f} × {percentage} = {volume_after_scaling:.2f}")
                    print(f"    [OK] Volume transferred to {target_hub}: {volume_after_scaling:.2f}")
                else:
                    print(f"    ℹ️  No matching products found between {source_hub} and {target_hub}")
        
        # ---------------------------------------------------------------------
        # Reduce Source Hub Volumes
        # ---------------------------------------------------------------------
        source_mask = (merged_df['hub_name'] == source_hub) & date_mask
        
        # Get volume before reduction
        volume_before_reduction = merged_df.loc[source_mask, 'Sales (qty)'].sum()
        
        for col in ["Sales (qty)"]:
            if col in merged_df.columns:
                merged_df.loc[source_mask, col] = merged_df.loc[source_mask, col] * (1 - percentage)
        
        # Get volume after reduction
        volume_after_reduction = merged_df.loc[source_mask, 'Sales (qty)'].sum()
        volume_reduced = volume_before_reduction - volume_after_reduction
        
        print(f"    [OK] Reduced source hub {source_hub} by {percentage*100:.1f}%")
        print(f"      Volume calculation: {volume_before_reduction:.2f} × (1 - {percentage}) = {volume_after_reduction:.2f}")
        print(f"      Volume reduced: {volume_reduced:.2f}")

# %%
# -----------------------------------------------------------------------------
# Aggregate Virtual History (if multiple sources contributed to same records)
# -----------------------------------------------------------------------------
if virtual_history_list:
    virtual_history = pd.concat(virtual_history_list, ignore_index=True)
    
    # Group and aggregate to combine volumes from multiple sources
    # Use only columns that actually exist in virtual_history
    _candidate_group_cols = [
        "process_dt", "Sub-category", "week", "day", "product_id", "product_name",
        "sku class prod", "city_name", "hub_name",
        "simple_flag_when_SP_0", "simple_instances_when_SP_0",
        "simple_grp_flag_when_SP_0", "simple_grp_instances_when_SP_0",
        "Avl Flag", "simple_avail_num", "simple_avail_den", "simple_availability"
    ]
    group_cols = [c for c in _candidate_group_cols if c in virtual_history.columns]
    
    agg_dict = {"Sales (qty)": "sum"}
    if "simple_avail_num" in virtual_history.columns:
        agg_dict["simple_avail_num"] = "sum"
    if "simple_avail_den" in virtual_history.columns:
        agg_dict["simple_avail_den"] = "sum"
    
    virtual_history = virtual_history.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # Recalculate availability
    if "simple_avail_num" in virtual_history.columns and "simple_avail_den" in virtual_history.columns:
        virtual_history["simple_availability"] = (
            virtual_history["simple_avail_num"]
            .div(virtual_history["simple_avail_den"].replace(0, np.nan))
            .fillna(0)
        )
    
    # Align columns with merged_df
    virtual_history_aligned = virtual_history.reindex(columns=merged_df.columns)
    
    print(f"\nTotal virtual history records created: {len(virtual_history_aligned)}")
else:
    virtual_history_aligned = pd.DataFrame(columns=merged_df.columns)
    print("\nNo virtual history created")

# %%
# =============================================================================
# PROCESS KML REMAPPING
# =============================================================================

for idx, row in kml_remapping_changes.iterrows():
    target_hub = row['Hub_name']
    source_hub = row['Source_Hub']
    percentage = row['Percentage']
    start_date = row['Start_date']
    end_date = row['End_date']
    
    print(f"\nProcessing KML Remapping: {source_hub} -> {target_hub} ({percentage*100:.1f}%, decimal: {percentage})")
    
    # Determine date filter
    if pd.notna(start_date) and pd.notna(end_date):
        if start_date == end_date:
            # Modify all sales BEFORE end_date
            date_mask = merged_df['process_dt'] < end_date
        else:
            # Modify sales BETWEEN start_date and end_date
            date_mask = (merged_df['process_dt'] >= start_date) & (merged_df['process_dt'] <= end_date)
    else:
        date_mask = merged_df['process_dt'].notna()
    
    # ---------------------------------------------------------------------
    # Transfer volumes (VECTORIZED - much faster!)
    # ---------------------------------------------------------------------
    # Step 1: Extract source hub data
    source_mask = (merged_df['hub_name'] == source_hub) & date_mask
    source_data = merged_df[source_mask].copy()
    
    if source_data.empty:
        print(f"  ⚠️  No source data found for {source_hub}")
        continue
    
    # Step 2: Calculate transfer amounts
    source_data['transfer_amount'] = source_data['Sales (qty)'] * percentage
    total_source_volume = source_data['Sales (qty)'].sum()
    total_transfer_amount = source_data['transfer_amount'].sum()
    
    # Step 3: Reduce source hub volumes (VECTORIZED)
    merged_df.loc[source_mask, 'Sales (qty)'] = merged_df.loc[source_mask, 'Sales (qty)'] * (1 - percentage)
    
    # Step 4: Find matching records in target hub
    target_mask = (merged_df['hub_name'] == target_hub) & date_mask
    target_data = merged_df[target_mask].copy()
    
    if not target_data.empty:
        # Create merge key for matching
        merge_key = ['process_dt', 'product_id']
        
        # Get target data with index for direct updates
        target_indexed = merged_df[target_mask].reset_index()
        
        # Merge to find matching records and their indices
        transfer_map = source_data[merge_key + ['transfer_amount']].merge(
            target_indexed[merge_key + ['index']],
            on=merge_key,
            how='inner'
        )
        
        if not transfer_map.empty:
            # Step 5: Add volumes to target hub (FULLY VECTORIZED - no loops!)
            # Use the original dataframe indices to update in bulk
            indices_to_update = transfer_map['index'].values
            amounts_to_add = transfer_map['transfer_amount'].values
            
            merged_df.loc[indices_to_update, 'Sales (qty)'] += amounts_to_add
            
            total_transferred = transfer_map['transfer_amount'].sum()
            records_transferred = len(transfer_map)
            total_lost = total_transfer_amount - total_transferred
            records_lost = len(source_data) - records_transferred
            
            print(f"  [OK] Completed KML remapping for {len(source_data):,} source records")
            print(f"    Volume transferred: {total_transferred:.2f} ({records_transferred:,} records)")
            if records_lost > 0:
                print(f"    ⚠️  Volume lost (no target record): {total_lost:.2f} ({records_lost:,} records)")
        else:
            print(f"  ⚠️  No matching records found in target hub {target_hub}")
            print(f"    Volume lost: {total_transfer_amount:.2f} ({len(source_data):,} records)")
    else:
        print(f"  ⚠️  Target hub {target_hub} has no data in the specified date range")
        print(f"    Volume lost: {total_transfer_amount:.2f} ({len(source_data):,} records)")

# %%
# -----------------------------------------------------------------------------
# Combine Original Data with Virtual History
# -----------------------------------------------------------------------------
final_df = pd.concat([merged_df, virtual_history_aligned], ignore_index=True)

# %%
# -----------------------------------------------------------------------------
# Summary Statistics
# -----------------------------------------------------------------------------

print("HUB CHANGES PROCESSING COMPLETE")
print("="*80)
print(f"Final DataFrame shape: {final_df.shape}")
print(f"Original data: {len(merged_df):,} records")
print(f"Virtual history added: {len(virtual_history_aligned):,} records")
print(f"Total records: {len(final_df):,}")

if len(new_hub_changes) > 0:
    print(f"\nNew Hub Launches processed: {new_hub_changes['Hub_name'].nunique()}")
    for hub in new_hub_changes['Hub_name'].unique():
        sources = new_hub_changes[new_hub_changes['Hub_name'] == hub]['Source_Hub'].tolist()
        print(f"  - {hub}: from {', '.join(sources)}")
        
        # Show volume for this hub in final_df
        hub_volume = final_df[final_df['hub_name'] == hub]['Sales (qty)'].sum()
        hub_records = len(final_df[final_df['hub_name'] == hub])
        print(f"    -> Total volume in final_df: {hub_volume:.2f} ({hub_records:,} records)")

if len(kml_remapping_changes) > 0:
    print(f"\nKML Remappings processed: {len(kml_remapping_changes)}")
    for _, row in kml_remapping_changes.iterrows():
        target_hub = row['Hub_name']
        source_hub = row['Source_Hub']
        
        # Show volume for this hub in final_df
        target_volume = final_df[final_df['hub_name'] == target_hub]['Sales (qty)'].sum()
        source_volume = final_df[final_df['hub_name'] == source_hub]['Sales (qty)'].sum()
        
        print(f"  - {source_hub} -> {target_hub} ({row['Percentage']*100:.1f}%)")
        print(f"    -> {target_hub} final volume: {target_volume:.2f}")
        print(f"    -> {source_hub} final volume: {source_volume:.2f}")

# -----------------------------------------------------------------------------
# Data Quality Check
# -----------------------------------------------------------------------------
print("\n" + "-"*80)
print("DATA QUALITY CHECKS")
print("-"*80)

# Check for duplicates
duplicates = final_df[final_df.duplicated(subset=['hub_name', 'product_id', 'process_dt'], keep=False)]
if len(duplicates) > 0:
    print(f"⚠️  WARNING: Found {len(duplicates)} duplicate hub-product-date records!")
    print("\nSample duplicates:")
    print(duplicates[['hub_name', 'product_id', 'process_dt', 'Sales (qty)']].head(10))
else:
    print("[OK] No duplicate hub-product-date combinations found")

# Check if new hubs have data from original merged_df (they shouldn't!)
if len(new_hub_changes) > 0:
    for hub in new_hub_changes['Hub_name'].unique():
        # Check if this hub appears in merged_df (it shouldn't after removal)
        hub_in_merged = merged_df[merged_df['hub_name'] == hub]
        if len(hub_in_merged) > 0:
            print(f"⚠️  WARNING: New Hub {hub} still has {len(hub_in_merged)} records in merged_df!")
            print(f"   This should be 0. Volume: {hub_in_merged['Sales (qty)'].sum():.2f}")

print("\n" + "="*80)

# %%
# =============================================================================
# DIAGNOSTIC: Check Specific Hub (GHA)
# =============================================================================
# Run this cell to debug a specific hu





# Uncomment to check other hubs:
# check_hub_details('BEG', final_df)
# check_hub_details('NDM', final_df)

#%%
# =============================================================================
# DP LOGICS — Read from local Excel files (synced from Google Sheet via Streamlit)
# =============================================================================
# DP_LOGICS_FOLDER is imported from config

outlier_df = read_dp_logics_table_engine(DP_LOGICS_FOLDER, "City_Cat")

# %%
outlier_df['process_dt'] = pd.to_datetime(outlier_df['process_dt'], format='%m/%d/%Y')

# %%
final_df['process_dt'] = pd.to_datetime(final_df['process_dt'], format='%m/%d/%Y')

# %%
final_df = final_df.merge(
   outlier_df[['city_name', 'sub category','process_dt', 'Outlier_Flag']],
    on=['city_name', 'sub category','process_dt'],
    how='left'
)

# %%
# Note: Old "Hub_date_change" worksheet logic has been removed.
# All hub changes are now handled through the "Hub_Changes" sheet above.
# This includes both New Hub launches and KML Remapping.


# %%
final_df['Outlier_Flag'] = pd.to_numeric(final_df['Outlier_Flag'], errors='coerce').fillna(0).astype(int)

# %%
final_df.head()

# %%
final_df.loc[final_df['Outlier_Flag'] == 1, ['Sales (qty)', 'simple_avail_num']] = 0



# %%
final_df.head()

# %%
availability_agg = final_df.groupby(
    ['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'process_dt','Week']
).agg(
    simple_avail_num_sum=('simple_avail_num', 'sum'),
    simple_avail_den_sum=('simple_avail_den', 'sum'),
    sales_qty_sum=('Sales (qty)', 'sum')  
).reset_index()

# %%
availability_agg['simple_availability'] = (
    availability_agg['simple_avail_num_sum']
    .div(availability_agg['simple_avail_den_sum'].replace(0, np.nan))
    .fillna(0)
)


# %%
availability_agg.head()

# %%
# availability_agg.to_clipboard()  # disabled for speed

# %%
pivot_df = pd.pivot_table(
    availability_agg,
    index=['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day'],
    columns='Week',
    values=['simple_availability', 'sales_qty_sum'],
    aggfunc='sum', 
    fill_value=0
)


# %%
# pivot_df.to_clipboard()  # disabled for speed

# %%
if isinstance(pivot_df.columns, pd.MultiIndex):
    pivot_df.columns = ['_'.join(map(str, col)).strip() for col in pivot_df.columns.values]

# %%
availability_cols = [c for c in pivot_df.columns if c.startswith("simple_availability")]


# %%
print(availability_cols)

# %%
for c in availability_cols:
    week_num = c.split('_')[-1]
    out_col = f'out_of_stock_{week_num}'
    
    pivot_df[out_col] = np.floor(20 - (1 - pivot_df[c]) * 12).astype(int) 

# %%
pivot_df = pivot_df.reset_index()


# %%
pivot_df.columns

# %%
avl_flag_full = read_dp_logics_table_engine(DP_LOGICS_FOLDER, "Avl_Flag")
subcat_cat_df = avl_flag_subcat_cat_df(avl_flag_full)

# %%
pivot_df = pivot_df.merge(subcat_cat_df, how='left', on='sub category')


# %%
stf_df = read_dp_logics_table_engine(DP_LOGICS_FOLDER, "SellThroughFactor")

# %%
for col in ['salethroughfactor', 'salethroughfactor_lowvolume']:
    stf_df[col] = pd.to_numeric(stf_df[col], errors='coerce')



# %%
stf_df['hour'] = stf_df['hour'].astype(int)

# %%
# Get week numbers from pivot_df columns
week_cols = [col for col in pivot_df.columns if col.startswith('simple_availability_')]
weeks = [col.split('_')[-1] for col in week_cols]
week_df = pd.DataFrame({'week': weeks})
week_df['key'] = 1

# %%
pivot_df.columns

# %%
pivot_list = []

for factor_col in ['salethroughfactor', 'salethroughfactor_lowvolume']:
    stf_daily = stf_df.groupby(['city_name', 'Cat', 'day', 'hour'], as_index=False)[
    ['salethroughfactor', 'salethroughfactor_lowvolume']
].mean()
    stf_daily['key'] = 1
    stf_expanded = pd.merge(stf_daily, week_df, on='key').drop('key', axis=1)

    stf_pivot = stf_expanded.pivot(index=['city_name', 'Cat', 'day', 'hour'], columns='week', values=factor_col)
    stf_pivot.columns = [f'{factor_col}_{w}' for w in stf_pivot.columns]
    stf_pivot = stf_pivot.reset_index()

    pivot_list.append(stf_pivot)

# Merge both sets of columns side-by-side
stf_pivot_all = reduce(lambda left, right: pd.merge(left, right, on=['city_name', 'Cat', 'day', 'hour']), pivot_list)




# %%
for week in weeks:
    out_of_stock_col = f'out_of_stock_{week}'

    if out_of_stock_col not in pivot_df.columns:
        continue

    # For both factor types
    for factor_prefix in ['salethroughfactor', 'salethroughfactor_lowvolume']:
        stf_week_col = f'{factor_prefix}_{week}'

        if stf_week_col not in stf_pivot_all.columns:
            continue

        temp_df = pivot_df[['city_name', 'Cat', 'day', out_of_stock_col]].copy()
        temp_df = temp_df.rename(columns={out_of_stock_col: 'hour'})

        temp_merge = temp_df.merge(
            stf_pivot_all[['city_name', 'Cat', 'day', 'hour', stf_week_col]],
            on=['city_name', 'Cat', 'day', 'hour'],
            how='left'
        )

        pivot_df[stf_week_col] = temp_merge[stf_week_col]


# %%
print(weeks)

# %%
for week in weeks:
    sales_col = f"sales_qty_sum_{week}"
    stf_col = f"salethroughfactor_{week}"
    stf_low_col = f"salethroughfactor_lowvolume_{week}"
    stockouthour_col = f"out_of_stock_{week}"
    corrected_col = f"avl_corrected_sales_{week}"
    availability_col = f"simple_availability_{week}"

    if all(col in pivot_df.columns for col in [sales_col, stf_col, stf_low_col, stockouthour_col, availability_col]):
        
        # Choose factor based on sales threshold
        factor_used = np.where(
            pivot_df[sales_col] <= 5,
            pivot_df[stf_low_col],
            pivot_df[stf_col]
        )
        

        # Compute corrected sales (object dtype — may hold numeric values or 'L')
        corrected = (
            pivot_df[sales_col] / np.where(factor_used == 0, np.nan, factor_used)
        ).round(0)
        mask_L = (pivot_df[sales_col] == 0) & (pivot_df[availability_col] < 0.9)
        corrected = corrected.astype(object)
        corrected.loc[mask_L] = 'L'
        pivot_df[corrected_col] = corrected

# %%
# pivot_df.to_clipboard()  # disabled for speed

# %%
City_drops = read_dp_logics_table_engine(DP_LOGICS_FOLDER, "City_drops")

# %%
value_cols = [col for col in pivot_df.columns if col.startswith("avl_corrected_sales_")]
pivot_long = pivot_df.melt(
    id_vars=["city_name", "sub category", "hub_name","SKU Class Prod","day"], 
    value_vars=value_cols, 
    var_name="week_col", 
    value_name="avl_corrected_sales"
)

# %%
# Extract week number from column name
pivot_long["week"] = pivot_long["week_col"].str.extract(r"(\d+)$").astype(int)

# %%
print(weeks)

# %%
# Step 2: Melt availability corrected cols into long format
value_cols = [f"avl_corrected_sales_{w}" for w in weeks if f"avl_corrected_sales_{w}" in pivot_df.columns]


# %%
pivot_long["week"] = pivot_long["week_col"].str.split("_").str[-1]

# %%
City_drops = City_drops.rename(columns={"Day": "day"})
City_drops["week"] = City_drops["week"].astype(str)

# %%
merged = pivot_long.merge(
    City_drops[["city_name", "sub category","week", "day", "%Change"]],
    how="left",
    on=["city_name", "sub category","week", "day"]
)

# %%
merged["avl_corrected_sales_num"] = pd.to_numeric(merged["avl_corrected_sales"], errors="coerce")
merged["%Change"] = pd.to_numeric(merged["%Change"], errors="coerce")

# %%
merged["adjusted_avl_corrected_sales"] = np.where(
    merged["avl_corrected_sales_num"].notna() & merged["%Change"].notna(),
    (merged["avl_corrected_sales_num"] * (1 + merged["%Change"])),
    merged["avl_corrected_sales"]  # keep original if it's 'L' or NaN
)

# %%
pivot_wide = merged.pivot_table(
    index=["city_name", "hub_name", "SKU Class Prod", "day", "sub category"],
    columns="week",
    values=["%Change", "adjusted_avl_corrected_sales"],
    aggfunc="first"
).reset_index()

# %%
pivot_wide.columns = [
    f"{a}_{b}" if b not in ["", None] else a
    for a, b in pivot_wide.columns.to_flat_index()
]

# %%
pivot_final = pivot_df.merge(
    pivot_wide,
    how="left",
    on=["city_name", "hub_name", "SKU Class Prod", "day", "sub category"]
)

# %%


# %%
adj_cols = [col for col in pivot_final.columns if col.startswith("adjusted_avl_corrected_sales_")]

# %%

def reorder_week_columns(pivot_final):
    fixed_cols = []
    week_cols = {}

    for col in pivot_final.columns:
        match = re.search(r"_(\d+)$", col)
        if match:
            base = col[:match.start()]   # metric name
            week = int(match.group(1))
            week_cols.setdefault(base, []).append((week, col))
        else:
            fixed_cols.append(col)

    reordered_week_cols = []

    for base, weeks in week_cols.items():
        # 2025 weeks (48–53)
        weeks_2025 = [(w, c) for w, c in weeks if w >= 10]

        # 2026 weeks (single digit)
        weeks_2026 = [(w, c) for w, c in weeks if w < 10]

        reordered_week_cols.extend(
            [c for _, c in sorted(weeks_2025)] +
            [c for _, c in sorted(weeks_2026)]
        )

    return pivot_final[fixed_cols + reordered_week_cols]


# %%
pivot_final = reorder_week_columns(pivot_final)

# %%
print(pivot_final.columns)

# %%
# =============================================================================
# AVAILABILITY-BASED OUTLIER CORRECTION
# Rule: if simple_availability < 20% for a week -> that week's
#       avl_corrected_sales is unreliable -> replace with the mean of
#       avl_corrected_sales from OTHER weeks where availability >= 20%.
# If no valid reference weeks exist (all < 20%), keep the original value.
# Non-numeric values ('L') are always preserved as-is.
# =============================================================================

# Load AVAIL_THRESHOLD dynamically from Google Sheets parameters
if os.environ.get("BASELINE_AVAIL_THRESHOLD"):
    AVAIL_THRESHOLD = float(os.environ["BASELINE_AVAIL_THRESHOLD"])
    print(f"[INFO] AVAIL_THRESHOLD from env: {AVAIL_THRESHOLD}")
else:
    try:
        _params = sheets_manager.read_pipeline_params()
        _avail_thresh_val = _params.get("avail_threshold", 0.20)
        # Convert percentage (e.g. 20) to float ratio (0.20) if entered as whole number
        if _avail_thresh_val > 1.0:
            _avail_thresh_val = _avail_thresh_val / 100.0
        AVAIL_THRESHOLD = _avail_thresh_val
        print(f"[INFO] Loaded AVAIL_THRESHOLD from Google Sheets: {AVAIL_THRESHOLD}")
    except Exception as _e:
        AVAIL_THRESHOLD = 0.20   # 20% default
        print(f"[WARN] Failed to load AVAIL_THRESHOLD from Google Sheets, using default: {AVAIL_THRESHOLD} (Error: {_e})")

# Collect week numbers present in both adj_cols and availability cols
avail_week_map = {}   # week_suffix -> (adj_col, avail_col)
for col in adj_cols:
    week_suffix = col.split("_")[-1]
    avail_col   = f"simple_availability_{week_suffix}"
    if avail_col in pivot_final.columns:
        avail_week_map[week_suffix] = (col, avail_col)

# Build numeric matrices once (rows = hub-SKU-day, cols = weeks)
week_suffixes  = list(avail_week_map.keys())
adj_col_list   = [avail_week_map[w][0] for w in week_suffixes]
avail_col_list = [avail_week_map[w][1] for w in week_suffixes]

# avl_corrected sales — used for cross-week mean reference
sales_matrix = pivot_final[adj_col_list].apply(pd.to_numeric, errors='coerce')   # NaN for 'L'
avail_matrix = pivot_final[avail_col_list].apply(pd.to_numeric, errors='coerce')

# Raw actual sales (sales_qty_sum_) — used for the ×1.5 scaled floor
raw_sales_col_list = [f"sales_qty_sum_{w}" for w in week_suffixes]
available_raw_cols = [c for c in raw_sales_col_list if c in pivot_final.columns]
raw_sales_matrix   = pivot_final[available_raw_cols].apply(pd.to_numeric, errors='coerce')
raw_sales_matrix.columns = [c.split("_")[-1] for c in available_raw_cols]  # align to week_suffixes

# Rename matrices to share the same week-suffix column names for easy masking
sales_matrix.columns = week_suffixes
avail_matrix.columns = week_suffixes

# Mask: True where availability is sufficient (>= 20%) AND sales value is numeric
good_avail_mask = avail_matrix >= AVAIL_THRESHOLD          # shape: (rows × weeks)
valid_sales_mask = sales_matrix.notna() & good_avail_mask  # numeric AND good avail

# For each row, compute mean of sales from "good availability" weeks
# Exclude the current week itself when computing the reference mean
for week in week_suffixes:
    adj_col   = avail_week_map[week][0]
    avail_col = avail_week_map[week][1]
    new_col   = f"Outlier_corrected_{week}"

    val_numeric   = sales_matrix[week]                      # numeric series for this week
    avail_numeric = avail_matrix[week]                      # availability for this week

    # Start with original (numeric) values
    pivot_final[new_col] = val_numeric

    # Identify rows where this week has low availability (< 20%) and a numeric sales value
    low_avail_mask = (
        avail_numeric.notna() &
        (avail_numeric < AVAIL_THRESHOLD) &
        val_numeric.notna()                                  # only replace if value exists
    )

    if low_avail_mask.any():
        # Reference weeks = all OTHER weeks with good availability
        other_weeks = [w for w in week_suffixes if w != week]

        # Mean of avl_corrected_sales for other good-availability weeks per row
        other_good = valid_sales_mask[other_weeks]          # (rows × other_weeks), bool
        other_sales = sales_matrix[other_weeks]             # (rows × other_weeks), numeric

        # Mask to NaN where avail is bad, then take row mean
        ref_sales = other_sales.where(other_good)           # NaN where avail < 20%
        ref_mean  = ref_sales.mean(axis=1)                  # row-wise mean of valid weeks

        # Only replace where low_avail AND a valid reference mean exists
        has_ref = ref_mean.notna()
        replace_mask = low_avail_mask & has_ref

        # Replacement = max(mean_of_good_weeks, raw_actual_sales × 1.5)
        # raw sales ×1.5 avoids double-uplifting (avl_corrected already has STF applied)
        if week in raw_sales_matrix.columns:
            raw_val = raw_sales_matrix[week]
        else:
            raw_val = val_numeric   # fallback to avl_corrected if raw col missing
        scaled_sales = (raw_val * 1.5).round(0)
        final_replacement = np.maximum(ref_mean, scaled_sales)

        pivot_final.loc[replace_mask, new_col] = final_replacement[replace_mask].round(0)

    # Always restore non-numeric values ('L') from the original column
    non_numeric_mask = pivot_final[adj_col].notna() & pd.to_numeric(pivot_final[adj_col], errors='coerce').isna()
    if non_numeric_mask.any():
        pivot_final[new_col] = pivot_final[new_col].astype(object)
        pivot_final.loc[non_numeric_mask, new_col] = pivot_final.loc[non_numeric_mask, adj_col]

    # Fill originally-blank (NaN) cells with 'L' for visual consistency
    blank_mask = pivot_final[adj_col].isna()
    if blank_mask.any():
        pivot_final[new_col] = pivot_final[new_col].astype(object)
        pivot_final.loc[blank_mask, new_col] = 'L'

# # %%
# # =============================================================================
# # STEP 2 — SPIKE / DIP OUTLIER CORRECTION  (commented out — enable when needed)
# # Runs on the Outlier_corrected_ columns produced by Step 1 above.
# # High spike : value deviates from BOTH row_avg and row_median -> replace with median
# # Low dip    : value < 0.5×avg AND < 0.5×median (row_avg >= 3) -> replace with avg
# # Latest week (_8) is never corrected.
# # 'L' and blank values are always preserved.
# =============================================================================

outlier_cols = [c for c in pivot_final.columns if c.startswith("Outlier_corrected_")]

# Row-wise stats on the already availability-corrected numeric values
oc_numeric = pivot_final[outlier_cols].apply(pd.to_numeric, errors='coerce')
pivot_final['row_avg']    = oc_numeric.mean(axis=1)
pivot_final['row_median'] = oc_numeric.median(axis=1)

for oc_col in outlier_cols:
    week_suffix = oc_col.split("_")[-1]

    # Latest week — no outlier correction
    if week_suffix == "8":
        continue

    val_numeric = pd.to_numeric(pivot_final[oc_col], errors='coerce')

    positive_mask = val_numeric > 0
    avg_outlier   = (val_numeric - pivot_final['row_avg']).abs()    > pivot_final['row_avg']
    med_outlier   = (val_numeric - pivot_final['row_median']).abs() > pivot_final['row_median']

    # High-spike: deviates from BOTH avg and median (meaningful baseline only)
    spike_mask = positive_mask & (pivot_final['row_avg'] >= 3) & avg_outlier & med_outlier
    pivot_final.loc[spike_mask, oc_col] = pivot_final.loc[spike_mask, 'row_median']

    # Low-dip: positive but < 50% of both avg and median
    dip_mask = (
        positive_mask &
        (pivot_final['row_avg'] >= 3) &
        (val_numeric < 0.5 * pivot_final['row_avg']) &
        (val_numeric < 0.5 * pivot_final['row_median'])
    )
    pivot_final.loc[dip_mask, oc_col] = pivot_final.loc[dip_mask, 'row_avg']

    # Re-preserve 'L' and blanks — spike/dip logic must never overwrite them
    non_numeric_mask = pivot_final[oc_col].notna() & pd.to_numeric(pivot_final[oc_col], errors='coerce').isna()
    if non_numeric_mask.any():
        pivot_final.loc[non_numeric_mask, oc_col] = pivot_final.loc[non_numeric_mask, oc_col]

# %%
pivot_final = reorder_week_columns(pivot_final)

# %%
print(pivot_final.columns)

# %%
_percentile_slices = load_percentile_slices_engine(DP_LOGICS_FOLDER)
Percentile = _percentile_slices["percentile"]

# %%
sugg_plan = pivot_final.merge(
    Percentile,
    how="left",
    on=["city_name", "sub category", "day"]
)

# %%
print(sugg_plan.columns)

# %%
# =============================================================================
# HTT-BASED PERCENTILE OVERRIDE
# Source: P-H Master tab in Product_Masters.xlsx (hub + SKU Class Prod + day)
# For rows where HTT == "head": set Percentile = 0.75
# =============================================================================
_ph_df = _ph_master_raw.copy()
_ph_df.columns = [str(c).strip() for c in _ph_df.columns]
print(f"P-H Master columns: {_ph_df.columns.tolist()}")

# Detect columns flexibly
_ph_hub_col = next((c for c in _ph_df.columns if c.strip().lower() == "hub_name"), None)
_ph_sku_col = next((c for c in _ph_df.columns if "sku" in c.strip().lower() and "class" in c.strip().lower()), None)
_ph_day_col = next((c for c in _ph_df.columns if c.strip().lower() == "day"), None)
_ph_htt_col = next((c for c in _ph_df.columns if c.strip().lower() == "htt"), None)

if _ph_hub_col and _ph_sku_col and _ph_htt_col:
    _keep_cols = [_ph_hub_col, _ph_sku_col, _ph_htt_col] + ([_ph_day_col] if _ph_day_col else [])
    _htt_raw = (
        _ph_df[_keep_cols]
        .rename(columns={
            _ph_hub_col: "hub_name",
            _ph_sku_col: "SKU Class Prod",
            _ph_htt_col: "_htt",
            **({_ph_day_col: "day"} if _ph_day_col else {}),
        })
        .dropna(subset=["hub_name", "SKU Class Prod"])
    )

    for _k in ["hub_name", "SKU Class Prod"] + (["day"] if "day" in _htt_raw.columns else []):
        _htt_raw[_k] = _htt_raw[_k].astype(str).str.strip()
    _htt_raw["_htt"] = _htt_raw["_htt"].astype(str).str.strip().str.lower()

    # Collapse duplicates deterministically: head > torso > tail
    def _pick_htt(vals):
        _s = set(v for v in vals if isinstance(v, str))
        if "head" in _s:
            return "head"
        if "torso" in _s:
            return "torso"
        return "tail"

    _grp_keys = ["hub_name", "SKU Class Prod"] + (["day"] if "day" in _htt_raw.columns else [])
    _htt_map = _htt_raw.groupby(_grp_keys, as_index=False)["_htt"].agg(_pick_htt)

    # Merge with day-level keys when available in P-H; otherwise hub+sku level.
    _merge_keys = ["hub_name", "SKU Class Prod"] + (["day"] if "day" in _htt_map.columns and "day" in sugg_plan.columns else [])
    for _k in _merge_keys:
        sugg_plan[_k] = sugg_plan[_k].astype(str).str.strip()
    sugg_plan = sugg_plan.merge(_htt_map, on=_merge_keys, how="left")
    sugg_plan["_htt"] = sugg_plan["_htt"].fillna("tail")

    sugg_plan["Percentile"] = pd.to_numeric(sugg_plan["Percentile"], errors="coerce")
    sugg_plan.loc[sugg_plan["_htt"] == "head", "Percentile"] = 0.75

    _head_count = (sugg_plan["_htt"] == "head").sum()
    print(f"HTT override applied: {_head_count:,} rows set to Percentile=0.75 (head mappings from P-H Master)")
    sugg_plan.drop(columns=["_htt"], inplace=True)
else:
    print(
        f"WARNING: P-H HTT columns not detected "
        f"(hub={_ph_hub_col}, sku={_ph_sku_col}, day={_ph_day_col}, htt={_ph_htt_col}). "
        "Skipping HTT override."
    )
    sugg_plan["Percentile"] = pd.to_numeric(sugg_plan["Percentile"], errors="coerce")



# %%
# J:K — hub-level percentile override (hub_name, percentile_override)
Percentile_override = _percentile_slices["override_hub"]

# %%
sugg_plan = sugg_plan.merge(Percentile_override, on="hub_name", how="left")

# %%
sugg_plan["Percentile"] = sugg_plan["percentile_override"].combine_first(sugg_plan["Percentile"])

# %%
sugg_plan = sugg_plan.drop(columns=["percentile_override"])

# %%
# O:R — hub × SKU Class Prod × day percentile override (hub_name, SKU Class Prod, day, percentile_override_2)
Percentile_override_2 = _percentile_slices["override_hub_sku_day"].copy()
Percentile_override_2.columns = [c.strip() for c in Percentile_override_2.columns]

# Normalize duplicated Excel headers like hub_name.1 / day.1
_p2_col_renames = {}
for _c in Percentile_override_2.columns:
    _base = str(_c).strip()
    if _base.lower().startswith("hub_name"):
        _p2_col_renames[_c] = "hub_name"
    elif _base.lower().startswith("day"):
        _p2_col_renames[_c] = "day"
Percentile_override_2 = Percentile_override_2.rename(columns=_p2_col_renames)

print(f"Percentile_override_2 columns: {Percentile_override_2.columns.tolist()}")

# %%
_p2_merge_keys = ["hub_name", "SKU Class Prod", "day"]
_p2_value_col  = "percentile_override_2"
_p2_cols_present = Percentile_override_2.columns.tolist()

if all(k in _p2_cols_present for k in _p2_merge_keys) and _p2_value_col in _p2_cols_present:
    # Standardize keys before merge to improve match rate.
    for _k in _p2_merge_keys:
        Percentile_override_2[_k] = Percentile_override_2[_k].astype(str).str.strip()
        sugg_plan[_k] = sugg_plan[_k].astype(str).str.strip()

    # Parse override values robustly (supports values like "45%" and decimals).
    _p2_raw = Percentile_override_2[_p2_value_col].astype(str).str.strip()
    _is_pct = _p2_raw.str.contains("%", regex=False, na=False)
    _p2_num = pd.to_numeric(_p2_raw.str.replace("%", "", regex=False), errors="coerce")
    _p2_num = np.where(_is_pct, _p2_num / 100.0, _p2_num)
    # If values are given as 45 (not 0.45), scale down.
    _p2_num = pd.Series(_p2_num)
    _p2_num = np.where(_p2_num > 1, _p2_num / 100.0, _p2_num)
    Percentile_override_2[_p2_value_col] = _p2_num

    # Compute allowed percentile range from O:R values
    _p2_pct_values = pd.to_numeric(Percentile_override_2[_p2_value_col], errors="coerce").dropna()
    _p2_min = _p2_pct_values.min()
    _p2_max = _p2_pct_values.max()
    print(f"Percentile_override_2 range: [{_p2_min}, {_p2_max}]")

    sugg_plan = sugg_plan.merge(
        Percentile_override_2,
        on=_p2_merge_keys,
        how="left"
    )
    sugg_plan[_p2_value_col] = pd.to_numeric(sugg_plan[_p2_value_col], errors="coerce")

    # Apply adjustment only where override_2 value exists.
    _has_override = sugg_plan[_p2_value_col].notna()
    _final_col = next((c for c in ["Final_Plan", "final_plan"] if c in sugg_plan.columns), None)
    _base_col  = next((c for c in ["Base_Plan (qty)", "Base_plan", "base_plan"] if c in sugg_plan.columns), None)

    if _final_col and _base_col:
        _final_vals = pd.to_numeric(sugg_plan[_final_col], errors="coerce")
        _base_vals  = pd.to_numeric(sugg_plan[_base_col],  errors="coerce")

        # Final < Base → increase by 10%, cap at O:R max
        _mask_low = _has_override & (_final_vals < _base_vals)
        sugg_plan.loc[_mask_low, _p2_value_col] = (
            sugg_plan.loc[_mask_low, _p2_value_col] * 1.1
        ).clip(upper=_p2_max)

        # Final > Base → decrease to 0.45 floor with O:R min bound
        _mask_high = _has_override & (_final_vals > _base_vals)
        sugg_plan.loc[_mask_high, _p2_value_col] = max(0.5 * 0.9, _p2_min)

        print(
            f"Percentile_override_2 adjustments: {_mask_low.sum():,} rows increased (Final<Base), "
            f"{_mask_high.sum():,} rows decreased (Final>Base)"
        )
    else:
        print(
            f"WARNING: Could not find comparison columns for override_2 adjustment "
            f"(final={_final_col}, base={_base_col}). Applying raw override_2 values without adjustment."
        )

    sugg_plan["Percentile"] = sugg_plan[_p2_value_col].combine_first(sugg_plan["Percentile"])
    sugg_plan = sugg_plan.drop(columns=[_p2_value_col])
else:
    print(f"WARNING: Percentile_override_2 columns {_p2_cols_present} do not match expected keys {_p2_merge_keys + [_p2_value_col]}. Skipping override_2 merge.")

# %%
sugg_plan["Percentile"] = pd.to_numeric(sugg_plan["Percentile"], errors="coerce")

# %%
outlier_cols = [c for c in sugg_plan.columns if c.startswith("Outlier_corrected_")]
# outlier_cols = sorted(outlier_cols, key=lambda x: int(x.split("_")[-1]))

# %%
print(outlier_cols)

# %%
sugg_plan["Percentile"] = pd.to_numeric(sugg_plan["Percentile"], errors="coerce")

# %%
print(sugg_plan.columns)

# %%
def get_sugg_plan(row, cols, percentile_col="Percentile"):
    # Convert all to string and strip spaces
    raw_values = row[cols].astype(str).str.strip()

    # Keep only purely numeric values (integer or decimal, positive or zero)
    numeric_mask = raw_values.str.match(r'^\d*\.?\d+$')
    numeric_values = pd.to_numeric(raw_values.where(numeric_mask), errors="coerce").values[::-1]

    # Include all numeric values (including 0s)
    valid_vals = [v for v in numeric_values if pd.notna(v)]

    # --- Final decision ---
    if len(valid_vals) == 0:
        return np.nan

    pct = row[percentile_col]
    if pct <= 1:  # if percentile is given in 0–1 scale
        pct *= 100

    # If percentile is 50, use mean of all numeric values instead
    if pct == 50:
        return np.mean(valid_vals)

    return np.percentile(valid_vals, pct)

# %%
print(sugg_plan.columns)

# %%
# ─── Fast vectorised replacement for get_sugg_plan ───────────────────────────
# The original apply() runs regex + pd.to_numeric inside a Python loop for
# every row, which is slow on large DataFrames.  The approach below:
#   1. Parses the entire outlier matrix to numeric ONCE (vectorised)
#   2. Reverses column order once (matching the original [::-1] logic)
#   3. Loops only over the few unique percentile values (~3-5) — each inner
#      iteration processes all matching rows with pure numpy, which is ~20x
#      faster than Python object processing per row.
_oc_raw      = sugg_plan[outlier_cols].astype(str).apply(lambda c: c.str.strip())
_oc_num_mask = _oc_raw.apply(lambda c: c.str.match(r'^\d*\.?\d+$'))
_oc_mat      = _oc_raw.where(_oc_num_mask).apply(pd.to_numeric, errors='coerce')
_oc_mat_rev  = _oc_mat[outlier_cols[::-1]].values   # numpy (n_rows, n_cols)

_pct_arr = sugg_plan['Percentile'].values.astype(float)
_pct_arr = np.where(_pct_arr <= 1, _pct_arr * 100, _pct_arr)

_sugg_result = np.full(len(sugg_plan), np.nan)
for _pct_val in np.unique(_pct_arr[~np.isnan(_pct_arr)]):
    _idx  = np.where(_pct_arr == _pct_val)[0]
    _rows = _oc_mat_rev[_idx]           # (n_matching, n_cols)
    if _pct_val == 50:
        _sugg_result[_idx] = np.nanmean(_rows, axis=1)
    else:
        for _k, _ri in enumerate(_idx):
            _valid = _rows[_k][~np.isnan(_rows[_k])]
            if len(_valid) > 0:
                _sugg_result[_ri] = np.percentile(_valid, _pct_val)

sugg_plan["sugg_plan"] = _sugg_result

# %%
# sugg_plan.to_clipboard()  # disabled for speed

# %%
_BP_CACHE_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "outputs", "prev_baseline_latest.parquet"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "prev_baseline_latest.parquet"),
]
base_plan = None
_BP_CACHE = None
for _cache_path in _BP_CACHE_CANDIDATES:
    if os.path.exists(_cache_path):
        _BP_CACHE = _cache_path
        base_plan = pd.read_parquet(_cache_path)
        print(f"[base_plan] Loaded from parquet cache: {_cache_path} ({len(base_plan):,} rows)")
        break

if base_plan is None:
    print("[base_plan] Cache not found — reading from Excel (update cache via Streamlit → Fetch Previous Baseline)")
    import glob
    _possible_files = glob.glob(os.path.join(BASELINE_OUTPUTS_FOLDER, "*.xlsx"))
    if _possible_files:
        _latest = max(_possible_files, key=os.path.getctime)
        base_plan = pd.read_excel(_latest)
        print(f"Loaded from: {_latest}")
    else:
        raise FileNotFoundError(
            "Could not find prev_baseline_latest.parquet or any excel file in BASELINE_OUTPUTS_FOLDER. "
            "Run Auto-Pilot / Fetch Previous Baseline in Streamlit first."
        )

base_plan = normalize_base_plan_columns(base_plan)
if "BasePlan" not in base_plan.columns:
    raise KeyError(
        "BasePlan column not found in previous baseline data. "
        f"Available columns: {base_plan.columns.tolist()}"
    )

# %%
print(base_plan["BasePlan"].sum())

# %%
base_plan_df = base_plan.merge(
    cluster_mapping_df[["product_id", "Mother_hubid", "MotherHub_name", "childHub_name"]],
    left_on=["product_id", "hub_name"],
    right_on=["product_id", "childHub_name"],
    how="left"
)

# %%
child_hubs = base_plan_df[~base_plan_df["MotherHub_name"].isna()].copy()

# %%
print(base_plan_df["BasePlan"].sum())

# %%
# child_hubs.to_clipboard()  # disabled for speed

# %%
child_hubs["process_dt"] = pd.to_datetime(child_hubs["process_dt"], errors="coerce")


# %%
mother_agg = (
    child_hubs.groupby(
        ["process_dt", "product_id", "MotherHub_name"],
        as_index=False
    )["BasePlan"].sum()
)


# %%
mother_agg_subset = mother_agg.rename(columns={
    "MotherHub_name": "hub_name",
    "Mother_hubid": "hub_id"
})[["process_dt", "hub_name", "product_id","BasePlan"]].copy()

# %%
mother_agg_subset = mother_agg_subset.rename(columns={
    "BasePlan": "Agg_base_plan_mother_hub"
})

# %%
base_plan_df.loc[base_plan_df.index.isin(child_hubs.index), "BasePlan"] = 0

# %%
print(base_plan_df["BasePlan"].sum())

# %%
base_plan_df["process_dt"] = pd.to_datetime(base_plan_df["process_dt"], errors="coerce")
mother_agg_subset["process_dt"] = pd.to_datetime(mother_agg_subset["process_dt"], errors="coerce")


# %%
Aggregated_base_plan = base_plan_df.merge(
    mother_agg_subset,
    on=["process_dt", "hub_name", "product_id"],
    how="left"
)

# %%
print(Aggregated_base_plan["BasePlan"].sum())

# %%
Aggregated_base_plan["Agg_base_plan_mother_hub"] = Aggregated_base_plan["Agg_base_plan_mother_hub"].fillna(0)

# %%
print(Aggregated_base_plan["Agg_base_plan_mother_hub"].sum())

# %%
Aggregated_base_plan["BasePlan"] += Aggregated_base_plan["Agg_base_plan_mother_hub"]

# %%
print(Aggregated_base_plan["BasePlan"].sum())

# %%
Aggregated_base_plan = Aggregated_base_plan.rename(columns={
    "sku class prod" : "SKU Class Prod"
})

# %%
print(Aggregated_base_plan.columns)

# %%
base_plan = Aggregated_base_plan[[
    "process_dt",
    "Sub-category",
    "Week",
    "day",
    "product_id",
    "product_name",
    "city_name",
    "hub_name",
    "BasePlan",
    "SKU Class Prod"
]].copy()

# %%
print(Aggregated_base_plan["BasePlan"].sum())

# %%
base_plan_grouped = (
    base_plan.groupby(["hub_name", "SKU Class Prod", "day"], as_index=False)
    .agg({"BasePlan": "sum"})
)

# %%
print(base_plan_grouped["BasePlan"].sum())

# %%
print(sugg_plan.head())

# %%
Final_Plan = sugg_plan.merge(base_plan_grouped, 
                         on=["hub_name", "SKU Class Prod", "day"],
                         how="left")

# %%
print(Final_Plan["BasePlan"].sum())

# %%
Final_Plan = Final_Plan.rename(columns={
    "BasePlan": "Base_Plan (qty)"
})

# %%
Final_Plan["Base_Plan (qty)"] = Final_Plan["Base_Plan (qty)"].fillna(0)



# %%
VA_exclusive_1 = [
    "Burger", "Eggs", 
 "Spreads", "Heat & Eat"
]

VA_exclusive_2 = [
    "Kebab & Tandoor", 
    "Ready to Cook",
]

# %%
outlier_cols = [c for c in Final_Plan.columns if c.startswith("Outlier_corrected_")]

Final_Plan["numeric_outlier_count"] = (
    Final_Plan[outlier_cols]
    .apply(pd.to_numeric, errors="coerce")
    .notna()
    .sum(axis=1)
)


# %%
skip_hubs = ["CCS", "ECS", "HKM", "KLK", "SMG", "SPC"]
skip_cities = ["Chennai", "Kolkata"]

def final_plan_logic(row):
    # Case -1: both NaN -> 0
    if pd.isna(row["sugg_plan"]) and pd.isna(row["Base_Plan (qty)"]):
        return 0

    # Case 0: sugg_plan NaN -> base_plan
    if pd.isna(row["sugg_plan"]):
        return row["Base_Plan (qty)"]

    # Case 1: base_plan NaN -> 0
    if pd.isna(row["Base_Plan (qty)"]):
        return 0

    # Case 2: base_plan 0 -> sugg_plan
    if row["Base_Plan (qty)"] == 0:
        return row["sugg_plan"]

    # 🔥 Case NEW: exactly one numeric outlier datapoint
    if row["numeric_outlier_count"] == 1:
        if row["sugg_plan"] == 0:
            return row["Base_Plan (qty)"]
        else:
            return max(
                row["sugg_plan"],
                (row["sugg_plan"] + row["Base_Plan (qty)"]) / 2
            )

    # Case 3 & 4: VA_exclusive rules
    if (row["hub_name"] not in skip_hubs) and (row["city_name"] not in skip_cities):

        if row["sub category"] in VA_exclusive_1:
            if row["sugg_plan"] < 5:
                return min(row["sugg_plan"], 2.0 * row["Base_Plan (qty)"])
            else:
                return min(row["sugg_plan"], 1.5 * row["Base_Plan (qty)"])

        if row["sub category"] in VA_exclusive_2:
            if row["sugg_plan"] < 5:
                return min(row["sugg_plan"], 2.0 * row["Base_Plan (qty)"])
            else:
                return min(row["sugg_plan"], 2.0 * row["Base_Plan (qty)"])

    # Default
    return row["sugg_plan"]


# %%
_s   = Final_Plan["sugg_plan"]
_b   = Final_Plan["Base_Plan (qty)"]
_n   = Final_Plan["numeric_outlier_count"]
_cat = Final_Plan["sub category"]
_hub = Final_Plan["hub_name"]
_cty = Final_Plan["city_name"]

_not_skip = ~_hub.isin(skip_hubs) & ~_cty.isin(skip_cities)

# Pre-compute branch values (evaluated for all rows; conditions pick the right one)
_va1 = np.where(_s < 5, np.minimum(_s, 2.0 * _b), np.minimum(_s, 1.5 * _b))
_va2 = np.minimum(_s, 2.0 * _b)
_oc1 = np.maximum(_s, (_s + _b) / 2.0)

Final_Plan["Final_Plan"] = np.select(
    [
        _s.isna() & _b.isna(),                    # both NaN  -> 0
        _s.isna(),                                 # sugg NaN  -> base
        _b.isna(),                                 # base NaN  -> 0
        _b == 0,                                   # base 0    -> sugg
        (_n == 1) & (_s == 0),                    # oc=1, sugg=0 -> base
        (_n == 1) & (_s != 0),                    # oc=1, sugg>0 -> max formula
        _not_skip & _cat.isin(VA_exclusive_1),    # VA cap 1
        _not_skip & _cat.isin(VA_exclusive_2),    # VA cap 2
    ],
    [0, _b, 0, _s, _b, _oc1, _va1, _va2],
    default=_s
).round()



# %%
# Final_Plan.to_clipboard()  # disabled for speed

# %%
_COMPARE_DIR = os.environ.get("BASELINE_COMPARE_DIR")
if _COMPARE_DIR:
    import json as _json
    _COMPARE_TAG = os.environ.get("BASELINE_COMPARE_TAG", "run")
    os.makedirs(_COMPARE_DIR, exist_ok=True)
    _compare_path = os.path.join(_COMPARE_DIR, f"Final_Plan_{_COMPARE_TAG}.pkl")
    Final_Plan.to_pickle(_compare_path)
    _meta = {
        "tag": _COMPARE_TAG,
        "rows": int(len(Final_Plan)),
        "columns": int(len(Final_Plan.columns)),
        "column_names": Final_Plan.columns.tolist(),
        "dtypes": {str(c): str(t) for c, t in Final_Plan.dtypes.items()},
    }
    with open(os.path.join(_COMPARE_DIR, f"meta_{_COMPARE_TAG}.json"), "w", encoding="utf-8") as _mf:
        _json.dump(_meta, _mf, indent=2)
    print(f"[COMPARE] Saved Final_Plan -> {_compare_path} ({len(Final_Plan):,} rows x {len(Final_Plan.columns)} cols)")
    raise SystemExit(0)

# %%

_OUTPUTS_FOLDER = BASELINE_OUTPUTS_FOLDER
_os.makedirs(_OUTPUTS_FOLDER, exist_ok=True)
_timestamp = _datetime.now().strftime("%Y%m%d_%H%M%S")
_output_path = _os.path.join(_OUTPUTS_FOLDER, f"Summary_{_timestamp}.xlsx")
Final_Plan.to_excel(_output_path, index=False)
print(f"[Baseline] Summary saved to: {_output_path}")

# %%
# =============================================================================
# HUB LEVEL SUGGESTION — save log of previous, then overwrite with new values
# =============================================================================
print(f"[Debug] Final_Plan shape: {Final_Plan.shape}")
print(f"[Debug] Final_Plan columns: {Final_Plan.columns.tolist()}")

_HUB_SHEET_URL = DP_LOGICS_SHEET_URL
_HUB_SHEET_TAB  = "Hub level Suggestion"
_LOG_FOLDER     = DP_LOGICS_FOLDER

# Initialise so comparison block always has valid references even if Hub step fails
_prev_df    = pd.DataFrame()
_new_hub_df = pd.DataFrame()

try:
    _hub_spreadsheet = sheets_manager.gc.open_by_url(_HUB_SHEET_URL)
    _hub_ws          = _hub_spreadsheet.worksheet(_HUB_SHEET_TAB)

    # Step 1: Read existing Hub level Suggestion (previous baseline)
    _prev_data  = _hub_ws.get_all_values()
    if len(_prev_data) < 2:
        raise ValueError("[Hub Suggestion] Sheet is empty — nothing to log or compare against.")
    _prev_df = pd.DataFrame(_prev_data[1:], columns=_prev_data[0])
    # Strip whitespace from column names to avoid hidden mismatches
    _prev_df.columns = [c.strip() for c in _prev_df.columns]
    print(f"[Hub Suggestion] Previous sheet loaded: {len(_prev_df):,} rows")
    print(f"[Hub Suggestion] Columns: {_prev_df.columns.tolist()}")

    # Step 2: Save previous sheet as timestamped log
    _os.makedirs(_LOG_FOLDER, exist_ok=True)
    _log_path = _os.path.join(_LOG_FOLDER, f"Hub_level_Suggestion_log_{_timestamp}.xlsx")
    _prev_df.to_excel(_log_path, index=False)
    print(f"[Hub Suggestion] Previous baseline logged to: {_log_path}")

    # Step 3: Build lookup from Final_Plan — detect column names flexibly
    def _detect(df, candidates):
        for c in df.columns:
            if c.strip().lower() in [x.lower() for x in candidates]:
                return c
        return None

    _fp_hub   = _detect(Final_Plan, ["hub_name", "hub"])
    _fp_sku   = _detect(Final_Plan, ["SKU Class Prod", "sku class prod", "sku class"])
    _fp_day   = _detect(Final_Plan, ["day"])
    _fp_fp    = _detect(Final_Plan, ["Final_Plan", "final_plan"])
    _missing_fp = [n for n, v in [("hub_name", _fp_hub), ("SKU Class Prod", _fp_sku),
                                   ("day", _fp_day), ("Final_Plan", _fp_fp)] if v is None]
    if _missing_fp:
        raise KeyError(f"Final_Plan missing required columns: {_missing_fp}. Available: {Final_Plan.columns.tolist()}")

    _final_lookup = Final_Plan[[_fp_hub, _fp_sku, _fp_day, _fp_fp]].copy()
    _final_lookup.columns = ["hub_name", "sku class prod", "day", "Final_Plan"]
    for _c in ["hub_name", "sku class prod", "day"]:
        _final_lookup[_c] = _final_lookup[_c].astype(str).str.strip()

    # Lookup mode (no summation): keep only one Final_Plan per hub+sku+day.
    # This avoids doubling when summary has repeated line items for the same key.
    _final_lookup["Final_Plan"] = pd.to_numeric(_final_lookup["Final_Plan"], errors="coerce")
    _dup_mask = _final_lookup.duplicated(subset=["hub_name", "sku class prod", "day"], keep="first")
    _dup_cnt = int(_dup_mask.sum())
    if _dup_cnt:
        print(f"[Hub Suggestion] WARNING: {_dup_cnt:,} duplicate summary rows detected for hub+sku+day; keeping first (lookup mode).")
    _final_lookup = _final_lookup.drop_duplicates(
        subset=["hub_name", "sku class prod", "day"],
        keep="first"
    ).reset_index(drop=True)
    print(f"[Hub Suggestion] Final_Plan lookup built (unique keys): {len(_final_lookup):,} rows")

    # Step 4: Detect key columns in _prev_df and merge
    _prev_hub = _detect(_prev_df, ["hub_name", "hub"])
    _prev_sku = _detect(_prev_df, ["sku class prod", "SKU Class Prod", "sku class"])
    _prev_day = _detect(_prev_df, ["day"])
    _prev_bp  = _detect(_prev_df, ["Base_plan", "base_plan", "base plan"])
    _missing_prev = [n for n, v in [("hub_name", _prev_hub), ("sku class prod", _prev_sku),
                                     ("day", _prev_day), ("Base_plan", _prev_bp)] if v is None]
    if _missing_prev:
        raise KeyError(f"Hub Suggestion sheet missing columns: {_missing_prev}. Available: {_prev_df.columns.tolist()}")

    # Standardise key column names in _prev_df
    _prev_df = _prev_df.rename(columns={_prev_hub: "hub_name", _prev_sku: "sku class prod",
                                         _prev_day: "day",      _prev_bp:  "Base_plan"})
    for _c in ["hub_name", "sku class prod", "day"]:
        _prev_df[_c] = _prev_df[_c].astype(str).str.strip()

    # Keep all rows from Hub Suggestion; if no matching Final_Plan key is found,
    # retain the previous Base_plan value from the sheet.
    _new_hub_df = _prev_df.merge(
        _final_lookup,
        on=["hub_name", "sku class prod", "day"],
        how="left"
    )
    _new_hub_df["Base_plan_prev"] = pd.to_numeric(_new_hub_df["Base_plan"], errors="coerce")
    _new_hub_df["Base_plan_new"] = pd.to_numeric(_new_hub_df["Final_Plan"], errors="coerce")
    _new_hub_df["Base_plan"] = _new_hub_df["Base_plan_new"].where(
        _new_hub_df["Base_plan_new"].notna(),
        _new_hub_df["Base_plan_prev"]
    )
    _new_hub_df["base_plan_source"] = np.where(
        _new_hub_df["Base_plan_new"].notna(),
        "summary",
        "previous_hub_suggestion"
    )

    _matched   = _new_hub_df["Base_plan_new"].notna().sum()
    _unmatched = _new_hub_df["Base_plan_new"].isna().sum()
    print(
        f"[Hub Suggestion] Matched: {_matched:,} rows | "
        f"Unmatched (kept previous Base_plan): {_unmatched:,} rows"
    )

    _new_hub_df = _new_hub_df.drop(columns=["Final_Plan", "Base_plan_prev", "Base_plan_new"], errors="ignore")
    print(f"[Hub Suggestion] Rows to write: {len(_new_hub_df):,}")

    # Persist audit source in Summary file as requested.
    # This tags each Final_Plan row with whether Hub-sheet base_plan came from
    # summary match or previous Hub level Suggestion fallback.
    _source_map = _new_hub_df[["hub_name", "sku class prod", "day", "base_plan_source"]].drop_duplicates(
        subset=["hub_name", "sku class prod", "day"], keep="first"
    )
    _summary_enriched = Final_Plan.copy()
    _summary_enriched["_hub_key"] = _summary_enriched[_fp_hub].astype(str).str.strip()
    _summary_enriched["_sku_key"] = _summary_enriched[_fp_sku].astype(str).str.strip()
    _summary_enriched["_day_key"] = _summary_enriched[_fp_day].astype(str).str.strip()
    _summary_enriched = _summary_enriched.merge(
        _source_map,
        left_on=["_hub_key", "_sku_key", "_day_key"],
        right_on=["hub_name", "sku class prod", "day"],
        how="left"
    )
    _summary_enriched["base_plan_source"] = _summary_enriched["base_plan_source"].fillna("summary_only_not_in_hub_sheet")
    _summary_enriched.drop(
        columns=["_hub_key", "_sku_key", "_day_key", "hub_name_y", "sku class prod", "day"],
        errors="ignore",
        inplace=True
    )
    _summary_enriched.rename(columns={"hub_name_x": "hub_name"}, inplace=True)
    _summary_enriched.to_excel(_output_path, index=False)
    print(f"[Baseline] Summary updated with base_plan_source: {_output_path}")

    # Step 5: Write updated Hub level Suggestion back to Google Sheet
    _hub_ws.clear()
    set_with_dataframe(_hub_ws, _new_hub_df)
    print(f"[Hub Suggestion] Google Sheet updated: {len(_new_hub_df):,} rows written to '{_HUB_SHEET_TAB}'")

except Exception as _hub_err:
    print(f"[Hub Suggestion] ERROR: {_hub_err}")
    import traceback as _tb
    print(_tb.format_exc())

# %%
# =============================================================================
# BASE PLAN COMPARISON — write 3 granularity views to validation Google Sheet
# Tabs: Hub SKU Day | City Category | City Level
# =============================================================================
_VALIDATION_SHEET_URL = VALIDATION_SHEET_URL

print(f"[Validation] _prev_df shape={_prev_df.shape} | columns={_prev_df.columns.tolist()}")
print(f"[Validation] _new_hub_df shape={_new_hub_df.shape} | columns={_new_hub_df.columns.tolist()}")

if _prev_df.empty or _new_hub_df.empty:
    print(f"[Validation] Skipping — prev_df empty={_prev_df.empty}, new_hub_df empty={_new_hub_df.empty}. Hub Suggestion step must succeed first.")
else:
    try:
        # Normalise column names in both DataFrames to lowercase+stripped for robust matching
        _prev_df.columns   = [c.strip().lower() for c in _prev_df.columns]
        _new_hub_df.columns = [c.strip().lower() for c in _new_hub_df.columns]

        # Detect the exact column names (handles casing variations)
        def _find_col(df, candidates):
            for c in df.columns:
                if c in candidates:
                    return c
            return None

        _city_col  = _find_col(_prev_df, ["city_name", "city"])
        _hub_col   = _find_col(_prev_df, ["hub_name", "hub"])
        _subcat_col = _find_col(_prev_df, ["sub category", "sub-category", "sub_category", "subcategory"])
        _sku_col   = _find_col(_prev_df, ["sku class prod", "sku_class_prod", "sku class", "skuprod"])
        _day_col   = _find_col(_prev_df, ["day"])
        _bp_col    = _find_col(_prev_df, ["base_plan", "base plan"])

        print(f"[Validation] Detected columns — city={_city_col} hub={_hub_col} subcat={_subcat_col} sku={_sku_col} day={_day_col} bp={_bp_col}")

        _missing = [n for n, v in [("city_name", _city_col), ("hub_name", _hub_col), ("sub category", _subcat_col),
                                    ("sku class prod", _sku_col), ("day", _day_col), ("Base_plan", _bp_col)] if v is None]
        if _missing:
            raise KeyError(f"Columns not found in hub suggestion data: {_missing}. Available: {_prev_df.columns.tolist()}")

        _curr_bp_col = _find_col(_new_hub_df, ["base_plan", "base plan"]) or _bp_col
        _key_cols = [_city_col, _hub_col, _subcat_col, _sku_col, _day_col]
        _rename_map = {_city_col: "city_name", _hub_col: "hub_name", _subcat_col: "sub category",
                       _sku_col: "sku class prod", _day_col: "day"}

        _prev_cmp = _prev_df[[*_key_cols, _bp_col]].copy().rename(columns={**_rename_map, _bp_col: "Base_plan"})

        _missing_curr = [c for c in [*_key_cols, _curr_bp_col] if c not in _new_hub_df.columns]
        if _missing_curr:
            raise KeyError(f"Columns missing in _new_hub_df: {_missing_curr}. Available: {_new_hub_df.columns.tolist()}")
        _curr_cmp = _new_hub_df[[*_key_cols, _curr_bp_col]].copy().rename(columns={**_rename_map, _curr_bp_col: "Base_plan"})

        print(f"[Validation] _prev_cmp shape={_prev_cmp.shape} | _curr_cmp shape={_curr_cmp.shape}")

        for _df_c in [_prev_cmp, _curr_cmp]:
            for _c in ["hub_name", "sku class prod", "day", "city_name", "sub category"]:
                _df_c[_c] = _df_c[_c].astype(str).str.strip()
            _df_c["Base_plan"] = pd.to_numeric(_df_c["Base_plan"], errors="coerce").fillna(0)

        _cmp = _prev_cmp.merge(
            _curr_cmp,
            on=["city_name", "hub_name", "sub category", "sku class prod", "day"],
            how="outer",
            suffixes=("_prev", "_curr")
        ).fillna(0)
        print(f"[Validation] _cmp shape after merge: {_cmp.shape}")
        _cmp["delta_%"] = np.where(
            _cmp["Base_plan_prev"] != 0,
            ((_cmp["Base_plan_curr"] - _cmp["Base_plan_prev"]) / _cmp["Base_plan_prev"] * 100).round(1),
            None
        )

        # Tab 1: Hub SKU Day — days in columns (prev | curr | delta% per day)
        _days_order   = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        _hub_sku_rows = []
        for (_hub, _sku), _grp in _cmp.groupby(["hub_name", "sku class prod"]):
            _row = {"Hub": _hub, "SKU Class": _sku}
            for _d in _days_order:
                _dr = _grp[_grp["day"] == _d]
                _prev_v = _dr["Base_plan_prev"].sum() if not _dr.empty else 0
                _curr_v = _dr["Base_plan_curr"].sum() if not _dr.empty else 0
                _row[f"{_d} Prev"]    = int(_prev_v)
                _row[f"{_d} Curr"]    = int(_curr_v)
                _row[f"{_d} Delta%"]  = round((_curr_v - _prev_v) / _prev_v * 100, 1) if _prev_v != 0 else None
            _hub_sku_rows.append(_row)
        _tab1_df = pd.DataFrame(_hub_sku_rows)

        # Tab 2: City × Category
        _tab2_df = _cmp.groupby(["city_name", "sub category"], as_index=False).agg(
            Prev_Plan=("Base_plan_prev", "sum"), Curr_Plan=("Base_plan_curr", "sum")
        )
        _tab2_df.rename(columns={"city_name": "City", "sub category": "Category"}, inplace=True)
        _tab2_df["Delta_%"] = np.where(
            _tab2_df["Prev_Plan"] != 0,
            ((_tab2_df["Curr_Plan"] - _tab2_df["Prev_Plan"]) / _tab2_df["Prev_Plan"] * 100).round(1),
            None
        )

        # Tab 3: City Level
        _tab3_df = _cmp.groupby("city_name", as_index=False).agg(
            Prev_Plan=("Base_plan_prev", "sum"), Curr_Plan=("Base_plan_curr", "sum")
        )
        _tab3_df.rename(columns={"city_name": "City"}, inplace=True)
        _tab3_df["Delta_%"] = np.where(
            _tab3_df["Prev_Plan"] != 0,
            ((_tab3_df["Curr_Plan"] - _tab3_df["Prev_Plan"]) / _tab3_df["Prev_Plan"] * 100).round(1),
            None
        )

        # Write all three tabs to validation Google Sheet
        _val_ss = sheets_manager.gc.open_by_url(_VALIDATION_SHEET_URL)

        def _apply_sheet_formatting(spreadsheet, ws, df):
            """Bold header, freeze row, number formats, green/red conditional on Delta% cols."""
            sid    = ws.id
            n_rows = len(df) + 1
            n_cols = len(df.columns)
            cols   = list(df.columns)
            reqs   = []

            # 1. Bold white-text navy header
            reqs.append({"repeatCell": {
                "range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": n_cols},
                "cell": {"userEnteredFormat": {
                    "textFormat": {"bold": True,
                                   "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                    "backgroundColor": {"red": 0.18, "green": 0.37, "blue": 0.58},
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE"
                }},
                "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment,verticalAlignment)"
            }})

            # 2. Freeze header
            reqs.append({"updateSheetProperties": {
                "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount"
            }})

            # 3. Per-column: number format + conditional colours for Delta% columns
            for ci, col in enumerate(cols):
                col_l      = col.lower()
                data_range = {"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows,
                              "startColumnIndex": ci, "endColumnIndex": ci + 1}

                if any(x in col_l for x in ["prev", "curr", "plan"]):
                    reqs.append({"repeatCell": {
                        "range": data_range,
                        "cell": {"userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}
                        }},
                        "fields": "userEnteredFormat.numberFormat"
                    }})

                elif "delta" in col_l:
                    # values stored as e.g. 5.2 → display "+5.2%" / "-3.1%"
                    reqs.append({"repeatCell": {
                        "range": data_range,
                        "cell": {"userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER",
                                             "pattern": '+0.0"%";-0.0"%";"-"'}
                        }},
                        "fields": "userEnteredFormat.numberFormat"
                    }})
                    # Green cell for positive delta
                    reqs.append({"addConditionalFormatRule": {"rule": {
                        "ranges": [data_range],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_GREATER",
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": {"red": 0.71, "green": 0.84, "blue": 0.66}}
                        }
                    }, "index": 0}})
                    # Red cell for negative delta
                    reqs.append({"addConditionalFormatRule": {"rule": {
                        "ranges": [data_range],
                        "booleanRule": {
                            "condition": {"type": "NUMBER_LESS",
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"backgroundColor": {"red": 0.96, "green": 0.69, "blue": 0.69}}
                        }
                    }, "index": 1}})

            # 4. Auto-resize columns
            reqs.append({"autoResizeDimensions": {
                "dimensions": {"sheetId": sid, "dimension": "COLUMNS",
                               "startIndex": 0, "endIndex": n_cols}
            }})

            spreadsheet.batch_update({"requests": reqs})
            print(f"    [fmt] base formatting applied to sheet id={sid}")

            # 5. Alternating row shading
            # First delete any existing banded ranges on this sheet (avoid duplicate error)
            try:
                _ss_meta = spreadsheet.get(fields="sheets(properties/sheetId,bandedRanges)")
                for _sh in _ss_meta.get("sheets", []):
                    if _sh.get("properties", {}).get("sheetId") == sid:
                        _del_reqs = [
                            {"deleteBanding": {"bandedRangeId": _br["bandedRangeId"]}}
                            for _br in _sh.get("bandedRanges", [])
                        ]
                        if _del_reqs:
                            spreadsheet.batch_update({"requests": _del_reqs})
                        break
            except Exception as _be:
                print(f"    [fmt] could not clear existing banding (ignored): {_be}")

            spreadsheet.batch_update({"requests": [{"addBanding": {
                "bandedRange": {
                    "range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": n_rows,
                              "startColumnIndex": 0, "endColumnIndex": n_cols},
                    "rowProperties": {
                        "firstBandColor":  {"red": 1.0,  "green": 1.0,  "blue": 1.0},
                        "secondBandColor": {"red": 0.93, "green": 0.95, "blue": 0.98}
                    }
                }
            }}]})
            print(f"    [fmt] banding applied")

        for _tab_name, _tab_df in [("Hub SKU Day", _tab1_df), ("City Category", _tab2_df), ("City Level", _tab3_df)]:
            try:
                _val_ws = _val_ss.worksheet(_tab_name)
            except Exception:
                _val_ws = _val_ss.add_worksheet(title=_tab_name, rows=5000, cols=50)
            _val_ws.clear()
            set_with_dataframe(_val_ws, _tab_df)
            try:
                _apply_sheet_formatting(_val_ss, _val_ws, _tab_df)
                print(f"[Validation] '{_tab_name}' written & formatted: {len(_tab_df):,} rows")
            except Exception as _fmt_err:
                print(f"[Validation] '{_tab_name}' written but formatting failed: {_fmt_err}")

        print("[Validation] All comparison tabs updated successfully.")

    except Exception as _val_err:
        print(f"[Validation] ERROR: {_val_err}")
        import traceback as _tb2
        print(_tb2.format_exc())

# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%


# %%
# def fast_smooth_all_weeks(pivot_df, weeks, threshold_multiplier=1.0, cutoff_count=1):
#     weeks_sorted = sorted(map(int, weeks))  # ensure weeks are in order
    
#     for i, target_week in enumerate(weeks_sorted):
#         current_col = f'avl_corrected_sales_{target_week}'
#         history_weeks = weeks_sorted[:i]
#         history_cols = [f'avl_corrected_sales_{w}' for w in history_weeks if f'avl_corrected_sales_{w}' in pivot_df.columns]
#         left_cols = [f'avl_corrected_sales_{w}' for w in weeks_sorted[:i+1] if f'avl_corrected_sales_{w}' in pivot_df.columns]

#         # Skip if the current column doesn't exist
#         if current_col not in pivot_df.columns:
#             continue

#         # Step 1: Calculate history mean (excluding 0s)
#         history_vals = pivot_df[history_cols].replace(0, np.nan)
#         avg_vals = history_vals.mean(axis=1).fillna(0)

#         # Step 2: Get current week's values
#         current_vals = pivot_df[current_col]

#         # Step 3: Count non-zero values from left
#         non_zero_count = (pivot_df[left_cols] > 0).sum(axis=1)

#         # Step 4: Conditions
#         is_too_many_nonzero = non_zero_count > cutoff_count
#         is_outlier = abs(current_vals - avg_vals) > (threshold_multiplier * avg_vals)

#         # Step 5: Apply smoothing logic
#         smoothed_col = f'smoothed_sales_{target_week}'
#         pivot_df[smoothed_col] = np.where(
#             is_too_many_nonzero,
#             0,
#             np.where(is_outlier, avg_vals.round(0), current_vals)
#         )



# %%
# history_weeks.to_clipboard()

# %%


# %%


# %%
# pivot_df.to_clipboard()

# # %%
# fast_smooth_all_weeks(pivot_df, weeks, threshold_multiplier=1.0, cutoff_count=1)

# # %%
# latest_week = max(map(int, weeks))
# weeks_sorted = sorted(map(int, weeks))

# for week in weeks_sorted:
#     if week >= latest_week - 1:
#         fast_smooth_week(pivot_df, week, weeks_sorted)


# # %%
# pivot_df.to_clipboard()

# %%