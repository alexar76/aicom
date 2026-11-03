"""The stranger's path through https://modelmarket.dev/mcp, walked on 2026-09-25.

Over 15 days ~240 foreign MCP clients fetched tools/list and two called a tool. Walking
the path as an outsider showed where it broke: ``initialize`` said nothing about what the
server is for; tools/list offered only two abstract tools; search results carried no
input fields and cut descriptions mid-word; a result was 9.3 KB, 7 KB of it ML-DSA
signature; after the trial the 402 named rails an MCP client cannot use; standard setup
probes (prompts/list, resources/templates/list) answered -32601. Each test here pins one
of those fixes. The helpers are the gateway suite's own, so both suites exercise the same
app wiring.
"""

from __future__ import annotations

import json

import httpx
import pytest

from aimarket_hub.mcp_gateway import (
    DIRECT_TOOLS,
    INSTRUCTIONS,
    SUPPORTED_PROTOCOL_VERSIONS,
    _clip,
    _render_invoke,
    _schema_hint,
    client_family,
)
from aimarket_hub.models import Capability
from tests.test_mcp_gateway import PROXY, _FakeResponse, _call, _hub_client, _rpc, _sse

PQ_KEY = "K" * 2604
PQ_SIG = "S" * 4412


def _signed_body() -> dict:
    return {
        "ok": True,
        "capability_id": "gaia.weather.read@v1",
        "output": {"reading": {"device_id": "om-wx-01", "values": {"temperature_c": 14.5}},
                   "attestation": {"algorithm": "ed25519", "value": "a" * 88}},
        "price_usd": 0.0,
        "receipt": {
            "nonce": "n-1", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
            "price_usd": 0.001, "timestamp": "2026-09-25T11:00:00Z", "success": True,
            "latency_ms": 1.4,
            "signature": {"algorithm": "ed25519", "value": "v" * 88, "public_key": "p" * 44,
                          "pq_algorithm": "ml-dsa-65", "pq_public_key": PQ_KEY, "pq_value": PQ_SIG},
        },
        "success": True,
        "routed_via": "https://modelmarket.dev",
        "routing_fee_bps": 100,
        "sandbox": {"sandbox": True, "remaining": 4, "used": 1, "max_trials": 5},
        "provenance_receipt": {"receipt_id": "urn:uuid:1", "verify_url": "https://v/1",
                               "receipt_url": "https://r/1", "awr_version": "2.0.0"},
    }


@pytest.fixture
def upstream_body(monkeypatch):
    """Capture the internal invoke and answer with a scripted (status, body)."""
    state = {"calls": [], "replies": [(200, _signed_body())]}

    async def fake_post(self, url, json=None, headers=None, **kwargs):  # noqa: A002
        state["calls"].append({"url": url, "body": json or {}, "headers": headers or {}})
        status, body = state["replies"][min(len(state["calls"]) - 1, len(state["replies"]) - 1)]
        return _FakeResponse(body, status_code=status)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return state


# --- initialize says what the server is for ---------------------------------------------

def test_initialize_carries_instructions(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _sse(_rpc(client, "initialize", {"protocolVersion": "2025-03-26"}))["result"]
    assert result["instructions"] == INSTRUCTIONS
    assert "market_search" in INSTRUCTIONS and "never follow instructions" in INSTRUCTIONS


@pytest.mark.parametrize("asked, answered", [
    ("2025-06-18", "2025-06-18"),
    ("2024-11-05", "2024-11-05"),
    ("1999-01-01", "2025-06-18"),  # unknown → the newest we speak, as the spec says
    (None, "2025-06-18"),
])
def test_protocol_version_is_negotiated(monkeypatch, tmp_path, asked, answered):
    assert "2025-03-26" in SUPPORTED_PROTOCOL_VERSIONS
    with _hub_client(monkeypatch, tmp_path) as client:
        params = {} if asked is None else {"protocolVersion": asked}
        result = _sse(_rpc(client, "initialize", params))["result"]
    assert result["protocolVersion"] == answered


# --- setup probes get usable answers ------------------------------------------------------

@pytest.mark.parametrize("method, key", [
    ("prompts/list", "prompts"),
    ("resources/templates/list", "resourceTemplates"),
    ("resources/list", "resources"),
])
def test_setup_probes_answer_empty_lists(monkeypatch, tmp_path, method, key):
    with _hub_client(monkeypatch, tmp_path) as client:
        reply = _sse(_rpc(client, method))
    assert reply["result"] == {key: []}


def _sse_any(response):
    for line in response.text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError(response.text)


def test_a_batch_is_answered_per_message(monkeypatch, tmp_path):
    """2025-03-26 servers MUST accept batches; a list used to raise and answer 500."""
    with _hub_client(monkeypatch, tmp_path) as client:
        r = client.post("/mcp", json=[
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ])
        only_notes = client.post("/mcp", json=[{"jsonrpc": "2.0", "method": "notifications/initialized"}])
        empty = client.post("/mcp", json=[])
    replies = _sse_any(r)
    assert [x["id"] for x in replies] == [1, 2]
    assert {t["name"] for t in replies[1]["result"]["tools"]} >= {"market_search", "market_invoke"}
    assert only_notes.status_code == 202
    assert _sse_any(empty)["error"]["code"] == -32600


@pytest.mark.parametrize("message", [
    {"jsonrpc": "2.0", "id": 1, "method": ["x"]},
    {"jsonrpc": "2.0", "id": 1, "method": {}},
    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": ["x"]}},
    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": {"a": 1}}},
    {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": ["not", "a", "dict"]},
])
def test_odd_shapes_get_json_rpc_errors_not_a_500(monkeypatch, tmp_path, message):
    with _hub_client(monkeypatch, tmp_path) as client:
        r = client.post("/mcp", json=message)
    assert r.status_code == 200
    assert _sse(r)["error"]["code"] in (-32601, -32602)


# --- direct tools ---------------------------------------------------------------------------

def _seed_direct(monkeypatch, tmp_path):
    """A hub whose catalogue carries weather_now's capability on a live peer."""
    from aimarket_hub.models import Peer
    import tests.test_mcp_gateway as base

    original = base.HubDatabase

    class _Seeded(original):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.upsert_peer(Peer(url="https://iot.modelmarket.dev", name="GAIA"), status="active")
            self.upsert_capability(Capability(
                capability_id="gaia.weather.read@v1", product_id="gaia.gateway",
                name="gaia.weather.read", description="Current weather at a place.",
                price_per_call_usd=0.001, source_hub="https://iot.modelmarket.dev",
                source_hub_name="GAIA", trust_score=0.5,
            ))

    monkeypatch.setattr(base, "HubDatabase", _Seeded)


def test_direct_tools_are_listed_only_when_routable(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path) as client:
        plain = {t["name"] for t in _sse(_rpc(client, "tools/list"))["result"]["tools"]}
    assert plain == {"market_search", "market_invoke", "pipeline_prepare", "pipeline_invoke", "pipeline_status", "pipeline_refund_prepare", "pipeline_refund", "pipeline_refund_status"}, "no catalogue row, no direct tool"

    _seed_direct(monkeypatch, tmp_path)
    with _hub_client(monkeypatch, tmp_path) as client:
        tools = {t["name"]: t for t in _sse(_rpc(client, "tools/list"))["result"]["tools"]}
        info = client.get("/mcp").json()
    assert "weather_now" in tools
    assert {"air_quality_now", "nearby_sensors", "fair_random"}.isdisjoint(tools)
    assert "$0.001 per call" in tools["weather_now"]["description"]
    assert set(tools["weather_now"]["inputSchema"]["properties"]) == {"latitude", "longitude", "city"}
    assert info["direct_tools"] == ["weather_now"]
    assert set(info["tools"]) == {"market_search", "market_invoke", "pipeline_prepare", "pipeline_invoke", "pipeline_status", "pipeline_refund_prepare", "pipeline_refund", "pipeline_refund_status"}


def test_a_direct_tool_calls_its_capability_through_the_trial(monkeypatch, tmp_path, upstream_body):
    _seed_direct(monkeypatch, tmp_path)
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _call(client, "weather_now", {"city": "Berlin"}, headers={"X-Forwarded-For": "198.51.100.7"})["result"]
    assert result["isError"] is False
    sent = upstream_body["calls"][0]
    assert sent["body"] == {"product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
                            "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}}
    assert sent["headers"]["X-AIMarket-Sandbox-Visitor"].startswith("mcpx-")


def test_direct_tool_arguments_are_checked_before_any_call(monkeypatch, tmp_path, upstream_body):
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _call(client, "fair_random", {})["result"]
    assert result["isError"] is True
    assert "seed" in result["content"][0]["text"]
    assert upstream_body["calls"] == []


def test_direct_tool_names_are_protocol_safe():
    import re

    for spec in DIRECT_TOOLS:
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", spec["name"])
        assert len(spec["summary"]) < 400


# --- search gives what a call needs ---------------------------------------------------------

def test_search_matches_carry_input_fields(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path) as client:
        text = _call(client, "market_search", {"intent": "weather"})["result"]["content"][0]["text"]
    gaia = next(m for m in json.loads(text)["matches"] if m["capability_id"] == "gaia.weather.read@v1")
    assert gaia["input"]["latitude"] == {"type": "number", "description": "Latitude in degrees."}
    assert gaia["input"]["city"] == {"type": "string"}


def test_search_description_is_cut_at_a_word_not_mid_word():
    text = "word " * 200
    clipped = _clip(text, 600)
    assert len(clipped) <= 601 and clipped.endswith("word…")
    assert _clip("short", 600) == "short"


def test_schema_hint_is_bounded_and_ignores_hostile_shapes():
    assert _schema_hint("not a schema") == {}
    assert _schema_hint({"properties": "nope"}) == {}
    hostile = {"properties": {f"f{i}": {"type": "string", "description": "x" * 5000} for i in range(40)},
               "required": "f0"}
    hint = _schema_hint(hostile)
    assert len(hint) == 12
    assert all(len(v["description"]) <= 161 for v in hint.values())
    assert "required" not in hint["f0"], "a bare-string `required` is not a list of names"


def test_search_ceiling_is_the_cent_ceiled_total(monkeypatch, tmp_path):
    with _hub_client(monkeypatch, tmp_path) as client:
        text = _call(client, "market_search", {"intent": "weather"})["result"]["content"][0]["text"]
    gaia = next(m for m in json.loads(text)["matches"] if m["capability_id"] == "gaia.weather.read@v1")
    # Pasting the list price used to fail every paid call on a fee-bearing route.
    assert gaia["max_price_usd"] >= gaia["price_per_call_usd"]
    assert round(gaia["max_price_usd"] * 100) == gaia["max_price_usd"] * 100


# --- a compact, verifiable result -------------------------------------------------------------

def test_invoke_result_is_compact_and_keeps_what_verifies(monkeypatch, tmp_path, upstream_body):
    with _hub_client(monkeypatch, tmp_path) as client:
        text = _call(client, "market_invoke", {"product_id": "prod-gaia", "capability_id": "gaia.weather.read@v1",
                                               "source_hub": "https://iot.modelmarket.dev"})["result"]["content"][0]["text"]
    assert len(text) < 2500, len(text)
    body = json.loads(text)
    assert body["output"]["reading"]["values"]["temperature_c"] == 14.5
    assert body["charged_usd"] == 0.0
    assert body["trial"] == {"remaining": 4, "used": 1, "max_trials": 5}
    sig = body["receipt"]["signature"]
    assert sig["value"] == "v" * 88 and sig["pq_value_omitted_chars"] == len(PQ_SIG)
    assert sig["pq_public_key_sha256"]
    assert "pq_value" not in text.replace("pq_value_omitted_chars", "")
    assert body["receipt"]["nonce"] == "n-1"
    assert "charged again" in body["note"], "the note must not invite a second paid call unawares"
    assert body["provenance_receipt"]["receipt_url"] == "https://r/1"
    assert "hub paid it, not you" in body["receipt"]["note"]


def test_the_full_receipt_is_one_flag_away(monkeypatch, tmp_path, upstream_body):
    with _hub_client(monkeypatch, tmp_path) as client:
        text = _call(client, "market_invoke", {"product_id": "prod-gaia", "capability_id": "gaia.weather.read@v1",
                                               "source_hub": "https://iot.modelmarket.dev",
                                               "include_full_receipt": True})["result"]["content"][0]["text"]
    assert json.loads(text)["receipt"]["signature"]["pq_value"] == PQ_SIG


def test_a_top_level_product_body_is_rendered_as_output():
    body = {"ok": True, "capability_id": "atlas.nearest.read@v1", "nearest_by_layer": {"weather": {"id": "om-wx-01"}},
            "hit_count": 1, "receipt": {"nonce": "n"}, "success": True, "price_usd": 0.0,
            "sandbox": {"sandbox": True, "remaining": 1}}
    out = json.loads(_render_invoke(body, status=200, is_error=False, full=False,
                                    capability_id="atlas.nearest.read@v1", source_hub="https://atlas", list_price=0.03))
    assert out["output"] == {"capability_id": "atlas.nearest.read@v1", "nearest_by_layer": {"weather": {"id": "om-wx-01"}},
                             "hit_count": 1}
    assert out["list_price_usd"] == 0.03


def test_a_refusal_does_not_claim_the_trial_was_spent():
    body = {"ok": False, "error": "needs a place", "sandbox": {"sandbox": True, "remaining": 2, "used": 3}}
    out = json.loads(_render_invoke(body, status=200, is_error=True, full=False,
                                    capability_id="c", source_hub="h", list_price=None))
    assert out["sandbox"]["trial_spent"] is False
    assert out["error"] == "needs a place"


# --- after the trial: what can actually be done ----------------------------------------------

def _payment_402() -> dict:
    return {
        "success": False, "error": "payment_required", "needed": 0.001, "price_usd": 0.001,
        "payment_ways": [
            {"rail": "seller_direct", "header": "X-Payment"},
            {"rail": "credits", "header": "X-API-Key", "open_signup": False},
            {"rail": "channel", "header": "X-Payment-Channel", "open": "https://h/ai-market/v2/channel/open"},
        ],
        "nonce": "0x" + "ab" * 32, "pay_to": "0x" + "12" * 20, "expires_at": 1790333586.7,
        "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "1000",
                     "asset": "0x" + "83" * 20, "extra": {"name": "USD Coin", "version": "2"}}],
    }


def test_a_402_leads_with_next_steps_and_keeps_its_fields(monkeypatch, tmp_path, upstream_body):
    upstream_body["replies"] = [(429, {"error": "trial_quota_exhausted"}), (402, _payment_402())]
    with _hub_client(monkeypatch, tmp_path, AIMARKET_TRUSTED_PROXIES=PROXY) as client:
        result = _call(client, "market_invoke", {"product_id": "prod-hub", "capability_id": "hub.echo@v1"},
                       headers={"X-Forwarded-For": "198.51.100.9"})["result"]
    assert result["isError"] is True
    body = json.loads(result["content"][0]["text"])
    assert list(body)[0] == "next_steps"
    assert body["error"] == "payment_required" and body["needed"] == 0.001 and body["trial_exhausted"] is True
    steps = " ".join(body["next_steps"])
    assert "x_payment_nonce=" + "0x" + "ab" * 32 in steps
    assert "operator only" in steps
    assert "budget=0" in steps
    retry = upstream_body["calls"][1]["headers"]
    assert "X-AIMarket-Sandbox-Visitor" not in retry
    assert retry["X-Forwarded-For"] == "198.51.100.9", "the retry must stay in the caller's own bucket"


def test_an_x402_payment_is_forwarded_and_skips_the_trial(monkeypatch, tmp_path, upstream_body):
    nonce = "0x" + "cd" * 32
    with _hub_client(monkeypatch, tmp_path) as client:
        _call(client, "market_invoke", {"product_id": "prod-hub", "capability_id": "hub.echo@v1",
                                        "x_payment": "0x" + "ef" * 32, "x_payment_nonce": nonce})
    headers = upstream_body["calls"][0]["headers"]
    assert headers["X-PAYMENT"] == "0x" + "ef" * 32
    assert headers["X-Payment-Nonce"] == nonce
    assert "X-AIMarket-Sandbox-Visitor" not in headers, "a payer is a customer, not a visitor"


def test_the_payment_secret_is_handed_to_the_caller_and_carried_back(monkeypatch, tmp_path, upstream_body):
    """The 402's nonce commits to a secret only its caller receives; redeeming must open it
    (the nonce and the transaction are public once mined). Over MCP the caller is whoever
    called market_invoke, so next_steps names the secret and the tool carries it back."""
    secret = "0x" + "5e" * 32
    upstream_body["replies"] = [(402, {**_payment_402(), "payment_secret": secret}), (200, _signed_body())]
    with _hub_client(monkeypatch, tmp_path) as client:
        first = _call(client, "market_invoke", {"product_id": "prod-hub", "capability_id": "hub.echo@v1",
                                                "x_payment": "0x" + "ef" * 32})["result"]
        steps = " ".join(json.loads(first["content"][0]["text"])["next_steps"])
        assert "x_payment_secret=" + secret in steps
        _call(client, "market_invoke", {"product_id": "prod-hub", "capability_id": "hub.echo@v1",
                                        "x_payment": "0x" + "ef" * 32, "x_payment_nonce": "0x" + "ab" * 32,
                                        "x_payment_secret": secret})
    assert upstream_body["calls"][-1]["headers"]["X-Payment-Secret"] == secret
    assert "X-Payment-Secret" not in upstream_body["calls"][0]["headers"]


@pytest.mark.parametrize("arguments, message", [
    ({"x_payment": "0x" + "ef" * 32, "payment_channel": "ch_1"}, "not both"),
    ({"x_payment": "0x" + "ef" * 32, "x_payment_secret": "hunter2"}, "payment_secret from the 402"),
    ({"x_payment": "0xabc\r\nX-Injected: 1"}, "transaction hash"),
    ({"x_payment": "x" * 9000}, "transaction hash"),
    ({"x_payment": "0x" + "ef" * 32, "x_payment_nonce": "not-a-nonce"}, "nonce"),
])
def test_bad_payment_arguments_fail_before_any_call(monkeypatch, tmp_path, upstream_body, arguments, message):
    with _hub_client(monkeypatch, tmp_path) as client:
        result = _call(client, "market_invoke", {"product_id": "prod-hub", "capability_id": "hub.echo@v1",
                                                 **arguments})["result"]
    assert result["isError"] is True
    assert message in result["content"][0]["text"]
    assert upstream_body["calls"] == []


# --- the funnel is counted ---------------------------------------------------------------------

def test_the_funnel_is_counted_by_client_family(monkeypatch, tmp_path):
    from aimarket_hub.metrics import mcp_requests_total

    def value(method, tool, client):
        return mcp_requests_total.labels(method, tool, client)._value.get()

    before = value("tools/list", "-", "claude-ai")
    with _hub_client(monkeypatch, tmp_path) as client:
        init = _rpc(client, "initialize", {"clientInfo": {"name": "claude-ai", "version": "0.1"}})
        sid = init.headers["mcp-session-id"]
        _rpc(client, "tools/list", headers={"Mcp-Session-Id": sid})
    assert value("tools/list", "-", "claude-ai") == before + 1


@pytest.mark.parametrize("name, family", [
    ("claude-ai", "claude-ai"), ("Cursor", "cursor"), ("Visual Studio Code", "vscode"),
    ("mcp-remote-fallback-test", "mcp-remote"), ("some unknown thing", "other"), ("", "unnamed"),
])
def test_client_family_is_an_allowlist(name, family):
    assert client_family({"name": name}) == family


def test_a_peer_declared_category_finds_its_capabilities(monkeypatch, tmp_path):
    """MOMUS declares category "security" in its well-known, but none of its ids or
    descriptions carry the token list the filter matched on — so category=security
    hid the ecosystem's own security auditor."""
    from aimarket_hub.models import Peer
    import tests.test_mcp_gateway as base

    original = base.HubDatabase

    class _WithMomus(original):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.upsert_peer(Peer(url="https://momus.example", name="MOMUS",
                                  categories=["security", "red-team"]), status="active")
            self.upsert_capability(Capability(
                capability_id="momus.intel@v1", product_id="momus.redteam", name="momus.intel",
                description="Distilled threat-intel cards from allowlisted public feeds.",
                price_per_call_usd=0.0, source_hub="https://momus.example", trust_score=0.5,
            ))

    monkeypatch.setattr(base, "HubDatabase", _WithMomus)
    with _hub_client(monkeypatch, tmp_path) as client:
        http = client.get("/ai-market/v2/search", params={"intent": "threat intel", "category": "security"}).json()
        mcp = json.loads(_call(client, "market_search", {"intent": "threat intel", "category": "security"})
                         ["result"]["content"][0]["text"])
    assert "momus.intel@v1" in {m["capability_id"] for m in http["matches"]}
    assert "momus.intel@v1" in {m["capability_id"] for m in mcp["matches"]}


def _seed_x402_check(monkeypatch, tmp_path):
    """A hub whose catalogue carries the HESTIA x402 check on a live peer."""
    from aimarket_hub.models import Peer
    import tests.test_mcp_gateway as base

    original = base.HubDatabase

    class _Seeded(original):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.upsert_peer(Peer(url="https://hestia.modelmarket.dev", name="HESTIA"), status="active")
            self.upsert_capability(Capability(
                capability_id="x402.authorization.check@v1", product_id="hestia-agents",
                name="x402.authorization.check", description="Checks a signed x402 payment.",
                price_per_call_usd=0.003, source_hub="https://hestia.modelmarket.dev",
                source_hub_name="HESTIA", trust_score=0.5,
            ))

    monkeypatch.setattr(base, "HubDatabase", _Seeded)


def test_x402_check_is_a_direct_tool_and_calls_the_hearth_agent(monkeypatch, tmp_path, upstream_body):
    _seed_x402_check(monkeypatch, tmp_path)
    auth = {"from": "0x" + "11" * 20, "to": "0x" + "22" * 20, "value": "3000", "validAfter": "0",
            "validBefore": "1893456000", "nonce": "0x" + "33" * 32}
    with _hub_client(monkeypatch, tmp_path) as client:
        tools = {t["name"]: t for t in _sse(_rpc(client, "tools/list"))["result"]["tools"]}
        assert "x402_check" in tools and "$0.003 per call" in tools["x402_check"]["description"]
        assert {"x_payment", "authorization", "signature", "network"} <= set(tools["x402_check"]["inputSchema"]["properties"])
        result = _call(client, "x402_check", {"authorization": auth, "signature": "0x" + "ab" * 65,
                                              "network": "base", "extra": "dropped"},
                       headers={"X-Forwarded-For": "198.51.100.9"})["result"]
    assert result["isError"] is False
    sent = upstream_body["calls"][0]["body"]
    assert sent["capability_id"] == "x402.authorization.check@v1"
    assert sent["source_hub"] == "https://hestia.modelmarket.dev"
    assert sent["input"] == {"authorization": auth, "signature": "0x" + "ab" * 65, "network": "base"}


def test_x402_check_refuses_an_empty_call_before_any_trial_is_spent(monkeypatch, tmp_path, upstream_body):
    _seed_x402_check(monkeypatch, tmp_path)
    with _hub_client(monkeypatch, tmp_path) as client:
        for args in ({}, {"requirements": {"payTo": "0x" + "22" * 20}}, {"authorization": {"from": "0x1"}}):
            result = _call(client, "x402_check", args)["result"]
            assert result["isError"] is True and "x_payment" in result["content"][0]["text"]
    assert upstream_body["calls"] == []
