"""The hub signs the provider calls it admits, so a gated provider can tell them apart.

The other half is oracles/core/oracle_core/price_gate.py: a priced capability there is
served only to a call a trusted hub signed. These tests pin what the hub sends, when it
sends it (a local listing always; a federated peer only when this hub sells for it),
and that the wire format is the one the provider checks.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import aimarket_hub.sandbox_trials as st
from aimarket_hub import provider_request_auth as pra
from aimarket_hub.federation_assay import parse_payment_challenge
from aimarket_hub.signing import Signer

from tests.test_federated_invoke import (
    MCP_ENDPOINT,
    ORACLE_PEER,
    _Outbound,
    _Resp,
    _add_federated_capability,
    _add_peer,
    _build,
    _open_channel,
    _oracle_envelope,
    _pay_headers,
    _wire,
)

SIGNED = {pra.HUB_HEADER, pra.AUDIENCE_HEADER, pra.TIMESTAMP_HEADER, pra.NONCE_HEADER,
          pra.SIGNATURE_HEADER}

_CORE = Path(__file__).resolve().parents[2] / "oracles" / "core"


def _core_gate():
    """oracle_core.price_gate from the monorepo, or skip (the hub ships without it)."""
    if _CORE.is_dir() and str(_CORE) not in sys.path:
        sys.path.insert(0, str(_CORE))
    return pytest.importorskip("oracle_core.price_gate")


def _verifies(headers, *, signer, capability_id, input_payload):
    canonical = pra.request_canonical(
        hub=headers[pra.HUB_HEADER], audience=headers[pra.AUDIENCE_HEADER],
        capability_id=capability_id, input_digest=pra.input_sha256(input_payload),
        timestamp=int(headers[pra.TIMESTAMP_HEADER]), nonce=headers[pra.NONCE_HEADER],
    )
    return Signer.verify(signer.public_key_b64, headers[pra.SIGNATURE_HEADER], canonical)


def _sold_peer(tmp_path, monkeypatch, *, sells=True, price=0.02):
    if sells:
        monkeypatch.setenv("AIMARKET_SELLS_FOR", ORACLE_PEER)
    else:
        monkeypatch.delenv("AIMARKET_SELLS_FOR", raising=False)
    app, db, config = _build(tmp_path, monkeypatch)
    _add_peer(db, ORACLE_PEER, categories=["oracle"])
    _add_federated_capability(db, ORACLE_PEER, price=price)
    out = _wire(monkeypatch, _Outbound(
        _Resp(200, _oracle_envelope()), well_known={"mcp_endpoint": MCP_ENDPOINT},
    ))
    return app, config, out


def _paid_invoke(client):
    channel_id, secret = _open_channel(deposit=5.0)
    return client.post(
        "/ai-market/v2/invoke", headers=_pay_headers(channel_id, secret),
        json={"product_id": "prod-x", "capability_id": "cap.x@v1",
              "source_hub": ORACLE_PEER, "input": {"q": "hi", "n": 1.5}},
    )


# ── The wire format ──────────────────────────────────────────────────────────────


def test_the_wire_format_is_the_one_oracle_core_pins():
    """Same vector as oracles/core/tests/test_price_gate.py::test_the_wire_format_is_pinned."""
    canonical = pra.request_canonical(
        hub="https://Hub.Example:443/", audience="https://provider.example/oracle/ai-market/v2/invoke",
        capability_id="gate.priced@v1", input_digest=pra.input_sha256({"msg": "hi", "n": 1.5}),
        timestamp=1_792_000_000, nonce="0123456789abcdef0123456789abcdef",
    )
    assert canonical == (
        "aimarket-hub-request/v1\n"
        '{"aud":"https://provider.example/oracle/ai-market/v2/invoke",'
        '"capability_id":"gate.priced@v1","hub":"https://hub.example",'
        '"input_sha256":"e119189c8dcefbf9474d5d89322c15b79c9d1424a8a31a923ec1b3f93d39f41a",'
        '"nonce":"0123456789abcdef0123456789abcdef","ts":1792000000}'
    )
    sk = Ed25519PrivateKey.from_private_bytes(b"\x07" * 32)
    assert base64.b64encode(sk.sign(canonical.encode())).decode() == (
        "fmyP68mgVGsglcunDqMxC5lgRpp1pGTdeGNEWDcfRX9UpoKofYudoc+oV+JaNbz8MgPL1shastKc8GRhl0xcDg=="
    )


@pytest.mark.parametrize("payload", [
    {}, None, {"q": "hi"}, {"b": [1, 2.5, {"z": None, "a": True}], "a": "ü—✓"},
    {"nested": {"deep": {"x": -0.0, "y": 1e-7, "big": 2**63}}},
])
@pytest.mark.parametrize("url", [
    "https://modelmarket.dev", "https://Modelmarket.dev:443/", "http://[::1]:9083/hub/",
    "http://gaia-backend:9320/ai-market/v2/invoke",
])
def test_both_copies_agree(payload, url):
    core = _core_gate()
    assert pra.normalize_url(url) == core.normalize_url(url)
    assert pra.input_sha256(payload) == core.input_sha256(payload)
    kw = dict(hub=url, audience=url, capability_id="c@v1", timestamp=1, nonce="ab" * 16)
    assert pra.request_canonical(input_digest=pra.input_sha256(payload), **kw) == \
        core.request_canonical(input_digest=core.input_sha256(payload), **kw)


def test_what_the_hub_signs_the_provider_accepts(tmp_path):
    core = _core_gate()
    signer = Signer(tmp_path / "hub.key")
    headers = pra.signed_headers(
        signer, hub_url="https://modelmarket.dev/", audience="https://p.example/ai-market/v2/invoke",
        capability_id="c@v1", input_payload={"q": "hi"},
    )
    assert set(headers) == SIGNED
    verifier = core.HubRequestVerifier({"https://modelmarket.dev": (signer.public_key_b64,)},
                                       ["https://p.example"])
    assert verifier.verify(headers, "c@v1", {"q": "hi"}).status == "valid"
    assert verifier.verify(headers, "c@v1", {"q": "hi"}).status == "invalid"  # replayed


def test_the_assay_reads_the_providers_402_as_a_payment_door():
    """The apex assay's `sandbox_price_enforced` FAIL ("listed at $x but answered an unpaid
    invoke with 200") becomes a 402 door whose quoted price it can check."""
    core = _core_gate()
    gate = core.PriceGate.from_env(
        "https://iot.modelmarket.dev",
        {"ORACLE_TRUSTED_HUBS": f"https://modelmarket.dev={_key_b64()}"},
    )
    status, body = gate.check("gaia.power.window@v1", 0.002, {}, {})
    assert status == 402
    challenge = parse_payment_challenge(body, {})
    assert challenge == {"price_usd": 0.002, "recipient": "", "rails": ["hub"]}


def _key_b64():
    sk = Ed25519PrivateKey.from_private_bytes(b"\x07" * 32)
    return base64.b64encode(sk.public_key().public_bytes_raw()).decode()


# ── When the hub signs ───────────────────────────────────────────────────────────


def test_a_peer_this_hub_sells_for_gets_a_signed_call(tmp_path, monkeypatch):
    app, config, out = _sold_peer(tmp_path, monkeypatch)
    with TestClient(app) as client:
        r = _paid_invoke(client)
    signer = Signer(config.signing_key_path)  # the same key file the hub signs with
    assert r.status_code == 200, r.text
    sent = out.post_headers[0]
    assert SIGNED <= set(sent)
    assert sent[pra.HUB_HEADER] == pra.normalize_url(config.hub_url)
    assert sent[pra.AUDIENCE_HEADER] == MCP_ENDPOINT
    assert _verifies(sent, signer=signer, capability_id="cap.x@v1", input_payload={"q": "hi", "n": 1.5})
    # The pre-existing headers are untouched.
    assert sent["X-AIMarket-Routing-Hub"] == config.hub_url


def test_a_trial_the_hub_gives_is_signed_too(tmp_path, monkeypatch):
    """The hub decided to give it, so the provider should serve it."""
    monkeypatch.setattr(st, "_ledger", st.SandboxTrialLedger(str(tmp_path / "trials.db")))
    app, config, out = _sold_peer(tmp_path, monkeypatch)
    with TestClient(app) as client:
        r = client.post(
            "/ai-market/v2/invoke", headers={"X-AIMarket-Sandbox-Visitor": "vis_signed_trial_1"},
            json={"product_id": "prod-x", "capability_id": "cap.x@v1",
                  "source_hub": ORACLE_PEER, "input": {"q": "hi"}},
        )
    assert r.status_code == 200, r.text
    assert SIGNED <= set(out.post_headers[0])


def test_a_peer_this_hub_only_brokers_gets_no_signature(tmp_path, monkeypatch):
    """The peer bills the buyer there; a signature would say 'paid' for an unpaid call."""
    app, _, out = _sold_peer(tmp_path, monkeypatch, sells=False)
    with TestClient(app) as client:
        r = _paid_invoke(client)  # pays this hub's routing fee, not the price
    assert r.status_code == 200, r.text
    assert out.post_headers, "the peer was never called"
    assert not SIGNED & set(out.post_headers[0])


def test_an_unpaid_call_never_reaches_the_peer(tmp_path, monkeypatch):
    app, _, out = _sold_peer(tmp_path, monkeypatch)
    with TestClient(app) as client:
        r = client.post("/ai-market/v2/invoke", json={
            "product_id": "prod-x", "capability_id": "cap.x@v1",
            "source_hub": ORACLE_PEER, "input": {"q": "hi"}})
    assert r.status_code == 402
    assert out.posts == []


def test_signing_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("AIMARKET_SIGN_PROVIDER_REQUESTS", "0")
    app, _, out = _sold_peer(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert _paid_invoke(client).status_code == 200
    assert not SIGNED & set(out.post_headers[0])


def test_a_signing_fault_sends_the_call_unsigned_rather_than_failing_it(tmp_path, monkeypatch):
    def boom(self, canonical):
        raise RuntimeError("key unreadable")

    monkeypatch.setattr(Signer, "sign_canonical", boom)
    app, _, out = _sold_peer(tmp_path, monkeypatch)
    with TestClient(app) as client:
        r = _paid_invoke(client)
    assert r.status_code == 200, r.text
    assert not SIGNED & set(out.post_headers[0])


def test_the_headers_never_collide_with_the_subcontract_headers():
    """Both sets go to the same local provider in one dict; one would overwrite the other."""
    from aimarket_hub import subcontract

    assert not SIGNED & {subcontract.HUB_HEADER, subcontract.JOB_HEADER, subcontract.GRANT_HEADER}


def test_signed_headers_refuses_to_sign_without_a_hub_or_an_audience(tmp_path):
    signer = Signer(tmp_path / "k")
    assert pra.signed_headers(signer, hub_url="", audience="https://p", capability_id="c",
                              input_payload={}) == {}
    assert pra.signed_headers(signer, hub_url="https://h", audience="not a url",
                              capability_id="c", input_payload={}) == {}
