"""Payment confirm: 409 pending_confirmation then single license on finalize."""

from __future__ import annotations

import pytest

from web.backend.services.commerce import CommerceService


@pytest.fixture
def pay_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_PAYMENT_TESTNET", "1")
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "1")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    CommerceService(base_dir=str(tmp_path / "data" / "store"))

    import importlib
    import web.backend.api.payment as pay_mod

    importlib.reload(pay_mod)
    monkeypatch.setattr(pay_mod, "commerce", CommerceService(base_dir=str(tmp_path / "data" / "store")))

    from fastapi.testclient import TestClient
    from web.backend.main import app

    with TestClient(app) as c:
        yield c, pay_mod


def test_confirm_pending_then_license_once(pay_client):
    client, pay_mod = pay_client
    email = "pay-pending@example.test"
    password = "password12345"
    reg = client.post("/api/customer/register", json={"email": email, "password": password})
    assert reg.status_code == 200
    token = reg.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    create = client.post(
        "/api/payment/create",
        headers=auth,
        json={
            "product_id": "prod-9388c62f0666",
            "chain": "base",
            "token": "ETH",
            "amount": 0.01,
        },
    )
    assert create.status_code == 200
    payment_id = create.json()["payment_id"]
    tx = "0x" + "ab" * 32

    r1 = client.post(
        f"/api/payment/confirm/{payment_id}?test_confirmations=1",
        json={"tx_hash": tx},
    )
    assert r1.status_code == 409
    body = r1.json()["detail"]
    assert body["status"] == "pending_confirmation"
    assert body["confirmations"] == 1
    assert body["required_confirmations"] == pay_mod.MIN_CONFIRMATIONS

    status = client.get(f"/api/payment/status/{payment_id}")
    assert status.json()["status"] == "pending_confirmation"

    r2 = client.post(
        f"/api/payment/confirm/{payment_id}?test_confirmations={pay_mod.MIN_CONFIRMATIONS}",
        json={"tx_hash": tx},
    )
    assert r2.status_code == 200
    out = r2.json()
    assert out["status"] == "confirmed"
    license_key = out["license_key"]
    assert license_key

    r3 = client.post(
        f"/api/payment/confirm/{payment_id}?test_confirmations={pay_mod.MIN_CONFIRMATIONS}",
        json={"tx_hash": tx},
    )
    assert r3.status_code == 200
    assert r3.json()["license_key"] == license_key

    orders = client.get("/api/customer/orders", headers=auth)
    assert orders.status_code == 200
    assert orders.json()["count"] == 1
