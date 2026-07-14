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
2. **Execute REST API Integration Suite**:
   Run the endpoints test suite:
   ```bash
   python scripts/test_api_endpoints.py
   ```
   This script spins up a standard FastAPI `TestClient`, mocks remote Google Sheets connections, and verifies request/response payloads for:
   - **/api/health** & **/api/validation/logics** (Auth verification)
   - **/api/new-product-launch/wizard/context** (Product launch context maps)
   - **/api/master-data/new-hub-sync/confirm** (Hub launch sync triggers)

---

## 4. Production Deployment Workflow

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
