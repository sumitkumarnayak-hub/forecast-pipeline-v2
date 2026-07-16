"""
FastAPI entry point for the Planning Suite backend.

All existing business logic lives in src/planning_suite/ — untouched.
This file only wires up routes, CORS, lifespan, and the DB init.
"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# ── Make sure backend/ is importable ──────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Load .env before anything else ────────────────────────────────────────────
from dotenv import load_dotenv
env_path = BACKEND_DIR / ".env"
if not env_path.exists():
    env_path = BACKEND_DIR.parent / ".env"
load_dotenv(env_path)

# Resolve Google credentials from GOOGLE_CREDENTIALS_JSON before app.config loads.
from core.shared.google_credentials import get_google_credentials_path

get_google_credentials_path()

from app.logging import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        environment=os.getenv("APP_ENV", "development"),
        release=os.getenv("APP_RELEASE", "planning-suite@2.0.0"),
    )

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.middleware import request_context_middleware
from app.production import public_error_detail, validate_production_environment
from features.auth import router as auth
from features.dashboard import router as dashboard
from features.master_data import router as master_data
from features.baseline import router as baseline
from features.autopilot import router as autopilot
from features.final_plan import router as final_plan
from features.product_launch import router as new_product_launch
from features.insights import router as insights
from features.settings import router as settings
from features.validation import router as validation
from features.shared import demo_filter_router as demo_filter



def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    return [o.strip() for o in raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        validate_production_environment()
        from core.database.engine import get_shared_database

        db = get_shared_database()
        db.init_database()
        logger.info("Database initialised")
    except Exception as exc:
        logger.warning("DB init warning: %s", exc)

    try:
        from core.storage.sync import pull_startup_artifacts
        from core.storage.factory import storage_backend_name

        if storage_backend_name() != "local":
            def _async_sync():
                try:
                    logger.info("Starting background download of pipeline startup artifacts from Google Drive...")
                    summary = pull_startup_artifacts(skip_existing=True)
                    pulled = [k for k, v in summary.items() if v == "downloaded"]
                    missing_remote = [k for k, v in summary.items() if v == "skipped (not in remote)"]
                    failed = [k for k, v in summary.items() if v.startswith("failed")]
                    if pulled:
                        logger.info("Background startup artifact pull complete: %s", ", ".join(pulled))
                    elif summary.get("outputs/rds_cache.parquet", "").startswith("skipped"):
                        logger.info("Startup artifacts already present locally on container")
                    else:
                        logger.warning(
                            "6w dashboard cache missing on disk — upload outputs/rds_cache.parquet "
                            "to shared Drive (python scripts/push_pipeline_storage.py)"
                        )
                    if missing_remote:
                        logger.warning(
                            "Startup artifacts not in remote storage: %s — run push_pipeline_storage.py "
                            "from a machine with pipeline files",
                            ", ".join(missing_remote),
                        )
                    if failed:
                        logger.error("Startup artifact pull failed: %s", ", ".join(failed))
                except Exception as exc:
                    logger.error("Async startup artifact pull failed: %s", exc)

            import threading
            threading.Thread(target=_async_sync, daemon=True, name="startup-artifact-pull").start()
        elif os.getenv("SPACE_ID") or os.getenv("RENDER"):
            logger.warning(
                "STORAGE_BACKEND=local on cloud host — pipeline files will not sync. "
                "Set STORAGE_BACKEND=drive and PIPELINE_DRIVE_FOLDER_URL."
            )
    except Exception as exc:
        logger.error(
            "Startup artifact sync thread scheduling failed: %s — check STORAGE_BACKEND, "
            "PIPELINE_DRIVE_FOLDER_URL, and GOOGLE_CREDENTIALS_JSON",
            exc,
        )

    try:
        from core.shared.cache_warmup import start_cache_warmup


        start_cache_warmup()
    except Exception as exc:
        logger.warning("Cache warmup warning: %s", exc)

    try:
        from features.product_launch.watcher import start_ff_input_watcher

        start_ff_input_watcher(interval_seconds=60)
        logger.info("FF Input change watcher started (60s interval)")
    except Exception as exc:
        logger.warning("FF Input watcher startup warning: %s", exc)

    queue_worker_stop_event = None
    try:
        import threading
        from core.database.engine import get_shared_database
        from core.queue.worker import QueueWorker
        from features.product_launch.tasks import register_npl_tasks

        db = get_shared_database()
        queue_worker_stop_event = threading.Event()
        worker = QueueWorker(engine=db.engine, sleep_interval=2.0)
        register_npl_tasks(worker)
        
        queue_thread = threading.Thread(
            target=worker.run,
            args=(queue_worker_stop_event,),
            daemon=True,
            name="queue-worker-daemon"
        )
        queue_thread.start()
        logger.info("Queue worker daemon started")
    except Exception as exc:
        logger.error("Queue worker startup failed: %s", exc)

    yield
    
    if queue_worker_stop_event:
        logger.info("Shutting down queue worker daemon...")
        queue_worker_stop_event.set()


app = FastAPI(
    title="Planning Suite API",
    description="FastAPI backend for the Demand Planning & Forecasting Suite",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.middleware("http")
async def _request_context(request: Request, call_next):
    return await request_context_middleware(request, call_next)


from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Strip raw input data from validation errors so passwords or sensitive inputs are never exposed."""
    details = []
    for error in exc.errors():
        err_dict = dict(error)
        err_dict.pop("input", None)
        details.append(err_dict)
    return JSONResponse(
        status_code=422,
        content={"detail": details}
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON errors with CORS headers (avoids browser 'CORS' masking of 500s)."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        
    # Detect Google API Quota Exceeded (429)
    exc_str = str(exc)
    is_quota = "quotaexceeded" in exc_str.lower() or "429" in exc_str or (hasattr(exc, "code") and getattr(exc, "code") == 429)
    if is_quota:
        logger.warning("Google API Quota Exceeded detected globally: %s", exc)
        return JSONResponse(
            status_code=429,
            content={"detail": "Google Sheets API quota limit reached. Please wait 60 seconds before retrying."}
        )

    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": public_error_detail(exc)})

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,               prefix="/api/auth",               tags=["Auth"])
app.include_router(dashboard.router,          prefix="/api/dashboard",          tags=["Dashboard"])
app.include_router(master_data.router,        prefix="/api/master-data",        tags=["Master Data"])
app.include_router(baseline.router,           prefix="/api/baseline",           tags=["Baseline"])
app.include_router(autopilot.router,          prefix="/api/autopilot",          tags=["Auto-Pilot"])
app.include_router(final_plan.router,         prefix="/api/final-plan",         tags=["Final Plan"])
app.include_router(new_product_launch.router, prefix="/api/new-product-launch", tags=["Product Launch"])
app.include_router(insights.router,           prefix="/api/insights",           tags=["Insights"])
app.include_router(settings.router,           prefix="/api/settings",           tags=["Settings"])
app.include_router(validation.router,         prefix="/api/validation",         tags=["Validation"])
app.include_router(demo_filter.router,        prefix="/api/demo-filter",        tags=["Demo Filter"])


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "Planning Suite API v2",
        "version": "2.0.0",
        "environment": os.getenv("APP_ENV", "development"),
    }


@app.get("/api/health/ready")
def health_ready():
    """Readiness probe — verifies database connectivity."""
    from sqlalchemy import text
    from core.database.engine import get_shared_database


    try:
        db = get_shared_database()
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {
            "status": "ready",
            "database": db.backend,
            "connection": db.connection_label(),
        }
    except Exception as exc:
        logger.warning("Readiness check failed: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable")


@app.get("/api/health/storage")
def health_storage():
    """Storage diagnostics — no secrets, for post-deploy troubleshooting."""
    from core.shared.storage_status import get_storage_status


    status = get_storage_status(check_remote=True)
    ok = not status.get("missing_artifacts") and not status.get("warning")
    return {"status": "ok" if ok else "degraded", **status}
