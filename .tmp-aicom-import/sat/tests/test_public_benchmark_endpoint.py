"""Public /api/benchmark must never 500 — storefront and /benchmark page depend on it."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from web.backend.main import app

    return TestClient(app)


def test_public_benchmark_returns_200_even_when_proxy_fails(client: TestClient):
    with patch(
        "web.backend.main._investor_metrics_pipeline_storefront_proxy",
        side_effect=RuntimeError("simulated failure"),
    ):
        r = client.get("/api/benchmark")
    assert r.status_code == 200
    body = r.json()
    assert "investor_metrics" in body
    assert body.get("degraded") is True
