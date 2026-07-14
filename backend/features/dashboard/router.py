"""Dashboard router — weekly analytics, pipeline card, run history."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.dependencies import get_current_user, get_db
from features.autopilot.state import load_autopilot_state

from core.database.engine import Database

from core.shared import pipeline_flow as pf

from features.dashboard.analytics_6w import describe_missing_6w_sources

from features.dashboard.analytics import (
    build_week_analytics,
    list_available_weeks,
)
from features.dashboard.revenue_trends import build_revenue_trends


router = APIRouter()


@router.get("/bootstrap")
def dashboard_bootstrap(
    week: str | None = None,
    cities: str | None = None,
    categories: str | None = None,
    days: str | None = None,
    dod_view: str = "City",
    wow_view: str = "City",
    current_user: dict = Depends(get_current_user),
):
    """
    Single round-trip for the dashboard — pipeline card, weeks, week analytics, and trends.
    Heavy 6w aggregates are cached in-process (shared across users, TTL from DASHBOARD_CACHE_TTL).
    """
    from core.shared.api_cache import CacheNS, cached


    is_default = (
        not week
        and not cities
        and not categories
        and not days
        and dod_view == "City"
        and wow_view == "City"
    )

    def _build():
        try:
            weeks_meta = list_available_weeks()
            week_label = week or weeks_meta.get("default_week")
            city_list = [c.strip() for c in cities.split(",") if c.strip()] if cities else None
            cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
            day_list = [d.strip() for d in days.split(",") if d.strip()] if days else None

            state = load_autopilot_state()
            if not state:
                pipeline_card = {"has_run": False, "run_name": None, "status": None}
            else:
                if state.get("success"):
                    status = "Success"
                elif state.get("failed_step") is not None:
                    status = "Failed"
                else:
                    status = "In progress"
                pipeline_card = {
                    "has_run": True,
                    "run_name": (state.get("run_name") or "—")[:28],
                    "status": status,
                }

            analytics = (
                build_week_analytics(week_label)
                if week_label
                else {"empty": True, "message": "No data found in the 6-week rolling file."}
            )
            revenue_trends = build_revenue_trends(
                cities=city_list,
                categories=cat_list,
                days=day_list,
                dod_view=dod_view,
                wow_view=wow_view,
            )

            return {
                "pipeline_card": pipeline_card,
                "weeks": weeks_meta,
                "analytics": analytics,
                "revenue_trends": revenue_trends,
            }
        except FileNotFoundError as exc:
            state = load_autopilot_state()
            if not state:
                pipeline_card = {"has_run": False, "run_name": None, "status": None}
            else:
                if state.get("success"):
                    status = "Success"
                elif state.get("failed_step") is not None:
                    status = "Failed"
                else:
                    status = "In progress"
                pipeline_card = {
                    "has_run": True,
                    "run_name": (state.get("run_name") or "—")[:28],
                    "status": status,
                }
            detail = str(exc)
            return {
                "pipeline_card": pipeline_card,
                "weeks": {"weeks": [], "default_week": None},
                "analytics": {"empty": True, "message": detail},
                "revenue_trends": {"empty": True},
                "data_warning": detail,
            }
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    if is_default:
        return cached(CacheNS.DASHBOARD, "bootstrap_default", _build, ttl=120.0)
    return _build()


@router.get("/pipeline-card")
def get_pipeline_card(current_user: dict = Depends(get_current_user)):
    """Compact last Auto-Pilot run summary (Streamlit render_pipeline_dashboard_card)."""
    state = load_autopilot_state()
    if not state:
        return {"has_run": False, "run_name": None, "status": None}
    if state.get("success"):
        status = "Success"
    elif state.get("failed_step") is not None:
        status = "Failed"
    else:
        status = "In progress"
    run_name = (state.get("run_name") or "—")[:28]
    return {"has_run": True, "run_name": run_name, "status": status}


@router.get("/weeks")
def get_dashboard_weeks(current_user: dict = Depends(get_current_user)):
    """ISO week labels for the dashboard week selector."""
    try:
        return list_available_weeks()
    except FileNotFoundError as exc:
        return {"weeks": [], "default_week": None, "message": str(exc)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analytics")
def get_dashboard_analytics(
    week: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """Weekly dashboard analytics for the selected ISO week."""
    try:
        meta = list_available_weeks()
        week_label = week or meta.get("default_week")
        if not week_label:
            return {"empty": True, "message": "No data found in the 6-week rolling file."}
        return build_week_analytics(week_label)
    except FileNotFoundError as exc:
        return {"empty": True, "message": str(exc)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/revenue-trends")
def get_revenue_trends(
    cities: str | None = None,
    categories: str | None = None,
    days: str | None = None,
    dod_view: str = "City",
    wow_view: str = "City",
    current_user: dict = Depends(get_current_user),
):
    """City revenue trend charts — day-on-day & week-on-week (Streamlit city_revenue_trends)."""
    try:
        city_list = [c.strip() for c in cities.split(",") if c.strip()] if cities else None
        cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
        day_list = [d.strip() for d in days.split(",") if d.strip()] if days else None
        return build_revenue_trends(
            cities=city_list,
            categories=cat_list,
            days=day_list,
            dod_view=dod_view,
            wow_view=wow_view,
        )
    except FileNotFoundError as exc:
        return {"empty": True, "message": str(exc)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/pipeline-flow")
def get_pipeline_flow(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Live evaluation of all 7 pipeline steps (no DB write)."""
    steps = pf.evaluate_all_steps(db)
    summary = pf.get_pipeline_summary(db)
    return {
        "steps": steps,
        "latest_run": summary,
    }


@router.post("/pipeline-flow/run")
def run_pipeline_audit(
    background: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Trigger a full pipeline audit and log it to DB."""
    user_id = int(current_user["sub"])
    run_id = pf.run_pipeline_flow(db, user_id)
    return {"run_id": run_id, "detail": "Pipeline audit complete"}


@router.get("/baseline-runs")
def get_baseline_runs(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Recent baseline run history."""
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file,
                           validation_status, approved_at
                    FROM baseline_runs
                    ORDER BY run_date DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        return []


@router.get("/final-plan-runs")
def get_final_plan_runs(
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Recent final plan run history."""
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT run_id, run_name, status, run_date, output_file,
                           validation_status, approved_at
                    FROM final_plan_runs
                    ORDER BY run_date DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as exc:
        return []


@router.get("/email-log")
def get_email_log(
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    try:
        with db.engine.connect() as conn:
            from sqlalchemy import text
            rows = conn.execute(
                text("""
                    SELECT id, sent_at, email_type, subject, recipients,
                           status, error_message
                    FROM email_log
                    ORDER BY sent_at DESC
                    LIMIT :limit
                """),
                {"limit": limit},
            ).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception:
        return []
