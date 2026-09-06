"""A hub that sells our capabilities must be able to complete the sale.

The factory bills its own 402. A routing hub collects the buyer's money on its own rail,
forwards the invoke, and gets that 402 back — aimed at a buyer who has no account here.
So the factory's capabilities were indexed in the federation and unbuyable through it.

A reseller key is the operator saying "this caller already took the money". It is issued
per reseller, out of band, and nothing in the request body can grant it.
"""

from __future__ import annotations

import inspect

import pytest

from web.backend.services.ai_market_protocol.invoke import invoke_capability_v1, reseller_label


def test_no_configuration_means_no_resellers(monkeypatch):
    monkeypatch.delenv("AIFACTORY_RESELLER_KEYS", raising=False)
    assert reseller_label("anything") == ""


def test_a_configured_key_names_its_reseller(monkeypatch):
    monkeypatch.setenv("AIFACTORY_RESELLER_KEYS", "modelmarket=abc123,other=def456")
    assert reseller_label("abc123") == "modelmarket"
    assert reseller_label("def456") == "other"


@pytest.mark.parametrize("presented", ["", None, "   ", "abc12", "abc1234", "ABC123", "ключ"])
def test_anything_else_is_not_a_reseller(monkeypatch, presented):
    """Including a near-miss and a non-ASCII header, which must not raise."""
    monkeypatch.setenv("AIFACTORY_RESELLER_KEYS", "modelmarket=abc123")
    assert reseller_label(presented) == ""


def test_an_unlabelled_pair_is_still_a_reseller(monkeypatch):
    monkeypatch.setenv("AIFACTORY_RESELLER_KEYS", "=abc123")
    assert reseller_label("abc123") == "reseller"


def test_both_invoke_entry_points_carry_the_key():
    """A guard applied at one of two doors is the shape of half this repo's incidents."""
    from web.backend.api import ai_market_protocol_v1 as v1
    from web.backend.api import ai_market_protocol_v2 as v2

    assert "x_api_key" in inspect.signature(invoke_capability_v1).parameters
    for module, route in ((v1, "invoke_capability_root"), (v2, "invoke_v2")):
        src = inspect.getsource(getattr(module, route))
        assert 'alias="X-API-Key"' in src, f"{route} does not read the reseller header"
        assert "x_api_key=x_api_key" in src, f"{route} does not forward the reseller header"


def test_the_reseller_check_runs_before_every_payment_branch():
    """Ordering is the whole behaviour: a reseller must not also be asked to pay."""
    src = inspect.getsource(invoke_capability_v1)
    assert src.index("reseller = reseller_label(") < src.index("elif x_payment_channel:")
    assert src.index("if reseller:") < src.index("elif not crypto_enabled():")


def test_a_reseller_sale_does_not_charge_a_uni_wallet():
    """The buyer is the reseller's customer and has no wallet here.

    Measured live on 2026-08-31: the UNI leg raised `insufficient_balance` and flipped
    `success` to false over a result that had already been produced and returned — so the
    routing hub, which fails closed on a provider envelope that says failure, could never
    complete the sale it had just charged for.
    """
    src = inspect.getsource(invoke_capability_v1)
    assert 'if success and paid and payment_kind != "reseller":' in src
    assert '"payment_kind": payment_kind,' in src
