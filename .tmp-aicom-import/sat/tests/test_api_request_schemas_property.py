"""Property-based checks for public API request schemas (Hypothesis)."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from web.backend.schemas.api_requests import (
    CreatePaymentRequest,
    FeedbackSubmitRequest,
    TelemetryEventRequest,
)

_VALID_PRODUCT_ID = "prod-abc12345"
_EVENT_TYPE = st.from_regex(r"^[a-z][a-z0-9_]{1,20}$", fullmatch=True)


@given(rating=st.integers())
def test_feedback_rating_bounds(rating: int) -> None:
    if 1 <= rating <= 5:
        m = FeedbackSubmitRequest(
            product_id=_VALID_PRODUCT_ID,
            rating=rating,
            comment="ok",
        )
        assert m.rating == rating
    else:
        with pytest.raises(ValidationError):
            FeedbackSubmitRequest(
                product_id=_VALID_PRODUCT_ID,
                rating=rating,
                comment="ok",
            )


@given(event_type=_EVENT_TYPE)
def test_telemetry_event_type_slug(event_type: str) -> None:
    m = TelemetryEventRequest(
        product_id=_VALID_PRODUCT_ID,
        event_type=event_type,
    )
    assert m.event_type == event_type


@given(chain=st.sampled_from(["base", "arbitrum", "ethereum"]))
def test_create_payment_accepts_evm_usdt(chain: str) -> None:
    m = CreatePaymentRequest(product_id=_VALID_PRODUCT_ID, chain=chain, token="USDT")
    assert m.chain == chain


def test_create_payment_solana_usdc() -> None:
    m = CreatePaymentRequest(product_id=_VALID_PRODUCT_ID, chain="solana", token="USDC")
    assert m.chain == "solana"
    assert m.token == "USDC"
