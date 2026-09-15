from __future__ import annotations

import os
from pathlib import Path

from web.backend.services.commerce import CommerceService


def test_register_auth_and_order_flow(tmp_path: Path):
    os.environ["AIFACTORY_DATA_DIR"] = str(tmp_path)
    service = CommerceService(base_dir=str(tmp_path / "store"))

    customer = service.register_customer("buyer@example.com", "strong-pass-123")
    authed = service.authenticate_customer("buyer@example.com", "strong-pass-123")
    assert authed is not None
    assert authed["id"] == customer["id"]

    token = service.create_token(customer["id"], customer["email"])
    payload = service.decode_token(token)
    assert payload is not None
    assert payload["sub"] == customer["id"]

    order = service.create_order_and_license(
        customer_id=customer["id"],
        customer_email=customer["email"],
        payment_id="pay-test-1",
        product_id="prod-test",
        amount=12.0,
        currency="USDT",
        tx_hash="0xabc",
    )
    assert order["license_key"].startswith("lic-")
    orders = service.get_orders_for_customer(customer["id"])
    assert len(orders) == 1
    assert (tmp_path / "store" / "commerce.db").exists()


def test_build_download_archive(tmp_path: Path):
    os.environ["AIFACTORY_DATA_DIR"] = str(tmp_path)
    service = CommerceService(base_dir=str(tmp_path / "store"))

    code_dir = tmp_path / "code" / "prod-zip"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "index.html").write_text("<h1>Hello</h1>")

    order = {
        "id": "ord-1",
        "product_id": "prod-zip",
        "license_key": "lic-1",
    }
    archive = service.build_download_archive(order)
    assert archive.exists()


def test_stripe_webhook_idempotent_plan_upgrade(tmp_path: Path):
    os.environ["AIFACTORY_DATA_DIR"] = str(tmp_path)
    service = CommerceService(base_dir=str(tmp_path / "store"))
    customer = service.register_customer("stripe@example.com", "strong-pass-123")

    service.save_stripe_checkout_session(
        session_id="cs_test_123",
        customer_id=customer["id"],
        customer_email=customer["email"],
        target_plan="maker",
        amount_total=1900,
        currency="usd",
        status="open",
        payment_status="unpaid",
        idempotency_key="idem-1",
    )
    first = service.apply_stripe_webhook_event(
        event_id="evt_1",
        event_type="checkout.session.completed",
        session_id="cs_test_123",
        payment_status="paid",
        session_status="complete",
        customer_email=customer["email"],
        metadata={"target_plan": "maker"},
    )
    second = service.apply_stripe_webhook_event(
        event_id="evt_1",
        event_type="checkout.session.completed",
        session_id="cs_test_123",
        payment_status="paid",
        session_status="complete",
        customer_email=customer["email"],
        metadata={"target_plan": "maker"},
    )

    profile = service.get_customer(customer["id"]) or {}
    assert first["already_processed"] is False
    assert second["already_processed"] is True
    assert profile.get("plan") == "maker"
