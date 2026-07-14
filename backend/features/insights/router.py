"""Insights router — availability loss, executive summary, reports, full insights views."""

from __future__ import annotations



from fastapi import APIRouter, Depends, HTTPException, Query



from app.dependencies import get_current_user, get_db

from core.database.engine import Database




router = APIRouter()





@router.get("/bootstrap")

def insights_bootstrap(current_user: dict = Depends(get_current_user)):

    """Weeks, cities, and view metadata for Analytics → Insights."""

    from features.insights.analytics import get_insights_bootstrap




    return get_insights_bootstrap()





@router.get("/view")

def insights_view(

    insight_view: str = Query(..., description="executive | revenue_loss | attainment | wastage | hub_health"),

    week: str | None = None,

    cities: str | None = Query(None, description="Comma-separated city names"),

    sub_view: str | None = None,

    oa_thr: int = 120,

    ua_thr: int = 80,

    min_plan: int = 500,

    top_n: int = 20,

    granularity: str = "Daily",

    loss_categories: str | None = None,

    pareto_dim: str = "Hub",

    category_focus: str | None = None,

    min_wastage: int = 500,

    current_user: dict = Depends(get_current_user),

):

    from features.dashboard.analytics import list_available_weeks


    from features.insights.analytics import build_insights_view




    meta = list_available_weeks()

    week_label = week or meta.get("default_week")

    if not week_label:

        return {"empty": True, "message": "No 6-week data available."}



    city_list = [c.strip() for c in cities.split(",") if c.strip()] if cities else None

    cat_list = [c.strip() for c in loss_categories.split(",") if c.strip()] if loss_categories else None



    try:

        return build_insights_view(

            insight_view=insight_view,

            week=week_label,

            cities=city_list or None,

            sub_view=sub_view,

            oa_thr=oa_thr,

            ua_thr=ua_thr,

            min_plan=min_plan,

            top_n=top_n,

            granularity=granularity,

            loss_categories=cat_list,

            pareto_dim=pareto_dim,

            category_focus=category_focus,

            min_wastage=min_wastage,

        )

    except FileNotFoundError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except Exception as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc





@router.get("/availability-loss")

def get_availability_loss(

    limit: int = 500,

    current_user: dict = Depends(get_current_user),

):

    try:

        from core.utils.dataframe import df_to_records


        from features.insights.analytics import load_loss_sheet




        df = load_loss_sheet()

        if df is None or df.empty:

            return {"rows": [], "columns": []}

        return {"rows": df_to_records(df.head(limit)), "columns": list(df.columns)}

    except Exception as exc:

        raise HTTPException(status_code=500, detail=str(exc)) from exc





@router.get("/6w-summary")

def get_6w_summary(current_user: dict = Depends(get_current_user)):

    try:

        from features.insights.analytics import load_6w_insights




        df = load_6w_insights()

        return {

            "available": True,

            "columns": df.columns.tolist(),

            "rows": len(df),

            "sample_rows": df.head(5).fillna("").to_dict(orient="records"),

        }

    except FileNotFoundError as exc:

        return {"available": False, "message": str(exc)}

    except Exception as exc:

        return {"available": False, "error": str(exc)}





@router.get("/executive-summary")

def executive_summary(

    week: str | None = None,

    cities: str | None = None,

    current_user: dict = Depends(get_current_user),

):

    """Week KPIs — delegates to insights view builder."""

    from features.dashboard.analytics import list_available_weeks


    from features.insights.analytics import build_insights_view




    meta = list_available_weeks()

    week_label = week or meta.get("default_week")

    if not week_label:

        return {"empty": True, "message": "No 6-week data available."}

    city_list = [c.strip() for c in cities.split(",") if c.strip()] if cities else None

    return build_insights_view(insight_view="executive", week=week_label, cities=city_list or None)





@router.get("/reports/baseline-summary")

def report_baseline_summary(

    limit: int = 500,

    current_user: dict = Depends(get_current_user),

):

    from features.dashboard.analytics_reports import get_baseline_summary_report




    return get_baseline_summary_report(limit=limit)





@router.get("/reports/plan-comparison")

def report_plan_comparison(current_user: dict = Depends(get_current_user)):

    from features.dashboard.analytics_reports import get_plan_comparison_report




    return get_plan_comparison_report()





@router.get("/reports/actual-vs-plan")

def report_actual_vs_plan(

    granularity: str = "city_category",

    limit: int = 200,

    current_user: dict = Depends(get_current_user),

):

    from features.dashboard.analytics_reports import get_actual_vs_plan_report




    return get_actual_vs_plan_report(granularity=granularity, limit=limit)





@router.get("/reports/city-revenue-trends")

def report_city_revenue_trends(

    cities: str | None = None,

    categories: str | None = None,

    days: str | None = None,

    dod_view: str = "City",

    wow_view: str = "City",

    current_user: dict = Depends(get_current_user),

):

    from features.dashboard.revenue_trends import build_revenue_trends




    city_list = [c.strip() for c in cities.split(",") if c.strip()] if cities else None

    cat_list = [c.strip() for c in categories.split(",") if c.strip()] if categories else None

    day_list = [d.strip() for d in days.split(",") if d.strip()] if days else None

    try:

        return build_revenue_trends(city_list, cat_list, day_list, dod_view, wow_view)

    except FileNotFoundError as exc:

        raise HTTPException(status_code=404, detail=str(exc)) from exc





@router.get("/reports/downloads")

def report_downloads(current_user: dict = Depends(get_current_user)):

    from features.dashboard.analytics_reports import list_downloadable_reports




    return {"files": list_downloadable_reports()}





@router.get("/reports/baseline-runs")

def report_baseline_runs(

    limit: int = 20,

    current_user: dict = Depends(get_current_user),

    db: Database = Depends(get_db),

):

    try:

        with db.engine.connect() as conn:

            from sqlalchemy import text



            rows = conn.execute(

                text("""

                    SELECT run_id, run_name, status, run_date, output_file, validation_status, approved_at

                    FROM baseline_runs ORDER BY run_date DESC LIMIT :limit

                """),

                {"limit": limit},

            ).fetchall()

        return [dict(r._mapping) for r in rows]

    except Exception:

        return []





@router.get("/reports/final-plan-runs")

def report_final_plan_runs(

    limit: int = 20,

    current_user: dict = Depends(get_current_user),

    db: Database = Depends(get_db),

):

    try:

        with db.engine.connect() as conn:

            from sqlalchemy import text



            rows = conn.execute(

                text("""

                    SELECT run_id, run_name, status, run_date, output_file, validation_status

                    FROM final_plan_runs ORDER BY run_date DESC LIMIT :limit

                """),

                {"limit": limit},

            ).fetchall()

        return [dict(r._mapping) for r in rows]

    except Exception:

        return []


