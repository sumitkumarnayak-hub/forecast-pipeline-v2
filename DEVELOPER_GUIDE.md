# Developer Guidelines & Style Standards

This document establishes the patterns, code conventions, styling policies, and testing workflows required for developers working on the monorepo codebase.

---

## 1. Backend Development Standards

### Writing Clean, Feature-Centric REST APIs
1. **Domain Isolation**: Maintain domain boundary separation under `backend/features/<feature_name>/`.
2. **Controller Decoupling**: Keep routers thin. Validate parameters using Pydantic schemas, delegate calculations to service layers, and inject dependencies using FastAPI `Depends(...)`.
3. **Database Sessions**: Always utilize injected dependencies to retrieve database sessions:
   ```python
   @router.get("/status")
   def get_status(db: Database = Depends(get_db)):
       # db context manager handles SQLAlchemy sessions automatically
   ```
4. **Exception Handling**: Raise `HTTPException` with explicit status codes. Keep descriptive messages, ensuring frontend clients can parse the error JSON (`{"detail": "..."}`).

---

## 2. Frontend Development & Aesthetic Rules

To build a premium visual experience, the frontend client matches modern UI/UX design standards:

### Vanilla CSS Styling Rules

1. **Do Not Use Plain Primary Colors**: Do not use ad-hoc bright red, primary blue, or flat green. Implement custom-tuned HSL palettes:
   - **Main Background**: Deep slate blue HSL: `hsl(224, 71%, 4%)`
   - **Cards Background**: Semi-transparent slate HSL: `hsla(222, 47%, 11%, 0.75)`
   - **Primary Action Tint**: Vivid Indigo HSL: `hsl(263.4, 70%, 50.4%)`
   - **System Accent Gray**: Slate HSL: `hsl(215.4, 16.3%, 56.9%)`
2. **Glassmorphism Backdrop Filters**: Enhance card layouts and modals using blur filters and fine borders:
   ```css
   background: rgba(15, 23, 42, 0.75);
   backdrop-filter: blur(8px);
   border: 1px solid rgba(255, 255, 255, 0.08);
   box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
   ```
3. **Smooth Micro-Transitions**: All active states, buttons, dropdown triggers, and card hover effects must utilize ease transitions:
   ```css
   transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
   ```

### Navigation Keys & Tab Management
* Flatten tab navigations where possible (promoting nested sub-tabs directly to the top-level page).
* Maintain the active tab key in the browser state.
* Use custom hooks (`useAuth`, `useParams`) to isolate data fetching from layout rendering.

---

## 3. Testing & Verification Runbook

### Running Integration & Feature Tests

1. **Verify Python Compilation**:
   Before committing backend changes, run compilation checks:
   ```bash
   python -m py_compile app/main.py
   ```
2. **Execute REST API Integration workbench**:
   Run the endpoints test workbench:
   ```bash
   python scripts/test_api_endpoints.py
   ```
   This script spins up a standard FastAPI `TestClient`, mocks remote Google Sheets connections, and verifies request/response payloads for:
   - **/api/health** & **/api/validation/logics** (Auth verification)
   - **/api/new-product-launch/wizard/context** (Product launch context maps)
   - **/api/master-data/new-hub-sync/confirm** (Hub launch sync triggers)

---

## 4. API Reference Manual

Requests from the Client Browser are intercepted by the Next.js API route handlers acting as a BFF (Backend-For-Frontend) proxy before being forwarded to the FastAPI backend microservice.

### Next.js BFF Proxy API Routes
All routes under `/api/*` (except specific local email routes) are handled dynamically by:
* **Proxy Handler (`frontend/src/app/api/[...path]/route.ts`)**:
  * **Type**: Next.js Node.js Edge Route (Proxy forwarding).
  * **Method**: `GET` | `POST` | `PUT` | `PATCH` | `DELETE`
  * **Purpose**: Rewrites request host header, forwards tokens, and maps the cookie domain from `ps_auth` to client domain to bypass browser SameSite/Secure locks in proxy environments.
* **Email Sender (`POST /api/send-email`)**:
  * **Type**: Next.js Serverless Route.
  * **Payload**: `{ "to": "email@example.com", "subject": "Alert", "html": "HTML String", "secret": "AUTH_SECRET_KEY" }`
  * **Response**: `{ "ok": true, "messageId": "msg-id" }`
  * **Purpose**: Dispatches SMTP alert emails directly from the frontend node runtime.

---

### FastAPI Backend REST API Endpoints
FastAPI maps endpoints under self-contained directories in `backend/features/`:

#### 1. Authentication Feature (`features/auth/`)
* **`POST /api/auth/login`**:
  * **Parameters**: Body: `{ "username": "user", "password": "pwd", "remember_me": true }`
  * **Returns**: `{ "token": "JWT_STRING", "user": { "id": 1, "username": "...", "role": "admin" } }`
  * **Purpose**: Verifies login, constructs JWT, and writes a Secure HttpOnly cookie `ps_auth` to the client.
* **`GET /api/auth/me`**:
  * **Parameters**: None (reads JWT cookie).
  * **Returns**: User details dictionary + preferences.
  * **Purpose**: Returns the logged-in user profile structure.
* **`POST /api/auth/logout`**:
  * **Parameters**: None.
  * **Returns**: `{ "detail": "Logged out successfully" }` (Sets cookie max-age to 0).

#### 2. Product Launch Feature (`features/product_launch/`)
* **`GET /api/new-product-launch/wizard/context`**:
  * **Parameters**: None (Requires Auth).
  * **Returns**: `{ "categories": ["Groceries", "Beverages"], "cities": ["Mumbai", "Delhi"], "earliest_launch_date": "YYYY-MM-DD" }`
  * **Purpose**: Bootstrap categories and active cities dropdowns in the launch wizard UI.
* **`POST /api/new-product-launch/upload`**:
  * **Parameters**: Multipart file upload (`file: UploadFile`).
  * **Returns**: `{ "success": true, "submission_id": "SUB-UUID", "rows_added": 12 }`
  * **Purpose**: Validates upload Excel format structure, triggers Pandera validations, and returns success logs.
* **`GET /api/new-product-launch/submissions/{id}/rows`**:
  * **Parameters**: Path parameter `id` (Submission ID key).
  * **Returns**: `{ "rows": SheetRow[], "columns": ["Submission ID", "SKU Name", "City", "Week", ...] }`
  * **Purpose**: Loads active worksheet rows from `Submission_Log` matching the selected ID.
* **`DELETE /api/new-product-launch/submissions/{id}/rows`**:
  * **Parameters**: Path parameter `id`, and JSON Body: `{ "rows": [12, 14], "delete_all": false }` containing row indices.
  * **Returns**: `{ "success": true, "rows_deleted": 2 }`
  * **Purpose**: Deletes target rows from Google Sheets, invalidates cache, and updates action audits.

#### 3. Autopilot Feature (`features/autopilot/`) - [DISABLED / COMING SOON]
* **`POST /api/autopilot/run`**:
  * **Parameters**: Query: `from_step` (Integer, defaults to 0).
  * **Returns**: `{ "task_id": "UUID-STRING", "detail": "Auto-Pilot pipeline started" }`
  * **Purpose**: Triggers a background thread running the 6-step weekly forecasting pipeline. (Inactive in current scoped release).
* **`GET /api/autopilot/status/{task_id}`**:
  * **Parameters**: Path parameter `task_id`.
  * **Returns**: `{ "task_id": "...", "status": "running", "current_step": "run_engine", "steps": [...] }`
  * **Purpose**: Check the current execution logs state of the autopilot task. (Inactive in current scoped release).
* **`GET /api/autopilot/stream/{task_id}`**:
  * **Parameters**: Path parameter `task_id`.
  * **Returns**: Server-Sent Events (SSE) data stream (`text/event-stream`).
  * **Purpose**: Streams real-time pipeline console logs and progress updates. (Inactive in current scoped release).

#### 4. Baseline Feature (`features/baseline/`) - [DISABLED / COMING SOON]
* **`GET /api/baseline/status`**:
  * **Parameters**: None.
  * **Returns**: `{ "approved": true, "latest_run": BaselineRun, "active_dataset": DatasetStatus }`
  * **Purpose**: Retrieves baseline approval states. (Inactive in current scoped release).
* **`POST /api/baseline/approve`**:
  * **Parameters**: None (Admin authorization required).
  * **Returns**: `{ "detail": "Baseline approved — Final Plan unlocked." }`
  * **Purpose**: Locks baseline overrides on sheets and enables final plan adjustments. (Inactive in current scoped release).

---

## 5. Production Deployment Workflow

### Backend Deployments (Render / Space Docker Build)
The backend container builds using the root [`Dockerfile`](file:///c:/Users/sumitkumar.nayak/Desktop/forecast-pipeline-v2/Dockerfile):
1. **Container Staging**:
   ```bash
   docker build -t forecasting-api:latest .
   ```
2. **Stateless Google Drive Cache Configuration**:
   When starting the container in stateless spaces (Hugging Face / Render), ensure that `STORAGE_BACKEND=drive` is set, and the `GOOGLE_CREDENTIALS_JSON` and `PIPELINE_DRIVE_FOLDER_URL` variables are configured. At startup, the entrypoint executes:
   ```bash
   python core/storage/sync.py
   ```
   to automatically pull Parquet databases from Google Drive.
