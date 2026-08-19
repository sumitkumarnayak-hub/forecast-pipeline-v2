import os
import json
from dotenv import load_dotenv

# Base directory (project root, parent of pipeline/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv(os.path.join(os.path.dirname(BASE_DIR), '.env'))
google_creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
GOOGLE_CREDENTIALS_DICT = json.loads(google_creds_json) if google_creds_json else {}

# Input paths
RDS_PATH = os.path.join(BASE_DIR, "data_folder_inputs", "6w_v3.RDS")
JSON_KEYFILE_PATH = os.path.join(BASE_DIR, "data_folder_inputs", "causal-flame-452312-q9-1b4341ee87db.json")
FF_FESTIVE_FILE_PATH = os.path.join(BASE_DIR, "data_folder_inputs", "Festive.xlsx")

# Drive folder IDs for inputs
DRIVE_FOLDER_ID = "1ZqSz5MYpBOKTffpTczE5SD7EjNvZE3PU"
RAW_DATA_DRIVE_FOLDER_ID = "19glDNTiMzMkgtEhmwztcp6tQ9AjBtstp"
BASELINE_DRIVE_PARQUET_FOLDER_ID = "1Vw2wC6IgD8OAXp9GAx42aMSNhXftdz8N"

# Drive destination folders for baseline outputs
BASELINE_OUTPUT_EXCEL_FOLDER_ID = "1SSJVaxtgQBTFncfBvAK7zFdbBBnyadcQ"
BASELINE_OUTPUT_PARQUET_FOLDER_ID = "12SuspXFi2xTKBwSEm3rw4ZtljZE-gRXp"

# Drive destination folders for FF Hub automation outputs
FF_OUTPUT_EXCEL_FOLDER_ID = "1uiY4gp-K16ZIZhmWWb2P0ecIMl7KwSVD"
FF_OUTPUT_PARQUET_FOLDER_ID = "1kXjCiYe310X-Mm7lAGJb4ijg7cmUU3WM"

# Output filename templates/basenames
FF_HUB_DIST_XLSX_PATH = os.path.join(BASE_DIR, "new_output", "Hub_Dist_Wk202626_Mon_Thu.xlsx")

# Legacy baseline path constants used by baseline_parquet.py and older scripts
BASELINE_RAW_DATA_PATH = os.path.join(BASE_DIR, "data_folder_inputs", "Raw_data.csv")
BASELINE_CURRENT_FORECASTING_DIR = os.path.join(BASE_DIR, "new_output")
BASELINE_WEEKLY_PLAN_PATH = os.path.join(BASELINE_CURRENT_FORECASTING_DIR, "Baseline Wk31 2026.xlsx")
HUB_LEVEL_PLAN_CSV_PATH = os.path.join(BASELINE_CURRENT_FORECASTING_DIR, "Hub_Level_Plan.csv")
