import io
import logging
import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
from core.shared.google_credentials import load_service_account_credentials

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    creds = load_service_account_credentials(SCOPES)
    return build('drive', 'v3', credentials=creds)

def upload_df_to_drive(df: pd.DataFrame, filename: str, folder_id: str) -> str:
    """
    Converts a DataFrame to Parquet in-memory and uploads to Google Drive.
    Returns the file ID.
    """
    if not folder_id:
        raise ValueError("Google Drive folder ID cannot be empty.")
        
    service = get_drive_service()
    
    # Cast object columns to string to prevent PyArrow crashes
    out_df = df.copy()
    for col in out_df.columns:
        if out_df[col].dtype == 'object':
            out_df[col] = out_df[col].apply(lambda x: str(x) if pd.notnull(x) else x)
            
    parquet_io = io.BytesIO()
    out_df.to_parquet(parquet_io, index=False)
    parquet_io.seek(0)
    
    # Check if file already exists in folder to overwrite it
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query, spaces='drive', fields='files(id)', supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    
    existing_files = results.get('files', [])
    
    media = MediaIoBaseUpload(
        parquet_io, 
        mimetype='application/vnd.apache.parquet', 
        chunksize=20 * 1024 * 1024,
        resumable=True
    )
    
    if existing_files:
        # Update existing file
        file_id = existing_files[0]['id']
        request = service.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True
        )
    else:
        # Create new file
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        )
        
    response = None
    while response is None:
        status, response = request.next_chunk()
        
    return response.get('id') if response else ""

def download_df_from_drive(filename: str, folder_id: str) -> pd.DataFrame:
    """
    Downloads a Parquet file from Google Drive and returns it as a DataFrame.
    Raises FileNotFoundError if it doesn't exist.
    """
    if not folder_id:
        raise ValueError("Google Drive folder ID cannot be empty.")
        
    service = get_drive_service()
    
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=query, spaces='drive', fields='files(id)', supportsAllDrives=True, includeItemsFromAllDrives=True
    ).execute()
    
    files = results.get('files', [])
    if not files:
        raise FileNotFoundError(f"File '{filename}' not found in Google Drive folder '{folder_id}'")
        
    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        
    fh.seek(0)
    return pd.read_parquet(fh)
