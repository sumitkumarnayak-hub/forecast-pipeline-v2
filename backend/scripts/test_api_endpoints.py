#!/usr/bin/env python3
"""
Test script for product launch, hub launch, and auth endpoints.
Uses FastAPI TestClient to test routing and handler integration.
"""

import sys
from pathlib import Path
from unittest.mock import patch

# Make sure backend/ is in path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.dependencies import create_access_token

client = TestClient(app)


def test_auth():
    print("Testing Auth Endpoints...")
    # Mock database auth lookup
    user_payload = {"id": 1, "role": "admin", "full_name": "Test Admin", "email": "admin@example.com"}
    token = create_access_token(user_payload)
    
    # Verify token decoding works correctly
    headers = {"Authorization": f"Bearer {token}"}
    
    # We test a health check first
    resp = client.get("/api/health")
    assert resp.status_code == 200, f"Health check failed: {resp.text}"
    print("OK: Health Check Passed")
    
    # Verify route with auth guard
    resp = client.get("/api/validation/logics", headers=headers)
    assert resp.status_code == 200, f"Auth verification failed: {resp.text}"
    print("OK: Authenticated Access Passed")


def test_product_launch():
    print("Testing Product Launch Endpoints...")
    user_payload = {"id": 1, "role": "admin", "full_name": "Test Admin", "email": "admin@example.com"}
    token = create_access_token(user_payload)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test wizard/context endpoint
    mock_payload = {
        "categories": ["Groceries", "Beverages"],
        "cities": ["Mumbai", "Delhi"],
        "earliest_launch_date": "2026-07-20"
    }
    with patch("features.product_launch.wizard.wizard_context_payload", return_value=mock_payload):
        resp = client.get("/api/new-product-launch/wizard/context", headers=headers)
        assert resp.status_code == 200, f"Wizard context retrieval failed: {resp.text}"
        data = resp.json()
        print("DEBUG: wizard context data = ", data)
        assert "categories" in data and "cities" in data
        assert "Groceries" in data["categories"]
        assert "Mumbai" in data["cities"]
        print("OK: Product Launch Wizard Context Retrieval Passed")


def test_hub_launch():
    print("Testing Hub Launch Endpoints...")
    user_payload = {"id": 1, "role": "admin", "full_name": "Test Admin", "email": "admin@example.com"}
    token = create_access_token(user_payload)
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test hub launch dry-run/auto-sync endpoint
    # Mocks run_new_hub_launch_sync to verify call integration and route resolution
    class FakeResult:
        success = True
        mappings_found = 1
        rows_inserted = 1
        duplicates_skipped = 0
        masters_re_synced = False
        mapping_report = ["Report line"]
        error = ""

    with patch("features.hub_launch.auto_sync.run_new_hub_launch_sync", return_value=FakeResult()):
        resp = client.post("/api/master-data/new-hub-sync/confirm", headers=headers)
        assert resp.status_code == 200, f"Hub launch auto-sync route failed: {resp.text}"
        data = resp.json()
        assert "rows_inserted" in data
        print("OK: Hub Launch Auto-Sync Endpoint Passed")


def main():
    try:
        test_auth()
        test_product_launch()
        test_hub_launch()
        print("\n==================================================")
        print(" ALL ENDPOINT TESTS PASSED SUCCESSFULLY! ")
        print("==================================================")
    except AssertionError as e:
        print(f"Test assertion failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error running tests: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
