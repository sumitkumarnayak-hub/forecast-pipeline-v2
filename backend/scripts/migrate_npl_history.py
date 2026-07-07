import sys
import os
import json
import logging
from pathlib import Path

# Add backend/src to path so we can import planning_suite
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir / "src"))

from planning_suite import config as cfg
from planning_suite.services.google_sheets import GoogleSheetsManager
from planning_suite.db.engine import Database

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("migrate_npl")

def migrate_submissions():
    logger.info("Connecting to Database...")
    db = Database()
    
    logger.info("Fetching Google Sheets data...")
    gsm = GoogleSheetsManager()
    
    try:
        df = gsm.read_worksheet(cfg.HUB_LEVEL_PLANNING_SHEET_URL, "Submission_Log")
    except Exception as e:
        logger.error(f"Failed to read Submission_Log from Sheets: {e}")
        return

    if df is None or df.empty:
        logger.info("Submission_Log is empty. Nothing to migrate.")
        return

    logger.info(f"Found {len(df)} submissions in Sheets. Migrating to Supabase...")
    
    success = 0
    errors = 0
    
    # Process oldest first if we want, or just iterate (it uses ON CONFLICT DO NOTHING)
    for idx, row in df.iterrows():
        try:
            sub_id = str(row.get("Submission_ID") or "")
            if not sub_id or sub_id.lower() == "nan":
                continue
                
            sub_type = str(row.get("Submission_Type") or "New Launch")
            pid = str(row.get("Product ID") or "")
            pname = str(row.get("Product Name") or "")
            category = str(row.get("Category") or "")
            cities_str = str(row.get("Cities") or "")
            cities = [c.strip() for c in cities_str.split(",") if c.strip()]
            
            hub_count = 0
            try:
                hub_count = int(row.get("Hub_Count") or 0)
            except ValueError:
                pass
                
            start_date = str(row.get("Start Date") or "")
            status = str(row.get("Status") or "Pending")
            reason = str(row.get("Rejection_Reason") or "")
            submitted_by = str(row.get("Submitted_By") or "")
            
            # Save to DB
            db.save_npl_submission(
                submission_id=sub_id,
                sub_type=sub_type,
                product_id=pid if pid.lower() != "nan" else "",
                product_name=pname if pname.lower() != "nan" else "",
                category=category if category.lower() != "nan" else "",
                cities=cities,
                hub_count=hub_count,
                start_date=start_date if start_date.lower() != "nan" else "",
                submitted_by=submitted_by if submitted_by.lower() != "nan" else "",
                step_log={"migrated": True}
            )
            
            if status.lower() != "pending":
                db.update_npl_submission_status(sub_id, status, reason)
                
            success += 1
        except Exception as e:
            logger.error(f"Failed to migrate row {idx}: {e}")
            errors += 1
            
    logger.info(f"Migration complete: {success} successful, {errors} errors.")

if __name__ == "__main__":
    migrate_submissions()
