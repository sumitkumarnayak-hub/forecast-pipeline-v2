"""Settings API tests."""
from __future__ import annotations

from unittest.mock import patch


def test_settings_bootstrap(client, auth_headers):
    with patch(
        "planning_suite.services.settings_service.get_settings_bootstrap",
        return_value={
            "profile": {"username": "admin", "role": "admin"},
            "preferences": {"preview_rows": 100},
            "env": {"smtp_configured": False},
            "recipients": [],
            "email_log": [],
            "session": {"has_session": False},
            "about": {"api_version": "2.0.0"},
        },
    ):
        resp = client.get("/api/settings/bootstrap", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "profile" in data
    assert "preferences" in data


def test_update_preferences(client, auth_headers):
    with patch.object(
        __import__("planning_suite.db.engine", fromlist=["Database"]).Database,
        "get_user_preferences",
        return_value={"email_notifications": True, "auto_sync_masters": False, "preview_rows": 100},
    ), patch.object(
        __import__("planning_suite.db.engine", fromlist=["Database"]).Database,
        "save_user_preferences",
    ) as mock_save:
        resp = client.post(
            "/api/settings/preferences",
            headers=auth_headers,
            json={"preview_rows": 200},
        )
    assert resp.status_code == 200
    mock_save.assert_called_once()


def test_session_system_details(client, auth_headers):
    with patch(
        "planning_suite.services.settings_service.save_session_system_details",
        return_value={"saved": True, "session_id": "abc123…", "system_details": {"client_browser_user_agent": "test"}},
    ):
        resp = client.post(
            "/api/settings/session/system-details",
            headers=auth_headers,
            json={"client_info": {"browser_user_agent": "test"}},
        )
    assert resp.status_code == 200
    assert resp.json()["saved"] is True


def test_email_log_admin(client, auth_headers):
    with patch(
        "planning_suite.services.settings_service._email_log_rows",
        return_value=[{"id": 1, "status": "sent", "subject": "Test"}],
    ):
        resp = client.get("/api/settings/email-log", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()["rows"]) == 1


def test_test_email_success(client, auth_headers):
    with patch(
        "planning_suite.services.email_service.send_test_email",
        return_value={"ok": True, "status": "sent", "recipients": ["a@b.com"]},
    ):
        resp = client.post(
            "/api/settings/test-email",
            headers=auth_headers,
            json={"to_email": "a@b.com", "message": "hello"},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_test_email_send_failure(client, auth_headers):
    with patch(
        "planning_suite.services.email_service.send_test_email",
        return_value={"ok": False, "status": "failed", "error": "SMTP timeout"},
    ):
        resp = client.post(
            "/api/settings/test-email",
            headers=auth_headers,
            json={"to_email": "test@example.com"},
        )
    assert resp.status_code == 500
    assert "SMTP timeout" in resp.json()["detail"]
