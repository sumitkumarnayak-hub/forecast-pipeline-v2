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

# ── Make sure src/ is importable ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ── Load .env before anything else ────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(BACKEND_DIR / ".env")

# Resolve Google credentials from GOOGLE_CREDENTIALS_JSON before planning_suite.config loads.
from planning_suite.google_credentials import get_google_credentials_path

get_google_credentials_path()

from app.logging_config import setup_logging

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
from app.routers import auth, dashboard, master_data, baseline, autopilot
from app.routers import final_plan, new_product_launch, insights, settings, validation, demo_filter


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
        from planning_suite.db.engine import get_shared_database
        db = get_shared_database()
        db.init_database()
        logger.info("Database initialised")
        from planning_suite.services.cache_warmup import start_cache_warmup

        start_cache_warmup()
    except Exception as exc:
        logger.warning("DB init warning: %s", exc)
    yield


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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return JSON errors with CORS headers (avoids browser 'CORS' masking of 500s)."""
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
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
    from planning_suite.db.engine import get_shared_database

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
        raise HTTPException(status_code=503, detail="Database not ready") from exc
