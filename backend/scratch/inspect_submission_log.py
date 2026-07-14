import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app import config as cfg

from features.product_launch.core import _open_sheet


try:
    log_sheet = _open_sheet(cfg.HUB_LEVEL_PLANNING_SHEET_KEY, "Submission_Log")
    print("Submission_Log columns:")
    print(log_sheet.row_values(1))
    print("Submission_Log row 2:")
    print(log_sheet.row_values(2))
except Exception as e:
    print("Error:", e)
