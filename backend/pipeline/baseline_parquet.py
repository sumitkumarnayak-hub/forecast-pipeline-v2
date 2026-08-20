#%%
import os
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyreadr
import pandas as pd
import numpy as np 
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe
import glob as _glob
import io
import zipfile
import threading
from google_auth import client
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from config_paths import (
    JSON_KEYFILE_PATH,
    DRIVE_FOLDER_ID,
    RAW_DATA_DRIVE_FOLDER_ID,
    BASELINE_DRIVE_PARQUET_FOLDER_ID,
    BASELINE_OUTPUT_PARQUET_FOLDER_ID,
    BASELINE_OUTPUT_EXCEL_FOLDER_ID,
    BASELINE_CURRENT_FORECASTING_DIR,
    BASELINE_WEEKLY_PLAN_PATH,
    HUB_LEVEL_PLAN_CSV_PATH,
    GOOGLE_CREDENTIALS_DICT,
)

def load_latest_parquet_from_drive(sheet_key: str, folder_id: str = DRIVE_FOLDER_ID) -> pd.DataFrame:
    """
    Connects to Google Drive, searches the specified folder
    for files matching '{sheet_key}_*.parquet', sorts them by name descending,
    downloads it in-memory, and returns a pandas DataFrame.
    """
    scopes = ['https://www.googleapis.com/auth/drive.readonly']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS_DICT, scopes)
    service = build('drive', 'v3', credentials=creds)
    
    query = f"'{folder_id}' in parents and name contains '{sheet_key}' and name contains '.parquet' and trashed = false"
    
    results = service.files().list(
        q=query,
        pageSize=100,
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        corpora='allDrives'
    ).execute()
    files = results.get('files', [])
    
    if not files:
        raise FileNotFoundError(f"No parquet files found for key: {sheet_key} in folder {folder_id}")
    
    files_sorted = sorted(files, key=lambda x: x['name'], reverse=True)
    target_file = files_sorted[0]
    print(f"[Drive Parquet Loader] Loading latest file: {target_file['name']} ({target_file['id']})")
    
    request = service.files().get_media(fileId=target_file['id'])
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        _, done = downloader.next_chunk()
    
    fh.seek(0)
    return pd.read_parquet(fh)

def upload_df_to_drive_as_parquet(df: pd.DataFrame, file_name: str, folder_id: str):
    try:
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS_DICT, scopes)
        service = build('drive', 'v3', credentials=creds)
        query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='allDrives'
        ).execute()
        files = results.get('files', [])
        for f in files:
            print(f"[Drive Uploader] Deleting existing file to overwrite: {f['name']} ({f['id']})")
            try:
                service.files().delete(fileId=f['id'], supportsAllDrives=True).execute()
            except Exception as del_err:
                print(f"[Drive Uploader] WARNING: Could not delete {f['name']}: {del_err}")
        fh = io.BytesIO()
        df.to_parquet(fh, index=False)
        fh.seek(0)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(fh, mimetype="application/octet-stream", resumable=True)
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name',
            supportsAllDrives=True
        ).execute()
        print(f"[Drive Uploader] SUCCESS: Uploaded {uploaded_file.get('name')} to Drive (ID: {uploaded_file.get('id')})")
    except Exception as e:
        print(f"[Drive Uploader] ERROR uploading {file_name}: {e}")

def upload_df_to_drive_as_parquet_async(df: pd.DataFrame, file_name: str, folder_id: str):
    t = threading.Thread(target=upload_df_to_drive_as_parquet, args=(df, file_name, folder_id))
    t.daemon = False
    t.start()
    print(f"[Drive Uploader] Started background upload for {file_name}...")

def upload_df_to_drive_as_zip_csv(df: pd.DataFrame, file_name: str, folder_id: str, csv_name: str, header: bool = True):
    try:
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS_DICT, scopes)
        service = build('drive', 'v3', credentials=creds)
        query = f"'{folder_id}' in parents and name = '{file_name}' and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora='allDrives'
        ).execute()
        files = results.get('files', [])
        for f in files:
            print(f"[Drive Uploader] Deleting existing file to overwrite: {f['name']} ({f['id']})")
            try:
                service.files().delete(fileId=f['id'], supportsAllDrives=True).execute()
            except Exception as del_err:
                print(f"[Drive Uploader] WARNING: Could not delete {f['name']}: {del_err}")
                
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False, header=header)
        csv_data = csv_buffer.getvalue().encode('utf-8')
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr(csv_name, csv_data)
        zip_buffer.seek(0)
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(zip_buffer, mimetype="application/zip", resumable=True)
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name',
            supportsAllDrives=True
        ).execute()
        print(f"[Drive Uploader] SUCCESS: Uploaded {uploaded_file.get('name')} to Drive (ID: {uploaded_file.get('id')})")
    except Exception as e:
        print(f"[Drive Uploader] ERROR uploading {file_name}: {e}")


def normalize_p_master_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility shim for legacy and current p_master exports."""
    df = df.copy()

    if "Product id" in df.columns and "product_id" in df.columns:
        df = df.rename(columns={"Product id": "_legacy_product_id"})
        df["product_id"] = df["product_id"].map(lambda x: "" if pd.isna(x) else str(x).strip())
        df["_legacy_product_id"] = df["_legacy_product_id"].map(lambda x: "" if pd.isna(x) else str(x).strip())
        df["product_id"] = df["product_id"].fillna(df["_legacy_product_id"])
        df = df.drop(columns=["_legacy_product_id"])
    elif "Product id" in df.columns:
        df = df.rename(columns={"Product id": "product_id"})

    if "Sub-category" in df.columns and "sub category" in df.columns:
        df["Sub-category"] = df["Sub-category"].fillna(df["sub category"])
        df = df.drop(columns=["sub category"])
    elif "sub category" in df.columns:
        df = df.rename(columns={"sub category": "Sub-category"})

    if "Avl Flag" in df.columns and "Avl_Flag" in df.columns:
        df = df.rename(columns={"Avl Flag": "_legacy_avl_flag"})
        df["Avl Flag"] = df["Avl Flag"].fillna(df["_legacy_avl_flag"])
        df = df.drop(columns=["_legacy_avl_flag"])
    elif "Avl_Flag" in df.columns:
        df = df.rename(columns={"Avl_Flag": "Avl Flag"})

    if "Category" in df.columns and "category" in df.columns:
        df["Category"] = df["Category"].fillna(df["category"])
        df = df.drop(columns=["category"])
    elif "category" in df.columns:
        df = df.rename(columns={"category": "Category"})
    elif "Sub-category" in df.columns and "Category" not in df.columns:
        df["Category"] = df["Sub-category"]

    if "product_id" in df.columns:
        df["product_id"] = df["product_id"].map(lambda x: "" if pd.isna(x) else str(x).strip())

    return df

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous: Read local CSV file from 'BASELINE_RAW_DATA_PATH' ('Raw_data.csv')
# Current: Loaded directly from Google Drive ('Raw_data.parquet') from folder ID RAW_DATA_DRIVE_FOLDER_ID
logging.info("Starting Baseline Parquet step...")
logging.info("Loading Raw_data parquet...")
main_df = load_latest_parquet_from_drive("Raw_data", RAW_DATA_DRIVE_FOLDER_ID)

# Keep logic identical while normalizing real schema variations from p_master exports.
# This is a compatibility shim only; it does not change business rules.

main_df = main_df.rename(columns={
    'Sub-category':                  'sub category',
    'week':                          'Week',
    'sku class prod':                'SKU Class Prod',
    'final_sales':                   'Sales (qty)',
    'final_sales_withoutclusterv2':  'Sales_withoutclusterv2 (qty)',
})

# Rename all columns: _grp_ -> _group_  (e.g. simple_grp_flag -> simple_group_flag)
main_df.columns = main_df.columns.str.replace('_grp_', '_group_', regex=False)

# =============================================================================
# AVL FLAG - Data Loading
# =============================================================================
# %%

# =============================================================================
# =============================================================================

# %% # Load Hub changes from parquet
hub_changes_df = load_latest_parquet_from_drive("ff_input")

# Display the data
print("Hub Changes Data:")
print(hub_changes_df)

# =============================================================================
# CLUSTER PHASE 2 - Data Loading + Processing
# =============================================================================
# %%
# Load cluster phase 2 mapping from parquet
cluster_mapping_df = load_latest_parquet_from_drive("cluster_v2")

# Read P master (ATB) sheet and override sub category in main_df
# Canonicalize legacy/current column names without altering the underlying logic.
p_master_df = normalize_p_master_columns(load_latest_parquet_from_drive("p_master"))

if "product_id" not in p_master_df.columns:
    raise KeyError("The p_master parquet does not contain a 'product_id' column.")

p_master_map = (
    p_master_df[["product_id", "Sub-category"]]
    .drop_duplicates(subset="product_id")
    .set_index("product_id")["Sub-category"]
)
main_df["sub category"] = (
    main_df["product_id"].astype(str).map(p_master_map).fillna(main_df["sub category"])
)

# Load Avl Flag from its dedicated parquet file
avl_flag_raw = normalize_p_master_columns(load_latest_parquet_from_drive("Avl_Flag"))

avl_flag_cols = ["product_id", "Avl Flag"]
for extra_col in ["Sub-category", "Category"]:
    if extra_col in avl_flag_raw.columns:
        avl_flag_cols.append(extra_col)

if "Avl Flag" in avl_flag_raw.columns and "product_id" in avl_flag_raw.columns:
    avl_flag_df = avl_flag_raw[avl_flag_cols].drop_duplicates(subset="product_id", keep="first").copy()
else:
    missing = set(["product_id", "Avl Flag"]) - set(avl_flag_raw.columns)
    raise KeyError(f"Avl_Flag parquet is missing required columns for baseline logic: {sorted(missing)}")

# %%
cluster_mapping_df["Cluster_Flag"] = cluster_mapping_df["Cluster_Flag"].astype(int)
cluster_mapping_df = cluster_mapping_df[cluster_mapping_df["Cluster_Flag"] == 1]


# %%
# =============================================================================
# BUILD UNIFIED _withoutclusterv2 COLUMNS  (original columns are NOT modified)
#
# The 5 _withoutclusterv2 columns become fully-populated unified series:
#    Before May 18 (all SKUs)          -> copy from original Sales (qty) / simple_*
#    On/after May 18, cluster SKU      -> copy from original Sales (qty) / simple_*
#    On/after May 18, non-cluster SKU  -> keep the existing _withoutclusterv2 values
#
# All downstream processing uses the _withoutclusterv2 column names.
# =============================================================================

CLUSTER_CUTOFF_DATE = pd.Timestamp("2026-05-18")

# Build set of all cluster (product_id, hub_name) pairs  both child hubs and mother hubs
_cluster_child_pairs = set(
    zip(
        cluster_mapping_df["product_id"].astype(str),
        cluster_mapping_df["childHub_name"].astype(str),
    )
)
_cluster_mother_pairs = set(
    zip(
        cluster_mapping_df["product_id"].astype(str),
        cluster_mapping_df["MotherHub_name"].astype(str),
    )
)
_all_cluster_pairs = _cluster_child_pairs | _cluster_mother_pairs

# Ensure process_dt is datetime for the date comparison
main_df["process_dt"] = pd.to_datetime(main_df["process_dt"], errors="coerce")

# Mask 1: rows on or after the cutoff date
_after_cutoff_mask = main_df["process_dt"] >= CLUSTER_CUTOFF_DATE

# Mask 2: rows whose (product_id, hub_name) pair is a cluster member
_is_cluster_mask = pd.Series(
    [
        (str(pid), str(hub)) in _all_cluster_pairs
        for pid, hub in zip(main_df["product_id"], main_df["hub_name"])
    ],
    index=main_df.index,
    dtype=bool,
)

# Rows that should keep original values in the unified column:
# either before the cutoff OR a cluster member
_fill_from_original_mask = ~_after_cutoff_mask | _is_cluster_mask

# Column mapping: original column -> unified _withoutclusterv2 column
_wc_col_map = {
    "Sales (qty)":                    "Sales_withoutclusterv2 (qty)",
    "simple_flag_when_SP_0":          "simple_flag_when_SP_0_withoutclusterv2",
    "simple_instances_when_SP_0":     "simple_instances_when_SP_0_withoutclusterv2",
    "simple_group_flag_when_SP_0":      "simple_group_flag_when_SP_0_withoutclusterv2",
    "simple_group_instances_when_SP_0": "simple_group_instances_when_SP_0_withoutclusterv2",
}

for _std_col, _wc_col in _wc_col_map.items():
    # Create the column if it doesn't exist yet (rows from file_path / file_path_1)
    if _wc_col not in main_df.columns:
        main_df[_wc_col] = np.nan
    # For before-cutoff rows and cluster rows: fill the unified column from the original
    main_df.loc[_fill_from_original_mask, _wc_col] = main_df.loc[_fill_from_original_mask, _std_col]
    # For non-cluster rows on/after cutoff: keep existing _withoutclusterv2 values where available.
    # If still NaN (row came from a file without _withoutclusterv2 columns e.g. file_path_1),
    # fall back to the original column value.
    _nan_fallback_mask = ~_fill_from_original_mask & main_df[_wc_col].isna()
    main_df.loc[_nan_fallback_mask, _wc_col] = main_df.loc[_nan_fallback_mask, _std_col]

print(
    f"[WC unified columns] Before cutoff (original): {(~_after_cutoff_mask).sum()}, "
    f"Cluster on/after cutoff (original): {(_after_cutoff_mask & _is_cluster_mask).sum()}, "
    f"Non-cluster on/after cutoff (withoutclusterv2 or fallback to original if NaN): {(_after_cutoff_mask & ~_is_cluster_mask).sum()}"
)


# %%
agg_cols = [
    "Sales_withoutclusterv2 (qty)",
    "simple_flag_when_SP_0_withoutclusterv2", "simple_instances_when_SP_0_withoutclusterv2",
    "simple_group_flag_when_SP_0_withoutclusterv2", "simple_group_instances_when_SP_0_withoutclusterv2"
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
    "simple_flag_when_SP_0_withoutclusterv2",
    "simple_instances_when_SP_0_withoutclusterv2",
    "simple_group_flag_when_SP_0_withoutclusterv2",
    "simple_group_instances_when_SP_0_withoutclusterv2"
]

for col in cols_to_multiply:
    valid_mask = child_rows[col].notna() & child_rows["Sales_withoutclusterv2 (qty)"].notna()

    # Case 1: Sales > 0 -> multiply by Sales
    mask_sales_pos = valid_mask & (child_rows["Sales_withoutclusterv2 (qty)"] > 0)
    child_rows.loc[mask_sales_pos, col] = (
        child_rows.loc[mask_sales_pos, col] * child_rows.loc[mask_sales_pos, "Sales_withoutclusterv2 (qty)"]
    )

    # Case 2: Sales == 0 -> multiply by 1 only for specific columns
    if col in ["simple_group_instances_when_SP_0_withoutclusterv2", "simple_instances_when_SP_0_withoutclusterv2"]:
        mask_sales_zero = valid_mask & (child_rows["Sales_withoutclusterv2 (qty)"] == 0)
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
    "Sales_withoutclusterv2 (qty)": "Agg_sale_mother_hub",
    "simple_flag_when_SP_0_withoutclusterv2": "Agg_simple_flag",
    "simple_instances_when_SP_0_withoutclusterv2": "Agg_simple_instances",
    "simple_group_flag_when_SP_0_withoutclusterv2": "Agg_simple_grp_flag",
    "simple_group_instances_when_SP_0_withoutclusterv2": "Agg_simple_grp_instances"
})

# %%
key_cols = ["process_dt", "hub_name", "product_id"]

# Create an indicator to mark rows that exist in child_rows
main_df["is_child"] = main_df[key_cols].merge(
    child_rows[key_cols].drop_duplicates(), 
    on=key_cols, 
    how="left", 
    indicator=True
)["_merge"].eq("both")

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
    "simple_flag_when_SP_0_withoutclusterv2",
    "simple_instances_when_SP_0_withoutclusterv2",
    "simple_group_flag_when_SP_0_withoutclusterv2",
    "simple_group_instances_when_SP_0_withoutclusterv2"
]

for col in cols_to_multiply:
    valid_mask = mask & final_df[col].notna() & final_df["Sales_withoutclusterv2 (qty)"].notna()

    # Case 1: Sales > 0 -> multiply by actual sales
    mask_sales_pos = valid_mask & (final_df["Sales_withoutclusterv2 (qty)"] > 0)
    final_df.loc[mask_sales_pos, col] = (
        final_df.loc[mask_sales_pos, col] * final_df.loc[mask_sales_pos, "Sales_withoutclusterv2 (qty)"]
    )

    # Case 2: Sales == 0 -> multiply by 1 for simple_flag and simple_instances only
    if col in ["simple_group_instances_when_SP_0_withoutclusterv2", "simple_instances_when_SP_0_withoutclusterv2"]:
        mask_sales_zero = valid_mask & (final_df["Sales_withoutclusterv2 (qty)"] == 0)
        final_df.loc[mask_sales_zero, col] = (
            final_df.loc[mask_sales_zero, col] * 1
        )


# %%
for col in ["Agg_sale_mother_hub", "Agg_simple_flag", "Agg_simple_instances",
            "Agg_simple_grp_flag", "Agg_simple_grp_instances"]:
    final_df[col] = final_df[col].fillna(0)


# %%
final_df["Sales_withoutclusterv2 (qty)"] += final_df["Agg_sale_mother_hub"]
final_df["simple_flag_when_SP_0_withoutclusterv2"] += final_df["Agg_simple_flag"]
final_df["simple_instances_when_SP_0_withoutclusterv2"] += final_df["Agg_simple_instances"]
final_df["simple_group_flag_when_SP_0_withoutclusterv2"] += final_df["Agg_simple_grp_flag"]
final_df["simple_group_instances_when_SP_0_withoutclusterv2"] += final_df["Agg_simple_grp_instances"]

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
    "Agg_simple_grp_flag", "Agg_simple6w_grp_instances",
    "Unnamed: 19", "Unnamed: 20"
], errors="ignore")

# %%
# Reuse already loaded avl_flag_df from the top of the file

# %%
merged_df = final_df.merge(
    avl_flag_df[['product_id', 'Avl Flag']],
    how='left',
    on='product_id'
)

#%%


# %%
# Drop rows where sub category is blank/NaN  these have no Avl Flag and can't be processed
merged_df = merged_df[merged_df['sub category'].notna() & (merged_df['sub category'].astype(str).str.strip() != '')]

# %%
# Avl Flag comes in as string from Google Sheets  cast to int before comparisons
merged_df['Avl Flag'] = pd.to_numeric(merged_df['Avl Flag'], errors='coerce').fillna(0).astype(int)

# %%
merged_df['simple_avail_num'] = np.where(
    merged_df['Avl Flag'] == 1,
    merged_df['simple_flag_when_SP_0_withoutclusterv2'],
    merged_df['simple_group_flag_when_SP_0_withoutclusterv2']
)

# %%
merged_df['simple_avail_den'] = np.where(
    merged_df['Avl Flag'] == 1,
    merged_df['simple_instances_when_SP_0_withoutclusterv2'],
    merged_df['simple_group_instances_when_SP_0_withoutclusterv2']
)


# %%
merged_df['simple_avail_num'] = merged_df['simple_avail_num'].fillna(0)

# %%
merged_df['simple_avail_den'] = merged_df['simple_avail_den'].fillna(0)

# %%
merged_df['simple_availability'] = np.where(
    (merged_df['simple_avail_num'] == 0) & (merged_df['simple_avail_den'] == 0),
    0,
    np.where(
        (merged_df['simple_avail_num'] == 0) | (merged_df['simple_avail_den'] == 0),
        0,
        (merged_df['simple_avail_num'] / merged_df['simple_avail_den']) * 100
    )
)


# %%
merged_df['simple_availability'] = merged_df['simple_availability'].fillna(0)

# %%
merged_df.to_csv(HUB_LEVEL_PLAN_CSV_PATH, index=False)


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
# Load Hub Changes Data from parquet source only
# -----------------------------------------------------------------------------
# This script already loads the Drive parquet source earlier in the file:
#   hub_changes_df = load_latest_parquet_from_drive("ff_input")
# We intentionally do not read Google Sheets here anymore.

hub_changes_df = hub_changes_df.copy()

# Display the data
print("Hub Changes Data:")
print(hub_changes_df)

# %%
required_cols = ['city_name','Type', 'Hub_name', 'Source_Hub', 'Hub_id', 'Percentage', 'Start_date', 'End_date']
missing_cols = [col for col in required_cols if col not in hub_changes_df.columns]


if missing_cols:
    raise ValueError(f"Missing required columns in Hub_Changes sheet: {missing_cols}")

# Convert all numeric-looking columns in merged_df
num_cols = ["Sales_withoutclusterv2 (qty)", "simple_avail_num", "simple_avail_den"]

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
            pre_launch_volume = pre_launch_records['Sales_withoutclusterv2 (qty)'].sum()
            
            # Ignore pre-launch data - remove it from merged_df
            print(f"  [!] {hub} has {len(pre_launch_records):,} records BEFORE launch date {launch_date.date()}")
            print(f"     Pre-launch volume: {pre_launch_volume:.2f}")
            print(f"     [->] Ignoring pre-launch data (will be replaced with virtual history)")
            
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
virtual_history_list = []

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
            print(f"    [!]  Warning: No data found for source hub {source_hub}")
            continue
        
        # Show source hub details
        source_volume_before = source_data['Sales_withoutclusterv2 (qty)'].sum()
        source_records = len(source_data)
        print(f"    Source data: {source_records:,} records, Volume: {source_volume_before:.2f}")
        
        # ---------------------------------------------------------------------
        # Create Virtual History
        # ---------------------------------------------------------------------
        if idx == 0:
            # FIRST source hub: Replicate ALL line items
            virtual_history_hub = source_data.copy()
            
            # Scale volumes by percentage
            volume_before_scaling = virtual_history_hub['Sales_withoutclusterv2 (qty)'].sum()
            scale_cols = ["Sales_withoutclusterv2 (qty)"]
            for col in scale_cols:
                if col in virtual_history_hub.columns:
                    virtual_history_hub[col] = virtual_history_hub[col] * percentage
            
            volume_after_scaling = virtual_history_hub['Sales_withoutclusterv2 (qty)'].sum()
            
            # Update hub_name to target hub
            virtual_history_hub['hub_name'] = target_hub
            
            virtual_history_list.append(virtual_history_hub)
            print(f"    [OK] Created {len(virtual_history_hub):,} virtual history records for {target_hub}")
            print(f"      Volume calculation: {volume_before_scaling:.2f}  {percentage} = {volume_after_scaling:.2f}")
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
                    volume_before_scaling = matching_source_data['Sales_withoutclusterv2 (qty)'].sum()
                    
                    # Scale volumes
                    for col in ["Sales_withoutclusterv2 (qty)"]:
                        if col in matching_source_data.columns:
                            matching_source_data[col] = matching_source_data[col] * percentage
                    
                    volume_after_scaling = matching_source_data['Sales_withoutclusterv2 (qty)'].sum()
                    
                    # Update hub_name
                    matching_source_data['hub_name'] = target_hub
                    
                    virtual_history_list.append(matching_source_data)
                    print(f"    [OK] Added volumes for {len(matching_source_data):,} matching product records")
                    print(f"      Volume calculation: {volume_before_scaling:.2f}  {percentage} = {volume_after_scaling:.2f}")
                    print(f"    [OK] Volume transferred to {target_hub}: {volume_after_scaling:.2f}")
                else:
                    print(f"    [i]  No matching products found between {source_hub} and {target_hub}")
        
        # ---------------------------------------------------------------------
        # Reduce Source Hub Volumes
        # ---------------------------------------------------------------------
        source_mask = (merged_df['hub_name'] == source_hub) & date_mask
        
        # Get volume before reduction
        volume_before_reduction = merged_df.loc[source_mask, 'Sales_withoutclusterv2 (qty)'].sum()
        
        for col in ["Sales_withoutclusterv2 (qty)"]:
            if col in merged_df.columns:
                merged_df.loc[source_mask, col] = merged_df.loc[source_mask, col] * (1 - percentage)
        
        # Get volume after reduction
        volume_after_reduction = merged_df.loc[source_mask, 'Sales_withoutclusterv2 (qty)'].sum()
        volume_reduced = volume_before_reduction - volume_after_reduction
        
        print(f"    [OK] Reduced source hub {source_hub} by {percentage*100:.1f}%")
        print(f"      Volume calculation: {volume_before_reduction:.2f}  (1 - {percentage}) = {volume_after_reduction:.2f}")
        print(f"      Volume reduced: {volume_reduced:.2f}")

# %%
# -----------------------------------------------------------------------------
# Aggregate Virtual History (if multiple sources contributed to same records)
# -----------------------------------------------------------------------------
if virtual_history_list:
    virtual_history = pd.concat(virtual_history_list, ignore_index=True)
    
    # Group and aggregate to combine volumes from multiple sources
    group_cols = [
        "process_dt", "sub category", "Week", "day", "product_id", "product_name",
        "SKU Class Prod", "city_name", "hub_name",
        "simple_flag_when_SP_0_withoutclusterv2", "simple_instances_when_SP_0_withoutclusterv2",
        "simple_group_flag_when_SP_0_withoutclusterv2", "simple_group_instances_when_SP_0_withoutclusterv2",
        "Avl Flag"
    ]
    
    agg_dict = {"Sales_withoutclusterv2 (qty)": "sum"}
    if "simple_avail_num" in virtual_history.columns:
        agg_dict["simple_avail_num"] = "sum"
    if "simple_avail_den" in virtual_history.columns:
        agg_dict["simple_avail_den"] = "sum"
    
    virtual_history = virtual_history.groupby(group_cols, as_index=False).agg(agg_dict)
    
    # Recalculate availability
    if "simple_avail_num" in virtual_history.columns and "simple_avail_den" in virtual_history.columns:
        virtual_history["simple_availability"] = (
            virtual_history["simple_avail_num"] / virtual_history["simple_avail_den"]
        )
    
    # Align columns with merged_df
    virtual_history_aligned = virtual_history.reindex(columns=merged_df.columns)
    
    print(f"\nTotal virtual history records created: {len(virtual_history_aligned)}")
else:
    virtual_history_aligned = pd.DataFrame(columns=merged_df.columns)
    print("\nNo virtual history created")

# %%
merged_df = pd.concat([merged_df, virtual_history_aligned], ignore_index=True)
# =============================================================================
# PROCESS KML REMAPPING
# =============================================================================
# Group rows by (Source_Hub, Start_date, End_date) so that when multiple
# target hubs draw from the same source on the same dates, all percentages
# are applied against the ORIGINAL source volume (not the progressively
# reduced one). Within each group we:
#   1. Snapshot the original source volumes once.
#   2. Transfer each target's share from the snapshot.
#   3. Write back the fully-reduced source volume once at the end.

def _build_date_mask(df, start_date, end_date):
    if pd.notna(start_date) and pd.notna(end_date):
        if start_date == end_date:
            return df['process_dt'] < end_date
        else:
            return (df['process_dt'] >= start_date) & (df['process_dt'] <= end_date)
    return df['process_dt'].notna()

for (source_hub, start_date, end_date), group in kml_remapping_changes.groupby(
    ['Source_Hub', 'Start_date', 'End_date'], dropna=False
):
    date_mask = _build_date_mask(merged_df, start_date, end_date)
    source_mask = (merged_df['hub_name'] == source_hub) & date_mask

    # Snapshot original source volumes ONCE for the entire group
    original_source = merged_df[source_mask].copy()

    if original_source.empty:
        for _, row in group.iterrows():
            print(f"\nProcessing KML Remapping: {source_hub} -> {row['Hub_name']} ({row['Percentage']*100:.1f}%)")
            print(f"  [!]  No source data found for {source_hub}")
        continue

    total_percentage = group['Percentage'].sum()
    original_source_volume = original_source['Sales_withoutclusterv2 (qty)'].sum()

    print(f"\n{'='*60}")
    print(f"KML Remapping Group: Source = {source_hub} | Dates: {start_date} to {end_date}")
    print(f"  Original source volume : {original_source_volume:.2f}")
    print(f"  Target hubs            : {group['Hub_name'].tolist()}")
    print(f"  Percentages            : {group['Percentage'].tolist()} (total = {total_percentage:.2f})")
    if total_percentage > 1.0:
        print(f"  [!]  WARNING: Total percentage {total_percentage:.2f} > 1.0  source will go negative!")

    merge_key = ['process_dt', 'product_id']

    for _, row in group.iterrows():
        target_hub = row['Hub_name']
        percentage = row['Percentage']

        print(f"\n  Processing: {source_hub} -> {target_hub} ({percentage*100:.1f}%)")

        # Transfer amount always calculated from the ORIGINAL snapshot
        transfer_source = original_source.copy()
        transfer_source['transfer_amount'] = transfer_source['Sales_withoutclusterv2 (qty)'] * percentage
        total_transfer_amount = transfer_source['transfer_amount'].sum()

        target_mask = (merged_df['hub_name'] == target_hub) & date_mask
        target_data = merged_df[target_mask]

        if not target_data.empty:
            target_indexed = merged_df[target_mask].reset_index()

            transfer_map = transfer_source[merge_key + ['transfer_amount']].merge(
                target_indexed[merge_key + ['index']],
                on=merge_key,
                how='inner'
            )

            if not transfer_map.empty:
                indices_to_update = transfer_map['index'].values
                amounts_to_add = transfer_map['transfer_amount'].values
                merged_df.loc[indices_to_update, 'Sales_withoutclusterv2 (qty)'] += amounts_to_add

                total_transferred = transfer_map['transfer_amount'].sum()
                records_transferred = len(transfer_map)
                total_lost = total_transfer_amount - total_transferred
                records_lost = len(transfer_source) - records_transferred

                print(f"    [OK] Volume transferred to {target_hub}: {total_transferred:.2f} ({records_transferred:,} records)")
                if records_lost > 0:
                    print(f"    [!]  Volume lost (no matching target record): {total_lost:.2f} ({records_lost:,} records)")
            else:
                print(f"    [!]  No matching records found in target hub {target_hub}")
                print(f"    Volume lost: {total_transfer_amount:.2f} ({len(transfer_source):,} records)")
        else:
            print(f"    [!]  Target hub {target_hub} has no data in the specified date range")
            print(f"    Volume lost: {total_transfer_amount:.2f} ({len(transfer_source):,} records)")

    # Reduce source ONCE using the total percentage across all targets in the group
    merged_df.loc[source_mask, 'Sales_withoutclusterv2 (qty)'] = (
        merged_df.loc[source_mask, 'Sales_withoutclusterv2 (qty)'] * (1 - total_percentage)
    )
    final_source_volume = merged_df.loc[source_mask, 'Sales_withoutclusterv2 (qty)'].sum()
    print(f"\n  [OK] Source {source_hub} reduced by {total_percentage*100:.1f}% (total across all targets)")
    print(f"    Original: {original_source_volume:.2f}  ->  Final: {final_source_volume:.2f}")
    print(f"{'='*60}")

# %%
# -----------------------------------------------------------------------------
# Combine Original Data with Virtual History
# -----------------------------------------------------------------------------
final_df = merged_df.copy()

# %%
# -----------------------------------------------------------------------------
# Summary Statistics
# -----------------------------------------------------------------------------

print("HUB CHANGES PROCESSING COMPLETE")
merged_df.to_csv('Pandas_Hub_Changes.csv', index=False)

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
        hub_volume = final_df[final_df['hub_name'] == hub]['Sales_withoutclusterv2 (qty)'].sum()
        hub_records = len(final_df[final_df['hub_name'] == hub])
        print(f"    -> Total volume in final_df: {hub_volume:.2f} ({hub_records:,} records)")

if len(kml_remapping_changes) > 0:
    print(f"\nKML Remappings processed: {len(kml_remapping_changes)}")
    for _, row in kml_remapping_changes.iterrows():
        target_hub = row['Hub_name']
        source_hub = row['Source_Hub']
        
        # Show volume for this hub in final_df
        target_volume = final_df[final_df['hub_name'] == target_hub]['Sales_withoutclusterv2 (qty)'].sum()
        source_volume = final_df[final_df['hub_name'] == source_hub]['Sales_withoutclusterv2 (qty)'].sum()
        
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
    print(f"  WARNING: Found {len(duplicates)} duplicate hub-product-date records!")
    print("\nSample duplicates:")
    print(duplicates[['hub_name', 'product_id', 'process_dt', 'Sales_withoutclusterv2 (qty)']].head(10))
else:
    print("[OK] No duplicate hub-product-date combinations found")

# Check if new hubs have data from original merged_df (they shouldn't!)
if len(new_hub_changes) > 0:
    for hub in new_hub_changes['Hub_name'].unique():
        # Check if this hub appears in merged_df (it shouldn't after removal)
        hub_in_merged = merged_df[merged_df['hub_name'] == hub]
        if len(hub_in_merged) > 0:
            print(f"  WARNING: New Hub {hub} still has {len(hub_in_merged)} records in merged_df!")
            print(f"   This should be 0. Volume: {hub_in_merged['Sales_withoutclusterv2 (qty)'].sum():.2f}")

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
# ---- 1. Load Pure Preorder data (self-contained  preorder_df not yet set) --
preorder_raw_df = load_latest_parquet_from_drive("pure_preorder")
_po_raw = pd.DataFrame()
if len(preorder_raw_df.columns) >= 2:
    _po_raw['hub_name'] = preorder_raw_df.iloc[:, 0].astype(str).str.strip()
    _po_raw['SKU Class Prod'] = preorder_raw_df.iloc[:, 1].astype(str).str.strip()
else:
    _po_raw = pd.DataFrame(columns=['hub_name', 'SKU Class Prod'])
_po_raw['hub_name'] = _po_raw['hub_name'].astype(str).str.strip()

# ---- 2. Build exclusion sets ------------------------------------------------

# Pure Preorder: Hub  product_id (if available) else Hub  SKU Class Prod
if 'product_id' in _po_raw.columns:
    _po_raw['product_id'] = _po_raw['product_id'].astype(str).str.strip()
    _preorder_excl = set(zip(_po_raw['hub_name'], _po_raw['product_id']))
    _preorder_excl_col = 'product_id'
else:
    _po_raw['SKU Class Prod'] = _po_raw['SKU Class Prod'].astype(str).str.strip()
    _preorder_excl = set(zip(_po_raw['hub_name'], _po_raw['SKU Class Prod']))
    _preorder_excl_col = 'SKU Class Prod'

print(f"Pure Preorder exclusions: {len(_preorder_excl)} hub{_preorder_excl_col} combinations")

# Cluster v2: both Mother Hub  product_id and Child Hub  product_id
_cluster_excl = set()
if not cluster_mapping_df.empty:
    _cm = cluster_mapping_df[['product_id', 'childHub_name', 'MotherHub_name']].copy()
    _cm['product_id']     = _cm['product_id'].astype(str).str.strip()
    _cm['childHub_name']  = _cm['childHub_name'].astype(str).str.strip()
    _cm['MotherHub_name'] = _cm['MotherHub_name'].astype(str).str.strip()
    _cluster_excl |= set(zip(_cm['childHub_name'],  _cm['product_id']))
    _cluster_excl |= set(zip(_cm['MotherHub_name'], _cm['product_id']))

print(f"Cluster v2 exclusions   : {len(_cluster_excl)} hubproduct_id combinations")

# ---- 3. Working copy of final_df (pre-outlier correction) ------------------

ci_df = final_df.copy()
ci_df['hub_name']   = ci_df['hub_name'].astype(str).str.strip()
ci_df['product_id'] = ci_df['product_id'].astype(str).str.strip()

# Exclude Pure Preorder
_po_key = list(zip(ci_df['hub_name'], ci_df[_preorder_excl_col].astype(str).str.strip()))
ci_df = ci_df[~pd.Series(_po_key, index=ci_df.index).isin(_preorder_excl)]

# Exclude Cluster v2
_cl_key = list(zip(ci_df['hub_name'], ci_df['product_id']))
ci_df = ci_df[~pd.Series(_cl_key, index=ci_df.index).isin(_cluster_excl)]

print(f"Records after exclusions: {len(ci_df):,}  (original final_df: {len(final_df):,})")

# ---- 4. Restrict to last 4 fully completed weeks (MonSun already passed) --

_today_dt = pd.Timestamp.today().normalize()

# For each Week, pick any date from that week and derive its Sunday
_week_end_map = (
    ci_df.dropna(subset=['Week', 'process_dt'])
    .groupby('Week')['process_dt']
    .first()
    .reset_index()
)
_week_end_map['week_sunday'] = _week_end_map['process_dt'].apply(
    lambda d: d + pd.Timedelta(days=(6 - d.weekday()))  # Mon=0  Sun=6
)

# Max date actually present in the data for each week
_week_max_date = (
    ci_df.groupby('Week')['process_dt']
    .max()
    .reset_index()
    .rename(columns={'process_dt': 'max_date'})
)
_week_end_map = _week_end_map.merge(_week_max_date, on='Week', how='left')

# A week is complete only if:
#   1. Its calendar Sunday is before today (week has ended), AND
#   2. The data for that week reaches its Sunday (no missing tail days)
_complete_weeks = (
    _week_end_map.loc[
        (_week_end_map['week_sunday'] < _today_dt) &
        (_week_end_map['max_date']    >= _week_end_map['week_sunday']),
        'Week'
    ]
    .tolist()
)
_last_4_weeks = sorted(_complete_weeks)[-4:]

if len(_last_4_weeks) < 4:
    print(f"  Only {len(_last_4_weeks)} complete week(s) available: {_last_4_weeks}")
else:
    print(f"Last 4 complete weeks   : {_last_4_weeks}")

ci_df = ci_df[ci_df['Week'].isin(_last_4_weeks)].copy()

# ---- 5. Row-level availability numerator/denominator -----------------------
# Fresh Water & Sea water -> group-level flags; all others -> simple (non-group)

_FRESH_SEA = ['Fresh Water', 'Sea water']
_is_fw_sw = ci_df['sub category'].isin(_FRESH_SEA)

ci_df['_avail_num'] = np.where(
    _is_fw_sw,
    pd.to_numeric(ci_df['simple_group_flag_when_SP_0_withoutclusterv2'],      errors='coerce').fillna(0),
    pd.to_numeric(ci_df['simple_flag_when_SP_0_withoutclusterv2'],            errors='coerce').fillna(0),
)
ci_df['_avail_den'] = np.where(
    _is_fw_sw,
    pd.to_numeric(ci_df['simple_group_instances_when_SP_0_withoutclusterv2'], errors='coerce').fillna(0),
    pd.to_numeric(ci_df['simple_instances_when_SP_0_withoutclusterv2'],       errors='coerce').fillna(0),
)

# Wastage quantity
ci_df['_wastage_qty'] = (
    pd.to_numeric(ci_df['wastage_qty_Quality'], errors='coerce').fillna(0) +
    pd.to_numeric(ci_df['wastage_qty_Expiry'],  errors='coerce').fillna(0)
)

# ---- 6. Aggregate at Hub  SKU Class Prod  Week --------------------------

_week_agg = ci_df.groupby(['hub_name', 'SKU Class Prod', 'Week'], as_index=False).agg(
    vol_bucket  = ('Sales_withoutclusterv2 (qty)', 'sum'),
    r7_plan_sum = ('r7_plan',                      'sum'),
    avail_num   = ('_avail_num',                   'sum'),
    avail_den   = ('_avail_den',                   'sum'),
    wastage_qty = ('_wastage_qty',                 'sum'),
    sales_wc    = ('Sales_withoutclusterv2 (qty)', 'sum'),
)

# ---- 7. Compute ratios -----------------------------------------------------

_week_agg['attainment']   = np.where(_week_agg['r7_plan_sum'] > 0,
                                      _week_agg['vol_bucket']  / _week_agg['r7_plan_sum'], np.nan)
_week_agg['availability'] = np.where(_week_agg['avail_den'] > 0,
                                      _week_agg['avail_num']   / _week_agg['avail_den'],   np.nan)
_week_agg['wastage_pct']  = np.where(_week_agg['sales_wc']  > 0,
                                      _week_agg['wastage_qty'] / _week_agg['sales_wc'],    np.nan)

# ---- 8. Flag weeks that meet ALL conditions --------------------------------
# Thresholds are read live from Google Sheet: "Consistent Issues Logic" tab.
# Sheet layout:
#   Row 3 = Rev Loss  | Cols B,C,D,E = Attainment, Availability, Wastage%, Vol Bucket
#   Row 5 = Wastage   | Cols B,C,D,E = Attainment, Availability, Wastage%, Vol Bucket

def _parse_threshold(raw: str):
    """Parse a threshold string like '>95%' or '<=30' into (operator, float).
    Raises ValueError if the string is empty, '-', or otherwise unparseable."""
    s = str(raw).strip()
    if not s or s == '-':
        raise ValueError(
            f"Threshold value '{raw}' in 'Consistent Issues Logic' sheet is blank or "
            f"placeholder ('-'). Please fill in a valid threshold (e.g. '>95%')."
        )
    if s.startswith('>='):
        op, num_str = '>=', s[2:]
    elif s.startswith('<='):
        op, num_str = '<=', s[2:]
    elif s.startswith('>'):
        op, num_str = '>', s[1:]
    elif s.startswith('<'):
        op, num_str = '<', s[1:]
    else:
        raise ValueError(
            f"Cannot parse operator from threshold '{raw}'. "
            f"Expected one of: >, <, >=, <=."
        )
    num_str = num_str.strip().rstrip('%')
    try:
        num = float(num_str)
    except ValueError:
        raise ValueError(
            f"Cannot parse numeric value from threshold '{raw}'. "
            f"Got '{num_str}' after stripping operator and '%'."
        )
    if '%' in s:
        num = num / 100.0
    return op, num

def _apply_op(series, op: str, val: float):
    """Apply a comparison operator to a pandas Series, returning a boolean mask."""
    if op == '>':
        return series > val
    elif op == '<':
        return series < val
    elif op == '>=':
        return series >= val
    elif op == '<=':
        return series <= val
    else:
        raise ValueError(f"Unknown operator '{op}'.")

df_logic = load_latest_parquet_from_drive("Consistent_issues_logics")
_cfg_rows = [[]] * 6
_cfg_rows[2] = [
    "Rev Loss",
    df_logic.iloc[1, 1], # index 1: Attainment
    df_logic.iloc[1, 2], # index 2: Availability
    df_logic.iloc[1, 3], # index 3: Wastage%
    df_logic.iloc[1, 4], # index 4: Vol Bucket
    "", "", "", "",
    df_logic.iloc[1, 8], # index 9: Day Attainment
    df_logic.iloc[1, 9], # index 10: Day Availability
    df_logic.iloc[1, 10] # index 11: Day Vol Bucket
]
_cfg_rows[4] = [
    "Wastage",
    df_logic.iloc[2, 1], # index 1: Attainment
    df_logic.iloc[2, 2], # index 2: Availability
    df_logic.iloc[2, 3], # index 3: Wastage%
    df_logic.iloc[2, 4], # index 4: Vol Bucket
    "", "", "", "",
    df_logic.iloc[2, 8], # index 9: Day Attainment
    df_logic.iloc[2, 9], # index 10: Day Availability
    df_logic.iloc[2, 10] # index 11: Day Vol Bucket
]

# Row 3 (index 2) -> Rev Loss | Row 5 (index 4) -> Wastage
# Cols B,C,D,E -> indices 1,2,3,4
_rl_row = _cfg_rows[2]   # Rev Loss
_wt_row = _cfg_rows[4]   # Wastage

_rl_att_op,  _rl_att_val  = _parse_threshold(_rl_row[1])   # Col B: Attainment
_rl_avl_op,  _rl_avl_val  = _parse_threshold(_rl_row[2])   # Col C: Availability
_rl_wst_op,  _rl_wst_val  = _parse_threshold(_rl_row[3])   # Col D: Wastage%
_rl_vol_op,  _rl_vol_val  = _parse_threshold(_rl_row[4])   # Col E: Vol Bucket

_wt_att_op,  _wt_att_val  = _parse_threshold(_wt_row[1])   # Col B: Attainment
_wt_avl_op,  _wt_avl_val  = _parse_threshold(_wt_row[2])   # Col C: Availability
_wt_wst_op,  _wt_wst_val  = _parse_threshold(_wt_row[3])   # Col D: Wastage%
_wt_vol_op,  _wt_vol_val  = _parse_threshold(_wt_row[4])   # Col E: Vol Bucket

print(f"[Config] Rev Loss   Attainment {_rl_att_op}{_rl_att_val} | "
      f"Availability {_rl_avl_op}{_rl_avl_val} | "
      f"Wastage% {_rl_wst_op}{_rl_wst_val} | "
      f"Vol {_rl_vol_op}{_rl_vol_val}")
print(f"[Config] Wastage    Attainment {_wt_att_op}{_wt_att_val} | "
      f"Availability {_wt_avl_op}{_wt_avl_val} | "
      f"Wastage% {_wt_wst_op}{_wt_wst_val} | "
      f"Vol {_wt_vol_op}{_wt_vol_val}")

# -- Apply flags --------------------------------------------------------------
_week_agg['rev_loss_flag'] = (
    _apply_op(_week_agg['attainment'],   _rl_att_op, _rl_att_val) &
    _apply_op(_week_agg['availability'], _rl_avl_op, _rl_avl_val) &
    _apply_op(_week_agg['wastage_pct'],  _rl_wst_op, _rl_wst_val) &
    _apply_op(_week_agg['vol_bucket'],   _rl_vol_op, _rl_vol_val)
)

_week_agg['wastage_flag'] = (
    _apply_op(_week_agg['attainment'],   _wt_att_op, _wt_att_val) &
    _apply_op(_week_agg['availability'], _wt_avl_op, _wt_avl_val) &
    _apply_op(_week_agg['wastage_pct'],  _wt_wst_op, _wt_wst_val) &
    _apply_op(_week_agg['vol_bucket'],   _wt_vol_op, _wt_vol_val)
)

# ---- 8b. Diagnostic: check how many rows pass each individual condition ----
print("\n[Diagnostic] _week_agg row count:", len(_week_agg))
print("[Diagnostic] rev_loss_flag True rows :", _week_agg['rev_loss_flag'].sum())
print("[Diagnostic] wastage_flag  True rows :", _week_agg['wastage_flag'].sum())

print("\n[Diagnostic] Condition breakdown for Rev Loss:")
print("  attainment NaN  :", _week_agg['attainment'].isna().sum())
print("  availability NaN:", _week_agg['availability'].isna().sum())
print("  wastage_pct NaN :", _week_agg['wastage_pct'].isna().sum())
_rl_c1 = _apply_op(_week_agg['attainment'],   _rl_att_op, _rl_att_val).sum()
_rl_c2 = _apply_op(_week_agg['availability'], _rl_avl_op, _rl_avl_val).sum()
_rl_c3 = _apply_op(_week_agg['wastage_pct'],  _rl_wst_op, _rl_wst_val).sum()
_rl_c4 = _apply_op(_week_agg['vol_bucket'],   _rl_vol_op, _rl_vol_val).sum()
print(f"  Pass attainment   {_rl_att_op}{_rl_att_val}: {_rl_c1}")
print(f"  Pass availability {_rl_avl_op}{_rl_avl_val}: {_rl_c2}")
print(f"  Pass wastage_pct  {_rl_wst_op}{_rl_wst_val}: {_rl_c3}")
print(f"  Pass vol_bucket   {_rl_vol_op}{_rl_vol_val}: {_rl_c4}")

print("\n[Diagnostic] Condition breakdown for Wastage:")
_wt_c1 = _apply_op(_week_agg['attainment'],   _wt_att_op, _wt_att_val).sum()
_wt_c2 = _apply_op(_week_agg['availability'], _wt_avl_op, _wt_avl_val).sum()
_wt_c3 = _apply_op(_week_agg['wastage_pct'],  _wt_wst_op, _wt_wst_val).sum()
_wt_c4 = _apply_op(_week_agg['vol_bucket'],   _wt_vol_op, _wt_vol_val).sum()
print(f"  Pass attainment   {_wt_att_op}{_wt_att_val}: {_wt_c1}")
print(f"  Pass availability {_wt_avl_op}{_wt_avl_val}: {_wt_c2}")
print(f"  Pass wastage_pct  {_wt_wst_op}{_wt_wst_val}: {_wt_c3}")
print(f"  Pass vol_bucket   {_wt_vol_op}{_wt_vol_val}: {_wt_c4}")

print("\n[Diagnostic] Rev Loss flags per week:")
print(_week_agg.groupby('Week')['rev_loss_flag'].sum().to_string())
print("\n[Diagnostic] Wastage flags per week:")
print(_week_agg.groupby('Week')['wastage_flag'].sum().to_string())

# How many combos are flagged in 2+ weeks (any weeks, not just consecutive)?
_rl_any = _week_agg.groupby(['hub_name','SKU Class Prod'])['rev_loss_flag'].sum()
_wt_any = _week_agg.groupby(['hub_name','SKU Class Prod'])['wastage_flag'].sum()
print(f"\n[Diagnostic] Rev Loss combos flagged in 2 of ANY 4 weeks : {(_rl_any >= 2).sum()}")
print(f"[Diagnostic] Wastage  combos flagged in 2 of ANY 4 weeks : {(_wt_any >= 2).sum()}")
print(f"[Diagnostic] Rev Loss combos flagged in week {_last_4_weeks[-1]} (latest): "
      f"{_week_agg[_week_agg['Week']==_last_4_weeks[-1]]['rev_loss_flag'].sum()}")
print(f"[Diagnostic] Wastage  combos flagged in week {_last_4_weeks[-1]} (latest): "
      f"{_week_agg[_week_agg['Week']==_last_4_weeks[-1]]['wastage_flag'].sum()}")

# ---- 9. Consecutive streak from latest week per Hub  SKU Class Prod ------
# A combo qualifies only if the latest week meets the condition AND each
# preceding week also meets it without a gap.
# e.g. weeks [23,24,25,26]: check 26 -> if passes check 25 -> if passes check 24.
# Stop at the first week that fails. Require streak  2 to be included.

def _consecutive_from_latest(flags):
    """Count unbroken True streak from the first element (latest week first)."""
    count = 0
    for f in flags:
        if f:
            count += 1
        else:
            break
    return count

# Sort latest week first within each group so streak starts from most recent
_week_agg_desc = _week_agg.sort_values(
    ['hub_name', 'SKU Class Prod', 'Week'], ascending=[True, True, False]
)

_rl_streak = (
    _week_agg_desc.groupby(['hub_name', 'SKU Class Prod'])['rev_loss_flag']
    .apply(_consecutive_from_latest)
    .reset_index()
    .rename(columns={'rev_loss_flag': 'Instances'})
)
rev_loss_result = (
    _rl_streak[_rl_streak['Instances'] >= 2]
    .sort_values('Instances', ascending=False)
    .reset_index(drop=True)
)

_wt_streak = (
    _week_agg_desc.groupby(['hub_name', 'SKU Class Prod'])['wastage_flag']
    .apply(_consecutive_from_latest)
    .reset_index()
    .rename(columns={'wastage_flag': 'Instances'})
)
wastage_result = (
    _wt_streak[_wt_streak['Instances'] >= 2]
    .sort_values('Instances', ascending=False)
    .reset_index(drop=True)
)

print(f"\nRev Loss   HubSKU Class Prod combos with 2 qualifying weeks: {len(rev_loss_result)}")
print(f"Wastage    HubSKU Class Prod combos with 2 qualifying weeks: {len(wastage_result)}")

# Quick streak distribution to diagnose 0-result issues
_rl_streak_dist = _rl_streak['Instances'].value_counts().sort_index()
_wt_streak_dist = _wt_streak['Instances'].value_counts().sort_index()
print(f"\n[Diagnostic] Rev Loss streak distribution (0=never flagged, 4=all 4 weeks):\n{_rl_streak_dist.to_string()}")
print(f"\n[Diagnostic] Wastage  streak distribution:\n{_wt_streak_dist.to_string()}")
print(f"\n[Diagnostic] Weeks used: {_last_4_weeks}")

logging.info("Consistent Issues identification completed. Saving outputs...")
# ---- 10. Save Parquet files directly to Drive --------------------------------
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as Excel files 'Consistent_Issues_RevLoss_{date}.xlsx' and 'Consistent_Issues_Wastage_{date}.xlsx'
# Current Output: Uploaded in-memory directly to Google Drive as Parquet files ('Consistent_Issues_RevLoss_{date}.parquet' and 'Consistent_Issues_Wastage_{date}.parquet') to BASELINE_DRIVE_PARQUET_FOLDER_ID
_today  = datetime.date.today().strftime('%Y-%m-%d')
_rl_file = f"Consistent_Issues_RevLoss_{_today}.parquet"
_wt_file = f"Consistent_Issues_Wastage_{_today}.parquet"

upload_df_to_drive_as_parquet_async(rev_loss_result, _rl_file, BASELINE_DRIVE_PARQUET_FOLDER_ID)
upload_df_to_drive_as_parquet_async(wastage_result, _wt_file, BASELINE_DRIVE_PARQUET_FOLDER_ID)

# ---- 11. (Logging moved to Consistent Issues Validation tab  see end of script) ----

# =============================================================================
# END CONSISTENT ISSUES LOGIC
# =============================================================================

# %%
# %%
outlier_df = load_latest_parquet_from_drive("City_Cat")

# %%
outlier_df['process_dt'] = pd.to_datetime(outlier_df['process_dt'], format='%m/%d/%Y', errors='coerce')

# %%
final_df['process_dt'] = pd.to_datetime(final_df['process_dt'], format='%m/%d/%Y', errors='coerce')

# %%
final_df = final_df.merge(
   outlier_df[['city_name', 'sub category','process_dt', 'Outlier_Flag']],
    on=['city_name', 'sub category','process_dt'],
    how='left'
)

# %%
final_df['Outlier_Flag'] = pd.to_numeric(final_df['Outlier_Flag'], errors='coerce').fillna(0).astype(int)

# %%
# =============================================================================
# HUB-LEVEL OUTLIER EXCLUSION (City_Cat tab, columns H:I -> Hub, Date)
# =============================================================================

# Hub exclusions are not present in City_Cat parquet (Column G was blank in sheet)
# Initialize empty DataFrame with target columns to safely bypass direct sheet calls.
hub_exclude_df = pd.DataFrame(columns=['hub_name', 'process_dt', 'Hub_Outlier_Flag'])
hub_exclude_df = hub_exclude_df.drop_duplicates(subset=['hub_name', 'process_dt'])

print(f"[HUB OUTLIER] {len(hub_exclude_df)} hub+date exclusion pairs found in City_Cat (cols H:I)")
if len(hub_exclude_df):
    print(hub_exclude_df[['hub_name', 'process_dt']].to_string(index=False))

# Merge onto final_df on hub_name + process_dt (applies across all
# cities / categories / SKUs for that hub on that date)
final_df = final_df.merge(
    hub_exclude_df[['hub_name', 'process_dt', 'Hub_Outlier_Flag']],
    on=['hub_name', 'process_dt'],
    how='left'
)
final_df['Hub_Outlier_Flag'] = final_df['Hub_Outlier_Flag'].fillna(0).astype(int)





# %%
# Skip city/subcategory outlier zeroing for sparse hubSKU-class patterns:
# weekly hubclass sales < 12 and that hubclass sells exactly 1 unit on this date.
hub_class_week_sales = final_df.groupby(
    ["hub_name", "SKU Class Prod", "Week"], dropna=False
)["Sales_withoutclusterv2 (qty)"].transform("sum")
hub_class_day_sales = final_df.groupby(
    ["hub_name", "SKU Class Prod", "process_dt"], dropna=False
)["Sales_withoutclusterv2 (qty)"].transform("sum")
exempt_low_week_single_day = (hub_class_week_sales < 12) & np.isclose(
    hub_class_day_sales, 1.0, rtol=0, atol=1e-9
)
apply_outlier_zero = (final_df["Outlier_Flag"] == 1) & (~exempt_low_week_single_day) | (final_df["Hub_Outlier_Flag"] == 1)
# Store outlier flag for downstream 'L' marking  do NOT zero out sales or availability
final_df['_apply_outlier'] = apply_outlier_zero.astype(int)






# %%
availability_agg = final_df.groupby(
    ['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'process_dt','Week']
).agg(
    simple_avail_num_sum=('simple_avail_num', 'sum'),
    simple_avail_den_sum=('simple_avail_den', 'sum'),
    sales_qty_sum=('Sales_withoutclusterv2 (qty)', 'sum'),
    _outlier_flag=('_apply_outlier', 'max'),
).reset_index()

# %%
availability_agg['simple_availability'] = np.where(
    (availability_agg['simple_avail_num_sum'] == 0) & (availability_agg['simple_avail_den_sum'] == 0),
    0,
    np.where(
        (availability_agg['simple_avail_num_sum'] == 0) | (availability_agg['simple_avail_den_sum'] == 0),
        0,
        availability_agg['simple_avail_num_sum'] / availability_agg['simple_avail_den_sum']
    )
)

# %%
# Pure Preorder override:
# For rows in the "Pure Preorder" tab where SKU Class Prod is a valid value (not #N/A/blank/nan),
# match to availability_agg on hub_name + SKU Class Prod + process_dt,
# and replace simple_availability = max(simple_availability, Availability Cap).
# Only adds PF flag column  no other columns.
preorder_raw_df = load_latest_parquet_from_drive("pure_preorder")
preorder_df = pd.DataFrame()
if len(preorder_raw_df.columns) >= 5:
    preorder_df['hub_name'] = preorder_raw_df.iloc[:, 0].astype(str).str.strip()
    preorder_df['SKU Class Prod'] = preorder_raw_df.iloc[:, 1].astype(str).str.strip()
    preorder_df['Date'] = pd.to_datetime(preorder_raw_df.iloc[:, 3], errors='coerce')
    preorder_df['Availability Cap'] = preorder_raw_df.iloc[:, 4]
else:
    preorder_df = pd.DataFrame(columns=['hub_name', 'SKU Class Prod', 'Date', 'Availability Cap'])

preorder_df["hub_name"] = preorder_df["hub_name"].astype(str).str.strip()
preorder_df["Date"] = pd.to_datetime(preorder_df["Date"], errors="coerce")

cap_raw = preorder_df["Availability Cap"].astype(str).str.strip()
preorder_df["Availability Cap"] = (
    pd.to_numeric(cap_raw.str.replace("%", "", regex=False), errors="coerce") / 100.0
)

# Keep only rows with a valid SKU Class Prod (exclude #N/A, blank, nan)
_sku = preorder_df["SKU Class Prod"].astype(str).str.strip()
_sku = _sku.replace({"nan": "#N/A", "": "#N/A"})
preorder_valid = preorder_df.loc[
    _sku.ne("#N/A"),
    ["hub_name", "SKU Class Prod", "Date", "Availability Cap"],
].copy()
preorder_valid["SKU Class Prod"] = _sku[_sku.ne("#N/A")].values
preorder_valid = preorder_valid.rename(columns={"Date": "process_dt", "Availability Cap": "preorder_cap"})

preorder_caps = (
    preorder_valid.groupby(["hub_name", "SKU Class Prod"], as_index=False)["preorder_cap"]
    .max()
)

cap_series = (
    pd.DataFrame({
        "hub_name": availability_agg["hub_name"].astype(str).str.strip(),
        "SKU Class Prod": availability_agg["SKU Class Prod"].astype(str).str.strip(),
    })
    .merge(preorder_caps, on=["hub_name", "SKU Class Prod"], how="left")
    ["preorder_cap"]
    .values
)

availability_agg["PF"] = np.where(pd.notna(cap_series), "PF", "")
mask_pf = pd.notna(cap_series)

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
if isinstance(pivot_df.columns, pd.MultiIndex):
    pivot_df.columns = ['_'.join(map(str, col)).strip() for col in pivot_df.columns.values]

# %%
availability_cols = [c for c in pivot_df.columns if c.startswith("simple_availability")]



# %%
for c in availability_cols:
    week_num = c.split('_')[-1]
    out_col = f'out_of_stock_{week_num}'
    
    pivot_df[out_col] = np.floor(20 - (1 - pivot_df[c]) * 12).astype(int) 

# %%
pivot_df = pivot_df.reset_index()

# Carry PF flag from availability_agg into pivot_df (hub_name + SKU Class Prod level)
_pf_map = (
    availability_agg[["hub_name", "SKU Class Prod", "PF"]]
    .drop_duplicates(subset=["hub_name", "SKU Class Prod"])
)
pivot_df = pivot_df.merge(_pf_map, on=["hub_name", "SKU Class Prod"], how="left")
pivot_df["PF"] = pivot_df["PF"].fillna("")

# %%
# Extract subcat to Cat mapping (previously H:J of Avl_Flag) from the loaded avl_flag_df.
# Some p_master exports omit the Category column entirely; in that case, preserve the
# original downstream logic by treating sub-category as the category key.
if 'Sub-category' in avl_flag_df.columns and 'Category' not in avl_flag_df.columns:
    avl_flag_df['Category'] = avl_flag_df['Sub-category']

if 'Sub-category' in avl_flag_df.columns and 'Category' in avl_flag_df.columns:
    subcat_cat_df = avl_flag_df[['Sub-category', 'Category']].drop_duplicates().rename(columns={
        'Sub-category': 'sub category',
        'Category': 'Cat'
    })
else:
    subcat_cat_df = pd.DataFrame(columns=['sub category', 'Cat'])

# %%
pivot_df = pivot_df.merge(subcat_cat_df, how='left', on='sub category')


# %%
# Load Sell-Through Factor from parquet
stf_df = load_latest_parquet_from_drive("SellThroughFactor")

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
from functools import reduce
stf_pivot_all = reduce(lambda left, right: pd.merge(left, right, on=['city_name', 'Cat', 'day', 'hour']), pivot_list)

# Hub  Cat  day  hour STF (STF_hub): overrides city factors where a hub row exists; NaN falls back to city
stf_hub_df = load_latest_parquet_from_drive("stf_hub")
stf_hub_df.columns = stf_hub_df.columns.str.strip()
_stf_hub_required = {"hub_name", "Cat", "day", "hour_15min", "STF_sales", "STF_sales_lowvolume"}
if len(stf_hub_df) > 0 and _stf_hub_required.issubset(set(stf_hub_df.columns)):
    stf_hub_df["hour"] = pd.to_numeric(stf_hub_df["hour_15min"], errors="coerce").fillna(0).astype(int)
    for _c in ["STF_sales", "STF_sales_lowvolume"]:
        stf_hub_df[_c] = pd.to_numeric(stf_hub_df[_c], errors="coerce")
    stf_hub_list = []
    for factor_col, src_col in [
        ("salethroughfactor", "STF_sales"),
        ("salethroughfactor_lowvolume", "STF_sales_lowvolume"),
    ]:
        stf_hub_daily = (
            stf_hub_df.groupby(["hub_name", "Cat", "day", "hour"], as_index=False)[src_col]
            .mean()
            .rename(columns={src_col: factor_col})
        )
        stf_hub_daily["key"] = 1
        stf_hub_expanded = pd.merge(stf_hub_daily, week_df, on="key").drop("key", axis=1)
        stf_hub_pivot = stf_hub_expanded.pivot(
            index=["hub_name", "Cat", "day", "hour"], columns="week", values=factor_col
        )
        stf_hub_pivot.columns = [f"{factor_col}_{w}" for w in stf_hub_pivot.columns]
        stf_hub_pivot = stf_hub_pivot.reset_index()
        stf_hub_list.append(stf_hub_pivot)
    stf_hub_pivot_all = reduce(
        lambda left, right: pd.merge(left, right, on=["hub_name", "Cat", "day", "hour"]),
        stf_hub_list,
    )
else:
    stf_hub_pivot_all = None


# %%
stf_pivot = stf_expanded.pivot(index=['city_name', 'Cat', 'day','hour'], columns='week', values='salethroughfactor')
stf_pivot.columns = [f'salethroughfactor_{w}' for w in stf_pivot.columns]
stf_pivot = stf_pivot.reset_index()


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

        temp_df = pivot_df[["city_name", "hub_name", "Cat", "day", out_of_stock_col]].copy()
        temp_df = temp_df.rename(columns={out_of_stock_col: "hour"})

        city_merge = temp_df.merge(
            stf_pivot_all[["city_name", "Cat", "day", "hour", stf_week_col]],
            on=["city_name", "Cat", "day", "hour"],
            how="left",
        )
        if (
            stf_hub_pivot_all is not None
            and stf_week_col in stf_hub_pivot_all.columns
        ):
            hub_merge = temp_df.merge(
                stf_hub_pivot_all[["hub_name", "Cat", "day", "hour", stf_week_col]],
                on=["hub_name", "Cat", "day", "hour"],
                how="left",
            )
            pivot_df[stf_week_col] = hub_merge[stf_week_col].combine_first(
                city_merge[stf_week_col]
            )
        else:
            pivot_df[stf_week_col] = city_merge[stf_week_col]

# Build salethroughfactor_8am_{week} columns using hub-then-city fallback at hour=8
_stf_8am_city = stf_pivot_all[stf_pivot_all["hour"] == 8].copy()
_stf_8am_hub  = stf_hub_pivot_all[stf_hub_pivot_all["hour"] == 8].copy() if stf_hub_pivot_all is not None else None

for week in [col.split('_')[-1] for col in pivot_df.columns if col.startswith('simple_availability_')]:
    _src_col   = f"salethroughfactor_{week}"
    _8am_col   = f"salethroughfactor_8am_{week}"
    _temp      = pivot_df[["city_name", "hub_name", "Cat", "day"]].copy()

    _city_8am  = _temp.merge(
        _stf_8am_city[["city_name", "Cat", "day", _src_col]].rename(columns={_src_col: _8am_col}),
        on=["city_name", "Cat", "day"], how="left",
    )[_8am_col]

    if _stf_8am_hub is not None and _src_col in _stf_8am_hub.columns:
        _hub_8am = _temp.merge(
            _stf_8am_hub[["hub_name", "Cat", "day", _src_col]].rename(columns={_src_col: _8am_col}),
            on=["hub_name", "Cat", "day"], how="left",
        )[_8am_col]
        pivot_df[_8am_col] = _hub_8am.combine_first(_city_8am)
    else:
        pivot_df[_8am_col] = _city_8am


# %%

week_cols = [col for col in pivot_df.columns if col.startswith('simple_availability_')]
weeks = [col.split('_')[-1] for col in week_cols]


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
        

        # Compute corrected sales
        pivot_df[corrected_col] = (pivot_df[sales_col] / np.where(factor_used == 0, np.nan, factor_used)).round(0)

# For PF rows: multiply corrected_col by salethroughfactor at 8am (hub-then-city fallback)
mask_pf = pivot_df["PF"] == "PF"
print(f"\n[PF DEBUG] PF rows in pivot_df: {mask_pf.sum()}")
if mask_pf.any():
    for week in weeks:
        corrected_col = f"avl_corrected_sales_{week}"
        _8am_col      = f"salethroughfactor_8am_{week}"
        if corrected_col not in pivot_df.columns or _8am_col not in pivot_df.columns:
            print(f"  [PF DEBUG] week {week}: missing column(s)  skipping")
            continue
        _pf_mask = mask_pf & (pivot_df[corrected_col] != "L")
        _corr    = pd.to_numeric(pivot_df.loc[_pf_mask, corrected_col], errors="coerce")
        _stf     = pd.to_numeric(pivot_df.loc[_pf_mask, _8am_col],      errors="coerce")
        _result  = (_corr * _stf).round(0)
        print(f"  [PF DEBUG] week {week}: {_pf_mask.sum()} rows multiplied | "
              f"corr sample={_corr.head(3).tolist()} | "
              f"stf_8am sample={_stf.head(3).tolist()} | "
              f"result sample={_result.head(3).tolist()}")
        pivot_df.loc[_pf_mask, corrected_col] = _result
    print(f"[PF DEBUG] Sample PF rows after multiplication:")
    _debug_cols = ["hub_name", "SKU Class Prod", "day", "PF"] + \
                  [f"avl_corrected_sales_{w}" for w in weeks if f"avl_corrected_sales_{w}" in pivot_df.columns]
    print(pivot_df.loc[mask_pf, _debug_cols].head(10).to_string(index=False))
else:
    print("[PF DEBUG] WARNING: No PF rows found in pivot_df  check PF merge step above")



# %%
# Load City drops from parquet
City_drops = load_latest_parquet_from_drive("City_drops")

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
# Build outlier flag lookup at (city, sub_cat, hub, sku, day, week) level
_outlier_for_adj = (
    availability_agg
    .groupby(['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'Week'], as_index=False)
    ['_outlier_flag'].max()
    .rename(columns={'Week': 'week'})
)
_outlier_for_adj['week'] = _outlier_for_adj['week'].astype(str)

# Build original-L lookup: sales=0 AND availability<0.9 at (city, sub_cat, hub, sku, day, week) level
# Mirrors the mask_L condition previously applied on pivot_df, now applied on adjusted_avl_corrected_sales
_original_L_lookup = (
    availability_agg
    .groupby(['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'Week'], as_index=False)
    .agg(_sales=('sales_qty_sum', 'sum'), _avail=('simple_availability', 'sum'))
    .rename(columns={'Week': 'week'})
)
_original_L_lookup['week'] = _original_L_lookup['week'].astype(str)
_original_L_lookup['_is_original_L'] = (
    (_original_L_lookup['_sales'] == 0) & (_original_L_lookup['_avail'] == 0)
).astype(int)
_original_L_lookup = _original_L_lookup[
    ['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'week', '_is_original_L']
]

# %%
merged = (
    pivot_long
    .merge(City_drops[["city_name", "sub category","week", "day", "%Change"]],
           how="left", on=["city_name", "sub category","week", "day"])
    .merge(_outlier_for_adj,
           on=['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'week'],
           how='left')
    .merge(_original_L_lookup,
           on=['city_name', 'sub category', 'hub_name', 'SKU Class Prod', 'day', 'week'],
           how='left')
)
merged['_outlier_flag'] = merged['_outlier_flag'].fillna(0).astype(int)
# If the lookup merge missed (NaN)  combo had no data in availability_agg for that week
# (pivot_table filled it with 0)  treat as 'L' when avl_corrected_sales is also 0
_avl_num = pd.to_numeric(merged['avl_corrected_sales'], errors='coerce')
merged['_is_original_L'] = np.where(
    merged['_is_original_L'].isna(),
    (_avl_num.fillna(0) == 0).astype(int),   # no real data + 0 sales -> L
    merged['_is_original_L']
).astype(int)

# %%
merged["avl_corrected_sales_num"] = pd.to_numeric(merged["avl_corrected_sales"], errors="coerce")
merged["%Change"] = pd.to_numeric(merged["%Change"], errors="coerce")

# %%
merged["adjusted_avl_corrected_sales"] = np.where(
    merged["avl_corrected_sales_num"].notna() & merged["%Change"].notna(),
    (merged["avl_corrected_sales_num"] * (1 + merged["%Change"])),
    merged["avl_corrected_sales"]  # keep original if it's 'L' or NaN
)

# Mark adjusted_avl_corrected_sales as 'L' for:
#   1. Outlier_Flag == 1 (non-exempt)  direct flag
#   2. Original logic: sales=0 AND availability < 0.9
_adj_L_mask = (merged['_outlier_flag'] >= 1) | (merged['_is_original_L'] >= 1)
merged["adjusted_avl_corrected_sales"] = merged["adjusted_avl_corrected_sales"].astype(object)
merged.loc[_adj_L_mask, 'adjusted_avl_corrected_sales'] = 'L'
merged.drop(columns=['_outlier_flag', '_is_original_L'], inplace=True)

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
import re

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
        # 2025 weeks (4853)
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

AVAIL_THRESHOLD = 0.20   # 20%

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

# avl_corrected sales  used for cross-week mean reference
sales_matrix = pivot_final[adj_col_list].apply(pd.to_numeric, errors='coerce')   # NaN for 'L'
avail_matrix = pivot_final[avail_col_list].apply(pd.to_numeric, errors='coerce')

# Raw actual sales (sales_qty_sum_)  used for the 1.5 scaled floor
raw_sales_col_list = [f"sales_qty_sum_{w}" for w in week_suffixes]
available_raw_cols = [c for c in raw_sales_col_list if c in pivot_final.columns]
raw_sales_matrix   = pivot_final[available_raw_cols].apply(pd.to_numeric, errors='coerce')
raw_sales_matrix.columns = [c.split("_")[-1] for c in available_raw_cols]  # align to week_suffixes

# Rename matrices to share the same week-su                                  ffix column names for easy masking
sales_matrix.columns = week_suffixes
avail_matrix.columns = week_suffixes

# Mask: True where availability is sufficient (>= 20%) AND sales value is numeric
good_avail_mask = avail_matrix >= AVAIL_THRESHOLD          # shape: (rows  weeks)
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
    pivot_final[new_col] = val_numeric.astype(object)

    # Identify rows where this week has low availability (< 20%) and a numeric sales value
    low_avail_mask = (
        avail_numeric.notna() &
        (avail_numeric < AVAIL_THRESHOLD) &
        val_numeric.notna()# only replace if value exists
    )

    if low_avail_mask.any():
        # Reference weeks = all OTHER weeks with good availability
        other_weeks = [w for w in week_suffixes if w != week]

        # Mean of avl_corrected_sales for other good-availability weeks per row
        other_good = valid_sales_mask[other_weeks]          # (rows  other_weeks), bool
        other_sales = sales_matrix[other_weeks]             # (rows  other_weeks), numeric

        # Mask to NaN where avail is bad, then take row mean
        ref_sales = other_sales.where(other_good)           # NaN where avail < 20%
        ref_mean  = ref_sales.mean(axis=1)                  # row-wise mean of valid weeks

        # Only replace where low_avail AND a valid reference mean exists
        has_ref = ref_mean.notna()
        replace_mask = low_avail_mask & has_ref

        # Replacement = max(mean_of_good_weeks, raw_actual_sales  1.5)
        # raw sales 1.5 avoids double-uplifting (avl_corrected already has STF applied)
        if week in raw_sales_matrix.columns:
            raw_val = raw_sales_matrix[week]
        else:
            raw_val = val_numeric   # fallback to avl_corrected if raw col missing
        scaled_sales = (raw_val * 1.5).round(0)
        final_replacement = np.maximum(ref_mean, scaled_sales)

        pivot_final.loc[replace_mask, new_col] = final_replacement[replace_mask].round(0)

    # Always restore non-numeric values ('L') from the original column
    non_numeric_mask = pivot_final[adj_col].apply(
        lambda x: pd.notna(x) and pd.isna(pd.to_numeric(x, errors='coerce'))
    )
    if non_numeric_mask.any():
        pivot_final.loc[non_numeric_mask, new_col] = pivot_final.loc[non_numeric_mask, adj_col]

    # Fill originally-blank (NaN) cells with 'L' for visual consistency
    blank_mask = pivot_final[adj_col].isna()
    if blank_mask.any():
        pivot_final.loc[blank_mask, new_col] = 'L'

# # %%
# # =============================================================================
# # STEP 2  SPIKE / DIP OUTLIER CORRECTION  (commented out  enable when needed)
# # Runs on the Outlier_corrected_ columns produced by Step 1 above.
# # High spike : value deviates from BOTH row_avg and row_median -> replace with median
# # Low dip    : value < 0.5avg AND < 0.5median (row_avg >= 3) -> replace with avg
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

    # Latest week  no outlier correction
   

    val_numeric = pd.to_numeric(pivot_final[oc_col], errors='coerce')

    positive_mask = val_numeric > 0
    avg_outlier   = (val_numeric - pivot_final['row_avg']).abs()    > 1.5 * pivot_final['row_avg']
    med_outlier   = (val_numeric - pivot_final['row_median']).abs() > 1.5 * pivot_final['row_median']

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

    # Re-preserve 'L' and blanks  spike/dip logic must never overwrite them
    non_numeric_mask = pivot_final[oc_col].apply(
        lambda x: pd.notna(x) and pd.isna(pd.to_numeric(x, errors='coerce'))
    )
    if non_numeric_mask.any():
        pivot_final.loc[non_numeric_mask, oc_col] = pivot_final.loc[non_numeric_mask, oc_col]

# %%
pivot_final = reorder_week_columns(pivot_final)

# %%
print(pivot_final.columns)

# %%
sugg_plan = pivot_final.copy()

# %%
# Load Percentile and overrides from parquet
df_pct = load_latest_parquet_from_drive("Percentile")

_pct_df = df_pct[['city_name', 'sub category', 'day', 'Percentile']].copy()
for _c in ["city_name", "sub category", "day"]:
    _pct_df[_c] = _pct_df[_c].astype(str).str.strip()
_pct_df["Percentile"] = pd.to_numeric(_pct_df["Percentile"], errors="coerce")

_override_df = df_pct[['hub_name_2', 'SKU Class Prod', 'day_2', 'percentile_override_2']].copy()
_override_df = _override_df.rename(columns={
    'hub_name_2': 'hub_name',
    'day_2': 'day'
})
for _c in ["hub_name", "SKU Class Prod", "day"]:
    _override_df[_c] = _override_df[_c].astype(str).str.strip()
_override_df["percentile_override_2"] = pd.to_numeric(_override_df["percentile_override_2"], errors="coerce")
_override_df = _override_df.dropna(subset=["percentile_override_2"])
_override_lookup = _override_df.set_index(["hub_name", "SKU Class Prod", "day"])["percentile_override_2"].to_dict()

sugg_plan = sugg_plan.merge(
    _pct_df[["city_name", "sub category", "day", "Percentile"]].rename(
        columns={"Percentile": "_pct_lookup"}
    ),
    on=["city_name", "sub category", "day"],
    how="left",
)
# Default to 0.5 (mean) where no mapping exists
sugg_plan["_pct_lookup"] = sugg_plan["_pct_lookup"].fillna(0.5)

# %%
outlier_cols = [c for c in sugg_plan.columns if c.startswith("Outlier_corrected_")]
# outlier_cols = sorted(outlier_cols, key=lambda x: int(x.split("_")[-1]))

# %%
print(outlier_cols)

# %%
print(sugg_plan.columns)

# %%
def _week_num_from_outlier_col(col_name: str) -> int:
    s = str(col_name)
    tail = s.split("_")[-1]
    m = re.search(r"(\d+)(?!.*\d)", tail)  # last run of digits
    return int(m.group(1)) if m else -1


# Reorder Outlier_corrected_ columns in the DataFrame from oldest to newest week
outlier_cols = sorted(outlier_cols, key=_week_num_from_outlier_col)
_other_cols = [c for c in sugg_plan.columns if c not in outlier_cols]
sugg_plan = sugg_plan[_other_cols + outlier_cols]


def get_weighted_recent_trend(
    row,
    cols,
    windows=(3, 6, 10),
    weights=(0.80, 0.10, 0.10),
    percentile: float = 0.5,
):
    cols_sorted = sorted(cols, key=_week_num_from_outlier_col)  # oldest -> newest by week number

    raw_values = row[cols_sorted].astype(str).str.strip()
    numeric_mask = raw_values.str.match(r"^\d*\.?\d+$")
    values_by_week = pd.to_numeric(raw_values.where(numeric_mask), errors="coerce").values  # NaN for non-numeric/'L'/blank

    if not np.isfinite(values_by_week).any():
        return np.nan

    # last values correspond to most recent weeks (because cols_sorted is oldest -> newest)
    # When percentile == 0.5 use mean (not median) as explicitly required.
    def _stat_last_k(k: int) -> float:
        window = values_by_week[-k:] if len(values_by_week) >= k else values_by_week
        window = [v for v in window if pd.notna(v)]  # keep 0s, drop NaNs
        if not window:
            return float("nan")
        if percentile == 0.5:
            return float(np.mean(window))
        return float(np.percentile(window, percentile * 100))

    stats = [_stat_last_k(int(w)) for w in windows]
    weighted = sum(float(wt) * s for wt, s in zip(weights, stats) if pd.notna(s))
    weight_sum = sum(float(wt) for wt, s in zip(weights, stats) if pd.notna(s))

    return weighted / weight_sum if weight_sum > 0 else np.nan

# %%


# %%
sugg_plan["sugg_plan"] = sugg_plan.apply(
    lambda r: get_weighted_recent_trend(r, outlier_cols, percentile=r["_pct_lookup"]), axis=1
)

# %%
# Hub-level percentile override on latest 2 data points (cols O:R of Percentile sheet)
_latest_2_cols = outlier_cols[-2:]  # already sorted oldest->newest, so last 2 = most recent

def _apply_hub_override(row):
    key = (str(row["hub_name"]).strip(), str(row["SKU Class Prod"]).strip(), str(row["day"]).strip())
    if key not in _override_lookup:
        return row["sugg_plan"]
    p = _override_lookup[key]
    raw = row[_latest_2_cols].astype(str).str.strip()
    numeric_mask = raw.str.match(r"^\d*\.?\d+$")
    values = pd.to_numeric(raw.where(numeric_mask), errors="coerce").dropna().tolist()
    if not values:  # both data points are L -> increase by 20%
        return row["sugg_plan"] * 1.10
    if p == 0.5:
        return float(np.mean(values))
    return float(np.percentile(values, p * 100))

sugg_plan["sugg_plan"] = sugg_plan.apply(_apply_hub_override, axis=1)

# %%
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded local Excel base plan file from 'BASELINE_WEEKLY_PLAN_PATH' ('Baseline Wk{Week} 2026.xlsx')
# Current Input: Loaded directly from Google Drive ('Baseline_*.parquet') from folder ID BASELINE_DRIVE_PARQUET_FOLDER_ID
logging.info("Loading base_plan parquet...")
base_plan = load_latest_parquet_from_drive("Baseline", BASELINE_DRIVE_PARQUET_FOLDER_ID)

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
# VA_exclusive_1 = [
#     "Burger", "Eggs", 
#  "Spreads", "Heat & Eat"
# ]

# VA_exclusive_2 = [
#     "Kebab & Tandoor", 
#     "Ready to Cook",
# ]

# %%
outlier_cols = [c for c in Final_Plan.columns if c.startswith("Outlier_corrected_")]

Final_Plan["numeric_outlier_count"] = (
    Final_Plan[outlier_cols]
    .apply(pd.to_numeric, errors="coerce")
    .notna()
    .sum(axis=1)
)


# # %%
# skip_hubs = ["CCS", "ECS", "HKM", "KLK", "SMG", "SPC"]
# skip_cities = ["Chennai", "Kolkata"]

# %%

# --- OLD CODE PRESERVED AS PER REQUEST ---
# def final_plan_logic(row):
#     # Case -1: both NaN -> 0
#     if pd.isna(row["sugg_plan"]) and pd.isna(row["Base_Plan (qty)"]):
#         return 0
# 
#     # Case 0: sugg_plan NaN -> base_plan
#     if pd.isna(row["sugg_plan"]):
#         return row["Base_Plan (qty)"]
# 
#     # Case 1: base_plan NaN -> 0
#     if pd.isna(row["Base_Plan (qty)"]):
#         return 0
# 
#     # Case 2: base_plan 0 -> sugg_plan
#     if row["Base_Plan (qty)"] == 0:
#         return row["sugg_plan"]
# 
#     #  Case NEW: exactly one numeric outlier datapoint
#     if row["numeric_outlier_count"] == 1:
#         if row["sugg_plan"] == 0:
#             return row["Base_Plan (qty)"]
#         else:
#             return max(
#                 row["sugg_plan"],
#                 (row["sugg_plan"] + row["Base_Plan (qty)"]) / 2
#             )
# 
#     # Case 3 & 4: VA_exclusive rules
#     # if (row["hub_name"] not in skip_hubs) and (row["city_name"] not in skip_cities):
# 
#     #     if row["sub category"] in VA_exclusive_1:
#     #         if row["sugg_plan"] < 5:
#     #             return min(row["sugg_plan"], 2.0 * row["Base_Plan (qty)"])
#     #         else:
#     #             return min(row["sugg_plan"], 1.5 * row["Base_Plan (qty)"])
# 
#     #     if row["sub category"] in VA_exclusive_2:
#     #         if row["sugg_plan"] < 5:
#     #             return min(row["sugg_plan"], 2.0 * row["Base_Plan (qty)"])
#     #         else:
#     #             return min(row["sugg_plan"], 2.0 * row["Base_Plan (qty)"])
# 
#     # Default
#     return row["sugg_plan"]
# 
# Final_Plan["Final_Plan"] = Final_Plan.apply(final_plan_logic, axis=1)
# ----------------------------------------

# Vectorized final_plan_logic
import numpy as np
sugg_isna = Final_Plan["sugg_plan"].isna()
base_isna = Final_Plan["Base_Plan (qty)"].isna()

c_both_nan = sugg_isna & base_isna
c_sugg_nan = sugg_isna & ~base_isna
c_base_nan = ~sugg_isna & base_isna
c_base_zero = (Final_Plan["Base_Plan (qty)"] == 0)

c_outlier_1 = (Final_Plan["numeric_outlier_count"] == 1)
c_outlier_sugg_zero = c_outlier_1 & (Final_Plan["sugg_plan"] == 0)
c_outlier_sugg_nonzero = c_outlier_1 & (Final_Plan["sugg_plan"] != 0)

max_outlier = np.maximum(
    Final_Plan["sugg_plan"],
    (Final_Plan["sugg_plan"] + Final_Plan["Base_Plan (qty)"]) / 2
)

Final_Plan["Final_Plan"] = np.select(
    [
        c_both_nan,
        c_sugg_nan,
        c_base_nan,
        c_base_zero,
        c_outlier_sugg_zero,
        c_outlier_sugg_nonzero
    ],
    [
        0,
        Final_Plan["Base_Plan (qty)"],
        0,
        Final_Plan["sugg_plan"],
        Final_Plan["Base_Plan (qty)"],
        max_outlier
    ],
    default=Final_Plan["sugg_plan"]
)

# %%
Final_Plan["Final_Plan"] = Final_Plan["Final_Plan"].apply(
    lambda x: round(x) if pd.notna(x) else x
)



# %%
# Final_Plan.to_clipboard()

# %%
# =============================================================================
# REV LOSS PLAN UPLIFT
# Adds new columns to Final_Plan (no extra rows):
#   Initial_Final_Plan   original Final_Plan value
#   Weekly_Plan_Agg      sum of Initial_Final_Plan across days per hub-SKU
#   Doubled_Plan         Weekly_Plan_Agg  2
#   Salience             hub  sub category  day weight from base_plan
#   is_rev_loss_uplift   True for combos in the latest Rev Loss file
#   Final_Plan (new)     Doubled_Plan  Salience for flagged rows,
#                         Initial_Final_Plan for all others
# ============================================================================

#  Rename existing Final_Plan column 
Final_Plan = Final_Plan.rename(columns={'Final_Plan': 'Initial_Final_Plan'})

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded latest local Excel Consistent_Issues_RevLoss_*.xlsx file
# Current Input: Loaded directly from Google Drive ('Consistent_Issues_RevLoss_*.parquet') from folder ID BASELINE_DRIVE_PARQUET_FOLDER_ID
try:
    rl_combos = load_latest_parquet_from_drive("Consistent_Issues_RevLoss", BASELINE_DRIVE_PARQUET_FOLDER_ID)
    rl_combos = rl_combos[['hub_name', 'SKU Class Prod']].drop_duplicates().reset_index(drop=True)
    print(f"[REV LOSS UPLIFT] Rev Loss combos: {len(rl_combos)}")
    has_rl_files = True
except Exception as e:
    print(f"WARNING: No Consistent_Issues_RevLoss parquet found on Drive ({e})  Rev Loss uplift skipped")
    has_rl_files = False

if not has_rl_files:
    Final_Plan['Weekly_Plan_Agg']    = np.nan
    Final_Plan['Doubled_Plan']       = np.nan
    Final_Plan['Salience']           = np.nan
    Final_Plan['is_rev_loss_uplift'] = False
    Final_Plan['Final_Plan']         = Final_Plan['Initial_Final_Plan']
else:
    print(f"[REV LOSS UPLIFT] Rev Loss combos: {len(rl_combos)}")

    #  Step 1: Flag Rev Loss combos 
    rl_combos['is_rev_loss_uplift'] = True
    Final_Plan = Final_Plan.merge(
        rl_combos, on=['hub_name', 'SKU Class Prod'], how='left'
    )
    Final_Plan['is_rev_loss_uplift'] = Final_Plan['is_rev_loss_uplift'].fillna(False)

    #  Step 2: Weekly_Plan_Agg and Doubled_Plan 
    _weekly_agg = (
        Final_Plan.groupby(['hub_name', 'SKU Class Prod'], as_index=False)['Initial_Final_Plan']
        .sum()
        .rename(columns={'Initial_Final_Plan': 'Weekly_Plan_Agg'})
    )
    Final_Plan = Final_Plan.merge(_weekly_agg, on=['hub_name', 'SKU Class Prod'], how='left')
    Final_Plan['Doubled_Plan'] = Final_Plan['Weekly_Plan_Agg'] * 1.5

    #  Step 3: Salience at hub  sub category  day from base_plan 
    _sku_subcat = (
        Final_Plan[['SKU Class Prod', 'sub category']]
        .drop_duplicates(subset=['SKU Class Prod'])
    )
    bp_sal = (
        base_plan_grouped[['hub_name', 'SKU Class Prod', 'day', 'BasePlan']]
        .merge(_sku_subcat, on='SKU Class Prod', how='left')
    )
    bp_subcat_day = (
        bp_sal.groupby(['hub_name', 'sub category', 'day'], as_index=False)['BasePlan']
        .sum()
        .rename(columns={'BasePlan': 'subcat_day_plan'})
    )
    bp_subcat_day['subcat_total'] = bp_subcat_day.groupby(
        ['hub_name', 'sub category'])['subcat_day_plan'].transform('sum')
    bp_subcat_day['Salience'] = np.where(
        bp_subcat_day['subcat_total'] > 0,
        bp_subcat_day['subcat_day_plan'] / bp_subcat_day['subcat_total'],
        np.nan,
    )
    _n_days = bp_subcat_day.groupby(['hub_name', 'sub category'])['day'].transform('count')
    bp_subcat_day['Salience'] = bp_subcat_day['Salience'].fillna(1.0 / _n_days)

    # Merge Salience back onto Final_Plan (hub  sub category  day)
    Final_Plan = Final_Plan.merge(
        bp_subcat_day[['hub_name', 'sub category', 'day', 'Salience']],
        on=['hub_name', 'sub category', 'day'],
        how='left',
    )

    #  Step 4: Compute new Final_Plan 
    # max(Initial_Final_Plan, Doubled_Plan  Salience)  never go below original
    _rl_salience_plan = (Final_Plan['Doubled_Plan'] * Final_Plan['Salience']).round(0)
    Final_Plan['Final_Plan'] = np.where(
        Final_Plan['is_rev_loss_uplift'],
        np.maximum(
            pd.to_numeric(Final_Plan['Initial_Final_Plan'], errors='coerce').fillna(0),
            pd.to_numeric(_rl_salience_plan, errors='coerce').fillna(0),
        ),
        Final_Plan['Initial_Final_Plan'],
    )

    _flagged = Final_Plan['is_rev_loss_uplift'].sum()
    print(f"[REV LOSS UPLIFT] Rows uplifted      : {_flagged}")
    print(f"[REV LOSS UPLIFT] Rows unchanged     : {len(Final_Plan) - _flagged}")
    print(f"[REV LOSS UPLIFT] Sample (flagged rows):")
    print(Final_Plan[Final_Plan['is_rev_loss_uplift']][
        ['hub_name', 'SKU Class Prod', 'day', 'Initial_Final_Plan',
         'Weekly_Plan_Agg', 'Doubled_Plan', 'Salience', 'Final_Plan']
    ].head(8).to_string(index=False))

# %%
# =============================================================================
# WASTAGE PLAN CORRECTION
# For hub  SKU Class Prod combos flagged as Consistent Wastage issues:
#   1. Load the latest Consistent_Issues_Wastage_*.xlsx from the folder
#   2. Compute 4-week average of avl_corrected_sales_{week} per hub-SKU-day
#      ('L' values treated as NaN and excluded from average)
#   3. Redistribute using same hub  sub category  day salience from base_plan
#   4. Add columns: Wastage_Avg_4Wk_Sales, is_wastage_uplift
#   5. Override Final_Plan for wastage-flagged rows with avg  Salience
# =============================================================================

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded latest local Excel Consistent_Issues_Wastage_*.xlsx file
# Current Input: Loaded directly from Google Drive ('Consistent_Issues_Wastage_*.parquet') from folder ID BASELINE_DRIVE_PARQUET_FOLDER_ID
try:
    wt_combos = load_latest_parquet_from_drive("Consistent_Issues_Wastage", BASELINE_DRIVE_PARQUET_FOLDER_ID)
    wt_combos = wt_combos[['hub_name', 'SKU Class Prod', 'Instances']].drop_duplicates(subset=['hub_name', 'SKU Class Prod']).reset_index(drop=True)
    print(f"[WASTAGE CORRECTION] Wastage combos: {len(wt_combos)}")
    has_wt_files = True
except Exception as e:
    print(f"WARNING: No Consistent_Issues_Wastage parquet found on Drive ({e})  Wastage correction skipped")
    has_wt_files = False

if not has_wt_files:
    Final_Plan['Wastage_Avg_4Wk_Sales'] = np.nan
    Final_Plan['is_wastage_uplift']     = False
else:
    print(f"[WASTAGE CORRECTION] Wastage combos: {len(wt_combos)}")

    #  Step 1: Flag wastage combos 
    wt_combos['is_wastage_uplift'] = True
    Final_Plan = Final_Plan.merge(
        wt_combos, on=['hub_name', 'SKU Class Prod'], how='left'
    )
    Final_Plan['is_wastage_uplift'] = Final_Plan['is_wastage_uplift'].fillna(False)

    #  Step 2: 4-week average of avl_corrected_sales per hub-SKU-day 
    # Identify avl_corrected_sales columns for _last_4_weeks
    # All 4 available avl_corrected_sales columns (sorted oldest -> latest)
    _all_avl_cols = [f"avl_corrected_sales_{w}" for w in _last_4_weeks
                     if f"avl_corrected_sales_{w}" in Final_Plan.columns]
    print(f"[WASTAGE CORRECTION] avl_corrected_sales cols available: {_all_avl_cols}")

    if _all_avl_cols:
        # Step A: coerce to numeric ('L' -> NaN), sum across days per hub-SKU per week
        _avl_num = Final_Plan[['hub_name', 'SKU Class Prod'] + _all_avl_cols].copy()
        for _c in _all_avl_cols:
            _avl_num[_c] = pd.to_numeric(_avl_num[_c], errors='coerce')

        _hub_sku_weekly = (
            _avl_num.groupby(['hub_name', 'SKU Class Prod'])[_all_avl_cols]
            .sum()
            .reset_index()
        )

        # Step B: merge Instances so we know how many weeks to average per combo
        _hub_sku_weekly = _hub_sku_weekly.merge(
            wt_combos[['hub_name', 'SKU Class Prod', 'Instances']],
            on=['hub_name', 'SKU Class Prod'], how='left'
        )

        # Step C: for each combo use last N weeks based on Instances
        def _wt_avg_and_weeks(row):
            n = int(row['Instances']) if pd.notna(row['Instances']) else len(_all_avl_cols)
            n = min(n, len(_all_avl_cols))          # cap at available weeks
            cols = _all_avl_cols[-n:]               # last N cols = most recent N weeks
            avg  = row[cols].mean()
            wks  = ', '.join(str(w) for w in _last_4_weeks[-n:])
            return pd.Series({'Wastage_Avg_4Wk_Sales': avg, 'Wastage_Avg_Weeks': wks})

        _hub_sku_avg = _hub_sku_weekly.apply(_wt_avg_and_weeks, axis=1)
        _hub_sku_weekly = pd.concat([
            _hub_sku_weekly[['hub_name', 'SKU Class Prod']], _hub_sku_avg
        ], axis=1)

        # Merge avg and week-label back onto Final_Plan
        Final_Plan = Final_Plan.merge(
            _hub_sku_weekly, on=['hub_name', 'SKU Class Prod'], how='left'
        )
        # Non-wastage rows get blank week label
        Final_Plan['Wastage_Avg_Weeks'] = Final_Plan['Wastage_Avg_Weeks'].fillna('')
    else:
        print("[WASTAGE CORRECTION] WARNING: No avl_corrected_sales columns found  using 0")
        Final_Plan['Wastage_Avg_4Wk_Sales'] = 0.0
        Final_Plan['Wastage_Avg_Weeks']      = ''

    #  Step 3: Salience already merged in Rev Loss step  reuse if present 
    # If Salience column is missing (Rev Loss file was absent), recompute it
    if 'Salience' not in Final_Plan.columns:
        _sku_subcat_wt = (
            Final_Plan[['SKU Class Prod', 'sub category']]
            .drop_duplicates(subset=['SKU Class Prod'])
        )
        bp_sal_wt = (
            base_plan_grouped[['hub_name', 'SKU Class Prod', 'day', 'BasePlan']]
            .merge(_sku_subcat_wt, on='SKU Class Prod', how='left')
        )
        bp_subcat_day_wt = (
            bp_sal_wt.groupby(['hub_name', 'sub category', 'day'], as_index=False)['BasePlan']
            .sum()
            .rename(columns={'BasePlan': 'subcat_day_plan'})
        )
        bp_subcat_day_wt['subcat_total'] = bp_subcat_day_wt.groupby(
            ['hub_name', 'sub category'])['subcat_day_plan'].transform('sum')
        bp_subcat_day_wt['Salience'] = np.where(
            bp_subcat_day_wt['subcat_total'] > 0,
            bp_subcat_day_wt['subcat_day_plan'] / bp_subcat_day_wt['subcat_total'],
            np.nan,
        )
        _n_days_wt = bp_subcat_day_wt.groupby(
            ['hub_name', 'sub category'])['day'].transform('count')
        bp_subcat_day_wt['Salience'] = bp_subcat_day_wt['Salience'].fillna(1.0 / _n_days_wt)
        Final_Plan = Final_Plan.merge(
            bp_subcat_day_wt[['hub_name', 'sub category', 'day', 'Salience']],
            on=['hub_name', 'sub category', 'day'],
            how='left',
        )

    #  Step 4: Override Final_Plan for wastage-flagged rows 
    # min(Final_Plan, Wastage_Avg_4Wk_Sales  Salience)  never go above current plan
    _wt_salience_plan = (Final_Plan['Wastage_Avg_4Wk_Sales'] * Final_Plan['Salience']).round(0)
    Final_Plan['Final_Plan'] = np.where(
        Final_Plan['is_wastage_uplift'],
        np.minimum(
            pd.to_numeric(Final_Plan['Final_Plan'], errors='coerce').fillna(0),
            pd.to_numeric(_wt_salience_plan, errors='coerce').fillna(0),
        ),
        Final_Plan['Final_Plan'],
    )

    _wt_flagged = Final_Plan['is_wastage_uplift'].sum()
    print(f"[WASTAGE CORRECTION] Rows corrected  : {_wt_flagged}")
    print(f"[WASTAGE CORRECTION] Rows unchanged  : {len(Final_Plan) - _wt_flagged}")
    print(f"[WASTAGE CORRECTION] Sample (flagged rows):")
    print(Final_Plan[Final_Plan['is_wastage_uplift']][
        ['hub_name', 'SKU Class Prod', 'day',
         'Wastage_Avg_4Wk_Sales', 'Salience', 'Final_Plan']
    ].head(8).to_string(index=False))





# %%
# Final_Plan.to_clipboard()

# %%
# =============================================================================
# NEW HUB WATCH  FF Input
# Local-only summary to avoid any Google Sheet dependency.
# =============================================================================

_ff_df   = hub_changes_df.copy()

# Normalise columns
_ff_df.columns = _ff_df.columns.str.strip()
_ff_df['Hub_name']   = _ff_df['Hub_name'].astype(str).str.strip()
_ff_df['Type']       = _ff_df['Type'].astype(str).str.strip()
_ff_df['Start_date'] = pd.to_datetime(_ff_df['Start_date'], errors='coerce')

_today_ts   = pd.Timestamp.today().normalize()
_watch_types = ['New Hub', 'KML Remapping']
_watched = _ff_df[
    (_ff_df['Type'].isin(_watch_types)) &
    (_ff_df['Start_date'].notna()) &
    ((_ff_df['Start_date'] - _today_ts).dt.days.abs() <= 15)
].copy()

print(f"\n[HUB WATCH] Entries within 15 days of today ({_today_ts.date()}): {len(_watched)}")

if _watched.empty:
    print("[HUB WATCH] No matching entries found.")
else:
    for _type in _watch_types:
        _type_df = _watched[_watched['Type'] == _type].copy()
        if _type_df.empty:
            print(f"[HUB WATCH] {_type}: none within 15 days.")
            continue
        _hub_names = set(_type_df['Hub_name'].str.lower())
        _fp_sub = Final_Plan[
            Final_Plan['hub_name'].astype(str).str.strip().str.lower().isin(_hub_names)
        ].copy()
        print(f"\n[HUB WATCH] {_type}: {len(_type_df)} entries")
        if _fp_sub.empty:
            print(f"[HUB WATCH] {_type}: no Final_Plan rows matched. Hubs: {_type_df['Hub_name'].tolist()}")
        else:
            _summary = (
                _fp_sub.groupby('hub_name', as_index=False).agg(
                    Final_Plan_Sum = ('Final_Plan', 'sum'),
                    Base_Plan_Sum  = ('Base_Plan (qty)', 'sum'),
                )
            )
            _summary['Delta'] = np.where(
                _summary['Final_Plan_Sum'] != 0,
                (_summary['Final_Plan_Sum'] - _summary['Base_Plan_Sum']) / _summary['Final_Plan_Sum'],
                np.nan
            ).round(4)
            _start_map = _type_df.set_index(_type_df['Hub_name'].str.lower())['Start_date'].to_dict()
            _summary['Start_date'] = _summary['hub_name'].str.lower().map(_start_map).dt.date
            print(_summary[['hub_name', 'Start_date', 'Final_Plan_Sum', 'Base_Plan_Sum', 'Delta']]
                  .to_string(index=False))


# =============================================================================
# DAY-LEVEL PLAN ADJUSTMENT
# Reads conditions from "Consistent Issues Logic" sheet, same tab, cols JL.
# Sheet layout (rows 3 & 5, day-level label at col I, thresholds at J,K,L):
#   Col J = Attainment | Col K = Availability | Col L = Vol Bucket
#
# For each hubSKUday row, check conditions across ALL last 4 complete weeks.
# Day_RL_Instances / Day_WT_Instances = number of weeks all conditions were met.
# Adjustment and Google Sheet logging only applied where Instances >= 3.
#
# Rev Loss: Final_Plan = max(Final_Plan, latest clean adj_avl_sales)
# Wastage : Final_Plan = min(Final_Plan, latest clean adj_avl_sales)
# "Latest clean" = most recent week where adjusted_avl_corrected_sales != 'L'
# =============================================================================

# -- Read day-level thresholds (label at col I=8, thresholds at J,K,L = 9,10,11) --
_rl_day_att_op, _rl_day_att_val = _parse_threshold(_rl_row[9])   # Col J: Attainment
_rl_day_avl_op, _rl_day_avl_val = _parse_threshold(_rl_row[10])  # Col K: Availability
_rl_day_vol_op, _rl_day_vol_val = _parse_threshold(_rl_row[11])  # Col L: Vol Bucket

_wt_day_att_op, _wt_day_att_val = _parse_threshold(_wt_row[9])   # Col J: Attainment
_wt_day_avl_op, _wt_day_avl_val = _parse_threshold(_wt_row[10])  # Col K: Availability
_wt_day_vol_op, _wt_day_vol_val = _parse_threshold(_wt_row[11])  # Col L: Vol Bucket

print(f"\n[Config Day] Rev Loss  Attainment {_rl_day_att_op}{_rl_day_att_val} | "
      f"Availability {_rl_day_avl_op}{_rl_day_avl_val} | Vol {_rl_day_vol_op}{_rl_day_vol_val}")
print(f"[Config Day] Wastage   Attainment {_wt_day_att_op}{_wt_day_att_val} | "
      f"Availability {_wt_day_avl_op}{_wt_day_avl_val} | Vol {_wt_day_vol_op}{_wt_day_vol_val}")

# -- Consecutive streak from latest week (same logic as week-level) ------------
# Start from the most recent week. If it passes, check the previous week.
# Stop at the first week that fails. Count = unbroken streak length.
_base_plan_num = pd.to_numeric(Final_Plan['Base_Plan (qty)'], errors='coerce')
_latest_week_str = str(int(_last_4_weeks[-1]))

# Discover all weeks present via avl_corrected_sales_{w} columns, latest first
_all_day_weeks = sorted(
    set(col.split('_')[-1] for col in Final_Plan.columns if col.startswith('avl_corrected_sales_')),
    key=lambda x: int(x),
    reverse=True   # latest week first
)

_rl_streak = pd.Series(0, index=Final_Plan.index)
_wt_streak = pd.Series(0, index=Final_Plan.index)

# Rows still in the running (haven't hit a failing week yet)
_rl_still_passing = pd.Series(True, index=Final_Plan.index)
_wt_still_passing = pd.Series(True, index=Final_Plan.index)

for _ws in _all_day_weeks:
    _sales_col = f"avl_corrected_sales_{_ws}"
    _avail_col = f"simple_availability_{_ws}"

    if _sales_col not in Final_Plan.columns or _avail_col not in Final_Plan.columns:
        # Treat missing week as a failure  break streak for all rows
        _rl_still_passing[:] = False
        _wt_still_passing[:] = False
        break

    _s   = pd.to_numeric(Final_Plan[_sales_col], errors='coerce')
    _a   = pd.to_numeric(Final_Plan[_avail_col], errors='coerce')
    _att = pd.Series(
        np.where(_base_plan_num > 0, _s / _base_plan_num, np.nan),
        index=Final_Plan.index
    )

    _rl_passes_this_week = (
        _apply_op(_att, _rl_day_att_op, _rl_day_att_val) &
        _apply_op(_a,   _rl_day_avl_op, _rl_day_avl_val) &
        _apply_op(_s,   _rl_day_vol_op, _rl_day_vol_val)
    )
    _wt_passes_this_week = (
        _apply_op(_att, _wt_day_att_op, _wt_day_att_val) &
        _apply_op(_a,   _wt_day_avl_op, _wt_day_avl_val) &
        _apply_op(_s,   _wt_day_vol_op, _wt_day_vol_val)
    )

    # Only count if the row is still in an unbroken streak
    _rl_streak += (_rl_still_passing & _rl_passes_this_week).astype(int)
    _wt_streak += (_wt_still_passing & _wt_passes_this_week).astype(int)

    # Break streak for rows that failed this week
    _rl_still_passing = _rl_still_passing & _rl_passes_this_week
    _wt_still_passing = _wt_still_passing & _wt_passes_this_week

    # If no row is still passing, no need to check earlier weeks
    if not _rl_still_passing.any() and not _wt_still_passing.any():
        break

Final_Plan['Day_RL_Instances'] = _rl_streak
Final_Plan['Day_WT_Instances'] = _wt_streak

# -- Latest clean adjusted_avl_corrected_sales (most recent non-'L' week) -----
_adj_weeks_rev = [
    str(int(w)) for w in reversed(_last_4_weeks)
    if f"adjusted_avl_corrected_sales_{int(w)}" in Final_Plan.columns
]
Final_Plan['_latest_clean_adj'] = np.nan
for _wk in _adj_weeks_rev:
    _col_adj  = f"adjusted_avl_corrected_sales_{_wk}"
    _num_vals = pd.to_numeric(Final_Plan[_col_adj], errors='coerce')
    _still_nan = Final_Plan['_latest_clean_adj'].isna()
    Final_Plan.loc[_still_nan, '_latest_clean_adj'] = _num_vals[_still_nan]

# -- Apply Rev Loss: only where Day_RL_Instances >= 3 -------------------------
_rl_day_mask = (
    (Final_Plan['Day_RL_Instances'] >= 3) &
    Final_Plan['_latest_clean_adj'].notna()
)
Final_Plan['is_day_revloss_flag'] = _rl_day_mask

Final_Plan.loc[_rl_day_mask, 'Final_Plan'] = np.maximum(
    pd.to_numeric(Final_Plan.loc[_rl_day_mask, 'Final_Plan'], errors='coerce').fillna(0),
    Final_Plan.loc[_rl_day_mask, '_latest_clean_adj']
).round()

# -- Apply Wastage: only where Day_WT_Instances >= 3 --------------------------
_wt_day_mask = (
    (Final_Plan['Day_WT_Instances'] >= 3) &
    Final_Plan['_latest_clean_adj'].notna()
)
Final_Plan['is_day_wastage_flag'] = _wt_day_mask

Final_Plan.loc[_wt_day_mask, 'Final_Plan'] = np.minimum(
    pd.to_numeric(Final_Plan.loc[_wt_day_mask, 'Final_Plan'], errors='coerce').fillna(0),
    Final_Plan.loc[_wt_day_mask, '_latest_clean_adj']
).round()

# -- Drop temp column ---------------------------------------------------------
Final_Plan.drop(columns=['_latest_clean_adj'], inplace=True)

print(f"\n[Day-Level] Rev Loss rows adjusted (instances 3): {_rl_day_mask.sum()}")
print(f"[Day-Level] Wastage  rows adjusted (instances 3): {_wt_day_mask.sum()}")

# ---- Save local validation summaries instead of writing to Google Sheets ----
_civ_ts  = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

_COL_HEADERS = ["City", "Hub", "SKU Class Prod", "Day", "Initial_Final_Plan", "Final_Plan"]

def _section_rows(label, df):
    """Return rows for one local validation section."""
    rows = [[f"--- {label} ---", "", "", "", "", ""],
            [f"Run: {_civ_ts}", "", "", "", "", ""],
            _COL_HEADERS]
    _view = df[['city_name', 'hub_name', 'SKU Class Prod', 'day',
                'Initial_Final_Plan', 'Final_Plan']].copy()
    _view = _view.sort_values(['hub_name', 'SKU Class Prod', 'day'])
    for _, _r in _view.iterrows():
        rows.append([
            str(_r['city_name']),
            str(_r['hub_name']),
            str(_r['SKU Class Prod']),
            str(_r['day']),
            float(_r['Initial_Final_Plan']) if pd.notna(_r['Initial_Final_Plan']) else "",
            float(_r['Final_Plan']) if pd.notna(_r['Final_Plan']) else "",
        ])
    rows.append([""])
    return rows

_all_civ_rows = [[f"Consistent Issues Validation  Last run: {_civ_ts}", "", "", "", "", ""], [""]]

_wrl_df = Final_Plan[Final_Plan.get('is_rev_loss_uplift', pd.Series(False, index=Final_Plan.index)) == True].copy()
_wwt_df = Final_Plan[Final_Plan.get('is_wastage_uplift', pd.Series(False, index=Final_Plan.index)) == True].copy()
_drl_df = Final_Plan[Final_Plan.get('is_day_revloss_flag', pd.Series(False, index=Final_Plan.index)) == True].copy()
_dwt_df = Final_Plan[Final_Plan.get('is_day_wastage_flag', pd.Series(False, index=Final_Plan.index)) == True].copy()

_all_civ_rows += _section_rows("1. WEEK-LEVEL REV LOSS (is_rev_loss_uplift)", _wrl_df)
_all_civ_rows += _section_rows("2. WEEK-LEVEL WASTAGE (is_wastage_uplift)", _wwt_df)
_all_civ_rows += _section_rows("3. DAY-LEVEL REV LOSS (instances 3)", _drl_df)
_all_civ_rows += _section_rows("4. DAY-LEVEL WASTAGE (instances 3)", _dwt_df)

_civ_path = os.path.join(BASELINE_CURRENT_FORECASTING_DIR, f"Consistent_Issues_Validation_{_today}.csv")
pd.DataFrame(_all_civ_rows).to_csv(_civ_path, index=False, header=False)
print(f"\n[CIV] Local validation output written to: {_civ_path}")

# Check KAM's simple_flag_when_SP_0_withoutclusterv2 at each stage
# import pandas as pd
#%%
# Final_Plan.to_clipboard()



# %%


# %%



# %%




Final_Plan.to_csv('Final_Plan_Old.csv', index=False)
