"""Search evidence must come from the successful signature check, never a peer claim."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.crawler import Crawler
from aimarket_hub.database import HubDatabase
from aimarket_hub.db_backend import create_backend
from aimarket_hub.migrations import Migrations
from aimarket_hub.models import Capability, Peer
from aimarket_hub.signing import Signer


def test_migration_keeps_existing_rows_without_inventing_checks(tmp_path):
    path = tmp_path / "old.db"
    backend = create_backend(db_path=path)
    Migrations(backend).apply(target_version=63)
    backend.execute(
        "INSERT INTO capabilities (capability_id, product_id, name, source_hub) VALUES (?, ?, ?, ?)",
        ("weather@v1", "weather", "Weather", "local"),
    )
    backend.commit()
    backend.close()
    db = HubDatabase(path)
    try:
        assert db.get_capability("weather", "weather@v1").catalogue_evidence == {}
    finally:
        db.close()


@pytest.mark.asyncio
async def test_successful_crawl_records_actual_signer_and_failed_refresh_keeps_old_check(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY", "0")
    monkeypatch.setattr("aimarket_hub.crawler._url_is_safe", lambda url: url.startswith("https://"))
    config = HubConfig()
    config.hub_url = "https://our-hub.example"
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "hub.key")
    peer_url = "https://peer.example"
    peer_signer = Signer(tmp_path / "peer.key")
    signer = Signer(config.signing_key_path)
    db = HubDatabase(config.db_path)
    db.upsert_peer(Peer(url=peer_url, name="Peer", public_key=peer_signer.public_key_b64, trusted=True))
    wk = {
        "name": "Peer", "protocol_versions": ["v1", "v2"],
        "manifest_url": peer_url + "/manifest", "capabilities_count": 1,
        "signer_public_key": peer_signer.public_key_b64,
    }
    manifest = {
        "protocol_version": "v2", "generated_at": datetime.now(timezone.utc).isoformat(),
        "capabilities_count": 1,
        "tools": [{"name": "weather", "capability_id": "weather@v1", "product_id": "weather",
                   "description": "Weather", "input_schema": {}, "price_per_call_usd": 0.003,
                   "catalogue_evidence": {"signer": "attacker", "checked_at": "2099-01-01T00:00:00Z"}}],
    }
    manifest["signature"] = peer_signer.sign_manifest(manifest)
    crawler = Crawler(config=config, db=db, signer=signer)

    async def get(url):
        return httpx.Response(200, json=wk if ".well-known/" in url else manifest)

    crawler._safe_get = AsyncMock(side_effect=get)
    try:
        result = await crawler._crawl_one(peer_url + "/.well-known/ai-market.json", 0, "test")
        assert result["capabilities_count"] == 1
        evidence = db.get_capability("weather", "weather@v1", peer_url).catalogue_evidence
        assert evidence["kind"] == "signed_catalogue"
        assert evidence["signer"] == peer_url
        assert evidence["signer_public_key"] == peer_signer.public_key_b64
        assert evidence["checked_by"] == config.hub_url
        assert evidence["checked_at"] != "2099-01-01T00:00:00Z"
        datetime.fromisoformat(evidence["checked_at"].replace("Z", "+00:00"))

        # An updated peer.last_crawl must not advance a listing's signature check.
        manifest["tools"][0]["price_per_call_usd"] = 9.0  # breaks the real signature
        monkeypatch.setattr("aimarket_hub.crawler.time.strftime", lambda *args: "2099-01-01T00:00:00Z")
        assert await crawler._crawl_one(peer_url + "/.well-known/ai-market.json", 0, "test") is None
        assert db.get_peer(peer_url).last_crawl == "2099-01-01T00:00:00Z"
        assert db.get_capability("weather", "weather@v1", peer_url).catalogue_evidence == evidence

        db.upsert_capability(Capability(capability_id="legacy@v1", product_id="legacy", name="Legacy",
                                       source_hub=peer_url, invoke_url=peer_url + "/invoke", trust_score=0.5))
        with TestClient(create_app(config=config, db=db, signer=signer)) as client:
            db.upsert_capability(Capability(capability_id="local@v1", product_id="local", name="Local",
                                           price_per_call_usd=0, trust_score=0.5,
                                           invoke_url="https://local.example/invoke"))
            response = client.get("/ai-market/v2/search", params={"intent": "", "limit": 0, "include_stale": True})
            assert response.status_code == 200
            rows = {r["capability_id"]: r for r in response.json()["matches"]}
            assert rows["weather@v1"]["evidence"] == evidence
            assert rows["legacy@v1"]["evidence"]["kind"] == "catalogue_unrecorded"
            assert rows["legacy@v1"]["evidence"]["checked_at"] is None
            assert rows["local@v1"]["evidence"]["kind"] == "local_catalogue"
            assert rows["local@v1"]["evidence"]["signer"] is None
    finally:
        await crawler.close()
        db.close()
