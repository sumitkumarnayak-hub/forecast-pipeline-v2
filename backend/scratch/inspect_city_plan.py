import os
import sys
from pathlib import Path
import json

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from app import config as cfg

from features.product_launch.core import _get_client


try:
    client = _get_client()
    sh = client.open_by_key(cfg.NEW_PRODUCT_LAUNCH_SHEET_KEY)
    ws = sh.worksheet("City_Plan")
    print("City_Plan row 1 (headers?):", ws.row_values(1))
    print("City_Plan row 2:", ws.row_values(2))
    print("City_Plan row 3:", ws.row_values(3))
    print("City_Plan row 4:", ws.row_values(4))
    print("City_Plan row 5:", ws.row_values(5))
except Exception as e:
    print("Error:", e)
