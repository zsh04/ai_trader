from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture(scope="module")
def client():
    return TestClient(main_module.app)


def test_health_live_smoke(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True
