import os
import json
from dotenv import load_dotenv

load_dotenv("C:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/.env")

from core.shared.google_sheets import GoogleSheetsManager

from app.config import DPM_SHEET_KEY

def run_sync():
    print("Loading preview output data...")
    with open("C:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/scratch/preview_output.json") as f:
        res = json.load(f)
    
    headers = res["ph_headers"]
    rows = res["rows_to_add"]
    
    # Simulating values matrix
    values = [[r.get(h, "") for h in headers] for r in rows]
    print(f"Generated matrix size: {len(values)} rows x {len(values[0]) if values else 0} cols")
    
    if not values:
        print("No values to sync.")
        return
        
    print("Initializing Sheets Manager and appending rows...")
    gsm = GoogleSheetsManager()
    ss = gsm.gc.open_by_key(DPM_SHEET_KEY)
    ph_ws = ss.worksheet("P-H Master")
    
    success = gsm.append_rows_to_worksheet(
        "demand_planning_masters",
        "product_hub_master",
        values,
        worksheet=ph_ws,
        value_input_option="RAW"
    )
    print(f"Sync Result: {success}")

if __name__ == "__main__":
    run_sync()
