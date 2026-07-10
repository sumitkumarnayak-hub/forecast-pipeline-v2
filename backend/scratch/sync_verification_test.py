import os
import io
import pandas as pd
import time
from dotenv import load_dotenv

PROJECT_ROOT = "C:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2"
load_dotenv(os.path.join(PROJECT_ROOT, "backend/.env"))

import sys
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend/src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from planning_suite import config as cfg
from planning_suite.features.new_product_launch import _open_sheet, parse_city_upload, load_hub_salience, split_city_to_hubs
from planning_suite.services import npl_wizard as wiz
from app.routers.new_product_launch import _get_product_master_details_map, _build_hub_plan_row_dynamic

def execute_real_sync_hub_level():
    print("=== Executing Real Hub Level Sync ===")

    # 1. Parse Excel data representing PDF input (re-created as a DataFrame)
    # The user provided: city_name=Bangalore, product_id=pr_id_1_test, product_name="Test Product Name", category="Ready to Cook", MRP=91
    # Weekday allocations: Mon=20, Tue=30, Wed=52, Thu=0, Fri=0, Sat=0, Sun=0
    raw_df = pd.DataFrame([
        {
            "city_name": "Bangalore",
            "product_id": "pr_id_1_test",
            "product_name": "Test Product Name",
            "category": "Ready to Cook",
            "MRP": 91.0,
            "Mon": 20, "Tue": 30, "Wed": 52, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0
        }
    ])
    
    # 2. Run upload parser to validate
    buf = io.BytesIO()
    raw_df.to_excel(buf, index=False)
    buf.seek(0)
    parsed_df, errors = parse_city_upload(buf)
    if errors:
        print(f"Validation failed: {errors}")
        return
    print("Success: Excel upload parsed successfully.")

    # 3. Generate Hub splits using Hub Salience Suggestions
    sal_df = load_hub_salience()
    hub_split_df, zero_sal_info = split_city_to_hubs(parsed_df, sal_df)
    print(f"Success: Hub allocation generated ({len(hub_split_df)} hub rows).")

    # 4. Attach Launch Dates
    hub_rows = hub_split_df.to_dict(orient="records")
    launch_date = "2026-07-27"
    rows_with_dates = wiz.apply_launch_dates(hub_rows, launch_date)

    # 5. Open target Hub_Plan sheet and fetch dynamic headers
    plan_sheet = _open_sheet(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY, "Hub_Plan")
    first_row = plan_sheet.row_values(1)
    print(f"DEBUG RAW ROW 1 VALUES: {first_row}")
    sheet_headers = [str(h).strip() for h in first_row]
    # Filter out empty cells, but preserve layout size
    sheet_headers = [h for h in sheet_headers if h != '']
    print(f"Success: Target worksheet headers fetched ({len(sheet_headers)} columns): {sheet_headers}")

    # 6. Map each row dynamically to Hub_Plan columns using _build_hub_plan_row_dynamic
    pm_details_map = _get_product_master_details_map()
    update_date = time.strftime("%Y-%m-%d")
    
    values_to_append = []
    for source in rows_with_dates:
        row_source = {
            "Submission_Type": "New Launch",
            "Product ID": str(source.get("product_id", "")).strip(),
            "Product Name": source.get("product_name", ""),
            "Category": source.get("category", ""),
            "City": source.get("city_name", ""),
            "Hub": str(source.get("hub_name", "")).strip(),
            "MRP": source.get("MRP", ""),
            "Start Date": source.get("Launch Date", ""),
            "Submitted_By": "System-Verification",
            "Timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Mon": source.get("Mon", 0),
            "Tue": source.get("Tue", 0),
            "Wed": source.get("Wed", 0),
            "Thu": source.get("Thu", 0),
            "Fri": source.get("Fri", 0),
            "Sat": source.get("Sat", 0),
            "Sun": source.get("Sun", 0),
            "_owner_email": "system@verification.com",
        }
        row_vals = _build_hub_plan_row_dynamic(row_source, sheet_headers, update_date=update_date, pm_details_map=pm_details_map)
        values_to_append.append(row_vals)

    # 7. Append directly to Google Sheet
    if values_to_append:
        print(f"DEBUG: Headers are: {sheet_headers}")
        print(f"DEBUG: Sample row generated has length {len(values_to_append[0])}: {values_to_append[0]}")
        print(f"Appending {len(values_to_append)} rows to Google Sheet starting at A...")
        # Specify table range starting cell explicitly as 'A1' or the bottom-most cell, or use insert_rows/append_rows with standard table layouts
        plan_sheet.append_rows(values_to_append, value_input_option="USER_ENTERED", table_range="A1")
        print("Success: Data appended successfully to Hub_Plan worksheet!")
    else:
        print("No values generated to append.")

if __name__ == "__main__":
    execute_real_sync_hub_level()
