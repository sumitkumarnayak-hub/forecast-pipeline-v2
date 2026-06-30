"""Smoke tests for remaining page APIs."""
from __future__ import annotations

from unittest.mock import patch


def test_wizard_context(client, auth_headers):
    with patch("planning_suite.services.npl_wizard.list_categories", return_value=["A"]):
        with patch("planning_suite.services.npl_wizard.list_cities", return_value=["Mumbai"]):
            resp = client.get("/api/new-product-launch/wizard/context", headers=auth_headers)
    assert resp.status_code == 200
    assert "categories" in resp.json()


def test_insights_executive_summary(client, auth_headers):
    with patch("planning_suite.services.dashboard_analytics.build_week_analytics", return_value={"kpis": {"x": 1}}):
        with patch("planning_suite.services.dashboard_analytics.list_available_weeks", return_value={"default_week": "Wk 1"}):
            resp = client.get("/api/insights/executive-summary", headers=auth_headers)
    assert resp.status_code == 200


def test_validation_logics(client, auth_headers):
    resp = client.get("/api/validation/logics", headers=auth_headers)
    assert resp.status_code == 200
    assert "validation_version" in resp.json()


def test_final_plan_latest_output(client, auth_headers):
    with patch(
        "planning_suite.services.final_plan_engine.get_latest_output_preview",
        return_value={"available": False},
    ):
        resp = client.get("/api/final-plan/latest-output", headers=auth_headers)
    assert resp.status_code == 200
