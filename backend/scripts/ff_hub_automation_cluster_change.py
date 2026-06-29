# %% Cell 1
import os
import sys
import argparse
import pyreadr
import pandas as pd
import numpy as np
import gspread
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from gspread_dataframe import set_with_dataframe

# ── CLI date arguments ─────────────────────────────────────────────────────────
_parser = argparse.ArgumentParser(description="FF Hub Automation – Cluster Change")
_parser.add_argument("--start_date", type=str, default=None,
                     help="Final Forecast start date YYYY-MM-DD (Monday)")
_parser.add_argument("--end_date",   type=str, default=None,
                     help="Final Forecast end date YYYY-MM-DD (Sunday)")
_args, _unknown = _parser.parse_known_args()

if _args.start_date and _args.end_date:
    FCST_START = datetime.strptime(_args.start_date, "%Y-%m-%d")
    FCST_END   = datetime.strptime(_args.end_date,   "%Y-%m-%d")
else:
    # Default: current week Mon–Sun
    _today     = datetime.today()
    FCST_START = _today - timedelta(days=_today.weekday())
    FCST_END   = FCST_START + timedelta(days=6)

REPL_START = FCST_START + timedelta(weeks=1)
REPL_END   = FCST_END   + timedelta(weeks=1)

_week_num  = FCST_START.isocalendar()[1]
_year      = FCST_START.year
OUTPUT_FILE = f"Hub_Dist_Wk{_year}{str(_week_num).zfill(2)}.xlsx"

print(f"[Config] Final Fcst:  {FCST_START.date()} → {FCST_END.date()}")
print(f"[Config] Replication: {REPL_START.date()} → {REPL_END.date()}")
print(f"[Config] Output file: {OUTPUT_FILE}")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_src = os.path.join(_PROJECT_ROOT, "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
from dotenv import load_dotenv
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))
from planning_suite.config.settings import (
    DEMAND_PLANNING_MASTERS_SHEET_URL,
    DP_LOGICS_SHEET_URL,
    EA_TRACKER_SHEET_URL,
    FF_INPUTS_FOLDER,
    FF_INV_LOGIC_FOLDER,
    FF_MASTERS_XLSX,
    GOOGLE_CREDENTIALS_PATH,
    INVENTORY_BUFFER_SHEET_URL,
    sheet_id_from_url,
)

def _ui_step(msg):
    """Lightweight progress logger visible in terminal/Streamlit script output."""
    print(f"[UI STEP] {msg}", flush=True)

# ── Constants (from .env via planning_suite.config) ───────────────────────────
_CREDS = GOOGLE_CREDENTIALS_PATH
_DPM_KEY = sheet_id_from_url(DEMAND_PLANNING_MASTERS_SHEET_URL)
_DP_LOGICS_KEY = sheet_id_from_url(DP_LOGICS_SHEET_URL)
_INV_LOGICS_KEY = sheet_id_from_url(INVENTORY_BUFFER_SHEET_URL)
_INPUTS_DIR = FF_INPUTS_FOLDER
_INV_DIR = FF_INV_LOGIC_FOLDER
_MASTERS_XLSX = FF_MASTERS_XLSX

# ── GSpread client ─────────────────────────────────────────────────────────────
# %% Cell 2
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(_CREDS, scope)
client = gspread.authorize(creds)

def _sheet_to_df(ws, range_notation=None):
    """Read worksheet data safely (handles duplicate/blank headers)."""
    data = ws.get(range_notation) if range_notation else ws.get_all_values()
    if not data or len(data) < 1:
        return pd.DataFrame()

    headers = [str(c).strip() for c in data[0]]
    rows_raw = data[1:]

    width = max([len(headers)] + [len(r) for r in rows_raw]) if rows_raw else len(headers)
    headers = headers + [""] * (width - len(headers))
    rows = [(r[:width] + [""] * (width - len(r))) for r in rows_raw]

    df = pd.DataFrame(rows, columns=headers)

    # Drop completely blank header columns and deduplicate repeated names.
    df = df.loc[:, df.columns != ""]
    seen = {}
    dedup_cols = []
    for col in df.columns:
        if col in seen:
            seen[col] += 1
            dedup_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 1
            dedup_cols.append(col)
    df.columns = dedup_cols
    return df


def _excel_tab_to_df(path, sheet_name, usecols=None):
    """Read a master tab from local Product_Masters.xlsx."""
    df = pd.read_excel(path, sheet_name=sheet_name, usecols=usecols)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# Hub level Suggestion from DP Logics sheet
_ui_step("Loading Hub level Suggestion and P-H Master")
_dp_logics_ss = client.open_by_key(_DP_LOGICS_KEY)
Hub_level_Suggestion = _dp_logics_ss.worksheet("Hub level Suggestion")
data = Hub_level_Suggestion.get("A:F")
Hub_suggestion = pd.DataFrame(data[1:], columns=data[0])
Hub_suggestion.columns = [c.strip() for c in Hub_suggestion.columns]
print(f"[Hub Suggestion] {len(Hub_suggestion):,} rows loaded")
print(Hub_suggestion.describe(include="all"))

# %% Cell 3
# P-H Master from synced local Product_Masters.xlsx
if not os.path.exists(_MASTERS_XLSX):
    raise FileNotFoundError(
        f"Master file not found: {_MASTERS_XLSX}. "
        "Sync Masters first from the Master Data page."
    )
ph_master_raw = _excel_tab_to_df(_MASTERS_XLSX, "P-H Master", usecols="A:AX")
print(f"[P-H Master] {len(ph_master_raw):,} rows loaded from {_MASTERS_XLSX}")

# Standardise column names to match downstream code (which was written for P-L Master)
_col_map = {}
for c in ph_master_raw.columns:
    cl = c.lower().strip()
    if cl in ('product_id', 'product id') and c != 'Product id':
        _col_map[c] = 'Product id'
    elif cl == 'sku class prod' and c != 'SKU Class Prod':
        _col_map[c] = 'SKU Class Prod'

Master_df = ph_master_raw.rename(columns=_col_map).copy()

# Ensure City alias exists (P-H Master uses city_name)
if 'City' not in Master_df.columns and 'city_name' in Master_df.columns:
    Master_df['City'] = Master_df['city_name']

# Channel used in downstream melt filters – P-H Master is all Online
if 'Channel' not in Master_df.columns:
    Master_df['Channel'] = 'Online'

# # Order Type alias
# if 'Order Type - pan india' not in Master_df.columns:
#     if 'Plan Design' in Master_df.columns:
#         Master_df['Order Type - pan india'] = Master_df['Plan Design']
#     else:
#         Master_df['Order Type - pan india'] = 'E'

# Cut class alias (must come from P-H Master cut-classification columns first)
if 'Cut class' not in Master_df.columns:
    _cut_class_candidates = [
        'Cut Classification',   # space variant (preferred)
        'Cut_Classification',   # underscore variant
        'cut classification',
        'cut_classification',
        'CutClass',
        'cutclass',
        'cut class',
    ]
    _norm_cols = {str(c).strip().lower().replace("_", " "): c for c in Master_df.columns}
    _picked_cut_col = None
    for _cc in _cut_class_candidates:
        _actual = _norm_cols.get(_cc.lower().replace("_", " "))
        if _actual is not None:
            _picked_cut_col = _actual
            break
    if _picked_cut_col is not None:
        Master_df['Cut class'] = Master_df[_picked_cut_col]
        print(f"[Cut class] Using P-H column: {_picked_cut_col}")
    else:
        # Final fallback only if P-H has no cut-classification column at all.
        Master_df['Cut class'] = Master_df.get('SKU Class Prod', '')
        print("[Cut class] WARNING: No cut-classification column in P-H Master; fallback to SKU Class Prod.")

# DOC flag – default 0 if missing
if 'DOC/Percentage_BufferFlag' not in Master_df.columns:
    Master_df['DOC/Percentage_BufferFlag'] = 0

Master_df.describe(include='all')

# %% Cell 4
# Prefer hub+sku lookup for Cut class from P-H, fallback to sku-only.
_cut_lkp = Master_df[['hub_name', 'SKU Class Prod', 'Cut class']].copy()
_cut_lkp['Cut class'] = _cut_lkp['Cut class'].astype(str).str.strip()
_cut_lkp = _cut_lkp[_cut_lkp['Cut class'] != ""]
_cut_lkp = _cut_lkp.drop_duplicates(subset=['hub_name', 'SKU Class Prod'], keep='first')
_cut_lkp = _cut_lkp.rename(columns={'SKU Class Prod': 'sku class prod'})

Hub_suggestion = Hub_suggestion.merge(
    _cut_lkp,
    on=['hub_name', 'sku class prod'],
    how='left'
)

_sku_cut_lkp = (
    Master_df[['SKU Class Prod', 'Cut class']]
    .dropna(subset=['Cut class'])
    .drop_duplicates(subset=['SKU Class Prod'], keep='first')
    .rename(columns={'SKU Class Prod': 'sku class prod'})
)
Hub_suggestion = Hub_suggestion.merge(
    _sku_cut_lkp,
    on='sku class prod',
    how='left',
    suffixes=('', '_sku')
)
Hub_suggestion['Cut class'] = (
    Hub_suggestion['Cut class'].astype(str).str.strip()
    .replace('nan', '')
)
Hub_suggestion['Cut class'] = Hub_suggestion['Cut class'].mask(
    Hub_suggestion['Cut class'] == '',
    Hub_suggestion['Cut class_sku'].astype(str).str.strip().replace('nan', '')
)
Hub_suggestion.drop(columns=['Cut class_sku'], inplace=True, errors='ignore')
Hub_suggestion.describe(include='all')


# %% Cell 5
# Hub Sku Master: reuse P-H Master (hub-level data, same source)
Hub_Master = ph_master_raw.copy()
Hub_Master.columns = [c.strip() for c in Hub_Master.columns]

# Ensure required columns for Cell 8 melt exist
if 'sku class prod' not in Hub_Master.columns:
    _sc = [c for c in Hub_Master.columns if c.lower().strip() == 'sku class prod']
    if _sc:
        Hub_Master = Hub_Master.rename(columns={_sc[0]: 'sku class prod'})

if 'Plan Flag' not in Hub_Master.columns:
    if 'Plan Design' in Hub_Master.columns:
        Hub_Master['Plan Flag'] = Hub_Master['Plan Design']
    else:
        Hub_Master['Plan Flag'] = 'A'

print(Hub_Master[Hub_Master.duplicated(subset=['hub_name', 'sku class prod'])])
Hub_Master.describe(include='all')

# %% Cell 6
# (clipboard removed – running as script)

# %% Cell 7
day_map = {
    "Active_Flag_Mon": "Mon",
    "Active_Flag_Tue": "Tue",
    "Active_Flag_Wed": "Wed",
    "Active_Flag_Thu": "Thu",
    "Active_Flag_Fri": "Fri",
    "Active_Flag_Sat": "Sat",
    "Active_Flag_Sun": "Sun"
}


# %% Cell 8
hub_master_long = Hub_Master.melt(
    id_vars=["hub_name", "sku class prod", "Plan Flag"],
    value_vars=day_map.keys(),
    var_name="flag_col",
    value_name="active"
)

# %% Cell 9
# Map flag column to actual day name
hub_master_long["day"] = hub_master_long["flag_col"].map(day_map)


# %% Cell 10
pass  # clipboard removed

# %% Cell 11
hub_master_long["active"] = pd.to_numeric(hub_master_long["active"], errors="coerce").fillna(0).astype(int)



# %% Cell 12
active_skus = hub_master_long[["hub_name", "sku class prod", "day", "Plan Flag", "active"]].copy()
active_skus["active"] = pd.to_numeric(active_skus["active"], errors="coerce").fillna(0).astype(int)
active_skus = active_skus[active_skus["Plan Flag"] != "I"]

# Ensure unique active map by hub×sku×day to prevent many-to-many multiplications.
active_skus = (
    active_skus
    .groupby(["hub_name", "sku class prod", "day"], as_index=False)["active"]
    .max()
)
active_skus = active_skus[active_skus["active"] == 1]



# %% Cell 13
Hub_suggestion["Base_plan"] = pd.to_numeric(Hub_suggestion.get("Base_plan"), errors="coerce").fillna(0)
Hub_suggestion_unique = (
    Hub_suggestion
    .groupby(["hub_name", "sku class prod", "day"], as_index=False)
    .agg({
        "Cut class": "first",
        "Base_plan": "sum"
    })
)

merged = active_skus.merge(
    Hub_suggestion_unique[["hub_name", "sku class prod", "day", "Cut class", "Base_plan"]],
    on=["hub_name", "sku class prod", "day"],
    how="left",
    indicator=True,
    validate="one_to_one"
)


# %% Cell 14
dupes = hub_master_long[
    hub_master_long.duplicated(subset=["hub_name", "sku class prod", "day"], keep=False)
].sort_values(["hub_name", "sku class prod", "day"])

if not dupes.empty:
    print(f"Found {len(dupes)} duplicate rows in hub_master_long:")
    print(dupes)
else:
    print("No duplicates found.")

# Add unique hub→city map after active merge to keep city_name downstream.
_hub_city_map = (
    Hub_Master[['hub_name', 'city_name']]
    .dropna(subset=['hub_name'])
    .drop_duplicates(subset=['hub_name'], keep='first')
)

# %% Cell 15
# Active SKUs present in Hub_suggestion
filtered_hub_level_suggestion = merged.query("_merge == 'both'").drop(columns="_merge")
filtered_hub_level_suggestion = filtered_hub_level_suggestion.merge(_hub_city_map, on='hub_name', how='left')
_dup_keys = ["hub_name", "sku class prod", "day"]
_before = len(filtered_hub_level_suggestion)
filtered_hub_level_suggestion = filtered_hub_level_suggestion.drop_duplicates(subset=_dup_keys, keep='first')
_removed = _before - len(filtered_hub_level_suggestion)
if _removed > 0:
    print(f"[Dedup] Removed {_removed:,} duplicate rows from filtered_hub_level_suggestion on {_dup_keys}.")

# %% Cell 16
pass  # active == 0 rows already excluded in Cell 12

# %% Cell 17
# Active SKUs missing from Hub_suggestion
missing_active_skus = merged.query("_merge == 'left_only'").drop(columns="_merge")

# %% Cell 18
# Print what is actually present in Hub_suggestion for reference
print("\n=== Hub_suggestion unique SKUs ===")
print(f"Total rows: {len(Hub_suggestion):,}")
print(f"Unique hub_name values ({Hub_suggestion['hub_name'].nunique()}): {sorted(Hub_suggestion['hub_name'].unique())}")
print(f"Unique sku class prod values ({Hub_suggestion['sku class prod'].nunique()}):")
print(sorted(Hub_suggestion['sku class prod'].unique()))
print(f"Unique day values: {sorted(Hub_suggestion['day'].unique())}")

if not missing_active_skus.empty:
    print(f"\n⚠️  WARNING: {len(missing_active_skus)} active hub×sku×day combos missing from Hub_suggestion.")
    print("Missing breakdown by hub:")
    print(missing_active_skus.groupby(['hub_name', 'sku class prod'])['day'].apply(list).to_string())
    print("\nThese rows will have Base_plan = 0 (treated as inactive).")
    # Set Base_plan = 0 for missing rows instead of crashing
    missing_active_skus = missing_active_skus.copy()
    missing_active_skus['Base_plan'] = 0
    missing_active_skus['Cut class'] = missing_active_skus['sku class prod']
    missing_active_skus = missing_active_skus.merge(_hub_city_map, on='hub_name', how='left')
    filtered_hub_level_suggestion = pd.concat(
        [filtered_hub_level_suggestion, missing_active_skus.drop(columns=['active'], errors='ignore')],
        ignore_index=True
    )
else:
    print("✅ All active SKUs are present in Hub_suggestion.")

# %% Cell 19
pass  # clipboard removed

# %% Cell 20
pass  # debug export removed


# %% Cell 21
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

# %% Cell 22
# New_Hub_Launch = Hub_level_planning.worksheet("New_Hub_Launch")

# # Get all values from A to L (1st to 12th column)
# data = New_Hub_Launch.get("A:F")  # Fetch only columns A to L

# # Convert to DataFrame
# Hub_Launch = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# # Display DataFrame
# Hub_Launch.describe(include='all')

# %% Cell 23
# final_df['date'] = pd.to_datetime(final_df['date'])
# Hub_Launch['Launch_Date'] = pd.to_datetime(Hub_Launch['Launch_Date'])

# %% Cell 24
# existing_hubs = set(final_df['hub_name'])
# Hub_Launch = Hub_Launch[~Hub_Launch['New_Hub'].isin(existing_hubs)].copy()

# %% Cell 25
# # Step 2: Merge on Source Hub
# merged = final_df.merge(
#     Hub_Launch,
#     left_on=['hub_name', 'city_name'],
#     right_on=['Source Hub', 'city_name'],
#     how='inner'
# )

# %% Cell 26
# # Step 3: Filter dates strictly before launch
# merged = merged[merged['Launch_Date'] < merged['date']]

# %% Cell 27
# merged['Percentage'] = merged['Percentage'].astype(str).str.replace('%', '').astype(float)
# merged['volume_transferred'] = np.round(merged['Base_plan'] * (merged['Percentage']), 0)

# %% Cell 28
# # Step 5: Update source hub Base_plan
# # First, sum total transferred per source hub per SKU/date
# source_updates = (
#     merged
#     .groupby(['city_name', 'hub_name', 'sku class prod', 'day', 'date'], as_index=False)
#     .agg(total_transferred=('volume_transferred', 'sum'),
#          original_plan=('Base_plan', 'first'))
# )
# source_updates['volume_remaining'] = np.maximum(source_updates['original_plan'] - source_updates['total_transferred'],0)


# %% Cell 29
# # Merge back to update
# final_df = final_df.merge(
#     source_updates[['city_name', 'hub_name', 'sku class prod', 'day', 'date', 'volume_remaining']],
#     on=['city_name', 'hub_name', 'sku class prod', 'day', 'date'],
#     how='left'
# )

# %% Cell 30
# final_df['Base_plan'] = np.where(
#     final_df['volume_remaining'].notna(),
#     final_df['volume_remaining'],
#     final_df['Base_plan']
# )
# final_df.drop(columns=['volume_remaining'], inplace=True)

# %% Cell 31
# # Step 6: Create new hub rows
# new_hub_rows = (
#     merged
#     .groupby(['city_name', 'New_Hub', 'sku class prod', 'Cut class', 'day', 'date'], as_index=False)
#     ['volume_transferred'].sum()
#     .rename(columns={'New_Hub': 'hub_name', 'volume_transferred': 'Base_plan'})
# )

# %% Cell 32
# # Step 7: Add zero-volume rows for completeness
# all_combos = final_df[['city_name', 'sku class prod', 'Cut class', 'day', 'date']].drop_duplicates()
# new_hub_ids = Hub_Launch[['city_name', 'New_Hub']].drop_duplicates().rename(columns={'New_Hub': 'hub_name'})
# zero_volume_rows = (
#     all_combos.assign(Base_plan=0)
#     .merge(new_hub_ids, on='city_name', how='inner')
# )

# %% Cell 33
# # Merge transferred volumes with zero-volume base
# new_hub_rows = pd.concat([new_hub_rows, zero_volume_rows], ignore_index=True).drop_duplicates(
#     subset=['city_name', 'hub_name', 'sku class prod', 'Cut class', 'day', 'date'],
#     keep='first'
# )


# %% Cell 34
# # Step 8: Append to final_df
# final_df = pd.concat([final_df, new_hub_rows], ignore_index=True)
# final_df.sort_values(['city_name', 'hub_name', 'sku class prod', 'date'], inplace=True)

# %% Cell 35
final_df.to_csv("Hub_level_plan.csv",index=False)

# %% Cell 36
# # Select the specific sheet/tab by its name
# worksheet = spreadsheet.worksheet("Festive Factor")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:G")  # Fetch only columns A to L

# # Convert to DataFrame
# festive_factor = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# print(festive_factor[festive_factor.duplicated(subset=['city_name', 'Cut class', 'date'])])

# # Display DataFrame
# festive_factor.describe()

# %% Cell 37
# # Ensure date format matches
# festive_factor["date"] = pd.to_datetime(festive_factor["date"]).dt.strftime("%Y-%m-%d")
# final_df["date"] = pd.to_datetime(final_df["date"]).dt.strftime("%Y-%m-%d")

# # Merge on 'date', 'Cut class', and 'city_name'
# FF_corrected_plan = final_df.merge(festive_factor, on=["date", "city_name", "Cut class"], how="left")
# FF_corrected_plan.to_csv("check.csv")


# def parse_festive_factor(val):
#     if isinstance(val, str) and "%" in val:
#         return float(val.replace("%", "")) / 100
#     try:
#         return float(val)
#     except:
#         return 0  # Or np.nan if you prefer to track invalids

# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Festive Factor"].apply(parse_festive_factor)


# FF_corrected_plan["Base_plan"] = pd.to_numeric(FF_corrected_plan["Base_plan"], errors="coerce")






# %% Cell 38
# worksheet = spreadsheet.worksheet("Festive Factor_Hub")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:I")  # Fetch only columns A to L

# # Convert to DataFrame
# festive_factor_hub = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# print(festive_factor[festive_factor.duplicated(subset=['city_name', 'Cut class', 'date'])])

# # Display DataFrame
# festive_factor.describe()

# %% Cell 39
# festive_long = festive_factor_hub.melt(
#     id_vars=["city_name", "Hub"],
#     var_name="date",
#     value_name="Hub_Festive_Factor"
# )


# %% Cell 40
# FF_corrected_plan = FF_corrected_plan.merge(
#     festive_long,
#     left_on=["city_name", "hub_name", "date"],
#     right_on=["city_name", "Hub", "date"],
#     how="left"
# )

# %% Cell 41
# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Hub_Festive_Factor"].fillna(FF_corrected_plan["Festive Factor"])


# %% Cell 42
# FF_corrected_plan["Base_plan"] = pd.to_numeric(FF_corrected_plan["Base_plan"], errors="coerce")
# FF_corrected_plan["Festive Factor"] = pd.to_numeric(FF_corrected_plan["Festive Factor"], errors="coerce")

# # Fill NaN with 0 (so no errors in multiplication)
# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Festive Factor"].fillna(0)


# %% Cell 43
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

# %% Cell 44

# print(FF_corrected_plan["final_plan"].sum())
# FF_corrected_plan.describe(include="all")

# %% Cell 45
# FF_corrected_plan.to_csv("total_plan.csv",index=False)

# %% Cell 46
festive_file_path = os.path.join(_INPUTS_DIR, "Festive.xlsx")
sheet_name = "Hub Festive"

# ---------------- READ EXCEL ----------------
hub_festive_factor = pd.read_excel(
    festive_file_path,
    sheet_name=sheet_name,
    usecols="B:H"
)
print(f"[Festive] {len(hub_festive_factor):,} rows loaded from {festive_file_path}")

# %% Cell 47
hub_festive_factor.head()

# %% Cell 48
print(hub_festive_factor[hub_festive_factor.duplicated(subset=['hub_name', 'Cut class', 'date'])])

# %% Cell 49
# # Open the Google Sheet by URL
# Festive = client.open_by_url("https://docs.google.com/spreadsheets/d/1_82bd2CsJVbLq0skI8Xr-ccG2QPuS_vH2mWP-rKoRAE/edit")


# # Select the specific sheet/tab by its name
# worksheet = Festive.worksheet("Hub Festive")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:H")  # Fetch only columns A to L

# # Convert to DataFrame
# hub_festive_factor = pd.DataFrame(data[1:], columns=data[0])  # First row as header
# print(hub_festive_factor[hub_festive_factor.duplicated(subset=['hub_name', 'Cut class', 'date'])])

# # Display DataFrame
# hub_festive_factor.describe()

# %% Cell 50
hub_festive_factor["date"] = pd.to_datetime(hub_festive_factor["date"]).dt.strftime("%Y-%m-%d")
final_df["date"] = pd.to_datetime(final_df["date"]).dt.strftime("%Y-%m-%d")

# Merge on 'date', 'Cut class', and 'city_name'
FF_corrected_plan = final_df.merge(hub_festive_factor, on=["date", "hub_name", "Cut class"], how="left")
FF_corrected_plan.to_csv("check.csv")


def parse_festive_factor(val):
    if isinstance(val, str) and "%" in val:
        return float(val.replace("%", "")) / 100
    try:
        return float(val)
    except:
        return 0  # Or np.nan if you prefer to track invalids

# Strip trailing '%' if present, then coerce to float (vectorised — replaces apply(parse_festive_factor))
FF_corrected_plan["Hub level Festive Factor"] = (
    FF_corrected_plan["Hub level Festive Factor"]
    .astype(str).str.replace("%", "", regex=False).str.strip()
)

# %% Cell 51
FF_corrected_plan["Hub level Festive Factor"] = pd.to_numeric(FF_corrected_plan["Hub level Festive Factor"], errors="coerce")

# Fill NaN with 0 (so no errors in multiplication)
FF_corrected_plan["Hub level Festive Factor"] = FF_corrected_plan["Hub level Festive Factor"].fillna(0)

# FF_corrected_plan["Festive Factor"] = FF_corrected_plan["Hub_Festive_Factor"].fillna(FF_corrected_plan["Festive Factor"])

# %% Cell 52
# Step 1: Continuous festive-adjusted plan
FF_corrected_plan["raw_festive_plan"] = FF_corrected_plan["Base_plan"] * (1 + FF_corrected_plan["Hub level Festive Factor"])

# Step 2: Initial rounding (nearest integer)
FF_corrected_plan["final_plan"] = np.round(FF_corrected_plan["raw_festive_plan"]).astype(int)

# Step 3: Decimal remainders for reconciliation
FF_corrected_plan["remainder"] = FF_corrected_plan["raw_festive_plan"] - FF_corrected_plan["final_plan"]


# Step 4: Reconciliation loop city by city
for city, group in FF_corrected_plan.groupby(["hub_name", "Sub-category", "date"]):
    target = round(group["raw_festive_plan"].sum())   # exact city-level festive target
    current = group["final_plan"].sum()             # what we have after rounding
    diff = int(target - current)

    if diff > 0:
        # Add +1 to hubs with largest remainders
        idx = group["remainder"].nlargest(diff).index
        FF_corrected_plan.loc[idx, "final_plan"] += 1

    elif diff < 0:
        # Subtract -1 from hubs with smallest remainders
        idx = group["remainder"].nsmallest(abs(diff)).index
        FF_corrected_plan.loc[idx, "final_plan"] -= 1

# %% Cell 53
pass  # clipboard removed

# %% Cell 54
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



# %% Cell 55
print(FF_corrected_plan.columns)

# %% Cell 56
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
FF_corrected_plan.to_csv("FF_corrected_plan.csv",index=False)

# %% Cell 57
pass  # clipboard removed

# %% Cell 58
# Filter P-H Master: use hub_name + sku class prod as join key (hub-level, more granular)
_ph_for_split = Master_df[['hub_name', 'SKU Class Prod', 'Product id', 'Split %', 'DOC/Percentage_BufferFlag']].copy()
_ph_for_split = _ph_for_split.rename(columns={'SKU Class Prod': 'sku class prod'})
# Keep product-level granularity: one hub+sku can map to multiple product_ids.
_ph_for_split = _ph_for_split.drop_duplicates(subset=['hub_name', 'sku class prod', 'Product id'], keep='first')

# Parse split percentage safely (e.g. "25%" -> 0.25).
_ph_for_split['Split %1'] = (
    _ph_for_split['Split %']
    .astype(str)
    .str.strip()
    .str.replace('%', '', regex=False)
)
_ph_for_split['Split %1'] = pd.to_numeric(_ph_for_split['Split %1'], errors='coerce').fillna(0) / 100

Final_sale = pd.merge(
    FF_corrected_plan,
    _ph_for_split,
    left_on=['hub_name', 'sku class prod'],
    right_on=['hub_name', 'sku class prod'],
    how="left"
)

# Keep 'City' alias for backward-compatible downstream code
Final_sale['City'] = Final_sale['city_name']

# Enforce active hub×sku×day combinations from P-H Master.
# Only rows with day flag == 1 are allowed to carry plan.
_day_flag_candidates = {
    "Mon": ["Active_Flag_Mon", "active_flag_mon", "sale_open_1_flag_Mon", "sale_open_1_flag_mon"],
    "Tue": ["Active_Flag_Tue", "active_flag_tue", "sale_open_1_flag_Tue", "sale_open_1_flag_tue"],
    "Wed": ["Active_Flag_Wed", "active_flag_wed", "sale_open_1_flag_wed", "sale_open_1_flag_Wed"],
    "Thu": ["Active_Flag_Thu", "active_flag_thu", "sale_open_1_flag_Thu", "sale_open_1_flag_thu"],
    "Fri": ["Active_Flag_Fri", "active_flag_fri", "sale_open_1_flag_Fri", "sale_open_1_flag_fri"],
    "Sat": ["Active_Flag_Sat", "active_flag_sat", "sale_open_1_flag_Sat", "sale_open_1_flag_sat"],
    "Sun": ["Active_Flag_Sun", "active_flag_sun", "sale_open_1_flag_Sun", "sale_open_1_flag_sun"],
}
_norm_to_actual = {str(c).strip().lower(): c for c in Master_df.columns}
_selected_flag_cols = {}
for _day, _cands in _day_flag_candidates.items():
    for _cand in _cands:
        _actual = _norm_to_actual.get(_cand.lower())
        if _actual is not None:
            _selected_flag_cols[_day] = _actual
            break

if {'hub_name', 'sku class prod', 'day'}.issubset(Final_sale.columns) and _selected_flag_cols:
    _ph_active_df = Master_df[['hub_name', 'SKU Class Prod'] + list(_selected_flag_cols.values())].copy()
    _ph_active_df = _ph_active_df.rename(columns={'SKU Class Prod': 'sku class prod'})
    _ph_active_df = _ph_active_df.rename(columns={v: k for k, v in _selected_flag_cols.items()})
    _ph_active_long = _ph_active_df.melt(
        id_vars=['hub_name', 'sku class prod'],
        value_vars=list(_selected_flag_cols.keys()),
        var_name='day',
        value_name='active_flag_raw'
    )

    _raw = _ph_active_long['active_flag_raw'].astype(str).str.strip().str.upper()
    _ph_active_long['is_active_ph'] = np.where(
        _raw.isin(['1', '1.0', 'A', 'Y', 'YES', 'TRUE']),
        1,
        pd.to_numeric(_ph_active_long['active_flag_raw'], errors='coerce').fillna(0).gt(0).astype(int)
    )
    _ph_active_long = _ph_active_long[['hub_name', 'sku class prod', 'day', 'is_active_ph']].drop_duplicates(
        subset=['hub_name', 'sku class prod', 'day'], keep='first'
    )

    Final_sale = Final_sale.merge(_ph_active_long, on=['hub_name', 'sku class prod', 'day'], how='left')
    Final_sale['is_active_ph'] = pd.to_numeric(Final_sale['is_active_ph'], errors='coerce').fillna(0).astype(int)
else:
    Final_sale['is_active_ph'] = 1
    print("[Active Filter] Could not build strict P-H day flag map; defaulting is_active_ph=1.")

# Display summary statistics
Final_sale.describe(include="all")

# %% Cell 59
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

# Hard gate: inactive P-H combinations should not carry forward plans.
_inactive_rows = int((Final_sale['is_active_ph'] != 1).sum()) if 'is_active_ph' in Final_sale.columns else 0
print(f"[Active Filter] Inactive hub×sku×day rows blocked: {_inactive_rows:,}")
Final_sale.loc[Final_sale['is_active_ph'] != 1, ['sale_plan', 'base_plan']] = 0

# Print the totals
print(Final_sale['sale_plan'].sum())
print(Final_sale['base_plan'].sum())

# %% Cell 60
# start_date = '2025-07-21'
# end_date = '2025-07-27'

# filtered_df = Final_sale[
#     (Final_sale['date'] >= start_date) & (Final_sale['date'] <= end_date)
# ]

# %% Cell 61
# grouped_df = filtered_df.groupby(['city_name', 'Product id', 'day'], as_index=False)[ 'base_plan'].sum()



# %% Cell 62
# filtered_master = Master_df[
#     (Master_df["Channel"] == "Online") & 
#     (Master_df["Order Type - pan india"] == "E")
# ]


# %% Cell 63
# merged_df = DP_suggestion.merge(
#     filtered_master[["City", "SKU Class Prod", "Product id", "Split %"]],
#     on=["City",  "SKU Class Prod"],
#     how="left"
# )

# %% Cell 64
# merged_df.to_clipboard()

# %% Cell 65
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

# %% Cell 66
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





# %% Cell 67
# result_df["difference"] = abs(result_df["Base Plan after Split"] - result_df["Hub_base_plan"])

# %% Cell 68
# result_df.to_clipboard()

# %% Cell 69
# Pricing from P-H Master 'Price' column (hub_name + Product id key)
_ph_price = Master_df[['hub_name', 'Product id', 'Price']].copy()
_ph_price = _ph_price.drop_duplicates(subset=['hub_name', 'Product id'])
print(f"[Pricing] {len(_ph_price):,} hub×product price rows from P-H Master")

# %% Cell 70
# Map price to Final_sale using hub_name + Product id (vectorised merge — no per-row apply)
_price_lookup = _ph_price[['hub_name', 'Product id', 'Price']].drop_duplicates(
    subset=['hub_name', 'Product id']
)
Final_sale = Final_sale.merge(_price_lookup, on=['hub_name', 'Product id'], how='left')
Final_sale.rename(columns={'Price': 'Updated Price'}, inplace=True)

# Display summary statistics
Final_sale.describe(include='all')


# %% Cell 71
# City Map from DP Logics sheet
_cm_data = _dp_logics_ss.worksheet("City Map").get("A:B")
city_map = pd.DataFrame(_cm_data[1:], columns=_cm_data[0])
city_map.columns = [c.strip() for c in city_map.columns]

city_map = city_map.rename(columns={"Attribute": "hub_name"})



Final_sale = Final_sale.merge(city_map, on='hub_name', how='left')
Final_sale['Original_city'] = Final_sale['Original_city'].fillna(Final_sale['city_name'])

Final_sale.describe(include='all')

# %% Cell 72
# Ensure columns are numeric
Final_sale['sale_plan'] = pd.to_numeric(Final_sale['sale_plan'], errors='coerce')
Final_sale['base_plan'] = pd.to_numeric(Final_sale['base_plan'], errors='coerce')
# Final_sale['Updated Price'] = pd.to_numeric(Final_sale['Updated Price'], errors='coerce')
Final_sale['Updated Price'] = Final_sale['Updated Price'].astype(str).str.replace(",", "").astype(float).round(0).astype(int)
                               
Final_sale['Revenue_plan'] = Final_sale['sale_plan'] * Final_sale['Updated Price']
Final_sale['base_Revenue_plan'] = Final_sale['base_plan'] * Final_sale['Updated Price']

# Enforce uniqueness on hub×product×date before downstream usage.
_plan_key = ['hub_name', 'Product id', 'date']
_dup_plan = Final_sale.duplicated(subset=_plan_key, keep='first').sum()
if _dup_plan:
    print(f"[Dedup] Dropping {_dup_plan:,} duplicate rows in Final_sale on {_plan_key}.")
    Final_sale = Final_sale.drop_duplicates(subset=_plan_key, keep='first').reset_index(drop=True)

Final_sale.to_csv("plan.csv",index=False)
# Group by city and date, summing Revenue_plan
gr = Final_sale.groupby(['Original_city', 'date','day'], as_index=False)[['Revenue_plan', 'base_Revenue_plan']].sum()
print(gr)


# %% Cell 73
pass  # clipboard removed

# %% Cell 74
pass  # debug csv removed

# %% Cell 75
# City × Product adhoc (H:K columns) from local Excel synced from DP Logics
City_adhoc = pd.read_excel(os.path.join(_INPUTS_DIR, "Adhoc_Adjustment_City_Product.xlsx"))
City_adhoc.columns = [c.strip() for c in City_adhoc.columns]
print(f"[City Adhoc] {len(City_adhoc):,} rows loaded")
print(City_adhoc.describe(include='all'))

# %% Cell 76
# Ensure date format matches
City_adhoc["date"] = pd.to_datetime(City_adhoc["date"]).dt.strftime("%Y-%m-%d")

# Merge on 'date', 'Cut class', and 'city_name'
Final_sale = Final_sale.merge(City_adhoc[["date", "Product id", "city_name","%Change3"]], on=["date", "Product id", "city_name"], how="left")

Final_sale.to_csv("check.csv")

Final_sale["%Change3"] = pd.to_numeric(Final_sale["%Change3"], errors="coerce")

Final_sale["%Change3"] = Final_sale["%Change3"].fillna(0)

# Calculate final plan
Final_sale["sale_plan"] = Final_sale["sale_plan"] + (Final_sale["sale_plan"] * Final_sale["%Change3"]) 


# Round to avoid decimal values
Final_sale["sale_plan"] = Final_sale["sale_plan"].round(0).astype(int)


# %% Cell 77
print(Final_sale['sale_plan'].sum())
Final_sale.describe(include='all')

# %% Cell 78
day_to_sale_buffer_column = {
    'sale_open_1_flag_Mon': 'Mon', 'sale_open_1_flag_Tue': 'Tue', 'sale_open_1_flag_wed': 'Wed',
    'sale_open_1_flag_Thu': 'Thu', 'sale_open_1_flag_Fri': 'Fri', 'sale_open_1_flag_Sat': 'Sat', 'sale_open_1_flag_Sun': 'Sun'
}

sale_open_buffer_df = Master_df.rename(columns=day_to_sale_buffer_column)

sale_open_buffer_long = sale_open_buffer_df.melt(
    id_vars=['hub_name', 'Product id', 'Channel'],
    value_vars=list(day_to_sale_buffer_column.values()),
    var_name='day',
    value_name='sale_Buffer_flag'
).loc[lambda df: df['Channel'] == 'Online']

# %% Cell 79
Final_sale = Final_sale.merge(
    sale_open_buffer_long[['hub_name', 'Product id', 'day', 'sale_Buffer_flag']],
    on=['hub_name', 'Product id', 'day'], how='left'
)

# %% Cell 80
# Ensure numeric types before threshold comparisons.
Final_sale['sale_Buffer_flag'] = pd.to_numeric(Final_sale['sale_Buffer_flag'], errors='coerce').fillna(0)
Final_sale['sale_plan'] = pd.to_numeric(Final_sale['sale_plan'], errors='coerce').fillna(0)
Final_sale['base_plan'] = pd.to_numeric(Final_sale['base_plan'], errors='coerce').fillna(0)

#Identify groups with sale_plan > 0  (transform('max') > 0 is equivalent and ~10x faster)
valid_groups = Final_sale.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform('max') > 0

# Apply the condition and update sale_plan
Final_sale.loc[
    (Final_sale['sale_Buffer_flag'] > 0) & 
    (Final_sale['sale_plan'] < Final_sale['sale_Buffer_flag']) &
(valid_groups),
   'sale_plan'
] = Final_sale['sale_Buffer_flag']

# Sum the updated sale_plan column
Final_sale["sale_plan"].sum()

# %% Cell 81
valid_groups = Final_sale.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform('max') > 0

# Apply the condition and update sale_plan
Final_sale.loc[
    (Final_sale['sale_Buffer_flag'] > 0) & 
    (Final_sale['base_plan'] < Final_sale['sale_Buffer_flag']) & 
    (valid_groups), 
    'base_plan'
] = Final_sale['sale_Buffer_flag']

# Sum the updated sale_plan column
Final_sale["base_plan"].sum()

# %% Cell 82
# # Select the specific sheet/tab by its name
# worksheet = spreadsheet.worksheet("Hub Sku plan override")

# # Get all values from A to L (1st to 12th column)
# data = worksheet.get("A:I")  # Fetch only columns A to L

# # Convert to DataFrame
# Hub_Sku_plan_override = pd.DataFrame(data[1:], columns=data[0])  # First row as header

# # Display DataFrame
# Hub_Sku_plan_override.describe()

# Hub_Sku_plan_override = Hub_Sku_plan_override.rename(columns={"Attribute": "hub_name"})


# %% Cell 83
# # Step 1: Handle discontinued items — set sale_plan = 0 for all dates in Final_sale
# discontinued = Hub_Sku_plan_override[Hub_Sku_plan_override['Discontinue Flag'] == '1'][
#     ['Product id', 'hub_name']
# ]

# %% Cell 84

# # Step 1: Mark discontinued products — set both sale_plan and base_plan to 0
# Final_sale = Final_sale.merge(discontinued, on=['Product id', 'hub_name'], how='left', indicator=True)
# Final_sale.loc[Final_sale['_merge'] == 'both', ['sale_plan', 'base_plan']] = 0
# Final_sale.drop(columns=['_merge'], inplace=True)



# %% Cell 85
# #Step 2: Apply overrides where Discontinue Flag is 0
# # Rename override columns for clarity
# override_active = Hub_Sku_plan_override[Hub_Sku_plan_override['Discontinue Flag'] == '0'][
#     ['Product id', 'hub_name', 'date', 'sale_plan']
# ].rename(columns={
#     'sale_plan': 'override_sale_plan'
# })




# %% Cell 86
# # Merge overrides with Final_sale
# Final_sale = Final_sale.merge(override_active, on=['Product id', 'hub_name', 'date'], how='left')

# # Use override values where available
# Final_sale['sale_plan'] = Final_sale['override_sale_plan'].combine_first(Final_sale['sale_plan'])


# %% Cell 87
# Final_sale['base_plan'] = Final_sale['override_sale_plan'].combine_first(Final_sale['base_plan'])


# # Cleanup temporary columns
# Final_sale.drop(columns=['override_sale_plan'], inplace=True)

# %% Cell 88
# City × Category adhoc (A:D columns) from local Excel synced from DP Logics
Adhoc_factor = pd.read_excel(os.path.join(_INPUTS_DIR, "Adhoc_Adjustment.xlsx"))
Adhoc_factor.columns = [c.strip() for c in Adhoc_factor.columns]
print(f"[Adhoc City-Cat] {len(Adhoc_factor):,} rows loaded")
Adhoc_factor.describe()

Final_sale = Final_sale.rename(columns={"Sub-category": "sub category"})




# %% Cell 89
# Convert dates
Adhoc_factor["date"] = pd.to_datetime(Adhoc_factor["date"]).dt.strftime("%Y-%m-%d")
Final_sale["date"] = pd.to_datetime(Final_sale["date"]).dt.strftime("%Y-%m-%d")

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




# %% Cell 90
Final_sale["sale_plan"] = Final_sale["sale_plan"].fillna(0).round(0).astype(int)

# # Optional: Drop helper columns if needed
# Final_sale.drop(columns=["spiked_plan_unrounded", "spiked_plan_scaled", "group_sum", "target_total"], inplace=True)

# Output
print("Final total sale_plan:", Final_sale["sale_plan"].sum())
Final_sale.to_csv("check_scaled_rounding.csv", index=False)

# %% Cell 91
print(Final_sale.head())

# %% Cell 92
# Hub-level adhoc from local Excel synced from DP Logics
Hub_adhoc = pd.read_excel(os.path.join(_INPUTS_DIR, "Adhoc_Adjustment_Hub.xlsx"))
Hub_adhoc.columns = [c.strip() for c in Hub_adhoc.columns]
print(f"[Hub Adhoc] {len(Hub_adhoc):,} rows loaded")
print(Hub_adhoc.describe(include='all'))

# %% Cell 93
# Ensure date format matches
Hub_adhoc["date"] = pd.to_datetime(Hub_adhoc["date"]).dt.strftime("%Y-%m-%d")
#City_adhoc["date"] = pd.to_datetime(City_adhoc["date"]).dt.strftime("%Y-%m-%d")
# Merge on 'date', 'Cut class', and 'city_name'
Final_sale = Final_sale.merge(Hub_adhoc[["date", "Product id", "hub_name","% Change1"]], on=["date", "Product id", "hub_name"], how="left")
#Final_sale = Final_sale.merge(City_adhoc[["date", "Product id", "city_name","% Change2"]], on=["date", "Product id", "city_name"], how="left")
Final_sale.to_csv("check.csv")

Final_sale["% Change1"] = pd.to_numeric(Final_sale["% Change1"], errors="coerce")
#Final_sale["% Change2"] = pd.to_numeric(Final_sale["% Change2"], errors="coerce")
# Fill missing deviations with 0 (if no festive factor exists for that city + cut class + date)
Final_sale["% Change1"] = Final_sale["% Change1"].fillna(0)
#Final_sale["% Change2"] = Final_sale["% Change2"].fillna(0)
# Calculate final plan
Final_sale["unrounded_sale_plan"] = Final_sale["sale_plan"] + (Final_sale["sale_plan"] * Final_sale["% Change1"]) 


# %% Cell 94
print(Final_sale.columns)

# %% Cell 95

# Step 2: Initial rounding (nearest integer)
Final_sale["sale_plan"] = np.round(Final_sale["unrounded_sale_plan"]).astype(int)

# Step 3: Decimal remainders for reconciliation
Final_sale["remainder"] = Final_sale["unrounded_sale_plan"] - Final_sale["sale_plan"]


# Step 4: Reconciliation loop city by city
for city, group in Final_sale.groupby(["city_name", "sub category", "date"]):
    target = round(group["unrounded_sale_plan"].sum())   # exact city-level festive target
    current = group["sale_plan"].sum()             # what we have after rounding
    diff = int(target - current)

    if diff > 0:
        # Add +1 to hubs with largest remainders
        idx = group["remainder"].nlargest(diff).index
        Final_sale.loc[idx, "sale_plan"] += 1

    elif diff < 0:
        # Subtract -1 from hubs with smallest remainders
        idx = group["remainder"].nsmallest(abs(diff)).index
        Final_sale.loc[idx, "sale_plan"] -= 1

# Re-apply strict active gate after all downstream adjustments.
if 'is_active_ph' in Final_sale.columns:
    Final_sale.loc[Final_sale['is_active_ph'] != 1, ['sale_plan', 'base_plan']] = 0

# Map sub category from P Master (Excel) — source of truth by Product id (before revenue / gr2 / plan.csv)
_pm_sub = _excel_tab_to_df(_MASTERS_XLSX, "P Master", usecols="A:K")
_pm_sub.columns = [str(c).strip() for c in _pm_sub.columns]
_pm_id = next((c for c in _pm_sub.columns if c.strip().lower() in ("product id", "product_id")), None)
_pm_sc = next((c for c in _pm_sub.columns if "sub" in c.lower() and "cat" in c.lower()), None)
if _pm_id and _pm_sc:
    mapping_df = (
        _pm_sub[[_pm_id, _pm_sc]]
        .dropna(subset=[_pm_id])
        .drop_duplicates(subset=[_pm_id])
        .rename(columns={_pm_id: "Product id", _pm_sc: "Sub-category"})
    )
    prod_to_subcat = dict(
        zip(
            mapping_df["Product id"].astype(str).str.strip(),
            mapping_df["Sub-category"],
        )
    )
    if "sub category" not in Final_sale.columns:
        Final_sale["sub category"] = ""
    Final_sale["sub category"] = (
        Final_sale["Product id"].astype(str).str.strip().map(prod_to_subcat).combine_first(Final_sale["sub category"])
    )
    print(f"[P Master] sub category remapped from P Master for {len(prod_to_subcat):,} product ids")
else:
    print(f"[P Master] WARNING: could not map sub category (Product id col={_pm_id}, Sub-category col={_pm_sc})")

# %% Cell 96
Final_sale['Revenue_plan'] = Final_sale['sale_plan'] * Final_sale['Updated Price']
Final_sale['base_Revenue_plan'] = Final_sale['base_plan'] * Final_sale['Updated Price']
Final_sale.to_csv("plan.csv",index=False)


# Group by city and date, summing Revenue_plan
gr2 = Final_sale.groupby(['Original_city', 'sub category', 'date','day'], as_index=False)[['Revenue_plan', 'base_Revenue_plan']].sum()
print(gr2)

# %% Cell 97
# EA vs FF – use dynamic dates from CLI args
gr2["date"] = pd.to_datetime(gr2["date"], format="%Y-%m-%d", dayfirst=True)
filtered_gr2 = gr2[(gr2['date'] >= FCST_START) & (gr2['date'] <= FCST_END)]
print(f"[EA vs FF] Writing {len(filtered_gr2):,} rows to Data_Dump3 ({FCST_START.date()} – {FCST_END.date()})")
Expected_Actuals_Tracker_spreadsheet = client.open_by_url(EA_TRACKER_SHEET_URL)
worksheet = Expected_Actuals_Tracker_spreadsheet.worksheet("Data_Dump3")
set_with_dataframe(worksheet, filtered_gr2)
print("✅ EA vs FF updated in UI (Data_Dump3).")
print(filtered_gr2[['Revenue_plan', 'base_Revenue_plan']].sum())

# %% Cell 98
pass  # clipboard removed

# %% Cell 99
# start_date = datetime(2026, 1, 26)
# end_date = datetime(2026, 2, 1)
# gr2["date"] = pd.to_datetime(gr2["date"], format="%Y-%m-%d", dayfirst=True)
# filtered_gr2 = gr2[(gr2['date'] >= start_date) & (gr2['date'] <= end_date)]
# Expected_Actuals_Tracker_spreadsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1QelNGlelD5SNJsctbULAGycU2fL2dcQtRM6MPSs1kPw/edit?gid=520551462#gid=520551462")
# worksheet = Expected_Actuals_Tracker_spreadsheet.worksheet("Data_Dump3")
# set_with_dataframe(worksheet, filtered_gr2)
# print(filtered_gr2[['Revenue_plan', 'base_Revenue_plan','sale_plan','base_plan']].sum())

# %% Cell 100
pass  # clipboard removed

# %% Cell 101
_ui_step("Running cluster transfer and buffer calculations")

# ── Duplicate diagnostic helper (hub/product/date level) ─────────────────────
def _dup_check(df, label, hub_col="Attribute"):
    key = [hub_col, "Product id", "date"]
    existing = [c for c in key if c in df.columns]
    if len(existing) < len(key):
        missing = [c for c in key if c not in df.columns]
        print(f"  [DUP-CHECK] {label}: skipped — missing columns {missing}")
        return
    n_dup = df.duplicated(subset=key, keep=False).sum()
    n_combo = df[key].drop_duplicates().shape[0]
    flag = "  *** DUPLICATES FOUND ***" if n_dup > 0 else "  OK"
    print(f"  [DUP-CHECK] {label}: {len(df):,} rows | {n_combo:,} unique combos | {n_dup:,} dup rows{flag}")

Final_sale = Final_sale.rename(columns={"hub_name": "Attribute"})
# Keep hub_name alias for downstream merges that still join on hub_name.
if "hub_name" not in Final_sale.columns and "Attribute" in Final_sale.columns:
    Final_sale["hub_name"] = Final_sale["Attribute"]

_dup_check(Final_sale, "STEP-0  Final_sale (before any merge)")

# %% Cell 102
# Cluster phase 2 from local Excel synced from Inventory Logics
cluster_mapping_df2 = pd.read_excel(os.path.join(_INV_DIR, "Cluster phase 2.xlsx"))
cluster_mapping_df2.columns = [c.strip() for c in cluster_mapping_df2.columns]
print(f"[Cluster phase 2] {len(cluster_mapping_df2):,} rows")

# %% Cell 103

cluster_mapping_df2 = cluster_mapping_df2[cluster_mapping_df2["Cluster_Flag"] == 1]
cluster_mapping_df2 = cluster_mapping_df2.rename(columns={'product_id': 'Product id', 'childHub_name': 'Attribute', 'MotherHub_name': 'Mother_hub'})
cluster_mapping_df2 = cluster_mapping_df2[['Attribute', 'Product id', 'Mother_hub']]
Final_sale = Final_sale.merge(cluster_mapping_df2, how='left', on=['Attribute', 'Product id'])
_dup_check(Final_sale, "STEP-1  after merge cluster_mapping_df2 (Cluster phase 2)")
Final_sale.describe(include='all')

# %% Cell 104
saleplan_transfer = Final_sale.groupby(['Product id', 'date', 'Mother_hub'])['sale_plan'].sum().reset_index()
Final_sale =  Final_sale.merge(
    saleplan_transfer,
    how='left', 
    left_on=['Product id', 'date', 'Attribute'], 
    right_on=['Product id', 'date', 'Mother_hub'],
    suffixes=('', '_transferred')
)
_dup_check(Final_sale, "STEP-2  after merge saleplan_transfer")

# %% Cell 105
Final_sale['sale_plan'] =Final_sale['sale_plan'] +Final_sale['sale_plan_transferred'].fillna(0)
Final_sale.loc[Final_sale['Mother_hub'].notna(), 'sale_plan'] = 0

# %% Cell 106
day_to_buffer_column = {
    'Buffer_Mon': 'Mon', 'Buffer_Tue': 'Tue', 'Buffer_Wed': 'Wed', 
    'Buffer_Thu': 'Thu', 'Buffer_Fri': 'Fri', 'Buffer_Sat': 'Sat', 'Buffer_Sun': 'Sun'
}

percentage_buffer_df = Master_df.rename(columns=day_to_buffer_column)
#%%
print(percentage_buffer_df.head())

percentage_buffer_long = percentage_buffer_df.melt(
    id_vars=['hub_name', 'Product id', 'Channel'],
    value_vars=list(day_to_buffer_column.values()),
    var_name='day',
    value_name='Buffer_Percentage'
).loc[lambda df: df['Channel'] == 'Online']

# %% Cell 107
Final_sale = Final_sale.merge(
    percentage_buffer_long[['hub_name', 'Product id', 'day', 'Buffer_Percentage']],
    on=['hub_name', 'Product id', 'day'], how='left'
)
_dup_check(Final_sale, "STEP-3  after merge percentage_buffer_long")

# %% Cell 108
Final_sale['Buffer_Percentage'] = Final_sale['Buffer_Percentage'].astype(str).str.replace('%', '', regex=False).str.strip()

# %% Cell 109
Final_sale['Buffer_Percentage'] = pd.to_numeric(Final_sale['Buffer_Percentage'], errors='coerce')

# %% Cell 110
# Inv_buffer from local Excel synced from Inventory Logics
inv_buffer = pd.read_excel(os.path.join(_INV_DIR, "Inv_buffer.xlsx"))
inv_buffer.columns = [c.strip() for c in inv_buffer.columns]
print(f"[Inv Buffer] {len(inv_buffer):,} rows")
inv_buffer.describe()

# %% Cell 111
# Split 'volume bucket' into 'min_volume' and 'max_volume'
inv_buffer[['min_volume', 'max_volume']] = inv_buffer['volume bucket'].str.split('-', expand=True).astype(float)


# Create a mask for rows where the flag is 0
mask = Final_sale['DOC/Percentage_BufferFlag'] == 0
Final_sale_flag0 = Final_sale[mask].copy()

# Define a function to look up the appropriate inv_buffer% based on sale_plan and day
# ── Vectorised buffer percentage lookup (replaces row-by-row apply) ──────────
# Step 1: join flagged rows with inv_buffer on day + city_name
_buf_merged = Final_sale_flag0.reset_index().merge(
    inv_buffer[['day', 'city_name', 'min_volume', 'max_volume', 'Buffer %']],
    on=['day', 'city_name'],
    how='left'
)
# Step 2: keep only rows where sale_plan falls inside the volume bucket
_buf_in_range = _buf_merged[
    (_buf_merged['sale_plan'] >= _buf_merged['min_volume']) &
    (_buf_merged['sale_plan'] <= _buf_merged['max_volume'])
]
# Step 3: first matching bucket per original row
_buf_first = _buf_in_range.drop_duplicates(subset='index').set_index('index')['Buffer %']
# Step 4: apply — use looked-up value where match exists, keep original as fallback
Final_sale_flag0['Buffer_Percentage'] = Final_sale_flag0['Buffer_Percentage'].where(
    ~Final_sale_flag0.index.isin(_buf_first.index),
    other=_buf_first.reindex(Final_sale_flag0.index)
)
Final_sale.loc[mask, 'Buffer_Percentage'] = Final_sale_flag0['Buffer_Percentage']


# %% Cell 112
Final_sale['Buffer_Percentage'] = Final_sale['Buffer_Percentage'].astype(str).str.replace('%', '', regex=False).str.strip()

# %% Cell 113
Final_sale['Buffer_Percentage'] = pd.to_numeric(Final_sale['Buffer_Percentage'], errors='coerce')

# %% Cell 114
# cluster_mapping from local Excel synced from Inventory Logics
mother_hub_mapping = pd.read_excel(os.path.join(_INV_DIR, "cluster_mapping.xlsx"))
mother_hub_mapping.columns = [c.strip() for c in mother_hub_mapping.columns]
print(f"[Cluster Mapping] {len(mother_hub_mapping):,} rows")

# %% Cell 115
unique_source_hubs = mother_hub_mapping[['sourceHub_name']].drop_duplicates().reset_index(drop=True)

# %% Cell 116
# Hub(Inv_Buffer) from local Excel synced from Inventory Logics
Hub_level_inv_buffer = pd.read_excel(os.path.join(_INV_DIR, "Hub(Inv_Buffer).xlsx"))
Hub_level_inv_buffer.columns = [c.strip() for c in Hub_level_inv_buffer.columns]
print(f"[Hub Inv Buffer] {len(Hub_level_inv_buffer):,} rows")


# %% Cell 117
# Merge to bring the Inv_Buffer into Final_sale where keys match
Final_sale = Final_sale.merge(
    Hub_level_inv_buffer[["Attribute", "Product id", "Inv_Buffer"]],
    on=["Attribute", "Product id"],
    how="left"
)
_dup_check(Final_sale, "STEP-4  after merge Hub_level_inv_buffer")

# Overwrite Buffer_Percentage wherever Inv_Buffer is available
Final_sale["Buffer_Percentage"] = Final_sale["Inv_Buffer"].combine_first(Final_sale["Buffer_Percentage"])




# %% Cell 118
# (Optional) Drop Inv_Buffer column if no longer needed
Final_sale.drop(columns=["Inv_Buffer"], inplace=True)

# %% Cell 119
Final_sale['Buffer_Percentage'] = pd.to_numeric(Final_sale['Buffer_Percentage'], errors='coerce')

# %% Cell 120
mask = Final_sale['Attribute'].isin(
    unique_source_hubs['sourceHub_name']
)

Final_sale.loc[mask, 'Buffer_Percentage'] = np.where(
    Final_sale.loc[mask, 'Buffer_Percentage'] < 100,
    Final_sale.loc[mask, 'Buffer_Percentage'] + 5,
    Final_sale.loc[mask, 'Buffer_Percentage'] + 100
)



# %% Cell 121
Final_sale['Uncapped Buffer'] = np.where(
    Final_sale['DOC/Percentage_BufferFlag'] == 0,  
    np.round(Final_sale['sale_plan'] *(1+ (Final_sale['Buffer_Percentage'] / 100))),  
    0  # If Buffer_Percentage is 100 or more, set Uncapped Buffer to 0
)

# %% Cell 122
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
    id_vars=['hub_name', 'Product id', 'Channel'],
    value_vars=list(day_to_buffer_column.values()),
    var_name='day',
    value_name='Max_Capped_Buffer'
).loc[lambda df: df['Channel'] == 'Online']

Final_sale = Final_sale.merge(
    buffer_capping_long[['hub_name', 'Product id', 'day', 'Max_Capped_Buffer']],
    on=['hub_name', 'Product id', 'day'], how='left'
)
_dup_check(Final_sale, "STEP-5  after merge buffer_capping_long (Max_Capped_Buffer)")

Final_sale['Max_Capped_Buffer'] = Final_sale['Max_Capped_Buffer'].astype(str).str.replace('%', '', regex=False).str.strip()
Final_sale['Max_Capped_Buffer'] = pd.to_numeric(Final_sale['Max_Capped_Buffer'], errors='coerce')




# %% Cell 123
Final_sale['Max_Capped_Buffer'] = pd.to_numeric(Final_sale['Max_Capped_Buffer'], errors='coerce')

unique_source_hubs_list = unique_source_hubs['sourceHub_name'].unique()


Final_sale.loc[
    Final_sale['Attribute'].isin(unique_source_hubs_list),
    'Max_Capped_Buffer'
] = 100

Final_sale['Capped_Buffer'] = np.where(
    Final_sale['DOC/Percentage_BufferFlag'] == 0,  
    np.round(Final_sale['sale_plan'] + (Final_sale['Next_Day_Plan'] *(Final_sale['Max_Capped_Buffer'] / 100))),  
    0  # If Buffer_Percentage is 100 or more, set Uncapped Buffer to 0
)
Final_sale.describe(include='all')

# %% Cell 124
pass  # clipboard removed

# %% Cell 125
df_excess = Final_sale[(Final_sale['Buffer_Percentage'] > 100)][['Product id', 'Attribute', 'date','sale_plan', 'Buffer_Percentage']].copy()
df_excess['Days_Allocation'] = (df_excess['Buffer_Percentage'] / 100)
df_excess = df_excess.sort_values(['Product id', 'Attribute', 'date'])

# %% Cell 126
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

    group['Allocated_Buffer'] = np.round(allocated_buffer).astype(int)
    return group

# %% Cell 127
df_excess = df_excess.groupby(['Attribute', 'Product id'], group_keys=False).apply(rolling_sum_dynamic)

# %% Cell 128
df_excess.describe(include='all')

# %% Cell 129
_ui_step("Building Final_plan and applying inventory rules")
Final_plan = Final_sale.merge(
    df_excess[['Attribute', 'Product id', 'date', 'Allocated_Buffer']],
    how='left',
    on=['Attribute', 'Product id', 'date']
)
_dup_check(Final_plan, "STEP-6  after merge df_excess (Allocated_Buffer)")

# %% Cell 130
Final_plan['Final_Inv_Plan'] = Final_plan['sale_plan']
Final_plan['Final_Inv_Plan'] = Final_plan['Allocated_Buffer'].combine_first(Final_plan['Final_Inv_Plan'])
Final_plan.drop(columns=['Allocated_Buffer'], inplace=True) 

# %% Cell 131
Final_plan['Final_Inv_Plan'] = np.where(
    (Final_plan['Uncapped Buffer'] > 0) & (Final_plan['Capped_Buffer'] > 0),
    np.minimum(Final_plan['Uncapped Buffer'], Final_plan['Capped_Buffer']),
    Final_plan['Final_Inv_Plan']  # Keep the non-zero buffer
)

# %% Cell 132
# Deduplicate Hub_Master on merge keys to prevent fan-out duplicates
_hub_master_htt = (
    Hub_Master[['hub_name', 'sku class prod', 'HTT']]
    .drop_duplicates(subset=['hub_name', 'sku class prod'])
)
Final_plan = Final_plan.merge(
    _hub_master_htt,
    left_on=['Attribute', 'sku class prod'],
    right_on=['hub_name', 'sku class prod'],
    how='left'
)
_dup_check(Final_plan, "STEP-7  after merge Hub_Master (HTT)")

# Normalise hub column names after merge (pandas may create hub_name_x / hub_name_y).
if "hub_name" not in Final_plan.columns:
    if "hub_name_x" in Final_plan.columns and "hub_name_y" in Final_plan.columns:
        Final_plan["hub_name"] = Final_plan["hub_name_x"].combine_first(Final_plan["hub_name_y"])
    elif "hub_name_x" in Final_plan.columns:
        Final_plan["hub_name"] = Final_plan["hub_name_x"]
    elif "hub_name_y" in Final_plan.columns:
        Final_plan["hub_name"] = Final_plan["hub_name_y"]
    elif "Attribute" in Final_plan.columns:
        Final_plan["hub_name"] = Final_plan["Attribute"]
Final_plan.drop(columns=["hub_name_x", "hub_name_y"], inplace=True, errors="ignore")


# %% Cell 133
mask = Final_plan['DOC/Percentage_BufferFlag'] == 0
_fp  = Final_plan.loc[mask]

_sp         = _fp['sale_plan']
_fip        = _fp['Final_Inv_Plan']
_htt        = _fp['HTT']
_attr       = _fp['Attribute']
_city       = _fp['city_name']
_sp_pos_lt4 = (_sp > 0) & (_sp < 4)
_special    = _attr.isin(["KOM", "TUB", "Indiranagar"])
_blr        = _city == "Bangalore"

Final_plan.loc[mask, 'Final_Inv_Plan'] = np.select(
    [
        (_htt == "head")   & _sp_pos_lt4,           # P1 – HTT head
        _special           & _sp_pos_lt4,           # P2 – special hubs
        _blr & (_sp > 0)   & (_sp < 2),             # P3a – Bangalore low
        _blr & (_sp > 1)   & (_sp < 4),             # P3b – Bangalore mid
        _blr,                                        # P3c – Bangalore other
        _sp_pos_lt4,                                 # P4  – other cities
    ],
    [
        _sp + 1,   # P1
        _sp + 1,   # P2
        _sp,       # P3a
        _sp + 1,   # P3b
        _fip,      # P3c
        _sp,       # P4
    ],
    default=_fip
)

print(Final_plan['Final_Inv_Plan'].sum())
Final_plan.describe(include='all')





# %% Cell 134
day_to_inv_buffer_column = {
    'Inv_open_1_flag_Mon': 'Mon', 'Inv_open_1_flag_Tue': 'Tue', 'Inv_open_1_flag_wed': 'Wed',
    'Inv_open_1_flag_Thu': 'Thu', 'Inv_open_1_flag_Fri': 'Fri', 'Inv_open_1_flag_Sat': 'Sat', 'Inv_open_1_flag_Sun': 'Sun'
}

Inv_open_buffer_df = Master_df.rename(columns=day_to_inv_buffer_column)

inv_open_buffer_long = Inv_open_buffer_df.melt(
    id_vars=['hub_name', 'Product id', 'Channel'],
    value_vars=list(day_to_inv_buffer_column.values()),
    var_name='day',
    value_name='Buffer_flag'
).loc[lambda df: df['Channel'] == 'Online']

# %% Cell 135
# Defensive fallback: ensure hub_name exists for downstream hub-level merges.
if "hub_name" not in Final_plan.columns and "Attribute" in Final_plan.columns:
    Final_plan["hub_name"] = Final_plan["Attribute"]

Final_plan = Final_plan.merge(
    inv_open_buffer_long[['hub_name', 'Product id', 'day', 'Buffer_flag']],
    on=['hub_name', 'Product id', 'day'], how='left'
)
_dup_check(Final_plan, "STEP-8  after merge inv_open_buffer_long (Buffer_flag)")

# %% Cell 136
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


# %% Cell 137
# valid_groups = Final_plan.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform('max') > 0

# # Apply the condition and update sale_plan
# Final_sale.loc[
#     (Final_sale['sale_Buffer_flag'] > 0) & 
#     (Final_sale['base_plan'] < Final_sale['sale_Buffer_flag']) & 
#     (valid_groups), 
#     'base_plan'
# ] = Final_sale['sale_Buffer_flag']

# # Sum the updated sale_plan column
# Final_sale["base_plan"].sum()

# %% Cell 138
valid_groups = Final_plan.groupby(['city_name', 'Product id', 'day'])['sale_plan'].transform('max') > 0



Final_plan.loc[
    (Final_plan['Buffer_flag'] == 1) & 
    (valid_groups) &
    (Final_plan['sale_plan'] == 0) & 
    (Final_plan['Final_Inv_Plan'] == 0), 
    'Final_Inv_Plan'
] = 1 * Final_plan["Split %1"].round(0).astype(int)
print(Final_plan['Final_Inv_Plan'].sum())

# %% Cell 139
# No_Buffer(Inv_Plan) from local Excel synced from Inventory Logics
No_buffer = pd.read_excel(os.path.join(_INV_DIR, "No_Buffer(Inv_Plan).xlsx"))
No_buffer.columns = [c.strip() for c in No_buffer.columns]
print(f"[No Buffer] {len(No_buffer):,} rows")
No_buffer.describe()

# %% Cell 140
# Correct way to access multiple columns
no_buffer_set = set([tuple(x) for x in No_buffer[['city_name', 'Pr_id']].values])

# Vectorised membership test — pd.MultiIndex is much faster than apply(tuple)
mask = pd.MultiIndex.from_arrays(
    [Final_plan['city_name'], Final_plan['Product id']]
).isin(no_buffer_set)
Final_plan.loc[mask, 'Final_Inv_Plan'] = Final_plan['sale_plan']

# %% Cell 141
Final_plan.loc[(Final_plan['sub category'] == 'Masalas') & (Final_plan['Final_Inv_Plan'] < 3), 'Final_Inv_Plan'] = 3

# %% Cell 142
Final_plan.to_csv('final_forecast.csv')

# %% Cell 143
# cluster_mapping from local Excel (same file as Cell 114)
cluster_mapping_df = pd.read_excel(os.path.join(_INV_DIR, "cluster_mapping.xlsx"))
cluster_mapping_df.columns = [c.strip() for c in cluster_mapping_df.columns]
cluster_mapping_df = cluster_mapping_df.rename(columns={'product_id': 'Product id', 'destinationHub_name': 'Attribute', 'sourceHub_name': 'source_hub'})
cluster_mapping_df = cluster_mapping_df[['Attribute', 'Product id', 'source_hub', 'CH Decrease%', 'MH Increase%']]
cluster_mapping_df['CH Decrease%'] = cluster_mapping_df['CH Decrease%'].fillna(0).apply(parse_festive_factor)
cluster_mapping_df['MH Increase%'] = cluster_mapping_df['MH Increase%'].fillna(0).apply(parse_festive_factor)


# %% Cell 144
cluster_mapping_df.drop_duplicates()


# %% Cell 145
merged_dataframe = Final_plan.merge(cluster_mapping_df, how='left', on=['Attribute', 'Product id'])

# city_name_x/_y collision from merge — keep the left (_x) value as city_name
merged_dataframe.rename(columns={'city_name_x': 'city_name'}, inplace=True)
merged_dataframe.drop(columns=['city_name_y'], inplace=True, errors='ignore')
_dup_check(merged_dataframe, "STEP-9  after merge cluster_mapping_df (CH/MH%)")
merged_dataframe.describe(include='all')


# %% Cell 146
# Raw buffer per child hub row
merged_dataframe['inv_buffer'] = merged_dataframe['Final_Inv_Plan'] - merged_dataframe['sale_plan']

# Amount arriving at mother hub = child buffer * MH Increase%
merged_dataframe['mh_transfer'] = merged_dataframe['inv_buffer'] * merged_dataframe['MH Increase%']

# Note: CH Decrease% = fraction child gives away, MH Increase% = fraction that arrives at mother

# Aggregate mh_transfer to mother hub level (per product, date, source_hub)
inventory_transfer = merged_dataframe[
    ~((merged_dataframe['sale_plan'] == 0) & (merged_dataframe['Final_Inv_Plan'] == 1))
].groupby(['Product id', 'date', 'source_hub'])['mh_transfer'].sum().reset_index()


# %% Cell 147
merged_dataframe = merged_dataframe.merge(
    inventory_transfer,
    how='left',
    left_on=['Product id', 'date', 'Attribute'],
    right_on=['Product id', 'date', 'source_hub'],
    suffixes=('', '_transferred')
)
_dup_check(merged_dataframe, "STEP-10 after merge inventory_transfer (mh_transfer)")

# %% Cell 148
# Mother hub: add aggregated (child inv_buffer * MH Increase%) from all child hubs, ceiling rounded
merged_dataframe['Final_Inv_Plan'] += np.ceil(merged_dataframe['mh_transfer_transferred'].fillna(0))


# %% Cell 149
# Child hub: retains (1 - CH Decrease%) of its buffer -> Final_Inv_Plan = sale_plan + inv_buffer * (1 - CH Decrease%)
merged_dataframe.loc[
    (merged_dataframe['source_hub'].notna()) &
    ~((merged_dataframe['sale_plan'] == 0) & (merged_dataframe['Final_Inv_Plan'] == 1)),
    'Final_Inv_Plan'
] = (
    merged_dataframe['sale_plan'] +
    merged_dataframe['inv_buffer'] * (1 - merged_dataframe['CH Decrease%'])
)

# %% Cell 150
print(merged_dataframe.columns)

# %% Cell 151
merged_dataframe.loc[merged_dataframe['Mother_hub'].notna(), 'Final_Inv_Plan'] = 0

# %% Cell 152
# discontinued = discontinued.rename(columns={"hub_name": "Attribute"})

# %% Cell 153
# # Step 2: Merge to identify discontinued entries
# merged_dataframe = merged_dataframe.merge(discontinued, on=['Product id', 'Attribute'], how='left', indicator=True)

# # Step 3: Set Final_Inv_Plan = 0 where discontinued
# merged_dataframe.loc[merged_dataframe['_merge'] == 'both', 'Final_Inv_Plan'] = 0

# # Step 4: Clean up
# merged_dataframe.drop(columns=['_merge'], inplace=True)


# %% Cell 154
Final_forecast = merged_dataframe[['city_name', 'Attribute', 'Product id', 'sub category', 'Cut class','Updated Price','day','date','sale_plan','Final_Inv_Plan','Revenue_plan','source_hub','DOC/Percentage_BufferFlag']].copy()
_dup_check(Final_forecast, "STEP-11 Final_forecast (before csv write)")
Final_forecast.to_csv('final_forecast.csv')


# %% Cell 155
pass  # clipboard removed

# %% Cell 156
pass  # debug csv removed

# %% Cell 157
merged_dataframe.describe(include='all')

# %% Cell 158
pass  # clipboard removed

# %% Cell 159
columns_to_keep = [
    'city_name', 'sub category','Product id', 'day', 'Cut class', 'date',
    'Attribute', 'sale_plan','base_plan','base_Revenue_plan', 'Updated Price', 'Revenue_plan',
    'Final_Inv_Plan'
]
final_dataframe = merged_dataframe[columns_to_keep]
final_dataframe = final_dataframe.rename(columns={
    'Attribute': 'hub_name',
    'sale_plan': 'r7_plan',
    'Revenue_plan': 'r7_plan_revenue',
    'Final_Inv_Plan': 'r7_inv',
    'Cut class' : 'Cut_Classification',
    'sub category' : 'category',
    'Updated Price' : 'price',
    'base_plan' : 'BasePlan',
    'base_Revenue_plan' : 'BaseRev'
})
final_dataframe["hub_type"] = "Online"
final_dataframe.describe(include='all')


# %% Cell 160
# Hub Mapping from synced local Product_Masters.xlsx
Hub_Mapping = _excel_tab_to_df(_MASTERS_XLSX, "Hub Mapping", usecols="A:F")
print(f"[Hub Mapping] {len(Hub_Mapping):,} rows from Product_Masters.xlsx")

# Deduplicate on merge key — multiple rows per hub_name would fan out left rows
_hub_mapping_dedup = Hub_Mapping.drop_duplicates(subset=["hub_name"])
_n_dropped = len(Hub_Mapping) - len(_hub_mapping_dedup)
if _n_dropped:
    print(f"  [Hub Mapping] dropped {_n_dropped} duplicate hub_name rows before merge")

final_dataframe = final_dataframe.merge(_hub_mapping_dedup, how='left', on="hub_name")
# Hub Mapping also has city_name — keep the left (_x) value
final_dataframe.rename(columns={'city_name_x': 'city_name'}, inplace=True)
final_dataframe.drop(columns=['city_name_y'], inplace=True, errors='ignore')
_dup_check(final_dataframe, "STEP-13 after merge Hub_Mapping", hub_col="hub_name")
final_dataframe.describe(include='all')

# %% Cell 161
# AF-50: hardcode 'old' for all rows (no sheet lookup needed)
final_dataframe['AF-50'] = 'old'

# %% Cell 162
# P Master from synced local Product_Masters.xlsx
Product_Master = _excel_tab_to_df(_MASTERS_XLSX, "P Master", usecols="A:K")
# Standardise Product id column name
if 'Product id' not in Product_Master.columns:
    _pid = [c for c in Product_Master.columns if c.lower().strip() in ('product id', 'product_id')]
    if _pid:
        Product_Master = Product_Master.rename(columns={_pid[0]: 'Product id'})
print(f"[P Master] {len(Product_Master):,} rows from Product_Masters.xlsx")

# Deduplicate on merge key — multiple rows per Product id would fan out left rows
_pm_dedup = (
    Product_Master[["Product id", "Product Name", "RM", "RM Category"]]
    .drop_duplicates(subset=["Product id"])
)
_n_dropped = len(Product_Master) - len(_pm_dedup)
if _n_dropped:
    print(f"  [P Master] dropped {_n_dropped} duplicate Product id rows before merge")

final_dataframe = final_dataframe.merge(_pm_dedup, how='left', on="Product id")
_dup_check(final_dataframe, "STEP-14 after merge P Master (Product Name/RM)", hub_col="hub_name")
final_dataframe.describe(include='all')

# %% Cell 163
# Classification and Order Type from P-H Master (hub-level)
_ot_col = 'Order Type - pan india'
_ph_class = Master_df[
    [c for c in ['hub_name', 'Product id', 'Channel', _ot_col] if c in Master_df.columns]
].copy()
_ph_class = _ph_class.rename(columns={
    'Channel': 'hub_type',
    _ot_col:   'Order Type',        # rename so downstream merge uses 'Order Type'
})
# Default any missing / blank Order Type values to 'E'
if 'Order Type' in _ph_class.columns:
    _ph_class['Order Type'] = _ph_class['Order Type'].replace('', pd.NA).fillna('E')
else:
    _ph_class['Order Type'] = 'E'

# Classification: from P Master if available, else empty
if 'Classification' in Product_Master.columns:
    _pm_class = Product_Master[['Product id', 'Classification']].drop_duplicates('Product id')
    final_dataframe = final_dataframe.merge(_pm_class, how='left', on='Product id')
else:
    final_dataframe['Classification'] = ''

_ph_class = _ph_class.drop_duplicates(subset=['hub_name', 'Product id'])
# Merge only Order Type from P-H Master — hub_type is already set to "Online" (line above)
# and we don't want a merge collision on hub_type.
final_dataframe = final_dataframe.merge(
    _ph_class[['hub_name', 'Product id', 'Order Type']],
    how='left', on=['hub_name', 'Product id']
)
# Any row still without an Order Type (not in P-H Master) defaults to 'E'
final_dataframe['Order Type'] = final_dataframe['Order Type'].replace('', pd.NA).fillna('E')
final_dataframe.describe(include='all')

# %% Cell 164
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

#%%
print(final_dataframe.columns)

final_dataframe = final_dataframe[
    [
        "city_name", "hub_name", "hub_id", "product_id", "product_name", "category", "new_catg",
        "RM", "rm_category", "Cut_Classification", "order_type", "Classification", "AF-50",
        "price", "day", "date", "hub_type", "sku_recency", "r7_plan", "r7_inv", "r7_plan_rev",
        "r7_inv_rev", "BasePlan", "BaseRev", "buffer_qty_at_upstream"
    ]
]
_dup_check(final_dataframe, "STEP-12 final_dataframe (after all merges, pre-export)", hub_col="hub_name")

# %% Cell 165
duplicate_counts = (
   final_dataframe.groupby(['hub_name', 'product_id', 'date'])
    .size()
    .reset_index(name='count')
)


duplicates_only = duplicate_counts[duplicate_counts['count'] > 1]

print(duplicates_only)

# %% Cell 166
pass  # clipboard removed

# %% Cell 167
pass  # clipboard removed

# %% Cell 168
# Avoid division by zero
mask = (
    (final_dataframe["r7_inv"] < 0) |
    (final_dataframe["r7_plan"] < 0) |
    (final_dataframe["BasePlan"] < 0) |
    (final_dataframe["r7_inv"] < 0)
)


# Print rows where condition holds true
print(final_dataframe[mask])

# %% Cell 169
pass  # clipboard removed

# %% Cell 170
# # Set up Google Sheets API credentials
# scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# creds = ServiceAccountCredentials.from_json_keyfile_name("G:/.shortcut-targets-by-id/1EF0u4bxTzGMLlMY1RfwniRIDikCT29Em/Planning Team/Chandramita/causal-flame-452312-q9-1b4341ee87db.json", scope)
# client = gspread.authorize(creds)

# # Open the Google Sheet by URL
# spreadsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1TnVwhmJBnVVRGJn0jgQLctJ98P4_EGzC4lXik6s-1mU/edit")

# # Select the specific sheet/tab by its name
# worksheet = spreadsheet.worksheet("P-L Master")

# # Get all values from
# data = worksheet.get_all_records() 

# Master_df = pd.DataFrame(data)
# print(Master_df[Master_df.duplicated(subset=['Channel', 'City', 'Product id'])])


# # Display DataFrame
# Master_df.describe(include='all')

# # %% Cell 171
# def read_sheet(sheet_name):
#     worksheet = spreadsheet.worksheet(sheet_name)
#     data = worksheet.get_all_values()
#     # df = pd.DataFrame(data[1:], columns=data[0])  # Convert to DataFrame
#     return df

# %% Cell 172
# CP / ExPreO: skipped (not needed in current flow)
pass

# %% Cell 173
pass

# %% Cell 174
# No CP/ExPreO concat
pass

# %% Cell 175
pass  # clipboard removed

# %% Cell 176
for name, df in {"final_dataframe": final_dataframe}.items():
    dup_cols = df.columns[df.columns.duplicated()].tolist()
    if dup_cols:
        print(f"{name} has duplicate columns:", dup_cols)

# %% Cell 177
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


# %% Cell 178
pass  # clipboard removed

# %% Cell 179
numeric_columns = ["hub_id","price","r7_plan", "r7_inv", "r7_plan_rev", "r7_inv_rev", "BasePlan", "BaseRev","buffer_qty_at_upstream"]

for col in numeric_columns:
    try:
        # Attempt conversion
        final_dataframe[col].astype(str).str.replace(",", "").astype(float)
    except ValueError as e:
        print(f"❌ Error in column: {col}")
        print(final_dataframe[col][~final_dataframe[col].astype(str).str.replace(",", "").str.match(r"^-?\d*\.?\d*$")].unique()[:10])
        print("-" * 50)


# %% Cell 180
# Dynamic date ranges from CLI args
print(f"[Output] Final Fcst: {FCST_START.date()} → {FCST_END.date()}")
print(f"[Output] Replication: {REPL_START.date()} → {REPL_END.date()}")

# Add key column
final_dataframe.insert(0, "", final_dataframe["hub_name"].astype(str)
                        + final_dataframe["product_id"].astype(str)
                        + final_dataframe["day"])

# Normalise date column
final_dataframe["date"] = pd.to_datetime(final_dataframe["date"], format="%Y-%m-%d", dayfirst=True)

# Filter: Final Forecast (this week)
final_Fcst = final_dataframe[
    (final_dataframe["date"] >= FCST_START) & (final_dataframe["date"] <= FCST_END)
].copy()

# Filter: Replication of Indents (next week = +7 days)
Replication_of_Indents = final_dataframe[
    (final_dataframe["date"] >= REPL_START) & (final_dataframe["date"] <= REPL_END)
].copy()

print(f"[Output] Final Fcst rows: {len(final_Fcst):,}  |  Replication rows: {len(Replication_of_Indents):,}")

# Dynamic output filename
with pd.ExcelWriter(OUTPUT_FILE, engine="xlsxwriter") as writer:
    final_Fcst.to_excel(writer, sheet_name="Final Fcst", index=False)
    Replication_of_Indents.to_excel(writer, sheet_name="Replications for indents", index=False)

_ui_step("Export complete - writing output workbook")
print(f"✅ Excel file '{OUTPUT_FILE}' created successfully with two sheets.")


# %% Cell 181
#VA projection
# Define the categories to exclude
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

# # %% Cell 182
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
