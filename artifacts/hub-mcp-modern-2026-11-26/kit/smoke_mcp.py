"""Smoke a hub image's MCP gateway in both protocol eras (MCP 2026-07-28 change, 2026-11-26).

Run inside the image with no network, on a fresh throw-away SQLite database: the change adds no
migration and touches no stored data, so no copy of the live database is needed. Prints one JSON
line; any failed check raises.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
os.chdir(TMP)
HUB = "https://smoke-hub.example"
os.environ.update({"AIMARKET_DB_PATH": str(TMP / "hub.db"), "AIMARKET_AUTO_CRAWL": "0",
                   "AIMARKET_FEDERATION_ASSAY": "0", "AIMARKET_SIGNING_KEY_PATH": str(TMP / "smoke.key"),
                   "AIMARKET_HUB_URL": HUB})
sys.path.insert(0, "/app")
import aimarket_hub  # noqa: E402

assert aimarket_hub.__file__.startswith(os.environ.get("SMOKE_EXPECT_PKG", "/app/aimarket_hub/")), aimarket_hub.__file__

from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub import mcp_gateway, mcp_modern  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

V = "2026-07-28"
META = {mcp_modern.META_PROTOCOL: V, mcp_modern.META_CLIENT_INFO: {"name": "smoke", "version": "1"},
        mcp_modern.META_CAPABILITIES: {}}


def sse(response):
    return json.loads(next(line for line in response.text.splitlines() if line.startswith("data:"))[5:])


config = HubConfig()
config.hub_url = HUB
config.db_path = str(TMP / "hub.db")
db = HubDatabase(config.db_path)
report = {"package_version": aimarket_hub.__version__, "mcp_server": mcp_gateway.SERVER_VERSION}
with TestClient(create_app(config=config, db=db, signer=Signer(str(TMP / "smoke.key")))) as client:
    assert client.get("/ai-market/v2/health").status_code == 200

    def old(method, params=None, headers=None):
        return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
                           headers={"Accept": "application/json, text/event-stream", **(headers or {})})

    def new(method, params=None, headers=None, meta=META):
        sent = {"MCP-Protocol-Version": V, "Mcp-Method": method, **(headers or {})}
        body = dict(params or {})
        if meta is not None:
            body["_meta"] = meta
        if method == "tools/call":
            sent.setdefault("Mcp-Name", body["name"])
        return client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": body}, headers=sent)

    # The handshake era, as before.
    init = old("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "smoke", "version": "1"}})
    assert init.status_code == 200 and init.headers["content-type"].startswith("text/event-stream"), init.status_code
    assert init.headers.get("mcp-session-id")
    assert sse(init)["result"]["protocolVersion"] == "2025-06-18"
    legacy_tools = sse(old("tools/list", headers={"MCP-Protocol-Version": "2025-06-18"}))["result"]
    assert "resultType" not in legacy_tools and legacy_tools["tools"]
    assert sse(old("ping"))["result"] == {}
    report["tools"] = len(legacy_tools["tools"])

    # 2026-07-28: no handshake.
    found = new("server/discover")
    assert found.status_code == 200 and found.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in found.headers
    result = found.json()["result"]
    assert result["supportedVersions"][0] == V and "2025-06-18" in result["supportedVersions"], result
    assert result["resultType"] == "complete" and result["ttlMs"] > 0 and result["cacheScope"] == "public"
    assert result["_meta"][mcp_modern.META_SERVER_INFO]["version"] == mcp_gateway.SERVER_VERSION
    report["supportedVersions"] = result["supportedVersions"]
    listed = new("tools/list").json()["result"]
    assert listed["tools"] == legacy_tools["tools"] and listed["resultType"] == "complete"
    called = new("tools/call", {"name": "market_search", "arguments": {"intent": "weather"}})
    assert called.status_code == 200 and called.json()["result"]["resultType"] == "complete", called.text[:300]

    # What the revision makes a server refuse.
    bad = new("tools/list", headers={"MCP-Protocol-Version": "2026-07-29"})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == mcp_modern.HEADER_MISMATCH
    future = new("tools/list", headers={"MCP-Protocol-Version": "2027-01-01"}, meta={**META, mcp_modern.META_PROTOCOL: "2027-01-01"})
    assert future.status_code == 400 and future.json()["error"]["code"] == mcp_modern.UNSUPPORTED_PROTOCOL_VERSION
    assert future.json()["error"]["data"]["supported"] == result["supportedVersions"]
    gone = new("initialize")
    assert gone.status_code == 404 and gone.json()["error"]["code"] == -32601

    # The documents that state the versions.
    assert client.get("/mcp").json()["protocol_versions"] == result["supportedVersions"]
    card = client.get("/.well-known/mcp/server-card.json")
    assert card.status_code == 200 and card.json()["serverInfo"]["version"] == mcp_gateway.SERVER_VERSION
    sep = client.get("/mcp/server-card")      # the SEP-2127 card the AI Catalog entry points to
    assert sep.status_code == 200 and all(f'"{v}"' in sep.text for v in result["supportedVersions"]), sep.text[-400:]
    assert client.get("/.well-known/ai-catalog.json").status_code == 200
print(json.dumps(report))
