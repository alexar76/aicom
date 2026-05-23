"""Pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ai_service_mesh.api import create_app
from ai_service_mesh.config import Settings


@pytest.fixture
def mesh_settings(tmp_path: Path) -> Settings:
    return Settings(
        env="test",
        cors_origins="http://test",
        api_token="test-api",
        admin_token="test-admin",
        data_dir=tmp_path / "data",
        rate_limit=10_000,
        hub_url="",
        skip_demo_capabilities=True,
        reject_demo_invoke_output=True,
        allow_localhost_agents=True,
    )


@pytest.fixture
def resolve_example_agent_hosts(request, monkeypatch):
    """Resolve *.example.com to a public IP in unit tests (opt-in, not global SSRF bypass)."""
    if request.node.get_closest_marker("integration"):
        return
    import socket

    real_getaddrinfo = socket.getaddrinfo

    def patched(host, port, *args, **kwargs):
        if host.endswith(".example.com"):
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 443))
            ]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", patched)


@pytest.fixture(autouse=True)
def stub_real_http(request, monkeypatch):
    """Unit tests stub HTTP; integration tests use real endpoints."""
    if request.node.get_closest_marker("integration"):
        return

    async def _preflight(endpoint_url: str):
        return True, 7, "health_ok"

    async def _preflight_hub(*_a, **_k):
        return True, 3, "hub_manifest_ok"

    async def _invoke_hub(*_a, **_k):
        return True, 25, "invoke_ok", {"success": True, "result": {"output": "unit_test"}}

    async def _invoke_direct(*_a, **_k):
        return True, 30, "invoke_ok", {"result": {"output": "unit_test"}}

    monkeypatch.setattr("ai_service_mesh.orchestrator.preflight_agent", _preflight)
    monkeypatch.setattr("ai_service_mesh.orchestrator.preflight_hub", _preflight_hub)
    monkeypatch.setattr("ai_service_mesh.orchestrator.invoke_via_hub", _invoke_hub)
    monkeypatch.setattr("ai_service_mesh.orchestrator.invoke_direct", _invoke_direct)


@pytest.fixture
def client(mesh_settings: Settings) -> TestClient:
    os.environ["MESH_ENV"] = "test"
    app = create_app(mesh_settings)
    with TestClient(app) as c:
        yield c
