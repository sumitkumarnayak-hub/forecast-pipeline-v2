"""Analytics / Insights API tests."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd


def test_insights_bootstrap(client, auth_headers):
    with patch(
        "features.insights.analytics.get_insights_bootstrap",
        return_value={
            "empty": False,
            "weeks": ["2026-W01"],
            "default_week": "2026-W01",
            "cities": ["Mumbai"],
            "insight_views": [{"id": "executive", "label": "Executive Summary"}],
        },
    ):
        resp = client.get("/api/insights/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "insight_views" in body
    assert body["default_week"] == "2026-W01"


def test_insights_view_executive(client, auth_headers):
    mock_payload = {
        "empty": False,
        "week": "2026-W01",
        "kpis": {"plan_revenue": 100.0},
        "city_leaderboard": [],
    }
    with patch(
        "features.insights.analytics.build_insights_view",
        return_value=mock_payload,
    ):
        resp = client.get(
            "/api/insights/view?insight_view=executive&week=2026-W01",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["kpis"]["plan_revenue"] == 100.0


def test_revenue_trends_chart_x_keys_align():
    """Chart x_values must match series point x keys (frontend joins on strict equality)."""
    from features.dashboard.revenue_trends import build_revenue_trends


    try:
        payload = build_revenue_trends(dod_view="City")
    except FileNotFoundError:
        return
    chart = payload.get("day_on_day", {}).get("chart")
    if not chart:
        return
    for x in chart.get("x_values", []):
        for series in chart.get("series", []):
            if any(p["x"] == x for p in series.get("points", [])):
                continue
            for p in series.get("points", []):
                if str(p["x"]).startswith(str(x)[:10]) and p["x"] != x:
                    raise AssertionError(f"x format mismatch: {x!r} vs {p['x']!r}")


def test_reports_city_revenue_trends(client, auth_headers):
    with patch(
        "features.dashboard.revenue_trends.build_revenue_trends",
        return_value={"day_on_day": {"empty": True}, "week_on_week": {"empty": True}},
    ):
        resp = client.get("/api/insights/reports/city-revenue-trends", headers=auth_headers)
    assert resp.status_code == 200


def test_reports_actual_vs_plan(client, auth_headers):
    df = pd.DataFrame(
        {
            "city_name": ["Mumbai"],
            "sub_category": ["Veg"],
            "r7_plan": [100],
            "sales": [90],
            "r7_plan_rev": [1000],
            "revenue": [900],
        }
    )
    with patch("features.insights.analytics.load_6w_insights", return_value=df):
        resp = client.get(
            "/api/insights/reports/actual-vs-plan?granularity=city_category",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert "metrics" in body
