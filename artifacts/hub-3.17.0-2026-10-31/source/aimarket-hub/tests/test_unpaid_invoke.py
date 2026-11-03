"""The unpaid-invoke gate MOMUS probes — keep the decision off api.py so it stays patchable."""

from __future__ import annotations

from aimarket_hub.unpaid_invoke import must_refuse_unpaid_paid_capability


def test_priced_rail_without_payment_must_402():
    assert must_refuse_unpaid_paid_capability(
        price_usd=0.01, sandbox_mode=False, price_rail_active=True,
        payment_channel=None, credit_account="", x402_accepted=None,
    ) is True


def test_sandbox_and_free_and_no_rail_are_served():
    assert must_refuse_unpaid_paid_capability(
        price_usd=0.01, sandbox_mode=True, price_rail_active=True,
        payment_channel=None, credit_account="", x402_accepted=None,
    ) is False
    assert must_refuse_unpaid_paid_capability(
        price_usd=0, sandbox_mode=False, price_rail_active=True,
        payment_channel=None, credit_account="", x402_accepted=None,
    ) is False
    assert must_refuse_unpaid_paid_capability(
        price_usd=0.01, sandbox_mode=False, price_rail_active=False,
        payment_channel=None, credit_account="", x402_accepted=None,
    ) is False


def test_channel_credits_or_x402_are_payment():
    assert must_refuse_unpaid_paid_capability(
        price_usd=0.01, sandbox_mode=False, price_rail_active=True,
        payment_channel="ch-1", credit_account="", x402_accepted=None,
    ) is False
    assert must_refuse_unpaid_paid_capability(
        price_usd=0.01, sandbox_mode=False, price_rail_active=True,
        payment_channel=None, credit_account="acct", x402_accepted=None,
    ) is False
    assert must_refuse_unpaid_paid_capability(
        price_usd=0.01, sandbox_mode=False, price_rail_active=True,
        payment_channel=None, credit_account="", x402_accepted={"ok": True},
    ) is False
