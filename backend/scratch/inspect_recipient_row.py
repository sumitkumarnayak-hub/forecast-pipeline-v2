
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from planning_suite.db.engine import Database

try:
    db = Database()
    with db.engine.connect() as conn:
        import pandas as pd
        df = pd.read_sql("SELECT * FROM email_notification_recipients", conn)
        for idx, row in df.iterrows():
            print(row.to_dict())
except Exception as e:
    print("Error:", e)
