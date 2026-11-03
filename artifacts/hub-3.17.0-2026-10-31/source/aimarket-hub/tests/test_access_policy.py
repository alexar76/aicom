from types import SimpleNamespace

from aimarket_hub.access_policy import (
    OPERATOR_GATED,
    PAID,
    PUBLIC_FREE,
    capability_access_mode,
    capability_is_publicly_offerable,
)


def _cap(price, description="", access_mode=""):
    return SimpleNamespace(
        price_per_call_usd=price,
        description=description,
        access_mode=access_mode,
    )


def test_zero_price_is_public_free_when_no_access_restriction_is_declared():
    assert capability_access_mode(_cap(0)) == PUBLIC_FREE


def test_operator_gated_zero_price_is_not_a_free_offer():
    cap = _cap(0, "Operator-gated: requires an operator token and answers 403 without it.")
    assert capability_access_mode(cap) == OPERATOR_GATED
    assert capability_is_publicly_offerable(cap) is False


def test_legacy_momus_unpriced_marker_is_recognized():
    cap = _cap(0, "It is published unpriced rather than sold.")
    assert capability_access_mode(cap) == OPERATOR_GATED


def test_paid_and_explicit_modes_are_preserved():
    assert capability_access_mode(_cap(0.002)) == PAID
    assert capability_access_mode(_cap(0, access_mode=OPERATOR_GATED)) == OPERATOR_GATED
