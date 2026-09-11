"""HTTP journey: register → login → demo-notes CRUD → logout (+ telemetry evolution signal)."""

from __future__ import annotations

import json

import pytest

from web.backend.services.commerce import CommerceService


@pytest.fixture
def journey_commerce(tmp_path, monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only-do-not-use-prod")
    svc = CommerceService(base_dir=str(tmp_path / "store"))
    import web.backend.api.customer as cust

    monkeypatch.setattr(cust, "commerce", svc)
    return svc


@pytest.fixture
def client(journey_commerce):
    from fastapi.testclient import TestClient

    from web.backend.main import app

    with TestClient(app) as c:
        root = journey_commerce.base.parent / "telemetry_root"
        root.mkdir(parents=True, exist_ok=True)
        c.app.state.telemetry.data_root = root
        yield c


def test_customer_journey_register_login_crud_logout(client):
    email = "journey-e2e@example.test"
    password = "password123"

    r = client.post("/api/customer/register", json={"email": email, "password": password})
    assert r.status_code == 200
    reg = r.json()
    token_register = reg["access_token"]

    r = client.post("/api/customer/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token_login = r.json()["access_token"]
    assert isinstance(token_login, str) and len(token_login) > 10

    auth_reg = {"Authorization": f"Bearer {token_register}"}
    auth_login = {"Authorization": f"Bearer {token_login}"}

    r = client.get("/api/customer/me", headers=auth_reg)
    assert r.status_code == 200
    assert r.json().get("email") == email

    r = client.post("/api/customer/demo-notes", headers=auth_reg, json={"title": "First", "body": "alpha"})
    assert r.status_code == 200
    note_id = r.json()["note"]["id"]

    r = client.get("/api/customer/demo-notes", headers=auth_login)
    assert r.status_code == 200
    assert r.json()["count"] == 1
    assert r.json()["notes"][0]["title"] == "First"

    r = client.patch(
        f"/api/customer/demo-notes/{note_id}",
        headers=auth_login,
        json={"title": "Updated", "body": "beta"},
    )
    assert r.status_code == 200
    assert r.json()["note"]["title"] == "Updated"

    r = client.delete(f"/api/customer/demo-notes/{note_id}", headers=auth_reg)
    assert r.status_code == 200

    r = client.get("/api/customer/demo-notes", headers=auth_login)
    assert r.status_code == 200
    assert r.json()["count"] == 0

    r = client.post("/api/customer/logout")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_customer_register_duplicate(client):
    email = "dup@example.test"
    password = "password123"
    assert client.post("/api/customer/register", json={"email": email, "password": password}).status_code == 200
    r = client.post("/api/customer/register", json={"email": email, "password": password})
    assert r.status_code == 409


def test_evolution_signal_endpoint(client):
    pid = "prod-testtelemetry01"
    r = client.post(
        "/api/telemetry/evolution-signal",
        json={
            "product_id": pid,
            "signal": "nps",
            "weight": 0.8,
            "context": {"bucket": "promoter"},
        },
    )
    assert r.status_code == 200
    assert r.json().get("ok") is True

    root = client.app.state.telemetry.data_root
    files = list((root / pid).glob("telemetry_*.jsonl"))
    assert files, "telemetry jsonl should exist"
    last = files[-1].read_text(encoding="utf-8").strip().splitlines()[-1]
    row = json.loads(last)
    assert row.get("event_type") == "evolution_signal"
    assert row.get("data", {}).get("signal") == "nps"
