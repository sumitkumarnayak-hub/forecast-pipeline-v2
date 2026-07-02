# Data Sources

Where Planning Suite v2 reads and writes data. Use this when deploying to cloud (Render/Vercel) or debugging stale UI.

## Database (PostgreSQL / SQLite)

| Table | Purpose |
|-------|---------|
| `users` | Login accounts, roles, `is_active` flag |
| `user_preferences` | Per-user email/sync/preview settings |
| `baseline_runs`, `final_plan_runs`, `pipeline_runs` | Run history and approval audit |
| `auth_sessions` | Persistent login sessions |
| `email_notification_recipients`, `email_log` | SMTP notification config and send log |
| `master_sync_log` | Master data sync history |

**Local dev:** SQLite file `forecasting_db.sqlite` when `DATABASE_URL` is unset.  
**Production:** Set `DATABASE_URL` to Supabase/Render Postgres.

## Google Sheets (live masters & NPL)

Service account JSON via `GOOGLE_CREDENTIALS_PATH`.

| Sheet key (config) | Worksheets | Used by |
|--------------------|------------|---------|
| `CLUSTER_MASTER_SHEET_KEY` | P-L Master | Product Launch wizard (product catalog) |
| `HUB_LEVEL_PLANNING_SHEET_KEY` | Submission_Log, Hub level Suggestion, Launch_Output | NPL submissions, salience, outputs |
| Demand planning masters URL | P Master, P-H Master, Hub Mapping, … | Master Data sync, Auto-Pilot step 1–2 |
| DP Logics sheet URL | City_Cat, STF, Percentile, Avl_Flag, … | Baseline engine config sync |
| Validation sheet URL | Validation tabs | Post-baseline validation |

**Caching:** Sheet grids are cached to parquet under `outputs/sheets_cache/` (`sheets_cache.py`). NPL reads (`load_product_master`, `load_log`, `load_salience_source`) use `npl_sheet_reads.py`. TTLs are env-tunable (`SHEETS_CACHE_TTL_*`). API responses also use in-process `api_cache` (e.g. NPL wizard context, 90s submission log).

**Warm-up:** On backend start, a background thread pre-loads NPL sheets unless `DISABLE_CACHE_WARMUP=true`.

## Local files & mounted drive

Paths from `backend/.env` (`PLANNING_DRIVE_ROOT`, `RAW_ACTUALS_FOLDER`, `DP_LOGICS_FOLDER`, etc.).

| Asset | Typical path | Notes |
|-------|--------------|-------|
| Product_Masters.xlsx | `FF_MASTERS_XLSX` | Written by master sync / Auto-Pilot step 1 |
| Raw actuals | `RAW_ACTUALS_FOLDER` | Weekly CSV/RData pull (step 3) |
| `active_dataset.parquet` | `outputs/active_dataset.parquet` | Active baseline input dataset |
| DP Logics Excel copies | `DP_LOGICS_FOLDER` | Synced from Sheets (step 4) |
| Baseline outputs | `BASELINE_OUTPUTS_FOLDER` | Engine output Excel/parquet |
| 6w rolling | `outputs/6w_v3.parquet` | Dashboard / insights aggregates |
| Hub suggestion parquet | `hub_suggestion_latest.parquet` | NPL city→hub split |

**Cloud deploy:** Ephemeral disk on Render is lost on redeploy. Either mount persistent storage (Render disk, S3, shared drive) or rely on Sheets + RDS paths configured in env. See `OPS_RUNBOOK.md`.

## Submission history (Product Launch)

Submission History in the UI is **not** from SQLite or browser storage. It comes from the **`Submission_Log`** worksheet in the Hub Level Planning Google Sheet, via `GET /api/new-product-launch/submission-log` (summary/detail views, server cache).

## What is not a data source

- `sessionStorage` / SWR on the frontend — UI cache only (NPL bootstrap, settings bootstrap).
- React duplicate-key fixes — presentation layer only; underlying IDs still come from Sheets.

## Invalidation

| Action | Cache cleared |
|--------|----------------|
| NPL submit / status change | `Submission_Log` parquet + `NPL_WIZARD` api_cache |
| Master data sync | `MASTER_SHEET` api_cache + relevant sheet parquets |
| Baseline approve/reject | Baseline-related api_cache namespaces |
