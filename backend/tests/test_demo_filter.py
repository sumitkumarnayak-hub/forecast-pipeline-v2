"""Demo filter API tests."""
from __future__ import annotations


def test_demo_filter_get(client, auth_headers):
    resp = client.get("/api/demo-filter", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "city" in data
    assert "cities" in data


def test_demo_filter_set_admin(client, auth_headers):
    resp = client.post(
        "/api/demo-filter",
        headers=auth_headers,
        json={"city": "Mumbai", "hubs": []},
    )
    assert resp.status_code == 200
    assert resp.json()["city"] == "Mumbai"
