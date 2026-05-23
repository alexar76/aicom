"""API integration tests."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("resolve_example_agent_hosts")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import base64
import hashlib


def _agent_payload(
    name: str,
    endpoint: str,
    caps: list[str],
    *,
    product_id: str = "prod_test",
    capability_id: str = "cap_test",
) -> dict:
    key = ed25519.Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    att = base64.urlsafe_b64encode(
        hashlib.sha256(f"{name}|{endpoint}|{','.join(sorted(caps))}".encode()).digest()
    ).decode().rstrip("=")
    return {
        "name": name,
        "endpoint_url": endpoint,
        "public_key_pem": pub,
        "capabilities": caps,
        "attestation": att,
        "product_id": product_id,
        "capability_id": capability_id,
        "source_hub": "local",
    }


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_and_list_agents(client):
    body = _agent_payload("Test Agent", "https://agent.example.com", ["search", "nlp"])
    r = client.post(
        "/v1/agents",
        json=body,
        headers={"Authorization": "Bearer test-admin"},
    )
    assert r.status_code == 201
    agent = r.json()
    assert agent["status"] == "verified"

    listed = client.get("/v1/agents", params={"verified_only": True})
    assert listed.status_code == 200
    assert any(a["id"] == agent["id"] for a in listed.json())


def test_mesh_task_pipeline(client):
    body = _agent_payload("Pipeline Bot", "https://pipeline.example.com", ["research", "summarize"])
    client.post("/v1/agents", json=body, headers={"Authorization": "Bearer test-admin"})

    task = client.post(
        "/v1/tasks",
        json={
            "intent": "research latest AI agent mesh patterns",
            "budget_usd": 5.0,
            "preferred_capabilities": ["research"],
        },
        headers={"Authorization": "Bearer test-api"},
    )
    assert task.status_code == 201
    data = task.json()
    assert data["status"] in ("completed", "failed")
    assert len(data["hops"]) >= 1

    activity = client.get("/v1/activity", params={"limit": 20})
    assert activity.status_code == 200
    kinds = {e["kind"] for e in activity.json()}
    assert "task.created" in kinds


def test_stats(client):
    r = client.get("/v1/stats")
    assert r.status_code == 200
    assert "agents_total" in r.json()


def test_admin_required_for_register(client):
    r = client.post(
        "/v1/agents",
        json=_agent_payload("No Auth Agent", "https://noauth.example.com", ["a"]),
    )
    assert r.status_code in (401, 403, 503)
