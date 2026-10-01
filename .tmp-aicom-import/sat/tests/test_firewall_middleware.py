"""Firewall HTTP middleware — rate limits and optional ACL."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from security.firewall import FirewallManager
from web.backend.middleware.firewall_http import firewall_http_middleware


@pytest.fixture
def firewall_app(tmp_path, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.delenv("AIFACTORY_FIREWALL_ENFORCE", raising=False)
    app = FastAPI()
    fw = FirewallManager(str(tmp_path / "firewall_rules.json"))
    fw.clear_rules()
    fw.set_rate_limit(3, 60)
    app.state.firewall = fw
    app.middleware("http")(firewall_http_middleware)

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    return app


def test_firewall_rate_limits_after_threshold(firewall_app: FastAPI) -> None:
    client = TestClient(firewall_app)
    for _ in range(3):
        assert client.get("/api/health").status_code == 200
    blocked = client.get("/api/health")
    assert blocked.status_code == 403
    assert blocked.json().get("reason") == "rate_limited"


def test_firewall_enforce_mode_blocks_unknown_ip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFACTORY_FIREWALL_ENFORCE", "1")
    app = FastAPI()
    fw = FirewallManager(str(tmp_path / "fw_enforce.json"))
    fw.clear_rules()
    app.state.firewall = fw
    app.middleware("http")(firewall_http_middleware)

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 403
