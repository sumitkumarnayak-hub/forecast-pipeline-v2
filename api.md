# Workspace API Usage Directory

This document details all API endpoints defined in the backend routing configuration (`backend/app/main.py` and its feature routers). It classifies them based on whether they are actively used in the targeted frontend deployment (focusing only on **Product Launch**, **Hub Launch**, and **Settings**), or whether they are unused and redundant.

---

## 🟢 Used APIs (Actively Called in Selected Features)

These endpoints must be kept intact in the backend deployment as the frontend targets them.

### 🔑 Authentication (`/api/auth`)
*   `POST /api/auth/login` — Authenticates user credentials.
*   `GET /api/auth/me` — Fetches active session profile.
*   `POST /api/auth/logout` — Destroys current session cookie/tokens.

### ⚙️ Settings (`/api/settings`)
*   `GET /api/settings/bootstrap` — Warm up configurations (user details, env variables, log lists).
*   `POST /api/settings/preferences` — Updates visual UI parameters (e.g. preview row sizes).
*   `POST /api/settings/session/system-details` — Saves client environment diagnostics for system logs.
*   `GET /api/settings/email-recipients` — Lists target notification emails.
*   `POST /api/settings/email-recipients` — Creates new email recipients.
*   `DELETE /api/settings/email-recipients/{recipient_id}` — Deletes email recipient records.
*   `PATCH /api/settings/email-recipients/{recipient_id}` — Edits email recipient preferences.
*   `POST /api/settings/test-email` — Dispatches test SMTP mail logs.
*   `GET /api/settings/users` — Queries credential user list.
*   `POST /api/settings/users` — Registers new workspace user.
*   `PATCH /api/settings/users/{user_id}` — Modifies profile data or triggers user state switches (active/suspended).
*   `POST /api/settings/users/{user_id}/reset-password` — Sets a new password for target user.

### 🚀 New Product Launch & Hub Launch (`/api/new-product-launch`)
*   `GET /api/new-product-launch/info` — Retrieves linked Google Sheet URLs.
*   `GET /api/new-product-launch/bootstrap` — Context parameters (cities, categories, product database, launch limits).
*   `GET /api/new-product-launch/masters/products` — Type-ahead autocomplete query interface for products.
*   **Wizard Split & Parse Flows:**
    *   `GET /api/new-product-launch/wizard/hubs` — Pulls hub structures for planning city selection.
    *   `POST /api/new-product-launch/wizard/template/city` — Exports empty city plan template file.
    *   `POST /api/new-product-launch/wizard/template/hub` — Exports empty hub plan template file.
    *   `POST /api/new-product-launch/wizard/parse-city` — Upload target to parse city layout parameters.
    *   `POST /api/new-product-launch/wizard/parse-hub` — Upload target to parse hub layout parameters.
    *   `POST /api/new-product-launch/wizard/check-duplicates` — Matches plans against log submissions to avoid overlaps.
    *   `POST /api/new-product-launch/wizard/preview-sync` — Previews data rows before committing.
    *   `POST /api/new-product-launch/wizard/submit` — Commits launch plan to sheets/database.
*   **Submission Administration & Logs:**
    *   `GET /api/new-product-launch/submissions/log` — Fetches submission grid layout summaries and status filters.
    *   `PATCH /api/new-product-launch/submissions/{submission_id}/status` — Changes status (Approve/Reject).
    *   `GET /api/new-product-launch/submissions/{submission_id}/rows` — Detail viewer for specific launches.
    *   `DELETE /api/new-product-launch/submissions/{submission_id}/rows` — Rollback deletion target.
    *   `PUT /api/new-product-launch/submissions/{submission_id}/notes` — Saves user notes against the log.
*   **Hub Launch (Cloning & Sync Mappings):**
    *   `GET /api/new-product-launch/sync-new-hub/hub-mapping` — Accesses mapping workspace.
    *   `POST /api/new-product-launch/sync-new-hub/hub-mapping/append` — Appends to hub sheet logic.
    *   `GET /api/new-product-launch/sync-new-hub/hub-sku-master` — Reads SKU rules.
    *   `POST /api/new-product-launch/sync-new-hub/hub-sku-master/append` — Appends to SKU rules.
    *   `POST /api/new-product-launch/sync-new-hub/ff-input/append` — Adds record to sync queue.
    *   `GET /api/new-product-launch/sync-new-hub/ff-input` — Reads pending changes state.
    *   `GET /api/new-product-launch/sync-new-hub/change-status` — Identifies staging changes size.
    *   `GET /api/new-product-launch/sync-new-hub/last-update` — Checks timestamps.
    *   `GET /api/new-product-launch/sync-new-hub/preview` — Returns the mapping generation preview.
    *   `POST /api/new-product-launch/sync-new-hub/confirm` — Commits staging modifications.
    *   `POST /api/new-product-launch/sync-new-hub/dismiss-changes` — Clears mapping playground buffer.

---

## 🔴 Unused APIs (Redundant for the Targeted Deployment)

These endpoints are completely unused in the target deployment and can be safely deleted or excluded to save compute resources and reduce code footprint.

### 📊 Dashboard (`/api/dashboard`)
*   `GET /api/dashboard/bootstrap`
*   `GET /api/dashboard/pipeline-card`
*   `GET /api/dashboard/weeks`
*   `GET /api/dashboard/analytics`
*   `GET /api/dashboard/revenue-trends`
*   `GET /api/dashboard/pipeline-flow`
*   `POST /api/dashboard/pipeline-flow/run`
*   `GET /api/dashboard/baseline-runs`
*   `GET /api/dashboard/final-plan-runs`
*   `GET /api/dashboard/email-log`

### 🏗️ Master Data (`/api/master-data`)
*   `GET /api/master-data/p-master`
*   `GET /api/master-data/ph-master`
*   `GET /api/master-data/hub-master`
*   `GET /api/master-data/inventory-buffer`
*   `POST /api/master-data/sync-inventory-excel`
*   `POST /api/master-data/preview-ph-sync`
*   `POST /api/master-data/confirm-ph-sync`
*   `GET /api/master-data/snapshot-runs`
*   `POST /api/master-data/restore-snapshot`
*   `GET /api/master-data/sync-history`
*   `GET /api/master-data/legacy-sync-types`
*   `POST /api/master-data/sync-legacy/{master_type}`
*   `POST /api/master-data/sync`
*   `GET /api/master-data/hub-changes`
*   `POST /api/master-data/hub-changes`
*   `POST /api/master-data/new-hub-sync/preview`
*   `POST /api/master-data/new-hub-sync/confirm`
*   `GET /api/master-data/users`

### 📉 Baseline (`/api/baseline`)
*   `GET /api/baseline/status` (Triggered as layout-wide pre-check in sidebar, but has no functional impact on NPL or Settings)
*   `GET /api/baseline/raw-data/status`
*   `GET /api/baseline/raw-data/status/details`
*   `POST /api/baseline/raw-data/dates`
*   `POST /api/baseline/raw-data/fetch`
*   `GET /api/baseline/raw-data/bulk-plan`
*   `POST /api/baseline/raw-data/bulk-pull`
*   `POST /api/baseline/raw-data/load-weeks`
*   `GET /api/baseline/params`
*   `POST /api/baseline/params`
*   `POST /api/baseline/sync-dp-logics`
*   `GET /api/baseline/generate/context`
*   `GET /api/baseline/generate/preflight`
*   `POST /api/baseline/generate/fetch-previous-baseline`
*   `POST /api/baseline/generate/run`
*   `GET /api/baseline/review/latest-summary`
*   `GET /api/baseline/review/comparison`
*   `GET /api/baseline/review/hub-sku-comparison`
*   `GET /api/baseline/approve/hub-suggestion`
*   `GET /api/baseline/runs`
*   `POST /api/baseline/approve`
*   `POST /api/baseline/reject`
*   `GET /api/baseline/config`

### ✈️ Auto-Pilot (`/api/autopilot`)
*   `GET /api/autopilot/bootstrap`
*   `GET /api/autopilot/bootstrap/static`
*   `GET /api/autopilot/manual-sync`
*   `GET /api/autopilot/history`
*   `GET /api/autopilot/runs/{run_id}/log`
*   `GET /api/autopilot/runs/{run_id}`
*   `POST /api/autopilot/run`
*   `GET /api/autopilot/state`
*   `GET /api/autopilot/output-paths`
*   `GET /api/autopilot/stream/{run_id}`
*   `GET /api/autopilot/status/{task_id}`

### 📝 Final Plan (`/api/final-plan`)
*   `GET /api/final-plan/bootstrap`
*   `GET /api/final-plan/status`
*   `GET /api/final-plan/inputs-status`
*   `GET /api/final-plan/city-mapping`
*   `POST /api/final-plan/sync-city-mapping`
*   `POST /api/final-plan/sync-festive`
*   `POST /api/final-plan/upload-input`
*   `GET /api/final-plan/runs`
*   `POST /api/final-plan/sync-adhoc`
*   `POST /api/final-plan/sync-inventory`
*   `GET /api/final-plan/config`
*   `POST /api/final-plan/run`
*   `GET /api/final-plan/latest-output`
*   `GET /api/final-plan/hub-suggestions`
*   `POST /api/final-plan/sync-inv-buffer`

### 🔍 Validation (`/api/validation`)
*   `GET /api/validation/bootstrap`
*   `GET /api/validation/logics`
*   `POST /api/validation/validate-input`
*   `POST /api/validation/validate-master`
*   `POST /api/validation/validate-baseline-output`
*   `GET /api/validation/validate-latest/baseline`
*   `GET /api/validation/validate-latest/final-plan`
*   `GET /api/validation/history`
*   `DELETE /api/validation/history`
*   `GET /api/validation/validation-logs`

### 👁️ Insights & Analytics (`/api/insights`)
*   `GET /api/insights/bootstrap`
*   `GET /api/insights/view`
*   `GET /api/insights/availability-loss`
*   `GET /api/insights/6w-summary`
*   `GET /api/insights/executive-summary`
*   `GET /api/insights/reports/baseline-summary`
*   `GET /api/insights/reports/plan-comparison`
*   `GET /api/insights/reports/actual-vs-plan`
*   `GET /api/insights/reports/city-revenue-trends`
*   `GET /api/insights/reports/downloads`
*   `GET /api/insights/reports/baseline-runs`
*   `GET /api/insights/reports/final-plan-runs`

### 🧪 Hidden/Deactivated Product Launch Flows (`/api/new-product-launch`)
These endpoints exist on the Product Launch router but are not mapped or called in the selected frontend UI:
*   `POST /api/new-product-launch/sync-ph/preview` — Unused sync check.
*   `POST /api/new-product-launch/sync-ph/confirm` — Unused sync confirm.
*   `POST /api/new-product-launch/auto-sync` — Auto sync trigger.
