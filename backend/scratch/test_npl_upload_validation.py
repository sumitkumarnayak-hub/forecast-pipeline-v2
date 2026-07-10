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

from planning_suite.features.new_product_launch import parse_city_upload, parse_hub_upload

def test_validation_edge_cases():
    print("=== Testing Upload Validation Edge Cases ===")
    
    # 1. Invalid City Test
    invalid_city_df = pd.DataFrame([
        {
            "city_name": "Atlantis",  # Invalid city
            "product_id": "pr_test123",
            "product_name": "Test Product",
            "category": "Eggs",
            "MRP": 150.0,
            "Mon": 10, "Tue": 10, "Wed": 10, "Thu": 10, "Fri": 10, "Sat": 10, "Sun": 10
        }
    ])
    
    # Write to memory buffer
    buf_invalid_city = io.BytesIO()
    invalid_city_df.to_excel(buf_invalid_city, index=False)
    buf_invalid_city.seek(0)
    
    t0 = time.perf_counter()
    _, errors = parse_city_upload(buf_invalid_city)
    t_invalid_city = (time.perf_counter() - t0) * 1000
    print(f"\n[Test 1] Invalid City Check (Time: {t_invalid_city:.2f}ms):")
    print(f"Errors returned: {errors}")
    
    # 2. Empty Columns Test (Product ID, Product Name, Category)
    empty_col_df = pd.DataFrame([
        {
            "city_name": "Bangalore",
            "product_id": "pr_1",
            "product_name": "  ",  # Blank Product Name
            "category": "Eggs",
            "MRP": 120.0,
            "Mon": 5, "Tue": 5, "Wed": 5, "Thu": 5, "Fri": 5, "Sat": 5, "Sun": 5
        }
    ])
    
    buf_empty_col = io.BytesIO()
    empty_col_df.to_excel(buf_empty_col, index=False)
    buf_empty_col.seek(0)
    
    t0 = time.perf_counter()
    _, errors = parse_city_upload(buf_empty_col)
    t_empty_col = (time.perf_counter() - t0) * 1000
    print(f"\n[Test 2] Empty Product Name Check (Time: {t_empty_col:.2f}ms):")
    print(f"Errors returned: {errors}")

    # 3. Invalid MRP (Zero/Negative) Test
    invalid_mrp_df = pd.DataFrame([
        {
            "city_name": "Bangalore",
            "product_id": "pr_test_mrp",
            "product_name": "Test Product",
            "category": "Eggs",
            "MRP": 0.0,  # Invalid MRP
            "Mon": 5, "Tue": 5, "Wed": 5, "Thu": 5, "Fri": 5, "Sat": 5, "Sun": 5
        }
    ])
    
    buf_invalid_mrp = io.BytesIO()
    invalid_mrp_df.to_excel(buf_invalid_mrp, index=False)
    buf_invalid_mrp.seek(0)
    
    t0 = time.perf_counter()
    _, errors = parse_city_upload(buf_invalid_mrp)
    t_invalid_mrp = (time.perf_counter() - t0) * 1000
    print(f"\n[Test 3] Zero/Negative MRP Check (Time: {t_invalid_mrp:.2f}ms):")
    print(f"Errors returned: {errors}")

    # 4. Valid Sync Payload Test
    valid_df = pd.DataFrame([
        {
            "city_name": "Bangalore",
            "product_id": "pr_test_valid",
            "product_name": "Test Product",
            "category": "Eggs",
            "MRP": 119.5,
            "Mon": 5, "Tue": 5, "Wed": 5, "Thu": 5, "Fri": 5, "Sat": 5, "Sun": 5
        }
    ])
    
    buf_valid = io.BytesIO()
    valid_df.to_excel(buf_valid, index=False)
    buf_valid.seek(0)
    
    # 5. Negative Weekdays Allocation Test
    negative_day_df = pd.DataFrame([
        {
            "city_name": "Bangalore",
            "product_id": "pr_test_neg",
            "product_name": "Test Product",
            "category": "Eggs",
            "MRP": 119.5,
            "Mon": -20, "Tue": 0, "Wed": 0, "Thu": 0, "Fri": 0, "Sat": 0, "Sun": 0
        }
    ])
    
    buf_neg = io.BytesIO()
    negative_day_df.to_excel(buf_neg, index=False)
    buf_neg.seek(0)
    
    t0 = time.perf_counter()
    _, errors = parse_city_upload(buf_neg)
    t_neg = (time.perf_counter() - t0) * 1000
    print(f"\n[Test 5] Negative Weekday Allocations Check (Time: {t_neg:.2f}ms):")
    print(f"Errors returned: {errors}")

if __name__ == "__main__":
    test_validation_edge_cases()
