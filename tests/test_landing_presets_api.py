"""Public landing style presets API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from web.backend.main import app


def test_public_landing_presets_lists_twenty():
    client = TestClient(app)
    res = client.get("/api/public/landing-presets")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] >= 20
    assert len(data["presets"]) >= 20
    first = data["presets"][0]
    assert "id" in first and "title" in first
    assert "neural_prompt" not in first
