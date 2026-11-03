"""Smoke for the handshake overlay, run inside the new image: the fallback rules on a mock transport, then four
public endpoints that prod failed on since 2026-10-29 (read-only: discover/initialize/tools/list, as every crawl)."""
import json

import httpx

from histor import mcpclient
from histor.mcpclient import McpReader

assert hasattr(mcpclient, "_offers_legacy") and 401 in mcpclient._PROBE_HTTP_STATUSES, mcpclient.__file__
TOOL = {"name": "old", "description": "d", "inputSchema": {"type": "object"}}


def legacy_after(first):
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body["method"])
        if body["method"] == "server/discover":
            return first(body)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fx", "version": "1"}}})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [TOOL]}})
    return handle, calls


def observe(handle):
    return McpReader(timeout=5, allow_private=True, transport=httpx.MockTransport(handle)).list_tools("https://127.0.0.1/mcp")


cases = {
    "401 on discover": lambda b: httpx.Response(401, json={"errorMessages": ["token"]}),
    "legacy code, id server-error": lambda b: httpx.Response(400, json={"jsonrpc": "2.0", "id": "server-error",
                                                                         "error": {"code": -32600, "message": "x"}}),
    "not JSON-RPC": lambda b: httpx.Response(400, json={"error": "Bad Request"}),
    "-32022 legacy only": lambda b: httpx.Response(400, json={"jsonrpc": "2.0", "id": b["id"], "error": {
        "code": -32022, "data": {"supported": ["2025-06-18"]}}}),
    "not a DiscoverResult": lambda b: httpx.Response(200, json={"jsonrpc": "2.0", "id": b["id"], "result": {"isError": True}}),
}
for name, first in cases.items():
    handle, calls = legacy_after(first)
    obs = observe(handle)
    assert obs.status == "ok" and calls == ["server/discover", "initialize", "notifications/initialized", "tools/list"], (name, obs, calls)
for name, first in {"-32021 ours": lambda b: httpx.Response(400, json={"jsonrpc": "2.0", "id": b["id"], "error": {"code": -32021}}),
                    "429": lambda b: httpx.Response(429)}.items():
    handle, calls = legacy_after(first)
    obs = observe(handle)
    assert obs.status != "ok" and calls == ["server/discover"], (name, obs, calls)
print("mock: 5 legacy refusals fall back once, a modern error and a 429 still stop")

reader = McpReader(timeout=20)
for url in ("https://mcp.kaiku.tech/mcp", "https://mcp.quotewise.io/", "https://nova.civai.co/mcp/agents/telegram-agent",
            "https://marx.finance/mcp"):
    obs = reader.list_tools(url)
    print(f"live {url}: {obs.status} {obs.protocol_version} tools={len(obs.tools or [])} {obs.detail[:60]}")
    assert obs.status == "ok" and obs.tools, url
print("SMOKE OK")
