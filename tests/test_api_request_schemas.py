"""Pydantic validation for admin/public API bodies."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from web.backend.schemas.api_requests import (
    AiMarketSearchRequest,
    AiMarketSettlementConfirmRequest,
    BatchCreateIdeasRequest,
    ConfirmPaymentRequest,
    CreatePaymentRequest,
    CreateProductRequest,
    CustomerLoginRequest,
    CustomerRegisterRequest,
    DemoNotePatchRequest,
    DemoReplayPatchRequest,
    FeedbackSubmitRequest,
    GuestLandingRequest,
    RunDiscoveryRequest,
    StripeCheckoutRequest,
    SupportCreateSessionRequest,
    TelemetryEventRequest,
)


def test_create_product_rejects_short_idea() -> None:
    with pytest.raises(ValidationError):
        CreateProductRequest(idea="ab")


def test_create_product_accepts_valid_payload() -> None:
    m = CreateProductRequest(idea="Valid product idea", delivery_profile="marketing_landing")
    assert m.delivery_profile == "marketing_landing"


def test_batch_create_validates_each_idea() -> None:
    with pytest.raises(ValidationError):
        BatchCreateIdeasRequest(ideas=["ok idea", "x"])


def test_run_discovery_top_k_bounds() -> None:
    with pytest.raises(ValidationError):
        RunDiscoveryRequest(top_k=0)
    assert RunDiscoveryRequest(top_k=20).top_k == 20


def test_guest_landing_phrase_length() -> None:
    with pytest.raises(ValidationError):
        GuestLandingRequest(phrase="short")


def test_customer_register_invalid_email() -> None:
    with pytest.raises(ValidationError):
        CustomerRegisterRequest(email="not-an-email", password="password12")


def test_customer_login_normalizes_email() -> None:
    m = CustomerLoginRequest(email="User@Example.COM", password="password12")
    assert m.email == "user@example.com"


def test_demo_note_patch_requires_field() -> None:
    with pytest.raises(ValidationError):
        DemoNotePatchRequest()


def test_stripe_checkout_requires_http_url() -> None:
    with pytest.raises(ValidationError):
        StripeCheckoutRequest(
            success_url="ftp://bad.example/checkout",
            cancel_url="https://example.com/cancel",
        )


def test_feedback_product_id_pattern() -> None:
    with pytest.raises(ValidationError):
        FeedbackSubmitRequest(
            product_id="bad-id",
            rating=5,
            comment="Great product",
        )
    m = FeedbackSubmitRequest(
        product_id="prod-abc123def456",
        rating=5,
        comment="Great product",
    )
    assert m.product_id.startswith("prod-")


def test_create_payment_chain_token() -> None:
    with pytest.raises(ValidationError):
        CreatePaymentRequest(product_id="prod-abc123def456", chain="solana", token="ETH")
    m = CreatePaymentRequest(product_id="prod-abc123def456", chain="base", token="usdt")
    assert m.token == "USDT"


def test_confirm_payment_tx_hash() -> None:
    with pytest.raises(ValidationError):
        ConfirmPaymentRequest(tx_hash="0xshort")
    ok = ConfirmPaymentRequest(tx_hash="0x" + "a" * 64)
    assert ok.tx_hash.startswith("0x")


def test_ai_market_settlement_no_client_amount() -> None:
    m = AiMarketSettlementConfirmRequest(
        product_id="prod-abc123def456",
        tx_hash="0x" + "b" * 64,
    )
    assert "amount" not in AiMarketSettlementConfirmRequest.model_fields


def test_ai_market_search_strips_task() -> None:
    m = AiMarketSearchRequest(task_description="  find analytics  ")
    assert m.task_description == "find analytics"


def test_telemetry_event_type_pattern() -> None:
    with pytest.raises(ValidationError):
        TelemetryEventRequest(product_id="prod-abc123def456", event_type="Bad-Type")
    m = TelemetryEventRequest(product_id="prod-abc123def456", event_type="page_view")
    assert m.event_type == "page_view"


def test_support_session_rejects_bad_product_id() -> None:
    with pytest.raises(ValidationError):
        SupportCreateSessionRequest(product_id="not-prod")


def test_demo_replay_patch_optional_fields() -> None:
    m = DemoReplayPatchRequest(enabled=True, title="Demo")
    assert m.enabled is True
    assert m.video_url is None
