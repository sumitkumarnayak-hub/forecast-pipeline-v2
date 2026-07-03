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
| `CORS_ORIGINS` | Your Vercel URL, e.g. `https://planning.yourcompany.com` |
| `GOOGLE_CREDENTIALS_PATH` | Path to service account JSON **or** paste JSON as env and write to file at build |

### File storage (critical)

Auto-Pilot and baseline steps read/write local paths (`RAW_ACTUALS_FOLDER`, `DP_LOGICS_FOLDER`, `outputs/`, etc.).

On Render without persistent disk, these are **lost on redeploy**. Options:

1. **Render persistent disk** mounted at your `PLANNING_DRIVE_ROOT`
2. **Shared network drive** accessible from the container
3. **S3-compatible storage** (requires script changes — not default today)

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

| Variable | Required | Notes |
|----------|----------|--------|
| `BACKEND_URL` | **Yes** | Public HTTPS URL of your FastAPI server, e.g. `https://planning-api.onrender.com` |

The frontend proxies `/api/*` to `BACKEND_URL` so httpOnly auth cookies work same-origin.

**Do not** set `BACKEND_URL` to `http://localhost:8000` on Vercel — Vercel runs in the cloud and **cannot** reach your PC's localhost (login will return **502 Bad Gateway**).

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
