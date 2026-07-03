# Production Deployment Guide

Step-by-step guide to run Planning Suite v2 in production (typical setup: **Vercel** frontend + **Render** backend + **PostgreSQL**).

## Architecture

```
Browser → Vercel (Next.js) → /api/* proxy → Render (FastAPI)
                              ↓
                    PostgreSQL (users, run history)
                              ↓
              Google Sheets + mounted drive / persistent disk
```

## 1. Database (PostgreSQL)

1. Create a Postgres instance (Render Postgres, Supabase, or RDS).
2. Copy the connection string to `DATABASE_URL` on the **backend** only.
3. Tables are created automatically on first API start (`init_database`).

**Important:** Set `APP_ENV=production` so default dev users (`admin123`, etc.) are **not** created.

Create your first admin user via SQL or temporarily run locally against prod DB, then use **Settings → Users**.

## 2. Backend (Render Web Service)

| Setting | Value |
|---------|--------|
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` |

### Required environment variables

| Variable | Notes |
|----------|--------|
| `APP_ENV` | `production` |
| `AUTH_SECRET_KEY` | 32+ byte random hex — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | PostgreSQL connection string |
| `AUTH_COOKIE_SECURE` | `true` (HTTPS) |
| `CORS_ORIGINS` | `https://forecast-pipeline-v2-frontend-nu.vercel.app` (plus localhost for dev) |
| `GOOGLE_CREDENTIALS_PATH` | Path to service account JSON **or** paste JSON as env and write to file at build |

### File storage (critical)

Auto-Pilot and baseline steps read/write local paths (`RAW_ACTUALS_FOLDER`, `DP_LOGICS_FOLDER`, `outputs/`, etc.).

On Render without persistent disk, these are **lost on redeploy**. Use the **storage adapter** (switch backends via env — no code changes):

| `STORAGE_BACKEND` | Behavior |
|-------------------|----------|
| `local` (default) | Files stay on disk paths from `.env` |
| `drive` (recommended) | Sync to a single Google Drive folder — no file size cap issues |
| `supabase` | Pull from bucket before Auto-Pilot, push after |

#### Google Drive (recommended)

Uses your existing Google service account (`GOOGLE_CREDENTIALS_PATH`). One folder URL is enough for all pipeline artifacts.

1. Create a folder in **Google Shared Drive** (recommended) or My Drive.
2. **Share it** with your service account email (`client_email` in the JSON) as **Content manager** / **Editor**.
3. In `backend/.env`:

| Variable | Value |
|----------|--------|
| `STORAGE_BACKEND` | `drive` |
| `PIPELINE_DRIVE_FOLDER_URL` | `https://drive.google.com/drive/folders/YOUR_FOLDER_ID` |
| `GOOGLE_DRIVE_IMPERSONATE_EMAIL` | *(optional)* Workspace user email if the folder is **not** on a Shared Drive |

**Important:** Service accounts have **no My Drive storage**. Uploads to a regular shared folder fail with `storageQuotaExceeded`. Use a [Shared Drive](https://developers.google.com/workspace/drive/api/guides/about-shareddrives) folder, or set `GOOGLE_DRIVE_IMPERSONATE_EMAIL` (requires Google Workspace admin to enable domain-wide delegation on the service account).

4. **Seed Drive** from your machine:

```bash
cd backend
python scripts/push_pipeline_storage.py
```

5. On Render, set container-local paths for `OUTPUT_PATH`, `DP_LOGICS_FOLDER`, etc. Auto-Pilot pulls from Drive at run start and pushes when finished.

Large files (`rds_cache.parquet`, `6w_v3.rds`) upload via Drive resumable API — no 50 MB Supabase limit.

#### Supabase Storage (optional)

1. Create or use bucket: [input-output](https://supabase.com/dashboard/project/prhfevvqxmxhevweyegh/storage/files/buckets/input-output)
2. In `backend/.env` on Render (and locally for upload):

| Variable | Value |
|----------|--------|
| `STORAGE_BACKEND` | `supabase` |
| `SUPABASE_URL` | `https://prhfevvqxmxhevweyegh.supabase.co` (or derive from `DATABASE_URL`) |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → **service_role** (never expose to frontend) |
| `SUPABASE_STORAGE_BUCKET` | `input-output` |

3. **Seed the bucket** from your machine (where pipeline files exist):

```bash
cd backend
# Add SUPABASE_SERVICE_ROLE_KEY to .env first
python scripts/push_pipeline_storage.py
```

4. On Render, set path env vars to **writable paths inside the container** (e.g. `/data/outputs`, `/data/dp_logics`). Auto-Pilot will download from Supabase at run start and upload when finished.

Other options:

1. **Render persistent disk** mounted at your `PLANNING_DRIVE_ROOT`
2. **Shared network drive** accessible from the container

See `DATA_SOURCES.md` for which files each step needs.

### Health checks

| Endpoint | Use |
|----------|-----|
| `GET /api/health` | Liveness — process up |
| `GET /api/health/ready` | Readiness — database reachable |

Configure Render health check path: `/api/health/ready`

### Optional

| Variable | Purpose |
|----------|---------|
| `SENTRY_DSN` | Backend error tracking |
| `DISABLE_CACHE_WARMUP` | `true` to skip NPL sheet warm-up on start |
| `LOGIN_RATE_MAX_ATTEMPTS` | Default 10 per 15 min per IP+user |

## 3. Frontend (Vercel)

| Setting | Value |
|---------|--------|
| Root directory | `frontend` |
| Build command | `npm run build` |
| Output | Next.js default |

### Environment variables (Vercel → Settings → Environment Variables)

Set these for **Production** (and Preview if you use preview URLs):

| Variable | Value | Required |
|----------|--------|----------|
| `BACKEND_URL` | `https://forecast-pipeline-v2.onrender.com` | **Yes** (recommended — also defaults in code if omitted) |

**Production URLs**

| Service | URL |
|---------|-----|
| Frontend | https://forecast-pipeline-v2-frontend-nu.vercel.app |
| Backend | https://forecast-pipeline-v2.onrender.com |

The frontend calls `/api/*` on the Vercel domain; the Next.js route handler proxies to `BACKEND_URL` (Render). You do **not** point the browser directly at Render.

**Render backend** (separate from Vercel) must include:

```env
CORS_ORIGINS=https://forecast-pipeline-v2-frontend-nu.vercel.app,http://localhost:3000
APP_ENV=production
AUTH_COOKIE_SECURE=true
```

After changing env vars on Vercel, click **Redeploy**.

**Do not** set `BACKEND_URL` to `http://localhost:8000` on Vercel — Vercel runs in the cloud and **cannot** reach your PC's localhost (login will return **502 Bad Gateway**).

Optional: set `BACKEND_URL=https://forecast-pipeline-v2.onrender.com` in Vercel → Settings → Environment Variables (the app already defaults to this on Vercel if unset).

### Render keep-alive (GitHub Actions)

To avoid Render free-tier cold starts, add a scheduled workflow. Copy `docs/github-workflows/render-keepalive.yml` into **GitHub → Actions → New workflow** (or push to `.github/workflows/` after running `gh auth refresh -h github.com -s workflow`).

#### Vercel UI + local backend (dev only)

1. Run backend locally: `python run_backend.py`
2. Expose port 8000 with [ngrok](https://ngrok.com/): `ngrok http 8000`
3. Set on Vercel: `BACKEND_URL=https://YOUR-SUBDOMAIN.ngrok-free.app` (no trailing slash)
4. **Redeploy** the frontend

For daily development, run both locally (`start.ps1`) instead of mixing Vercel + localhost.

Legacy alias: `NEXT_PUBLIC_API_URL` is used if `BACKEND_URL` is unset.

### Optional

| Variable | Purpose |
|----------|---------|
| `NEXT_PUBLIC_SENTRY_DSN` | Frontend error tracking |

## 4. Google Sheets & SMTP

1. Upload service account JSON to backend (or secret file mount).
2. Share all planning spreadsheets with the service account email.
3. Set SMTP vars for email notifications (`FROM_EMAIL`, `FROM_EMAIL_APP_PASSWORD` or `SMTP_*`).

## 5. Post-deploy checklist

- [ ] `GET /api/health/ready` returns `ready`
- [ ] Login works over HTTPS; cookie `ps_auth` is set
- [ ] Dashboard loads a week of data
- [ ] Auto-Pilot step 1 completes (masters sync)
- [ ] Product Launch wizard loads categories (Sheets cache warm-up)
- [ ] Admin can create users under Settings → Users
- [ ] Team reads **About & Guide** in the app sidebar

## 6. Smoke test script

```bash
curl -s https://YOUR-API/api/health
curl -s https://YOUR-API/api/health/ready
```

## Related docs

- `OPS_RUNBOOK.md` — incidents, logs, restarts
- `BACKUP_STRATEGY.md` — Postgres + drive backups
- `DATA_SOURCES.md` — Sheets vs files vs DB
- In-app **About & Guide** (`/about`) — for planners and new team members
