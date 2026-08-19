# Workspace API Usage Directory

This document details all active API endpoints defined in the FastAPI backend routers (`backend/app/main.py` and its domain feature routers). It serves as the authoritative, up-to-date catalog of REST API endpoints supported by the Demand Planning & Forecasting workbench.

---

## 🔑 Authentication (`/api/auth`)
* `POST /api/auth/login` — Authenticates user credentials and sets HttpOnly session token.
* `GET /api/auth/me` — Fetches profile & role metadata for the active session.
* `POST /api/auth/logout` — Destroys active session and clears auth cookies.

---

## ⚡ Pipeline Execution & External Automation (`/api/pipeline`)
* `GET /api/pipeline/runs` — Fetches history of 3-step pipeline executions (GitHub Actions, Airflow, CLI, or Portal UI).
* `GET /api/pipeline/runs/{run_id}/log` — Retrieves detailed console output stream and step statuses for a specific run.
* `POST /api/pipeline/run` — Triggers the 3-step pipeline execution (`raw_data_6w.py` → `baseline_parquet.py` → `ff_hub_automation.py`) on demand or via external webhooks.

---

## 📊 Dashboard & Analytics (`/api/dashboard`)
* `GET /api/dashboard/bootstrap` — Initializes dashboard filters, week metadata, and cached metrics.
* `GET /api/dashboard/summary` — Fetches high-level executive summary KPIs (revenue, baseline volume, forecast delta).
* `GET /api/dashboard/filters` — Provides available city/hub/category filter options.
* `GET /api/dashboard/charts` — Generates chart datasets for revenue trends, inventory buffer heatmaps, and category breakdowns.
* `GET /api/dashboard/forecast-runs` — Lists recent baseline and final plan run summaries.

---

## 📈 Baseline Generation & Management (`/api/baseline`)
* `GET /api/baseline/status` — Checks active dataset availability and overall baseline engine state.
* `GET /api/baseline/raw-data/status` — Inspects step 1 raw RDS data status and loaded date ranges.
* `POST /api/baseline/raw-data/dates` — Sets start and end date parameters for raw data extraction.
* `POST /api/baseline/raw-data/fetch` — Executes raw RDS data fetch and saves parquet snapshot.
* `GET /api/baseline/configure/params` — Reads DP logic parameters and percentiles.
* `POST /api/baseline/configure/params` — Saves updated DP logic configuration parameters.
* `GET /api/baseline/generate/context` — Provides pre-run baseline context and summary file lists.
* `GET /api/baseline/generate/preflight` — Runs preflight validation checks prior to baseline calculation.
* `POST /api/baseline/generate/run` — Runs the baseline engine and generates Summary Excel files.
* `GET /api/baseline/review/latest-summary` — Previews output rows from the latest baseline summary file.
* `GET /api/baseline/review/comparison` — Compares current baseline summary against previous runs.
* `GET /api/baseline/review/hub-sku-comparison` — Performs granular Hub-SKU level baseline comparison.
* `POST /api/baseline/review/approve-hub-suggestion` — Approves hub baseline suggestions.
* `GET /api/baseline/runs` — Lists historical baseline runs with status and output file references.
* `POST /api/baseline/runs/{run_id}/approve` — Marks a baseline run as approved.
* `POST /api/baseline/runs/{run_id}/reject` — Rejects a baseline run with reason.
* `POST /api/baseline/festive-upload` — Uploads festive override files (CSV/Excel) to Google Drive in background.
* `GET /api/baseline/festive-upload/status/{task_id}` — Polls status of async festive upload background tasks.

---

## 📋 Final Plan Consensus & Distribution (`/api/final-plan`)
* `GET /api/final-plan/status` — Checks final plan prerequisite statuses and input files.
* `GET /api/final-plan/inputs-status` — Validates required input files (Adhoc adjustments, inventory logic).
* `GET /api/final-plan/city-mapping` — Previews city mapping layouts for hub distribution.
* `POST /api/final-plan/sync-city-mapping` — Syncs city mapping changes to remote storage.
* `POST /api/final-plan/sync-festive` — Syncs festive placeholders from Google Sheets.
* `POST /api/final-plan/upload-input` — Uploads custom final plan input overrides.
* `GET /api/final-plan/runs` — Retrieves historical final plan run records.
* `POST /api/final-plan/sync-adhoc` — Pulls adhoc adjustment sheet updates.
* `POST /api/final-plan/sync-inventory` — Pulls inventory buffer logic sheet updates.
* `GET /api/final-plan/config` — Provides final plan execution configuration.
* `POST /api/final-plan/run` — Executes the Final Plan Engine and generates distribution output files.
* `GET /api/final-plan/latest-output` — Previews rows from the latest generated final plan Excel workbook.
* `GET /api/final-plan/hub-suggestions` — Loads hub allocation suggestions and overrides.
* `POST /api/final-plan/sync-inv-buffer` — Syncs inventory buffer rules.

---

## 🚀 New Product Launch & Hub Launch (`/api/new-product-launch`)
* `GET /api/new-product-launch/info` — Retrieves linked Google Sheet URLs.
* `GET /api/new-product-launch/bootstrap` — Provides wizard context (cities, categories, product catalog).
* `GET /api/new-product-launch/masters/products` — Type-ahead product search autocomplete.
* `GET /api/new-product-launch/wizard/hubs` — Pulls active hub structures for city selections.
* `POST /api/new-product-launch/wizard/template/city` — Exports empty city launch plan template.
* `POST /api/new-product-launch/wizard/template/hub` — Exports empty hub launch plan template.
* `POST /api/new-product-launch/wizard/parse-city` — Upload target to parse city launch plans.
* `POST /api/new-product-launch/wizard/parse-hub` — Upload target to parse hub launch plans.
* `POST /api/new-product-launch/wizard/check-duplicates` — Validates plans against existing submissions.
* `POST /api/new-product-launch/wizard/preview-sync` — Previews launch rows before committing.
* `POST /api/new-product-launch/wizard/submit` — Commits launch plan to sheets and database.
* `GET /api/new-product-launch/submissions/log` — Fetches submission grid layout summaries and status filters.
* `PATCH /api/new-product-launch/submissions/{submission_id}/status` — Updates submission status (Approve/Reject).
* `GET /api/new-product-launch/submissions/{submission_id}/rows` — Fetches detailed launch rows for a submission.
* `DELETE /api/new-product-launch/submissions/{submission_id}/rows` — Deletes or voids submission records.
* `PUT /api/new-product-launch/submissions/{submission_id}/notes` — Saves planner notes on submission records.
* **Hub Launch & Mapping:**
  * `GET /api/new-product-launch/sync-new-hub/hub-mapping` — Accesses Hub Mapping configuration.
  * `POST /api/new-product-launch/sync-new-hub/hub-mapping/append` — Appends validated row to Hub Mapping sheet.
  * `POST /api/new-product-launch/sync-new-hub/ff-input/append` — Appends row to FF Input sheet.
  * `GET /api/new-product-launch/sync-new-hub/ff-input` — Reads raw FF Input sheet rows.
  * `GET /api/new-product-launch/sync-new-hub/change-status` — Returns sheet diff status.
  * `GET /api/new-product-launch/sync-new-hub/last-update` — Returns timestamp of last detected sheet change.
  * `GET /api/new-product-launch/sync-new-hub/preview` — Generates hub launch preview dataset.
  * `POST /api/new-product-launch/sync-new-hub/confirm` — Commits hub cloning actions to master sheets.
  * `POST /api/new-product-launch/sync-new-hub/dismiss-changes` — Clears change notification alerts.

---

## 📄 Base Sheets Management (`/api/base-sheets`)
* `GET /api/base-sheets/bootstrap` — Loads configuration for embedded base sheets tabs.
* `GET /api/base-sheets/files` — Lists synced parquet sidecars and sheet cache files.
* `POST /api/base-sheets/sync` — Forces sync of master sheets to local parquet cache.
* `POST /api/base-sheets/upload` — Uploads custom base sheet Excel files.

---

## 📁 Master Data Management (`/api/master-data`)
* `GET /api/master-data/bootstrap` — Loads master data configuration context.
* `GET /api/master-data/sheet-url` — Fetches Google Sheet URL for demand planning masters.
* `GET /api/master-data/demand-masters` — Reads P Master, P-H Master, and P-L Master tables.
* `POST /api/master-data/sync-single-dp-logic` — Forces sync of a specific DP logic sheet tab.
* `POST /api/master-data/sync-dp-logics` — Forces bulk sync of all DP logic master sheets.

---

## 🔍 Output & Data Validation (`/api/validation`)
* `GET /api/validation/bootstrap` — Preloads validation rules and sheet metadata.
* `GET /api/validation/logics` — Lists active validation schemes and rules.
* `POST /api/validation/validate-input` — Validates uploaded input files against Pandera schemas.
* `POST /api/validation/validate-master` — Validates master data sheet structures.
* `POST /api/validation/validate-baseline-output` — Runs Pandera validation on baseline summary files.
* `GET /api/validation/validate-latest/baseline` — Runs validation on latest generated baseline file.
* `GET /api/validation/validate-latest/final-plan` — Runs validation on latest generated final plan file.
* `GET /api/validation/history` — Fetches historical validation run logs.
* `DELETE /api/validation/history` — Clears validation run log history.
* `GET /api/validation/validation-logs` — Reads system validation error log messages.

---

## 👁️ Insights & Executive Analytics (`/api/insights`)
* `GET /api/insights/bootstrap` — Preloads analytics configuration and dataset options.
* `GET /api/insights/view` — Renders main analytics insight charts.
* `GET /api/insights/availability-loss` — Calculates availability loss and revenue impacts.
* `GET /api/insights/6w-summary` — Computes 6-week aggregate revenue and volume metrics.
* `GET /api/insights/executive-summary` — Generates high-level executive report summaries.
* `GET /api/insights/reports/baseline-summary` — Generates baseline volume summary report.
* `GET /api/insights/reports/plan-comparison` — Generates baseline vs final plan comparison report.
* `GET /api/insights/reports/actual-vs-plan` — Computes actual sales vs plan delta report.
* `GET /api/insights/reports/city-revenue-trends` — Computes city-wise revenue trend aggregations.
* `GET /api/insights/reports/downloads` — Generates exportable analytics Excel workbooks.

---

## ⚙️ System Settings & Administration (`/api/settings`)
* `GET /api/settings/bootstrap` — Loads initial admin system details and environment flags.
* `GET /api/settings/env-status` — Returns environment configuration health.
* `GET /api/settings/queue/status` — Polls background queue worker status and job counts.
* `GET /api/settings/preferences` — Reads planner UI display preferences.
* `POST /api/settings/preferences` — Saves updated planner UI display preferences.
* `GET /api/settings/session` — Fetches current user auth session details.
* `POST /api/settings/session/system-details` — Saves client browser diagnostics for security audit logs.
* `GET /api/settings/email-recipients` — Lists configured email notification recipients.
* `POST /api/settings/email-recipients` — Adds new email notification recipient.
* `DELETE /api/settings/email-recipients/{recipient_id}` — Removes an email notification recipient.
* `PATCH /api/settings/email-recipients/{recipient_id}` — Updates email recipient preferences.
* `GET /api/settings/email-log` — Reads history of sent email notification outcomes.
* `POST /api/settings/test-email` — Sends test notification email via configured SMTP.
* `GET /api/settings/users` — Lists workspace user accounts.
* `POST /api/settings/users` — Creates a new workspace user account.
* `PATCH /api/settings/users/{user_id}` — Updates user role, full name, or active status.
* `POST /api/settings/users/{user_id}/reset-password` — Resets password for a user account.
* `GET /api/settings/storage/status` — Checks Google Drive / cloud storage backend status.
* `POST /api/settings/storage/pull` — Triggers manual pull of startup artifacts from Google Drive.

---

## 🧪 Demo Filter API (`/api/demo-filter`)
* `GET /api/demo-filter` — Fetches active city/hub demo scope filters for the user.
* `POST /api/demo-filter` — Sets demo city/hub scope filter.
* `DELETE /api/demo-filter` — Clears active demo scope filter.
