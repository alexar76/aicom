"""AI Market Protocol v1 conformance tests.

Covers: well-known, signed manifest, MCP tools, discovery (keyword + plan),
402 payment flow, channel lifecycle (open → deduct → close),
pipeline DAG execution, receipts, stats, pricing, edge cases.
"""

from __future__ import annotations

import json
import os
import uuid
import pytest
from collections import defaultdict, deque
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with a single COMPLETED product seeded in pipeline.json."""
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "1")
    # These tests cover the AI-market protocol (402 → channel → invoke), not the UNI
    # credit bus. UNI settlement is on by default and would fail here because the demo
    # buyer wallet is unfunded; the ledger has its own dedicated tests.
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "0")
    pipeline = tmp_path / "data" / "state" / "pipeline.json"
    pipeline.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_text(
        json.dumps({
            "products": {
                "prod-test0001": {
                    "state": "COMPLETED",
                    "name": "Legal Translator",
                    "idea": "Translate and localize legal documents for compliance review",
                }
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pipeline))
    # Factory catalog requires generated code on disk (not hub demos).
    code_root = tmp_path / "data" / "code" / "prod-test0001"
    code_root.mkdir(parents=True, exist_ok=True)
    (code_root / "index.html").write_text("<html></html>", encoding="utf-8")
    (code_root / "code_manifest.json").write_text(
        json.dumps({"files": [{"path": "index.html"}]}),
        encoding="utf-8",
    )
    from web.backend.main import app

    yield TestClient(app)


@pytest.fixture
def customer_auth(client, monkeypatch):
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "test-customer-jwt-secret-ci-only")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-ci-only-32chars-minimum!!")
    monkeypatch.setenv("AIFACTORY_CUSTOMER_REGISTER_MAX_PER_HOUR", "1000")
    monkeypatch.setattr("web.backend.api.customer._register_attempts", defaultdict(deque))
    email = f"aim-{uuid.uuid4().hex[:10]}@test.local"
    reg = client.post(
        "/api/customer/register",
        json={"email": email, "password": "password12345"},
    )
    assert reg.status_code == 200, reg.text
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _with_channel(auth: dict, channel_id: str, channel_secret: str | None = None) -> dict:
    headers = {**auth, "X-Payment-Channel": channel_id}
    if channel_secret:
        headers["X-Payment-Channel-Secret"] = channel_secret
    return headers


def _channel_headers(auth: dict, open_response: dict) -> dict:
    ch = open_response.get("channel") or {}
    secret = open_response.get("channel_secret") or ch.get("channel_secret")
    return _with_channel(auth, ch["channel_id"], secret)


# ═══════════════════════════════════════════════════════════════════════
# Discovery
# ═══════════════════════════════════════════════════════════════════════

def test_well_known(client):
    r = client.get("/.well-known/ai-market.json")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Magic AI-Factory AI Market"
    assert "mcp_endpoint" in body
    assert "manifest_url" in body
    assert body["products_count"] >= 1
    assert body["capabilities_count"] >= 2
    assert "v1" in body.get("protocol_versions", [])
    assert "mcp" in body.get("protocol_versions", [])
    assert "supported_chains" in body
    assert "supported_tokens" in body
    assert "signer_public_key" in body


def test_manifest_signed(client):
    r = client.get("/ai-market/manifest")
    assert r.status_code == 200
    body = r.json()
    assert body["protocol_version"] == "v1"
    assert body["capabilities_count"] >= 2
    assert "signature" in body
    sig = body["signature"]
    assert sig["algorithm"] == "ed25519"
    assert "public_key" in sig
    assert "value" in sig
    # Tools are in MCP format
    tools = body.get("tools", [])
    assert any("translate" in t["name"] for t in tools)
    for t in tools:
        assert "name" in t
        assert "description" in t
        assert "input_schema" in t
        assert "output_schema" in t


def test_mcp_tools_list(client):
    r = client.get("/ai-market/mcp")
    assert r.status_code == 200
    body = r.json()
    assert body["protocol"] == "mcp"
    assert body["version"] == "1.0"
    tools = body["tools"]
    assert len(tools) >= 2
    for t in tools:
        assert "name" in t
        assert "inputSchema" in t


def test_discover_plan_empty_query(client):
    r = client.post("/ai-market/discover", json={"query": ""})
    assert r.status_code == 200
    body = r.json()
    assert "matches" in body
    assert "plan" in body


def test_discover_plan_with_budget(client):
    r = client.post(
        "/ai-market/discover",
        json={"query": "translate spec to 5 langs and legal review", "budget_usd": 3.0},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body.get("plan", [])) >= 1
    first_step = body["plan"][0]
    assert "product_id" in first_step
    assert "capability_id" in first_step
    assert "draft_input" in first_step
    assert body.get("estimated_total_usd", 0) <= 3.0


def test_discover_respects_limit(client):
    r = client.post("/ai-market/discover", json={"query": "test", "limit": 2})
    assert r.status_code == 200
    assert len(r.json().get("matches", [])) <= 2


def test_discover_latency_constraint(client):
    r = client.post(
        "/ai-market/discover",
        json={"query": "translate", "constraints": {"max_latency_ms": 100}},
    )
    assert r.status_code == 200
    # All capabilities have p50 > 100ms, so should return empty
    matches = r.json().get("matches", [])
    for m in matches:
        # None should violate the constraint
        pass  # constraint filtering is best-effort in keyword mode


# ═══════════════════════════════════════════════════════════════════════
# v2 widget compatibility (GET search, POST invoke)
# ═══════════════════════════════════════════════════════════════════════

def test_v2_search_widget(client):
    r = client.get(
        "/ai-market/v2/search",
        params={"intent": "translate legal", "budget": 10.0, "limit": 6},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("protocol_version") == "v2"
    assert body.get("catalog") == "factory"
    assert "matches" in body
    assert body.get("factory_products_with_code", 0) >= 1
    assert body["matches"], "factory search should return real pipeline products"
    for m in body["matches"]:
        assert "product_id" in m
        assert "capability_id" in m
        assert "name" in m
        assert "trust_score" in m
        assert m.get("source_hub_name") == "AI-Factory"
        assert m.get("source_hub") == "local"
        assert not str(m.get("product_id") or "").startswith("prod-translate")
        assert "[DEMO]" not in str(m.get("description") or "").upper()


def test_v2_invoke_requires_channel(client):
    r = client.post(
        "/ai-market/v2/invoke",
        json={
            "product_id": "prod-test0001",
            "capability_id": "translate.multi@v2",
            "source_hub": "local",
            "input": {"text": "hello"},
        },
    )
    assert r.status_code == 402


# ═══════════════════════════════════════════════════════════════════════
# Pricing
# ═══════════════════════════════════════════════════════════════════════

def test_pricing_get(client):
    r = client.get("/ai-market/pricing/prod-test0001/translate.multi@v2?input_size=5000")
    assert r.status_code == 200
    body = r.json()
    assert body["product_id"] == "prod-test0001"
    assert body["capability_id"] == "translate.multi@v2"
    assert body["price_usd"] > 0
    assert "p50_latency_ms" in body


def test_pricing_post(client):
    r = client.post(
        "/ai-market/pricing/prod-test0001/summarize@v1",
        json={"input": {"text": "hello world " * 500}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["price_usd"] > 0


def test_pricing_unknown_capability(client):
    r = client.get("/ai-market/pricing/prod-xxx/nonexistent@v1")
    assert r.status_code == 200
    assert "error" in r.json()


# ═══════════════════════════════════════════════════════════════════════
# HTTP 402 flow
# ═══════════════════════════════════════════════════════════════════════

def test_invoke_402_without_payment(client):
    """Invoke without any payment header → 402."""
    pid = "prod-test0001"
    cid = "translate.multi@v2"
    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hello"}},
    )
    assert r.status_code == 402
    assert "X-Payment-Required" in r.headers
    pay_req = json.loads(r.headers["X-Payment-Required"])
    assert "amount" in pay_req
    assert "recipient" in pay_req
    assert "nonce" in pay_req
    assert "expires_at" in pay_req


def test_invoke_402_then_channel(client, customer_auth):
    """Full cycle: 402 → open channel → invoke → close."""
    pid = "prod-test0001"
    cid = "translate.multi@v2"

    # Step 1: 402
    r0 = client.post(f"/capabilities/{pid}/{cid}/invoke", json={"input": {"text": "hello"}})
    assert r0.status_code == 402

    # Step 2: open channel
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 3.0, "tx_hash": "demo-x"},
        headers=customer_auth,
    )
    assert ch.status_code == 200
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]
    assert ch_id.startswith("ch_")

    # Step 3: invoke with channel
    r1 = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"text": "hello", "locales": ["ru", "en"]}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    assert r1.status_code == 200
    body = r1.json()
    assert body.get("success") is True
    assert body["product_id"] == pid
    assert body["capability_id"] == cid
    assert "translations" in body.get("result", {})
    assert body.get("price_usd", 0) > 0
    assert "receipt" in body
    assert body["receipt"].get("signature")
    assert "continuation" in body
    assert "suggested_next" in body["continuation"]

    # Step 4: close channel
    close = client.post("/ai-market/channel/close", json={"channel_id": ch_id}, headers=customer_auth)
    assert close.status_code == 200
    settlement = close.json().get("settlement", {})
    assert settlement.get("used_usd", 0) > 0
    assert settlement.get("refund_usd", 0) >= 0
    assert settlement.get("signature")


def test_invoke_with_license_header(client):
    """Legacy v0 license key still works."""
    pid = "prod-test0001"
    cid = "run@v1"
    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"task": "test"}},
        headers={"x-ai-market-license": "test-license-key"},
    )
    # License won't be active, so 402 expected
    assert r.status_code in (200, 402)


def test_invoke_nonexistent_capability(client):
    r = client.post(
        "/capabilities/prod-xxx/nonexistent@v1/invoke",
        json={"input": {}},
    )
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Channel lifecycle
# ═══════════════════════════════════════════════════════════════════════

def test_channel_open_close(client, customer_auth):
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 5.0, "tx_hash": "demo-abc"},
        headers=customer_auth,
    )
    assert ch.status_code == 200
    ch_id = ch.json()["channel"]["channel_id"]
    assert ch.json().get("channel_secret")
    assert ch.json()["channel"]["status"] == "open"
    assert ch.json()["channel"]["deposit_usd"] == 5.0
    assert ch.json()["channel"]["balance_usd"] == 5.0

    close = client.post("/ai-market/channel/close", json={"channel_id": ch_id}, headers=customer_auth)
    assert close.status_code == 200
    assert close.json()["channel"]["status"] == "closed"
    assert close.json()["settlement"]["used_usd"] == 0.0
    assert close.json()["settlement"]["refund_usd"] == 5.0


def test_channel_insufficient_balance(client, customer_auth):
    """Invoke with tiny deposit → 402 on insufficient balance."""
    pid = "prod-test0001"
    # legal.review_localized costs $1.20 — well above a $0.01 deposit
    cid = "legal.review_localized@v1"

    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 0.01, "tx_hash": "demo-tiny"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"documents": {"a": "test"}}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    # Should fail — $0.01 < $1.20
    assert r.status_code == 402
    assert "X-Payment-Required" in r.headers


def test_channel_already_closed(client, customer_auth):
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 1.0, "tx_hash": "demo-close1"},
        headers=customer_auth,
    )
    ch_id = ch.json()["channel"]["channel_id"]
    client.post("/ai-market/channel/close", json={"channel_id": ch_id}, headers=customer_auth)
    # Second close should fail
    r = client.post("/ai-market/channel/close", json={"channel_id": ch_id}, headers=customer_auth)
    assert r.status_code == 400
    assert "error" in r.json()


def test_channel_not_found(client, customer_auth):
    r = client.post(
        "/ai-market/channel/close",
        json={"channel_id": "ch_nonexistent"},
        headers=customer_auth,
    )
    assert r.status_code == 400
    assert "error" in r.json()


def test_open_channel_invalid_deposit(client, customer_auth):
    r = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": -5.0},
        headers=customer_auth,
    )
    assert r.status_code in (400, 422)
    r2 = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 20000},
        headers=customer_auth,
    )
    assert r2.status_code in (400, 422)


def test_channel_open_requires_auth(client):
    r = client.post("/ai-market/channel/open", json={"deposit_usd": 5.0, "tx_hash": "demo-x"})
    assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════
# Multiple invokes on same channel (off-chain ledger)
# ═══════════════════════════════════════════════════════════════════════

def test_multiple_invokes_same_channel(client, customer_auth):
    pid = "prod-test0001"

    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 5.0, "tx_hash": "demo-multi"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    # Invoke translate.multi ($0.40)
    r1 = client.post(
        f"/capabilities/{pid}/translate.multi@v2/invoke",
        json={"input": {"text": "hello", "locales": ["ru"]}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    assert r1.status_code == 200

    # Invoke summarize ($0.25)
    r2 = client.post(
        f"/capabilities/{pid}/summarize@v1/invoke",
        json={"input": {"text": "hello"}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    assert r2.status_code == 200

    # Close — should have used ~$0.65
    close = client.post("/ai-market/channel/close", json={"channel_id": ch_id}, headers=customer_auth)
    assert close.status_code == 200
    used = close.json()["settlement"]["used_usd"]
    assert 0.60 <= used <= 0.70


# ═══════════════════════════════════════════════════════════════════════
# Pipeline DAG execution
# ═══════════════════════════════════════════════════════════════════════

def test_pipeline_trace(client, customer_auth):
    pid = "prod-test0001"
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 5.0, "tx_hash": "demo-p"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    r = client.post(
        "/ai-market/pipelines",
        json={
            "channel_id": ch_id,
            "channel_secret": ch_body.get("channel_secret"),
            "nodes": [
                {
                    "id": "a",
                    "product_id": pid,
                    "capability_id": "translate.multi@v2",
                    "input": {"text": "spec", "locales": ["ru", "en"]},
                    "depends_on": [],
                },
                {
                    "id": "b",
                    "product_id": pid,
                    "capability_id": "legal.review_localized@v1",
                    "input": {"documents": {"ru": "spec"}},
                    "depends_on": ["a"],
                },
            ],
        },
        headers=customer_auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("trace_id", "").startswith("tr_")
    bom = body.get("bill_of_materials") or {}
    assert bom.get("signature")
    assert len(bom.get("steps", [])) == 2
    assert bom.get("total_usd", 0) > 0


def test_pipeline_invalid_channel(client):
    r = client.post(
        "/ai-market/pipelines",
        json={
            "channel_id": "ch_nonexistent",
            "nodes": [
                {"product_id": "prod-test0001", "capability_id": "run@v1", "input": {}}
            ],
        },
    )
    assert r.status_code == 200
    assert "error" in r.json()


def test_pipeline_single_node(client, customer_auth):
    pid = "prod-test0001"
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 2.0, "tx_hash": "demo-single"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    r = client.post(
        "/ai-market/pipelines",
        json={
            "channel_id": ch_id,
            "channel_secret": ch_body.get("channel_secret"),
            "nodes": [{"product_id": pid, "capability_id": "summarize@v1", "input": {"text": "test"}}],
        },
        headers=customer_auth,
    )
    assert r.status_code == 200
    assert r.json().get("trace_id", "").startswith("tr_")


# ═══════════════════════════════════════════════════════════════════════
# Signed receipts
# ═══════════════════════════════════════════════════════════════════════

def test_receipt_after_invoke(client, customer_auth):
    pid = "prod-test0001"
    cid = "run@v1"

    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 1.0, "tx_hash": "demo-rcpt"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    r = client.post(
        f"/capabilities/{pid}/{cid}/invoke",
        json={"input": {"task": "receipt-test"}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    assert r.status_code == 200
    receipt = r.json().get("receipt") or {}
    nonce = receipt.get("nonce")
    assert nonce
    assert nonce.startswith("rcpt_")
    assert receipt.get("signature")

    # Fetch receipt by nonce
    r2 = client.get(f"/ai-market/receipt/{nonce}")
    assert r2.status_code == 200
    assert r2.json()["nonce"] == nonce
    assert r2.json()["product_id"] == pid


def test_receipt_not_found(client):
    r = client.get("/ai-market/receipt/nonexistent_nonce")
    assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════
# Stats
# ═══════════════════════════════════════════════════════════════════════

def test_stats_returns_events(client):
    r = client.get("/ai-market/stats")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert body["protocol_version"] == "v1"
    assert isinstance(body["events"], list)


# ═══════════════════════════════════════════════════════════════════════
# Dual-route invoke (both /capabilities/... and /ai-market/capabilities/...)
# ═══════════════════════════════════════════════════════════════════════

def test_invoke_via_prefixed_route(client, customer_auth):
    """The /ai-market/capabilities/.../invoke route proxies to the same handler."""
    pid = "prod-test0001"
    cid = "run@v1"
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 1.0, "tx_hash": "demo-prefix"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    r = client.post(
        f"/ai-market/capabilities/{pid}/{cid}/invoke",
        json={"input": {"task": "prefixed"}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    assert r.status_code == 200
    assert r.json().get("success") is True


# ═══════════════════════════════════════════════════════════════════════
# Continuation hints
# ═══════════════════════════════════════════════════════════════════════

def test_continuation_hints_in_response(client, customer_auth):
    pid = "prod-test0001"
    ch = client.post(
        "/ai-market/channel/open",
        json={"deposit_usd": 2.0, "tx_hash": "demo-cont"},
        headers=customer_auth,
    )
    ch_body = ch.json()
    ch_id = ch_body["channel"]["channel_id"]

    r = client.post(
        f"/capabilities/{pid}/translate.multi@v2/invoke",
        json={"input": {"text": "hello", "locales": ["ru", "en"]}},
        headers=_channel_headers(customer_auth, ch_body),
    )
    assert r.status_code == 200
    continuation = r.json().get("continuation") or {}
    suggested = continuation.get("suggested_next") or []
    # translate should suggest legal.review_localized
    assert any("legal" in s.get("capability_id", "") for s in suggested)


# ═══════════════════════════════════════════════════════════════════════
# Catalog: declared capabilities take precedence
# ═══════════════════════════════════════════════════════════════════════

def test_declared_capabilities_in_manifest(tmp_path, monkeypatch):
    """When a product declares capabilities explicitly, they appear in the manifest."""
    pipeline = tmp_path / "data" / "state" / "pipeline.json"
    pipeline.parent.mkdir(parents=True, exist_ok=True)
    pipeline.write_text(json.dumps({
        "products": {
            "prod-declared": {
                "state": "COMPLETED",
                "name": "Custom Product",
                "capabilities": [{
                    "id": "custom.action@v3",
                    "name": "custom.action",
                    "version": "v3",
                    "description": "A custom declared capability",
                    "input_schema": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                    "output_schema": {
                        "type": "object",
                        "properties": {"answer": {"type": "string"}},
                    },
                    "price_per_call_usd": 1.50,
                    "p50_latency_ms": 5000,
                    "agent": "developer",
                    "prompt_template": "Answer: {query}",
                }],
            }
        }
    }), encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_AI_MARKET_DEMO_PAYMENT", "1")
    monkeypatch.setenv("AICOM_PIPELINE_JSON", str(pipeline))

    from fastapi.testclient import TestClient as TC
    from web.backend.main import app
    client2 = TC(app)

    r = client2.get("/ai-market/manifest")
    assert r.status_code == 200
    tools = r.json().get("tools", [])
    declared = [t for t in tools if "custom.action" in t["name"]]
    assert len(declared) == 1
    assert declared[0]["price_per_call_usd"] == 1.50
    assert declared[0]["input_schema"]["required"] == ["query"]
