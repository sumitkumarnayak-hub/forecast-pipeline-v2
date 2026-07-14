---
title: Planning Suite API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Demand Planning & Forecasting Suite (Monorepo)

A production-grade web application for forecasting pipelines, manual baseline operations, auto-pilot synchronization, and new product/hub launches. 

Built using a **Next.js (React)** frontend with vanilla CSS/Tailwind styling and a modular **FastAPI (Python)** backend, this suite serves as a high-performance system integrating supabased databases and cached Google Sheets worksheets.

---

## 1. Project Directory Layout

```
forecast-pipeline-v2/
├── backend/               # FastAPI Backend Service
│   ├── app/               # FastAPI Configuration & Bootstrapping
│   │   ├── main.py        # App initialization, middleware, routes mounting
│   │   ├── config.py      # App configurations, worksheets mappings, path resolver
│   │   ├── dependencies.py# JWT auth decoders & role check dependencies
│   │   └── middleware.py  # Request id tracing & HttpOnly cookies parser
│   ├── core/              # Platform Infrastructure (Domain-Agnostic Modules)
│   │   ├── database/      # SQL base engines & models.py (SQLAlchemy schema)
│   │   ├── security/      # JWT handlers & role permission maps
│   │   ├── storage/       # Cloud sync factory (Local, Google Drive, Supabase Bucket)
│   │   └── shared/        # Sheets manager, sheets Parquet cache, SMTP email module
│   ├── features/          # Self-Contained Business Domains (Route Controllers & Logic)
│   │   ├── auth/          # Login authentication handlers
│   │   ├── product_launch/# Product launch wizard, sheet_reads cache, watcher service
│   │   ├── autopilot/     # 6-step autopilot runner, logs, & live stream (SSE)
│   │   ├── baseline/      # Manual raw data pull, configs, approval statuses
│   │   ├── dashboard/     # Week analytics & KPI dashboard engine
│   │   ├── final_plan/    # Festive/adhoc synchronizers & final planning exports
│   │   ├── validation/    # Pandera validation schemes on files
│   │   ├── settings/      # Admin bootstrap configurations, users preferences, recipients
│   │   ├── insights/      # Revenue availability loss reports
│   │   └── master_data/   # Master Excel updates, snapshoting & syncs
│   ├── scripts/           # DevOps and verification runners
│   └── run_backend.py     # Main Uvicorn development server script
│
└── frontend/              # Next.js Frontend Client (React)
    ├── src/
    │   ├── app/           # Next.js App Router (dashboard, baseline, new-product-launch...)
    │   ├── components/    # Page-specific panels, NPL tables, forms
    │   ├── hooks/         # Client context state hooks (useAuth, useToast)
    │   └── lib/           # Axios networking layer & client calls
    ├── package.json       # Node package descriptors
    └── postcss.config.js  # Tailwind CSS configurator
```

---

## 2. Environment Variables Configuration

Configure the environment variables in a local file at `backend/.env`. Below is the complete, verified list of variables required:

```ini
# --- Core Deployment Environment ---
APP_ENV=development                       # Set to 'production' or 'prod' in server environments
AUTH_SECRET_KEY=dev-insecure-auth-key     # Generate a 64-char hex string in production
CORS_ORIGINS=http://localhost:3000        # Comma-separated client browser domains

# --- Authentication & Session Options ---
AUTH_COOKIE_NAME=ps_auth                  # Session HttpOnly cookie name (defaults to 'ps_auth')
AUTH_COOKIE_DAYS=7.0                      # Cookie lifetime token expiration in days

# --- Database Storage Fallbacks ---
# Omit DATABASE_URL to fall back to local sqlite database 'forecasting_db.sqlite'
DATABASE_URL=postgresql://postgres:password@localhost:5432/postgres?sslmode=require

# --- Caching, Snapshots, & Google Drive Sync ---
# Options: 'local' (files stay on disk) | 'drive' (sync from Google Drive folder) | 'supabase'
STORAGE_BACKEND=local
PIPELINE_DRIVE_FOLDER_URL=https://drive.google.com/drive/folders/<FOLDER_ID_ON_DRIVE>
GOOGLE_CREDENTIALS_PATH=credentials/google-service-account.json # Impersonation certificate path
GOOGLE_CREDENTIALS_JSON=                  # Minified raw JSON credentials on a single line (Production/HF)

# --- SMTP Email Notifications Configuration ---
FROM_EMAIL=alert-sender@example.com       # Sender email address
FROM_EMAIL_APP_PASSWORD=abcd-efgh-ijkl   # Application-specific password
# Alternative naming:
SMTP_USER=alert-sender@example.com
SMTP_PASSWORD=abcd-efgh-ijkl

# --- Google Sheets Spreadsheet URL Targets ---
HUB_LEVEL_PLANNING_SHEET_URL=https://docs.google.com/spreadsheets/d/...
NEW_HUB_LAUNCH_SHEET_URL=https://docs.google.com/spreadsheets/d/...
DEMAND_PLANNING_MASTERS_SHEET_URL=https://docs.google.com/spreadsheets/d/...
CLUSTER_MASTER_SHEET_URL=https://docs.google.com/spreadsheets/d/...
AVAILABILITY_LOSS_SHEET_URL=https://docs.google.com/spreadsheets/d/...
DP_LOGICS_SHEET_URL=https://docs.google.com/spreadsheets/d/...
VALIDATION_SHEET_URL=https://docs.google.com/spreadsheets/d/...
EA_TRACKER_SHEET_URL=https://docs.google.com/spreadsheets/d/...
INVENTORY_BUFFER_SHEET_URL=https://docs.google.com/spreadsheets/d/...
NEW_PRODUCT_LAUNCH_SHEET_URL=             # Optional override
PIPELINE_PARAMS_SHEET_URL=                # Optional override
```

---

## 3. Quickstart Guide

### 1. Launch the Backend API Service

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Build your local Python virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\Activate
   # macOS/Linux:
   source venv/bin/activate
   ```
3. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Verify the setup and start the development server:
   ```bash
   python run_backend.py
   ```
   The backend API will start on **http://localhost:8000** (reload enabled, watching directories: `app`, `core`, `features`). Swagger UI is visible at **http://localhost:8000/docs**.

---

### 2. Launch the Next.js Frontend

1. Open a new terminal and navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install node dependencies:
   ```bash
   npm install
   ```
3. Start the Next.js client development server:
   ```bash
   npm run dev
   ```
   Open **http://localhost:3000** in your browser.
