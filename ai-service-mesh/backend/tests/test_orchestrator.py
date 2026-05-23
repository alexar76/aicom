"""Orchestrator unit tests."""

import pytest

pytestmark = pytest.mark.usefixtures("resolve_example_agent_hosts")

from ai_service_mesh.config import Settings
from ai_service_mesh.db import MeshStore
from ai_service_mesh.discovery import DiscoveryService
from ai_service_mesh.orchestrator import MeshOrchestrator
from ai_service_mesh.payments import EscrowLedger


@pytest.mark.asyncio
async def test_run_task_completes_with_verified_agent(tmp_path):
    store = MeshStore(tmp_path / "mesh")
    discovery = DiscoveryService(store)
    orch = MeshOrchestrator(store, discovery, EscrowLedger(store), hub_url="")

    import base64
    import hashlib
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    key = ed25519.Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    name, endpoint, caps = "Orchestrator Bot", "https://orch.example.com", ["etl", "sql"]
    att = base64.urlsafe_b64encode(
        hashlib.sha256(f"{name}|{endpoint}|{','.join(sorted(caps))}".encode()).digest()
    ).decode().rstrip("=")
    agent = store.register_agent(name, endpoint, pub, caps, att)
    store.verify_agent(agent.id, 0.95)

    task = store.create_task("run etl on sales data", 10.0, "")
    result = await orch.run_task(task, ["etl"])
    assert result.status.value in ("completed", "failed")
    assert len(result.hops) >= 2


@pytest.mark.asyncio
async def test_run_task_falls_back_to_second_agent(tmp_path, monkeypatch):
    store = MeshStore(tmp_path / "mesh")
    discovery = DiscoveryService(store)
    orch = MeshOrchestrator(store, discovery, EscrowLedger(store), hub_url="")

    import base64
    import hashlib
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    def register(name: str, endpoint: str, caps: list[str]):
        key = ed25519.Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        att = base64.urlsafe_b64encode(
            hashlib.sha256(f"{name}|{endpoint}|{','.join(sorted(caps))}".encode()).digest()
        ).decode().rstrip("=")
        agent = store.register_agent(name, endpoint, pub, caps, att)
        store.verify_agent(agent.id, 0.9)
        return agent

    register("Fail Bot", "https://fail.example.com", ["etl"])
    register("Win Bot", "https://win.example.com", ["etl"])

    async def flaky_preflight(endpoint_url: str):
        if "fail.example.com" in endpoint_url:
            return False, 1, "down"
        return True, 5, "health_ok"

    async def invoke_direct(endpoint_url: str, intent: str, **_k):
        if "win.example.com" in endpoint_url:
            return True, 10, "invoke_ok", {}
        return False, 10, "invoke_failed", {}

    monkeypatch.setattr("ai_service_mesh.orchestrator.preflight_agent", flaky_preflight)
    monkeypatch.setattr("ai_service_mesh.orchestrator.invoke_direct", invoke_direct)

    task = store.create_task("run etl pipeline", 10.0, "")
    result = await orch.run_task(task, ["etl"])
    assert result.status.value == "completed"
    assert result.selected_agent_id
    assert any(h.phase == "invoke" and h.success for h in result.hops)


@pytest.mark.asyncio
async def test_invoke_hub_requires_hub_url(tmp_path):
    store = MeshStore(tmp_path / "mesh")
    orch = MeshOrchestrator(store, DiscoveryService(store), EscrowLedger(store), hub_url="")
    agent = store.register_agent(
        "Hub Agent",
        "https://hub-agent.example.com",
        "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEA\n-----END PUBLIC KEY-----",
        ["etl"],
        "x",
        product_id="prod1",
        capability_id="cap1",
    )
    store.verify_agent(agent.id, 0.9)
    from ai_service_mesh.discovery import DiscoveryMatch

    match = DiscoveryMatch(
        agent=store.get_agent(agent.id),
        score=1.0,
        price_usd=1.0,
        source="local",
    )
    ok, _lat, detail, _ = await orch._invoke_match(match, "test")
    assert not ok
    assert detail == "hub_url_not_configured"
