"""Wave A — baseline comparison, bulk plan, hub suggestion (unit + API smoke)."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from planning_suite.services import baseline_wave_ops as wave


def test_get_bulk_week_plan_returns_ten_weeks():
    plan = wave.get_bulk_week_plan()
    assert len(plan) == 10
    assert all("iso_week" in w and "start_date" in w for w in plan)


def test_load_hub_suggestion_pivot_from_cache(tmp_path, monkeypatch):
    cache = tmp_path / "hub_suggestion_latest.parquet"
    df = pd.DataFrame(
        {
            "city_name": ["Mumbai", "Mumbai"],
            "hub_name": ["H1", "H2"],
            "sku class prod": ["CatA", "CatA"],
            "day": ["Monday", "Tuesday"],
            "Base_plan": [100, 50],
        }
    )
    df.to_parquet(cache, index=False)
    monkeypatch.setattr(wave, "HUB_SUGGESTION_CACHE", cache)
    monkeypatch.setattr(wave, "OUTPUT_PATH", tmp_path)

    result = wave.load_hub_suggestion_for_approve(refresh=False)
    assert result["metrics"]["total_base_plan"] == 150
    assert result["pivot_rows"]
    assert "Total" in result["pivot_columns"]


def test_comparison_view_keys():
    assert set(wave.COMPARISON_VIEW_KEYS.keys()) == {
        "city-day",
        "city-cat-day",
        "hub-cat-day",
        "hub-day",
    }


def test_api_bulk_plan_endpoint(client, auth_headers):
    resp = client.get("/api/baseline/raw-data/bulk-plan", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10


def test_api_hub_suggestion_error_handling(client, auth_headers):
    with patch(
        "app.routers.baseline.wave.load_hub_suggestion_for_approve",
        side_effect=ValueError("empty"),
    ):
        resp = client.get("/api/baseline/approve/hub-suggestion", headers=auth_headers)
    assert resp.status_code == 400


def test_api_review_comparison_unknown_view(client, auth_headers):
    resp = client.get(
        "/api/baseline/review/comparison",
        params={"view": "invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


@patch("app.routers.baseline.wave.fetch_previous_baseline")
def test_api_fetch_previous_baseline(mock_fetch, client, auth_headers):
    mock_fetch.return_value = {"rows": 10, "target_week": 28}
    resp = client.post(
        "/api/baseline/generate/fetch-previous-baseline",
        json={"target_week": 28, "target_year": 2026},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["rows"] == 10
