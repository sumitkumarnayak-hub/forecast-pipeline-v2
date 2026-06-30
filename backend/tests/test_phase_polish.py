"""Phase polish — preflight, new hub sync, NPL product picker APIs."""
from __future__ import annotations

from unittest.mock import patch


def test_generate_preflight_endpoint(client, auth_headers):
    resp = client.get("/api/baseline/generate/preflight", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "checks" in body
    assert isinstance(body["checks"], list)
    assert len(body["checks"]) >= 3
    assert "ready" in body


def test_new_hub_sync_preview_empty(client, auth_headers, monkeypatch):
    class FakeGsm:
        def ensure_pipeline_params_hub_changes_tab(self):
            pass

        def read_hub_changes_table(self):
            import pandas as pd

            return pd.DataFrame()

    monkeypatch.setattr(
        "planning_suite.services.sheets_session.get_sheets_manager",
        lambda: FakeGsm(),
    )
    resp = client.post("/api/master-data/new-hub-sync/preview", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["mappings_found"] == 0


def test_npl_product_ids_endpoint(client, auth_headers, monkeypatch):
    import pandas as pd

    fake = pd.DataFrame(
        {
            "Product ID": ["P001", "P002"],
            "Product Name": ["Alpha", "Beta"],
            "Sub-category": ["Snacks", "Snacks"],
        }
    )
    monkeypatch.setattr(
        "planning_suite.services.npl_wizard.load_product_master",
        lambda: fake,
    )
    resp = client.get("/api/new-product-launch/masters/product-ids", headers=auth_headers)
    assert resp.status_code == 200
    products = resp.json()["products"]
    assert len(products) == 2
    assert products[0]["product_id"] == "P001"
