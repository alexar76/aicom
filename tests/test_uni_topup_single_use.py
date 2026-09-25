"""A UNI top-up spends its transfer through the same single-use claim as every other door.

UNI verifies against the platform wallet checkout, channels and invoke use. It checked
only commerce orders (and credited anyway when that store was down), and keyed its own
idempotency on the hash as typed, so one transfer could become UNI credit plus a license,
a channel or an invoke, and a case variant of the same hash was credited twice.
Synthetic chain answers only: no RPC, no real transfers.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException

TX = "0x" + "cd" * 32
PAYER = "0x" + "77" * 20


@pytest.fixture
def uni(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_UNI_TOPUP_SPREAD_BPS", "0")
    monkeypatch.delenv("AIMARKET_DEPOSIT_CLAIMS_DIR", raising=False)
    import core.uni.store as uni_store

    uni_store._sqlite_conn = None
    from web.backend.api import uni_wallet as api
    from web.backend.services.ai_market_protocol import channels, on_chain
    from web.backend.services.commerce import CommerceService

    store = CommerceService(base_dir=str(tmp_path / "store"))
    monkeypatch.setattr(channels, "_commerce", store)
    monkeypatch.setattr(on_chain, "verify_tx_payment_details", lambda **kw: (True, PAYER))
    monkeypatch.setattr(api, "_recover_topup_signer", lambda owner, tx, chain, sig: PAYER)
    return api, channels


def _topup(api, owner, tx=TX, usd=10.0):
    body = api.UniTopupConfirmRequest(tx_hash=tx, usd_amount=usd, chain="base", token="USDT",
                                      from_address=PAYER, signature="0x" + "11" * 65)
    return asyncio.run(api.confirm_topup(body, customer={"sub": owner}))


def test_a_topped_up_transfer_cannot_be_spent_at_another_door(uni):
    api, channels = uni
    assert _topup(api, "cust-a")["status"] == "credited"
    other = channels.claim_transfer(chain="base", tx_hash=TX, door="web-checkout", claim_id="pay-1")
    assert other["ok"] is False and other["error"] == "tx_hash_already_used"


def test_a_transfer_spent_elsewhere_is_not_minted_into_uni(uni):
    api, channels = uni
    assert channels.claim_transfer(chain="base", tx_hash=TX, door="web-checkout", claim_id="pay-1")["ok"]
    with pytest.raises(HTTPException) as exc:
        _topup(api, "cust-a")
    assert exc.value.status_code == 409


def test_a_case_variant_of_the_hash_is_the_same_transfer(uni):
    api, _ = uni
    first = _topup(api, "cust-a", TX.lower())
    with pytest.raises(HTTPException) as exc:
        _topup(api, "cust-b", "0x" + TX[2:].upper())
    assert exc.value.status_code == 409
    assert first["wallet"]["balance_uni"] == 1000


def test_a_topup_from_before_the_shared_claim_still_counts_as_spent(uni):
    api, channels = uni
    from core.uni.wallet import UniWalletService

    # Credited directly, as the old door did, under a mixed-case hash and no shared claim.
    UniWalletService().topup_from_chain("cust-old", usd_amount=10.0, tx_hash="0x" + "CD" * 32,
                                        chain="base", token="USDT")
    other = channels.claim_transfer(chain="base", tx_hash=TX, door="web-checkout", claim_id="pay-2")
    assert other["ok"] is False


def test_a_credit_that_fails_gives_the_transfer_back(uni, monkeypatch):
    api, channels = uni
    from core.uni.wallet import UniWalletError, UniWalletService

    def boom(self, *a, **k):
        raise UniWalletError("wallet frozen")

    monkeypatch.setattr(UniWalletService, "topup_from_chain", boom)
    with pytest.raises(HTTPException) as exc:
        _topup(api, f"cust-{uuid.uuid4().hex[:6]}")
    assert exc.value.status_code == 400
    # Nothing was credited, so another door may still spend it.
    assert channels.claim_transfer(chain="base", tx_hash=TX, door="web-checkout", claim_id="pay-3")["ok"]
