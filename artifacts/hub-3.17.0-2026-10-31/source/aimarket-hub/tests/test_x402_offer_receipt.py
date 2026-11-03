"""x402 Offer and Receipt extension (x402 Foundation, v0.6): signed offers on a 402, a signed
receipt in the settlement of a paid, delivered call."""
from __future__ import annotations

import base64
import json

import pytest

from aimarket_hub import x402_offer_receipt as oor
from aimarket_hub.signing import Signer

from tests.test_x402_accept import (  # noqa: F401 - shared fixtures of the x402 acceptance tests
    PAY_TO,
    USDC_BASE,
    _authorization,
    _envelope,
    _hub,
    _invoke,
    _sign,
    _stub_chain,
    _with_tx,
    crypto,
)


def _payload(token: str) -> dict:
    return json.loads(oor.b64url_decode(token.split(".")[1]))


def test_did_key_matches_the_awr_reference(tmp_path):
    awr = pytest.importorskip("awr")
    signer = Signer(tmp_path / "k")
    pub = base64.b64decode(signer.public_key_b64)
    assert oor.did_key(pub) == awr.didkey.derive_did_key(pub)


def test_jws_round_trip_and_tamper(tmp_path):
    signer = Signer(tmp_path / "k")
    pub = base64.b64decode(signer.public_key_b64)
    token = oor.jws_sign(signer, {"version": 1, "amount": "20000", "résumé": "✓"})
    header = json.loads(oor.b64url_decode(token.split(".")[0]))
    assert header == {"alg": "EdDSA", "kid": oor.did_key_url(pub)}
    assert oor.jws_verify(token, pub) == {"version": 1, "amount": "20000", "résumé": "✓"}
    # the payload is the RFC 8785 form: keys sorted, no whitespace, non-ASCII as itself
    assert oor.b64url_decode(token.split(".")[1]) == '{"amount":"20000","résumé":"✓","version":1}'.encode()
    h, p, s = token.split(".")
    forged = oor.b64url(json.dumps({"version": 1, "amount": "1"}).encode())
    assert oor.jws_verify(f"{h}.{forged}.{s}", pub) is None
    other = base64.b64decode(Signer(tmp_path / "other").public_key_b64)
    assert oor.jws_verify(token, other) is None


def test_offer_turns_v1_fields_into_the_extension_payload():
    entry = {"scheme": "exact", "network": "base", "maxAmountRequired": "20000",
             "asset": USDC_BASE, "payTo": PAY_TO}
    assert oor.offer_payload(entry, "https://h.example/x", network="eip155:8453", valid_until=10) == {
        "version": 1, "resourceUrl": "https://h.example/x", "scheme": "exact", "network": "eip155:8453",
        "asset": USDC_BASE, "payTo": PAY_TO, "amount": "20000", "validUntil": 10,
    }


def test_a_402_carries_signed_offers_for_its_terms(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path) as client:
        r = _invoke(client)
        assert r.status_code == 402
        v2 = json.loads(base64.b64decode(r.headers["PAYMENT-REQUIRED"]))
        signer_key = base64.b64decode(client.get("/.well-known/agent-marketplace").json()["signer_public_key"])
        for doc, accepts in ((v2, v2["accepts"]), (r.json(), r.json()["accepts"])):
            offers = doc["extensions"]["offer-receipt"]["info"]["offers"]
            assert len(offers) == len(accepts) == 1
            offer = offers[0]
            assert offer["format"] == "jws" and offer["acceptIndex"] == 0 and "payload" not in offer
            payload = oor.jws_verify(offer["signature"], signer_key)
            assert payload is not None, "the offer must verify under the hub's published signer key"
            entry = accepts[0]
            assert payload["payTo"] == entry["payTo"] == PAY_TO
            assert payload["asset"] == entry["asset"]
            assert payload["amount"] == (entry.get("amount") or entry.get("maxAmountRequired"))
            assert payload["network"] == "eip155:8453" and payload["scheme"] == "exact"
            assert payload["resourceUrl"].endswith("/ai-market/v2/invoke")
            assert payload["validUntil"] > 0


def test_offers_can_be_switched_off(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, AIMARKET_X402_OFFER_RECEIPT="0") as client:
        v2 = json.loads(base64.b64decode(_invoke(client).headers["PAYMENT-REQUIRED"]))
        assert "extensions" not in v2


@crypto
def test_a_paid_call_returns_a_signed_receipt(monkeypatch, tmp_path):
    from eth_account import Account

    acct = Account.create()
    _stub_chain(monkeypatch)
    with _hub(monkeypatch, tmp_path) as client:
        quote = _invoke(client).json()
        auth = _authorization(acct.address, nonce=quote["nonce"])
        r = _invoke(client, _with_tx(_envelope(auth, _sign(auth, acct.key))), secret=quote["payment_secret"])
        assert r.status_code == 200, r.text
        body = r.json()
        settlement = body["x402_settlement"]
        assert json.loads(base64.b64decode(r.headers["PAYMENT-RESPONSE"])) == settlement
        assert settlement["success"] is True and settlement["network"] == "eip155:8453"
        assert settlement["transaction"]
        receipt = settlement["extensions"]["offer-receipt"]["info"]["receipt"]
        signer_key = base64.b64decode(client.get("/.well-known/agent-marketplace").json()["signer_public_key"])
        payload = oor.jws_verify(receipt["signature"], signer_key)
        assert payload is not None
        assert payload["version"] == 1 and payload["network"] == "eip155:8453"
        assert payload["resourceUrl"].endswith("/ai-market/v2/invoke")
        assert payload["payer"] == settlement["payer"]
        assert "transaction" not in payload  # privacy-minimal by default (extension §5.2)
        assert isinstance(payload["issuedAt"], int)


@crypto
def test_the_work_receipt_settlement_is_the_x402_receipt(monkeypatch, tmp_path):
    """AWR-X402/1: the receipt hooks get the x402 receipt, verbatim, as `settlement`."""
    from eth_account import Account

    from aimarket_hub.plugin import PluginRegistry

    contexts: list[dict] = []
    real = PluginRegistry.run_receipt_hooks

    def record(self, output, context):
        contexts.append(context)
        return real(self, output, context)

    monkeypatch.setattr(PluginRegistry, "run_receipt_hooks", record)
    acct = Account.create()
    _stub_chain(monkeypatch)
    with _hub(monkeypatch, tmp_path) as client:
        quote = _invoke(client).json()
        auth = _authorization(acct.address, nonce=quote["nonce"])
        r = _invoke(client, _with_tx(_envelope(auth, _sign(auth, acct.key))), secret=quote["payment_secret"])
        assert r.status_code == 200, r.text
        settlement = r.json()["x402_settlement"]
        signer_key = base64.b64decode(client.get("/.well-known/agent-marketplace").json()["signer_public_key"])
    binding = contexts[-1]["settlement"]
    assert binding == oor.awr_settlement(settlement)
    assert binding["receipt"] == settlement["extensions"]["offer-receipt"]["info"]["receipt"]["signature"]
    assert "transaction" not in binding
    assert oor.check_awr_settlement(binding, signer_key) == []


def test_awr_settlement_checks(tmp_path):
    pytest.importorskip("awr")
    signer = Signer(tmp_path / "k")
    key = base64.b64decode(signer.public_key_b64)
    url = "https://h.example/ai-market/v2/invoke"
    settlement = oor.settlement_response(signer, network="eip155:8453", resource_url=url, payer="0xabc",
                                         transaction="0x01", now=1_000)
    binding = oor.awr_settlement(settlement)
    assert binding["scheme"] == "x402-offer-receipt-v1" and binding["resourceUrl"] == url
    assert oor.check_awr_settlement(binding, key) == []
    # a different work-receipt issuer: valid, but the two keys are not shown to be one service
    other = base64.b64decode(Signer(tmp_path / "other").public_key_b64)
    assert oor.check_awr_settlement(binding, other) == ["AWR-X402-004"]
    assert oor.check_awr_settlement(binding) == ["AWR-X402-004"]
    # tampered payload
    h, p, s = binding["receipt"].split(".")
    forged = oor.b64url(json.dumps({**_payload(binding["receipt"]), "payer": "0xdef"}).encode())
    assert oor.check_awr_settlement({**binding, "receipt": f"{h}.{forged}.{s}"}, key) == ["AWR-X402-002"]
    # binding disagrees with the receipt it carries
    assert oor.check_awr_settlement({**binding, "resourceUrl": "https://evil.example/"}, key) == ["AWR-X402-003"]
    # malformed: wrong scheme, not a JWS, kid not a did:key URL
    assert oor.check_awr_settlement({**binding, "scheme": "x"}, key) == ["AWR-X402-001"]
    assert oor.check_awr_settlement({**binding, "receipt": "nope"}, key) == ["AWR-X402-001"]
    bad_kid = oor.b64url(json.dumps({"alg": "EdDSA", "kid": "did:web:h.example#k"}).encode())
    assert oor.check_awr_settlement({**binding, "receipt": f"{bad_kid}.{p}.{s}"}, key) == ["AWR-X402-001"]
    # a transaction hash is reported, never looked up
    assert oor.check_awr_settlement({**binding, "transaction": "0x01"}, key) == ["AWR-X402-005"]
    # with the accepted offer: same origin and network, not expired before the receipt
    entry = {"scheme": "exact", "network": "eip155:8453", "amount": "20000", "asset": USDC_BASE, "payTo": PAY_TO}
    offer = oor.jws_sign(signer, oor.offer_payload(entry, url, network="eip155:8453", valid_until=2_000))
    assert oor.check_awr_settlement({**binding, "offer": offer}, key) == []
    stale = oor.jws_sign(signer, oor.offer_payload(entry, url, network="eip155:8453", valid_until=500))
    assert oor.check_awr_settlement({**binding, "offer": stale}, key) == ["AWR-X402-003"]
    elsewhere = oor.jws_sign(signer, oor.offer_payload(entry, url + "/x", network="eip155:8453", valid_until=0))
    assert oor.check_awr_settlement({**binding, "offer": elsewhere}, key) == ["AWR-X402-003"]
    assert oor.awr_settlement({"extensions": {}}) is None


def test_a_work_receipt_with_the_binding_verifies(tmp_path):
    """The binding is an ordinary AWR/2 §10.3 settlement to the AWR reference verifier."""
    awr = pytest.importorskip("awr")
    receipt_mod = pytest.importorskip("aimarket_provenance.receipt")
    signer = Signer(tmp_path / "k")
    binding = oor.awr_settlement(oor.settlement_response(
        signer, network="eip155:8453", resource_url="https://h.example/ai-market/v2/invoke",
        payer="0xabc", transaction=""))
    receipt = receipt_mod.ProvenanceReceipt.create(
        model_id="m@p", provider_hub="https://h.example", input_payload={"a": 1},
        output_payload={"b": 2}, signer=signer, settlement=binding)
    assert receipt.settlement == binding
    result = receipt.verify_result()
    assert result["valid"] is True and result["reasons"] == [], result
    warnings = [w["code"] for w in result["warnings"]]
    assert "AWR-L2-001" in warnings  # present, well-formed and signed; nothing looked up
    issuer_key = awr.didkey.parse_did_key(receipt.issuer_did)
    assert oor.check_awr_settlement(receipt.settlement, issuer_key) == []
