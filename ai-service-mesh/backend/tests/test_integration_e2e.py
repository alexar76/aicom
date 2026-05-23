"""Live integration tests — real HTTP, no stubbed invoke (requires local agent on :8091)."""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import time

import json
import urllib.error
import urllib.request

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

pytestmark = pytest.mark.integration

REAL_AGENT = os.environ.get("MESH_REAL_AGENT_URL", "http://127.0.0.1:8091")
MESH_API = os.environ.get("MESH_API_URL", "http://127.0.0.1:8090")
MESH_TOKEN = os.environ.get("MESH_API_TOKEN", "mesh-local-api")
MESH_ADMIN = os.environ.get("MESH_ADMIN_TOKEN", "mesh-local-admin")


def _agent_body() -> dict:
    key = ed25519.Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    endpoint = REAL_AGENT.rstrip("/")
    caps = ["research", "summarize"]
    name = "E2E Real Agent"
    att = base64.urlsafe_b64encode(
        hashlib.sha256(f"{name}|{endpoint}|{','.join(sorted(caps))}".encode()).digest()
    ).decode().rstrip("=")
    return {
        "name": name,
        "endpoint_url": endpoint,
        "public_key_pem": pub,
        "capabilities": caps,
        "attestation": att,
        "product_id": "",
        "capability_id": "",
        "source_hub": "local",
    }


def _http_json(method, url, body=None, headers=None):
    data = None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode() or "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return e.code, payload


@pytest.fixture(scope="module", autouse=True)
def ensure_real_agent():
    started = False
    proc = None
    try:
        code, _ = _http_json("GET", f"{REAL_AGENT.rstrip('/')}/health")
        if code == 200:
            yield
            return
    except OSError:
        pass
    proc = subprocess.Popen(
        [os.environ.get("PYTHON", "python3"), "scripts/real_agent_server.py"],
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
        env={**os.environ, "REAL_AGENT_PORT": "8091"},
    )
    started = True
    for _ in range(40):
        try:
            code, _ = _http_json("GET", f"{REAL_AGENT.rstrip('/')}/health")
            if code == 200:
                break
        except OSError:
            pass
        time.sleep(0.25)
    else:
        if proc:
            proc.kill()
        pytest.skip("real agent server did not start on :8091")
    yield
    if started and proc:
        proc.terminate()


def test_mesh_health():
    code, data = _http_json("GET", f"{MESH_API}/health")
    assert code == 200
    assert data["service"] == "ai-service-mesh"


def test_real_agent_task_pipeline():
    code, _ = _http_json(
        "POST",
        f"{MESH_API}/v1/agents",
        _agent_body(),
        {"Authorization": f"Bearer {MESH_ADMIN}"},
    )
    assert code == 201, _
    assert _["status"] == "verified", _
    code, task = _http_json(
        "POST",
        f"{MESH_API}/v1/tasks",
        {
            "intent": "research market trends for agent orchestration",
            "budget_usd": 5.0,
            "preferred_capabilities": ["research"],
        },
        {"Authorization": f"Bearer {MESH_TOKEN}"},
    )
    assert code == 201, task
    assert task["status"] == "completed"
    assert task["total_spent_usd"] > 0
    assert "[DEMO]" not in str(task).upper()
    invoke_hops = [h for h in task["hops"] if h["phase"] == "invoke"]
    assert invoke_hops and invoke_hops[0]["success"]
    assert "demo" not in invoke_hops[0]["detail"].lower()


def test_demo_hub_capability_rejected():
    """If hub only returns [DEMO] capabilities, mesh must not complete a paid task."""
    hub = os.environ.get("MESH_HUB_URL", "http://127.0.0.1:9080")
    try:
        s = httpx.get(
            f"{hub}/ai-market/v2/search",
            params={"intent": "translate", "budget": "5", "limit": "3"},
            timeout=5.0,
        )
        if s.status_code != 200:
            pytest.skip("hub not available")
        matches = s.json().get("matches") or []
        if any("[DEMO]" not in (m.get("description") or "") for m in matches):
            pytest.skip("hub has non-demo capabilities")
    except httpx.HTTPError:
        pytest.skip("hub not available")

    code, task = _http_json(
        "POST",
        f"{MESH_API}/v1/tasks",
        {"intent": "translate document", "budget_usd": 5.0},
        {"Authorization": f"Bearer {MESH_TOKEN}"},
    )
    assert code == 201
    assert task["status"] == "failed"
    assert task["error"]
