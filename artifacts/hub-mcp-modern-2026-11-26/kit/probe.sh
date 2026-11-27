#!/usr/bin/env bash
# probe.sh URL — one MCP endpoint from outside, in both eras: server/discover and tools/list as an
# MCP 2026-07-28 client sends them (no handshake), then the initialize handshake.
set -euo pipefail
U="$1"; T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
M='{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientInfo":{"name":"rollout-probe","version":"1"},"io.modelcontextprotocol/clientCapabilities":{}}'
post() { # post NAME METHOD BODY [extra curl args]
  local name="$1" method="$2" body="$3"; shift 3
  curl -sS --max-time 20 -D "$T/$name.h" -o "$T/$name.body" -w "$method HTTP %{http_code} %{content_type}\n" -X POST "$U" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' "$@" -d "$body"
}
post discover server/discover "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"server/discover\",\"params\":{\"_meta\":$M}}" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: server/discover'
post list tools/list "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/list\",\"params\":{\"_meta\":$M}}" \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/list'
post init initialize '{"jsonrpc":"2.0","id":3,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"rollout-probe","version":"1"}}}'
python3 - "$T" <<'P'
import json, sys
from pathlib import Path
T = Path(sys.argv[1])
def body(name):
    text = (T / f"{name}.body").read_text()
    data = [line[5:] for line in text.splitlines() if line.startswith("data:")]
    try:
        return json.loads(data[0] if data else text)
    except ValueError:
        return {"unparsed": text[:120]}
d = body("discover"); r = d.get("result")
print("  discover:", (r.get("supportedVersions"), r.get("_meta", {}).get("io.modelcontextprotocol/serverInfo"),
                      r.get("resultType"), r.get("ttlMs"), r.get("cacheScope")) if r else json.dumps(d)[:160])
l = body("list").get("result") or {}
print("  tools/list:", len(l.get("tools", [])), "tools", l.get("resultType"), l.get("ttlMs"), l.get("cacheScope"))
i = body("init").get("result") or {}
session = "mcp-session-id" in (T / "init.h").read_text().lower()
print("  initialize:", i.get("protocolVersion"), i.get("serverInfo"), "session" if session else "no session")
P
