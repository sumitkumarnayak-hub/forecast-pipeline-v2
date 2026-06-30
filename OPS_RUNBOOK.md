# Operations Runbook — Planning Suite v2

Operational procedures for production deployments. Pair with `BACKUP_STRATEGY.md`.

## Architecture (production)

- **Frontend:** Next.js (`npm run build` → `npm start` or container)
- **Backend:** FastAPI + uvicorn (single worker recommended while Auto-Pilot uses in-process threads)
- **Auth:** HttpOnly cookie `ps_access_token` (JWT); API proxied same-origin via Next `/api/*` rewrites
- **Data:** PostgreSQL (`DATABASE_URL`), mounted planning drive, Google Sheets service account

## Environment checklist

| Variable | Purpose |
|----------|---------|
| `APP_ENV=production` | Disables default dev users, enforces secrets |
| `AUTH_SECRET_KEY` | 32+ byte random secret for JWT |
| `DATABASE_URL` | PostgreSQL connection string |
| `CORS_ORIGINS` | Comma-separated frontend origins (if not same-origin proxy) |
| `AUTH_COOKIE_SECURE=true` | HTTPS-only cookies |
| `SENTRY_DSN` / `NEXT_PUBLIC_SENTRY_DSN` | Error tracking (optional) |
| `LOG_LEVEL` | `INFO` (default) or `DEBUG` |

See `DEVELOPER_GUIDE.md` for full env var list (paths, sheets, SMTP).

## Start / restart

### Backend (production)

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Do **not** use `reload=True` in production.

### Frontend

```bash
cd frontend
npm run build
npm start
```

Set `NEXT_PUBLIC_API_URL` to the internal backend URL used by Next rewrites at **build time**.

### Health check

```bash
curl -s http://localhost:8000/api/health
# {"status":"ok","service":"Planning Suite API v2"}
```

## Logs

- Backend emits **JSON logs** to stdout with `request_id` correlation (`X-Request-Id` response header).
- Pipe to CloudWatch, Datadog, or ELK via your platform log agent.
- Search by `request_id` when correlating user reports with API errors.

## Common incidents

### 1. User cannot log in

1. Verify `AUTH_SECRET_KEY` unchanged (rotating invalidates all sessions).
2. Check `DATABASE_URL` connectivity and `users` table.
3. Confirm `APP_ENV=production` — default `admin123` users are **not** auto-created in prod.
4. Browser: cookie `ps_access_token` must be set on login; check HTTPS + `AUTH_COOKIE_SECURE`.

### 2. Auto-Pilot stuck / “running” forever

1. Check `backend/outputs/autopilot_state.json` and DB `pipeline_runs` for the `run_id`.
2. Inspect `pipeline_run_log_lines` for the run.
3. If process died mid-run, state may show `running` — mark failed in DB or delete stale `_ACTIVE` in-memory state by **restarting the backend** (single worker).
4. Resume from failed step via UI **Run from step** after fixing root cause.

### 3. Auto-Pilot SSE not updating

1. SSE must hit **same origin** (`/api/autopilot/stream/{run_id}`) so httpOnly cookie is sent.
2. Reverse proxy must not buffer SSE (`X-Accel-Buffering: no` on nginx).
3. Check 401 on stream — session expired; re-login.

### 4. Dashboard empty / wrong week

1. Confirm `RDS_6W_PATH` / `6w_v3.parquet` exists and is fresh.
2. Clear dashboard bootstrap cache: change week or hard-refresh; backend sheet caches in `outputs/`.
3. Re-run Auto-Pilot step 1 (fetch raw) if data is stale.

### 5. Google Sheets errors

1. Validate `GOOGLE_CREDENTIALS_PATH` and service account access to all sheet URLs in `.env`.
2. Check quota / rate limits; P-H Master full read can take 60–90s.

### 6. Email notifications failing

1. Set `FROM_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` (or app password).
2. Test via Settings → Test email.

## Cache invalidation

| Cache | Location | Clear action |
|-------|----------|--------------|
| Dashboard bootstrap | Browser `sessionStorage` / in-memory | Hard refresh; change week |
| Master-data metadata | `outputs/` parquet caches | Re-fetch from UI or delete cache files |
| Baseline approved flag | `shell:baseline-approved` in query cache | Approve/revoke baseline; refresh |
| Sheet read cache | `outputs/sheet_cache/` | Delete specific cache or restart after env change |

## Security rotation

1. **JWT secret:** Set new `AUTH_SECRET_KEY` → all users re-login.
2. **DB password:** Update `DATABASE_URL`, restart backend.
3. **Google credentials:** Replace JSON file, restart backend.

## Escalation data to collect

- `X-Request-Id` from browser network tab or response headers
- `run_id` for Auto-Pilot / baseline / final-plan runs
- Timestamp, username, role
- Relevant log lines (JSON) around the incident
