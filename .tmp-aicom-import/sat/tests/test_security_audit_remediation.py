"""Regression tests for security audit findings (2026-05)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from web.backend.main import app
from web.backend.services.sandbox_preview_auth import sanitize_git_remote_line


@pytest.fixture
def client():
    return TestClient(app)


def test_sanitize_git_remote_strips_credentials():
    line = "origin\thttps://ghp_secret@github.com/org/repo.git (fetch)"
    assert "ghp_secret" not in sanitize_git_remote_line(line)
    assert "https://github.com/org/repo.git" in sanitize_git_remote_line(line)


def test_git_status_requires_admin(client):
    r = client.get("/api/sandbox/git/status/prod-demo-market-01")
    assert r.status_code != 200


def test_sandbox_view_with_preview_token(client):
    sid = "sandbox-" + uuid.uuid4().hex
    token = "preview-view-token-value-32chars-ok"
    import web.backend.api.sandbox as sb_mod

    sb_mod._active_sandboxes[sid] = {
        "id": sid,
        "product_id": "prod-demo-landing-studio",
        "preview_token": token,
        "status": "running",
    }
    denied = client.get(f"/api/sandbox/view/{sid}")
    assert denied.status_code == 403
    ok = client.get(f"/api/sandbox/view/{sid}", params={"preview_token": token})
    assert ok.status_code == 200
    assert "Sandbox Demo" in ok.text or "Sandbox:" in ok.text
    sb_mod._active_sandboxes.pop(sid, None)


def test_sandbox_backend_proxy_requires_preview_token(client):
    sid = "sandbox-" + uuid.uuid4().hex
    token = "preview-test-token-value"
    import web.backend.api.sandbox as sb_mod

    sb_mod._active_sandboxes[sid] = {
        "id": sid,
        "product_id": "prod-test",
        "preview_token": token,
        "status": "running",
        "backend_preview_port": 59999,
    }
    denied = client.get(f"/api/sandbox/backend/{sid}/")
    assert denied.status_code == 403
    ok = client.get(
        f"/api/sandbox/backend/{sid}/",
        headers={"X-Sandbox-Preview-Token": token},
    )
    assert ok.status_code in (200, 502, 503, 504)
    sb_mod._active_sandboxes.pop(sid, None)


def test_payment_status_requires_customer_auth(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    import web.backend.api.payment as pay_mod

    pay_mod._pending_payments["pay-deadbeef"] = {
        "payment_id": "pay-deadbeef",
        "customer_id": "cust-1",
        "customer_email": "leak@example.test",
        "status": "pending",
        "product_id": "prod-x",
        "amount": 1.0,
        "currency": "USDT",
        "chain": "base",
        "wallet_address": "0xabc",
        "created_at": 0,
        "expires_at": 9999999999,
    }
    anon = client.get("/api/payment/status/pay-deadbeef")
    assert anon.status_code == 401
