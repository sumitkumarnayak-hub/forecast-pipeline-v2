import config_paths
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

import os
import pyreadr
import pandas as pd
import numpy as np 
import gspread
import io
import threading
from datetime import datetime, timedelta
from gspread_dataframe import set_with_dataframe
from google_auth import client
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from config_paths import (
    JSON_KEYFILE_PATH,
    DRIVE_FOLDER_ID,
    BASELINE_OUTPUT_PARQUET_FOLDER_ID,
    FF_OUTPUT_PARQUET_FOLDER_ID,
    FF_OUTPUT_EXCEL_FOLDER_ID,
    GOOGLE_CREDENTIALS_DICT,
)


def normalize_common_aliases(df: pd.DataFrame) -> pd.DataFrame:
    """Compatibility shim for mixed legacy/current export names without changing business logic."""
    df = df.copy()

    alias_map = {
        'sku class prod': ['sku class prod', 'SKU Class Prod'],
        'SKU Class Prod': ['sku class prod', 'SKU Class Prod'],
        'cut class': ['Cut class'],
        'Cut class': ['Cut class'],
        'base_plan': ['Base_plan'],
        'Base_plan': ['Base_plan'],
        'BasePlan': ['Base_plan'],
        'Base Plan': ['Base_plan'],
        'base plan': ['Base_plan'],
        'hub name': ['hub_name'],
        'hub_name': ['hub_name'],
        'city name': ['city_name'],
        'city_name': ['city_name'],
        'plan flag': ['Plan Flag'],
        'Plan Flag': ['Plan Flag'],
        'product id': ['Product id'],
        'Product id': ['Product id'],
        'product_id': ['Product id'],
        'sub-category': ['Sub-category'],
        'sub category': ['Sub-category'],
        'Sub-category': ['Sub-category'],
    }

    for src, targets in alias_map.items():
        if src in df.columns:
            for target in targets:
                if target not in df.columns:
                    df[target] = df[src]

    if 'sku class prod' not in df.columns and 'SKU Class Prod' in df.columns:
        df['sku class prod'] = df['SKU Class Prod']
    if 'SKU Class Prod' not in df.columns and 'sku class prod' in df.columns:
        df['SKU Class Prod'] = df['sku class prod']
    if 'Base_plan' not in df.columns and 'BasePlan' in df.columns:
        df['Base_plan'] = df['BasePlan']
    if 'Base_plan' not in df.columns and 'r7_plan' in df.columns:
        df['Base_plan'] = df['r7_plan']
    if 'Base_plan' not in df.columns:
        df['Base_plan'] = 0

    return df


def load_latest_parquet_from_drive(sheet_key: str, folder_id: str = DRIVE_FOLDER_ID) -> pd.DataFrame:
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
    matching_files = [f for f in files if f['name'].lower().startswith(sheet_key.lower())]
    if matching_files:
        files = matching_files

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
    # Add date suffix to filename for FF outputs
    if folder_id == FF_OUTPUT_PARQUET_FOLDER_ID:
        date_str = datetime.now().strftime("%Y%m%d")
        if file_name.endswith('.parquet'):
            file_name = file_name.replace('.parquet', f'_{date_str}.parquet')
        else:
            file_name = f"{file_name}_{date_str}"
            
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


_upload_threads = []
def upload_df_to_drive_as_parquet_async(df: pd.DataFrame, file_name: str, folder_id: str):
    t = threading.Thread(target=upload_df_to_drive_as_parquet, args=(df, file_name, folder_id))
    t.daemon = False
    _upload_threads.append(t)
    t.start()
    print(f"[Drive Uploader] Started background upload for {file_name}...")

def wait_for_all_uploads():
    for t in _upload_threads:
        if t.is_alive():
            t.join()

def upload_sheets_to_drive_as_excel(sheets: dict, file_name: str, folder_id: str):
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
            print(f"[Drive Uploader] Deleting existing file: {f['name']} ({f['id']})")
            try:
                service.files().delete(fileId=f['id'], supportsAllDrives=True).execute()
            except Exception as del_err:
                print(f"[Drive Uploader] WARNING: Could not delete {f['name']}: {del_err}")
                
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
            for sheet_name, df in sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        excel_buffer.seek(0)
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(excel_buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resumable=True)
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name',
            supportsAllDrives=True
        ).execute()
        print(f"[Drive Uploader] SUCCESS: Uploaded {uploaded_file.get('name')} to Drive (ID: {uploaded_file.get('id')})")
    except Exception as e:
        print(f"[Drive Uploader] ERROR uploading {file_name}: {e}")

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Hub level Suggestion' (columns A to F) from Google Sheet 'Hub_level_planning'
# Current Input: Loaded directly from Google Drive ('Hub_level_plan.parquet') from folder ID BASELINE_OUTPUT_PARQUET_FOLDER_ID
logging.info("Starting FF Hub Automation step...")
logging.info("Loading Hub_level_plan parquet...")
Hub_suggestion = normalize_common_aliases(load_latest_parquet_from_drive("Hub_level_plan", BASELINE_OUTPUT_PARQUET_FOLDER_ID))
Hub_suggestion = Hub_suggestion.rename(columns={'Week': 'Weeknum'})

# Check duplicates on key columns (make sure names match your sheet headers exactly)
# Show summary
print(Hub_suggestion.describe(include="all"))
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'P-L Master' from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('pl_master_*.parquet') from folder ID DRIVE_FOLDER_ID
logging.info("Loading pl_master parquet...")
Master_df = normalize_common_aliases(load_latest_parquet_from_drive("pl_master", DRIVE_FOLDER_ID))
print(Master_df[Master_df.duplicated(subset=['Channel', 'City', 'Product id'])])


# Display DataFrame
Master_df.describe(include='all')
# Create a dictionary: {SKU Class Prod: Cut class}
sku_to_cutclass = Master_df.set_index('SKU Class Prod')['Cut class'].to_dict()

# Map the Cut class to DP_suggestion using sku class prod
Hub_suggestion['Cut class'] = Hub_suggestion['sku class prod'].map(sku_to_cutclass)
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as 'config_paths.FF_TEST_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Hub_suggestion.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Hub_suggestion, "Hub_suggestion.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
Hub_suggestion.describe(include='all')

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Hub Sku Master' (columns A to O) from Google Sheet 'Hub_level_planning'
# Current Input: Loaded directly from Google Drive ('Hub_sku_master_*.parquet') from folder ID DRIVE_FOLDER_ID
Hub_Master = normalize_common_aliases(load_latest_parquet_from_drive("Hub_sku_master", DRIVE_FOLDER_ID))  # First row as header
print(Hub_Master[Hub_Master.duplicated(subset=['hub_name', 'sku class prod'])])
# Display DataFrame
Hub_Master.describe(include='all')
# Hub_Master[Hub_Master.duplicated(subset=['hub_name', 'sku class # prod'])].to_clipboard()
day_map = {
    "Active_Flag_Mon": "Mon",
    "Active_Flag_Tue": "Tue",
    "Active_Flag_Wed": "Wed",
    "Active_Flag_Thu": "Thu",
    "Active_Flag_Fri": "Fri",
    "Active_Flag_Sat": "Sat",
    "Active_Flag_Sun": "Sun"
}

hub_master_long = Hub_Master.melt(
    id_vars=["city_name", "hub_name", "sku class prod", "Plan Flag"],
    value_vars=day_map.keys(),
    var_name="flag_col",
    value_name="active"
)
# Map flag column to actual day name
hub_master_long["day"] = hub_master_long["flag_col"].map(day_map)

hub_master_long["active"] = hub_master_long["active"].astype(int)


active_skus = hub_master_long[
    ["city_name", "hub_name", "sku class prod", "day","Plan Flag", "active"]
]

active_skus = active_skus[active_skus["Plan Flag"] != "I"]


# active_skus.to_clipboard()
merged = active_skus.merge(
    Hub_suggestion[["hub_name", "sku class prod", "day","Cut class","Base_plan"]],
    on=["hub_name", "sku class prod", "day"],
    how="left",
    indicator=True
)

dupes = hub_master_long[
    hub_master_long.duplicated(subset=["city_name", "hub_name", "sku class prod", "day"], keep=False)
].sort_values(["city_name", "hub_name", "sku class prod", "day"])

if not dupes.empty:
    print(f"Found {len(dupes)} duplicate rows in hub_master_long:")
    print(dupes)
else:
    print("No duplicates found.")
# Active SKUs present in Hub_suggestion
filtered_hub_level_suggestion = merged.query("_merge == 'both'").drop(columns="_merge")
filtered_hub_level_suggestion.loc[filtered_hub_level_suggestion["active"] == 0, "Base_plan"] = 0
# Active SKUs missing from Hub_suggestion
missing_active_skus = merged.query("_merge == 'left_only'").drop(columns="_merge")
if not missing_active_skus.empty:
    logging.warning(
        "Found %s active SKUs missing in Hub_suggestion; continuing with zero Base_plan for those rows.",
        len(missing_active_skus)
    )
    missing_active_skus = missing_active_skus.copy()
    missing_active_skus["Base_plan"] = pd.to_numeric(missing_active_skus["Base_plan"], errors='coerce').fillna(0)
    missing_active_skus["Cut class"] = missing_active_skus["Cut class"].fillna(np.nan)
    filtered_hub_level_suggestion = pd.concat(
        [filtered_hub_level_suggestion, missing_active_skus[filtered_hub_level_suggestion.columns]],
        ignore_index=True,
        sort=False
    )
else:
    print("All active SKUs are present in Hub_suggestion.")

# missing_active_skus.to_clipboard()
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as Excel file 'FF_FILTERED_HUB_SUGGESTION_XLSX_PATH'
# Current Output: Uploaded directly to Google Drive as 'filtered_hub_level_suggestion.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(filtered_hub_level_suggestion.drop(columns=["Plan Flag", "active"]), "filtered_hub_level_suggestion.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)

# Step 1: Generate a DataFrame with 4 weeks of dates
start_date = datetime.today() - timedelta(days=datetime.today().weekday())  # Last Monday
end_date = start_date + timedelta(weeks=5, days=6)  # Next 2 weeks Sunday

date_list = pd.date_range(start=start_date, end=end_date)
date_df = pd.DataFrame({"date": date_list})
date_df["day"] = date_df["date"].dt.strftime("%a")  # Get weekday names

Hub_suggestion["day"] = Hub_suggestion["day"].astype(str)
date_df["day"] = date_df["day"].astype(str)

# Step 2: Merge with original DataFrame on "day"
final_df = filtered_hub_level_suggestion.merge(date_df, on="day", how="left")

# Step 3: Format date
final_df["date"] = final_df["date"].dt.strftime("%Y-%m-%d")
final_df["Base_plan"] = pd.to_numeric(final_df["Base_plan"], errors='coerce')
print(final_df["Base_plan"].sum())
final_df.describe(include='all')
# New_Hub_Launch = Hub_level_planning.worksheet("New_Hub_Launch")

# # Get all values from A to L (1st to 12th column)
# data = New_Hub_Launch.get("A:F")  # Fetch only columns A to L

# # Convert to DataFrame
# Hub_Launch = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# # Display DataFrame
# Hub_Launch.describe(include='all')
# final_df['date'] = pd.to_datetime(final_df['date'])
# Hub_Launch['Launch_Date'] = pd.to_datetime(Hub_Launch['Launch_Date'])
# existing_hubs = set(final_df['hub_name'])
# Hub_Launch = Hub_Launch[~Hub_Launch['New_Hub'].isin(existing_hubs)].copy()
# # Step 2: Merge on Source Hub
# merged = final_df.merge(
#     Hub_Launch,
#     left_on=['hub_name', 'city_name'],
#     right_on=['Source Hub', 'city_name'],
#     how='inner'
# )
# # Step 3: Filter dates strictly before launch
# merged = merged[merged['Launch_Date'] < merged['date']]
# merged['Percentage'] = merged['Percentage'].astype(str).str.replace('%', '').astype(float)
# merged['volume_transferred'] = np.round(merged['Base_plan'] * (merged['Percentage']), 0)
# # Step 5: Update source hub Base_plan
# # First, sum total transferred per source hub per SKU/date
# source_updates = (
#     merged
#     .groupby(['city_name', 'hub_name', 'sku class prod', 'day', 'date'], as_index=False)
#     .agg(total_transferred=('volume_transferred', 'sum'),
#          original_plan=('Base_plan', 'first'))
# )
# source_updates['volume_remaining'] = np.maximum(source_updates['original_plan'] - source_updates['total_transferred'],0)

# # Merge back to update
# final_df = final_df.merge(
#     source_updates[['city_name', 'hub_name', 'sku class prod', 'day', 'date', 'volume_remaining']],
#     on=['city_name', 'hub_name', 'sku class prod', 'day', 'date'],
#     how='left'
# )
# final_df['Base_plan'] = np.where(
#     final_df['volume_remaining'].notna(),
#     final_df['volume_remaining'],
#     final_df['Base_plan']
# )
# final_df.drop(columns=['volume_remaining'], inplace=True)
# # Step 6: Create new hub rows
# new_hub_rows = (
#     merged
#     .groupby(['city_name', 'New_Hub', 'sku class prod', 'Cut class', 'day', 'date'], as_index=False)
#     ['volume_transferred'].sum()
#     .rename(columns={'New_Hub': 'hub_name', 'volume_transferred': 'Base_plan'})
# )
# # Step 7: Add zero-volume rows for completeness
# all_combos = final_df[['city_name', 'sku class prod', 'Cut class', 'day', 'date']].drop_duplicates()
# new_hub_ids = Hub_Launch[['city_name', 'New_Hub']].drop_duplicates().rename(columns={'New_Hub': 'hub_name'})
# zero_volume_rows = (
#     all_combos.assign(Base_plan=0)
#     .merge(new_hub_ids, on='city_name', how='inner')
# )
# # Merge transferred volumes with zero-volume base
# new_hub_rows = pd.concat([new_hub_rows, zero_volume_rows], ignore_index=True).drop_duplicates(
#     subset=['city_name', 'hub_name', 'sku class prod', 'Cut class', 'day', 'date'],
#     keep='first'
# )

# # Step 8: Append to final_df
# final_df = pd.concat([final_df, new_hub_rows], ignore_index=True)
# final_df.sort_values(['city_name', 'hub_name', 'sku class prod', 'date'], inplace=True)
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_HUB_LEVEL_PLAN_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'final_df.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(final_df, "final_df.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
# # Select the specific sheet/tab by its name
# worksheet = spreadsheet.worksheet("Festive Factor")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:G")  # Fetch only columns A to L

# # Convert to DataFrame
# festive_factor = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# print(festive_factor[festive_factor.duplicated(subset=['city_name', 'Cut class', 'date'])])

# # Display DataFrame
# festive_factor.describe()
# # Ensure date format matches
# festive_factor["date"] = pd.to_datetime(festive_factor["date"]).dt.strftime("%Y-%m-%d")
# final_df["date"] = pd.to_datetime(final_df["date"]).dt.strftime("%Y-%m-%d")

# # Merge on 'date', 'Cut class', and 'city_name'
# FF_corrected_plan = final_df.merge(festive_factor, on=["date", "city_name", "Cut class"], how="left")
# FF_corrected_plan.to_csv(config_paths.FF_CHECK_CSV_PATH)


# def parse_festive_factor(val):
#     if isinstance(val, str) and "%" in val:
#         return float(val.replace("%", "")) / 100
#     try:
#         return float(val)
#     except:
#         return 0  # Or np.nan if you prefer to track invalids

# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Festive Factor"].apply(parse_festive_factor)


# FF_corrected_plan["Base_plan"] = pd.to_numeric(FF_corrected_plan["Base_plan"], errors="coerce")





# worksheet = spreadsheet.worksheet("Festive Factor_Hub")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:I")  # Fetch only columns A to L

# # Convert to DataFrame
# festive_factor_hub = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# print(festive_factor[festive_factor.duplicated(subset=['city_name', 'Cut class', 'date'])])

# # Display DataFrame
# festive_factor.describe()
# festive_long = festive_factor_hub.melt(
#     id_vars=["city_name", "Hub"],
#     var_name="date",
#     value_name="Hub_Festive_Factor"
# )

# FF_corrected_plan = FF_corrected_plan.merge(
#     festive_long,
#     left_on=["city_name", "hub_name", "date"],
#     right_on=["city_name", "Hub", "date"],
#     how="left"
# )
# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Hub_Festive_Factor"].fillna(FF_corrected_plan["Festive Factor"])

# FF_corrected_plan["Base_plan"] = pd.to_numeric(FF_corrected_plan["Base_plan"], errors="coerce")
# FF_corrected_plan["Festive Factor"] = pd.to_numeric(FF_corrected_plan["Festive Factor"], errors="coerce")

# # Fill NaN with 0 (so no errors in multiplication)
# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Festive Factor"].fillna(0)

# # Step 1: Continuous festive-adjusted plan
# FF_corrected_plan["raw_final_plan"] = FF_corrected_plan["Base_plan"] * (1 + FF_corrected_plan["Festive Factor"])

# # Step 2: Initial rounding (nearest integer)
# FF_corrected_plan["final_plan"] = np.round(FF_corrected_plan["raw_final_plan"]).astype(int)

# # Step 3: Decimal remainders for reconciliation
# FF_corrected_plan["remainder"] = FF_corrected_plan["raw_final_plan"] - FF_corrected_plan["final_plan"]


# # Step 4: Reconciliation loop city by city
# for city, group in FF_corrected_plan.groupby(["city_name", "Sub-category", "date"]):
#     target = round(group["raw_final_plan"].sum())   # exact city-level festive target
#     current = group["final_plan"].sum()             # what we have after rounding
#     diff = int(target - current)

#     if diff > 0:
#         # Add +1 to hubs with largest remainders
#         idx = group["remainder"].nlargest(diff).index
#         FF_corrected_plan.loc[idx, "final_plan"] += 1

#     elif diff < 0:
#         # Subtract -1 from hubs with smallest remainders
#         idx = group["remainder"].nsmallest(abs(diff)).index
#         FF_corrected_plan.loc[idx, "final_plan"] -= 1

# # # Cleanup helper columns
# # FF_corrected_plan = FF_corrected_plan.drop(columns=["raw_final_plan", "remainder"])

# print(FF_corrected_plan["final_plan"].sum())
# FF_corrected_plan.describe(include="all")
# FF_corrected_plan.to_csv(config_paths.FF_TOTAL_PLAN_CSV_PATH,index=False)
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Local Excel file 'Festive.xlsx' (or via URL)
# Current Input: Loaded directly from Google Drive ('Festive*.parquet') from folder ID 17mYoNPGhmhw4MlZoE24gWG2onA9WmFya
try:
    hub_festive_factor = load_latest_parquet_from_drive("Festive", "17mYoNPGhmhw4MlZoE24gWG2onA9WmFya")
except Exception as e:
    # Try alternate naming in case it's named 'Hub_Festive'
    hub_festive_factor = load_latest_parquet_from_drive("Hub_Festive", "17mYoNPGhmhw4MlZoE24gWG2onA9WmFya")
    
# Ensure only required columns if they exist
required_cols = ["hub_name", "Cut class", "date", "festive_factor"] # Add other columns if known
# Let pandas handle columns if the parquet matches the expected shape.

# hub_festive_factor.head()
print(hub_festive_factor[hub_festive_factor.duplicated(subset=['hub_name', 'Cut class', 'date'])])
# # Open the Google Sheet by URL
# Festive = client.open_by_url(config_paths.FF_FESTIVE_FILE_PATH)


# # Select the specific sheet/tab by its name
# worksheet = Festive.worksheet("Hub Festive")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:H")  # Fetch only columns A to L

# # Convert to DataFrame
# hub_festive_factor = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# print(hub_festive_factor[hub_festive_factor.duplicated(subset=['hub_name', 'Cut class', 'date'])])

# # Display DataFrame
# hub_festive_factor.describe()
hub_festive_factor["date"] = pd.to_datetime(hub_festive_factor["date"]).dt.strftime("%Y-%m-%d")
final_df["date"] = pd.to_datetime(final_df["date"]).dt.strftime("%Y-%m-%d")

merge_cols = ["date", "hub_name", "Cut class"]
if "city_name" in hub_festive_factor.columns:
    merge_cols.append("city_name")

# Merge on 'date', 'Cut class', and 'city_name' (if present)
FF_corrected_plan = final_df.merge(hub_festive_factor, on=merge_cols, how="left")
# FF_corrected_plan.to_csv(config_paths.FF_CHECK_CSV_PATH)


# --- OLD CODE PRESERVED AS PER REQUEST ---
# def parse_festive_factor(val):
#     if isinstance(val, str) and "%" in val:
#         return float(val.replace("%", "")) / 100
#     try:
#         return float(val)
#     except:
#         return 0  # Or np.nan if you prefer to track invalids
# FF_corrected_plan["Hub level Festive Factor"] = FF_corrected_plan["Hub level Festive Factor"].apply(parse_festive_factor)
# ==============================
def vectorize_festive_factor(series):
    s = series.astype(str).str.strip()
    is_pct = s.str.contains('%', na=False)
    s_clean = s.str.replace('%', '', regex=False)
    num = pd.to_numeric(s_clean, errors='coerce')
    num = np.where(series.notna() & num.isna(), 0, num)
    return np.where(is_pct, num / 100, num)

FF_corrected_plan["Hub level Festive Factor"] = vectorize_festive_factor(FF_corrected_plan["Hub level Festive Factor"])




FF_corrected_plan["Hub level Festive Factor"] = pd.to_numeric(FF_corrected_plan["Hub level Festive Factor"], errors="coerce")

# Fill NaN with 0 (so no errors in multiplication)
FF_corrected_plan["Hub level Festive Factor"] = FF_corrected_plan["Hub level Festive Factor"].fillna(0)

# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Hub_Festive_Factor"].fillna(FF_corrected_plan["Festive Factor"])
# Step 1: Continuous festive-adjusted plan
FF_corrected_plan["raw_festive_plan"] = FF_corrected_plan["Base_plan"] * (1 + FF_corrected_plan["Hub level Festive Factor"])

# Step 2: Initial rounding (nearest integer)
FF_corrected_plan["final_plan"] = np.round(FF_corrected_plan["raw_festive_plan"]).astype(int)

# Step 3: Decimal remainders for reconciliation
FF_corrected_plan["remainder"] = FF_corrected_plan["raw_festive_plan"] - FF_corrected_plan["final_plan"]


# Step 4: Reconciliation loop city by city
# --- OLD CODE PRESERVED AS PER REQUEST ---
# for city, group in FF_corrected_plan.groupby(["hub_name", "Sub-category", "date"]):
#     target = round(group["raw_festive_plan"].sum())
#     current = group["final_plan"].sum()
#     diff = int(target - current)
#     if diff > 0:
#         idx = group["remainder"].nlargest(diff).index
#         FF_corrected_plan.loc[idx, "final_plan"] += 1
#     elif diff < 0:
#         idx = group["remainder"].nsmallest(abs(diff)).index
#         FF_corrected_plan.loc[idx, "final_plan"] -= 1
# ==============================
_grp1 = FF_corrected_plan.groupby(["hub_name", "Sub-category", "date"])
_target1 = _grp1["raw_festive_plan"].transform("sum").round()
_current1 = _grp1["final_plan"].transform("sum")
_diff1 = (_target1 - _current1).fillna(0).astype(int)

_rank_desc1 = _grp1["remainder"].rank(ascending=False, method="first")
_rank_asc1 = _grp1["remainder"].rank(ascending=True, method="first")

_add_mask1 = (_diff1 > 0) & (_rank_desc1 <= _diff1)
_sub_mask1 = (_diff1 < 0) & (_rank_asc1 <= _diff1.abs())

FF_corrected_plan["final_plan"] = FF_corrected_plan["final_plan"] + _add_mask1.astype(int) - _sub_mask1.astype(int)
# # Step 3: Calculate the fractional part (both for sale_plan and base_plan)
# FF_corrected_plan['fraction_sale'] = FF_corrected_plan['final_plan'] - FF_corrected_plan['rounded_final_plan']

# # Step 4: Calculate the difference between final_plan and sum of rounded_plan
# grouped = FF_corrected_plan.groupby(['city_name', 'sku class prod', 'date'])
# FF_corrected_plan['sum_rounded_sale'] = grouped['rounded_final_plan'].transform('sum')

# FF_corrected_plan['rounded_sale_festive'] = FF_corrected_plan["sum_rounded_sale"] + (FF_corrected_plan["sum_rounded_sale"] * FF_corrected_plan["Festive Factor"])

# FF_corrected_plan['difference_sale'] = (
#     FF_corrected_plan['rounded_sale_festive'] - FF_corrected_plan['sum_rounded_sale']
# ).astype(int)

# # Step 5: Adjust for differences
# def adjust_both_plans(group):
#     diff_sale = group['difference_sale'].iloc[0]

#     if diff_sale > 0:
#         top_sale = group[group['fraction_sale'] > 0].nlargest(diff_sale, 'fraction_sale')
#         group.loc[top_sale.index, 'rounded_final_plan'] += 1
#     elif diff_sale < 0:
#         bottom_sale = group[group['fraction_sale'] < 0].nsmallest(abs(diff_sale), 'fraction_sale')
#         group.loc[bottom_sale.index, 'rounded_final_plan'] -= 1

#     return group   # ✅ fixed indentation

# # Apply adjustment
# FF_corrected_plan = FF_corrected_plan.groupby(
#     ['city_name', 'sku class prod', 'date'], group_keys=False
# ).apply(adjust_both_plans)

# Finalize
# FF_corrected_plan['final_plan'] = FF_corrected_plan['rounded_final_plan']


print(FF_corrected_plan.columns)
# Step 4: Calculate Expected Final Plan at Cut Class Level
FF_corrected_plan["expected_final_plan"] = FF_corrected_plan.groupby(["city_name", "date", "Cut class"])["Base_plan"].transform("sum") * (1 + FF_corrected_plan["Hub level Festive Factor"])

# # Step 5: Calculate Sum of Final Plan at Cut Class Level
FF_corrected_plan["sum_final_plan"] = FF_corrected_plan.groupby(["city_name", "date", "Cut class"])["final_plan"].transform("sum")

# # Step 6: Compute Delta
FF_corrected_plan["delta"] = FF_corrected_plan["expected_final_plan"] - FF_corrected_plan["sum_final_plan"] #make it in % to know if changes need

# Calculate and print max and min of delta
max_delta = FF_corrected_plan["delta"].max()
min_delta = FF_corrected_plan["delta"].min()

print(f"Max Delta: {max_delta}")
print(f"Min Delta: {min_delta}")
print(FF_corrected_plan["final_plan"].sum())
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_CORRECTED_PLAN_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'FF_corrected_plan.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(FF_corrected_plan, "FF_corrected_plan.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
# Filter Master_df for only 'online' channel
Master_filtered = Master_df[
    (Master_df['Channel'] == 'Online') & 
    (Master_df['Order Type - pan india'] == 'E')
]


# Merge with filtered Master_df
Final_sale = pd.merge(
    FF_corrected_plan, 
    Master_filtered[['City', 'SKU Class Prod', 'Product id', 'Split %','DOC/Percentage_BufferFlag']], 
    left_on=['city_name', 'sku class prod'], 
    right_on=['City', 'SKU Class Prod'], 
    how="left"
)

# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_TEST_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_test.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_test.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)

# Display summary statistics
Final_sale.describe(include="all")
Final_sale['Split %1'] = Final_sale['Split %'].str.rstrip('%').astype(float) / 100
Final_sale['sale_plan'] = np.where(
    (Final_sale['final_plan'] == 1) & (Final_sale['Split %1'] > 0.2),
    1,
    round((Final_sale['final_plan'] * Final_sale['Split %1']).fillna(0))
)

Final_sale['base_plan'] = np.where(
    (Final_sale['Base_plan'] == 1) & (Final_sale['Split %1'] > 0.2),
    1,
    round((Final_sale['Base_plan'] * Final_sale['Split %1']).fillna(0))
)

# Print the totals
print(Final_sale['sale_plan'].sum())
print(Final_sale['base_plan'].sum())
# start_date = '2025-07-21'
# end_date = '2025-07-27'

# filtered_df = Final_sale[
#     (Final_sale['date'] >= start_date) & (Final_sale['date'] <= end_date)
# ]
# grouped_df = filtered_df.groupby(['city_name', 'Product id', 'day'], as_index=False)[ 'base_plan'].sum()


# filtered_master = Master_df[
#     (Master_df["Channel"] == "Online") & 
#     (Master_df["Order Type - pan india"] == "E")
# ]

# merged_df = DP_suggestion.merge(
#     filtered_master[["City", "SKU Class Prod", "Product id", "Split %"]],
#     on=["City",  "SKU Class Prod"],
#     how="left"
# )
# # merged_df.to_clipboard()
# # Step 1: Select required columns
# result_df = merged_df[[
#     "City", 
#     "Product id", 
#     "Base Plan",
#     "day",
#     "with Manual Checks", 
#     "Split %"
# ]].copy()

# result_df["Base Plan"] = pd.to_numeric(result_df["Base Plan"], errors="coerce")
# result_df["with Manual Checks"] = pd.to_numeric(result_df["with Manual Checks"], errors="coerce")

# # Step 3: Convert 'Split %' to float (from '37%' to 0.37)
# result_df["Split %"] = (
#     result_df["Split %"]
#     .str.replace("%", "", regex=False)
#     .astype(float) / 100
# )

# # Step 4: Calculate Base Plan after Split
# result_df["Base Plan after Split"] = round(result_df["with Manual Checks"] * result_df["Split %"])
# # Standardize column names for joining
# grouped_df.rename(columns={'city_name': 'City', 'base_plan': 'Hub_base_plan'}, inplace=True)

# # Merge on City, Product id, and day
# result_df = result_df.merge(
#     grouped_df[['City', 'Product id', 'day', 'Hub_base_plan']],
#     on=['City', 'Product id', 'day'],
#     how='left'
# )

# print(result_df['Base Plan after Split'].sum())
# print(result_df['Hub_base_plan'].sum())




# result_df["difference"] = abs(result_df["Base Plan after Split"] - result_df["Hub_base_plan"])
# # result_df.to_clipboard()
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Pricing' (columns A to D) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('Pricing_*.parquet') from folder ID DRIVE_FOLDER_ID
logging.info("Loading Pricing parquet...")
Product_price = load_latest_parquet_from_drive("Pricing", DRIVE_FOLDER_ID)  # First row as header

# Display DataFrame
Product_price.describe()
# Create a dictionary mapping (city_name, pr_id) to 'Updated Price'
price_data = Product_price.set_index(['city_name', 'pr_id'])['Updated Price'].to_dict()

# Map price data to Final_sale using city_name and Product id
# --- OLD CODE PRESERVED AS PER REQUEST ---
# Final_sale['Updated Price'] = Final_sale.apply(lambda row: price_data.get((row['city_name'], row['Product id'])), axis=1)
Final_sale['Updated Price'] = Final_sale.set_index(['city_name', 'Product id']).index.map(price_data.get)
Final_sale['Updated Price'] = Final_sale['Updated Price']
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_PRICE_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_price.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_price.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
# Display summary statistics
Final_sale.describe(include='all')

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'City_Map' (columns A to B) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('City_Map_*.parquet') from folder ID DRIVE_FOLDER_ID
city_map = load_latest_parquet_from_drive("City_Map", DRIVE_FOLDER_ID)

city_map = city_map.rename(columns={"Attribute": "hub_name"})



Final_sale = Final_sale.merge(city_map, on='hub_name', how='left')
Final_sale['Original_city'] = Final_sale['Original_city'].fillna(Final_sale['city_name'])

Final_sale.describe(include='all')
# Ensure columns are numeric
Final_sale['sale_plan'] = pd.to_numeric(Final_sale['sale_plan'], errors='coerce')
Final_sale['base_plan'] = pd.to_numeric(Final_sale['base_plan'], errors='coerce')
# Final_sale['Updated Price'] = pd.to_numeric(Final_sale['Updated Price'], errors='coerce')
Final_sale['Updated Price'] = Final_sale['Updated Price'].astype(str).str.replace(",", "").astype(float).round(0).fillna(0).astype(int)
                               
Final_sale['Revenue_plan'] = Final_sale['sale_plan'] * Final_sale['Updated Price']
Final_sale['base_Revenue_plan'] = Final_sale['base_plan'] * Final_sale['Updated Price']
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_PLAN_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_plan.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_plan.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
# Group by city and date, summing Revenue_plan
gr = Final_sale.groupby(['Original_city', 'date','day'], as_index=False)[['Revenue_plan', 'base_Revenue_plan']].sum()
print(gr)

# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_FF_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'gr.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(gr, "gr.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Adhoc Adjustment' (columns H to K) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('Adhoc_adjustment_City_Product_*.parquet') from folder ID DRIVE_FOLDER_ID
logging.info("Loading Adhoc Adjustments parquets...")
City_adhoc = load_latest_parquet_from_drive("Adhoc_adjustment_City_Product", DRIVE_FOLDER_ID)  # First row as header


# Display DataFrame
print(City_adhoc.describe(include='all'))
City_adhoc.describe(include='all')
# Ensure date format matches
City_adhoc["date"] = pd.to_datetime(City_adhoc["date"]).dt.strftime("%Y-%m-%d")

# Merge on 'date', 'Cut class', and 'city_name'
Final_sale = Final_sale.merge(City_adhoc[["date", "Product id", "city_name","%Change3"]], on=["date", "Product id", "city_name"], how="left")

# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_CHECK_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_check.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_check.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)

Final_sale["%Change3"] = pd.to_numeric(Final_sale["%Change3"], errors="coerce")

Final_sale["%Change3"] = Final_sale["%Change3"].fillna(0)

# Calculate final plan
Final_sale["sale_plan"] = Final_sale["sale_plan"] + (Final_sale["sale_plan"] * Final_sale["%Change3"]) 


# Round to avoid decimal values
Final_sale["sale_plan"] = Final_sale["sale_plan"].round(0).astype(int)

print(Final_sale['sale_plan'].sum())
Final_sale.describe(include='all')
day_to_sale_buffer_column = {
    'sale_open_1_flag_Mon': 'Mon', 'sale_open_1_flag_Tue': 'Tue', 'sale_open_1_flag_wed': 'Wed',
    'sale_open_1_flag_Thu': 'Thu', 'sale_open_1_flag_Fri': 'Fri', 'sale_open_1_flag_Sat': 'Sat', 'sale_open_1_flag_Sun': 'Sun'
}

sale_open_buffer_df = Master_df.rename(columns=day_to_sale_buffer_column)

sale_open_buffer_long = sale_open_buffer_df.melt(
    id_vars=['City', 'Product id', 'Channel'],  # Keep channel_type intact for filtering
    value_vars=list(day_to_sale_buffer_column.values()),  # Convert day-wise columns into rows
    var_name='day',
    value_name='sale_Buffer_flag'
).loc[lambda df: df['Channel'] == 'Online']
Final_sale = Final_sale.merge(
   sale_open_buffer_long[['City', 'Product id','day','sale_Buffer_flag']], on=['City', 'Product id','day'], how='left'
)
Final_sale['sale_Buffer_flag'] = pd.to_numeric(Final_sale['sale_Buffer_flag'], errors='coerce').fillna(0)
#Identify groups with sale_plan > 0
valid_groups = Final_sale.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform(lambda x: (x > 0).any())

# Apply the condition and update sale_plan
Final_sale.loc[
    (Final_sale['sale_Buffer_flag'] > 0) & 
    (Final_sale['sale_plan'] < Final_sale['sale_Buffer_flag']) &
(valid_groups),
   'sale_plan'
] = Final_sale['sale_Buffer_flag']

# Sum the updated sale_plan column
Final_sale["sale_plan"].sum()
# Final_sale.to_clipboard()
valid_groups = Final_sale.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform(lambda x: (x > 0).any())

# Apply the condition and update sale_plan
Final_sale.loc[
    (Final_sale['sale_Buffer_flag'] > 0) & 
    (Final_sale['base_plan'] < Final_sale['sale_Buffer_flag']) & 
    (valid_groups), 
    'base_plan'
] = Final_sale['sale_Buffer_flag']

# Sum the updated sale_plan column
Final_sale["base_plan"].sum()
# # Select the specific sheet/tab by its name
# worksheet = spreadsheet.worksheet("Hub Sku plan override")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:I")  # Fetch only columns A to L

# # Convert to DataFrame
# Hub_Sku_plan_override = pd.DataFrame(data[1:], columns=data[0])  # First row as header

# # Display DataFrame
# Hub_Sku_plan_override.describe()

# Hub_Sku_plan_override = Hub_Sku_plan_override.rename(columns={"Attribute": "hub_name"})

# # Step 1: Handle discontinued items — set sale_plan = 0 for all dates in Final_sale
# discontinued = Hub_Sku_plan_override[Hub_Sku_plan_override['Discontinue Flag'] == '1'][
#     ['Product id', 'hub_name']
# ]

# # Step 1: Mark discontinued products — set both sale_plan and base_plan to 0
# Final_sale = Final_sale.merge(discontinued, on=['Product id', 'hub_name'], how='left', indicator=True)
# Final_sale.loc[Final_sale['_merge'] == 'both', ['sale_plan', 'base_plan']] = 0
# Final_sale.drop(columns=['_merge'], inplace=True)


# #Step 2: Apply overrides where Discontinue Flag is 0
# # Rename override columns for clarity
# override_active = Hub_Sku_plan_override[Hub_Sku_plan_override['Discontinue Flag'] == '0'][
#     ['Product id', 'hub_name', 'date', 'sale_plan']
# ].rename(columns={
#     'sale_plan': 'override_sale_plan'
# })



# # Merge overrides with Final_sale
# Final_sale = Final_sale.merge(override_active, on=['Product id', 'hub_name', 'date'], how='left')

# # Use override values where available
# Final_sale['sale_plan'] = Final_sale['override_sale_plan'].combine_first(Final_sale['sale_plan'])

# Final_sale['base_plan'] = Final_sale['override_sale_plan'].combine_first(Final_sale['base_plan'])


# # Cleanup temporary columns
# Final_sale.drop(columns=['override_sale_plan'], inplace=True)
# Select the specific sheet/tab by its name
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Adhoc Adjustment' (columns A to D) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('Adhoc_adjustment_*.parquet') from folder ID DRIVE_FOLDER_ID
Adhoc_factor = load_latest_parquet_from_drive("Adhoc_adjustment_202", DRIVE_FOLDER_ID)  # First row as header

# Display DataFrame
Adhoc_factor.describe()

Final_sale = Final_sale.rename(columns={"Sub-category": "sub category"})



# Convert dates
Adhoc_factor["date"] = pd.to_datetime(Adhoc_factor["date"], format='mixed', dayfirst=True).dt.strftime("%Y-%m-%d")
Final_sale["date"] = pd.to_datetime(Final_sale["date"], format='mixed', dayfirst=True).dt.strftime("%Y-%m-%d")

# Merge festive factor
Final_sale = Final_sale.merge(Adhoc_factor, on=["date", "city_name", "sub category"], how="left")

# Convert columns safely
Final_sale["sale_plan"] = pd.to_numeric(Final_sale["sale_plan"], errors="coerce")
Final_sale["% Change2"] = pd.to_numeric(Final_sale["% Change2"], errors="coerce").fillna(0)

# Step 1: Apply unrounded spike
Final_sale["sale_plan"] = Final_sale["sale_plan"] * (1 + Final_sale["% Change2"])

# # Step 2: Get target aggregate per group (city, sub category, date)
# group_total = Final_sale.groupby(["city_name", "sub category", "date"])["spiked_plan_unrounded"].sum().reset_index(name="group_sum")

# # Step 3: Calculate desired target based on original sale_plan sum × (1 + %Change2)
# orig_total = Final_sale.groupby(["city_name", "sub category", "date"])["sale_plan"].sum().reset_index(name="orig_sum")
# merged_group = pd.merge(orig_total, Adhoc_factor, on=["city_name", "sub category", "date"], how="left")
# merged_group["% Change2"] = pd.to_numeric(merged_group["% Change2"], errors="coerce").fillna(0)
# merged_group["target_total"] = merged_group["orig_sum"] * (1 + merged_group["% Change2"].fillna(0))

# # Step 4: Merge target total back to SKU-level data
# Final_sale = Final_sale.merge(merged_group[["city_name", "sub category", "date", "target_total"]], on=["city_name", "sub category", "date"], how="left")
# Final_sale["group_sum"] = Final_sale.groupby(["city_name", "sub category", "date"])["spiked_plan_unrounded"].transform('sum')

# # Step 5: Scale proportionally to match target group sum
# Final_sale["spiked_plan_scaled"] = Final_sale["spiked_plan_unrounded"] * Final_sale["target_total"] / Final_sale["group_sum"]



Final_sale["sale_plan"] = Final_sale["sale_plan"].fillna(0).round(0).astype(int)

# # Optional: Drop helper columns if needed
# Final_sale.drop(columns=["spiked_plan_unrounded", "spiked_plan_scaled", "group_sum", "target_total"], inplace=True)

# Output
print("Final total sale_plan:", Final_sale["sale_plan"].sum())
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_CHECK_SCALED_ROUNDING_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_scaled_rounding.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_scaled_rounding.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
print(Final_sale.head())
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Adhoc Adjustment Hub' (columns A to F) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('Adhoc_adjustment_Hub_*.parquet') from folder ID DRIVE_FOLDER_ID
Hub_adhoc = load_latest_parquet_from_drive("Adhoc_adjustment_Hub", DRIVE_FOLDER_ID)  # First row as header
#City_adhoc = pd.DataFrame(City_adhoc[1:], columns=City_adhoc[0])
# Display DataFrame
print(Hub_adhoc.describe(include='all'))
#City_adhoc.describe(include='all')
Hub_adhoc["date"] = pd.to_datetime(
    Hub_adhoc["date"],
    format="%Y-%m-%d",
    errors="coerce"
).dt.strftime("%Y-%m-%d")
# Ensure date format matches
Hub_adhoc["date"] = pd.to_datetime(Hub_adhoc["date"]).dt.strftime("%Y-%m-%d")
#City_adhoc["date"] = pd.to_datetime(City_adhoc["date"]).dt.strftime("%Y-%m-%d")
# Merge on 'date', 'Cut class', and 'city_name'
Final_sale = Final_sale.merge(Hub_adhoc[["date", "Product id", "hub_name","% Change1"]], on=["date", "Product id", "hub_name"], how="left")
#Final_sale = Final_sale.merge(City_adhoc[["date", "Product id", "city_name","% Change2"]], on=["date", "Product id", "city_name"], how="left")
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_CHECK_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_check.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_check.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)

Final_sale["% Change1"] = pd.to_numeric(Final_sale["% Change1"], errors="coerce")
#Final_sale["% Change2"] = pd.to_numeric(Final_sale["% Change2"], errors="coerce")
# Fill missing deviations with 0 (if no festive factor exists for that city + cut class + date)
Final_sale["% Change1"] = Final_sale["% Change1"].fillna(0)
#Final_sale["% Change2"] = Final_sale["% Change2"].fillna(0)
# Calculate final plan
Final_sale["unrounded_sale_plan"] = Final_sale["sale_plan"] + (Final_sale["sale_plan"] * Final_sale["% Change1"]) 

print(Final_sale.columns)

# Step 2: Initial rounding (nearest integer)
Final_sale["sale_plan"] = np.round(Final_sale["unrounded_sale_plan"]).astype(int)

# Step 3: Decimal remainders for reconciliation
Final_sale["remainder"] = Final_sale["unrounded_sale_plan"] - Final_sale["sale_plan"]


# Step 4: Reconciliation loop city by city
# --- OLD CODE PRESERVED AS PER REQUEST ---
# for city, group in Final_sale.groupby(["city_name", "sub category", "date"]):
#     target = round(group["unrounded_sale_plan"].sum())
#     current = group["sale_plan"].sum()
#     diff = int(target - current)
#     if diff > 0:
#         idx = group["remainder"].nlargest(diff).index
#         Final_sale.loc[idx, "sale_plan"] += 1
#     elif diff < 0:
#         idx = group["remainder"].nsmallest(abs(diff)).index
#         Final_sale.loc[idx, "sale_plan"] -= 1
# ==============================
_grp2 = Final_sale.groupby(["city_name", "sub category", "date"])
_target2 = _grp2["unrounded_sale_plan"].transform("sum").round()
_current2 = _grp2["sale_plan"].transform("sum")
_diff2 = (_target2 - _current2).fillna(0).astype(int)

_rank_desc2 = _grp2["remainder"].rank(ascending=False, method="first")
_rank_asc2 = _grp2["remainder"].rank(ascending=True, method="first")

_add_mask2 = (_diff2 > 0) & (_rank_desc2 <= _diff2)
_sub_mask2 = (_diff2 < 0) & (_rank_asc2 <= _diff2.abs())

Final_sale["sale_plan"] = Final_sale["sale_plan"] + _add_mask2.astype(int) - _sub_mask2.astype(int)
# Step 1: Create unique mapping from Master_df
mapping_df = (
    Master_df[['Product id', 'Sub-category']]
    .drop_duplicates(subset=['Product id'])
)

# Step 2: Convert to dictionary
prod_to_subcat = dict(zip(mapping_df['Product id'], mapping_df['Sub-category']))

# Step 3: Override in Final_sale
Final_sale['sub category'] = Final_sale['Product id'].map(prod_to_subcat).combine_first(Final_sale['sub category'])
Final_sale['Revenue_plan'] = Final_sale['sale_plan'] * Final_sale['Updated Price']
Final_sale['base_Revenue_plan'] = Final_sale['base_plan'] * Final_sale['Updated Price']
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_PLAN_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_sale_plan.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_sale, "Final_sale_plan.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
# Group by city and date, summing Revenue_plan
gr2 = Final_sale.groupby(['Original_city', 'date','day'], as_index=False)[['Revenue_plan', 'base_Revenue_plan']].sum()
gr3 = Final_sale.groupby(['Original_city','sub category', 'date','day'], as_index=False)[['Revenue_plan', 'base_Revenue_plan']].sum()
print(gr2)
print(gr3)
# ========================================================================================================================
# dynamic date
_today = datetime.now()
_current_monday = _today - timedelta(days=_today.weekday())
start_date = _current_monday - timedelta(days=7)
end_date = _current_monday - timedelta(days=1)
gr3["date"] = pd.to_datetime(gr3["date"], format="%Y-%m-%d", dayfirst=True)
filtered_gr3 = gr3[(gr3['date'] >= start_date) & (gr3['date'] <= end_date)]
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Output: Uploaded directly to Google Drive as 'Expected_Actuals_Tracker.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(filtered_gr3, "Expected_Actuals_Tracker.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
print(filtered_gr3[['Revenue_plan', 'base_Revenue_plan']].sum())

# [PRODUCTION COMMENT - ADDED AS PER USER REQUEST]
# Output: Also write to GSheet tab 'Data_Dump3' in the provided spreadsheet
try:
    Expected_Actuals_Tracker_spreadsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1XHl--DBSlkvoPQaHHirh60pV8T8Lg8Ib8HSgWSrt448/edit?gid=520551462#gid=520551462")
    worksheet = Expected_Actuals_Tracker_spreadsheet.worksheet("Data_Dump3")
    set_with_dataframe(worksheet, filtered_gr3)
    print("Successfully updated Data_Dump3 in Google Sheet.")
except Exception as e:
    print(f"Error updating Google Sheet: {e}")
# # print(filtered_gr2[['Revenue_plan', 'base_Revenue_plan','sale_plan','base_plan']].sum())
# start_date = datetime(2026, 1, 26)
# end_date = datetime(2026, 2, 1)
# gr2["date"] = pd.to_datetime(gr2["date"], format="%Y-%m-%d", dayfirst=True)
# filtered_gr2 = gr2[(gr2['date'] >= start_date) & (gr2['date'] <= end_date)]
# Expected_Actuals_Tracker_spreadsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1QelNGlelD5SNJsctbULAGycU2fL2dcQtRM6MPSs1kPw/edit?gid=520551462#gid=520551462")
# worksheet = Expected_Actuals_Tracker_spreadsheet.worksheet("Data_Dump3")
# set_with_dataframe(worksheet, filtered_gr2)
# print(filtered_gr2[['Revenue_plan', 'base_Revenue_plan','sale_plan','base_plan']].sum())
Final_sale = Final_sale.rename(columns={"hub_name": "Attribute"})
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Cluster phase 2' from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('cluster_v2_*.parquet') from folder ID DRIVE_FOLDER_ID
cluster_mapping_df2 = load_latest_parquet_from_drive("cluster_v2", DRIVE_FOLDER_ID)
# cluster_mapping_df2.to_clipboard()
cluster_mapping_df2["Cluster_Flag"] = pd.to_numeric(cluster_mapping_df2["Cluster_Flag"], errors='coerce').fillna(0).astype(int)
cluster_mapping_df2 = cluster_mapping_df2[cluster_mapping_df2["Cluster_Flag"] == 1]
cluster_mapping_df2 = cluster_mapping_df2.rename(columns={'product_id': 'Product id', 'childHub_name': 'Attribute', 'MotherHub_name': 'Mother_hub'})
cluster_mapping_df2 = cluster_mapping_df2[['Attribute', 'Product id', 'Mother_hub']]
Final_sale = Final_sale.merge(cluster_mapping_df2, how='left', on=['Attribute', 'Product id'])
Final_sale.describe(include='all')
saleplan_transfer = Final_sale.groupby(['Product id', 'date', 'Mother_hub'])['sale_plan'].sum().reset_index()
Final_sale =  Final_sale.merge(
    saleplan_transfer,
    how='left', 
    left_on=['Product id', 'date', 'Attribute'], 
    right_on=['Product id', 'date', 'Mother_hub'],
    suffixes=('', '_transferred')
)
Final_sale['sale_plan'] =Final_sale['sale_plan'] +Final_sale['sale_plan_transferred'].fillna(0)
Final_sale.loc[Final_sale['Mother_hub'].notna(), 'sale_plan'] = 0
day_to_buffer_column = {
    'Buffer_Mon': 'Mon', 'Buffer_Tue': 'Tue', 'Buffer_Wed': 'Wed', 
    'Buffer_Thu': 'Thu', 'Buffer_Fri': 'Fri', 'Buffer_Sat': 'Sat', 'Buffer_Sun': 'Sun'
}

percentage_buffer_df = Master_df.rename(columns=day_to_buffer_column)

percentage_buffer_long = percentage_buffer_df.melt(
    id_vars=['City', 'Product id', 'Channel'],  # Keep channel_type intact for filtering
    value_vars=list(day_to_buffer_column.values()),  # Convert day-wise columns into rows
    var_name='day',
    value_name='Buffer_Percentage'
).loc[lambda df: df['Channel'] == 'Online']
Final_sale = Final_sale.merge(
    percentage_buffer_long, on=['City', 'Product id','day'], how='left'
)
Final_sale['Buffer_Percentage'] = Final_sale['Buffer_Percentage'].astype(str).str.replace('%', '', regex=False).str.strip()
Final_sale['Buffer_Percentage'] = pd.to_numeric(Final_sale['Buffer_Percentage'], errors='coerce')
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Inv_buffer' (columns A to D) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('Inv_buffer_*.parquet') from folder ID DRIVE_FOLDER_ID
inv_buffer = load_latest_parquet_from_drive("Inv_buffer", DRIVE_FOLDER_ID)  # First row as header
# print(inv_buffer[inv_buffer.duplicated()])

# Display DataFrame
inv_buffer.describe()
# Ensure case-insensitivity for 'volume bucket'
vol_col = next((c for c in inv_buffer.columns if c.lower() == 'volume bucket'), None)
if vol_col and vol_col != 'volume bucket':
    inv_buffer = inv_buffer.rename(columns={vol_col: 'volume bucket'})

# Split 'volume bucket' into 'min_volume' and 'max_volume'
inv_buffer[['min_volume', 'max_volume']] = inv_buffer['volume bucket'].str.split('-', expand=True).astype(float)


# Create a mask for rows where the flag is 0
mask = Final_sale['DOC/Percentage_BufferFlag'] == 0
Final_sale_flag0 = Final_sale[mask].copy()

# --- OLD CODE PRESERVED AS PER REQUEST ---
# def get_buffer_percentage(row):
#     day = row['day']
#     city = row['city_name']
#     plan = row['sale_plan']
#     match = inv_buffer[
#         (inv_buffer['day'] == day) &
#         (inv_buffer['city_name'] == city) &
#         (plan >= inv_buffer['min_volume']) &
#         (plan <= inv_buffer['max_volume'])
#     ]
#     if not match.empty:
#         return match.iloc[0]['Buffer %']
#     else:
#         return row['Buffer_Percentage']
# Final_sale.loc[mask, 'Buffer_Percentage'] = Final_sale_flag0.apply(get_buffer_percentage, axis=1)
# ==============================
_merged_buf = Final_sale_flag0[['day', 'city_name', 'sale_plan', 'Buffer_Percentage']].reset_index().merge(
    inv_buffer[['day', 'city_name', 'min_volume', 'max_volume', 'Buffer %']],
    on=['day', 'city_name'],
    how='left'
)
_valid_buf = _merged_buf[
    (_merged_buf['sale_plan'] >= _merged_buf['min_volume']) &
    (_merged_buf['sale_plan'] <= _merged_buf['max_volume'])
].drop_duplicates(subset=['index'])

_valid_buf_map = _valid_buf.set_index('index')['Buffer %']
Final_sale.loc[mask, 'Buffer_Percentage'] = pd.Series(
    Final_sale_flag0.index.map(_valid_buf_map), index=Final_sale_flag0.index
).fillna(Final_sale_flag0['Buffer_Percentage'])

Final_sale['Buffer_Percentage'] = Final_sale['Buffer_Percentage'].astype(str).str.replace('%', '', regex=False).str.strip()
Final_sale['Buffer_Percentage'] = pd.to_numeric(Final_sale['Buffer_Percentage'], errors='coerce')
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'cluster_mapping' from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('cluster_v1_*.parquet') from folder ID DRIVE_FOLDER_ID
mother_hub_mapping = load_latest_parquet_from_drive("cluster_v1", DRIVE_FOLDER_ID)
unique_source_hubs = mother_hub_mapping[['sourceHub_name']].drop_duplicates().reset_index(drop=True)
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Hub(Inv_Buffer)' from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('hub_inv_buffer_*.parquet') from folder ID DRIVE_FOLDER_ID
Hub_level_inv_buffer = load_latest_parquet_from_drive("hub_inv_buffer", DRIVE_FOLDER_ID)

# Merge to bring the Inv_Buffer into Final_sale where keys match
Final_sale = Final_sale.merge(
    Hub_level_inv_buffer[["Attribute", "Product id","day", "Inv_Buffer"]],
    on=["Attribute", "Product id", "day"],
    how="left"
)





Final_sale['Buffer_Percentage'] = pd.to_numeric(Final_sale['Buffer_Percentage'], errors='coerce')
# Overwrite Buffer_Percentage wherever Inv_Buffer is available
Final_sale["Buffer_Percentage"] = Final_sale["Inv_Buffer"].combine_first(Final_sale["Buffer_Percentage"])
Final_sale['Buffer_Percentage'] = Final_sale['Buffer_Percentage'].astype(str).str.replace('%', '', regex=False).str.strip()
Final_sale['Buffer_Percentage'] = pd.to_numeric(
    Final_sale['Buffer_Percentage'], errors='coerce'
).fillna(0)
mask = Final_sale['Attribute'].isin(
    unique_source_hubs['sourceHub_name']
)

Final_sale.loc[mask, 'Buffer_Percentage'] = np.where(
    Final_sale.loc[mask, 'Buffer_Percentage'] < 100,
    Final_sale.loc[mask, 'Buffer_Percentage'] + 5,
    Final_sale.loc[mask, 'Buffer_Percentage']
)


Final_sale['Uncapped Buffer'] = np.where(
    Final_sale['DOC/Percentage_BufferFlag'] == 0,  
    np.round(Final_sale['sale_plan'] *(1+ (Final_sale['Buffer_Percentage'] / 100))),  
    0  # If Buffer_Percentage is 100 or more, set Uncapped Buffer to 0
)
Final_sale = Final_sale.sort_values(by=['Attribute', 'Product id', 'date'])

# Shift 'hub_level_plan' for the next day within each 'hub_name' and 'Pr_id'
Final_sale['Next_Day_Plan'] = Final_sale.groupby(['Attribute', 'Product id'])['sale_plan'].shift(-1).fillna(0)
buffer_to_day_mapping = {
    'Mon': 'Buffer_Mon', 'Tue': 'Buffer_Tue', 'Wed': 'Buffer_Wed',
    'Thu': 'Buffer_Thu', 'Fri': 'Buffer_Fri', 'Sat': 'Buffer_Sat', 'Sun': 'Buffer_Sun'
}
percentage_buffer_df.rename(columns=buffer_to_day_mapping , inplace=True)
day_capping_mapping = {
    'Capping_Mon': 'Mon', 'Capping_Tue': 'Tue', 'Capping_Wed': 'Wed',
    'Capping_Thu': 'Thu', 'Capping_Fri': 'Fri', 'Capping_Sat': 'Sat', 'Capping_Sun': 'Sun'
}
percentage_buffer_df.rename(columns=day_capping_mapping, inplace=True)


buffer_capping_long = percentage_buffer_df.melt(
    id_vars=['City', 'Product id','Channel'],  # Keep channel_type intact for filtering
    value_vars=list(day_to_buffer_column.values()),  # Convert day-wise columns into rows
    var_name='day',
    value_name= 'Max_Capped_Buffer'
).loc[lambda df: df['Channel'] == 'Online']

Final_sale = Final_sale.merge(
    buffer_capping_long, on=['City', 'Product id','day'], how='left'
)

Final_sale['Max_Capped_Buffer'] = Final_sale['Max_Capped_Buffer'].astype(str).str.replace('%', '', regex=False).str.strip()
Final_sale['Max_Capped_Buffer'] = pd.to_numeric(Final_sale['Max_Capped_Buffer'], errors='coerce')



Final_sale['Max_Capped_Buffer'] = pd.to_numeric(Final_sale['Max_Capped_Buffer'], errors='coerce')

unique_source_hubs_list = unique_source_hubs['sourceHub_name'].unique()


# Final_sale.loc[
#     Final_sale['Attribute'].isin(unique_source_hubs_list),
#     'Max_Capped_Buffer'
# ] = 100

Final_sale['Capped_Buffer'] = np.where(
    Final_sale['DOC/Percentage_BufferFlag'] == 0,  
    np.round(Final_sale['sale_plan'] + (Final_sale['Next_Day_Plan'] *(Final_sale['Max_Capped_Buffer'] / 100))),  
    0  # If Buffer_Percentage is 100 or more, set Uncapped Buffer to 0
)
Final_sale.describe(include='all')
df_excess = Final_sale[(Final_sale['Buffer_Percentage'] > 100)][['Product id', 'Attribute', 'date','sale_plan', 'Buffer_Percentage']].copy()
df_excess['Days_Allocation'] = (df_excess['Buffer_Percentage'] / 100)
df_excess = df_excess.sort_values(['Product id', 'Attribute', 'date'])
def rolling_sum_dynamic(group):
    allocated_buffer = np.zeros(len(group))  # Initialize buffer allocation array

    for i in range(len(group)):
        days_allocation = group.iloc[i]['Days_Allocation']
        full_days = int(days_allocation)  # Extract full days (integer part)
        fraction = days_allocation - full_days  # Extract remaining fraction (decimal part)

        # Sum full days completely
        if full_days > 0:
            allocated_buffer[i] += group['sale_plan'].iloc[i:i + full_days].sum()
        
        # Add fractional part from the next day's sale_plan
        if fraction > 0 and (i + full_days) < len(group):
            allocated_buffer[i] += fraction * group['sale_plan'].iloc[i + full_days]

    return np.round(allocated_buffer).astype(int)

if df_excess.empty:
    df_excess['Allocated_Buffer'] = pd.Series(dtype=int)
else:
    df_excess['Allocated_Buffer'] = 0
    for _, group in df_excess.groupby(['Attribute', 'Product id']):
        df_excess.loc[group.index, 'Allocated_Buffer'] = rolling_sum_dynamic(group)
df_excess.describe(include='all')
Final_plan = Final_sale.merge(
    df_excess[['Attribute', 'Product id', 'date', 'Allocated_Buffer']],
    how='left',
    on=['Attribute', 'Product id', 'date']
)
Final_plan['Final_Inv_Plan'] = Final_plan['sale_plan']
Final_plan['Final_Inv_Plan'] = Final_plan['Allocated_Buffer'].combine_first(Final_plan['Final_Inv_Plan'])
Final_plan.drop(columns=['Allocated_Buffer'], inplace=True) 
Final_plan['Final_Inv_Plan'] = np.where(
    (Final_plan['Uncapped Buffer'] > 0) & (Final_plan['Capped_Buffer'] > 0),
    np.minimum(Final_plan['Uncapped Buffer'], Final_plan['Capped_Buffer']),
    Final_plan['Final_Inv_Plan']  # Keep the non-zero buffer
)
Final_plan = Final_plan.merge(
    Hub_Master[['hub_name', 'sku class prod', 'HTT']],
    left_on=['Attribute', 'sku class prod'],
    right_on=['hub_name', 'sku class prod'],
    how='left'
)

# --- OLD CODE PRESERVED AS PER REQUEST ---
# def update_final_inv_plan(row):
#     if (row["HTT"] == "head") and (0 < row["sale_plan"] < 4):
#         return row["sale_plan"] + 1
#     special_hubs = ["KOM", "TUB", "Indiranagar"]
#     if (row["Attribute"] in special_hubs) and (0 < row["sale_plan"] < 4):
#         return row["sale_plan"] + 1
#     if row["city_name"] == "Bangalore":
#         if 0 < row["sale_plan"] < 2:
#             return row["sale_plan"]
#         if 1 < row["sale_plan"] < 4:
#             return row["sale_plan"] + 1
#         return row["Final_Inv_Plan"]
#     if 0 < row["sale_plan"] < 4:
#         return row["sale_plan"]
#     return row["Final_Inv_Plan"]
# mask = Final_plan['DOC/Percentage_BufferFlag'] == 0
# Final_plan.loc[mask, 'Final_Inv_Plan'] = (
#     Final_plan.loc[mask].apply(update_final_inv_plan, axis=1)
# )
# ==============================
mask = Final_plan['DOC/Percentage_BufferFlag'] == 0
m_df = Final_plan.loc[mask]
sp = m_df['sale_plan']
fip = m_df['Final_Inv_Plan']

cond1 = (m_df['HTT'] == 'head') & (sp > 0) & (sp < 4)
cond2 = (m_df['Attribute'].isin(["KOM", "TUB", "Indiranagar"])) & (sp > 0) & (sp < 4)
cond3 = (m_df['city_name'] == 'Bangalore') & (sp > 0) & (sp < 2)
cond4 = (m_df['city_name'] == 'Bangalore') & (sp > 1) & (sp < 4)
cond5 = (m_df['city_name'] != 'Bangalore') & (sp > 0) & (sp < 4)

Final_plan.loc[mask, 'Final_Inv_Plan'] = np.select(
    [cond1, cond2, cond3, cond4, cond5],
    [sp + 1, sp + 1, sp, sp + 1, sp],
    default=fip
)

print(Final_plan['Final_Inv_Plan'].sum())
Final_plan.describe(include='all')




day_to_inv_buffer_column = {
    'Inv_open_1_flag_Mon': 'Mon', 'Inv_open_1_flag_Tue': 'Tue', 'Inv_open_1_flag_wed': 'Wed',
    'Inv_open_1_flag_Thu': 'Thu', 'Inv_open_1_flag_Fri': 'Fri', 'Inv_open_1_flag_Sat': 'Sat', 'Inv_open_1_flag_Sun': 'Sun'
}

Inv_open_buffer_df = Master_df.rename(columns=day_to_inv_buffer_column)

inv_open_buffer_long = Inv_open_buffer_df.melt(
    id_vars=['City', 'Product id', 'Channel'],  # Keep channel_type intact for filtering
    value_vars=list(day_to_inv_buffer_column.values()),  # Convert day-wise columns into rows
    var_name='day',
    value_name='Buffer_flag'
).loc[lambda df: df['Channel'] == 'Online']
Final_plan = Final_plan.merge(
   inv_open_buffer_long[['City', 'Product id','day','Buffer_flag']], on=['City', 'Product id','day'], how='left'
)
# mask = (
#     (Final_plan['Buffer_flag'] == 1) & 
#     (Final_plan['sale_plan'] == 0) & 
#     (Final_plan['Final_Inv_Plan'] == 0)
# )

# # Old logic (commented out):
# # Final_plan.loc[mask, 'Final_Inv_Plan'] = Final_plan.loc[mask, "Split %1"].round(0).astype(int)

# # New logic: Set Final_Inv_Plan to 1 directly
# Final_plan.loc[mask, 'Final_Inv_Plan'] = 1

# print(Final_plan['Final_Inv_Plan'].sum())

# valid_groups = Final_plan.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform(lambda x: (x > 0).any())

# # Apply the condition and update sale_plan
# Final_sale.loc[
#     (Final_sale['sale_Buffer_flag'] > 0) & 
#     (Final_sale['base_plan'] < Final_sale['sale_Buffer_flag']) & 
#     (valid_groups), 
#     'base_plan'
# ] = Final_sale['sale_Buffer_flag']

# # Sum the updated sale_plan column
# Final_sale["base_plan"].sum()
valid_groups = Final_plan.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform(lambda x: (x > 0).any())



Final_plan.loc[
    (Final_plan['Buffer_flag'] == 1) & 
    (valid_groups) &
    (Final_plan['sale_plan'] == 0) & 
    (Final_plan['Final_Inv_Plan'] == 0), 
    'Final_Inv_Plan'
] = 1 * Final_plan["Split %1"].round(0).astype(int)
print(Final_plan['Final_Inv_Plan'].sum())
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'No_Buffer(Inv_Plan)' (columns A to B) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('no_buffer_inv_plan_*.parquet') from folder ID DRIVE_FOLDER_ID
No_buffer = load_latest_parquet_from_drive("no_buffer_inv_plan", DRIVE_FOLDER_ID)  # First row as header

# Display DataFrame
No_buffer.describe()
# Correct way to access multiple columns
no_buffer_set = set([tuple(x) for x in No_buffer[['city_name', 'Pr_id']].values])

# Set inv_plan to 0 for matching rows using vectorized approach
# --- OLD CODE PRESERVED AS PER REQUEST ---
# mask = Final_plan[['city_name', 'Product id']].apply(tuple, axis=1).isin(no_buffer_set)
mask = Final_plan.set_index(['city_name', 'Product id']).index.isin(no_buffer_set)
Final_plan.loc[mask, 'Final_Inv_Plan'] = Final_plan['sale_plan']
Final_plan.loc[(Final_plan['sub category'] == 'Masalas') & (Final_plan['Final_Inv_Plan'] < 3), 'Final_Inv_Plan'] = 3
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_FINAL_FORECAST_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'Final_plan.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(Final_plan, "Final_plan.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
upload_sheets_to_drive_as_excel({"Final_plan": Final_plan}, "Final_plan.xlsx", FF_OUTPUT_EXCEL_FOLDER_ID)
# Select the specific sheet/tab by its name
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'COGS' (columns A to G) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('cogs_*.parquet') from folder ID DRIVE_FOLDER_ID
cogs_df = load_latest_parquet_from_drive("cogs", DRIVE_FOLDER_ID) 

cogs_df.describe(include='all')


cogs_df['Product id'].value_counts().head()
cogs_df = cogs_df.drop_duplicates('Product id')
Final_plan = Final_plan.merge(
    cogs_df[['Product id', 'COGS']],
    on='Product id',
    how='left'
)
Final_plan['COGS'] = pd.to_numeric(Final_plan['COGS'], errors='coerce')
mask = Final_plan['COGS'] > 400

Final_plan['inv_buffer'] = Final_plan['Final_Inv_Plan'] - Final_plan['sale_plan']

Final_plan.loc[mask, 'inv_buffer'] = (
    Final_plan.loc[mask, 'inv_buffer'] * 0.85
)

Final_plan['Final_Inv_Plan'] = Final_plan['inv_buffer'] + Final_plan['sale_plan']
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'cluster_mapping' from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('cluster_v1_*.parquet') from folder ID DRIVE_FOLDER_ID
cluster_mapping_df = load_latest_parquet_from_drive("cluster_v1", DRIVE_FOLDER_ID)
cluster_mapping_df = cluster_mapping_df.rename(columns={'product_id': 'Product id', 'destinationHub_name': 'Attribute', 'sourceHub_name': 'source_hub'})
cluster_mapping_df = cluster_mapping_df[['Attribute', 'Product id', 'source_hub', 'CH Decrease%', 'MH Increase%']]
# --- OLD CODE PRESERVED AS PER REQUEST ---
# cluster_mapping_df['CH Decrease%'] = cluster_mapping_df['CH Decrease%'].fillna(0).apply(parse_festive_factor)
# cluster_mapping_df['MH Increase%'] = cluster_mapping_df['MH Increase%'].fillna(0).apply(parse_festive_factor)
# ==============================
cluster_mapping_df['CH Decrease%'] = vectorize_festive_factor(cluster_mapping_df['CH Decrease%'].fillna(0))
cluster_mapping_df['MH Increase%'] = vectorize_festive_factor(cluster_mapping_df['MH Increase%'].fillna(0))

merged_dataframe = Final_plan.merge(cluster_mapping_df, how='left', on=['Attribute', 'Product id'])
merged_dataframe.describe(include='all')

# Raw buffer per child hub row
merged_dataframe['inv_buffer'] = merged_dataframe['Final_Inv_Plan'] - merged_dataframe['sale_plan']

# Amount arriving at mother hub = child buffer * MH Increase%
merged_dataframe['mh_transfer'] = merged_dataframe['inv_buffer'] * merged_dataframe['MH Increase%']

# Note: CH Decrease% = fraction child gives away, MH Increase% = fraction that arrives at mother

# Aggregate mh_transfer to mother hub level (per product, date, source_hub)
inventory_transfer = merged_dataframe[
    ~((merged_dataframe['sale_plan'] == 0) & (merged_dataframe['Final_Inv_Plan'] == 1))
].groupby(['Product id', 'date', 'source_hub'])['mh_transfer'].sum().reset_index()

merged_dataframe = merged_dataframe.merge(
    inventory_transfer,
    how='left',
    left_on=['Product id', 'date', 'Attribute'],
    right_on=['Product id', 'date', 'source_hub'],
    suffixes=('', '_transferred')
)
# Mother hub: add aggregated (child inv_buffer * MH Increase%) from all child hubs, ceiling rounded
merged_dataframe['Final_Inv_Plan'] += np.ceil(merged_dataframe['mh_transfer_transferred'].fillna(0))

# Child hub: retains (1 - CH Decrease%) of its buffer -> Final_Inv_Plan = sale_plan + inv_buffer * (1 - CH Decrease%)
merged_dataframe.loc[
    (merged_dataframe['source_hub'].notna()) &
    ~((merged_dataframe['sale_plan'] == 0) & (merged_dataframe['Final_Inv_Plan'] == 1)),
    'Final_Inv_Plan'
] = (
    merged_dataframe['sale_plan'] +
    merged_dataframe['inv_buffer'] * (1 - merged_dataframe['CH Decrease%'])
)
print(merged_dataframe.columns)
merged_dataframe.loc[merged_dataframe['Mother_hub'].notna(), 'Final_Inv_Plan'] = 0
# discontinued = discontinued.rename(columns={"hub_name": "Attribute"})
# # Step 2: Merge to identify discontinued entries
# merged_dataframe = merged_dataframe.merge(discontinued, on=['Product id', 'Attribute'], how='left', indicator=True)

# # Step 3: Set Final_Inv_Plan = 0 where discontinued
# merged_dataframe.loc[merged_dataframe['_merge'] == 'both', 'Final_Inv_Plan'] = 0

# # Step 4: Clean up
# merged_dataframe.drop(columns=['_merge'], inplace=True)

Final_forecast = merged_dataframe[['city_name', 'Attribute', 'Product id', 'sub category', 'Cut class','Updated Price','day','date','sale_plan','Final_Inv_Plan','Revenue_plan','source_hub','DOC/Percentage_BufferFlag']].copy()
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_FINAL_FORECAST_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'merged_dataframe.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(merged_dataframe, "merged_dataframe.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
merged_dataframe.describe(include='all')
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Pure Preorder' (columns A to B) from Google Sheet 'Hub_level_planning'
# Current Input: Loaded directly from Google Drive ('pure_preorder_*.parquet') from folder ID DRIVE_FOLDER_ID
Pure_Preorder = load_latest_parquet_from_drive("pure_preorder", DRIVE_FOLDER_ID)  # First row as header

# Display DataFrame
Pure_Preorder.describe()

Pure_Preorder.rename(columns={'hub_name': 'Attribute'}, inplace=True)

Pure_Preorder.head()
# Correct way to access multiple columns
Pure_Preorder = set([tuple(x) for x in Pure_Preorder[['Attribute', 'Product id']].values])

# Set inv_plan to 0 for matching rows using vectorized approach
# --- OLD CODE PRESERVED AS PER REQUEST ---
# mask = merged_dataframe[['Attribute', 'Product id']].apply(tuple, axis=1).isin(Pure_Preorder)
mask = merged_dataframe.set_index(['Attribute', 'Product id']).index.isin(Pure_Preorder)                                                            
merged_dataframe.loc[mask, 'Final_Inv_Plan'] = merged_dataframe['sale_plan']
columns_to_keep = [
    'city_name', 'sub category','Product id', 'day', 'Cut class', 'date',
    'Attribute', 'sale_plan','base_plan','base_Revenue_plan', 'Updated Price', 'Revenue_plan', 'Channel_x',
    'Final_Inv_Plan'
]
final_dataframe = merged_dataframe[columns_to_keep]
final_dataframe = final_dataframe.rename(columns={
    'Attribute': 'hub_name',
    'Channel_x': 'hub_type',
    'sale_plan': 'r7_plan',
    'Revenue_plan': 'r7_plan_revenue',
    'Final_Inv_Plan': 'r7_inv',
    'Cut class' : 'Cut_Classification',
    'sub category' : 'category',
    'Updated Price' : 'price',
    'base_plan' : 'BasePlan',
    'base_Revenue_plan' : 'BaseRev'
})
final_dataframe.describe(include='all')

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'Hub_Mapping' (columns A to B) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('Hub_Mapping_*.parquet') from folder ID DRIVE_FOLDER_ID
Hub_Mapping = load_latest_parquet_from_drive("Hub_Mapping", DRIVE_FOLDER_ID)  # First row as header

final_dataframe =final_dataframe.merge(
   Hub_Mapping, 
    how='left', 
    on="hub_name" 
)
final_dataframe.describe(include='all')
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'AF-50' (columns A to C) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('AF-50_*.parquet') from folder ID DRIVE_FOLDER_ID
AF_50_df = load_latest_parquet_from_drive("AF-50", DRIVE_FOLDER_ID)
final_dataframe = final_dataframe.merge(AF_50_df, how='left', on=["hub_name", "Product id"])
final_dataframe.describe(include='all')
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheet 'P Master' (columns A to I) from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive ('p_master_*.parquet') from folder ID DRIVE_FOLDER_ID
Product_Master = load_latest_parquet_from_drive("p_master", DRIVE_FOLDER_ID)
final_dataframe = final_dataframe.merge(
    Product_Master[["Product id","Product Name",  "RM", "RM Category"]], 
    how='left', 
    on="Product id"
)
final_dataframe.describe(include='all')
Product_Location_Master = Master_df.rename(columns={
    'City' : 'city_name',
    'Channel' : 'hub_type',
    'Order Type - pan india' : 'Order Type'
})
final_dataframe = final_dataframe.merge(
    Product_Location_Master[["hub_type","city_name", "Product id", "Classification", "Order Type"]], 
    how='left', 
    on=["hub_type","city_name", "Product id"]
)
final_dataframe.describe(include='all')
final_dataframe["new_catg"] = final_dataframe["category"]  # Same as category
final_dataframe["sku_recency"] = "old"
final_dataframe["r7_plan_revenue"] = final_dataframe["r7_plan"] * final_dataframe["price"] 
final_dataframe["r7_inv_rev"] = final_dataframe["r7_inv"] * final_dataframe["price"]  # Calculate r7_inv_rev
final_dataframe["buffer_qty_at_upstream"] = 0 
final_dataframe = final_dataframe.rename(columns={
   'Product id': 'product_id',
    'Product Name' : 'product_name',
    'RM Category' : 'rm_category',
    'Order Type' : 'order_type',
    'r7_plan_revenue' : 'r7_plan_rev'
    
})

day_mapping = {
    "Mon": "Monday",
    "Tue": "Tuesday",
    "Wed": "Wednesday",
    "Thu": "Thursday",
    "Fri": "Friday",
    "Sat": "Saturday",
    "Sun": "Sunday"
}

# Replace short names with full names in the 'Day' column
final_dataframe["day"] = final_dataframe["day"].map(day_mapping)

final_dataframe = final_dataframe[
    [
        "city_name", "hub_name", "hub_id", "product_id", "product_name", "category", "new_catg",
        "RM", "rm_category", "Cut_Classification", "order_type", "Classification", "AF-50",
        "price", "day", "date", "hub_type", "sku_recency", "r7_plan", "r7_inv", "r7_plan_rev",
        "r7_inv_rev", "BasePlan", "BaseRev", "buffer_qty_at_upstream"
    ]
]
duplicate_counts = (
   final_dataframe.groupby(['hub_name', 'product_id', 'date'])
    .size()
    .reset_index(name='count')
)


duplicates_only = duplicate_counts[duplicate_counts['count'] > 1]

print(duplicates_only)
# duplicates_only.to_clipboard()
# Avoid division by zero
mask = (
    (final_dataframe["r7_inv"] < 0) |
    (final_dataframe["r7_plan"] < 0) |
    (final_dataframe["BasePlan"] < 0) |
    (final_dataframe["r7_inv"] < 0)
)


# Print rows where condition holds true
print(final_dataframe[mask])
mask = (
    (final_dataframe["r7_plan"] > final_dataframe["r7_inv"])
)


# Print rows where condition holds true
print(final_dataframe[mask])
# final_dataframe.to_clipboard()
# # Set up Google Sheets API credentials using config

# # Open the Google Sheet by URL
# spreadsheet = client.open_by_url(config_paths.FF_PL_MASTER_SHEET_URL)

# # Select the specific sheet/tab by its name
# worksheet = spreadsheet.worksheet("P-L Master")

# # Get all values from
# data = worksheet.get_all_records() 

# Master_df = pd.DataFrame(data)
# print(Master_df[Master_df.duplicated(subset=['Channel', 'City', 'Product id'])])


# # Display DataFrame
# Master_df.describe(include='all')
# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous Input: Loaded worksheets 'CP' and 'ExPreO' from Google Sheet 'FF_PL_MASTER_SHEET_URL'
# Current Input: Loaded directly from Google Drive as Parquet files ('CP_*.parquet' and 'ExPreO_*.parquet') from folder ID DRIVE_FOLDER_ID
cp_df = load_latest_parquet_from_drive("CP", DRIVE_FOLDER_ID)
excl_df = load_latest_parquet_from_drive("ExPreO", DRIVE_FOLDER_ID)
columns_required = [
    "city_name", "hub_name", "hub_id", "product_id", "product_name", "category", "new_catg",
    "RM", "rm_category", "Cut_Classification", "order_type", "Classification", "AF-50",
    "price", "day", "date", "hub_type", "sku_recency", "r7_plan", "r7_inv", "r7_plan_rev",
    "r7_inv_rev", "BasePlan", "BaseRev", "buffer_qty_at_upstream"
]
cp_df = cp_df[columns_required]
excl_df = excl_df[columns_required]
logging.info("Concatenating final forecast datasets...")
final_dataframe = pd.concat([final_dataframe, cp_df,excl_df], ignore_index=True)
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as CSV file 'FF_FINAL_DATAFRAME_COMBINED_CSV_PATH'
# Current Output: Uploaded directly to Google Drive as 'final_dataframe_combined.parquet' to FF_OUTPUT_PARQUET_FOLDER_ID
upload_df_to_drive_as_parquet_async(final_dataframe, "final_dataframe_combined.parquet", FF_OUTPUT_PARQUET_FOLDER_ID)
upload_sheets_to_drive_as_excel({"final_dataframe": final_dataframe}, "final_dataframe_combined.xlsx", FF_OUTPUT_EXCEL_FOLDER_ID)
for name, df in {
    "final_dataframe": final_dataframe,
    "cp_df": cp_df,
    "excl_df": excl_df
}.items():
    dup_cols = df.columns[df.columns.duplicated()].tolist()
    if dup_cols:
        print(f"{name} has duplicate columns:", dup_cols)
# Remove commas and convert columns to float before rounding and converting to int
numeric_columns = ["hub_id","price","r7_plan", "r7_inv", "r7_plan_rev", "r7_inv_rev", "BasePlan", "BaseRev","buffer_qty_at_upstream"]

for col in numeric_columns:
    final_dataframe[col] = (
        final_dataframe[col]
        .astype(str)           # Convert to string (to handle commas)
        .str.replace(",", "")  # Remove commas
        .astype(float)         # Convert to float
        .round(0)              # Round to nearest integer
        .astype(int)           # Convert to int
    )

numeric_columns = [
    "hub_id", "price", "r7_plan", "r7_inv", "r7_plan_rev",
    "r7_inv_rev", "BasePlan", "BaseRev", "buffer_qty_at_upstream"
]

for col in numeric_columns:
    final_dataframe[col] = (
        final_dataframe[col]
        .astype(str)
        .str.replace(",", "")
    )

    # Find rows causing issue
    error_rows = final_dataframe[
        pd.to_numeric(final_dataframe[col], errors='coerce').isna()
    ]

    print(f"\nError rows in column: {col}")
    print(error_rows[[col]])   # or print(error_rows) for full row

    # Convert safely
    final_dataframe[col] = (
        pd.to_numeric(final_dataframe[col], errors='coerce')
        .fillna(0)   # optional: replace bad values with 0
        .round(0)
        .astype(int)
    )
numeric_columns = ["hub_id","price","r7_plan", "r7_inv", "r7_plan_rev", "r7_inv_rev", "BasePlan", "BaseRev","buffer_qty_at_upstream"]

for col in numeric_columns:
    try:
        # Attempt conversion
        final_dataframe[col].astype(str).str.replace(",", "").astype(float)
    except ValueError as e:
        print(f"❌ Error in column: {col}")
        print(final_dataframe[col][~final_dataframe[col].astype(str).str.replace(",", "").str.match(r"^-?\d*\.?\d*$")].unique()[:10])
        print("-" * 50)

duplicate_counts = (
    final_dataframe[final_dataframe['hub_type'] == 'Online']  # ✅ filter first
    .groupby(['hub_name', 'product_id', 'date'])
    .size()
    .reset_index(name='count')
)

duplicates_only = duplicate_counts[duplicate_counts['count'] > 1]

print(duplicates_only)
# Hardcoded start and end dates
# ========================================================================================================================
# dynamic date
_today = datetime.now()
_current_monday = _today - timedelta(days=_today.weekday())
start_date = _current_monday - timedelta(days=7)
end_date = _current_monday - timedelta(days=1)
start_date_r = _current_monday
end_date_r = _current_monday + timedelta(days=6)

# # Add a new column that concatenates 'hubname', 'product id', and 'date'
final_dataframe.insert(0, "", final_dataframe["hub_name"].astype(str)  +
                        final_dataframe["product_id"].astype(str)  +
                        final_dataframe["day"])

# Convert 'date' column to datetime format (assuming it's in DD-MM-YYYY format)
final_dataframe["date"] = pd.to_datetime(final_dataframe["date"], format="%Y-%m-%d", dayfirst=True)

# Filter data
final_Fcst = final_dataframe[
    (final_dataframe["date"] >= start_date) & (final_dataframe["date"] <= end_date)
]

Replication_of_Indents = final_dataframe[
    (final_dataframe["date"] >= start_date_r) & (final_dataframe["date"] <= end_date_r)
]

final_Fcst["date"] = pd.to_datetime(final_Fcst["date"], format="%d-%m-%Y")
Replication_of_Indents["date"] = pd.to_datetime(Replication_of_Indents["date"], format="%d-%m-%Y")

# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as multi-sheet Excel file 'FF_HUB_DIST_XLSX_PATH' ('Hub_Distribution_Wk{Week} 2026.xlsx')
# Current Output: Uploaded directly to Google Drive as multi-sheet Excel file under FF_OUTPUT_EXCEL_FOLDER_ID folder in-memory
file_name = os.path.basename(config_paths.FF_HUB_DIST_XLSX_PATH)
sheets = {
    "Final Fcst": final_Fcst,
    "Replications for indents": Replication_of_Indents
}
upload_sheets_to_drive_as_excel(sheets, file_name, FF_OUTPUT_EXCEL_FOLDER_ID)
logging.info("FF Hub Automation step completed successfully.")


# #VA projection
# # Define the categories to exclude
# exclude_categories = ['Chicken', 'Eggs', 'Fish & Seafood', 'Fresh Water', 'Lamb & Goat', 'Prawn', 'Sea water']

# # Filter and groupby
# result_df = (
#     final_dataframe[~final_dataframe['category'].isin(exclude_categories)]
#     .groupby(['city_name', 'product_id', 'product_name', 'category', 'date'], as_index=False)
#     .agg({'r7_plan': 'sum'}).rename(columns={'r7_plan': 'sale_plan'})
# )

# VA_projection_spsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1Efi9q4IsOO-OWoX0NN_R-PYmsTC01j_i3InKot_OOJM/edit?gid=1811572769#gid=1811572769")
# worksheet = VA_projection_spsheet.worksheet("4w rolling_Projection")
# set_with_dataframe(worksheet, result_df)
# # Define the categories to exclude
# exclude_categories = ['Chicken', 'Eggs', 'Fish & Seafood', 'Fresh Water', 'Lamb & Goat', 'Prawn', 'Sea water']

# # Filter and groupby
# result_df = (
#     final_dataframe[~final_dataframe['category'].isin(exclude_categories)]
#     .groupby(['product_id', 'hub_name', 'city_name','date'], as_index=False)
#     .agg({'r7_plan': 'sum'}).rename(columns={'r7_plan': 'Planquantity', 'product_id': 'Productid', 'hub_name': 'Hubname', 'city_name': 'Cityname', 'date': 'Date'})
# )

# VA_projection_spsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/13llF4m1JmDVRqRgx_EqqEFdqMzhCq8Ft2Gd-Gmhi7sY")
# worksheet = VA_projection_spsheet.worksheet("Sheet1")
# set_with_dataframe(worksheet, result_df)
wait_for_all_uploads()
























































































