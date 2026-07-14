import os
import io
import pandas as pd
import time
from dotenv import load_dotenv

# Set paths
PROJECT_ROOT = "C:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2"
load_dotenv(os.path.join(PROJECT_ROOT, "backend/.env"))

import sys
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend/src"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "backend"))

from features.product_launch.core import parse_city_upload, parse_hub_upload

from features.product_launch.wizard import check_duplicates

from features.product_launch import wizard as wiz

from features.product_launch.core import load_salience_source, get_cities_from_salience, get_hubs_for_city


def test_full_pipeline_flow():
    print("=== Testing Full Wizard Flow (Step 1 to Step 4) ===")
    
    # -------------------------------------------------------------
    # STEP 1: Upload and Validation (Time it takes to parse & validate Excel)
    # -------------------------------------------------------------
    valid_city_df = pd.DataFrame([
        {
            "city_name": "Bangalore",
            "product_id": "pr_test_flow",
            "product_name": "Vitamin D Eggs - Pack of 6",
            "category": "Eggs",
            "MRP": 119.5,
            "Mon": 5, "Tue": 5, "Wed": 5, "Thu": 5, "Fri": 5, "Sat": 5, "Sun": 5
        }
    ])
    
    buf = io.BytesIO()
    valid_city_df.to_excel(buf, index=False)
    buf.seek(0)
    
    t0 = time.perf_counter()
    parsed_df, errors = parse_city_upload(buf)
    t_step1 = (time.perf_counter() - t0) * 1000
    print(f"Step 1: Upload Parsing & Validation completed in {t_step1:.2f}ms")
    assert not errors, f"Failed Step 1 validation: {errors}"

    # -------------------------------------------------------------
    # STEP 2: Hub Split generation (Derived from Hub Salience Suggestions)
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    from features.product_launch.core import load_hub_salience

    salience_df = load_hub_salience()
    from features.product_launch.core import split_city_to_hubs

    hub_split_df, zero_sal_info = split_city_to_hubs(parsed_df, salience_df)
    t_step2 = (time.perf_counter() - t0) * 1000
    print(f"Step 2: Hub Allocation Split generated in {t_step2:.2f}ms")
    print(f"       Allocated to {len(hub_split_df)} hub rows.")

    # -------------------------------------------------------------
    # STEP 3: Setup Date & Duplicate Checks
    # -------------------------------------------------------------
    hub_rows = hub_split_df.to_dict(orient="records")
    # Simulate adding launch date
    launch_date = "2026-07-20"
    t0 = time.perf_counter()
    res = check_duplicates(hub_rows, sub_type="New Launch", plan_level="hub")
    t_step3 = (time.perf_counter() - t0) * 1000
    print(f"Step 3: Duplicate Checks completed in {t_step3:.2f}ms (Has duplicates: {res.get('has_duplicates')})")

    # -------------------------------------------------------------
    # STEP 4: Preview Sync preparation (Building dynamic headers & fields mapping)
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    # Call the exact backend route builder logic we just resolved
    from features.product_launch.router import _get_product_master_details_map, _build_city_plan_row_dynamic
    pm_details_map = _get_product_master_details_map()
    
    rows_with_dates = wiz.apply_launch_dates(hub_rows, launch_date)
    preview_records = []
    headers = ["OWNER", "TYPE", "CHANNEL", "UPDATE_DATE", "SUB_CATEGORY", "PRODUCT_ID", "PRODUCT_NAME", "Anchor ID", "PLU_CODE", "City", "hub_name", "MRP", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Planning Confirmation"]
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
            "Mon": source.get("Mon", 0),
            "Tue": source.get("Tue", 0),
            "Wed": source.get("Wed", 0),
            "Thu": source.get("Thu", 0),
            "Fri": source.get("Fri", 0),
            "Sat": source.get("Sat", 0),
            "Sun": source.get("Sun", 0),
        }
        row_vals = _build_city_plan_row_dynamic(row_source, headers, update_date="2026-07-10", pm_details_map=pm_details_map)
        preview_records.append(row_vals)
    t_step4 = (time.perf_counter() - t0) * 1000
    print(f"Step 4: Preview Generation completed in {t_step4:.2f}ms")
    
    total_time = t_step1 + t_step2 + t_step3 + t_step4
    print(f"\nTotal client-server flow execution time: {total_time:.2f}ms (~{total_time/1000:.2f}s)")

if __name__ == "__main__":
    test_full_pipeline_flow()
