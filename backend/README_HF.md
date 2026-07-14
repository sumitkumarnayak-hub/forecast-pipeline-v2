---
title: Planning Suite API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Deployed FastAPI Backend on Hugging Face Spaces (Docker SDK)

This directory contains the Docker configurations, entrypoint parameters, and settings mapping required to deploy the FastAPI forecasting API to Hugging Face Spaces.

---

## 1. Spaces Configurations & Environment Variables

Add these environment variables as **Variables** or **Secrets** under your Space's **Settings ➔ Variables and Secrets** panel:

| Name | Key Type | Notes / Description |
|------|----------|---------------------|
| `APP_ENV` | Variable | Set to `production` or `prod` |
| `AUTH_SECRET_KEY` | Secret | *Generate a strong 64-character hex string* |
| `DATABASE_URL` | Secret | Supabase Postgres URI connection string with `?sslmode=require` |
| `GOOGLE_CREDENTIALS_JSON` | Secret | The minified Google Sheet service-account JSON block |
| `STORAGE_BACKEND` | Variable | Set to `drive` |
| `PIPELINE_DRIVE_FOLDER_URL` | Variable | Google Drive folder URL holding Parquet caches & database backups |
| `CORS_ORIGINS` | Variable | Vercel Client Frontend domain URL |
| All `*_SHEET_URL` vars | Variable / Secret | The exact spreadsheet URLs mapped in the root config |

---

## 2. Stateless Sync Lifecycle

Hugging Face containers are ephemeral and reboot on space restarts, resetting the local disk. By defining `STORAGE_BACKEND=drive` and configuring `PIPELINE_DRIVE_FOLDER_URL`:
1. **Container Start (`docker-entrypoint.sh`)**: The container executes the sync utility [`core/storage/sync.py`](file:///c:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/core/storage/sync.py) at startup to download:
   - `outputs/rds_cache.parquet`
   - `analytics/6w_v3.rds`
   - `masters/Product_Masters.xlsx`
   - `outputs/active_dataset.parquet`
   - `outputs/active_dataset_meta.json`
   - `forecasting_db.sqlite` (if no PostgreSQL DATABASE_URL is set)
2. **Autopilot Execution**: Prior to executing the autopilot forecasting run, the backend runs `sync_before_pipeline()` to pull fresh files. After execution completes, it runs `sync_after_pipeline()` to push newly generated baseline and final plan files back to Google Drive.
3. **Database Backups**: If using the local SQLite database fallback, database sync runs backup copies directly to Google Drive.

---

## 3. Local Preparation Runbook (Seeding the Drive Cache)

If setting up the Space for the first time, you must initialize the Google Drive directory structure:
1. Configure your local `.env` file in `backend/` with `STORAGE_BACKEND=drive` and the target `PIPELINE_DRIVE_FOLDER_URL`.
2. Run the seed CLI script:
   ```bash
   python scripts/push_pipeline_storage.py
   ```
3. Check the Google Drive folder to ensure that `6w_v3.rds` and all essential cached parquet files are uploaded.
4. Restart your Hugging Face space.
