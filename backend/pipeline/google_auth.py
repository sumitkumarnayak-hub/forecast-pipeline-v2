import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config_paths import GOOGLE_CREDENTIALS_DICT

# Define authorization scopes
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client():
    """Initializes and returns a gspread client using Service Account credentials."""
    creds = ServiceAccountCredentials.from_json_keyfile_dict(GOOGLE_CREDENTIALS_DICT, SCOPE)
    return gspread.authorize(creds)

# Global client instance to be imported and reused across modules/notebook cells
client = get_gspread_client()
