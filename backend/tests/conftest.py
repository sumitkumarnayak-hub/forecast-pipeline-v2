"""Pytest fixtures for Planning Suite API tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.dependencies import create_access_token  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    token = create_access_token(
        {"id": 1, "username": "admin", "role": "admin", "full_name": "Test Admin"},
        remember_me=True,
    )
    return {"Authorization": f"Bearer {token}"}
