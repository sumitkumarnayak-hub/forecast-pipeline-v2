"""
Configuration file for Planning & Forecasting Tool
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Project paths (repo root = grandparent of src/planning_suite/)
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent
BASE_DIR = PROJECT_ROOT

load_dotenv(BASE_DIR / ".env")


def _env_path(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise KeyError(f"Configuration path environment variable '{name}' must be set in your .env file.")
    return value


# Google Sheets Configuration
PLANNING_DRIVE_ROOT = _env_path("PLANNING_DRIVE_ROOT")

from planning_suite.google_credentials import get_google_credentials_path

GOOGLE_CREDENTIALS_PATH = get_google_credentials_path()


def sheet_id_from_url(url: str) -> str:
    """Extract spreadsheet ID from a Google Sheets URL (or return as-is if already an ID)."""
    if "/d/" in url:
        return url.split("/d/")[1].split("/")[0]
    return url.strip()


# Google Sheets URLs
HUB_LEVEL_PLANNING_SHEET_URL = _env_path("HUB_LEVEL_PLANNING_SHEET_URL")
NEW_HUB_LAUNCH_SHEET_URL = _env_path("NEW_HUB_LAUNCH_SHEET_URL")
DEMAND_PLANNING_MASTERS_SHEET_URL = _env_path("DEMAND_PLANNING_MASTERS_SHEET_URL")
CLUSTER_MASTER_SHEET_URL = _env_path("CLUSTER_MASTER_SHEET_URL")
AVAILABILITY_LOSS_SHEET_URL = _env_path("AVAILABILITY_LOSS_SHEET_URL")
DP_LOGICS_SHEET_URL = _env_path("DP_LOGICS_SHEET_URL")
VALIDATION_SHEET_URL = _env_path("VALIDATION_SHEET_URL")
EA_TRACKER_SHEET_URL = _env_path("EA_TRACKER_SHEET_URL")
INVENTORY_BUFFER_SHEET_URL = _env_path("INVENTORY_BUFFER_SHEET_URL")
PIPELINE_PARAMS_SHEET_URL = os.getenv("PIPELINE_PARAMS_SHEET_URL", "").strip()
PIPELINE_PARAMS_VARIABLES_TAB = os.getenv("PIPELINE_PARAMS_VARIABLES_TAB", "Variables").strip() or "Variables"
PIPELINE_PARAMS_HUB_CHANGES_TAB = os.getenv("PIPELINE_PARAMS_HUB_CHANGES_TAB", "Hub_Changes").strip() or "Hub_Changes"

HUB_CHANGES_COLUMNS = [
    "city_name",
    "Type",
    "Hub_name",
    "Source_Hub",
    "Hub_id",
    "Percentage",
    "Start_date",
    "End_date",
    # Manual UI config (P-H sync / Auto-Pilot Step 2)
    "product_ids",       # comma-separated; blank = copy all products from Source_Hub
    "add_hub_mapping",   # TRUE/FALSE — add Hub Mapping row from source if missing
]

# Spreadsheet IDs
HUB_LEVEL_PLANNING_SHEET_KEY = sheet_id_from_url(HUB_LEVEL_PLANNING_SHEET_URL)
NEW_HUB_LAUNCH_SHEET_KEY = sheet_id_from_url(NEW_HUB_LAUNCH_SHEET_URL)
DPM_SHEET_KEY = sheet_id_from_url(DEMAND_PLANNING_MASTERS_SHEET_URL)
DEMAND_PLANNING_SHEET_ID = DPM_SHEET_KEY  # alias used by pipeline / master data flows
CLUSTER_MASTER_SHEET_KEY = sheet_id_from_url(CLUSTER_MASTER_SHEET_URL)
DP_LOGICS_SHEET_KEY = sheet_id_from_url(DP_LOGICS_SHEET_URL)
INV_LOGICS_SHEET_KEY = sheet_id_from_url(INVENTORY_BUFFER_SHEET_URL)
EA_TRACKER_SHEET_KEY = sheet_id_from_url(EA_TRACKER_SHEET_URL)

SHEETS_CONFIG = {
    "hub_level_planning": {
        "url": HUB_LEVEL_PLANNING_SHEET_URL,
        "worksheets": {
            "avl_flag": "Avl_Flag",
            "hub_changes": "Hub_Changes",
            "outlier": "City_Cat",
            "city_drops": "City_drops",
            "percentile": "Percentile",
            "hub_sku_master": "Hub Sku Master",
            "sell_through": "SellThroughFactor",
            "hub_suggestion": "Hub level Suggestion"
        }
    },
    "new_hub_launch": {
        "url": NEW_HUB_LAUNCH_SHEET_URL,
        "worksheets": {
            "new_hub_launch": "New Hub launch",
            "ff_input": "FF Input"
        }
    },
    "demand_planning_masters": {
        "url": DEMAND_PLANNING_MASTERS_SHEET_URL,
        "worksheets": {
            "product_master": "P Master",
            "product_hub_master": "P-H Master",
            "htt_mapping": "HTT Mapping",
            "hub_mapping": "Hub Mapping",
            "city_mapping": "City_Mapping",
            "product_location_master": "P-L Master"
        }
    },
    "cluster_master": {
        "url": CLUSTER_MASTER_SHEET_URL,
        "worksheets": {
            "cluster_mapping": "Cluster phase 2"
        }
    },
    "availability_loss": {
        "url": AVAILABILITY_LOSS_SHEET_URL,
        "worksheets": {
            "avail_led_rev_loss": "Avail Led Rev Loss"
        }
    }
}

# Database Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None
DATABASE_PATH = BASE_DIR / "forecasting_db.sqlite"


def get_database_url():
    load_dotenv(BASE_DIR / ".env", override=True)
    return os.getenv("DATABASE_URL", "").strip() or None


def get_database_backend(db_url=None):
    url = db_url if db_url is not None else get_database_url()
    return "postgresql" if url else "sqlite"


def get_supabase_project_ref(db_url=None) -> str:
    url = db_url if db_url is not None else get_database_url()
    if not url:
        return ""
    try:
        userinfo = url.split("://", 1)[1].split("@", 1)[0]
        username = userinfo.split(":", 1)[0]
        if username.startswith("postgres.") and "." in username:
            return username.split(".", 1)[1]
    except (IndexError, ValueError):
        pass
    return ""


def get_supabase_url(db_url=None) -> str:
    explicit = os.getenv("SUPABASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    ref = get_supabase_project_ref(db_url)
    return f"https://{ref}.supabase.co" if ref else ""


def get_supabase_service_role_key() -> str:
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def get_supabase_storage_bucket() -> str:
    return os.getenv("SUPABASE_STORAGE_BUCKET", "input-output").strip() or "input-output"


def get_storage_backend_name() -> str:
    return os.getenv("STORAGE_BACKEND", "local").strip().lower() or "local"


def get_pipeline_drive_folder_url() -> str:
    return os.getenv("PIPELINE_DRIVE_FOLDER_URL", "").strip()


def drive_folder_id_from_url(url_or_id: str) -> str:
    """Extract a Drive folder ID from a share URL or bare ID."""
    value = (url_or_id or "").strip()
    if not value:
        return ""
    if "/folders/" in value:
        return value.split("/folders/", 1)[1].split("?")[0].split("/")[0].strip()
    if "id=" in value:
        return value.split("id=", 1)[1].split("&")[0].strip()
    return value


def get_pipeline_drive_folder_id() -> str:
    explicit = drive_folder_id_from_url(get_pipeline_drive_folder_url())
    if explicit:
        return explicit
    # Google Drive for Desktop: G:\.shortcut-targets-by-id\<FOLDER_ID>\...
    root = os.getenv("PLANNING_DRIVE_ROOT", "").strip().replace("/", "\\")
    marker = ".shortcut-targets-by-id\\"
    if marker in root:
        return root.split(marker, 1)[1].split("\\")[0].strip()
    return ""


def get_google_drive_impersonate_email() -> str:
    """Optional Workspace user for domain-wide delegation (regular My Drive uploads)."""
    return os.getenv("GOOGLE_DRIVE_IMPERSONATE_EMAIL", "").strip()


def get_database_host_label(db_url=None) -> str:
    url = db_url if db_url is not None else get_database_url()
    if not url:
        return ""
    try:
        return url.split("@", 1)[1].split("/", 1)[0]
    except (IndexError, ValueError):
        return ""


# File paths
_output_env = os.getenv("OUTPUT_PATH", "").strip()
OUTPUT_PATH = Path(_output_env) if _output_env else BASE_DIR / "outputs"
OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
BASELINE_APPROVAL_JSON = OUTPUT_PATH / "baseline_approval.json"

RAW_DATA_PATH = _env_path("RAW_DATA_PATH")
RDS_6W_PATH = _env_path("RDS_6W_PATH")
BASELINE_OUTPUTS_FOLDER = _env_path("BASELINE_OUTPUTS_FOLDER")
FF_INPUTS_FOLDER = _env_path("FF_INPUTS_FOLDER")
FF_INV_LOGIC_FOLDER = _env_path("FF_INV_LOGIC_FOLDER")
FF_MASTERS_XLSX = _env_path("FF_MASTERS_XLSX")
RAW_ACTUALS_FOLDER = _env_path("RAW_ACTUALS_FOLDER")
DP_LOGICS_FOLDER = _env_path("DP_LOGICS_FOLDER")



USER_ROLES = {
    "admin": ["read", "write", "approve", "manage_users"],
    "planner": ["read", "write"],
    "viewer": ["read"]
}

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

VALIDATION_RULES = {
    "product_master": {
        "required_columns": [],
        "unique_columns": []
    },
    "hub_changes": {
        "required_columns": ["Type", "Hub_name", "Source_Hub", "Percentage", "Start_date", "End_date"],
        "optional_columns": ["Hub_id", "city_name", "product_ids", "add_hub_mapping"],
        "valid_types": ["New Hub", "KML Remapping"]
    }
}

APP_TITLE = "Planning Suite"
APP_ICON = "📊"
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}

AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "ps_auth").strip() or "ps_auth"
AUTH_COOKIE_DAYS = float(os.getenv("AUTH_COOKIE_DAYS", "7"))


def get_auth_secret() -> str:
    secret = os.getenv("AUTH_SECRET_KEY", "").strip()
    if secret:
        return secret
    if IS_PRODUCTION:
        raise RuntimeError(
            "AUTH_SECRET_KEY must be set in .env when APP_ENV=production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return "dev-insecure-auth-key-change-before-production"


PAGE_CONFIG = {
    "page_title": "Planning Suite — Demand Planning",
    "page_icon": APP_ICON,
    "layout": "wide",
    "initial_sidebar_state": "expanded"
}


def _smtp_host_for_email(email: str) -> str:
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain in {"gmail.com", "googlemail.com"}:
        return "smtp.gmail.com"
    if domain in {"outlook.com", "hotmail.com", "live.com", "office365.com"}:
        return "smtp.office365.com"
    return "smtp.gmail.com"


def get_smtp_config() -> dict:
    load_dotenv(BASE_DIR / ".env", override=True)
    from_email = os.getenv("FROM_EMAIL", "").strip()
    app_password = os.getenv("FROM_EMAIL_APP_PASSWORD", "").strip()

    if not from_email:
        from_email = os.getenv("SMTP_USER", "").strip()
    if not app_password:
        app_password = os.getenv("SMTP_PASSWORD", "").strip()

    return {
        "host": _smtp_host_for_email(from_email) if from_email else "",
        "port": 587,
        "username": from_email,
        "password": app_password,
        "from_address": from_email,
        "use_tls": True,
    }


def is_smtp_configured() -> bool:
    cfg = get_smtp_config()
    return bool(cfg["username"] and cfg["password"])
