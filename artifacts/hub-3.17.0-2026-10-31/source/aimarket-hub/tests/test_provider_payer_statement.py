"""The hub tells a provider who paid for a call it admitted, where the provider needs to know.

The other half is gaia/gaia/payer_identity.py: GAIA leases a plug to the payer of its "on"
and refuses anyone else's "off" until the auto-off, and it believes only a payer a trusted
hub signed next to the price-gate admission of the same call (aimarket-hub-payer/v1).
These tests pin the wire format (GAIA's golden vector), which payer the hub names on each
rail, that it names nobody it did not check, that it tells only the capabilities that need
it, and that a fault never fails the buyer's call.
"""

from __future__ import annotations

import base64
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import aimarket_hub.channels as channels_mod
import aimarket_hub.sandbox_trials as st
from aimarket_hub import provider_request_auth as pra
from aimarket_hub.api import create_app
from aimarket_hub.channels import ChannelLedger
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer

from tests.test_federated_invoke import (
    MCP_ENDPOINT,
    ORACLE_PEER,
    _Outbound,
    _Resp,
    _add_federated_capability,
    _add_peer,
    _build,
    _oracle_envelope,
    _pay_headers,
    _wire,
)

ADMISSION = {pra.HUB_HEADER, pra.AUDIENCE_HEADER, pra.TIMESTAMP_HEADER, pra.NONCE_HEADER,
             pra.SIGNATURE_HEADER}
STATEMENT = {pra.PAYER_HEADER, pra.PAYER_RAIL_HEADER, pra.PAYER_SIGNATURE_HEADER}

_ROOT = Path(__file__).resolve().parents[2]

# gaia/tests/test_payer_identity.py::test_the_wire_format_is_pinned_by_a_golden_vector: the
# price gate's own fixture (seed 07×32, the same hub, audience, capability, input, time and
# nonce) plus a payer and a rail.
GOLDEN = dict(hub="https://Hub.Example:443/",
              audience="https://provider.example/oracle/ai-market/v2/invoke",
              capability_id="gate.priced@v1", input_payload={"msg": "hi", "n": 1.5},
              timestamp=1792000000, nonce="0123456789abcdef0123456789abcdef",
              payer="0x" + "AB" * 20, rail="channel")
GOLDEN_PUBKEY = "6kpsY+KcUgq+9VB7Ey7F+ZVHdq6+vnuSQh7qaRRG0iw="
GOLDEN_CANONICAL = (
    'aimarket-hub-payer/v1\n{"aud":"https://provider.example/oracle/ai-market/v2/invoke",'
    '"capability_id":"gate.priced@v1","hub":"https://hub.example",'
    '"input_sha256":"e119189c8dcefbf9474d5d89322c15b79c9d1424a8a31a923ec1b3f93d39f41a",'
    '"nonce":"0123456789abcdef0123456789abcdef",'
    '"payer":"0xabababababababababababababababababababab","rail":"channel","ts":1792000000}')
GOLDEN_SIGNATURE = ("bD78JNaEh3ZRhvL7aFMVPUHv5Ys0fTBSAszy9MlnteErc7ul6hUj5kFfFLIIAqpQSitGbPLV"
                    "ymyzYRDVkgBECQ==")

CAP_ID = "gaia.actuate@v1"
INPUT = {"actuator_id": "plug-sim-01", "command": "on", "duration_s": 60}
PAYER = "0x" + "Ab" * 20                      # EIP-55-style case: sent lowercased
OTHER = "0x" + "cd" * 20
GOOD_PROOF = "0xgoodproof"


class _SeedSigner:
    """The golden vector's key, behind the one method the hub's Signer offers."""

    def __init__(self, seed: bytes = b"\x07" * 32):
        self._sk = Ed25519PrivateKey.from_private_bytes(seed)

    def sign_canonical(self, canonical: str) -> str:
        return base64.b64encode(self._sk.sign(canonical.encode())).decode()


def _golden_admission() -> dict[str, str]:
    g = GOLDEN
    return {pra.HUB_HEADER: pra.normalize_url(g["hub"]),
            pra.AUDIENCE_HEADER: pra.normalize_url(g["audience"]),
            pra.TIMESTAMP_HEADER: str(g["timestamp"]), pra.NONCE_HEADER: g["nonce"],
            pra.SIGNATURE_HEADER: "(the admission's own)"}


def _gaia_identity():
    """gaia.payer_identity from the monorepo, or skip (the hub ships without it)."""
    for part in ("oracles/core", "gaia"):
        path = str(_ROOT / part)
        if (_ROOT / part).is_dir() and path not in sys.path:
            sys.path.insert(0, path)
    return pytest.importorskip("gaia.payer_identity")


def _statement_verifies(headers, *, signer, capability_id, input_payload) -> bool:
    canonical = pra.payer_canonical(
        hub=headers[pra.HUB_HEADER], audience=headers[pra.AUDIENCE_HEADER],
        capability_id=capability_id, input_digest=pra.input_sha256(input_payload),
        timestamp=int(headers[pra.TIMESTAMP_HEADER]), nonce=headers[pra.NONCE_HEADER],
        payer=headers[pra.PAYER_HEADER], rail=headers[pra.PAYER_RAIL_HEADER],
    )
    return Signer.verify(signer.public_key_b64, headers[pra.PAYER_SIGNATURE_HEADER], canonical)


# ── The wire format ──────────────────────────────────────────────────────────────


def test_the_wire_format_is_gaias_golden_vector():
    g = GOLDEN
    canonical = pra.payer_canonical(
        hub=g["hub"], audience=g["audience"], capability_id=g["capability_id"],
        input_digest=pra.input_sha256(g["input_payload"]), timestamp=g["timestamp"],
        nonce=g["nonce"], payer=g["payer"], rail=g["rail"],
    )
    assert canonical == GOLDEN_CANONICAL
    sk = Ed25519PrivateKey.from_private_bytes(b"\x07" * 32)
    assert base64.b64encode(sk.public_key().public_bytes_raw()).decode() == GOLDEN_PUBKEY
    assert base64.b64encode(sk.sign(canonical.encode())).decode() == GOLDEN_SIGNATURE


def test_the_headers_reproduce_the_golden_vector(monkeypatch):
    """What the hub puts on the wire, for the vector's call, is the vector."""
    g = GOLDEN
    monkeypatch.setenv(pra.PAYER_CAPABILITIES_ENV, g["capability_id"])
    out = pra.payer_headers(
        _SeedSigner(), _golden_admission(), capability_id=g["capability_id"],
        input_payload=g["input_payload"], payer=g["payer"], rail=g["rail"],
    )
    assert out == {pra.PAYER_HEADER: "0x" + "ab" * 20, pra.PAYER_RAIL_HEADER: "channel",
                   pra.PAYER_SIGNATURE_HEADER: GOLDEN_SIGNATURE}
    assert Signer.verify(GOLDEN_PUBKEY, GOLDEN_SIGNATURE, GOLDEN_CANONICAL)


def test_both_copies_agree_with_gaia():
    gaia = _gaia_identity()
    assert pra.PAYER_DOMAIN == gaia.DOMAIN
    for name in ("HUB_HEADER", "AUDIENCE_HEADER", "TIMESTAMP_HEADER", "NONCE_HEADER"):
        assert getattr(pra, name) == getattr(gaia, name)
    assert (pra.PAYER_HEADER, pra.PAYER_RAIL_HEADER, pra.PAYER_SIGNATURE_HEADER) == (
        gaia.PAYER_HEADER, gaia.RAIL_HEADER, gaia.PAYER_SIGNATURE_HEADER)
    assert pra.PAYER_RAILS == gaia.RAILS
    for raw in ("0x" + "Ab" * 20, "  0x" + "12" * 20 + " ",
                "7EcDhSYGxXyscszYEp35KHN8vvw3svAuLKTzXwCFLtV"):
        assert pra.normalize_payer(raw) == gaia.normalize_identity(raw)
    for raw in ("", "buyer-1", "0x" + "ab" * 19, "0x" + "zz" * 20, "0O" + "1" * 40, None):
        with pytest.raises(ValueError):
            pra.normalize_payer(raw)
        with pytest.raises(ValueError):
            gaia.normalize_identity(raw)
    kw = dict(hub="https://Modelmarket.dev:443/", audience="http://gaia-backend:9320/ai-market/v2/invoke",
              capability_id=CAP_ID, input_digest=pra.input_sha256(INPUT), timestamp=1,
              nonce="ab" * 16, payer=PAYER, rail="x402")
    assert pra.payer_canonical(**kw) == gaia.payer_canonical(**kw)
    g = GOLDEN
    assert gaia.sign_payer(_SeedSigner().sign_canonical, hub_url=g["hub"], audience=g["audience"],
                           capability_id=g["capability_id"], input_payload=g["input_payload"],
                           payer=g["payer"], rail=g["rail"], timestamp=g["timestamp"],
                           nonce=g["nonce"])[gaia.PAYER_SIGNATURE_HEADER] == GOLDEN_SIGNATURE


def test_what_the_hub_states_gaia_accepts_for_that_call_only(tmp_path):
    gaia = _gaia_identity()
    signer = Signer(tmp_path / "hub.key")
    aud = "https://iot.modelmarket.dev/ai-market/v2/invoke"
    admission = pra.signed_headers(signer, hub_url="https://modelmarket.dev/", audience=aud,
                                   capability_id=CAP_ID, input_payload=INPUT)
    headers = {**admission, **pra.payer_headers(signer, admission, capability_id=CAP_ID,
                                                input_payload=INPUT, payer=PAYER, rail="channel")}
    assert ADMISSION | STATEMENT == set(headers)
    ts = int(headers[pra.TIMESTAMP_HEADER])
    verifier = gaia.PayerVerifier({"https://modelmarket.dev": [signer.public_key_b64]},
                                  ["https://iot.modelmarket.dev"], clock=lambda: ts)
    other_input = {**INPUT, "duration_s": 900}
    assert "does not verify" in verifier.resolve(headers, CAP_ID, other_input).problem
    out = verifier.resolve(headers, CAP_ID, INPUT)
    assert out.caller == gaia.Caller(PAYER.lower(), vouched_by="https://modelmarket.dev",
                                     rail="channel")


def test_the_statement_is_for_the_admissions_own_call(tmp_path, monkeypatch):
    """Same signer, audience, time and nonce as the admission: read back, never re-made."""
    signer = Signer(tmp_path / "hub.key")
    admission = pra.signed_headers(signer, hub_url="https://h.example", audience="https://p.example/x",
                                   capability_id=CAP_ID, input_payload=INPUT, now=1_792_000_123)
    monkeypatch.setattr(pra.secrets, "token_hex", lambda n: pytest.fail("a second nonce was made"))
    monkeypatch.setattr(pra.time, "time", lambda: pytest.fail("a second clock read"))
    out = pra.payer_headers(signer, admission, capability_id=CAP_ID, input_payload=INPUT,
                            payer=PAYER, rail="x402")
    assert _statement_verifies({**admission, **out}, signer=signer, capability_id=CAP_ID,
                               input_payload=INPUT)
    assert admission[pra.TIMESTAMP_HEADER] == "1792000123"


@pytest.mark.parametrize("kw", [
    dict(payer=""),                                   # nobody checked
    dict(payer="buyer-1"),                            # not a wallet
    dict(rail="credits"),                             # not a rail GAIA knows
    dict(capability_id="symmartys.vat.check@v1"),      # does not need one
])
def test_no_statement_rather_than_a_wrong_one(tmp_path, kw):
    signer = Signer(tmp_path / "hub.key")
    admission = pra.signed_headers(signer, hub_url="https://h.example", audience="https://p.example/x",
                                   capability_id=CAP_ID, input_payload=INPUT)
    args = {"capability_id": CAP_ID, "input_payload": INPUT, "payer": PAYER, "rail": "channel", **kw}
    assert pra.payer_headers(signer, admission, **args) == {}


def test_no_admission_no_statement(tmp_path):
    """Signing switched off (or failed) leaves the statement out too: it has no call to name."""
    signer = Signer(tmp_path / "hub.key")
    assert pra.payer_headers(signer, {}, capability_id=CAP_ID, input_payload=INPUT,
                             payer=PAYER, rail="channel") == {}


def test_the_list_of_capabilities_is_the_operators(monkeypatch):
    monkeypatch.delenv(pra.PAYER_CAPABILITIES_ENV, raising=False)
    assert pra.payer_statement_wanted("gaia.actuate@v1")
    assert not pra.payer_statement_wanted("gaia.power.window@v1")
    monkeypatch.setenv(pra.PAYER_CAPABILITIES_ENV, " a.b@v1 , gaia.actuate@v1")
    assert pra.payer_statement_wanted("a.b@v1") and pra.payer_statement_wanted("gaia.actuate@v1")
    monkeypatch.setenv(pra.PAYER_CAPABILITIES_ENV, "")
    assert not pra.payer_statement_wanted("gaia.actuate@v1")


def test_the_headers_never_collide_with_the_others():
    from aimarket_hub import subcontract

    assert not STATEMENT & (ADMISSION | {subcontract.HUB_HEADER, subcontract.JOB_HEADER,
                                         subcontract.GRANT_HEADER})


# ── Which payer a channel names: only the one its opener proved ───────────────────


def _prod_mode(monkeypatch, *, senders: dict[str, str]):
    """channels on the production path, as tests/test_channels.py::_prod_mode puts it: the
    chain reports the sender of each tx, and the payer proof recovers the claimed payer for
    GOOD_PROOF and nothing else (eth_account is not needed for that shape)."""
    monkeypatch.setattr(channels_mod, "_is_production_mode", lambda: True)
    monkeypatch.setattr(channels_mod, "_VERIFY_STUB", False)
    monkeypatch.setattr(channels_mod, "_verify_tx_onchain",
                        lambda **kw: {"ok": True, "sender": senders[kw["tx_hash"]]})
    monkeypatch.setattr(
        channels_mod, "_recover_payer_address",
        lambda *, payer, tx_hash, chain, deposit_usd, signature: (
            senders[tx_hash] if signature == GOOD_PROOF else None),
    )


def _proven_channel(ledger, tx_hash: str) -> tuple[str, str]:
    ch = ledger.open(5.0, tx_hash=tx_hash, payer_signature=GOOD_PROOF)["channel"]
    return ch["channel_id"], ch["channel_secret"]


def test_a_proven_open_records_the_payer_and_nothing_else_does(tmp_path, monkeypatch):
    ledger = ChannelLedger(db_path=str(tmp_path / "ch.db"))
    monkeypatch.setattr(channels_mod, "_ledger", ledger)
    try:
        monkeypatch.setattr(channels_mod, "_allow_demo_credit", lambda: True)
        demo = ledger.open(5.0, wallet=PAYER)["channel"]          # typed, not proven
        assert demo["wallet"] == PAYER and channels_mod.channel_payer(demo["channel_id"]) == ""

        _prod_mode(monkeypatch, senders={"0xdep1": PAYER, "0xdep2": OTHER})
        proven, _ = _proven_channel(ledger, "0xdep1")
        assert channels_mod.channel_payer(proven) == PAYER
        monkeypatch.setattr(channels_mod, "_allow_unproven_payer", lambda: True)
        unproven = ledger.open(5.0, tx_hash="0xdep2")["channel"]  # opt-out: no proof asked
        assert unproven["wallet"] == OTHER and channels_mod.channel_payer(unproven["channel_id"]) == ""
        assert channels_mod.channel_payer("ch_unknown") == "" and channels_mod.channel_payer("") == ""
    finally:
        ledger.stop_sweep()


def test_a_proven_escrow_open_records_the_depositor(tmp_path, monkeypatch):
    depositor = "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c"
    ledger = ChannelLedger(db_path=str(tmp_path / "esc.db"))
    try:
        monkeypatch.setattr(channels_mod, "_ledger", ledger)
        monkeypatch.setattr(ledger, "_verify_escrow_funding",
                            lambda **kw: (True, "", "escrow:" + kw["escrow_channel_id"]))
        monkeypatch.setattr(channels_mod, "_recover_payer_address",
                            lambda **kw: depositor if kw.get("signature") == "good" else None)
        squat = ledger.open(deposit_usd=5.0, wallet=depositor, escrow_channel_id="0x" + "e1" * 32)
        assert channels_mod.channel_payer(squat["channel"]["channel_id"]) == ""
        mine = ledger.open(deposit_usd=5.0, wallet=depositor, escrow_channel_id="0x" + "e1" * 32,
                           payer_signature="good")
        assert channels_mod.channel_payer(mine["channel"]["channel_id"]) == depositor
    finally:
        ledger.stop_sweep()


def test_a_lookup_fault_names_nobody(monkeypatch):
    class _Broken:
        def proven_payer_for(self, channel_id):
            raise RuntimeError("db gone")

    monkeypatch.setattr(channels_mod, "_ledger", _Broken())
    assert channels_mod.channel_payer("ch_x") == ""


# ── Through the invoke route: a local listing (how apex reaches GAIA) ─────────────


def _capture_provider(monkeypatch) -> list[dict[str, str]]:
    import aimarket_hub.outbound_http as outbound

    seen: list[dict[str, str]] = []

    class _Resp200:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"ok": true}'

        @staticmethod
        def json():
            return {"ok": True, "output": {"switched": True}}

    async def _post(url, **kwargs):
        seen.append(dict(kwargs.get("headers") or {}))
        return _Resp200()

    monkeypatch.setattr(outbound, "safe_post", _post)
    return seen


@contextmanager
def _local_hub(monkeypatch, tmp_path, *, capability_id=CAP_ID, price=0.05, payout="", **env):
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://hub.example")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    ledger = ChannelLedger(db_path=str(tmp_path / "channels.db"))
    monkeypatch.setattr(channels_mod, "_ledger", ledger)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "hub.key")
    db = HubDatabase(config.db_path)
    db.upsert_capability(Capability(
        capability_id=capability_id, product_id="gaia.gateway", name="switch", version="v1",
        description="", input_schema={}, output_schema={}, price_per_call_usd=price,
        source_hub="local", invoke_url="https://iot.example/ai-market/v2/invoke",
        payout_address=payout,
    ))
    signer = Signer(config.signing_key_path)
    app = create_app(config=config, db=db, signer=signer)
    try:
        with TestClient(app) as client:
            yield client, ledger, signer
    finally:
        ledger.stop_sweep()


def _invoke(client, headers, *, capability_id=CAP_ID, inp=INPUT):
    return client.post("/ai-market/v2/invoke", headers=headers, json={
        "product_id": "gaia.gateway", "capability_id": capability_id, "source_hub": "local",
        "input": inp})


def test_a_proven_channels_payer_is_stated_next_to_the_admission(tmp_path, monkeypatch):
    seen = _capture_provider(monkeypatch)
    with _local_hub(monkeypatch, tmp_path) as (client, ledger, signer):
        _prod_mode(monkeypatch, senders={"0xdepA": PAYER})
        channel_id, secret = _proven_channel(ledger, "0xdepA")
        r = _invoke(client, _pay_headers(channel_id, secret))
    assert r.status_code == 200, r.text
    sent = seen[0]
    assert ADMISSION | STATEMENT <= set(sent)
    assert sent[pra.PAYER_HEADER] == PAYER.lower() and sent[pra.PAYER_RAIL_HEADER] == "channel"
    assert sent[pra.HUB_HEADER] == "https://hub.example"
    assert sent[pra.AUDIENCE_HEADER] == "https://iot.example/ai-market/v2/invoke"
    assert _statement_verifies(sent, signer=signer, capability_id=CAP_ID, input_payload=INPUT)
    # The rest of what a provider is told about the buyer stays opaque.
    assert channel_id not in json.dumps(sent)


def test_a_demo_credit_channel_names_nobody(tmp_path, monkeypatch):
    seen = _capture_provider(monkeypatch)
    with _local_hub(monkeypatch, tmp_path, AIMARKET_ALLOW_DEMO_CREDIT="1") as (client, ledger, _):
        ch = ledger.open(5.0, wallet=PAYER)["channel"]   # a wallet typed at open is no proof
        r = _invoke(client, _pay_headers(ch["channel_id"], ch["channel_secret"]))
    assert r.status_code == 200, r.text
    assert ADMISSION <= set(seen[0]) and not STATEMENT & set(seen[0])


def test_a_trial_names_nobody(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "_ledger", st.SandboxTrialLedger(str(tmp_path / "trials.db")))
    seen = _capture_provider(monkeypatch)
    with _local_hub(monkeypatch, tmp_path) as (client, _, _):
        r = _invoke(client, {"X-AIMarket-Sandbox-Visitor": "vis_payer_trial_1"})
    assert r.status_code == 200, r.text
    assert ADMISSION <= set(seen[0]) and not STATEMENT & set(seen[0])


def test_a_capability_that_does_not_need_it_is_not_told_the_payer(tmp_path, monkeypatch):
    seen = _capture_provider(monkeypatch)
    with _local_hub(monkeypatch, tmp_path, capability_id="gaia.power.window@v1") as (client, ledger, _):
        _prod_mode(monkeypatch, senders={"0xdepB": PAYER})
        channel_id, secret = _proven_channel(ledger, "0xdepB")
        r = _invoke(client, _pay_headers(channel_id, secret), capability_id="gaia.power.window@v1")
    assert r.status_code == 200, r.text
    assert ADMISSION <= set(seen[0]) and not STATEMENT & set(seen[0])


@pytest.mark.parametrize("target", [
    "aimarket_hub.provider_request_auth.payer_canonical",   # signing the statement
    "aimarket_hub.hub_routes.invoke.channel_payer",         # finding the payer
])
def test_a_statement_fault_sends_the_call_without_one(tmp_path, monkeypatch, target):
    seen = _capture_provider(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("fault")

    with _local_hub(monkeypatch, tmp_path) as (client, ledger, _):
        _prod_mode(monkeypatch, senders={"0xdepC": PAYER})
        channel_id, secret = _proven_channel(ledger, "0xdepC")
        monkeypatch.setattr(target, boom)
        r = _invoke(client, _pay_headers(channel_id, secret))
    assert r.status_code == 200, r.text
    assert ADMISSION <= set(seen[0]) and not STATEMENT & set(seen[0])


def _x402_settled(monkeypatch, *, price: float, authorizer: str):
    """The chain says this transfer paid the seller, authorized by ``authorizer``
    (tests/test_credits_invoke.py::_settled, with the payer named)."""
    from aimarket_hub import settle

    def _verify(*, tx_hash, terms, timeout=10.0, max_age_s=0, paid_before=None,
                require_nonce, rpc_url=""):
        return {"tx_hash": tx_hash, "paid_units": settle.to_units(price, terms.decimals),
                "authorizer": authorizer}

    monkeypatch.setattr(settle, "verify_transfer", _verify)


def test_an_x402_payer_is_the_authorizer_the_chain_settled(tmp_path, monkeypatch):
    seen = _capture_provider(monkeypatch)
    with _local_hub(monkeypatch, tmp_path, payout="0x" + "5e" * 20, AIMARKET_X402_ACCEPT="1",
                    AIMARKET_CREDITS_ENABLED="0",
                    AIMARKET_PAYMENT_RECIPIENT="0x" + "cd" * 20) as (client, _, signer):
        _x402_settled(monkeypatch, price=0.05, authorizer=OTHER)
        quote = _invoke(client, {})
        assert quote.status_code == 402, quote.text
        r = _invoke(client, {"X-Payment": "0x" + "11" * 32, "X-Payment-Nonce": quote.json()["nonce"],
                             "X-Payment-Secret": quote.json()["payment_secret"]})
    assert r.status_code == 200, r.text
    sent = seen[-1]
    assert sent[pra.PAYER_HEADER] == OTHER and sent[pra.PAYER_RAIL_HEADER] == "x402"
    assert _statement_verifies(sent, signer=signer, capability_id=CAP_ID, input_payload=INPUT)


# ── Through the invoke route: a federated peer this hub sells for ─────────────────


def _sold_peer(tmp_path, monkeypatch, *, sells=True):
    if sells:
        monkeypatch.setenv("AIMARKET_SELLS_FOR", ORACLE_PEER)
    else:
        monkeypatch.delenv("AIMARKET_SELLS_FOR", raising=False)
    monkeypatch.setenv(pra.PAYER_CAPABILITIES_ENV, "cap.x@v1")
    app, db, config = _build(tmp_path, monkeypatch)
    _add_peer(db, ORACLE_PEER, categories=["oracle"])
    _add_federated_capability(db, ORACLE_PEER, price=0.02)
    out = _wire(monkeypatch, _Outbound(
        _Resp(200, _oracle_envelope()), well_known={"mcp_endpoint": MCP_ENDPOINT},
    ))
    return app, config, out


def _fed_paid(client, channel_id, secret):
    return client.post(
        "/ai-market/v2/invoke", headers=_pay_headers(channel_id, secret),
        json={"product_id": "prod-x", "capability_id": "cap.x@v1",
              "source_hub": ORACLE_PEER, "input": {"q": "hi", "n": 1.5}},
    )


def test_a_sold_peer_is_told_the_proven_payer(tmp_path, monkeypatch):
    app, config, out = _sold_peer(tmp_path, monkeypatch)
    with TestClient(app) as client:
        _prod_mode(monkeypatch, senders={"0xdepF": PAYER})
        channel_id, secret = _proven_channel(channels_mod._ledger, "0xdepF")
        r = _fed_paid(client, channel_id, secret)
    assert r.status_code == 200, r.text
    sent = out.post_headers[0]
    assert sent[pra.PAYER_HEADER] == PAYER.lower() and sent[pra.PAYER_RAIL_HEADER] == "channel"
    assert sent[pra.AUDIENCE_HEADER] == MCP_ENDPOINT
    assert _statement_verifies(sent, signer=Signer(config.signing_key_path), capability_id="cap.x@v1",
                               input_payload={"q": "hi", "n": 1.5})


def test_a_brokered_peer_is_told_nobody(tmp_path, monkeypatch):
    """No admission there (the peer bills the buyer itself), so no statement either."""
    app, _, out = _sold_peer(tmp_path, monkeypatch, sells=False)
    with TestClient(app) as client:
        _prod_mode(monkeypatch, senders={"0xdepG": PAYER})
        channel_id, secret = _proven_channel(channels_mod._ledger, "0xdepG")
        r = _fed_paid(client, channel_id, secret)
    assert r.status_code == 200, r.text
    assert not (ADMISSION | STATEMENT) & set(out.post_headers[0])
