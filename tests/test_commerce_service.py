from __future__ import annotations

import pytest

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
        amount_total=1900,
        currency="usd",
    )
    second = service.apply_stripe_webhook_event(
        event_id="evt_1",
        event_type="checkout.session.completed",
        session_id="cs_test_123",
        payment_status="paid",
        session_status="complete",
        amount_total=1900,
        currency="usd",
    )

    profile = service.get_customer(customer["id"]) or {}
    assert first["already_processed"] is False
    assert second["already_processed"] is True
    assert profile.get("plan") == "maker"


def test_stripe_webhook_rejects_unbound_or_mismatched_payment(tmp_path: Path):
    service = CommerceService(base_dir=tmp_path / "store")
    customer = service.register_customer("stripe@example.test", "strong-pass-123")
    event = dict(event_id="evt_1", event_type="checkout.session.completed",
                 session_id="cs_test_123", payment_status="paid", session_status="complete",
                 amount_total=1900, currency="usd")
    with pytest.raises(LookupError):
        service.apply_stripe_webhook_event(**event)
    service.save_stripe_checkout_session(
        session_id=event["session_id"], customer_id=customer["id"],
        customer_email=customer["email"], target_plan="maker", amount_total=1900,
        currency="usd", status="open", payment_status="unpaid",
    )
    with pytest.raises(ValueError):
        service.apply_stripe_webhook_event(**{**event, "amount_total": 1})
    assert not service.apply_stripe_webhook_event(
        **{**event, "event_type": "charge.updated"}
    )["plan_upgraded"]
    assert service.apply_stripe_webhook_event(**event)["plan_upgraded"]
    assert service.apply_stripe_webhook_event(
        **{**event, "event_id": "evt_2"}
    )["already_processed"]


# ── audit 2026-11-11, desks-stripe-7: a refund or chargeback took nothing back ──────────
def _paid_checkout(service, customer, session_id, plan, pi, amount=1900):
    service.save_stripe_checkout_session(
        session_id=session_id, customer_id=customer["id"], customer_email=customer["email"],
        target_plan=plan, amount_total=amount, currency="usd", status="open", payment_status="unpaid")
    assert service.apply_stripe_webhook_event(
        event_id=f"evt_{session_id}", event_type="checkout.session.completed", session_id=session_id,
        payment_status="paid", session_status="complete", amount_total=amount, currency="usd",
        payment_intent=pi)["plan_upgraded"] in (True, False)


def test_a_full_refund_takes_the_plan_back(tmp_path: Path):
    service = CommerceService(base_dir=tmp_path / "store")
    customer = service.register_customer("refund@example.test", "strong-pass-123")
    _paid_checkout(service, customer, "cs_test_r1", "enterprise", "pi_r1", 49900)
    assert service.get_customer(customer["id"])["plan"] == "enterprise"
    out = service.apply_stripe_reversal("evt_ref1", "charge.refunded", payment_intent="pi_r1")
    assert out["plan_reverted"] is True and out["reversal"] == "refunded"
    assert service.get_customer(customer["id"])["plan"] == "free"
    assert service.apply_stripe_reversal("evt_ref1", "charge.refunded", payment_intent="pi_r1")["already_processed"]


def test_a_dispute_falls_back_to_the_plan_another_paid_checkout_bought(tmp_path: Path):
    service = CommerceService(base_dir=tmp_path / "store")
    customer = service.register_customer("dispute@example.test", "strong-pass-123")
    _paid_checkout(service, customer, "cs_test_d1", "maker", "pi_d1")
    _paid_checkout(service, customer, "cs_test_d2", "studio", "pi_d2", 4900)
    assert service.get_customer(customer["id"])["plan"] == "studio"
    service.apply_stripe_reversal("evt_dis", "charge.dispute.created", payment_intent="pi_d2")
    assert service.get_customer(customer["id"])["plan"] == "maker"


def test_an_operator_set_plan_is_not_taken_back_by_an_unrelated_refund(tmp_path: Path):
    service = CommerceService(base_dir=tmp_path / "store")
    customer = service.register_customer("op@example.test", "strong-pass-123")
    _paid_checkout(service, customer, "cs_test_o1", "maker", "pi_o1")
    service.set_customer_plan(customer["id"], "enterprise")            # granted by hand
    assert service.apply_stripe_reversal("evt_o", "charge.refunded", payment_intent="pi_o1")["plan_reverted"] is False
    assert service.get_customer(customer["id"])["plan"] == "enterprise"


def test_a_reversal_for_an_unknown_payment_is_a_lookup_error(tmp_path: Path):
    service = CommerceService(base_dir=tmp_path / "store")
    with pytest.raises(LookupError):
        service.apply_stripe_reversal("evt_x", "charge.refunded", payment_intent="pi_unknown")


def test_a_completed_event_after_the_refund_grants_nothing(tmp_path: Path):
    """Review of 2026-11-11: Stripe does not order events; a refund handled before the
    checkout's completed event was undone when the completed event arrived."""
    service = CommerceService(base_dir=tmp_path / "store")
    customer = service.register_customer("late@example.test", "strong-pass-123")
    service.save_stripe_checkout_session(
        session_id="cs_test_late", customer_id=customer["id"], customer_email=customer["email"],
        target_plan="studio", amount_total=4900, currency="usd", status="open", payment_status="unpaid")
    service.apply_stripe_reversal("evt_refund_first", "charge.refunded", payment_intent="pi_late",
                                  session_id="cs_test_late")
    out = service.apply_stripe_webhook_event(
        event_id="evt_completed_late", event_type="checkout.session.completed", session_id="cs_test_late",
        payment_status="paid", session_status="complete", amount_total=4900, currency="usd",
        payment_intent="pi_late")
    assert out["plan_upgraded"] is False and out["reversed"] == "refunded"
    assert service.get_customer(customer["id"])["plan"] == "free"


def test_an_old_database_gains_the_payment_intent_column_at_start(tmp_path: Path):
    import sqlite3

    first = CommerceService(base_dir=tmp_path / "store")
    db_path = first.db_path
    with sqlite3.connect(db_path) as raw:
        raw.execute("DROP INDEX IF EXISTS idx_stripe_sessions_payment_intent")
        raw.execute("ALTER TABLE stripe_checkout_sessions DROP COLUMN payment_intent")
    again = CommerceService(base_dir=tmp_path / "store")
    cols = [r[1] for r in sqlite3.connect(db_path).execute("PRAGMA table_info(stripe_checkout_sessions)")]
    assert "payment_intent" in cols and again is not None
