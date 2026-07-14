import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app.config import CLUSTER_MASTER_SHEET_KEY
from features.product_launch.core import _open_sheet


try:
    client = _open_sheet(CLUSTER_MASTER_SHEET_KEY, "P-L Master").spreadsheet
    for ws in client.worksheets():
        print(f"Worksheet: {ws.title}")
        try:
            print("  Headers:", ws.row_values(1)[:15])
        except Exception as e:
            print("  Error reading headers:", e)
except Exception as e:
    print("Error:", e)
