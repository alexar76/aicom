"""Regression tests for payment price control (security audit)."""

from __future__ import annotations

import uuid
from collections import defaultdict, deque

import pytest
from fastapi.testclient import TestClient

from web.backend.services.commerce import CommerceService


@pytest.fixture
def pay_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "1000")
    # The crypto master switch defaults OFF ecosystem-wide, and with it off the payment
    # endpoints answer 503 / `crypto_disabled` before any price or tx-hash logic runs —
    # which is exactly what these tests are about. Enable it here, the way
    # `test_ai_market_channel_settlement.py` and `test_ai_market_protocol_v1_admin.py`
    # already do; the "crypto is off" behaviour has its own dedicated cases.
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    # `_ensure_recipient_configured` reads the resolved recipient (config, else
    # `AIMARKET_PAYMENT_RECIPIENT`) and answers 503 for a placeholder, so patching
    # `pay_mod.RECIPIENT_ADDRESS_EVM` alone stopped being enough — payment creation
    # refused before reaching anything these tests measure.
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x" + "11" * 20)
    monkeypatch.setattr("web.backend.api.customer._register_attempts", defaultdict(deque))
    store = str(tmp_path / "data" / "store")
    svc = CommerceService(base_dir=store)

    import web.backend.api.customer as customer_mod
    import web.backend.api.payment as pay_mod
    import web.backend.services.customer_auth as customer_auth_mod

    # See the note in tests/test_payment_confirm_pending_api.py: the recipient is
    # resolved at module import, so re-resolve it after setting the env var.
    pay_mod._reload_addresses_from_config()
    pay_mod._pending_payments.clear()
    monkeypatch.setattr(customer_mod, "commerce", svc)
    monkeypatch.setattr(customer_auth_mod, "_commerce", svc)
    monkeypatch.setattr(pay_mod, "commerce", svc)
    # A real settlement wallet must be configured or payment creation now fails (F1).
    monkeypatch.setattr(pay_mod, "RECIPIENT_ADDRESS_EVM", "0x" + "11" * 20)

    from web.backend.main import app

    with TestClient(app) as client:
        yield client, pay_mod


def test_create_payment_ignores_client_amount(pay_client, monkeypatch):
    client, pay_mod = pay_client
    monkeypatch.setattr(pay_mod, "checkout_usdt_from_sales_file", lambda pid, **kw: 49.99)

    reg = client.post(
        "/api/customer/register",
        json={"email": f"buyer-{uuid.uuid4().hex[:8]}@test.local", "password": "password12345"},
    )
    assert reg.status_code == 200, reg.text
    auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    r = client.post(
        "/api/payment/create",
        headers=auth,
        json={
            "product_id": "prod-9388c62f0666",
            "chain": "base",
            "token": "USDT",
            "amount": 0.01,
        },
    )
    assert r.status_code == 422


def test_confirm_payment_revalidates_catalog_price(pay_client, monkeypatch):
    client, pay_mod = pay_client
    monkeypatch.setenv("AIFACTORY_PAYMENT_VERIFY_STUB", "1")
    monkeypatch.setattr(pay_mod, "checkout_usdt_from_sales_file", lambda pid, **kw: 49.99)

    reg = client.post(
        "/api/customer/register",
        json={"email": f"confirm-{uuid.uuid4().hex[:8]}@test.local", "password": "password12345"},
    )
    auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    create = client.post(
        "/api/payment/create",
        headers=auth,
        json={"product_id": "prod-9388c62f0666", "chain": "base", "token": "USDT"},
    )
    assert create.status_code == 200
    payment_id = create.json()["payment_id"]
    assert create.json()["amount"] == 49.99

    pay_mod._pending_payments[payment_id]["amount"] = 0.01
    pay_mod._persist_pending_payments()

    tx = "0x" + "cd" * 32
    # `confirm_payment` takes `Depends(require_customer)`. Without the header this got
    # 401 and never reached the catalog re-validation this test exists to pin.
    r = client.post(
        f"/api/payment/confirm/{payment_id}?test_confirmations={pay_mod.MIN_CONFIRMATIONS}",
        headers=auth,
        json={"tx_hash": tx},
    )
    # Confirm must revalidate against the catalog price: the tampered-down stored amount
    # (0.01) no longer matches the catalog (49.99), so the payment is rejected outright
    # rather than verifying an under-payment.
    assert r.status_code == 400
    body = str(r.json()).lower()
    assert "amount" in body and "catalog" in body


def test_channel_open_rejects_forged_tx_when_demo_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "0")
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "1000")
    # Crypto master switch: off by default, and these endpoints refuse before
    # reaching the logic under test. See the note on the `pay_client` fixture.
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    # `_ensure_recipient_configured` reads the resolved recipient (config, else
    # `AIMARKET_PAYMENT_RECIPIENT`) and answers 503 for a placeholder, so patching
    # `pay_mod.RECIPIENT_ADDRESS_EVM` alone stopped being enough — payment creation
    # refused before reaching anything these tests measure.
    monkeypatch.setenv("AIMARKET_PAYMENT_RECIPIENT", "0x" + "11" * 20)
    monkeypatch.setattr("web.backend.api.customer._register_attempts", defaultdict(deque))

    from web.backend.main import app

    client = TestClient(app)
    reg = client.post(
        "/api/customer/register",
        json={"email": f"ch-{uuid.uuid4().hex[:8]}@test.local", "password": "password12345"},
    )
    assert reg.status_code == 200, reg.text
    auth = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    r = client.post(
        "/ai-market/channel/open",
        headers=auth,
        json={"deposit_usd": 100.0, "tx_hash": "0xdeadbeef"},
    )
    assert r.status_code == 400
    assert r.json().get("error") in {"tx_not_verified", "tx_hash_required"}
