"""The interlocks that must all hold before the hub tells peers it takes money.

`payment_readiness()` is the single list behind `payment_configured` in
`.well-known/ai-market.json`. Nothing tested it, which is how the hub came to advertise
payments while pointed at an Anvil dev address whose private key is public.

The last test here is the KI-11 rail-separation interlock. It has no dev-address or stub
analogue: both addresses can be perfectly good production addresses and the configuration
still be unsafe, purely because they are the SAME one.
"""

from __future__ import annotations

import pytest

from aimarket_hub.config import HubConfig, is_dev_chain_address

_REAL_RECIPIENT = "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a"
_REAL_ESCROW = "0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb"
_ANVIL_0 = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def _ready_config(**over):
    """A configuration that takes real money, so each test can break exactly one thing."""
    cfg = HubConfig()
    cfg.crypto_enabled = True
    cfg.payment_verify_stub = False
    cfg.production_mode = True
    cfg.payment_recipient = _REAL_RECIPIENT
    cfg.escrow_evm_address = ""
    for k, v in over.items():
        setattr(cfg, k, v)
    return cfg


@pytest.fixture(autouse=True)
def _no_demo_credit(monkeypatch):
    monkeypatch.delenv("AIMARKET_ALLOW_DEMO_CREDIT", raising=False)


class TestTheBaseline:
    def test_a_fully_configured_hub_is_ready(self):
        assert _ready_config().payment_readiness() == []

    @pytest.mark.parametrize(
        "field,value,expect",
        [
            ("crypto_enabled", False, "AIFACTORY_CRYPTO_ENABLED"),
            ("payment_verify_stub", True, "VERIFY_STUB"),
            ("production_mode", False, "AIFACTORY_PROD"),
            ("payment_recipient", "", "nowhere to settle"),
            ("payment_recipient", _ANVIL_0, "sweepable by anyone"),
        ],
    )
    def test_breaking_one_interlock_is_reported(self, field, value, expect):
        reasons = _ready_config(**{field: value}).payment_readiness()
        assert reasons, f"{field}={value!r} must not be advertised as payment-ready"
        assert any(expect in r for r in reasons), reasons

    def test_demo_credit_is_an_active_bypass_not_a_missing_interlock(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_ALLOW_DEMO_CREDIT", "1")
        reasons = _ready_config().payment_readiness()
        assert any("DEMO_CREDIT" in r for r in reasons), reasons

    def test_the_anvil_address_set_is_what_it_claims_to_be(self):
        """The blocklist is only as good as its contents."""
        assert is_dev_chain_address(_ANVIL_0)
        assert is_dev_chain_address(_ANVIL_0.lower()), "must be case-insensitive"
        assert not is_dev_chain_address(_REAL_RECIPIENT)


class TestRailSeparation:
    """KI-11 case 2 — the two rails must never be backed by the same money.

    If the custodial ledger and an escrow contract channel share a deposit, the contract's
    `usedAmount` stays 0 however much the ledger consumed, so refundChannel/expireChannel
    returns a fully-consumed deposit IN FULL. Pointing the settlement recipient at the
    escrow contract is how that happens by accident: every deposit then lands inside the
    contract while the hub books it as a plain transfer it fully controls.
    """

    def test_recipient_equal_to_escrow_is_refused(self):
        reasons = _ready_config(
            payment_recipient=_REAL_ESCROW, escrow_evm_address=_REAL_ESCROW
        ).payment_readiness()
        assert any("must be different addresses" in r for r in reasons), reasons

    def test_it_is_case_insensitive(self):
        """Checksummed and lowercase spellings are the same address on chain."""
        reasons = _ready_config(
            payment_recipient=_REAL_ESCROW.lower(), escrow_evm_address=_REAL_ESCROW.upper()
        ).payment_readiness()
        assert any("must be different addresses" in r for r in reasons), reasons

    def test_whitespace_does_not_smuggle_it_past(self):
        reasons = _ready_config(
            payment_recipient=f"  {_REAL_ESCROW}  ", escrow_evm_address=_REAL_ESCROW
        ).payment_readiness()
        assert any("must be different addresses" in r for r in reasons), reasons

    def test_two_different_real_addresses_are_fine(self):
        """The check must not fire on the ONLY correct configuration."""
        assert _ready_config(escrow_evm_address=_REAL_ESCROW).payment_readiness() == []

    def test_an_unset_escrow_does_not_trip_it(self):
        """A hub with no bridge at all has one rail, and one rail cannot conflict."""
        assert _ready_config(escrow_evm_address="").payment_readiness() == []
        assert _ready_config(escrow_evm_address="   ").payment_readiness() == []

    def test_this_is_the_live_production_pairing(self):
        """Documents the values prod actually runs, so a regression is obvious here."""
        assert _REAL_RECIPIENT.lower() != _REAL_ESCROW.lower()
        assert _ready_config(escrow_evm_address=_REAL_ESCROW).payment_readiness() == []
