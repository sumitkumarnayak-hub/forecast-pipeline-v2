import io
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from core.shared.google_credentials import load_service_account_credentials

logger = logging.getLogger(__name__)

# Global dictionary to hold progress for the festive upload tasks
UPLOAD_PROGRESS = {}

FESTIVE_DRIVE_FOLDER_ID = "17mYoNPGhmhw4MlZoE24gWG2onA9WmFya"
SCOPES = ['https://www.googleapis.com/auth/drive']

def upload_parquet_to_drive_bg(task_id: str, parquet_bytes: bytes, filename: str):
    """
    Background task to upload parquet file to Google Drive.
    Updates the UPLOAD_PROGRESS dictionary with real-time percentage.
    """
    UPLOAD_PROGRESS[task_id] = {"progress": 0, "status": "processing", "error": None}
    
    try:
        creds = load_service_account_credentials(SCOPES)
        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': filename,
            'parents': [FESTIVE_DRIVE_FOLDER_ID]
        }

        fh = io.BytesIO(parquet_bytes)
        
        media = MediaIoBaseUpload(
            fh, 
            mimetype='application/vnd.apache.parquet', 
            chunksize=20 * 1024 * 1024, # 20 MB chunks for faster upload
            resumable=True
        )

        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress_val = int(status.progress() * 100)
                UPLOAD_PROGRESS[task_id]["progress"] = progress_val
                logger.info("Upload %s progress: %d%%", task_id, progress_val)

        UPLOAD_PROGRESS[task_id] = {
            "progress": 100,
            "status": "completed",
            "file_id": response.get('id'),
            "error": None
        }
        logger.info("Upload %s completed. File ID: %s", task_id, response.get('id'))

    except Exception as exc:
        logger.exception("Festive upload %s failed", task_id)
        UPLOAD_PROGRESS[task_id] = {
            "progress": 0,
            "status": "error",
            "error": str(exc)
        }
