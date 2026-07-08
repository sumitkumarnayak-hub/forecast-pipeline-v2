import os
import sys
from pathlib import Path
import json

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

from planning_suite import google_credentials as gc

print("--- ENV VARS ---")
print("GOOGLE_CREDENTIALS_PATH in env:", os.getenv("GOOGLE_CREDENTIALS_PATH"))
print("GOOGLE_CREDENTIALS_JSON in env length:", len(os.getenv("GOOGLE_CREDENTIALS_JSON") or ""))

print("\n--- RESOLUTION ---")
try:
    path = gc.get_google_credentials_path()
    print("Resolved path:", path)
    print("Path is file?", Path(path).is_file())
    if Path(path).is_file():
        content = Path(path).read_text(encoding="utf-8")
        print("Materialized JSON content length:", len(content))
        # Try parsing it
        data = json.loads(content)
        print("JSON keys:", list(data.keys()))
        print("type:", data.get("type"))
        print("project_id:", data.get("project_id"))
        print("private_key_id:", data.get("private_key_id"))
        print("token_uri present?", "token_uri" in data)
        print("token_uri value:", data.get("token_uri"))
except Exception as e:
    print("Error during get_google_credentials_path:", e)
