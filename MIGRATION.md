# Streamlit → Next.js Migration Plan

**Source:** `forecast-pipeline-new-codebase` (Streamlit)  
**Target:** `forecast-pipeline-v2` (Next.js + FastAPI monorepo)

## Rules

1. **Zero business-logic drift** — `backend/src/planning_suite/` must behave identically to the Streamlit codebase.
2. **UI parity per phase** — each phase audits Streamlit controls (buttons, tabs, filters, tables, charts) and reproduces them in Next.js calling new or existing REST endpoints.
3. **One sidebar page = one phase** (manual baseline steps 1–5 are grouped as Phase 3).

---

## Navigation map

| Phase | Streamlit page | Next.js route | Status |
|-------|----------------|---------------|--------|
| 1 | Dashboard | `/dashboard` | Done (6w analytics + pipeline card) |
| 2 | Auto-Pilot | `/autopilot` | Done |
| 3 | 1. Load Raw Data → 5. Approve Baseline | `/baseline/*` (5 step routes) | Done |
| 4 | Master Data | `/master-data` | Done |
| 5 | Product Launch | `/new-product-launch` | Done |
| 6 | Final Plan | `/final-plan` | Done |
| 7 | Analytics (Insights + Reports) | `/analytics` | Done |
| 8 | Validation | `/validation` | Done |
| 9 | Settings | `/settings` | Mostly done |
| — | Sidebar demo filter (admin) | Sidebar component | Not started |

---

## Phase 1 — Dashboard

**Streamlit:** `reporting.py` → `display_dashboard_page` + `pipeline_flow.render_pipeline_dashboard_card`

### UI inventory (Streamlit)

| Control | Purpose |
|---------|---------|
| Welcome strip | User name + role |
| Pipeline card | Last autopilot run name, status, **Open** → Auto-Pilot |
| Week selectbox | Choose ISO week from 6w data |
| Week badge | Selected range + vs previous week warning |
| KPI metrics (×5) | Plan qty, plan rev, cities, hubs, SKUs |
| Tabs: City×Date / City×Category×Date | Plan/baseline delta % heat tables |
| Inventory buffer table | r7_inv vs r7_plan by city×category |
| New hub/product section | Tabs: By Product / By City / By Category (when prev week exists) |
| Filters | Cities, categories, days multiselect |
| View mode radio | Table vs chart for revenue trends |
| WoW radio | Week-over-week comparison view |

### Next.js current state

- Welcome strip, pipeline card with Open → `/autopilot`
- Week selector, KPI row, delta tables (City×Date, City×Category×Date)
- Inventory buffer heatmap, new hubs/products section
- APIs: `/pipeline-card`, `/weeks`, `/analytics`

### Backend work needed

- ~~Port `services/analytics_6w.py`~~ Done
- ~~Add dashboard analytics endpoints~~ Done

---

## Phase 2 — Auto-Pilot

**Streamlit:** `optimized_baseline.display_autopilot_page` + `autopilot_runner.py`

### UI inventory

| Control | Purpose |
|---------|---------|
| 6 step cards | Status per autopilot step |
| **Run from step** selector | Resume from step N |
| **Run Auto-Pilot** button | Start pipeline |
| Progress / log output | Step messages, errors |
| Output paths panel | Env folder paths + sheet link |
| Last run state | From `autopilot_state.json` |
| Read-only mode | Viewers cannot run |

### Next.js current state

- Steps list, SSE streaming, from-step selector, paths panel, last state
- Failed-step banner with deep-link to manual workflow page
- Manual workflow tab with all 6 step links
- Per-step output path reference during runs

### Gaps

- ~~Link to manual baseline steps after failure~~ Done (`autopilotManualLinks.ts`)
- Minor: verify step callback messages match Streamlit verbatim in edge cases

---

## Phase 3 — Manual Baseline (steps 1–5)

**Streamlit:** Five separate sidebar pages in `optimized_baseline.py`

### 3a — Load Raw Data

| Control | Purpose |
|---------|---------|
| Also save CSV checkbox | Optional CSV alongside parquet |
| Use cached week checkbox | Skip fetch if cache valid |
| **Fetch Raw Data** | Single-week pull |
| **Pull All 10 Weeks & Save** | Bulk historical pull |
| Multiselect weeks + **Load Selected Weeks** | Load cached weeks into session |
| Data preview dataframe | After load |
| **Continue to 2. Configure Parameters →** | Nav button |

### 3b — Configure Parameters

| Tab: Configuration Masters | |
| **Sync All & Save as Excel** | Download DP logics workbooks |
| **Fetch Previous Baseline** | Load prior summary for comparison |
| **Continue →** | Nav to step 3 |

### 3c — Generate Baseline

| Control | Purpose |
|---------|---------|
| Pre-run validation messages | Block run if inputs missing |
| **Run Baseline & Save Summary** | Execute `optimized_baseline_avail_correction.py` |
| Output preview | Summary stats after run |
| **Continue →** | Nav to step 4 |

### 3d — Review & Validate

| Control | Purpose |
|---------|---------|
| **Load Comparison** | Current vs previous baseline |
| Comparison tabs | Multiple review views (city, hub, SKU filters) |
| Validation results | Pandera / business rules |
| **Continue →** | Nav to step 5 |

### 3e — Approve Baseline

| Control | Purpose |
|---------|---------|
| **Load / Refresh** | Reload approval dataframe |
| City / SKU class filters | Narrow approval view |
| **Approve Baseline** / **Reject** | Admin approve actions |
| **Revoke Approval** | Undo approval |
| **Continue → Final Plan** | Nav when approved |

### Next.js current state

- Five step routes under `/baseline/*` with `BaselineStepShell` continue footers
- Generate: pre-run validation checklist (`/api/baseline/generate/preflight`)
- Configure: Fetch Previous Baseline + DP Logics sync
- Review: Pandera validate-latest + master validation buttons
- Wave A/B APIs: comparison tabs, bulk pull, hub suggestion, fetch-previous

### Backend work needed

- ~~Endpoints wrapping each manual baseline action~~ Done

---

## Phase 4 — Master Data

**Streamlit:** `master_data.py` → `display_master_data_page`

### Tabs

1. **Sync History** — log table, refresh, snapshot rollback (select run, confirm checkbox, restore)
2. **Masters** — P Master, P-H Master, Hub Master sub-tabs with load, filters, download
3. **P-H Sync** — product ID input, preview, confirm write, new hub sync flow
4. **Hub Changes** — editable grid, save
5. **Inventory Buffer** — tab per worksheet, preview, sync to Excel
6. **Legacy sync** — per-master sync buttons

### Next.js current state

- P / P-H / Hub tabs with filters, CSV download, P-H product sync preview
- Hub Changes editor + **New Hub Launch Sync** preview/confirm (`/api/master-data/new-hub-sync/*`)
- Inventory buffer preview + sync, sync history + snapshot rollback

---

## Phase 5 — Product Launch

**Streamlit:** `new_product_launch_page.py`

### UI inventory

| Tab | Controls |
|-----|----------|
| Plan | Radio sub-pages, upload, validation display |
| Sync | Dry run checkbox, **Run New Product Sync** |
| Automation | Autopilot-related launch sync |

### Next.js current state

- 4-stage wizard for New Launch, Expansion (product picker), Replacement (old/new SKU setup)
- Per-city hub multiselect, duplicate check, email notification status on submit
- Sync P-H + Auto-sync tabs, submission history with SLA

---

## Phase 6 — Final Plan

**Streamlit:** `final_plan.py` (locked until baseline approved)

### Tabs: Inputs / Run / Output

| Control | Purpose |
|---------|---------|
| Load hub suggestions | Sheet preview |
| Load city mapping | Sheet preview |
| Sync adhoc / inventory / inv buffer | Sheet → Excel |
| File uploader | Manual input override |
| **Run Final Plan** | Execute final plan engine |
| Output preview | Hub_Dist results |

### Next.js current state

- **Done:** Bootstrap API, inputs checklist, city mapping preview/sync, festive template, manual Excel upload, pre-run validation, run log, hub suggestions + output preview

---

## Phase 7 — Analytics

**Streamlit:** `analytics.py` → Insights + Reports sections

### Insights (`insights.py`)

- Week + city multiselect, view radio
- Many sub-tabs: loss trends, RCA, pareto, OA/UA, concentration, category deep-dive, warehouse views
- Sliders for top-N, thresholds

### Reports (`reporting.display_reporting_page`)

- Report selectbox: Baseline Summary, Plan Comparison, Actual vs Plan, City Revenue Trends, Run History, Download Reports

### Next.js current state

- **Done:** Insights with week/city filters, 5 views (Executive, Revenue Loss, OA/UA, Wastage, Hub Health 360) and all Streamlit sub-tabs via `/api/insights/view`
- Reports: Baseline Summary, Plan Comparison, Actual vs Plan (aggregated), City Revenue Trends (recharts), Run History, Downloads

---

## Phase 8 — Validation

**Streamlit:** `validation.py`

### Tabs

- Input validation (upload CSV/XLSX, run)
- Master validation (select master, validate)
- Output validation (validate latest Summary / Hub_Dist on disk)
- Validation history

### Next.js current state

- **Done:** Four Streamlit tabs — Input (CSV/XLSX upload + Pandera), Master (selectable sheets + P-H Polars rules), Output (latest on disk + upload), History (server session per user)
- Single `GET /api/validation/bootstrap` with 120s client cache

---

## Phase 9 — Settings

**Streamlit:** `settings.py`

### Tabs

- Profile, Preferences (email notifications, auto sync masters, preview rows)
- Email Settings (test send, recipients CRUD)
- Session, About (system details save)

### Next.js current state

- Preferences, env status, email recipients — mostly done
- Missing: test email, system details, session tab

---

## Sidebar extras

| Feature | Streamlit | Next.js |
|---------|-----------|---------|
| Role-based nav | `allowed_pages()` | `Sidebar.tsx` roles array |
| Final Plan lock | Hidden until baseline approved | Lock icon on nav item |
| Demo city filter (admin) | City selectbox + hub multiselect + badge | Not implemented |
| Manual baseline caption | "follow steps 1 → 5" | Not shown |
| Sign out | Auth manager panel | Sign Out button |

---

## How to execute a phase

1. Open the Streamlit page in `forecast-pipeline-new-codebase` and list every interactive element.
2. Check `backend/app/routers/` for an existing endpoint; if missing, add a thin wrapper around `planning_suite` logic.
3. Update the matching `frontend/src/app/<route>/page.tsx`.
4. Update `backend/README.md` and this file's status column.
5. Manual test: same inputs → same outputs as Streamlit.

---

## Suggested order

Phases **1 → 2 → 3** are the critical path (dashboard analytics, autopilot polish, full manual baseline). Phases **4–9** can proceed in parallel once APIs exist.
