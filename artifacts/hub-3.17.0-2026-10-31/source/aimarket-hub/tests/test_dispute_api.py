"""HTTP API for dispute filing (O-1 consumer-signed + operator paths)."""

import tempfile
from pathlib import Path

import pytest
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.reputation_oracle import Dispute
from aimarket_hub.signing import Signer
from fastapi.testclient import TestClient

ADMIN = "Bearer test-admin-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AIMARKET_SKIP_SEED", "1")
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", "test-admin-token")
    with tempfile.TemporaryDirectory() as tmp:
        config = HubConfig()
        config.db_path = str(Path(tmp) / "t.db")
        config.signing_key_path = str(Path(tmp) / "hub_key")
        config.hub_url = "https://hub-self.example"
        db = HubDatabase(Path(config.db_path))
        signer = Signer(config.signing_key_path)
        app = create_app(config=config, db=db, signer=signer)
        with TestClient(app) as c:
            yield c, signer


def test_operator_file_dispute(client):
    http, _hub_signer = client
    http.app.state.reputation_oracle.stake_bond("agent-evil", 500.0)
    resp = http.post(
        "/ai-market/v2/reputation/disputes",
        json={
            "invocation_id": "inv-1",
            "provider_hub": "agent-evil",
            "consumer_hub": "consumer-a",
            "reason": "bad output",
            "requested_slash_pct": 0.2,
        },
        headers={"Authorization": ADMIN},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "hub_operator"
    assert body["dispute_id"]
    assert body["status"] == "recorded"


def test_consumer_signed_dispute(client):
    http, _hub_signer = client
    consumer = Signer()
    dispute = Dispute(
        dispute_id="d-consumer-1",
        invocation_id="inv-2",
        provider_hub="agent-evil",
        consumer_hub="consumer-b",
        reason="timeout",
        requested_slash_pct=0.15,
    ).sign(consumer)
    dispute.consumer_pubkey = consumer.public_key_b64
    resp = http.post(
        "/ai-market/v2/reputation/disputes",
        json={
            "dispute_id": dispute.dispute_id,
            "invocation_id": dispute.invocation_id,
            "provider_hub": dispute.provider_hub,
            "consumer_hub": dispute.consumer_hub,
            "reason": dispute.reason,
            "requested_slash_pct": dispute.requested_slash_pct,
            "timestamp": dispute.timestamp,
            "signature": dispute.signature,
            "consumer_pubkey": dispute.consumer_pubkey,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "consumer_signed"


def test_consumer_signed_bad_signature_rejected(client):
    http, _hub_signer = client
    consumer = Signer()
    dispute = Dispute(
        dispute_id="d-bad",
        invocation_id="inv-3",
        provider_hub="agent-evil",
        consumer_hub="consumer-c",
        reason="x",
    ).sign(consumer)
    dispute.consumer_pubkey = consumer.public_key_b64
    resp = http.post(
        "/ai-market/v2/reputation/disputes",
        json={
            "dispute_id": dispute.dispute_id,
            "invocation_id": dispute.invocation_id,
            "provider_hub": dispute.provider_hub,
            "consumer_hub": dispute.consumer_hub,
            "reason": dispute.reason,
            "timestamp": dispute.timestamp,
            "signature": "invalid-signature",
            "consumer_pubkey": dispute.consumer_pubkey,
        },
    )
    assert resp.status_code == 400


def test_operator_path_requires_admin(client):
    http, _hub_signer = client
    resp = http.post(
        "/ai-market/v2/reputation/disputes",
        json={
            "invocation_id": "inv-4",
            "provider_hub": "agent-evil",
            "consumer_hub": "consumer-d",
            "reason": "no auth",
        },
    )
    assert resp.status_code in (401, 403)
