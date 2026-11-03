"""Supply-side security — stake, rate limits, LUMEN trust, response signatures."""

from __future__ import annotations

import json
import base64
import logging
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.publish import validate_manifest
from aimarket_hub.signing import Signer
from aimarket_hub.supply_security import (
    SupplySecurity,
    SupplySecurityPolicy,
    TrustOracleUnavailable,
    _TRUST_UNSCORED,
)

PUBLISH_TOKEN = "sec-test-token"
PUBLISH_HEADERS = {"Authorization": f"Bearer {PUBLISH_TOKEN}"}

MANIFEST = {
    "product_id": "sec-demo",
    "capability_id": "secure.greet@v1",
    "name": "secure greet",
    "description": "Signed provider demo",
    "invoke_url": "http://127.0.0.1:3457/invoke",
    "price_per_call_usd": 0.02,
    "publisher_id": "pub-wallet-1",
    "provider_pubkey": "",
    "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}},
    "output_schema": {"type": "object", "properties": {"greeting": {"type": "string"}}},
}


class _ProviderResp:
    status_code = 200
    text = ""

    def __init__(self, payload: dict, headers: dict | None = None):
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


@pytest.fixture
def keys_and_signer(tmp_path):
    key_path = tmp_path / "provider_key"
    signer = Signer(key_path)
    return signer.public_key_b64, signer


class _Lumen:
    """Deterministic stand-in for the LUMEN oracle client.

    The real client talks to oracles.modelmarket.dev, so any test that lets it through is
    (a) network-dependent and (b) silently exercising whatever the live graph says today.
    """

    def __init__(self, result: dict | None = None):
        self.result = result if result is not None else _healthy(0.8)
        self.calls: list[tuple[str, list]] = []

    def score_entity(self, entity_id: str, edges):
        self.calls.append((entity_id, list(edges)))
        return dict(self.result)


def _healthy(score: float) -> dict:
    return {"score": score, "degraded": False, "unavailable": False}


def _outage(reason: str = "http_503") -> dict:
    return {"score": None, "degraded": True, "unavailable": True, "reason": reason}


def _no_signal(reason: str = "no_edges") -> dict:
    return {"score": None, "degraded": True, "unavailable": False, "reason": reason}


@pytest.fixture
def hub_client(monkeypatch, keys_and_signer):
    pubkey, provider_signer = keys_and_signer
    monkeypatch.setenv("AIMARKET_PUBLISH_TOKEN", PUBLISH_TOKEN)
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SANDBOX_STUB_INVOKE", "1")
    monkeypatch.setenv("AIFACTORY_PUBLIC_URL", "http://factory.test")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")

    manifest = {**MANIFEST, "provider_pubkey": pubkey}

    class _RoutingAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *a, **k):
            if "127.0.0.1:3457" in url:
                inp = (k.get("json") or {}).get("input", {})
                name = inp.get("name", "world")
                result = {"greeting": f"Hello, {name}!"}
                from aimarket_hub.supply_security import _bound_response_canonical
                request_body = k.get("json") or {}
                canonical = _bound_response_canonical(request_body.get("capability_id", ""),
                    request_body.get("product_id", ""), inp, result)
                sig = provider_signer.sign_canonical(canonical)
                return _ProviderResp({"success": True, "result": result}, {"X-Provider-Signature": sig})
            return _ProviderResp({"output": {}})

    import aimarket_hub.api as api_mod

    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _RoutingAsyncClient)

    with tempfile.TemporaryDirectory() as tmp:
        config = HubConfig()
        config.db_path = str(Path(tmp) / "test.db")
        config.signing_key_path = str(Path(tmp) / "hub_key")
        db = HubDatabase(config.db_path)
        signer = Signer(config.signing_key_path)
        app = create_app(config=config, db=db, signer=signer)
        # Pin the trust oracle: otherwise these API tests hit the live LUMEN endpoint and
        # their trust gates depend on the network and on today's real graph.
        app.state.supply_security.lumen = _Lumen(_healthy(0.8))
        with TestClient(app) as client:
            yield client, manifest, db


class TestSupplySecurityPolicy:
    def test_relaxed_zero_stake(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "1")
        pol = SupplySecurityPolicy.from_config(HubConfig())
        assert pol.min_stake_usd == 0.0
        assert pol.relaxed is True


class TestSupplySecurityUnit:
    def test_stake_and_publish_gate(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
        monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "10")
        monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")
        db_path = tmp_path / "unit.db"
        db = HubDatabase(db_path)
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        with patch.object(sec.lumen, "score_entity", return_value={"score": 0.6, "degraded": False}):
            body = {**MANIFEST, "provider_pubkey": "dGVzdA=="}
            with pytest.raises(ValueError, match="minimum stake"):
                sec.validate_publish(body)
            sec.stake("pub-wallet-1", 15.0, "tx-demo")
            pub_id, _ = sec.validate_publish(body)
            assert pub_id == "pub-wallet-1"

    def test_sanitize_blocks_secrets(self, tmp_path):
        db = HubDatabase(tmp_path / "san.db")
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        with pytest.raises(ValueError, match="sensitive"):
            sec.sanitize_input({"api_key": "leak"})

    def test_verify_response_signature(self, tmp_path, keys_and_signer, monkeypatch):
        monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
        pubkey, provider_signer = keys_and_signer
        db = HubDatabase(tmp_path / "sig.db")
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.policy.require_response_signature = True
        cap = validate_manifest({**MANIFEST, "provider_pubkey": pubkey, "publisher_id": "p1"})
        cap.provider_pubkey = pubkey
        result = {"greeting": "hi"}
        from aimarket_hub.supply_security import _bound_response_canonical
        canonical = _bound_response_canonical(cap.capability_id, "", None, result)
        sig = provider_signer.sign_canonical(canonical)
        sec.verify_provider_response(cap, result, sig)
        legacy = provider_signer.sign_canonical(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        with pytest.raises(ValueError, match="invalid provider"):
            sec.verify_provider_response(cap, result, legacy)
        for altered in ({"product_id": "other"}, {"input_payload": {"name": "other"}}):
            with pytest.raises(ValueError, match="invalid provider"):
                sec.verify_provider_response(cap, result, sig, **altered)
        with pytest.raises(ValueError, match="invalid provider"):
            sec.verify_provider_response(cap, result, base64.b64encode(b"\x00" * 64).decode())


class TestSupplyApi:
    def test_stake_register_invoke(self, hub_client):
        client, manifest, db = hub_client
        stake = client.post(
            "/ai-market/v2/supply/stake",
            json={"publisher_id": "pub-wallet-1", "amount_usd": 20.0, "tx_hash": "0xabc"},
            headers=PUBLISH_HEADERS,
        )
        assert stake.status_code == 200
        assert stake.json()["stake_usd"] == 20.0

        reg = client.post("/ai-market/v2/supply/register", json=manifest, headers=PUBLISH_HEADERS)
        assert reg.status_code == 200
        body = reg.json()
        assert body["published"] is True
        assert body["trust_score"] >= 0

        inv = client.post("/ai-market/v2/invoke", json={
            "product_id": "sec-demo",
            "capability_id": "secure.greet@v1",
            "source_hub": "local",
            "input": {"name": "argus"},
        })
        assert inv.status_code == 200
        assert inv.json()["result"]["greeting"] == "Hello, argus!"

    def test_publish_rate_limit(self, hub_client, monkeypatch):
        client, manifest, _ = hub_client
        monkeypatch.delenv("AIMARKET_SUPPLY_SECURITY_RELAXED", raising=False)
        monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "0")
        monkeypatch.setenv("AIMARKET_SUPPLY_PUBLISH_PER_HOUR", "1")
        monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")

        with tempfile.TemporaryDirectory() as tmp:
            config = HubConfig()
            config.db_path = str(Path(tmp) / "rate.db")
            config.signing_key_path = str(Path(tmp) / "key")
            db = HubDatabase(config.db_path)
            signer = Signer(config.signing_key_path)
            app = create_app(config=config, db=db, signer=signer)
            with TestClient(app) as c:
                c.post("/ai-market/v2/supply/register", json=manifest, headers=PUBLISH_HEADERS)
                second = c.post(
                    "/ai-market/v2/supply/register",
                    json={**manifest, "capability_id": "secure.greet2@v1"},
                    headers=PUBLISH_HEADERS,
                )
                assert second.status_code == 400
                assert "rate limit" in second.json()["detail"]

    def test_search_hides_low_trust(self, hub_client):
        client, manifest, db = hub_client
        client.post("/ai-market/v2/supply/stake", json={"publisher_id": "pub-wallet-1", "amount_usd": 5}, headers=PUBLISH_HEADERS)
        client.post("/ai-market/v2/supply/register", json=manifest, headers=PUBLISH_HEADERS)
        db.supply_set_publisher_trust("pub-wallet-1", 0.1)
        search = client.get("/ai-market/v2/search", params={"intent": "secure", "min_trust": 0.25})
        ids = [m["capability_id"] for m in search.json()["matches"]]
        assert "secure.greet@v1" not in ids

# ── Verify-first wiring + DB-backed failure streak (production entry points) ──────


def test_create_app_wires_verify_first_escalation(tmp_path):
    """A cheap guard that dies if `verify_svc.attach_supply_security(...)` is dropped
    or reordered in create_app — otherwise the whole verified-failure slash ladder is
    silently dead in production while every unit test still passes."""
    config = HubConfig()
    config.db_path = str(tmp_path / "wire.db")
    config.signing_key_path = str(tmp_path / "wire_key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    with TestClient(app):
        assert app.state.verify_svc._supply_security is app.state.supply_security


class _FailingProviderClient:
    """Outbound client that answers the provider invoke_url with a 5xx."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, *a, **k):
        if "127.0.0.1:3457" in url:
            r = _ProviderResp({"error": "provider exploded"})
            r.status_code = 500
            return r
        return _ProviderResp({"output": {}})


def test_invoke_5xx_streak_accumulates_and_slashes_over_http(tmp_path, monkeypatch):
    """End-to-end coverage of the PRODUCTION slash entry point: N provider 5xx invokes
    over HTTP must write supply_fault_events rows and fire one calibrated slash. Guards
    the api.py handler (>=500 branch, cap.publisher_id, record_invoke call) — a unit test
    on record_invoke alone cannot catch a regression there."""
    monkeypatch.setenv("AIMARKET_PUBLISH_TOKEN", PUBLISH_TOKEN)
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_FAILURE_THRESHOLD", "2")
    monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_COOLDOWN_S", "0")
    monkeypatch.delenv("AIMARKET_SANDBOX_STUB_INVOKE", raising=False)

    import aimarket_hub.api as api_mod
    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _FailingProviderClient)

    config = HubConfig()
    config.db_path = str(tmp_path / "streak.db")
    config.signing_key_path = str(tmp_path / "streak_key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    # Pin LUMEN: otherwise this hits live oracles.modelmarket.dev, an oracle 403
    # fails-closed as untrusted, and invoke returns 403 before the provider 5xx.
    app.state.supply_security.lumen = _Lumen(_healthy(0.8))
    with TestClient(app) as client:
        client.post("/ai-market/v2/supply/stake",
                    json={"publisher_id": "pub-wallet-1", "amount_usd": 20.0, "tx_hash": "0xabc"},
                    headers=PUBLISH_HEADERS)
        client.post("/ai-market/v2/supply/register", json=MANIFEST, headers=PUBLISH_HEADERS)

        for _ in range(2):
            r = client.post("/ai-market/v2/invoke", json={
                "product_id": "sec-demo", "capability_id": "secure.greet@v1",
                "source_hub": "local", "input": {"name": "x"},
            })
            assert r.status_code == 502  # provider 5xx surfaces to the consumer

        assert db.supply_slash_events_recent("pub-wallet-1"), "2nd 5xx should have fired a slash"
        assert db.supply_stake_get("pub-wallet-1") < 20.0  # stake actually reduced

    # A 4xx must NOT be counted as a provider fault (boundary guard, both directions).
    assert db.supply_fault_count_recent("pub-wallet-1", "invoke_failure", 600) == 0  # cleared after slash


def test_lumen_outage_on_invoke_is_502_not_403(tmp_path, monkeypatch):
    """A LUMEN outage (HTTP 403/5xx from the oracle, transport failure, …) must
    surface as 502 to the consumer, not 403. 403 is a policy deny — "this caller
    is forbidden" — and an oracle the hub cannot consult is a hub dependency
    failure, the same class as a provider 5xx."""
    monkeypatch.setenv("AIMARKET_PUBLISH_TOKEN", PUBLISH_TOKEN)
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG", "0")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    monkeypatch.delenv("AIMARKET_SANDBOX_STUB_INVOKE", raising=False)

    import aimarket_hub.api as api_mod
    monkeypatch.setattr(api_mod.httpx, "AsyncClient", _FailingProviderClient)

    config = HubConfig()
    config.db_path = str(tmp_path / "lumen403.db")
    config.signing_key_path = str(tmp_path / "lumen403_key")
    db = HubDatabase(config.db_path)
    app = create_app(config=config, db=db, signer=Signer(config.signing_key_path))
    app.state.supply_security.lumen = _Lumen(_outage("http_403"))
    with TestClient(app) as client:
        client.post("/ai-market/v2/supply/stake",
                    json={"publisher_id": "pub-wallet-1", "amount_usd": 20.0, "tx_hash": "0xabc"},
                    headers=PUBLISH_HEADERS)
        client.post("/ai-market/v2/supply/register", json=MANIFEST, headers=PUBLISH_HEADERS)
        r = client.post("/ai-market/v2/invoke", json={
            "product_id": "sec-demo", "capability_id": "secure.greet@v1",
            "source_hub": "local", "input": {"name": "x"},
        })
        assert r.status_code == 502, r.text
        assert r.status_code != 403
        detail = str(r.json().get("detail") or "")
        assert "trust oracle unavailable" in detail
        # Provider was never reached — this is not an invoke_failure slash.
        assert not db.supply_slash_events_recent("pub-wallet-1")


# ── FINDING #6: the production stake requirement must not be bypassable ───────────


_STAKE_PAYER = "0x" + "Ab" * 20


def _stub_stake_deposit(monkeypatch, *, verified=True, sender=_STAKE_PAYER):
    """Put the stake path on the production rails without exercising PAYAUTH-003.

    A production stake credit needs a verified deposit AND a signature proving
    control of the paying wallet. These tests are about the stake ladder itself —
    bypass, replay, dev-credit laundering, the gate — so recovery is stubbed to
    always succeed and the 39 call sites stay free of signature plumbing. The
    proof-of-control behaviour has its own tests in test_supply_stake_prod.py
    (missing/forged signature, unattributable transfer) and test_payer_proof.py.
    """
    monkeypatch.setattr(
        "aimarket_hub.supply_security._verify_stake_deposit",
        lambda tx, amt: (verified, sender if verified else ""),
    )
    monkeypatch.setattr(
        "aimarket_hub.supply_security._recover_stake_payer",
        lambda *, payer, tx_hash, chain, amount_usd, signature: payer,
    )


def _prod_sec(tmp_path, monkeypatch, *, min_stake=25.0, verified=True):
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    monkeypatch.setenv("AIFACTORY_PROD", "1")
    _stub_stake_deposit(monkeypatch, verified=verified)
    db = HubDatabase(db_path=str(tmp_path / "prod.db"))
    sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
    sec.policy.min_stake_usd = min_stake
    sec.policy.relaxed = False
    sec.lumen = _Lumen(_healthy(0.8))
    return sec, db


class TestProductionStakeCannotBeBypassed:
    """Every production stake credit must be a verified, single-use on-chain deposit.

    The verification+replay block used to be guarded by ``amount_usd >= min_stake_usd``, so
    a publisher could credit itself sub-threshold amounts indefinitely — unverified, undeduped
    — and walk past the publish gate on the accumulated total.
    """

    def test_sub_threshold_deposit_still_requires_a_tx_hash(self, tmp_path, monkeypatch):
        sec, db = _prod_sec(tmp_path, monkeypatch)
        with pytest.raises(ValueError, match="tx_hash required"):
            sec.stake("pub-a", 9.99)  # $9.99 against a $25 minimum — the old bypass
        assert db.supply_stake_get("pub-a") == 0.0

    def test_sub_threshold_deposits_cannot_accumulate_past_the_publish_gate(self, tmp_path, monkeypatch):
        sec, db = _prod_sec(tmp_path, monkeypatch)
        for _ in range(3):
            with pytest.raises(ValueError):
                sec.stake("pub-wallet-1", 9.99)
        assert db.supply_stake_get("pub-wallet-1") == 0.0
        with pytest.raises(ValueError, match="minimum stake"):
            sec.validate_publish({**MANIFEST, "provider_pubkey": "dGVzdA=="})

    def test_sub_threshold_deposit_is_verified_on_chain(self, tmp_path, monkeypatch):
        """An unverifiable small deposit is rejected — size never made a tx trustworthy."""
        sec, db = _prod_sec(tmp_path, monkeypatch, verified=False)
        with pytest.raises(ValueError, match="not verified on-chain"):
            sec.stake("pub-a", 1.0, tx_hash="0xfabricated")
        assert db.supply_stake_get("pub-a") == 0.0

    def test_sub_threshold_tx_hash_is_single_use(self, tmp_path, monkeypatch):
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec.stake("pub-a", 1.0, tx_hash="0xsmall")
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-b", 1.0, tx_hash="0xsmall")
        assert db.supply_stake_get("pub-b") == 0.0

    def test_verified_small_deposits_do_accumulate(self, tmp_path, monkeypatch):
        """The gate is verification, not size: three verified $9.99 deposits clear a $25 min."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        for i in range(3):
            sec.stake("pub-wallet-1", 9.99, tx_hash=f"0xdeposit{i}")
        assert db.supply_stake_get("pub-wallet-1") == pytest.approx(29.97)
        pub_id, _ = sec.validate_publish({**MANIFEST, "provider_pubkey": "dGVzdA=="})
        assert pub_id == "pub-wallet-1"

    def test_dev_credited_balance_cannot_satisfy_a_production_gate(self, tmp_path, monkeypatch):
        """The cumulative angle: stake credited while the hub was NOT in production is
        unverified money. Flipping AIFACTORY_PROD on must not turn it into collateral."""
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
        monkeypatch.delenv("AIFACTORY_PROD", raising=False)
        db = HubDatabase(db_path=str(tmp_path / "flip.db"))
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.policy.min_stake_usd = 25.0
        sec.lumen = _Lumen(_healthy(0.8))
        sec.stake("pub-wallet-1", 30.0)  # free dev credit
        assert db.supply_stake_get("pub-wallet-1") == 30.0
        # In dev the balance is usable (nothing is verified there anyway).
        assert sec.validate_publish({**MANIFEST, "provider_pubkey": "dGVzdA=="})[0] == "pub-wallet-1"

        monkeypatch.setenv("AIFACTORY_PROD", "1")
        with pytest.raises(ValueError, match="unverified credits"):
            sec.validate_publish({**MANIFEST, "provider_pubkey": "dGVzdA=="})
        # …and a verified top-up must not launder the unverified remainder either.
        _stub_stake_deposit(monkeypatch)
        with pytest.raises(ValueError, match="unverified dev credits"):
            sec.stake("pub-wallet-1", 25.0, tx_hash="0xlaunder")

    def test_dev_credited_balance_cannot_back_a_production_self_bond(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
        monkeypatch.delenv("AIFACTORY_PROD", raising=False)
        db = HubDatabase(db_path=str(tmp_path / "bond.db"))
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.lumen = _Lumen(_healthy(0.8))
        sec.stake("agent-1", 10.0)
        assert sec.register_self_bond("agent-1", "0xabc", 1.0, 5.0)["status"] == "bonded"
        monkeypatch.setenv("AIFACTORY_PROD", "1")
        with pytest.raises(ValueError, match="unverified credits"):
            sec.register_self_bond("agent-1", "0xabc", 1.0, 5.0)


# ── FINDING #7: LUMEN degradation must fail CLOSED ────────────────────────────────


def _sec_with_cap(tmp_path, monkeypatch, publisher="pub-a"):
    """A SupplySecurity whose publisher owns one local capability row (the durable store
    supply_set_publisher_trust writes into)."""
    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    db = HubDatabase(db_path=str(tmp_path / "trust.db"))
    cap = validate_manifest({**MANIFEST, "provider_pubkey": "dGVzdA==", "publisher_id": publisher})
    cap.publisher_id = publisher
    db.upsert_capability(cap)
    sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
    sec.policy.relaxed = False
    sec.lumen = _Lumen(_healthy(0.8))
    return sec, db, cap


def _stored_trust(db, publisher="pub-a") -> float:
    caps = [c for c in db.list_capabilities(source_hub="local") if c.publisher_id == publisher]
    assert caps, "expected a local capability row for the publisher"
    return caps[0].trust_score


class TestLumenDegradationFailsClosed:
    def test_outage_never_overwrites_a_stored_score(self, tmp_path, monkeypatch):
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        assert sec.refresh_publisher_trust("pub-a") == 0.8
        sec.lumen = _Lumen(_outage("http_502"))
        assert sec.refresh_publisher_trust("pub-a") == 0.8     # retained, not re-derived
        assert _stored_trust(db) == 0.8                        # and not overwritten

    def test_outage_survives_a_restart_through_the_capability_row(self, tmp_path, monkeypatch):
        """The retained score must be durable, not just process-local: a hub restarted in
        the middle of an outage must not fall back to a passing default."""
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        sec.lumen = _Lumen(_healthy(0.62))
        sec.refresh_publisher_trust("pub-a")
        restarted = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        restarted.lumen = _Lumen(_outage("connect timeout"))
        assert restarted.refresh_publisher_trust("pub-a") == pytest.approx(0.62)

    def test_outage_for_an_unknown_publisher_is_untrusted_not_0_5(self, tmp_path, monkeypatch):
        """0.5 cleared BOTH gates, so an outage used to grant every publisher invoke rights."""
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        sec.lumen = _Lumen(_outage("connection refused"))
        score = sec.refresh_publisher_trust("never-scored")
        assert score == 0.0
        assert score < sec.policy.min_trust_invoke and score < sec.policy.min_trust_discover

    def test_outage_at_publish_makes_invoke_unavailable_not_forbidden(self, tmp_path, monkeypatch):
        """after_publish during an outage must not persist 0.0 as a verdict: that
        became last-known and check_invoke_trust mapped it to HTTP 403."""
        monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
        db = HubDatabase(db_path=str(tmp_path / "unscored.db"))
        cap = validate_manifest({**MANIFEST, "provider_pubkey": "dGVzdA==", "publisher_id": "pub-a"})
        cap.publisher_id = "pub-a"
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.policy.relaxed = False
        sec.lumen = _Lumen(_outage("http_403"))
        sec.after_publish(cap, "pub-a")
        assert cap.trust_score == _TRUST_UNSCORED
        with pytest.raises(TrustOracleUnavailable, match="trust oracle unavailable"):
            sec.check_invoke_trust(cap)

    def test_slash_trust_effect_survives_an_outage(self, tmp_path, monkeypatch):
        """slash() refreshes right after writing its -0.5 trust edge. With LUMEN down that
        edge reaches nothing, so retaining the last score silently ERASED the slash. The
        penalty must be applied locally and persisted instead."""
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        db.supply_stake_add("pub-a", 100.0)
        assert sec.refresh_publisher_trust("pub-a") == 0.8
        sec.lumen = _Lumen(_outage("http_500"))
        out = sec.slash("pub-a", 5.0, "invoke_failure:prod-x/cap-x")
        assert out["slashed_usd"] == 5.0
        assert out["trust_score"] == pytest.approx(0.3)          # 0.8 - 0.5 (the edge weight)
        assert out["trust_score"] < sec.policy.min_trust_invoke  # actually locked out
        assert _stored_trust(db) == pytest.approx(0.3)           # durable, not in-memory only

    def test_slash_does_not_double_penalize_when_lumen_is_healthy(self, tmp_path, monkeypatch):
        """With the oracle up the -0.5 edge is already in the score; no extra local penalty."""
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        db.supply_stake_add("pub-a", 100.0)
        sec.lumen = _Lumen(_healthy(0.44))
        out = sec.slash("pub-a", 5.0, "invoke_failure:prod-x/cap-x")
        assert out["trust_score"] == pytest.approx(0.44)
        assert _stored_trust(db) == pytest.approx(0.44)

    def test_no_signal_bootstraps_a_brand_new_publisher(self, tmp_path, monkeypatch):
        """A graph with nothing to say is not an outage: a first-time publisher must not be
        locked out permanently."""
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch, publisher="pub-a")
        sec.lumen = _Lumen(_no_signal("no_edges"))
        assert sec.refresh_publisher_trust("brand-new") == 0.5

    def test_no_signal_never_resets_an_existing_score_upward(self, tmp_path, monkeypatch):
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        sec.lumen = _Lumen(_healthy(0.10))
        sec.refresh_publisher_trust("pub-a")
        sec.lumen = _Lumen(_no_signal("empty_graph"))
        assert sec.refresh_publisher_trust("pub-a") == pytest.approx(0.10)
        assert _stored_trust(db) == pytest.approx(0.10)

    def test_non_finite_score_is_treated_as_an_outage(self, tmp_path, monkeypatch):
        """A "healthy" verdict carrying NaN must not be clamped into a passing number."""
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        sec.lumen = _Lumen({"score": float("nan"), "degraded": False})
        assert sec.refresh_publisher_trust("never-scored") == 0.0


def _is_unavailable(result: dict, reason: str) -> bool:
    return result["score"] is None and result["unavailable"] is True and result["reason"] == reason


class TestLumenClientContract:
    """The client must never invent a score: an outage and a signal-less graph are
    different answers, and neither of them is 0.5."""

    def _client(self, monkeypatch, responder):
        from aimarket_hub import lumen_client as lc

        class _Resp:
            def __init__(self, status, payload):
                self.status_code = status
                self._payload = payload

            def json(self):
                return self._payload

        class _Client:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def post(self, url, **kwargs):
                status, payload = responder()
                return _Resp(status, payload)

        monkeypatch.setattr(lc.httpx, "Client", _Client)
        return lc.LumenTrustClient("https://oracle.test/family")

    def test_no_edges_is_no_signal_not_an_outage(self):
        from aimarket_hub.lumen_client import LumenTrustClient

        out = LumenTrustClient("https://oracle.test/family").score_entity("p", [])
        assert out["score"] is None and out["degraded"] is True
        assert out["unavailable"] is False and out["reason"] == "no_edges"

    def test_all_zero_weights_is_no_signal(self):
        from aimarket_hub.lumen_client import LumenTrustClient

        out = LumenTrustClient("https://oracle.test/family").score_entity("p", [("a", "p", 0.0)])
        assert out["reason"] == "empty_graph" and out["unavailable"] is False

    def test_http_error_is_unavailable_with_no_score(self, monkeypatch):
        client = self._client(monkeypatch, lambda: (503, {}))
        out = client.score_entity("p", [("a", "p", 0.5)])
        assert out["score"] is None and out["unavailable"] is True and out["reason"] == "http_503"

    def test_malformed_payload_is_unavailable(self, monkeypatch):
        client = self._client(monkeypatch, lambda: (200, {"output": {"scores": []}}))
        assert _is_unavailable(client.score_entity("p", [("a", "p", 0.5)]), "bad_output")

    def test_nan_score_is_unavailable(self, monkeypatch):
        client = self._client(monkeypatch, lambda: (200, {"output": {"scores": [0.1, float("nan")]}}))
        assert _is_unavailable(client.score_entity("p", [("a", "p", 0.5)]), "bad_scores")

    def test_transport_error_is_unavailable(self, monkeypatch):
        def boom():
            raise RuntimeError("dns failure")

        client = self._client(monkeypatch, boom)
        out = client.score_entity("p", [("a", "p", 0.5)])
        assert out["score"] is None and out["unavailable"] is True

    def test_healthy_percentile(self, monkeypatch):
        client = self._client(monkeypatch, lambda: (200, {"output": {"scores": [0.1, 0.9]}}))
        out = client.score_entity("p", [("a", "p", 0.5)])
        assert out["degraded"] is False and 0.0 <= out["score"] <= 1.0

    def test_clamp01_rejects_non_finite(self):
        from aimarket_hub.lumen_client import clamp01

        assert clamp01(1.7) == 1.0 and clamp01(-2) == 0.0
        for bad in (float("nan"), float("inf"), None, "0.5"):
            with pytest.raises(ValueError):
                clamp01(bad)


class TestTrustGraphBound:
    """MINOR: the graph fed to LUMEN was silently cut at 1000 edges."""

    def test_truncation_is_bounded_and_logged(self, tmp_path, monkeypatch, caplog):
        sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
        sec.policy.max_trust_graph_edges = 2
        db.supply_stake_add("pub-a", 100.0)
        for i in range(5):
            db.trust_add_edge(f"c{i}", "pub-a", 0.15, "invoke_success")
        lumen = _Lumen(_healthy(0.7))
        sec.lumen = lumen
        with caplog.at_level(logging.WARNING, logger="aimarket_hub.supply_security"):
            sec.refresh_publisher_trust("pub-a")
        assert "trust graph truncated" in caplog.text
        _entity, edges = lumen.calls[-1]
        assert len(edges) == 3                       # 2 graph edges + the stake anchor
        assert edges[0][0] == "hub:local"            # the anchor is never the one cut

    def test_non_positive_bound_falls_back_to_the_default(self, monkeypatch):
        monkeypatch.setenv("AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES", "0")
        assert SupplySecurityPolicy.from_config(HubConfig()).max_trust_graph_edges == 1000
        monkeypatch.setenv("AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES", "notanumber")
        assert SupplySecurityPolicy.from_config(HubConfig()).max_trust_graph_edges == 1000
        monkeypatch.setenv("AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES", "50")
        assert SupplySecurityPolicy.from_config(HubConfig()).max_trust_graph_edges == 50


def test_empty_invoke_url_is_not_deduped(tmp_path, monkeypatch):
    """MINOR: dedup looked "" up and matched the first OTHER local row that also had no
    invoke_url — every factory-seeded product — so a non-invoke capability was rejected with
    "invoke_url already registered to another product" by an unrelated product's empty URL."""
    from aimarket_hub.models import Capability

    monkeypatch.setenv("AIMARKET_ALLOW_LOCAL_PUBLISH", "1")
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "1")
    db = HubDatabase(db_path=str(tmp_path / "dedup.db"))
    # A factory-style local capability: no invoke_url at all.
    db.upsert_capability(Capability(
        capability_id="seeded.thing@v1", product_id="seeded-product", name="seeded",
        description="factory product", source_hub="local", publisher_id="pub-a",
    ))
    sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
    sec.lumen = _Lumen(_healthy(0.8))
    other = {"product_id": "other-product", "capability_id": "other.thing@v1",
             "publisher_id": "pub-b", "provider_pubkey": "dGVzdA=="}
    assert sec.validate_publish(other)[0] == "pub-b"

    # A genuinely duplicated invoke_url is still rejected.
    db.upsert_capability(validate_manifest({**MANIFEST, "publisher_id": "pub-a"}))
    with pytest.raises(ValueError, match="already registered"):
        sec.validate_publish({**MANIFEST, "product_id": "third-product",
                              "publisher_id": "pub-c", "provider_pubkey": "dGVzdA=="})


# ── Adversarial review of the #6/#7 remediation ───────────────────────────────────


class TestStakeDepositIsSingleUseForever:
    """The replay guard must outlive the deposit that follows it.

    ``supply_stakes`` holds ONE tx_hash per publisher and every credit overwrites it, so
    checking ``supply_stake_tx_exists`` alone forgot a deposit as soon as the same publisher
    staked again — the first hash became claimable by anyone.
    """

    def test_a_consumed_deposit_cannot_be_replayed_after_a_later_deposit(self, tmp_path, monkeypatch):
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec.stake("pub-a", 10.0, tx_hash="0xAAA")
        sec.stake("pub-a", 10.0, tx_hash="0xBBB")   # overwrites the row's tx_hash with 0xBBB
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-evil", 10.0, tx_hash="0xAAA")
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-a", 10.0, tx_hash="0xAAA")   # …not even by the original depositor
        assert db.supply_stake_get("pub-evil") == 0.0
        assert db.supply_stake_get("pub-a") == pytest.approx(20.0)

    def test_a_deposit_is_burned_before_it_is_credited(self, tmp_path, monkeypatch):
        """Order matters: a crash between burn and credit must lose the deposit, never
        duplicate it."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        real_add = db.supply_stake_add

        def boom(publisher_id, amount_usd, tx_hash=""):
            if publisher_id == "pub-a":
                raise RuntimeError("ledger write failed")
            return real_add(publisher_id, amount_usd, tx_hash)

        # Restored by hand, not via monkeypatch.undo(), which would also roll back the
        # production env this test runs in.
        db.supply_stake_add = boom  # type: ignore[method-assign]
        try:
            with pytest.raises(RuntimeError):
                sec.stake("pub-a", 10.0, tx_hash="0xCCC")
        finally:
            db.supply_stake_add = real_add  # type: ignore[method-assign]
        assert db.supply_stake_get("pub-a") == 0.0
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-a", 10.0, tx_hash="0xCCC")

    def test_reserved_publisher_ids_are_not_addressable(self, tmp_path, monkeypatch):
        """The burn row and the dev-credit sentinel live in supply_stakes under reserved
        publisher_ids. Staking to one would overwrite its tx_hash and un-burn the deposit."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec.stake("pub-a", 10.0, tx_hash="0xAAA")
        with pytest.raises(ValueError, match="reserved prefix"):
            sec.stake("tx-consumed:0xAAA", 1.0, tx_hash="0xDDD")
        with pytest.raises(ValueError, match="reserved prefix"):
            sec.stake("unverified-dev-credit:pub-a", 1.0, tx_hash="0xDDD")
        with pytest.raises(ValueError, match="reserved prefix"):
            sec.validate_publish({**MANIFEST, "publisher_id": "tx-consumed:0xAAA",
                                  "provider_pubkey": "dGVzdA=="})
        with pytest.raises(ValueError, match="reserved prefix"):
            sec.register_self_bond("tx-consumed:0xAAA", "0xabc", 1.0, 5.0)
        # …and 0xAAA is still burned.
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-b", 10.0, tx_hash="0xAAA")

    def test_a_tx_hash_cannot_impersonate_a_ledger_marker(self, tmp_path, monkeypatch):
        """The sentinel and the burn key share the tx_hash column. A caller-supplied hash
        shaped like another publisher's sentinel would lock that publisher out of production
        (its presence is what _require_verified_stake refuses on)."""
        sec, db = _prod_sec(tmp_path, monkeypatch)   # verifier stubbed to accept anything
        with pytest.raises(ValueError, match="reserved stake-ledger prefix"):
            sec.stake("pub-evil", 1.0, tx_hash="unverified-dev-credit:pub-victim")
        with pytest.raises(ValueError, match="reserved stake-ledger prefix"):
            sec.stake("pub-evil", 1.0, tx_hash="tx-consumed:0xAAA")
        sec.stake("pub-victim", 30.0, tx_hash="0xREAL")
        sec._require_verified_stake("pub-victim", "publish")   # not poisoned

    def test_a_zero_balance_clears_the_unverified_dev_marker(self, tmp_path, monkeypatch):
        """The refusal message tells the operator to write the balance off and re-stake. That
        has to actually work: with no recovery route the sentinel locks the publisher out of
        production permanently (nothing else ever clears it)."""
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
        monkeypatch.delenv("AIFACTORY_PROD", raising=False)
        db = HubDatabase(db_path=str(tmp_path / "recover.db"))
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.policy.relaxed = False
        sec.policy.min_stake_usd = 25.0
        sec.lumen = _Lumen(_healthy(0.8))
        sec.stake("pub-a", 30.0)                       # unverified dev credit
        monkeypatch.setenv("AIFACTORY_PROD", "1")
        _stub_stake_deposit(monkeypatch)
        with pytest.raises(ValueError, match="unverified dev credits"):
            sec.stake("pub-a", 30.0, tx_hash="0xGOOD")   # still refused while the money stands
        db.supply_stake_slash("pub-a", 30.0)             # write the unverified balance off
        assert db.supply_stake_get("pub-a") == 0.0
        assert sec.stake("pub-a", 30.0, tx_hash="0xGOOD")["stake_usd"] == pytest.approx(30.0)
        sec._require_verified_stake("pub-a", "publish")  # gate now passes: balance is verified
        # The recovered balance is real collateral again.
        assert sec.validate_publish({**MANIFEST, "provider_pubkey": "dGVzdA==",
                                     "publisher_id": "pub-a"})[0] == "pub-a"

    def test_non_finite_stake_amount_is_rejected(self, tmp_path, monkeypatch):
        """``inf <= 0`` and ``nan <= 0`` are both False, and a non-finite BALANCE then passes
        ``stake < min_stake_usd`` — the stake gate evaluates to "satisfied" on money that
        does not exist."""
        monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "1")
        db = HubDatabase(db_path=str(tmp_path / "inf.db"))
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.lumen = _Lumen(_healthy(0.8))
        for bad in (float("inf"), float("nan"), float("-inf")):
            with pytest.raises(ValueError, match="finite|positive"):
                sec.stake("pub-a", bad)
        with pytest.raises(ValueError, match="must be a number"):
            sec.stake("pub-a", "lots")
        with pytest.raises(ValueError, match="publisher_id is required"):
            sec.stake("   ", 10.0)
        assert db.supply_stake_get("pub-a") == 0.0


class TestStakeBurnIsAtomicUnderConcurrency:
    """The single-use burn must be a CLAIM, not a read-then-write.

    The burn used to go through ``supply_stake_add`` (SELECT, then UPDATE when the row is
    already there), so two requests that both passed ``supply_stake_tx_exists`` before
    either burned BOTH succeeded — the loser quietly updated the winner's burn row — and
    one on-chain deposit was credited to two publishers.
    """

    def test_the_same_hash_cannot_be_burned_twice(self, tmp_path, monkeypatch):
        """The narrow claim, with no threads in the way: a second burn of a live hash is a
        replay and must be refused, not absorbed by an UPDATE."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec._consume_stake_tx("0xONCE")
        with pytest.raises(ValueError, match="already recorded"):
            sec._consume_stake_tx("0xONCE")

    def test_a_second_connection_cannot_re_burn_a_hash(self, tmp_path, monkeypatch):
        """Multi-worker shape: the claim is enforced by the DATABASE, so it holds across
        connections that never see each other's caches."""
        sec_a, db_a = _prod_sec(tmp_path, monkeypatch)
        db_b = HubDatabase(db_path=str(tmp_path / "prod.db"))   # same file, own connection
        sec_b = SupplySecurity(db_b, HubConfig(), signer=Signer(tmp_path / "k2"))
        sec_b.policy.relaxed = False
        sec_b.lumen = _Lumen(_healthy(0.8))
        sec_a._consume_stake_tx("0xSHARED")
        with pytest.raises(ValueError, match="already recorded"):
            sec_b._consume_stake_tx("0xSHARED")

    def test_concurrent_stakes_of_one_deposit_credit_it_exactly_once(self, tmp_path, monkeypatch):
        """Real threads, one deposit, one hub process (the FastAPI thread-pool shape).

        Every racer is held inside on-chain verification — the exact gap between the
        replay check and the burn — until all of them are past the check, then released
        one at a time. Under the old read-then-write burn each straggler found the
        winner's row and UPDATEd it, so N publishers were funded by one deposit.
        """
        sec, db = _prod_sec(tmp_path, monkeypatch)
        outcome = _race_one_deposit(sec, monkeypatch, racers=4, tx_hash="0xRACE")

        assert outcome["credited"] == ["pub-0"], outcome
        assert len(outcome["rejected"]) == 3
        assert all("already recorded" in msg for msg in outcome["rejected"]), outcome
        total = sum(db.supply_stake_get(f"pub-{i}") for i in range(4))
        assert total == pytest.approx(10.0), "one deposit must credit one balance"

    def test_concurrent_stakes_across_connections_credit_it_exactly_once(self, tmp_path, monkeypatch):
        """Same race with a SEPARATE HubDatabase (own SQLite connection) per racer — the
        multi-worker deployment, where an in-process lock would prove nothing."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        peers = []
        for i in range(3):
            peer_db = HubDatabase(db_path=str(tmp_path / "prod.db"))
            peer = SupplySecurity(peer_db, HubConfig(), signer=Signer(tmp_path / f"k{i}"))
            peer.policy.relaxed = False
            peer.lumen = _Lumen(_healthy(0.8))
            peers.append(peer)
        outcome = _race_one_deposit(sec, monkeypatch, racers=4, tx_hash="0xFLEET", peers=peers)

        assert outcome["credited"] == ["pub-0"], outcome
        assert len(outcome["rejected"]) == 3
        assert all("already recorded" in msg for msg in outcome["rejected"]), outcome
        total = sum(db.supply_stake_get(f"pub-{i}") for i in range(4))
        assert total == pytest.approx(10.0)

    def test_an_unclaimable_burn_refuses_the_credit(self, tmp_path, monkeypatch):
        """Fail closed: a burn that cannot be evaluated (no reachable DB backend) must
        reject the deposit rather than credit a hash nothing burned."""
        sec, db = _prod_sec(tmp_path, monkeypatch)

        class _Detached:
            """HubDatabase-shaped, but with nothing to run the claim against."""
            _backend = None
            _conn = None

            def supply_stake_tx_exists(self, tx_hash: str) -> bool:
                return False

            def supply_stake_get(self, publisher_id: str) -> float:
                return 0.0

        sec.db = _Detached()
        with pytest.raises(ValueError, match="cannot be claimed atomically"):
            sec.stake("pub-a", 10.0, tx_hash="0xNOBACKEND")
        assert db.supply_stake_get("pub-a") == 0.0


# One real transaction, written two ways. eth_getTransactionByHash resolves both, so the
# on-chain verifier says "verified" for both.
_TX_LOWER = "0x" + "ab" * 32
_TX_UPPER = "0x" + "AB" * 32


class TestTheBurnKeyIsTheCanonicalDeposit:
    """An atomic claim on a non-canonical key is not single-use.

    The claim decides one winner per KEY, so it is only a single-use guard if two spellings
    of one deposit produce one key. Keyed on the caller's string, ``0xAB…`` and ``0xab…``
    were two keys: both verified on-chain, both burned, and one $10 deposit credited two
    publishers $10 each. The channel ledger canonicalises for exactly this reason
    (``channels._normalize_tx_hash``); the stake ledger now shares that definition.
    """

    def test_a_case_flipped_hash_is_the_same_deposit(self, tmp_path, monkeypatch):
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec.stake("pub-a", 10.0, tx_hash=_TX_LOWER)
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-b", 10.0, tx_hash=_TX_UPPER)
        assert db.supply_stake_get("pub-b") == 0.0
        assert db.supply_stake_get("pub-a") == pytest.approx(10.0)

    def test_the_same_publisher_cannot_re_credit_its_own_deposit(self, tmp_path, monkeypatch):
        """The stake gate reads a TOTAL, so re-crediting one's own deposit under a new
        capitalisation walks past the publish minimum on money deposited once."""
        sec, db = _prod_sec(tmp_path, monkeypatch, min_stake=15.0)
        sec.stake("pub-a", 10.0, tx_hash=_TX_LOWER)
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-a", 10.0, tx_hash=_TX_UPPER)
        assert db.supply_stake_get("pub-a") == pytest.approx(10.0)

    def test_a_deposit_burned_verbatim_by_an_older_build_stays_burned(self, tmp_path, monkeypatch):
        """Back-compat with rows already on disk: canonicalising the key turns an
        old verbatim burn (`tx-consumed:0xAB…`) into a free key, so the replay would win
        the claim unless the lookup also folds case."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        db.supply_stake_add(f"tx-consumed:{_TX_UPPER}", 0.0, _TX_UPPER)   # pre-fix burn row
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-b", 10.0, tx_hash=_TX_LOWER)
        assert db.supply_stake_get("pub-b") == 0.0

    def test_a_deposit_credited_verbatim_by_an_older_build_stays_spent(self, tmp_path, monkeypatch):
        """Same for the credit row an older build wrote: its tx_hash is the only record
        that the deposit was consumed."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        db.supply_stake_add("pub-old", 10.0, _TX_UPPER)
        with pytest.raises(ValueError, match="already recorded"):
            sec.stake("pub-b", 10.0, tx_hash=_TX_LOWER)
        assert db.supply_stake_get("pub-b") == 0.0

    def test_case_variants_racing_credit_the_deposit_exactly_once(self, tmp_path, monkeypatch):
        """The two defects together: concurrent racers each using a different spelling.
        Atomicity alone does not save this — every racer would win its own key."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        outcome = _race_one_deposit(
            sec, monkeypatch, racers=4, tx_hash=_TX_LOWER,
            tx_hash_for=lambda i: _TX_LOWER if i % 2 == 0 else _TX_UPPER,
        )
        assert len(outcome["credited"]) == 1, outcome
        assert len(outcome["rejected"]) == 3
        assert all("already recorded" in msg for msg in outcome["rejected"]), outcome
        total = sum(db.supply_stake_get(f"pub-{i}") for i in range(4))
        assert total == pytest.approx(10.0), "one deposit must credit one balance"

    def test_a_base58_signature_keeps_its_case(self, tmp_path, monkeypatch):
        """Solana signatures are base58: case is part of the identifier, so folding it
        would reject a genuinely different deposit."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec.stake("pub-a", 10.0, tx_hash="5Kd" + "Xy" * 30)
        sec.stake("pub-b", 10.0, tx_hash="5kD" + "xY" * 30)
        assert db.supply_stake_get("pub-a") == pytest.approx(10.0)
        assert db.supply_stake_get("pub-b") == pytest.approx(10.0)

    def test_the_credit_row_records_the_canonical_hash(self, tmp_path, monkeypatch):
        """What the ledger stores has to be what a later replay check looks up."""
        sec, db = _prod_sec(tmp_path, monkeypatch)
        sec.stake("pub-a", 10.0, tx_hash=_TX_UPPER)
        assert db.supply_stake_tx_exists(_TX_LOWER)


def _race_one_deposit(sec, monkeypatch, *, racers: int, tx_hash: str, peers=None, tx_hash_for=None):
    """Run ``racers`` genuine threads staking the SAME tx_hash and report who got credited.

    The stagger is inside the (stubbed) on-chain verifier, i.e. after every racer has passed
    the replay check and before any of them burns. That is the window the old code lost, and
    releasing the racers into it one at a time makes the double-credit deterministic rather
    than a coin flip — without weakening the concurrency: all four threads are live and
    inside ``stake()`` at the same time.
    """
    barrier = threading.Barrier(racers, timeout=30)
    # One stake() per racer: the caller's own, plus one per peer hub instance it supplied.
    stake_fns = [sec.stake] + [p.stake for p in (peers or [])]
    delays = {f"racer-{i}": 0.05 * i for i in range(racers)}

    def verifier(tx: str, amount_usd: float) -> tuple[bool, str]:
        # The barrier + staggered sleep hold every racer inside stake() at once, so the
        # dedup burn is genuinely contended rather than accidentally serialised.
        barrier.wait()
        time.sleep(delays[threading.current_thread().name])
        return True, _STAKE_PAYER

    monkeypatch.setattr("aimarket_hub.supply_security._verify_stake_deposit", verifier)
    monkeypatch.setattr(
        "aimarket_hub.supply_security._recover_stake_payer",
        lambda *, payer, tx_hash, chain, amount_usd, signature: payer,
    )

    credited: list[str] = []
    rejected: list[str] = []
    lock = threading.Lock()

    def run(i: int) -> None:
        fn = stake_fns[i] if i < len(stake_fns) else sec.stake
        try:
            fn(f"pub-{i}", 10.0, tx_hash_for(i) if tx_hash_for else tx_hash)
        except ValueError as exc:
            with lock:
                rejected.append(str(exc))
        else:
            with lock:
                credited.append(f"pub-{i}")

    threads = [threading.Thread(target=run, args=(i,), name=f"racer-{i}") for i in range(racers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a racer deadlocked"
    return {"credited": sorted(credited), "rejected": rejected}


def test_a_concurrent_healthy_refresh_cannot_cancel_the_slash_penalty(tmp_path, monkeypatch):
    """One SupplySecurity instance serves every worker thread. Deciding "was LUMEN up?" from a
    single shared attribute meant a concurrent healthy refresh of ANOTHER publisher, landing
    between slash()'s own refresh and its read of that attribute, told slash the oracle was
    reachable — so the local penalty was skipped and the outage erased the slash again.

    The interleaving is forced deterministically: the concurrent refresh is driven from inside
    the degraded path's capability-row lookup, which is exactly where the window sits."""
    sec, db, _cap = _sec_with_cap(tmp_path, monkeypatch)
    other = validate_manifest({**MANIFEST, "product_id": "p2", "capability_id": "c2@v1",
                               "invoke_url": "http://127.0.0.1:9/i", "publisher_id": "pub-b"})
    other.publisher_id = "pub-b"
    db.upsert_capability(other)

    assert sec.refresh_publisher_trust("pub-a") == 0.8
    db.supply_stake_add("pub-a", 100.0)

    class _PerPublisherLumen(_Lumen):
        def score_entity(self, entity_id, edges):
            self.calls.append((entity_id, list(edges)))
            return _outage("http_503") if entity_id == "pub-a" else _healthy(0.9)

    sec.lumen = _PerPublisherLumen()
    sec._trust_cache.clear()          # cold cache → the degraded path reads capability rows
    real_list, fired = db.list_capabilities, []

    def concurrent(*args, **kwargs):
        if not fired:
            fired.append(True)
            sec.refresh_publisher_trust("pub-b")   # the other request, oracle healthy for it
        return real_list(*args, **kwargs)

    db.list_capabilities = concurrent  # type: ignore[method-assign]
    try:
        out = sec.slash("pub-a", 5.0, "invoke_failure:prod-x/cap-x")
    finally:
        db.list_capabilities = real_list  # type: ignore[method-assign]

    assert fired, "the interleaving under test never happened"
    assert out["trust_score"] == pytest.approx(0.3)          # 0.8 - 0.5, applied locally
    assert out["trust_score"] < sec.policy.min_trust_invoke
    assert _stored_trust(db) == pytest.approx(0.3)


def test_non_finite_stored_trust_never_passes_a_trust_gate(tmp_path, monkeypatch):
    """`nan < min_trust` is False, so an unusable stored score would read as "above the
    gate" — the gate must refuse what it cannot compare."""
    from aimarket_hub.models import Capability

    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    db = HubDatabase(db_path=str(tmp_path / "nan.db"))
    sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
    sec.policy.relaxed = False
    cap = Capability(capability_id="x@v1", product_id="x", name="x", description="x",
                     source_hub="local", publisher_id="pub-a",
                     invoke_url="http://127.0.0.1:1/i", trust_score=float("nan"))
    with pytest.raises(ValueError, match="below minimum"):
        sec.check_invoke_trust(cap)
    assert sec.filter_for_discover([cap]) == []


def test_non_finite_policy_thresholds_fall_back_to_the_documented_default(monkeypatch):
    """A NaN threshold disables the gate it configures; an 'inf' edge bound used to raise
    OverflowError out of hub construction. Garbage must degrade to the default, visibly."""
    monkeypatch.setenv("AIMARKET_SUPPLY_SECURITY_RELAXED", "0")
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "nan")
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_TRUST_INVOKE", "inf")
    monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_FAILURE_WINDOW_S", "inf")
    monkeypatch.setenv("AIMARKET_SUPPLY_VERIFIED_FAIL_WINDOW_S", "nan")
    monkeypatch.setenv("AIMARKET_SUPPLY_TRUST_GRAPH_MAX_EDGES", "inf")
    monkeypatch.setenv("AIMARKET_SUPPLY_SLASH_COOLDOWN_S", "not-a-number")
    policy = SupplySecurityPolicy.from_config(HubConfig())
    assert policy.min_stake_usd == 10.0            # dev default (AIFACTORY_PROD unset here)
    assert policy.min_trust_invoke == 0.35
    assert policy.slash_failure_window_s == 600.0
    assert policy.verified_fail_window_s == 86400.0
    assert policy.max_trust_graph_edges == 1000
    assert policy.slash_cooldown_s == 3600.0
    # A real value is still honoured.
    monkeypatch.setenv("AIMARKET_SUPPLY_MIN_STAKE_USD", "42.5")
    assert SupplySecurityPolicy.from_config(HubConfig()).min_stake_usd == 42.5


# --- 2026-09 re-audit: a publish must not be able to take over someone else's listing ---

class TestALocalListingCannotBeHijacked:
    """`validate_publish` checked the publisher's credential, stake, rate, product allowlist
    and invoke_url dedup — but never who already OWNS (product_id, capability_id, 'local').
    `after_publish` then calls `db.upsert_capability`, an INSERT OR REPLACE against
    UNIQUE(capability_id, product_id, source_hub).

    So any actor holding one publisher credential (an AIMARKET_PUBLISHER_TOKENS entry, or a
    self-serve credits account key, which may publish as its own acct_ id) could re-publish an
    existing capability under its own invoke_url, price, publisher_id and provider_pubkey.
    Afterwards every paid invoke of that capability sends the buyer's input to the attacker's
    endpoint, verifies the response against the attacker's key, and pays the attacker the
    publisher share. The invoke_url dedup does not catch it: it only fires when the
    product_id DIFFERS, and a takeover reuses the same product_id.
    """

    @staticmethod
    def _sec(db, tmp_path):
        """A SupplySecurity whose unrelated gates are satisfied, so the OWNERSHIP check is
        the only thing these tests can be measuring."""
        sec = SupplySecurity(db, HubConfig(), signer=Signer(tmp_path / "k"))
        sec.policy.min_stake_usd = 0.0
        return sec

    @staticmethod
    def _own(db, publisher_id: str) -> None:
        from aimarket_hub.models import Capability

        db.upsert_capability(Capability(
            capability_id=MANIFEST["capability_id"],
            product_id=MANIFEST["product_id"],
            name="the original",
            price_per_call_usd=0.02,
            source_hub="local",
            invoke_url="http://127.0.0.1:3457/invoke",
            publisher_id=publisher_id,
        ))

    def test_a_different_publisher_cannot_replace_the_row(self, tmp_path):
        db = HubDatabase(tmp_path / "hijack.db")
        self._own(db, "pub-wallet-1")
        sec = self._sec(db, tmp_path)
        with pytest.raises(ValueError, match="already published|another publisher|owner"):
            sec.validate_publish({
                **MANIFEST,
                "publisher_id": "pub-attacker",
                "invoke_url": "https://attacker.example/invoke",
                "price_per_call_usd": 0.99,
            })

    def test_the_owner_may_still_update_its_own_listing(self, tmp_path):
        """The guard must not turn a legitimate re-publish into an outage."""
        db = HubDatabase(tmp_path / "update.db")
        self._own(db, "pub-wallet-1")
        sec = self._sec(db, tmp_path)
        pub_id, _ = sec.validate_publish({**MANIFEST, "price_per_call_usd": 0.05})
        assert pub_id == "pub-wallet-1"

    def test_a_first_publish_of_an_unclaimed_capability_still_works(self, tmp_path):
        db = HubDatabase(tmp_path / "fresh.db")
        sec = self._sec(db, tmp_path)
        pub_id, _ = sec.validate_publish(MANIFEST)
        assert pub_id == "pub-wallet-1"

    def test_a_row_with_no_recorded_owner_can_still_be_claimed(self, tmp_path):
        """Rows predating publisher_id (seeder / factory imports) must stay publishable."""
        db = HubDatabase(tmp_path / "legacy.db")
        self._own(db, "")
        sec = self._sec(db, tmp_path)
        pub_id, _ = sec.validate_publish(MANIFEST)
        assert pub_id == "pub-wallet-1"

    def test_a_peer_row_with_the_same_ids_is_not_treated_as_the_owner(self, tmp_path):
        """Only the LOCAL row is the thing being replaced; a peer's listing is not."""
        from aimarket_hub.models import Capability

        db = HubDatabase(tmp_path / "peer.db")
        db.upsert_capability(Capability(
            capability_id=MANIFEST["capability_id"], product_id=MANIFEST["product_id"],
            name="a peer's", source_hub="https://peer.example", publisher_id="pub-somebody",
        ))
        sec = self._sec(db, tmp_path)
        pub_id, _ = sec.validate_publish(MANIFEST)
        assert pub_id == "pub-wallet-1"
