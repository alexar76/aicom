"""Production aliases must all prevent accidental disclosure of exception details."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.backend.main import global_exception_handler, safe_error

_SECRET = "private-host-path /srv/secrets/test-only.key"


@pytest.fixture(autouse=True)
def clean_production_env(monkeypatch):
    for key in ("AIFACTORY_PROD", "AIFACTORY_PRODUCTION", "AIFACTORY_ENV", "AIFACTORY_EXPOSE_ERROR_DETAILS"):
        monkeypatch.delenv(key, raising=False)


def _client():
    app = FastAPI(exception_handlers={Exception: global_exception_handler})

    @app.get("/unexpected")
    def unexpected():
        raise RuntimeError(_SECRET)

    @app.get("/handled")
    def handled():
        raise safe_error(RuntimeError(_SECRET), log_message="test", client_detail="Operation failed")

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("key,value", [
    ("AIFACTORY_PROD", "1"), ("AIFACTORY_PROD", "true"), ("AIFACTORY_PROD", " YES "),
    ("AIFACTORY_PROD", "on"), ("AIFACTORY_PRODUCTION", "true"),
    ("AIFACTORY_ENV", "production"), ("AIFACTORY_ENV", "prod"), ("AIFACTORY_ENV", " LIVE "),
])
def test_production_never_echoes_details_even_with_debug_enabled(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    monkeypatch.setenv("AIFACTORY_EXPOSE_ERROR_DETAILS", "true")
    with _client() as client:
        for route in ("/unexpected", "/handled"):
            response = client.get(route)
            assert response.status_code == 500
            assert _SECRET not in response.text
            assert "message" not in response.json()


def test_details_are_hidden_by_default():
    with _client() as client:
        assert client.get("/unexpected").json() == {"detail": "Internal server error"}
        assert client.get("/handled").json() == {"detail": "Operation failed"}


def test_explicit_development_debug_still_works(monkeypatch):
    monkeypatch.setenv("AIFACTORY_EXPOSE_ERROR_DETAILS", "true")
    with _client() as client:
        assert client.get("/unexpected").json()["message"] == _SECRET
        assert _SECRET in client.get("/handled").json()["detail"]
