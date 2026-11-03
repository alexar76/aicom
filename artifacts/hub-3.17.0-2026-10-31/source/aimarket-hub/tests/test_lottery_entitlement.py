from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.lottery_entitlement import entitlement_canonical, participant_id
from aimarket_hub.signing import Signer


def test_authenticated_agent_gets_wallet_bound_lottery_entitlement(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_AGENT_TOKENS", "agent-7:secret-7")
    monkeypatch.setenv("AIMARKET_HUB_URL", "https://home-hub.example")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "signing.key")
    signer = Signer(config.signing_key_path)
    app = create_app(config=config, db=HubDatabase(config.db_path), signer=signer)
    wallet = "0x000000000000000000000000000000000000dEaD"
    with TestClient(app) as client:
        discovery = client.get("/.well-known/ai-market.json").json()
        denied = client.post(
            "/ai-market/v2/lottery/work-seat-entitlement",
            json={"agent_id": "agent-7", "wallet": wallet},
        )
        assert denied.status_code == 401
        response = client.post(
            "/ai-market/v2/lottery/work-seat-entitlement",
            json={"agent_id": "agent-7", "wallet": wallet},
            headers={"Authorization": "Bearer secret-7"},
        )
    assert response.status_code == 200, response.text
    admission = discovery["lottery_admission"]
    assert admission["enabled"] is True
    assert admission["max_ttl_s"] == 600
    assert admission["work_seat_entitlement_url"] == (
        "https://home-hub.example/ai-market/v2/lottery/work-seat-entitlement"
    )
    entitlement = response.json()["entitlement"]
    assert entitlement["participant_id"] == participant_id("https://home-hub.example", "agent-7")
    assert entitlement["wallet"] == wallet.lower()
    signature = entitlement["signature"]
    Ed25519PublicKey.from_public_bytes(base64.b64decode(signature["public_key"])).verify(
        base64.b64decode(signature["value"]),
        entitlement_canonical(entitlement).encode("utf-8"),
    )


def test_entitlement_refuses_invalid_wallet(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_AGENT_TOKENS", "agent-7:secret-7")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "signing.key")
    app = create_app(
        config=config,
        db=HubDatabase(config.db_path),
        signer=Signer(config.signing_key_path),
    )
    with TestClient(app) as client:
        response = client.post(
            "/ai-market/v2/lottery/work-seat-entitlement",
            json={"agent_id": "agent-7", "wallet": "x" * 42},
            headers={"Authorization": "Bearer secret-7"},
        )
    assert response.status_code == 422
