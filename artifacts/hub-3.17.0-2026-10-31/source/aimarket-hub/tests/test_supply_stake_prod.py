"""Supply stake hardening in production mode."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.supply_security import SupplySecurity


_EVM_PAYER = "0x" + "Ab" * 20
_GOOD_SIG = "0xgoodproof"


@pytest.fixture
def sec(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    db = HubDatabase(db_path=str(tmp_path / "hub.db"))
    return SupplySecurity(db, HubConfig(), signer=MagicMock(), slash_registry=None)


def _verified_deposit(monkeypatch, *, sender=_EVM_PAYER, proof_signer=_EVM_PAYER):
    """Put the stake path on the production (payer-bound) rails.

    A stake deposit now needs BOTH halves of PAYAUTH-003: the chain must name the
    payer, and the caller must prove control of that wallet. The real proof path
    needs eth_account (absent from the hub test venv), so recovery is stubbed to
    the same shape a real ECDSA recovery has — `proof_signer` for the one good
    signature, nothing otherwise.
    """
    monkeypatch.setattr(
        "aimarket_hub.supply_security._verify_stake_deposit",
        lambda tx, amt: (True, sender),
    )
    monkeypatch.setattr(
        "aimarket_hub.supply_security._recover_stake_payer",
        lambda *, payer, tx_hash, chain, amount_usd, signature: (
            proof_signer if signature == _GOOD_SIG else None
        ),
    )


def test_stake_requires_tx_hash_in_prod(sec, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    sec.policy.min_stake_usd = 10.0
    with pytest.raises(ValueError, match="tx_hash required"):
        sec.stake("publisher-a", 25.0, tx_hash="")


def test_stake_accepts_verified_tx_hash_in_prod(sec, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    sec.policy.min_stake_usd = 10.0
    # On-chain verification is now required in prod — mock a verified deposit.
    _verified_deposit(monkeypatch)
    out = sec.stake("publisher-a", 25.0, tx_hash="0xabc123", payer_signature=_GOOD_SIG)
    assert out["stake_usd"] >= 25.0


def test_stake_rejects_unverified_tx_in_prod(sec, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    sec.policy.min_stake_usd = 10.0
    monkeypatch.setattr(
        "aimarket_hub.supply_security._verify_stake_deposit", lambda tx, amt: (False, "")
    )
    with pytest.raises(ValueError, match="not verified on-chain"):
        sec.stake("publisher-a", 25.0, tx_hash="0xfabricated", payer_signature=_GOOD_SIG)


def test_stake_rejects_replayed_tx_in_prod(sec, monkeypatch):
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    sec.policy.min_stake_usd = 10.0
    _verified_deposit(monkeypatch)
    sec.stake("publisher-a", 25.0, tx_hash="0xdeadbeef", payer_signature=_GOOD_SIG)
    # The same on-chain deposit cannot be claimed again (by anyone).
    with pytest.raises(ValueError, match="already recorded"):
        sec.stake("publisher-b", 25.0, tx_hash="0xdeadbeef", payer_signature=_GOOD_SIG)


def test_stake_rejects_a_deposit_the_caller_cannot_prove_it_paid(sec, monkeypatch):
    """PAYAUTH-003 for stake: quoting a stranger's verified deposit is not enough.

    The payer address is public in the transaction being quoted, so knowing it
    proves nothing — without a signature from that wallet the credit is refused,
    and the refusal hands back the exact challenge to sign.
    """
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    sec.policy.min_stake_usd = 10.0
    _verified_deposit(monkeypatch)
    with pytest.raises(ValueError, match="missing or invalid payer proof"):
        sec.stake("publisher-a", 25.0, tx_hash="0xstranger", payer_signature="0xforged")


def test_stake_refuses_a_deposit_the_chain_cannot_attribute(sec, monkeypatch):
    """A verified transfer with no reported sender cannot be bound to anyone."""
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    sec.policy.min_stake_usd = 10.0
    monkeypatch.setattr(
        "aimarket_hub.supply_security._verify_stake_deposit", lambda tx, amt: (True, "")
    )
    with pytest.raises(ValueError, match="did not report the paying wallet"):
        sec.stake("publisher-a", 25.0, tx_hash="0xunattributable", payer_signature=_GOOD_SIG)
