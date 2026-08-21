import config_paths
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
import os
import pyreadr
import pandas as pd
import numpy as np
from datetime import timedelta, datetime
import datetime as dt_mod
import trino
import time as _time
import subprocess
import io
import threading
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials

from config_paths import (
    RDS_PATH,
    JSON_KEYFILE_PATH,
    GOOGLE_CREDENTIALS_DICT,
    DRIVE_FOLDER_ID,
    RAW_DATA_DRIVE_FOLDER_ID,
    BASELINE_DRIVE_PARQUET_FOLDER_ID,
)

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
    # --- OLD CODE PRESERVED AS PER REQUEST ---
    # if not files:
    #     raise FileNotFoundError(f"No parquet files found for key: {sheet_key} in folder {folder_id}")
    # files_sorted = sorted(files, key=lambda x: x['name'], reverse=True)
    # ==============================
    # Filter out false-positives matched by Drive's tokenized 'name contains'
    files = [f for f in files if f['name'].lower().startswith(sheet_key.lower())]
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

# [PRODUCTION COMMENT - INPUT MIGRATION]
# Previous: Google Sheet 'P-L Master' -> Tab: 'P Master' (Columns A to J: Product id, SKU Class Prod, Product Name, Sub-category, etc.)
# Current: Parquet file downloaded from Google Drive ('p_master_*.parquet') from folder ID DRIVE_FOLDER_ID
# Load and clean p_master early to get Anchor ID mapping
logging.info("Starting Raw Data 6W step...")
logging.info("Loading p_master parquet...")
p_master_df = load_latest_parquet_from_drive("p_master")

# The downloaded parquet sometimes contains both "Product id" and "product_id".
# Keep a single canonical column to avoid pandas returning a DataFrame instead of a Series.
if "Product id" in p_master_df.columns and "product_id" in p_master_df.columns:
    p_master_df = p_master_df.rename(columns={"Product id": "_legacy_product_id"})
    p_master_df["_legacy_product_id"] = p_master_df["_legacy_product_id"].map(
        lambda x: pd.NA if pd.isna(x) or str(x).strip() == "" else str(x).strip()
    )
    p_master_df["product_id"] = p_master_df["product_id"].map(
        lambda x: pd.NA if pd.isna(x) or str(x).strip() == "" else str(x).strip()
    )
    p_master_df["product_id"] = p_master_df["product_id"].fillna(p_master_df["_legacy_product_id"])
    p_master_df = p_master_df.drop(columns=["_legacy_product_id"])
elif "Product id" in p_master_df.columns:
    p_master_df = p_master_df.rename(columns={"Product id": "product_id"})

if "product_id" not in p_master_df.columns:
    raise KeyError("The p_master parquet does not contain a 'product_id' column.")

p_master_df = p_master_df.reset_index(drop=True).copy()
p_master_df["product_id"] = p_master_df["product_id"].map(
    lambda x: "" if pd.isna(x) else str(x).strip()
)
p_master_df = p_master_df[p_master_df["product_id"] != ""].copy()

# Dynamic start date — always this week's Monday, no manual edit needed
today = dt_mod.date.today()
start_date = today - timedelta(days=today.weekday()) + timedelta(days=7)

# Columns + dynamic all-zero rows for the week
columns = [
    "Weeknum", "Weekday", "process_dt", "Agra", "Chandigarh", "Jaipur", "Central_India",
    "Coimbatore", "INDORE", "Kochi", "Surat", "Vijayawada", "Vizag", "Bangalore",
    "Mumbai", "NCR", "Pune", "Kolkata", "Chennai", "Hyderabad"
]
city_columns = columns[3:]
city_values = [0] * len(city_columns)

rows = []
for i in range(7):
    day_date = start_date + timedelta(days=i)
    row = [
        day_date.isocalendar()[1],
        day_date.strftime("%a"),
        f"{day_date.month}/{day_date.day}/{day_date.year}",
    ] + city_values
    rows.append(row)

# --- City_date: wide format ---
# [PRODUCTION COMMENT - INPUT & OUTPUT MIGRATION]
# Previous Output: Appended rows directly to Google Sheet 'Avl_Flag' -> Tab: 'City_date' (Columns: Weeknum, Weekday, process_dt, Agra, etc.)
# Current Output: Reads latest 'City_date_*.parquet' from Google Drive, appends, and uploads a new version directly to Drive folder ID DRIVE_FOLDER_ID
logging.info("Processing City_date and City_Cat outlier mappings...")
try:
    df_to_append = pd.DataFrame(rows, columns=columns)
    try:
        city_date_df = load_latest_parquet_from_drive("City_date")
        city_date_df = pd.concat([city_date_df, df_to_append], ignore_index=True)
    except Exception as read_err:
        print("Could not load latest City_date from Drive, creating new:", read_err)
        city_date_df = df_to_append
    _today_str = dt_mod.date.today().strftime('%Y%m%d')
    upload_df_to_drive_as_parquet(city_date_df, f"City_date_{_today_str}.parquet", DRIVE_FOLDER_ID)
    print(f"Appended week {rows[0][0]} to City_date parquet and uploaded.")
except Exception as e:
    print("Failed to write to City_date parquet:", e)

# --- City_Cat: melted format with Python Outlier lookup ---
# [PRODUCTION COMMENT - INPUT & OUTPUT MIGRATION]
# Previous Output: Appended rows to Google Sheet 'Avl_Flag' -> Tab: 'City_Cat' (Columns: Weeknum, city_name, sub category, process_dt, Outlier_Flag, day). Used complex XLOOKUP formulas.
# Current Output: Reads latest 'City_Cat_*.parquet' from Google Drive, resolves Outlier_Flag programmatically in Python, and uploads updated version directly to Drive folder ID DRIVE_FOLDER_ID
try:
    melt_columns = ["Weeknum", "city_name", "sub category", "process_dt", "Outlier_Flag", "day"]
    try:
        city_cat_df = load_latest_parquet_from_drive("City_Cat")
        sub_categories = city_cat_df["sub category"].unique().tolist()
    except Exception as read_err:
        print("Could not load latest City_Cat from Drive, using unique values from p_master:", read_err)
        sub_categories = p_master_df["Sub-category"].dropna().unique().tolist()
    
    # --- OLD CODE PRESERVED AS PER REQUEST ---
    # melt_rows = []
    # for week_num, weekday_str, date_str, *_ in rows:
    #     for sub_cat in sub_categories:
    #         for city in city_columns:
    #             # Resolve outlier flag directly using df_to_append (wide format value for the city)
    #             date_row = df_to_append[df_to_append["process_dt"] == date_str]
    #             outlier_val = int(date_row[city].iloc[0]) if not date_row.empty else 0
    #             melt_rows.append([week_num, city, sub_cat, date_str, outlier_val, weekday_str])
    # df_melt = pd.DataFrame(melt_rows, columns=melt_columns)
    # ==============================
    df_melted_cities = df_to_append.melt(
        id_vars=["Weeknum", "Weekday", "process_dt"],
        value_vars=city_columns,
        var_name="city_name",
        value_name="Outlier_Flag"
    )
    sub_cat_df = pd.DataFrame({"sub category": sub_categories})
    df_melt = df_melted_cities.merge(sub_cat_df, how="cross")
    df_melt = df_melt.rename(columns={"Weekday": "day"})
    df_melt = df_melt[["Weeknum", "city_name", "sub category", "process_dt", "Outlier_Flag", "day"]]
    if 'city_cat_df' in locals():
        city_cat_df = pd.concat([city_cat_df, df_melt], ignore_index=True)
    else:
        city_cat_df = df_melt
    city_cat_df["Weeknum"] = pd.to_numeric(city_cat_df["Weeknum"], errors="coerce").fillna(0).astype(int)
    city_cat_df["Outlier_Flag"] = pd.to_numeric(city_cat_df["Outlier_Flag"], errors="coerce").fillna(0).astype(int)
    _today_str = dt_mod.date.today().strftime('%Y%m%d')
    upload_df_to_drive_as_parquet(city_cat_df, f"City_Cat_{_today_str}.parquet", DRIVE_FOLDER_ID)
    # --- OLD CODE PRESERVED AS PER REQUEST ---
    # print(f"Appended {len(melt_rows)} melted rows to City_Cat parquet and uploaded.")
    # ==============================
    print(f"Appended {len(df_melt)} melted rows to City_Cat parquet and uploaded.")
except Exception as e:
    print("Failed to write to City_Cat parquet:", e)

    # Leftover GSheet writing logic removed
    pass
import tempfile

def download_file_from_drive_to_temp(file_id: str) -> str:
    scopes = ['https://www.googleapis.com/auth/drive.readonly']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS_DICT, scopes)
    service = build('drive', 'v3', credentials=creds)
    
    print(f"[Drive Loader] Downloading RDS file directly from Drive (ID: {file_id})")
    request = service.files().get_media(fileId=file_id)
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".RDS")
    downloader = MediaIoBaseDownload(temp_file, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        if status:
            print(f"Download {int(status.progress() * 100)}%.")
    
    temp_file.close()
    return temp_file.name

# [PRODUCTION COMMENT - INPUT]
# Input: Forecasting data file downloaded from Google Drive to a temp file
logging.info("Outlier processing completed. Downloading forecasting RDS file from Drive...")
rds_file_id = "1XIDXihOJzF1Ifdqogh0SZtmJyT1GZw4J"
temp_rds_path = download_file_from_drive_to_temp(rds_file_id)

result = pyreadr.read_r(temp_rds_path)
import os
os.remove(temp_rds_path)  # Clean up temp file
df = next(iter(result.values()))
df['process_dt'] = pd.to_datetime(df['process_dt'])

# --- OLD CODE PRESERVED AS PER REQUEST ---
# Baseline_df = df.copy()
# Baseline_df["Week"] = Baseline_df["process_dt"].dt.isocalendar().week
# Baseline_df["Year"] = Baseline_df["process_dt"].dt.isocalendar().year
# Baseline_df["day"] = Baseline_df["process_dt"].dt.strftime("%a")
# _today = pd.Timestamp.today()
# _target_week = _today.isocalendar().week
# _target_year = _today.isocalendar().year
# Baseline_df = Baseline_df[
#     (Baseline_df["Week"] == _target_week) & (Baseline_df["Year"] == _target_year)
# ]
# ==============================
_today = pd.Timestamp.today()
_target_week = _today.isocalendar().week
_target_year = _today.isocalendar().year

week_series = df["process_dt"].dt.isocalendar().week
year_series = df["process_dt"].dt.isocalendar().year
mask_target = (week_series == _target_week) & (year_series == _target_year)

Baseline_df = df[mask_target].copy()
Baseline_df["Week"] = _target_week
Baseline_df["Year"] = _target_year
Baseline_df["day"] = Baseline_df["process_dt"].dt.strftime("%a")

import gc
del result
gc.collect()
latest_date = pd.to_datetime(df['process_dt']).max().date()
print(latest_date)
end_date = pd.Timestamp.today().normalize() - pd.Timedelta(days=1)

# Start date = 10 weeks before end date
start_date = end_date - pd.Timedelta(weeks=10)

def day_week_info(dt):
    iso = dt.isocalendar()
    return f"{dt.strftime('%A')} | {dt.date()} | Week {iso.week}, {iso.year}"

print("Start Date:", day_week_info(start_date))
print("End Date  :", day_week_info(end_date))

# today = pd.to_datetime("today").normalize()
# weekday = today.weekday()

# # Monday=0, Tuesday=1, Wednesday=2
# if weekday in [0, 1, 2]:  # Mon, Tue, Wed
#     start_date = today - timedelta(days=9)
#     end_date = today - timedelta(days=1)
# else:  # Thu–Sun
#     start_date = today - timedelta(days=9)
#     end_date = today - timedelta(days=1)

# def day_week_info(dt):
#     iso = dt.isocalendar()
#     return f"{dt.strftime('%A')} | {dt.date()} | Week {iso.week}, {iso.year}"

# print("Today     :", day_week_info(today))
# print("Start Date:", day_week_info(start_date))
# print("End Date  :", day_week_info(end_date))
filtered_df = df[(df['process_dt'] >= start_date) & (df['process_dt'] <= end_date)]


print(filtered_df.columns.tolist())
# columns_to_keep = [
#     'city_name', 'product_id', 'hub_name', 'process_dt', 'sales','revenue',
#     'r7_plan', 'r7_inv', 'r7_plan_rev', 
#     'BasePlan', 'flag', 'instances',  'group_flag', 'group_instances','wastage_qty_Expiry', 'wastage_val_Quality', 'wastage_val_Expiry','wastage_qty_Quality',
# 'product_name', 'sub_category', 'Cut Classification','product_discount', 'instant_discount', 'coupon_discount', 'licious_cash', 'licious_cashp', 'price'
# ]

columns_to_keep = [
    'city_name', 'product_id', 'hub_name', 'process_dt', 'sales', 'group_flag', 'group_instances',
    'grp_r7_plan', 'grp_r7_inv', 'grp_r7_plan_rev', 'grp_r7_inv_rev','revenue',
    'grp_BasePlan', 'grp_BaseRev',
    'r7_plan', 'r7_inv', 'r7_plan_rev', 'r7_inv_rev',
    'BasePlan', 'flag', 'instances', 'wastage_qty_Expiry', 'wastage_qty_Quality', 'saleswithoutclusterv2','flagwithoutclusterv2','instanceswithoutclusterv2',
    'group_flagwithoutclusterv2','group_instanceswithoutclusterv2'
]

# print(filtered_df['sales'].sum())
filtered_df = filtered_df[columns_to_keep]

import gc
try:
    del df
    del result
except NameError:
    pass
gc.collect()
# Checkpoint write removed
pass

# import pandas as pd
# import gspread
# )

# # Open worksheet
# ppo = Hub_level_planning.worksheet("Pure Preorder")

# # Fetch data A:J
# data = ppo.get("A:B")

# # Convert to DataFrame
# ppo = pd.DataFrame(data[1:], columns=data[0])
# print(ppo.head())
# ppo.rename(columns={'Product id': 'product_id'}, inplace=True)
# pure_preorder_pairs = set(
#     zip(
#         ppo["hub_name"],
#         ppo["product_id"]
#     )
# )
# filtered_df["Bucket"] = filtered_df.apply(
#     lambda row: (
#         "Pure_preorder"
#         if (row["hub_name"], row["product_id"]) in pure_preorder_pairs
#         else "Others"
#     ),
#     axis=1
# )
filtered_df = filtered_df.loc[:, ~filtered_df.columns.duplicated()]
agg_df = (
    filtered_df[columns_to_keep]
    .groupby(['city_name', 'product_id', 'process_dt'], as_index=False)
    .agg({
        'sales': 'sum',
        'saleswithoutclusterv2' : 'sum',
        'group_instances': 'sum',
        'group_flag': 'sum',
        'r7_plan': 'sum',
        'r7_inv': 'sum',
        'r7_plan_rev': 'sum',
        'r7_inv_rev': 'sum',
        'BasePlan': 'sum',
        'revenue':'sum'
        
        
        
    })
)
filtered_df['wgt_flag'] = filtered_df['flag'] * filtered_df['r7_plan_rev']
filtered_df['wgt_instances'] = filtered_df['instances'] * filtered_df['r7_plan_rev']

filtered_df['new_grp_flag'] = np.where(
    filtered_df['r7_plan'] == 0,
    0,
    filtered_df['group_flag'] * filtered_df['grp_r7_plan_rev']
)

filtered_df['new_grp_instances'] = np.where(
    filtered_df['r7_plan'] == 0,
    0,
    filtered_df['group_instances'] * filtered_df['grp_r7_plan_rev']
)
filtered_df.columns
# Replaced Google Sheet read with existing p_master parquet read
P_Master = p_master_df[['product_id', 'Anchor ID', 'Avl_Flag']].drop_duplicates(subset=['product_id'])
merged_df = filtered_df.merge(P_Master, on="product_id", how="left")
merged_df['plan_sum'] = merged_df.groupby(['hub_name', 'process_dt', 'Anchor ID'])['r7_inv'].transform('sum')

merged_df['simple_flag_when_SP_0'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_flag'],  # Use anchor group's flag when plan_sum = 0
    merged_df['flag']
)
merged_df['simple_instances_when_SP_0'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_instances'],  # Use anchor group's instances when plan_sum = 0
    merged_df['instances']
)
merged_df['simple_group_flag_when_SP_0'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_flag'],  # Keep anchor group's flag (same value)
    merged_df['group_flag']
)
merged_df['simple_group_instances_when_SP_0'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_instances'],  # Keep anchor group's instances (same value)
    merged_df['group_instances']
)
merged_df['simple_flag_when_SP_0_withoutclusterv2'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_flagwithoutclusterv2'],  # Use anchor group's flag when plan_sum = 0
    merged_df['flagwithoutclusterv2']
)
merged_df['simple_instances_when_SP_0_withoutclusterv2'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_instanceswithoutclusterv2'],  # Use anchor group's instances when plan_sum = 0
    merged_df['instanceswithoutclusterv2']
)
merged_df['simple_group_flag_when_SP_0_withoutclusterv2'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_flagwithoutclusterv2'],  # Keep anchor group's flag (same value)
    merged_df['group_flagwithoutclusterv2']
)
merged_df['simple_group_instances_when_SP_0_withoutclusterv2'] = np.where(
    merged_df['plan_sum'] == 0,
    merged_df['group_instanceswithoutclusterv2'],  # Keep anchor group's instances (same value)
    merged_df['group_instanceswithoutclusterv2']
)
merged_df = merged_df.drop_duplicates(
    subset=["city_name", "hub_name", "product_id", "process_dt"]
)

print(merged_df.columns)
filtered_df = merged_df[
    [
        "city_name",
        "hub_name",
        "product_id",
        "process_dt",
        "sales",
        "saleswithoutclusterv2",
        "simple_flag_when_SP_0",
        "simple_instances_when_SP_0",
        "simple_group_flag_when_SP_0",
        "simple_group_instances_when_SP_0",
        "simple_flag_when_SP_0_withoutclusterv2",
        "simple_instances_when_SP_0_withoutclusterv2",
        "simple_group_flag_when_SP_0_withoutclusterv2",
        "simple_group_instances_when_SP_0_withoutclusterv2",
        "r7_plan",
        "r7_inv",
        "wastage_qty_Quality",
        "wastage_qty_Expiry"
        
    ]
]

# Checkpoint write removed
pass

# Database Connection (Presto/Trino)
conn = trino.dbapi.connect(
    host="trino.internal.dp.licious.com",
    port=80,
    user="default",
    catalog="hive",
    schema="planning",
    http_scheme="http",
)
cursor = conn.cursor()
Start = start_date.strftime("%Y-%m-%d")
End   = end_date.strftime("%Y-%m-%d")

query_hubs = f"""
SELECT
    fnl4.dt,
    fnl4.hubid,
    map.hub_name,
    map.city_name,
    fnl4.productid,
    fnl4.productname,
    fnl4.liq_discount_perc,
    fnl4.packets_sold,
    fnl4.gross_revenue AS "gross_revenue (mrp)"
FROM (
    SELECT
        dt,
        hubid,
        productid,
        productname,
        liq_discount_perc,
        SUM(productqty) AS packets_sold,
        SUM(mrpproductpricef) AS gross_revenue
    FROM (
        SELECT
            *,
            ROUND(
                (mrpproductpricef - productdiscountf)
                * 100.00 / mrpproductpricef,
                0
            ) AS liq_discount_perc
        FROM (
            SELECT
                *,
                CASE
                    WHEN pormotionlevers_string LIKE '%"type":"LIQUIDATION"%'
                    THEN 1 ELSE 0
                END AS flag
            FROM (
                SELECT
                    *,
                    array_join(
                        transform(
                            promotionlevers,
                            x -> format(
                                '{{"leverid":"%s","type":"%s"}}',
                                x.leverid,
                                x.type
                            )
                        ),
                        ',',
                        '[]'
                    ) AS pormotionlevers_string
                FROM b2c_supplychain.order_item_events_fact
                WHERE status != 'Rejected'
                  AND (
                        yr > year(current_date - interval '84' day)
                     OR (
                            yr  = year(current_date - interval '84' day)
                        AND mon >= month(current_date - interval '84' day)
                        )
                      )
            ) fnl
        ) fnl2
        WHERE flag = 1
    ) fnl3
    WHERE CAST(dt AS DATE)
          BETWEEN
            CAST(date_parse('{Start}', '%Y-%m-%d') AS DATE)
        AND
            CAST(date_parse('{End}', '%Y-%m-%d') AS DATE)
    GROUP BY
        dt,
        hubid,
        productid,
        productname,
        liq_discount_perc
) fnl4
LEFT JOIN pipeline.city_mapping_ba map
    ON CAST(map.hub_id AS VARCHAR) = fnl4.hubid
ORDER BY
    1, 2, 5, 8 DESC
"""

cursor.execute(query_hubs)
 #Fetch all rows
rows = cursor.fetchall()

# Get column names from cursor description
columns = [col[0] for col in cursor.description]

# Create DataFrame
infinity_data = pd.DataFrame(rows, columns=columns)

# Optional: inspect
print(infinity_data.head())

infinity_data.rename(
    columns={
        "productid": "product_id",
        "dt" : "process_dt"
    },
    inplace=True
)

print(infinity_data["process_dt"].dtype)
print(infinity_data.columns)
infinity_data["process_dt"]= pd.to_datetime(infinity_data["process_dt"], errors="coerce")



# --- OLD CODE PRESERVED AS PER REQUEST ---
# infinity_data.to_clipboard()
# ==============================
pass
infinity_data = (
    infinity_data.groupby(['process_dt', 'hub_name', 'product_id'], as_index=False)
      .agg({
          'packets_sold': 'sum'
      })
)
merged_df = filtered_df.merge(
    infinity_data[["hub_name", "product_id", "process_dt","packets_sold"]],
    on=["hub_name", "product_id", "process_dt"],
    how="left",
    indicator=True
)
print(merged_df.columns)
merged_df['packets_sold']= merged_df['packets_sold'].fillna(0)
merged_df['final_sales'] = np.maximum(
    merged_df['sales'] - merged_df['packets_sold'],
    0
)
merged_df['final_sales_withoutclusterv2'] = np.maximum(
    merged_df['saleswithoutclusterv2'] - merged_df['packets_sold'],
    0
)
merged_df = merged_df.drop(columns=["_merge"])

# --- OLD CODE PRESERVED AS PER REQUEST ---
# p_master_lookup = p_master_df.drop_duplicates(subset="product_id", keep="first").copy()
# sku_map = p_master_lookup.set_index("product_id")["SKU Class Prod"]
# name_map = p_master_lookup.set_index("product_id")["Product Name"]
# category_map = p_master_lookup.set_index("product_id")["Sub-category"]
# merged_df["sku class prod"] = merged_df["product_id"].astype(str).str.strip().map(sku_map)
# merged_df["product_name"] = merged_df["product_id"].astype(str).str.strip().map(name_map)
# merged_df["Sub-category"] = merged_df["product_id"].astype(str).str.strip().map(category_map)
# ==============================
p_master_clean = p_master_df[['product_id', 'SKU Class Prod', 'Product Name', 'Sub-category']].drop_duplicates(subset=['product_id'])
p_master_clean = p_master_clean.rename(columns={
    'SKU Class Prod': 'sku class prod',
    'Product Name': 'product_name'
})
merged_df = merged_df.merge(p_master_clean, on="product_id", how="left")
merged_df = merged_df[~merged_df["hub_name"].str.startswith("PAW", na=False)]

# --- OLD CODE PRESERVED AS PER REQUEST ---
# merged_df.to_clipboard
# ==============================
pass
print(merged_df.columns)
merged_df["day"] = merged_df["process_dt"].dt.strftime("%a")

merged_df["week"] = merged_df["process_dt"].dt.isocalendar().week

final_cols = [
    "process_dt",
    "Sub-category",
    "week",
    "day",
    "product_id",
    "product_name",
    "sku class prod",
    "city_name",
    "hub_name",
    "final_sales",
    "final_sales_withoutclusterv2",
    "wastage_qty_Quality",
    "wastage_qty_Expiry",
    "simple_flag_when_SP_0",
    "simple_instances_when_SP_0",
    "simple_group_flag_when_SP_0",
    "simple_group_instances_when_SP_0",
    "simple_flag_when_SP_0_withoutclusterv2",
    "simple_instances_when_SP_0_withoutclusterv2",
    "simple_group_flag_when_SP_0_withoutclusterv2",
    "simple_group_instances_when_SP_0_withoutclusterv2",
    "r7_plan",
    "r7_inv"
]

merged_df = merged_df[final_cols]

merged_df = merged_df.dropna(subset=["Sub-category", "product_id"])
weekly_sales = (
    merged_df
    .groupby("week", as_index=False)
    .agg(
        sales_sum=("final_sales", "sum"),
        sales_withoutclusterv2_sum=("final_sales_withoutclusterv2", "sum")
    )
)

print(weekly_sales)
logging.info("Starting Google Drive uploads...")
# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as a CSV file to 'RAW_DATA_CSV_PATH'
# Current Output: Uploaded in-memory directly to Google Drive as 'Raw_data.parquet' to folder ID RAW_DATA_DRIVE_FOLDER_ID
os.makedirs("new_output", exist_ok=True)
merged_df.to_csv("new_output/Final_merged_data.csv", index=False)
upload_df_to_drive_as_parquet_async(merged_df, "Raw_data.parquet", RAW_DATA_DRIVE_FOLDER_ID)
# Baseline_df was already extracted and filtered at the start to save memory
Baseline_df.to_parquet(f"new_output/Baseline_Wk{_target_week}_{_target_year}.parquet", index=False)

# --- OLD CODE PRESERVED AS PER REQUEST ---
# Baseline_df["sku class prod"] = Baseline_df["product_id"].astype(str).str.strip().map(sku_map)
# Baseline_df["product_name"] = Baseline_df["product_id"].astype(str).str.strip().map(name_map)
# Baseline_df["Sub-category"] = Baseline_df["product_id"].astype(str).str.strip().map(category_map)
# ==============================
# Drop any existing master columns in Baseline_df to prevent _x / _y duplicate suffixes
cols_to_drop = [c for c in ['sku class prod', 'product_name', 'Sub-category', 'sub_category'] if c in Baseline_df.columns]
Baseline_df = Baseline_df.drop(columns=cols_to_drop)
Baseline_df = Baseline_df.merge(p_master_clean, on="product_id", how="left")
print(Baseline_df.columns)
final_cols = [
    "process_dt",
    "Sub-category",
    "Week",
    "day",
    "product_id",
    "product_name",
    "city_name",
    "hub_name",
    "BasePlan",
    "sku class prod"
]

Baseline_df = Baseline_df[final_cols]
Week = Baseline_df["Week"].iloc[0]


print(Week)

# [PRODUCTION COMMENT - OUTPUT MIGRATION]
# Previous Output: Written locally as an Excel file Baseline Wk{Week} 2026.xlsx to BASE_PATH
# Current Output: Uploaded in-memory directly to Google Drive as 'Baseline Wk{Week} 2026.parquet' to folder ID BASELINE_DRIVE_PARQUET_FOLDER_ID
# ========================================================================================================================
# dynamic date
file_name = f"Baseline Wk{_target_week} {_target_year}.parquet"
upload_df_to_drive_as_parquet_async(Baseline_df, file_name, BASELINE_DRIVE_PARQUET_FOLDER_ID)
wait_for_all_uploads()
logging.info("Raw Data 6W step completed successfully.")

