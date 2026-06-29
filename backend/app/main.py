"""
FastAPI entry point for the Planning Suite backend.

All existing business logic lives in src/planning_suite/ — untouched.
This file only wires up routes, CORS, lifespan, and the DB init.
"""
import sys
import os
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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, dashboard, master_data, baseline, autopilot
from app.routers import final_plan, new_product_launch, insights, settings, validation


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure DB tables exist on startup (uses existing Database().init_db())
    try:
        from planning_suite.db.engine import Database
        db = Database()
        db.init_db()
        print("[startup] Database initialised OK", flush=True)
    except Exception as exc:
        print(f"[startup] DB init warning: {exc}", flush=True)
    yield


app = FastAPI(
    title="Planning Suite API",
    description="FastAPI backend for the Demand Planning & Forecasting Suite",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS (allow Next.js dev server) ───────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "Planning Suite API v2"}
