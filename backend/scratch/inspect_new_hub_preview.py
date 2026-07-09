import os
import json
import pandas as pd
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.services.hub_sync import build_new_hub_sync_preview

def run_test():
    from dotenv import load_dotenv
    load_dotenv("C:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/.env")
    print("Initializing Google Sheets client...")
    gsm = GoogleSheetsManager()
    
    print("Calling build_new_hub_sync_preview to fetch parameters from FF Input...")
    try:
        res = build_new_hub_sync_preview(gsm)
        print("Success! Summary Report:")
        print(f"Total Rows to Insert: {res.get('total_to_insert')}")
        print(f"Duplicates Skipped: {res.get('duplicates_skipped')}")
        print(f"Validation Errors: {res.get('validation_errors')}")
        print("\nMapping Report details:")
        for r in res.get("mapping_report", []):
            print(f"  New Hub: {r.get('new_hub')} | Source: {r.get('source_hub')} | Status: {r.get('status')} | Added: {r.get('rows_inserted')} | Skipped: {r.get('duplicates_skipped')} | Message: {r.get('message', '')}")
            
        with open("C:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/scratch/preview_output.json", "w") as f:
            json.dump(res, f, indent=2)
        print("\nRaw preview output saved to scratch/preview_output.json")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")

if __name__ == "__main__":
    run_test()
