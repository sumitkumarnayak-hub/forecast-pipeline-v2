---
title: Planning Suite API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Planning Suite API (FastAPI)

Backend for the Demand Planning & Forecasting Suite.

## Health

- `GET /api/health` — liveness
- `GET /api/health/ready` — database check
- `GET /api/health/storage` — pipeline artifact sync status (no auth)
- `GET /docs` — Swagger UI

## Required Space secrets (Settings → Variables)

Set these in the Hugging Face Space **Settings → Variables** (same as Render):

| Variable | Notes |
|----------|--------|
| `APP_ENV` | `production` |
| `AUTH_SECRET_KEY` | Random 64-char hex |
| `DATABASE_URL` | Supabase Postgres URL |
| `GOOGLE_CREDENTIALS_JSON` | Service account JSON, **one line** |
| `STORAGE_BACKEND` | `drive` |
| `PIPELINE_DRIVE_FOLDER_URL` | **Required** — Shared Drive folder URL, e.g. `https://drive.google.com/drive/folders/0AKKX6JjhUdibUk9PVA` |
| `CORS_ORIGINS` | Your Vercel frontend URL |
| All `*_SHEET_URL` vars | Same as local `.env` |

**Do not** set `G:\` paths. Artifacts use `/app/data/*` and pull from shared Drive at startup.

**Critical:** If logs show `STORAGE_BACKEND=drive requires PIPELINE_DRIVE_FOLDER_URL`, add that variable in Settings → Variables and restart. Without it, no pipeline files are downloaded from Drive.

Copy values from `backend/dotenv-profiles/render.env` on your machine.

## Frontend

Point Vercel `BACKEND_URL` to your Space URL:

```
https://<your-username>-<space-name>.hf.space
```

The API routes are under `/api/*`.
