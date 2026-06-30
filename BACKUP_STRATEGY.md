# Backup Strategy — Planning Suite v2

What to back up, how often, and how to restore.

## 1. PostgreSQL database (critical)

**Contains:** users, roles, preferences, pipeline run history, step logs, autopilot snapshots, approval audit trail.

| | Recommendation |
|--|----------------|
| **Frequency** | Daily automated snapshots; point-in-time recovery (PITR) if on managed Postgres (RDS, Supabase, Cloud SQL) |
| **Retention** | 30 days minimum; 90 days for audit |
| **Method** | `pg_dump` or provider-native backups |

**Restore:**

```bash
pg_restore -d planning_suite backup.dump
# or psql -f backup.sql
```

After restore, restart the backend and verify login + latest `pipeline_runs`.

## 2. Planning drive / mounted data (critical)

**Contains:** raw actuals, DP logics Excel, baseline outputs, FF inputs, parquet intermediates.

Paths from `.env` (examples):

- `PLANNING_DRIVE_ROOT`
- `RAW_DATA_PATH` / `RAW_ACTUALS_FOLDER`
- `BASELINE_OUTPUTS_FOLDER`
- `FF_INPUTS_FOLDER`
- `DP_LOGICS_FOLDER`

| | Recommendation |
|--|----------------|
| **Frequency** | Daily incremental; weekly full |
| **Method** | Filesystem snapshots (EBS, Azure Files backup) or `rsync` to object storage |

**Restore:** Mount restored volume at the same paths; confirm permissions for the service user.

## 3. `backend/outputs/` (important)

**Contains:** `6w_v3.parquet`, autopilot state JSON, sheet caches, RDS week caches.

| | Recommendation |
|--|----------------|
| **Frequency** | Daily (can be regenerated but slow) |
| **Note** | Safe to rebuild by re-running pipeline; backup avoids long recovery |

## 4. Google Sheets (source of truth for masters)

Sheets are authoritative for hub/product masters. The app reads/writes via API.

| | Recommendation |
|--|----------------|
| **Frequency** | Rely on Google Workspace version history + periodic exports |
| **Method** | Scheduled export to Drive or download critical tabs to parquet/Excel in planning drive |

## 5. Secrets & configuration (critical)

**Never commit to git.** Store in:

- Secret manager (AWS Secrets Manager, Vault, Doppler)
- Encrypted `.env` on server

Back up:

- `AUTH_SECRET_KEY` (rotation plan documented in runbook)
- `GOOGLE_CREDENTIALS_PATH` JSON
- `DATABASE_URL`
- SMTP credentials

## 6. Application code & releases

| | Recommendation |
|--|----------------|
| **Method** | Git tags per release; container images in registry |
| **Retention** | Keep last N deployable images |

## Recovery priorities (RTO order)

1. Restore PostgreSQL (users + run history)
2. Restore planning drive paths (pipeline can run)
3. Restore or regenerate `outputs/` caches
4. Redeploy application from known-good image/tag

## What is NOT backed up by default

- In-memory Auto-Pilot `_ACTIVE` state (lost on restart — use DB `pipeline_runs`)
- Browser session cookies (users re-login)
- Frontend build artifacts (rebuild from git)

## Verification (monthly drill)

1. Restore DB to a staging instance.
2. Mount a copy of planning drive.
3. Run health check + login + dashboard week load.
4. Document time to recover and gaps.
