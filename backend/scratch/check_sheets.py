import os
import sys
from pathlib import Path

# Add backend/src to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

# Bypass GOOGLE_CREDENTIALS_PATH to force GOOGLE_CREDENTIALS_JSON env resolution
if "GOOGLE_CREDENTIALS_PATH" in os.environ:
    del os.environ["GOOGLE_CREDENTIALS_PATH"]
# Also let's overwrite the temp file if it exists, or just let google_credentials materialize it.
# Actually, let's delete the file at C:\tmp\google-credentials.json to see if it gets materialized correctly.
try:
    p = Path("C:/tmp/google-credentials.json")
    if p.is_file():
        p.unlink()
        print("Deleted C:/tmp/google-credentials.json to force re-materialization")
except Exception as e:
    print("Could not delete temp file:", e)

from app import config as cfg

from features.product_launch.core import _get_client


print(f"NEW_PRODUCT_LAUNCH_SHEET_URL: {cfg.NEW_PRODUCT_LAUNCH_SHEET_URL}")
print(f"NEW_PRODUCT_LAUNCH_SHEET_KEY: {cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY}")

try:
    client = _get_client()
    sh = client.open_by_key(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY)
    print("Successfully connected to the spreadsheet!")
    print("Worksheets present:")
    for ws in sh.worksheets():
        print(f" - {ws.title}")
        
    # Let's inspect "Hub_Plan" and "City_Plan" if they exist
    for sheet_name in ["Hub_Plan", "City_Plan"]:
        try:
            ws = sh.worksheet(sheet_name)
            print(f"\nSheet '{sheet_name}' properties:")
            print(f"  Rows: {ws.row_count}, Cols: {ws.col_count}")
            headers = ws.row_values(1)
            print(f"  Headers: {headers}")
        except Exception as e:
            print(f"\nSheet '{sheet_name}' not found: {e}")
            
except Exception as e:
    print(f"Error occurred: {e}")
