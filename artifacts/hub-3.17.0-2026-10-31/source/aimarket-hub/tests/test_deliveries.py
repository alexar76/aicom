"""Buyer-confirmed deliveries (deliveries.py, POST /reputation/deliveries).

A seller paid directly by the buyer is out of the hub's sight. A buyer may bring evidence that
the seller delivered: the seller's receipt, signed with the key its listing published, and the
transaction that paid it under the receipt's own authorization. The hub counts it once, keeps no
amount, address or transaction in the clear, and shows the counter on the seller's listings.
Seen live 2026-10-15: ARGUS bought an eSIM through modelmarket.dev from a seller paid directly;
the market's feed showed the quotes and nothing of the sale.
"""
from __future__ import annotations

import base64
import json
from contextlib import contextmanager

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from aimarket_hub import deliveries, settle
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import _provider_pubkey
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

PAYER = "0x428f2be4327908948e3b1915c55ddf8fa6bf73cc"
PAY_TO = "0xf47161fbb56d0d910a17e503c8292903f41bbae2"
NONCE = "0x" + "ab" * 32
TX = "0x" + "ee" * 32
SELLER_HUB = "https://esim.example"


def _key():
    k = Ed25519PrivateKey.generate()
    pub = base64.b64encode(k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    return k, pub


def _sign(k, receipt):
    return base64.b64encode(k.sign(deliveries.canonical(receipt).encode())).decode()


def _delivery(**over):
    r = {"v": 1, "kind": "delivery", "capability": "esim.order@v1", "product_id": "esim-test", "chain_id": 8453,
         "payer": PAYER, "pay_to": PAY_TO, "nonce": NONCE, "offer_id": "TR_0.5_7", "at": "2026-10-15T07:47:35Z"}
    r.update(over)
    return r


def _listing(pub, product="esim-test", hub=SELLER_HUB, cid="esim.quote@v1"):
    return Capability(capability_id=cid, product_id=product, name="quote", description="",
                      price_per_call_usd=0.0, source_hub=hub, provider_pubkey=pub)


def _chain(authorizer=PAYER, fail=None):
    seen = []

    def verify_transfer(*, tx_hash, terms, require_nonce, max_age_s):
        seen.append((tx_hash, terms.pay_to, require_nonce))
        if fail:
            raise settle.PaymentError(fail)
        return {"authorizer": authorizer, "tx_hash": tx_hash}
    return verify_transfer, seen


def _confirm(receipt, sig, listings, chain, tx=TX):
    return deliveries.confirm(receipt, sig, tx, listings=listings, verify_signature=Signer.verify,
                              verify_transfer=chain, terms_factory=lambda pay_to: type("T", (), {"pay_to": pay_to})())


def test_a_signed_receipt_backed_by_the_chain_is_one_confirmation_without_the_books():
    k, pub = _key()
    chain, seen = _chain()
    c = _confirm(_delivery(), _sign(k, _delivery()), [_listing(pub)], chain)
    assert (c.source_hub, c.product_id, c.kind) == (SELLER_HUB, "esim-test", "delivery")
    assert seen == [(TX, PAY_TO, NONCE)], "the payment under the receipt's own nonce, to the seller's wallet"
    assert PAYER not in c.buyer_hash and TX not in c.id, "no address or transaction in the clear"


def test_the_seller_is_the_listing_whose_key_signed_not_whoever_names_the_product():
    k, pub = _key()
    _other, other_pub = _key()
    chain, _ = _chain()
    c = _confirm(_delivery(), _sign(k, _delivery()), [_listing(other_pub, hub="https://impostor"), _listing(pub)], chain)
    assert c.source_hub == SELLER_HUB
    with pytest.raises(deliveries.DeliveryError) as e:
        _confirm(_delivery(), _sign(k, _delivery()), [_listing(other_pub)], chain)
    assert e.value.status == 404


def test_what_the_evidence_must_hold():
    k, pub = _key()
    ok_chain, _ = _chain()
    bad = [
        (_delivery(v=2), "receipt.v"),
        (_delivery(kind="praise"), "receipt.kind"),
        (_delivery(chain_id=1), "chain_id"),
        (_delivery(nonce="0x12"), "receipt.nonce"),
        (_delivery(pay_to="nobody"), "receipt.pay_to"),
    ]
    for receipt, needle in bad:
        with pytest.raises(deliveries.DeliveryError, match=needle):
            _confirm(receipt, _sign(k, receipt), [_listing(pub)], ok_chain)
    # a changed field breaks the seller's signature
    signed = _sign(k, _delivery())
    with pytest.raises(deliveries.DeliveryError):
        _confirm(_delivery(pay_to="0x" + "11" * 20), signed, [_listing(pub)], ok_chain)
    # the chain must back it, and the payment must be the payer's own authorization
    with pytest.raises(deliveries.DeliveryError, match="does not back"):
        _confirm(_delivery(), signed, [_listing(pub)], _chain(fail="no EIP-3009 authorization for the nonce")[0])
    with pytest.raises(deliveries.DeliveryError, match="another wallet"):
        _confirm(_delivery(), signed, [_listing(pub)], _chain(authorizer="0x" + "99" * 20)[0])
    with pytest.raises(deliveries.DeliveryError, match="transaction"):
        _confirm(_delivery(), signed, [_listing(pub)], ok_chain, tx="0xabc")


def test_a_refund_is_the_seller_paying_the_buyer_back_under_its_own_authorization():
    k, pub = _key()
    refund_wallet = "0x" + "f4" * 20
    r = {"v": 1, "kind": "refund", "capability": "esim.order@v1", "product_id": "esim-test", "chain_id": 8453,
         "payer": PAYER, "refund_from": refund_wallet, "refund_nonce": "0x" + "cd" * 32, "delivery_nonce": NONCE}
    chain, seen = _chain(authorizer=refund_wallet)
    c = _confirm(r, _sign(k, r), [_listing(pub)], chain)
    assert c.kind == "refund"
    assert seen == [(TX, PAYER, "0x" + "cd" * 32)], "money back to the payer, under the refund's own nonce"


def test_the_crawler_keeps_only_a_real_ed25519_key():
    _k, pub = _key()
    assert _provider_pubkey(pub) == pub
    for junk in ("", None, "not base64!", base64.b64encode(b"short").decode(), "A" * 200):
        assert _provider_pubkey(junk) == ""


@contextmanager
def _hub(monkeypatch, tmp_path, listings):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token-not-for-production")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(tmp_path / "hub.db")
    for cap in listings:
        db.upsert_capability(cap)
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "key"))
    with TestClient(app) as client:
        yield client, db


def test_the_endpoint_counts_once_and_search_shows_the_seller_delivers(monkeypatch, tmp_path):
    k, pub = _key()
    calls = []

    def fake_verify(*, tx_hash, terms, require_nonce, max_age_s=0, **_kw):
        calls.append(tx_hash)
        return {"authorizer": PAYER if terms.pay_to.lower() == PAY_TO else "0x" + "f4" * 20}
    monkeypatch.setattr(settle, "verify_transfer", fake_verify)
    # A local listing: search shows federated rows only from peers this hub knows, and the
    # counting is the same for both.
    quote = _listing(pub, hub="local")
    quote.description = "Travel eSIM offers for a country"
    quote.prompt_template = '{"ok": true}'
    with _hub(monkeypatch, tmp_path, [quote, _listing(pub, hub="local", cid="esim.status@v1")]) as (client, db):
        body = {"receipt": _delivery(), "signature": _sign(k, _delivery()), "transaction": TX}
        first = client.post("/ai-market/v2/reputation/deliveries", json=body)
        assert first.status_code == 200, first.text
        assert first.json()["recorded"] is True
        assert first.json()["deliveries_30d"] == {"confirmed": 1, "distinct_buyers": 1, "refunded": 0}
        again = client.post("/ai-market/v2/reputation/deliveries", json=body)
        assert again.json()["recorded"] is False, "one transaction counts once"
        refund = {"v": 1, "kind": "refund", "capability": "esim.order@v1", "product_id": "esim-test", "chain_id": 8453,
                  "payer": PAYER, "refund_from": "0x" + "f4" * 20, "refund_nonce": "0x" + "cd" * 32}
        r = client.post("/ai-market/v2/reputation/deliveries", json={"receipt": refund, "signature": _sign(k, refund), "transaction": "0x" + "dd" * 32})
        assert r.json()["deliveries_30d"] == {"confirmed": 1, "distinct_buyers": 1, "refunded": 1}
        bad = client.post("/ai-market/v2/reputation/deliveries", json={**body, "signature": _sign(_key()[0], _delivery())})
        assert bad.status_code == 404
        rows = db._conn.execute("SELECT * FROM delivery_confirmations").fetchall()
        assert len(rows) == 2 and not any(PAYER in json.dumps([str(x) for x in row]) for row in rows)
        # A fresh test listing has neither trust nor a recent route: ask for it explicitly.
        found = client.get("/ai-market/v2/search", params={"intent": "esim", "include_stale": "true", "min_trust": 0}).json()["matches"]
        mine = [m for m in found if m["product_id"] == "esim-test"]
        assert mine and all(m["deliveries_30d"] == {"confirmed": 1, "distinct_buyers": 1, "refunded": 1} for m in mine)


def test_a_hub_publishes_its_own_sellers_key_and_never_restates_a_peers(monkeypatch, tmp_path):
    """An operator who runs a whole hub instead of `aimarket node` (esim-kit docs, own hub)
    must still be countable: the hub that crawls it reads provider_pubkey off the signed
    manifest. Only for local rows — a relay restating a key for someone else's listing could
    otherwise substitute its own."""
    _k, pub = _key()
    own = _listing(pub, hub="local")
    own.description = "Travel eSIM offers for a country"
    own.prompt_template = '{"ok": true}'
    relayed = _listing(pub, hub="https://peer.example", cid="esim.status@v1")
    with _hub(monkeypatch, tmp_path, [own, relayed]) as (client, _db):
        manifest = client.get("/ai-market/v2/manifest").json()
        body = manifest.get("manifest", manifest)
        tools = {t["capability_id"]: t for t in body["tools"]}
        assert tools["esim.quote@v1"]["provider_pubkey"] == pub
        assert "provider_pubkey" not in tools.get("esim.status@v1", {}), "a peer's key is the peer's to publish"


def test_a_hub_can_say_what_it_is_in_its_signed_well_known(monkeypatch, tmp_path):
    """An eSIM operator's own hub had no description: maps and directories showed
    "discovered node". AIMARKET_HUB_DESCRIPTION puts one sentence in the signed well-known,
    and it still validates against the protocol schema."""
    from aimarket_hub.validator import validate_well_known

    monkeypatch.setenv("AIMARKET_HUB_DESCRIPTION", "Travel eSIMs for people and AI agents, paid over x402")
    with _hub(monkeypatch, tmp_path, []) as (client, _db):
        wk = client.get("/.well-known/ai-market.json").json()
        assert wk["description"] == "Travel eSIMs for people and AI agents, paid over x402"
        assert validate_well_known(wk) == []
    monkeypatch.delenv("AIMARKET_HUB_DESCRIPTION")
    with _hub(monkeypatch, tmp_path / "b", []) as (client, _db):
        assert "description" not in client.get("/.well-known/ai-market.json").json()


@pytest.mark.parametrize("chain_id", ["not-a-chain", {"id": 8453}, [8453], 8453.9, True, None])
def test_malformed_chain_id_is_a_client_error_without_chain_lookup(monkeypatch, tmp_path, chain_id):
    def unexpected_transfer(**kwargs):
        pytest.fail("malformed receipts must be rejected before any chain lookup")
    monkeypatch.setattr(settle, "verify_transfer", unexpected_transfer)
    with _hub(monkeypatch, tmp_path, []) as (client, _db):
        response = client.post("/ai-market/v2/reputation/deliveries", json={
            "receipt": _delivery(chain_id=chain_id), "signature": "unused", "transaction": TX,
        })
    assert response.status_code == 422
    assert "receipt.chain_id" in response.json()["detail"]
