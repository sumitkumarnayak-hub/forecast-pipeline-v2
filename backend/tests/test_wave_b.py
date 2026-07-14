"""Wave B — NPL validation, master data CSV helper paths, NPL API smoke."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from features.product_launch.core import WEEKDAYS, validate_npl_upload



def test_validate_npl_upload_city_schema():
    rows = {
        "city_name": ["Mumbai"],
        "product_id": ["P001"],
        **{d: [10] for d in WEEKDAYS},
    }
    df = pd.DataFrame(rows)
    result = validate_npl_upload(df)
    assert result["valid"] is True
    assert result["type"] == "city"


def test_validate_npl_upload_hub_schema():
    rows = {
        "city_name": ["Mumbai"],
        "hub_name": ["HUB1"],
        "product_id": ["P001"],
        **{d: [5] for d in WEEKDAYS},
    }
    df = pd.DataFrame(rows)
    result = validate_npl_upload(df)
    assert result["valid"] is True
    assert result["type"] == "hub"


def test_validate_npl_upload_rejects_empty():
    df = pd.DataFrame({"foo": [1]})
    result = validate_npl_upload(df)
    assert result["valid"] is False
    assert result["errors"]


def test_npl_categories_endpoint(client, auth_headers, monkeypatch):
    from core.shared.api_cache import CacheNS, cache_invalidate

    import features.product_launch.wizard as wiz

    cache_invalidate(CacheNS.NPL_WIZARD, "categories")
    monkeypatch.setattr(wiz, "list_categories", lambda: ["A", "B"])
    resp = client.get("/api/new-product-launch/masters/categories", headers=auth_headers)
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert "A" in cats and "B" in cats


def test_npl_auto_sync_dry_run(client, auth_headers):
    class FakeResult:
        success = True
        products_found = 2
        rows_inserted = 0
        duplicates_skipped = 0
        masters_re_synced = False
        ph_rows_after = 100
        products_synced = ["P1"]
        error = ""

    with patch(
        "features.product_launch.auto_sync.run_new_product_launch_sync_cli",
        return_value=FakeResult(),
    ):
        resp = client.post(
            "/api/new-product-launch/auto-sync",
            json={"product_ids": [], "dry_run": True},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["dry_run"] is True
