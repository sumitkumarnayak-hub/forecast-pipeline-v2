"""Final Plan API — bootstrap, inputs, city mapping, upload."""
from __future__ import annotations

import io
from unittest.mock import patch

import pandas as pd


def test_final_plan_bootstrap(client, auth_headers):
    mock_inputs = {
        "ready": False,
        "required_ok": False,
        "inv_logic_ok": False,
        "inv_logic_count": 0,
        "inv_logic_files": [],
        "checks": [],
    }
    with patch("planning_suite.services.pipeline_state.is_baseline_approved", return_value=True):
        with patch("planning_suite.services.final_plan_inputs.get_inputs_status", return_value=mock_inputs):
            with patch(
                "planning_suite.services.final_plan_inputs.load_city_mapping_preview",
                return_value={"available": False, "rows": [], "columns": []},
            ):
                with patch(
                    "planning_suite.services.final_plan_engine.load_hub_suggestions_preview",
                    return_value={"rows": [], "columns": []},
                ):
                    with patch(
                        "planning_suite.services.final_plan_engine.get_latest_output_preview",
                        return_value={"available": False},
                    ):
                        resp = client.get("/api/final-plan/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["baseline_approved"] is True
    assert "inputs" in body
    assert "city_mapping" in body
    assert "runs" in body


def test_final_plan_inputs_status(client, auth_headers):
    with patch(
        "planning_suite.services.final_plan_inputs.get_inputs_status",
        return_value={"ready": True, "checks": []},
    ):
        resp = client.get("/api/final-plan/inputs-status", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


def test_sync_city_mapping(client, auth_headers):
    with patch(
        "planning_suite.services.final_plan_inputs.sync_city_mapping_to_folder",
        return_value={"detail": "Saved 10 rows", "rows": 10},
    ):
        resp = client.post("/api/final-plan/sync-city-mapping", headers=auth_headers)
    assert resp.status_code == 200
    assert "Saved" in resp.json()["detail"]


def test_upload_festive_input(client, auth_headers):
    df = pd.DataFrame({"city_name": ["Mumbai"], "hub_name": ["H1"]})
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    buf.seek(0)

    with patch(
        "planning_suite.services.final_plan_inputs.save_uploaded_input",
        return_value={"detail": "Saved Festive.xlsx (1 rows)", "rows": 1},
    ) as mock_save:
        resp = client.post(
            "/api/final-plan/upload-input?kind=festive",
            headers=auth_headers,
            files={"file": ("festive.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert resp.status_code == 200
    mock_save.assert_called_once()
    assert mock_save.call_args.kwargs["kind"] == "festive"


def test_run_final_plan_blocks_when_inputs_missing(client, auth_headers):
    with patch("planning_suite.services.pipeline_state.is_baseline_approved", return_value=True):
        with patch(
            "planning_suite.services.final_plan_inputs.get_inputs_status",
            return_value={"ready": False, "inv_logic_ok": False, "checks": [{"label": "Festive.xlsx", "required": True, "exists": False}]},
        ):
            resp = client.post("/api/final-plan/run", headers=auth_headers)
    assert resp.status_code == 400
    assert "not ready" in resp.json()["detail"].lower()
