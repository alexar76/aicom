"""Federated slash transport (O-4): serve endpoints + crawler pull with issuer binding."""

import asyncio
import tempfile
from pathlib import Path

import pytest
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.slash_sync import ProofOfMisbehavior, SlashRegistry
from fastapi.testclient import TestClient


def _pom(
    consumer: Signer,
    *,
    dispute_id: str = "d1",
    provider_hub: str = "agent-evil",
    canonical: str | None = None,
) -> ProofOfMisbehavior:
    """A PoM that BINDS to the slash it justifies (see slash_sync._evidence_tier).

    The previous default signed the free-form string "dispute|agent-evil|x", i.e. a proof
    of nothing in particular — which the tier rule now (correctly) treats as weak.
    """
    canonical = canonical if canonical is not None else (
        f"dispute_id:{dispute_id}|invocation_id:inv-1|provider_hub:{provider_hub}"
        f"|consumer_hub:https://consumer.example|reason:undelivered"
        f"|requested_slash_pct:0.5|timestamp:2026-01-01T00:00:00Z"
    )
    return ProofOfMisbehavior(canonical, consumer.public_key_b64, consumer.sign_canonical(canonical))


@pytest.fixture
def app_ctx(monkeypatch):
    monkeypatch.setenv("AIMARKET_SKIP_SEED", "1")
    with tempfile.TemporaryDirectory() as tmp:
        config = HubConfig()
        config.db_path = str(Path(tmp) / "t.db")
        config.signing_key_path = str(Path(tmp) / "k")
        config.hub_url = "https://hub-self.example"
        db = HubDatabase(Path(config.db_path))
        signer = Signer(config.signing_key_path)
        app = create_app(config=config, db=db, signer=signer)
        consumer = Signer(Path(tmp) / "consumer")
        issuer = Signer(Path(tmp) / "issuer")
        with TestClient(app) as c:
            yield c, signer, consumer, issuer


def test_get_slashes_serves_local_log(app_ctx):
    client, signer, consumer, _issuer = app_ctx
    client.app.state.slash_registry.record_local_slash(
        provider_hub="agent-evil", slashed_usd=10.0, dispute_id="d1",
        reason="x", signer=signer, pom=_pom(consumer, dispute_id="d1", provider_hub="agent-evil"),
    )
    resp = client.get("/ai-market/v2/reputation/slashes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["hub_url"] == "https://hub-self.example"
    assert len(body["slashes"]) == 1
    assert body["slashes"][0]["provider_hub"] == "agent-evil"


def test_get_slash_signal_by_provider(app_ctx):
    client, signer, consumer, issuer = app_ctx
    src = SlashRegistry("https://peer.example")
    env = src.record_local_slash(
        provider_hub="agent-evil", slashed_usd=5.0, dispute_id="d2",
        reason="x", signer=issuer, pom=_pom(consumer, dispute_id="d2", provider_hub="agent-evil"),
    )
    client.app.state.slash_registry.ingest_remote(
        [env], verifier=signer, expected_issuer_pubkey=issuer.public_key_b64
    )
    resp = client.get("/ai-market/v2/reputation/slashes/by-provider/agent-evil")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slash_count"] == 1
    assert body["distinct_issuers"] == 1
    assert body["federated_penalty"] > 0


def test_slashes_route_not_shadowed_by_catchall(app_ctx):
    # /reputation/slashes must hit the exact route, not /reputation/{hub_url}.
    client, *_ = app_ctx
    resp = client.get("/ai-market/v2/reputation/slashes")
    assert "slashes" in resp.json()


def test_crawler_pulls_and_binds_issuer(tmp_path, monkeypatch):
    from aimarket_hub import crawler as crawler_mod
    from aimarket_hub.crawler import Crawler

    config = HubConfig()
    config.db_path = str(tmp_path / "c.db")
    config.signing_key_path = str(tmp_path / "ck")
    crawler = Crawler(config=config, slash_registry=SlashRegistry("https://self.example"))

    issuer = Signer(tmp_path / "issuer")
    consumer = Signer(tmp_path / "consumer")
    src = SlashRegistry("https://peer.example")
    env = src.record_local_slash(
        provider_hub="agent-evil", slashed_usd=5.0, dispute_id="d1",
        reason="x", signer=issuer, pom=_pom(consumer, dispute_id="d1", provider_hub="agent-evil"),
    )

    class _Resp:
        status_code = 200

        def json(self):
            return {"slashes": [env]}

    monkeypatch.setattr(crawler_mod, "_url_is_safe", lambda u: True)

    async def fake_get(url):
        return _Resp()

    monkeypatch.setattr(crawler, "_safe_get", fake_get)

    # Correct peer key → ingested.
    assert asyncio.run(crawler._pull_peer_slashes("https://peer.example", issuer.public_key_b64)) == 1
    # Spoofed peer key → rejected by issuer binding.
    crawler.slash_registry = SlashRegistry("https://self.example")
    wrong = Signer(tmp_path / "wrong").public_key_b64
    assert asyncio.run(crawler._pull_peer_slashes("https://peer.example", wrong)) == 0


def test_crawler_weak_tier_gated_on_trust_and_env(tmp_path, monkeypatch):
    """A peer's no-PoM (weak) attestation is stored ONLY from an operator-TRUSTED peer
    AND with AIMARKET_SLASH_ACCEPT_WEAK on. F6 anti-poisoning: an untrusted first-contact
    peer must never contribute a weak slash (two Sybil hubs could otherwise slash a
    competitor with zero consumer proof). The env opt-out kills the tier entirely."""
    from aimarket_hub import crawler as crawler_mod
    from aimarket_hub.crawler import Crawler

    config = HubConfig()
    config.db_path = str(tmp_path / "cw.db")
    config.signing_key_path = str(tmp_path / "cwk")

    issuer = Signer(tmp_path / "wissuer")
    src = SlashRegistry("https://peer.example")
    weak_env = src.record_local_slash(  # no PoM → weak tier
        provider_hub="agent-gray", slashed_usd=5.0, dispute_id="supply_1",
        reason="verified_failure", signer=issuer, pom=None,
    )

    class _Resp:
        status_code = 200

        def json(self):
            return {"slashes": [weak_env]}

    monkeypatch.setattr(crawler_mod, "_url_is_safe", lambda u: True)

    async def fake_get(url):
        return _Resp()

    def _pull(reg, *, trusted):
        crawler = Crawler(config=config, slash_registry=reg)
        monkeypatch.setattr(crawler, "_safe_get", fake_get)
        return asyncio.run(
            crawler._pull_peer_slashes("https://peer.example", issuer.public_key_b64, trusted=trusted)
        )

    # TRUSTED peer + env on (default) → weak stored; single weak issuer still 0 penalty.
    monkeypatch.delenv("AIMARKET_SLASH_ACCEPT_WEAK", raising=False)
    reg_trusted = SlashRegistry("https://self.example")
    assert _pull(reg_trusted, trusted=True) == 1
    assert reg_trusted.slash_signal("agent-gray")["weak_issuers"] == ["https://peer.example"]
    assert reg_trusted.federated_penalty("agent-gray") == 0.0

    # UNTRUSTED peer (first contact) + env on → F6 gate drops the weak attestation.
    reg_untrusted = SlashRegistry("https://self.example")
    assert _pull(reg_untrusted, trusted=False) == 0
    assert reg_untrusted.slash_signal("agent-gray")["slash_count"] == 0

    # Explicit opt-out → nothing stored even from a trusted peer.
    monkeypatch.setenv("AIMARKET_SLASH_ACCEPT_WEAK", "0")
    reg_off = SlashRegistry("https://self.example")
    assert _pull(reg_off, trusted=True) == 0
    assert reg_off.slash_signal("agent-gray")["slash_count"] == 0


def test_crawler_accepts_strong_attestation_from_untrusted_peer(tmp_path, monkeypatch):
    """The F6 trust gate must NOT block STRONG (consumer-PoM) attestations — they are
    independently verifiable and cannot be forged, so they federate from any peer."""
    from aimarket_hub import crawler as crawler_mod
    from aimarket_hub.crawler import Crawler

    config = HubConfig()
    config.db_path = str(tmp_path / "cs.db")
    config.signing_key_path = str(tmp_path / "csk")

    issuer = Signer(tmp_path / "sissuer")
    consumer = Signer(tmp_path / "sconsumer")
    src = SlashRegistry("https://peer.example")
    strong_env = src.record_local_slash(
        provider_hub="agent-evil", slashed_usd=5.0, dispute_id="d1",
        reason="undelivered", signer=issuer, pom=_pom(consumer, dispute_id="d1", provider_hub="agent-evil"),
    )

    class _Resp:
        status_code = 200

        def json(self):
            return {"slashes": [strong_env]}

    monkeypatch.setattr(crawler_mod, "_url_is_safe", lambda u: True)

    async def fake_get(url):
        return _Resp()

    reg = SlashRegistry("https://self.example")
    crawler = Crawler(config=config, slash_registry=reg)
    monkeypatch.setattr(crawler, "_safe_get", fake_get)
    # trusted=False, yet the strong attestation is accepted.
    assert asyncio.run(
        crawler._pull_peer_slashes("https://peer.example", issuer.public_key_b64, trusted=False)
    ) == 1
    assert reg.federated_penalty("agent-evil") == 0.5
