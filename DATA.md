# Data Schema, Mappings & Caching Specifications

This document describes the database schema, sheets mapping configurations, caching policies, and row diff synchronization algorithms of the Forecasting Pipeline system.

---

## 1. Database Schema (SQLAlchemy Definitions)

All relational database structures are constructed via SQLAlchemy ORM models mapped in [`core/database/models.py`](file:///c:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/core/database/models.py). The tables support PostgreSQL (Supabase) in production and fall back to SQLite in local environments.

### SQLAlchemy Model Table Schemas

#### 1. `users`
Represents system user profiles and authorization roles.
- `id` (Integer, Primary Key, autoincrement=True)
- `password_hash` (String, nullable=False)
- `full_name` (String)
- `email` (String, unique=True, nullable=False)
- `role` (String, nullable=False) — `admin`, `planner`, `product`, or `viewer`
- `is_active` (Boolean, default=True, nullable=False)
- `created_at` (DateTime, server_default=func.now())
- `last_login` (DateTime)

#### 2. `user_preferences`
Holds customizable user UI configurations.
- `user_id` (Integer, ForeignKey("users.id"), Primary Key)
- `email_notifications` (Boolean, default=True)
- `auto_sync_masters` (Boolean, default=False)
- `preview_rows` (Integer, default=100)
- `updated_at` (DateTime)

#### 3. `auth_sessions`
Audit log of active users and client environment fingerprints.
- `session_id` (String, Primary Key)
- `user_id` (Integer, ForeignKey("users.id"), nullable=False)
- `expires_at` (DateTime, nullable=False)
- `created_at` (DateTime, server_default=func.now())
- `system_details` (String) — Minified JSON string containing client metadata (OS, Browser, IP, location coordinates)

#### 4. `baseline_runs` & `final_plan_runs` - [UNUSED / RESERVED]
Main audit tables logging historical executions of baseline forecasting engines. (These structures are not active in this scoped release).
- `id` (Integer, Primary Key, autoincrement=True)
- `run_id` (String, unique=True, nullable=False)
- `run_name` (String)
- `run_date` (DateTime, server_default=func.now())
- `user_id` (Integer, ForeignKey("users.id"))
- `baseline_run_id` (String, ForeignKey("baseline_runs.run_id")) # Used in final_plan_runs only
- `status` (String) — `success` or `failed`
- `raw_data_file` (String) — Reference path to input parquet/RDS file
- `output_file` (String) — Reference path to generated forecast output
- `summary_stats` (String) — JSON containing error margins, aggregate SKU metrics, or baseline volumes
- `validation_status` (String) — `Pending`, `Approved`, or `Rejected`
- `approved_by` (Integer, references users.id)
- `approved_at` (DateTime)

#### 5. `pipeline_runs`, `pipeline_step_logs`, `pipeline_run_log_lines` - [UNUSED / RESERVED]
Main tables tracking the Auto-Pilot step transitions and stdout stream logs. (These structures are not active in this scoped release).
- `pipeline_runs`: Holds the overarching execution state of the 6-step flow.
  - Fields: `id`, `run_id` (unique), `user_id`, `status`, `current_step`, `started_at`, `completed_at`, `summary_stats`, `session_id`
- `pipeline_step_logs`: Step-specific metrics (e.g. `master_sync` or `run_engine` status, error_detail, logged_at).
- `pipeline_run_log_lines`: Real-time line-by-line log output generated during a run.

#### 6. `npl_submissions`
Audit log of New Product Launch wizard applications.
- `id` (Integer, Primary Key, autoincrement=True)
- `submission_id` (String, unique=True, nullable=False, index=True)
- `sub_type` (String) — `New Launch`, `Expansion`, or `Replacement`
- `product_id` (String)
- `product_name` (String)
- `category` (String)
- `cities` (String) — Comma-separated list of target cities
- `hub_count` (Integer)
- `city_count` (Integer)
- `start_date` (String) — Target launch launch-date
- `status` (String, default="Pending") — `Pending`, `Approved`, `Rejected`, or `Voided`
- `rejection_reason` (String)
- `submitted_by` (String)
- `user_id` (Integer, ForeignKey("users.id"))
- `step_log` (Text) — JSON tracking wizard timing metadata

---

## 2. Google Sheets Mapping Configurations

The system reads and updates Google Sheets using credentials from `GOOGLE_CREDENTIALS_PATH`. Below is the exact configuration maps defined in `app.config.SHEETS_CONFIG`:

* **`hub_level_planning`** (Target URL variable: `HUB_LEVEL_PLANNING_SHEET_URL`)
  * `Avl_Flag` ➔ Availability override flags
  * `Hub_Changes` ➔ Parameters and remappings
  * `City_Cat` ➔ Outliers classifications
  * `City_drops` ➔ Historic drops and volumes exclusions
  * `Percentile` ➔ Availability percentile margins
  * `Hub Sku Master` ➔ Cluster allocations
  * `SellThroughFactor` ➔ Weekly sell-through factors
  * `Hub level Suggestion` ➔ Baseline output engine suggestions
* **`new_hub_launch`** (Target URL variable: `NEW_HUB_LAUNCH_SHEET_URL`)
  * `New Hub launch` ➔ Hub parameters mappings
  * `FF Input` ➔ Active forecasting input table (A:H)
* **`demand_planning_masters`** (Target URL variable: `DEMAND_PLANNING_MASTERS_SHEET_URL`)
  * `P Master` ➔ Product Master list (cols A:K)
  * `P-H Master` ➔ Product-Hub Master mappings (A:AX)
  * `Hub Mapping` ➔ Hub metadata (A:F)
  * `P-L Master` ➔ Product-Location relationships
* **`cluster_master`** (Target URL variable: `CLUSTER_MASTER_SHEET_URL`)
  * `Cluster phase 2` ➔ Cluster phase mappings
* **`availability_loss`** (Target URL variable: `AVAILABILITY_LOSS_SHEET_URL`)
  * `Avail Led Rev Loss` ➔ Revenue availability reports

---

## 3. Caching Architecture & TTL Settings

To optimize performance and circumvent API quota limit breakages, the system operates a strict caching hierarchy:

1. **Short-Term TTL API Cache (`core/shared/api_cache.py`)**:
   An in-memory dictionary-based Cache that stores REST responses (e.g. settings bootstrap payloads or catalog logs) with a short TTL (usually 25s - 60s) to prevent query flooding on simultaneous dashboard loads.
2. **Local Parquet Cache (`core/shared/sheets_cache.py`)**:
   Master data sheets are pulled from Google Sheets, parsed into pandas DataFrames, and stored as compressed binary Parquet files under `data/outputs/sheets_cache/`. These cache files default to a TTL of **600 seconds**.
3. **Database Write Queue (`WriteQueue`)**:
   To prevent request locks, write operations to Google Sheets are queued inside the `write_queue` database table and flushed asynchronously by the background task scheduler.

---

## 4. Change Tracking & Multi-Set Row Diff Engine

In features like Product Launch, the backend watcher [`features/product_launch/watcher.py`](file:///c:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/backend/features/product_launch/watcher.py) runs a diff detection loop on the Google Sheet `ff_input` tab. 

When comparing the local cached parquet dataset against the fresh Google Sheet version:
* It reads the entire worksheet range `A:H`.
* Each row is serialized and hashed using data values (e.g. segment names, city names, product identifiers, and forecast weeks) to construct a **row signature**.
* **New Rows** are identified as row signatures present in the sheet but missing in the cache.
* **Deleted Rows** are signatures present in the cache but missing in the sheet.
* **Modified Rows** are caught by comparing row values sharing matching primary signatures (detecting changes in numeric volumes or dates).
* **Positional Index Mapping**: To safely manage duplicate rows (e.g. two identical rows submitted accidentally), the diff engine tracks the exact Google Sheets row indices. When deleting a specific row, the API invokes standard spreadsheet row deletions using the exact positional indices, ensuring only the target copy is deleted.
* **Log Persistency**: Diff actions are audited in `submission_actions_log` and registered in the NPL submission logs.
