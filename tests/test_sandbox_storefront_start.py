"""Public storefront sandbox start must not require admin JWT."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_storefront_start_without_auth(client):
  pid = "prod-demo-market-01"
  with patch(
    "web.backend.api.sandbox._storefront_allows_sandbox_preview",
    return_value=True,
  ), patch(
    "web.backend.api.sandbox._start_sandbox_for_product",
    return_value={
      "sandbox_id": "sandbox-test123",
      "status": "running",
      "url": "/api/sandbox/view/sandbox-test123",
      "expires_at": 9999999999.0,
    },
  ), patch(
    "web.backend.api.sandbox._enforce_storefront_start_rate_limit",
  ):
    r = client.post(f"/api/sandbox/storefront/start/{pid}")
  assert r.status_code == 200
  assert r.json()["sandbox_id"] == "sandbox-test123"


def test_storefront_start_allowed_in_public_demo_mode(client, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DEMO_READONLY", "1")
    pid = "prod-demo-landing-studio"
    with patch(
        "web.backend.api.sandbox._storefront_allows_sandbox_preview",
        return_value=True,
    ), patch(
        "web.backend.api.sandbox._start_sandbox_for_product",
        return_value={
            "sandbox_id": "sandbox-demo1",
            "status": "running",
            "url": "/api/sandbox/view/sandbox-demo1",
            "expires_at": 9999999999.0,
        },
    ), patch(
        "web.backend.api.sandbox._enforce_storefront_start_rate_limit",
    ):
        r = client.post(f"/api/sandbox/storefront/start/{pid}")
    assert r.status_code == 200
    assert r.json()["sandbox_id"] == "sandbox-demo1"


def test_storefront_start_rejects_unlisted_product(client):
  with patch(
    "web.backend.api.sandbox._storefront_allows_sandbox_preview",
    return_value=False,
  ), patch(
    "web.backend.api.sandbox._enforce_storefront_start_rate_limit",
  ):
    r = client.post("/api/sandbox/storefront/start/prod-not-on-shelf")
  assert r.status_code == 404
