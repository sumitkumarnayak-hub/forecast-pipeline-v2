# Planning Suite API (FastAPI)

FastAPI backend for the Demand Planning & Forecasting Suite. All business logic lives in `src/planning_suite/` — copied unchanged from the original Streamlit codebase. The `app/` layer is a thin REST + SSE wrapper only.

## Quick start

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
python run_backend.py
```

The API listens on **http://localhost:8000** by default. Swagger UI: **http://localhost:8000/docs**

### Environment

Place `.env` and Google service-account JSON in `backend/` (same layout as the Streamlit repo). Key variables are loaded via `planning_suite.config`.

| Variable | Purpose |
|----------|---------|
| `AUTH_SECRET_KEY` | JWT signing secret (change in production) |
| `AUTH_COOKIE_DAYS` | Token expiry when "remember me" is checked (default 7) |
| `DATABASE_URL` | Supabase PostgreSQL URL; omit for SQLite fallback |
| `GOOGLE_CREDENTIALS_PATH` | Path to Google Sheets service account JSON |
| `PLANNING_DRIVE_ROOT` | Mounted drive root for 6w CSV / baseline files |
| `RDS_6W_PATH` | Path to `.RData` for 6-week rolling cache build |

---

## Authentication

All routes except `/api/health` and `POST /api/auth/login` require a Bearer token.

```
Authorization: Bearer <jwt>
```

JWT payload fields: `sub` (user id), `username`, `role`, `full_name`, `email`, `exp`.

### Roles & permissions

Mirrors `planning_suite.core.permissions`:

| Role | Read | Write | Approve | Pages |
|------|------|-------|---------|-------|
| `admin` | ✓ | ✓ | ✓ | All |
| `planner` | ✓ | ✓ | ✗ | All except admin-only settings |
| `viewer` | ✓ | ✗ | ✗ | Dashboard, Master Data, Analytics, Settings |

Dependency helpers in `app/deps.py`:

- `get_current_user` — any authenticated user
- `require_write` — admin or planner (403 otherwise)
- `require_approve` — admin only
- `require_admin` — admin only

---

## API reference

Base URL: `/api`

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness — process up. |
| `GET` | `/health/ready` | None | Readiness — database connectivity check (use for load balancers). |

---

### Auth — `/api/auth`

| Method | Path | Auth | Body / params | Response | Notes |
|--------|------|------|---------------|----------|-------|
| `POST` | `/login` | None | `{ username, password, remember_me? }` | `{ token, user }` | Authenticates against DB; updates `last_login`; loads user preferences. |
| `GET` | `/me` | Bearer | — | User record + `preferences` | Full DB user by token `sub`. |
| `POST` | `/logout` | Bearer | — | `{ detail }` | Stateless — client discards token. |

---

### Dashboard — `/api/dashboard`

Maps to Streamlit **Dashboard** page (`display_dashboard_page` + `render_pipeline_dashboard_card`).

| Method | Path | Auth | Query | Response | Notes |
|--------|------|------|-------|----------|-------|
| `GET` | `/pipeline-card` | Bearer | — | `{ has_run, run_name, status }` | Last Auto-Pilot run summary for dashboard card. |
| `GET` | `/weeks` | Bearer | — | `{ weeks[], default_week }` | ISO week labels from 6w rolling data. |
| `GET` | `/analytics` | Bearer | `week` (optional) | Full week analytics payload | KPIs, delta tables, inventory buffer, new hubs/products. Same logic as Streamlit dashboard. |
| `GET` | `/pipeline-flow` | Bearer | — | `{ steps[], latest_run }` | Live evaluation of 7 pipeline steps (no DB write). |
| `POST` | `/pipeline-flow/run` | Bearer (write) | — | `{ run_id, detail }` | Full pipeline audit; persists run to DB. |
| `GET` | `/baseline-runs` | Bearer | `limit=10` | Baseline run rows | Recent runs from `baseline_runs` table. |
| `GET` | `/final-plan-runs` | Bearer | `limit=10` | Final plan run rows | Recent runs from `final_plan_runs` table. |
| `GET` | `/email-log` | Bearer | `limit=20` | Email log rows | Recent notifications from `email_log`. |

**Services:** `planning_suite.services.analytics_6w` (data loading), `planning_suite.services.dashboard_analytics` (week aggregations).

---

### Auto-Pilot — `/api/autopilot`

Maps to Streamlit **Auto-Pilot** page (`optimized_baseline.display_autopilot_page`).

| Method | Path | Auth | Query / body | Response | Notes |
|--------|------|------|--------------|----------|-------|
| `GET` | `/manual-sync` | Bearer | `refresh?` | Detect manual workflow progress; suggests `from_step`. Cached 25s. |
| `POST` | `/run` | Write | `from_step=0` | `{ task_id }` | Starts 6-step pipeline in a background thread. |
| `GET` | `/status/{task_id}` | Bearer | — | Task object | Poll task `{ status, steps[], error }`. |
| `GET` | `/stream/{task_id}` | None* | — | SSE stream | Real-time step events: `{ event: "step"|"completed"|"failed", ... }`. |
| `GET` | `/state` | Bearer | — | JSON | Contents of `outputs/autopilot_state.json`. |
| `GET` | `/output-paths` | Bearer | — | Path config | Env-derived folders and sheet URL for UI panel. |

\* SSE endpoint does not validate JWT today; task IDs are UUIDs. Frontend passes token via separate status polling.

**Steps (in order):** master_sync → new_product_launch → pull_raw_data → sync_config → run_engine → notify.

Step labels and descriptions are defined once in `planning_suite/automation/autopilot_ui_config.py` (shared by runner + UI).

---

### Baseline (manual workflow) — `/api/baseline`

Maps to Streamlit manual steps **1–5** (load raw data through approve baseline). REST endpoints cover status, runs, approve/reject, config, and step-specific operations via the baseline router.

| Method | Path | Auth | Response | Notes |
|--------|------|------|----------|-------|
| `GET` | `/status` | Bearer | `{ approved, latest_run }` | Uses `pipeline_state.is_baseline_approved()`. |
| `GET` | `/runs` | Bearer | Run list | `limit=20`; includes approver name. |
| `POST` | `/approve` | Approve | `{ detail }` | Unlocks Final Plan. |
| `POST` | `/reject` | Approve | `{ detail }` | Revokes approval state. |
| `GET` | `/config` | Bearer | Path config | Masters XLSX, raw actuals, DP logics, outputs folder, params sheet URL. |

Additional step endpoints (raw data pull, params sync, engine run, review tables) are exposed on the same router — see `/docs` for the full list.

---

### Master Data — `/api/master-data`

Maps to Streamlit **Master Data** page tabs.

| Method | Path | Auth | Body | Notes |
|--------|------|------|------|-------|
| `GET` | `/p-master` | Bearer | — | Read Product Master sheet (cols A:K). |
| `GET` | `/ph-master` | Bearer | — | Read P-H Master sheet (A:AX). |
| `GET` | `/hub-master` | Bearer | — | Read Hub Mapping sheet (A:F). |
| `GET` | `/inventory-buffer` | Bearer | — | All tabs from inventory logic Google Sheet. |
| `POST` | `/sync-inventory-excel` | Write | — | Sync inventory sheet tabs → local Excel files. |
| `POST` | `/preview-ph-sync` | Write | `{ product_ids: string[] }` | Preview new-product P-H rows before write. |
| `POST` | `/confirm-ph-sync` | Write | `{ rows_to_add, ph_headers, product_ids }` | Append rows to P-H Master sheet. |
| `GET` | `/snapshot-runs` | Bearer | — | List successful `master_sync` sync runs for rollback. |
| `POST` | `/restore-snapshot` | Write | `{ run_id }` | Restore master snapshots to Google Sheets. |
| `GET` | `/sync-history` | Bearer | `limit=20` | Master sync log with user names. |
| `POST` | `/sync` | Write | — | Trigger `run_master_data_sync()`. |
| `GET` | `/hub-changes` | Bearer | — | Load editable Hub Changes dataframe. |
| `POST` | `/hub-changes` | Write | `{ rows: object[] }` | Save Hub Changes back to sheet. |
| `GET` | `/users` | Admin | — | List all users (includes `is_active`). Legacy — prefer `/api/settings/users`. |

---

### Final Plan — `/api/final-plan`

Maps to Streamlit **Final Plan** page (unlocked after baseline approval).

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| `GET` | `/status` | Bearer | `{ baseline_approved, latest_run }` |
| `GET` | `/runs` | Bearer | `limit=20` — final plan run history |
| `POST` | `/sync-adhoc` | Write | Sync adhoc adjustments sheet → Excel |
| `POST` | `/sync-inventory` | Write | Sync inventory buffer sheet → Excel |
| `GET` | `/config` | Bearer | FF inputs / inv logic folder paths |

Hub suggestions, mapping load, upload, and run-engine triggers are on this router — see Swagger `/docs`.

---

### Product Launch — `/api/new-product-launch`

Maps to Streamlit **Product Launch** page (wizard, sync, submission history).

| Method | Path | Auth | Body | Notes |
|--------|------|------|------|-------|
| `GET` | `/context` | Bearer | — | Wizard bootstrap (categories, cities, masters) — cached |
| `GET` | `/submission-log` | Bearer | `view=summary\|detail`, `submission_id?` | Submission_Log sheet (grouped summary or hub detail) |
| `PATCH` | `/submissions/{id}/status` | Write/Approve | `{ status, reason? }` | Approve/reject/withdraw |
| `POST` | `/upload` | Write | multipart `file` (.xlsx) | Validates via `validate_npl_upload()` |

NPL Google Sheet reads use parquet cache (`npl_sheet_reads.py`); warm-up runs on API startup. See `DATA_SOURCES.md`.

---

### Insights / Analytics — `/api/insights`

Maps to Streamlit **Analytics → Insights** and dashboard 6w data.

| Method | Path | Auth | Query | Notes |
|--------|------|------|-------|-------|
| `GET` | `/availability-loss` | Bearer | `limit=500` | Avail Led Rev Loss worksheet. |
| `GET` | `/6w-summary` | Bearer | — | Lightweight parquet sample from `outputs/6w_v3.parquet`. |

Full dashboard aggregates are served from `/api/dashboard/analytics`.

---

### Validation — `/api/validation`

Maps to Streamlit **Validation** page.

| Method | Path | Auth | Body | Notes |
|--------|------|------|------|-------|
| `POST` | `/validate-baseline-output` | Write | multipart Excel | Pandera validation of baseline Summary file. |
| `GET` | `/validation-logs` | Bearer | `limit=20` | Failed/warning rows from `master_sync_log`. |

---

### Settings — `/api/settings`

Maps to Streamlit **Settings** page.

| Method | Path | Auth | Body | Notes |
|--------|------|------|------|-------|
| `GET` | `/bootstrap` | Bearer | — | Profile, prefs, env, email recipients (admin), session |
| `GET` | `/env-status` | Bearer | — | Redacted env summary |
| `GET` | `/preferences` | Bearer | — | User preferences from DB. |
| `POST` | `/preferences` | Bearer | `{ email_notifications?, auto_sync_masters?, preview_rows? }` | Update preferences. |
| `GET` | `/users` | Admin | — | List users (`is_active`, roles). |
| `POST` | `/users` | Admin | `{ username, password, full_name?, email?, role }` | Create user. |
| `PATCH` | `/users/{user_id}` | Admin | `{ full_name?, email?, role?, is_active? }` | Update / deactivate. |
| `POST` | `/users/{user_id}/reset-password` | Admin | `{ password }` | Reset password. |
| `GET` | `/email-recipients` | Admin | — | Notification recipient list. |
| `POST` | `/email-recipients` | Admin | `{ email, display_name?, category, enabled? }` | Add recipient. |
| `DELETE` | `/email-recipients/{recipient_id}` | Admin | — | Remove recipient. |
| `POST` | `/test-email` | Admin | `{ recipient_id?, to_email?, message? }` | Send test email. |

Inactive users cannot log in (`users.is_active = false`).

---

## Server-Sent Events (Auto-Pilot)

Subscribe after `POST /api/autopilot/run`:

```
GET /api/autopilot/stream/{task_id}
Accept: text/event-stream
```

Event payloads (JSON in `data:` lines):

```json
{ "event": "step", "index": 0, "key": "master_sync", "label": "...", "status": "running", "message": "...", "error": "" }
{ "event": "completed" }
{ "event": "failed", "error": "..." }
```

Frontend should also poll `GET /api/autopilot/status/{task_id}` as a fallback.

---

## Project layout

```
backend/
├── app/
│   ├── main.py          # FastAPI app, CORS, router registration
│   ├── deps.py          # JWT auth dependencies
│   └── routers/         # One file per domain (thin wrappers)
├── src/planning_suite/  # Original business logic (DO NOT change behavior)
├── scripts/             # CLI runners (autopilot, baseline engine)
├── migrations/          # Supabase SQL
├── run_backend.py       # uvicorn entry point
└── requirements.txt
```

### Adding a new endpoint

1. Implement or reuse logic in `src/planning_suite/services/` or `automation/` — **no Streamlit imports**.
2. Add a route in the appropriate `app/routers/*.py` file.
3. Use `Depends(get_current_user)` / `require_write` / `require_approve` as needed.
4. Document the route in this README and in `MIGRATION.md` if it closes a UI parity gap.

---

## Error responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid JWT |
| `403` | Authenticated but insufficient role |
| `404` | Resource not found (e.g. autopilot task) |
| `422` | Validation failed (file upload / Pandera) |
| `500` | Unhandled server error; `detail` contains message |

---

## Related docs

- Root `README.md` — monorepo quick start
- `MIGRATION.md` — Streamlit → Next.js parity checklist (**complete**)
- `DATA_SOURCES.md` — Sheets vs DB vs local files
- `PRODUCT_GAPS.md` — remaining optional gaps
- `OPS_RUNBOOK.md` — production operations
