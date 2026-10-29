"""Isolate HISTOR's legacy lifecycle against three in-memory HTTP fixtures.

This is a lifecycle probe, not a complete MCP conformance suite. No network
connection, package execution, tool invocation or production mutation occurs.
Run with histor/.venv/bin/python from the aicom workspace.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "histor"))

import httpx  # noqa: E402
from histor.mcpclient import McpReader  # noqa: E402

URL = "https://127.0.0.1/mcp"
TOOL = {"name": "fixture_read", "description": "Synthetic read-only fixture", "inputSchema": {"type": "object"}}
MODERN = "2026-07-28"
LEGACY = "2025-06-18"


def fixture(era: str, calls: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body["method"]
        calls.append({"method": method, "protocol_header": request.headers.get("MCP-Protocol-Version"),
                      "method_header": request.headers.get("Mcp-Method")})
        if era == "modern_only":
            meta = body.get("params", {}).get("_meta", {})
            accepted = {part.strip() for part in request.headers.get("Accept", "").split(",")}
            if (method == "initialize" or request.headers.get("Mcp-Method") != method
                    or request.headers.get("MCP-Protocol-Version") != MODERN
                    or meta.get("io.modelcontextprotocol/protocolVersion") != MODERN
                    or not isinstance(meta.get("io.modelcontextprotocol/clientCapabilities"), dict)
                    or not {"application/json", "text/event-stream"}.issubset(accepted)):
                return httpx.Response(400, json={"jsonrpc": "2.0", "id": body.get("id"),
                    "error": {"code": -32600, "message": "Fixture requires modern request metadata", "data": {"supported": [MODERN]}}})
            if method == "tools/list":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"],
                    "result": {"resultType": "complete", "ttlMs": 0, "cacheScope": "public", "tools": [TOOL]}})
        elif method == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {
                "protocolVersion": LEGACY, "capabilities": {"tools": {}},
                "serverInfo": {"name": f"fixture-{era}", "version": "1.0"}}})
        elif method == "notifications/initialized":
            return httpx.Response(202)
        elif method == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [TOOL]}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"),
            "error": {"code": -32601, "message": "Method outside this fixture"}})
    return handler


def main() -> None:
    cases = []
    for era in ("legacy_only", "dual_era_legacy_branch", "modern_only"):
        calls: list[dict] = []
        obs = McpReader(timeout=2, allow_private=True,
                        transport=httpx.MockTransport(fixture(era, calls))).list_tools(URL)
        cases.append({"fixture": era, "status": obs.status, "detail": obs.detail,
                      "tools_observed": len(obs.tools or []), "calls": calls})
    modern_calls: list[dict] = []
    with httpx.Client(transport=httpx.MockTransport(fixture("modern_only", modern_calls))) as client:
        headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/list",
                   "Accept": "application/json, text/event-stream"}
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {
                "io.modelcontextprotocol/protocolVersion": MODERN,
                "io.modelcontextprotocol/clientCapabilities": {}}}}
        response = client.post(URL, headers=headers, json=body)
        missing_accept = client.post(URL, headers={**headers, "Accept": "*/*"}, json=body)
        no_capabilities = json.loads(json.dumps(body))
        del no_capabilities["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"]
        missing_capabilities = client.post(URL, headers=headers, json=no_capabilities)
    control = {"http_status": response.status_code, "tools_observed": len(response.json()["result"]["tools"]),
               "calls": modern_calls, "missing_accept_status": missing_accept.status_code,
               "missing_client_capabilities_status": missing_capabilities.status_code}
    assert [case["status"] for case in cases] == ["ok", "ok", "http-400"]
    assert control["http_status"] == 200 and control["tools_observed"] == 1
    assert control["missing_accept_status"] == 400 and control["missing_client_capabilities_status"] == 400
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "scope": "in-memory lifecycle fixtures only",
        "implementation": "histor/histor/mcpclient.py",
        "implementation_sha256": hashlib.sha256((ROOT / "histor/histor/mcpclient.py").read_bytes()).hexdigest(),
        "specification": "https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning",
        "cases": cases, "modern_request_control": control,
        "limitations": ["Does not measure prevalence of modern-only servers or production availability",
                        "Dual-era case exercises its legacy branch only",
                        "The synthetic modern fixture is not a full MCP server or conformance test"]}
    target = Path(__file__).with_name("compatibility-probe.json")
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"evidence": str(target), "case_statuses": [case["status"] for case in cases],
                      "modern_control": control["http_status"]}))


if __name__ == "__main__":
    main()
