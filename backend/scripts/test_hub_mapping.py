#!/usr/bin/env python3
"""Tests for Hub Mapping (FF Automation Hub_Mapping tab) — validation, row keys, API routes."""

import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import create_access_token
from features.product_launch.hub_mapping_routes import (
    _normalize_hub_mapping_row,
    _validate_hub_mapping_row,
    portal_sheet_last_update,
)
from features.product_launch.watcher import _hub_mapping_row_key

client = TestClient(app)


def test_normalize_hub_mapping_row_aliases():
    raw = {
        "Hub ID": "2606",
        "Hub Name": "AGC",
        "City ID": "12",
        "City Name": "NCR",
        "Plan Flag": "A",
    }
    out = _normalize_hub_mapping_row(raw)
    assert out["hub_id"] == "2606"
    assert out["hub_name"] == "AGC"
    assert out["city_id"] == "12"
    assert out["city_name"] == "NCR"
    assert out["status"] == "A"
    print("OK: normalize aliases")


def test_validate_hub_mapping_row_ok():
    row = _validate_hub_mapping_row({
        "hub_id": "2606",
        "hub_name": "AGC",
        "city_id": "12",
        "city_name": "NCR",
        "status": "1",
    })
    assert row["status"] == "A"
    print("OK: validate row (status 1 -> A)")


def test_validate_hub_mapping_row_rejects_bad_id():
    try:
        _validate_hub_mapping_row({
            "hub_id": "abc",
            "hub_name": "AGC",
            "city_id": "12",
            "city_name": "NCR",
            "status": "A",
        })
        raise AssertionError("expected validation error")
    except Exception:
        print("OK: reject non-numeric hub_id")


def test_hub_mapping_row_key():
    headers = ["hub_id", "hub_name", "city_id", "city_name", "status"]
    row = {"hub_id": "2606", "hub_name": "AGC", "city_id": "12", "city_name": "NCR", "status": "A"}
    key = _hub_mapping_row_key(row, headers)
    assert key == "2606|agc"
    print("OK: row key hub_id|hub_name")


def test_hub_mapping_api_routes():
    user = {"id": 1, "role": "admin", "full_name": "Test Admin", "email": "admin@example.com"}
    headers = {"Authorization": f"Bearer {create_access_token(user)}"}

    mock_rows = [
        {"hub_id": "1", "hub_name": "NGC", "city_id": "10", "city_name": "NCR", "status": "A"},
        {"hub_id": "2", "hub_name": "AGC", "city_id": "10", "city_name": "NCR", "status": "A"},
    ]
    mock_status = {
        "change_detected": False,
        "change_history": [],
        "last_checked_at": "2026-07-17T10:00:00Z",
        "watcher_started": True,
        "poll_interval_seconds": 60,
    }

    with patch("features.product_launch.ff_masters.fetch_hub_mapping_snapshot", return_value=(mock_rows, list(mock_rows[0].keys()))), \
         patch("features.product_launch.watcher.get_hub_mapping_change_status", return_value=mock_status), \
         patch("features.product_launch.router._fetch_actual_drive_last_update", return_value={"ts": None, "user_id": None}), \
         patch("features.product_launch.hub_mapping_routes.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        mock_session_cls.return_value = mock_session
        with patch("core.database.engine.get_shared_database") as mock_db:
            mock_db.return_value.engine = MagicMock()
        resp = client.get("/api/new-product-launch/sync-new-hub/hub-mapping", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["row_count"] == 2
        assert "hub_id" in data["headers"]
        print("OK: GET hub-mapping")

        resp = client.get("/api/new-product-launch/sync-new-hub/hub-mapping/change-status", headers=headers)
        assert resp.status_code == 200, resp.text
        assert "change_history" in resp.json()
        print("OK: GET hub-mapping/change-status")

        resp = client.get("/api/new-product-launch/sync-new-hub/hub-mapping/last-update", headers=headers)
        assert resp.status_code == 200, resp.text
        print("OK: GET hub-mapping/last-update")

        resp = client.post("/api/new-product-launch/sync-new-hub/hub-mapping/dismiss-changes", headers=headers)
        assert resp.status_code == 200, resp.text
        print("OK: POST hub-mapping/dismiss-changes")

    # Append validation — bad row should 400 without touching sheet
    resp = client.post(
        "/api/new-product-launch/sync-new-hub/hub-mapping/append",
        headers=headers,
        json={"row": {"hub_id": "x", "hub_name": "T", "city_id": "1", "city_name": "NCR", "status": "A"}},
    )
    assert resp.status_code == 400, resp.text
    print("OK: append rejects invalid hub_id")

    # Deprecated alias still resolves
    with patch("features.product_launch.ff_masters.fetch_hub_mapping_snapshot", return_value=(mock_rows, list(mock_rows[0].keys()))):
        resp = client.get("/api/new-product-launch/sync-new-hub/hub-sku-master", headers=headers)
        assert resp.status_code == 200, resp.text
        print("OK: deprecated hub-sku-master alias")


def test_portal_last_update_prefers_audit_log_user():
    mock_drive = MagicMock(return_value={
        "ts": "2026-07-17T12:00:00Z",
        "user_id": "service@gserviceaccount.com",
    })
    mock_entry = MagicMock()
    mock_entry.user_id = "planner@licious.com"
    mock_entry.ts = datetime.fromisoformat("2026-07-17T11:59:30+00:00")

    with patch("core.database.engine.get_shared_database") as mock_db, \
         patch("features.product_launch.hub_mapping_routes.Session") as mock_session_cls:
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_entry
        mock_session_cls.return_value = mock_session
        mock_db.return_value.engine = MagicMock()

        result = portal_sheet_last_update(
            audit_action="append_hub_mapping",
            sheet_key="sheet-id",
            fetch_actual_drive_last_update=mock_drive,
        )
    assert result["user_id"] == "planner@licious.com"
    mock_drive.assert_not_called()
    print("OK: last-update uses portal audit user")


def test_clean_hub_mapping_df_drops_blanks():
    import pandas as pd
    from features.product_launch.ff_masters import _clean_hub_mapping_df

    df = pd.DataFrame([
        {"hub_id": "1", "hub_name": "NGC", "city_id": "10", "city_name": "NCR", "status": "A"},
        {"hub_id": "", "hub_name": "", "city_id": "", "city_name": "", "status": ""},
        {"hub_id": "2", "hub_name": "AGC", "city_id": "10", "city_name": "NCR", "status": "A"},
    ])
    cleaned = _clean_hub_mapping_df(df)
    assert len(cleaned) == 2
    print("OK: blank hub mapping rows dropped")


def test_npl_info_hub_mapping_url():
    user = {"id": 1, "role": "admin", "full_name": "Test Admin", "email": "admin@example.com"}
    headers = {"Authorization": f"Bearer {create_access_token(user)}"}
    resp = client.get("/api/new-product-launch/info", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("hub_mapping_sheet_url"), "hub_mapping_sheet_url should be set"
    assert "272986515" in data["hub_mapping_sheet_url"], "hub_mapping_sheet_url should open Hub_Mapping tab"
    print("OK: NPL info returns hub_mapping_sheet_url")


if __name__ == "__main__":
    test_normalize_hub_mapping_row_aliases()
    test_validate_hub_mapping_row_ok()
    test_validate_hub_mapping_row_rejects_bad_id()
    test_hub_mapping_row_key()
    test_clean_hub_mapping_df_drops_blanks()
    test_portal_last_update_prefers_audit_log_user()
    test_hub_mapping_api_routes()
    test_npl_info_hub_mapping_url()
    print("\nAll Hub Mapping tests passed.")
