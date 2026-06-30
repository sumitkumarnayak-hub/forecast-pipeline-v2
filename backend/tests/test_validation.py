"""Validation API tests."""
from __future__ import annotations

import io
from unittest.mock import patch

import pandas as pd


def test_validation_bootstrap(client, auth_headers):
    with patch(
        "planning_suite.services.validation_service.get_validation_bootstrap",
        return_value={"logics": {"validation_version": "1"}, "outputs": {}, "history_count": 0},
    ):
        resp = client.get("/api/validation/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    assert "logics" in resp.json()


def test_validate_input_raw_csv(client, auth_headers):
    df = pd.DataFrame(
        {
            "process_dt": ["2026-01-01"],
            "product_id": ["P1"],
            "hub_name": ["H1"],
            "city_name": ["Mumbai"],
            "Sales (qty)": [10],
            "sub category": ["Veg"],
            "day": ["Mon"],
        }
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    content = buf.getvalue().encode()

    resp = client.post(
        "/api/validation/validate-input?data_type=raw_data",
        headers=auth_headers,
        files={"file": ("raw.csv", content, "text/csv")},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_validate_master_ph(client, auth_headers):
    with patch(
        "planning_suite.services.validation_service.validate_master_by_id",
        return_value={"master_id": "product_hub_master", "valid": True, "error_count": 0, "errors": []},
    ):
        resp = client.post(
            "/api/validation/validate-master?master_id=product_hub_master",
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


def test_validation_history(client, auth_headers):
    resp = client.get("/api/validation/history", headers=auth_headers)
    assert resp.status_code == 200
    assert "rows" in resp.json()
