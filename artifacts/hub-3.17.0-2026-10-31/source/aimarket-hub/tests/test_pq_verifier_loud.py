"""A hub that cannot check post-quantum signatures must say so — never silently.

Every AIMarket hub signs hybrid (Ed25519 + ML-DSA-65). A hub without the ML-DSA-65 verifier
fails closed on those signatures, which is right: it cannot tell a real PQ signature from junk
attached to a forged classical one. What was wrong (found 2026-10-06): the verifier was an
optional extra, so a plain `pip install aimarket-hub` produced exactly that hub, and it said
nothing but "Invalid manifest signature" — the operator was told the PEER was broken.

Since 3.15.18 the verifier is a core dependency, and a hub that still lacks it says so at
import, in the crawler's log by name, and in /health as "degraded".
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import aimarket_hub.signing as signing
from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import Crawler
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.signing import Signer

PEER = "https://seed-hub.example.com"


@pytest.fixture(autouse=True)
def _safe_urls(monkeypatch):
    import aimarket_hub.crawler as crawler_mod

    monkeypatch.setattr(crawler_mod, "_url_is_safe", lambda url: url.startswith("https://"))
    monkeypatch.delenv("AIMARKET_PQC_REQUIRE", raising=False)


@pytest.fixture
def no_pq_library(monkeypatch):
    monkeypatch.setattr(signing, "_PQ_LIB", False)
    monkeypatch.setattr(signing, "_pq_unverifiable_refusals", 0)


def _hybrid_signature(signer: Signer, doc: dict) -> dict:
    """A real classical signature plus PQ fields; their content does not matter to a hub that
    cannot evaluate them, which is the point."""
    sig = signer.sign_manifest(doc)
    sig.update({"pq_algorithm": "ml-dsa-65", "pq_public_key": "AAAA", "pq_value": "AAAA"})
    return sig


# ── the dependency ───────────────────────────────────────────────────────────────────────

def test_the_verifier_is_a_core_dependency():
    project = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text())
    core = project["project"]["dependencies"]
    assert any(d.startswith("dilithium-py") for d in core), (
        "a plain `pip install aimarket-hub` must be able to read hybrid-signing peers")
    # The documented `[pqc]` install lines keep working.
    assert any(d.startswith("dilithium-py") for d in project["project"]["optional-dependencies"]["pqc"])


def test_this_install_can_verify():
    assert signing.pqc_available(), "the test environment itself lacks the PQ verifier"


# ── the refusal is named, counted and logged ────────────────────────────────────────────

def test_an_unverifiable_pq_signature_is_refused_counted_and_explained(tmp_path, no_pq_library, caplog):
    signer = Signer(tmp_path / "k")
    doc = {"capabilities_count": 1, "generated_at": "2026-01-01T00:00:00Z", "tools": [{"name": "t"}]}
    doc["signature"] = _hybrid_signature(signer, doc)
    assert signing.pq_unverifiable(doc["signature"]) is True
    with caplog.at_level(logging.ERROR, logger="aimarket_hub.signing"):
        assert signer.verify_manifest_signature(doc, signer.public_key_b64) is False
        assert signer.verify_manifest_signature(doc, signer.public_key_b64) is False
    assert signing.pq_unverifiable_refusals() == 2
    explained = [r for r in caplog.records if "dilithium-py" in r.getMessage()]
    assert len(explained) == 1, "explained once, not once per document"
    assert "aimarket-hub[pqc]" in explained[0].getMessage()


def test_a_classical_signature_is_not_counted_as_unverifiable(tmp_path, no_pq_library):
    signer = Signer(tmp_path / "k")
    doc = {"capabilities_count": 1, "generated_at": "2026-01-01T00:00:00Z", "tools": [{"name": "t"}]}
    doc["signature"] = signer.sign_manifest(doc)
    assert signing.pq_unverifiable(doc["signature"]) is False
    assert signer.verify_manifest_signature(doc, signer.public_key_b64) is True
    assert signing.pq_unverifiable_refusals() == 0


# ── the crawler names the real reason ───────────────────────────────────────────────────

async def _crawl_hybrid_peer(tmp_path, *, tamper: bool):
    signer = Signer(tmp_path / "peer_key")   # the peer's key; the crawler's own key is irrelevant
    db = HubDatabase(tmp_path / "hub.db")
    db.upsert_peer(Peer(url=PEER, name="Peer", public_key=signer.public_key_b64, trusted=True))
    config = HubConfig()
    config.max_crawl_depth = 1
    config.request_timeout_s = 5
    well_known = {"name": "Peer", "protocol_versions": ["v2"], "capabilities_count": 1,
                  "manifest_url": f"{PEER}/ai-market/manifest",
                  "signer_public_key": signer.public_key_b64, "peers": []}
    manifest = {"protocol_version": "v2", "capabilities_count": 1,
                "generated_at": "2026-10-06T00:00:00Z",
                "tools": [{"name": "weather.read", "description": "d",
                           "input_schema": {"type": "object"}}]}
    manifest["signature"] = _hybrid_signature(signer, manifest)
    if tamper:
        manifest["capabilities_count"] = 2      # the classical half no longer verifies

    class _Resp:
        status_code = 200

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    crawler = Crawler(config=config, db=db, signer=Signer(tmp_path / "own_key"))
    crawler._safe_get = AsyncMock(side_effect=lambda url, *a, **k: _Resp(
        well_known if url.endswith("ai-market.json") else manifest))
    try:
        return await crawler._crawl_one(f"{PEER}/.well-known/ai-market.json", 0, "seed")
    finally:
        await crawler.close()
        db.close()


@pytest.mark.asyncio
async def test_the_crawler_blames_the_missing_library_not_the_peer(tmp_path, no_pq_library, caplog):
    with caplog.at_level(logging.WARNING):
        result = await _crawl_hybrid_peer(tmp_path, tamper=False)
    assert result is None
    text = caplog.text
    assert "refused, not indexed" in text and "aimarket-hub[pqc]" in text
    assert "Invalid manifest signature" not in text, "the peer's document is fine"


@pytest.mark.asyncio
async def test_a_really_invalid_signature_is_still_called_invalid(tmp_path, caplog):
    """With the verifier present, a tampered document keeps its old, true message."""
    with caplog.at_level(logging.WARNING):
        result = await _crawl_hybrid_peer(tmp_path, tamper=True)
    assert result is None
    assert "Invalid manifest signature" in caplog.text
    assert "aimarket-hub[pqc]" not in caplog.text


# ── /health says it ─────────────────────────────────────────────────────────────────────

def _health(tmp_path):
    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app

    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = create_app(config=config, db=HubDatabase(tmp_path / "hub.db"), signer=Signer(tmp_path / "key"))
    with TestClient(app) as client:
        return client.get("/ai-market/v2/health").json()


def test_health_reports_a_hub_that_can_read_hybrid_peers(tmp_path):
    body = _health(tmp_path)
    assert body["status"] == "ok" and body["pqc_can_verify"] is True
    assert "warnings" not in body


def test_health_is_degraded_and_says_why_without_the_verifier(tmp_path, no_pq_library):
    body = _health(tmp_path)
    assert body["status"] == "degraded"
    assert body["pqc_can_verify"] is False
    assert any("aimarket-hub[pqc]" in w for w in body["warnings"])
    assert body["pq_unverifiable_refusals"] == 0


# ── a hub must not lose its identity silently ───────────────────────────────────────────

def test_new_signing_keys_are_announced_loudly(tmp_path, monkeypatch, caplog):
    """A hub that quietly makes a new identity is refused by every peer that pinned the old
    one and drops out of the federation. Generating keys is therefore always loud — not only
    under AIFACTORY_PROD, which a stranger's hub never sets."""
    monkeypatch.delenv("AIFACTORY_PROD", raising=False)
    with caplog.at_level(logging.WARNING, logger="aimarket_hub.signing"):
        Signer(tmp_path / "hub_key", pqc=True)
    messages = [r.getMessage() for r in caplog.records]
    assert any("NEW Ed25519 signing key" in m and str(tmp_path / "hub_key") in m for m in messages)
    assert any("NEW post-quantum (ML-DSA-65) signing key" in m for m in messages)


def test_an_existing_identity_loads_quietly(tmp_path, caplog):
    Signer(tmp_path / "hub_key", pqc=True)
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="aimarket_hub.signing"):
        Signer(tmp_path / "hub_key", pqc=True)
    assert not [r for r in caplog.records if "NEW" in r.getMessage()]


# ── a new hub signs like ours; an existing one keeps what it has ────────────────────────

@pytest.mark.parametrize("env, has_ed25519, has_mldsa, expected", [
    (None, False, False, True),    # a new hub: hybrid, like every AIMarket hub
    (None, True, False, False),    # an existing Ed25519-only hub: unchanged
    (None, True, True, True),      # a hybrid hub that lost its flag on a redeploy keeps signing PQ
    ("1", True, False, True),      # the operator's word wins
    ("0", False, False, False),
    ("0", True, True, False),
])
def test_hub_signs_hybrid_rule(tmp_path, monkeypatch, env, has_ed25519, has_mldsa, expected):
    if env is None:
        monkeypatch.delenv("AIMARKET_PQC", raising=False)
    else:
        monkeypatch.setenv("AIMARKET_PQC", env)
    key = tmp_path / "hub_signing_key"
    if has_ed25519:
        key.write_bytes(b"x" * 64)
    if has_mldsa:
        (tmp_path / "hub_signing_key_mldsa").write_text("aa\nbb\n")
    assert signing.hub_signs_hybrid(key) is expected


def test_a_new_hub_without_the_library_starts_classically(tmp_path, monkeypatch, no_pq_library):
    monkeypatch.delenv("AIMARKET_PQC", raising=False)
    assert signing.hub_signs_hybrid(tmp_path / "hub_signing_key") is False


def test_a_new_hub_app_signs_its_manifest_hybrid(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app

    monkeypatch.delenv("AIMARKET_PQC", raising=False)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "fresh_key")
    app = create_app(config=config, db=HubDatabase(tmp_path / "hub.db"))   # the hub builds its own signer
    with TestClient(app) as client:
        wk = client.get("/.well-known/ai-market.json").json()
        health = client.get("/ai-market/v2/health").json()
    assert wk["signature"].get("pq_algorithm") == "ml-dsa-65"
    assert health["pqc_ready"] is True
