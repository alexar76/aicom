"""read_eras.py OUT_DIR NAME=ENDPOINT ... — does one MCP server list the same tools in every protocol era?

For each endpoint: one read per mode, each on a fresh connection, read-only (discover / initialize + tools/list,
never a tool call), with our own client identity. Modes:

  modern          server/discover, then tools/list with the 2026-07-28 per-request _meta (how HISTOR reads a
                  server that answers server/discover)
  hs-<version>    initialize asking <version>, notifications/initialized, tools/list with the session and the
                  negotiated version in MCP-Protocol-Version (how a handshake client reads)

Prints, per mode, the negotiated version, the number of tools and the mcp-tool-set-digest/1 contract digest
(HISTOR's own implementation, histor.subject.tool_set_digest), and saves every raw tools/list result.
"""
import json, sys, time, urllib.error, urllib.request
from pathlib import Path

from histor.subject import tool_set_digest

UA = "histor-peer-check/1 (+https://histor.modelmarket.dev/#crawler; read-only: discover + tools/list; alexar76/histor#13)"
MODERN = "2026-07-28"
META = {"io.modelcontextprotocol/protocolVersion": MODERN,
        "io.modelcontextprotocol/clientInfo": {"name": "histor-peer-check", "version": "1"},
        "io.modelcontextprotocol/clientCapabilities": {}}
HANDSHAKES = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")


def post(url, message, headers):
    body = json.dumps(message).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": UA, **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw, status, hdrs = r.read(4_000_000).decode("utf-8", "replace"), r.status, r.headers
    except urllib.error.HTTPError as e:
        raw, status, hdrs = e.read(200_000).decode("utf-8", "replace"), e.code, e.headers
    reply = None
    if "id" in message:
        want = message["id"]
        candidates = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")] or [raw]
        for text in candidates:
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict) and parsed.get("id") == want:
                reply = parsed
    return status, hdrs, reply


def list_all(url, headers, meta=None):
    tools, cursor, pages = [], None, 0
    while pages < 20:
        params = {}
        if cursor:
            params["cursor"] = cursor
        if meta is not None:
            params["_meta"] = meta
        status, _, reply = post(url, {"jsonrpc": "2.0", "id": 10 + pages, "method": "tools/list", "params": params}, headers)
        if not reply or "result" not in reply:
            return None, f"tools/list HTTP {status}: {json.dumps((reply or {}).get('error'))[:120]}", pages
        tools += reply["result"].get("tools") or []
        pages += 1
        cursor = reply["result"].get("nextCursor")
        if not cursor:
            break
    return tools, None, pages


def read(url, mode):
    if mode == "modern":
        h = {"MCP-Protocol-Version": MODERN}
        status, _, reply = post(url, {"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": META}},
                                {**h, "Mcp-Method": "server/discover"})
        if not reply or "result" not in reply:
            return {"mode": mode, "error": f"server/discover HTTP {status}: {json.dumps((reply or {}).get('error'))[:120]}"}
        tools, err, pages = list_all(url, {**h, "Mcp-Method": "tools/list"}, META)
        negotiated = MODERN
    else:
        asked = mode[3:]
        status, hdrs, reply = post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": asked, "capabilities": {}, "clientInfo": {"name": "histor-peer-check", "version": "1"}}}, {})
        if not reply or "result" not in reply:
            return {"mode": mode, "error": f"initialize HTTP {status}: {json.dumps((reply or {}).get('error'))[:120]}"}
        negotiated = reply["result"].get("protocolVersion")
        h = {"MCP-Protocol-Version": negotiated or asked}
        if hdrs.get("mcp-session-id"):
            h["Mcp-Session-Id"] = hdrs.get("mcp-session-id")
        post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, h)
        tools, err, pages = list_all(url, h)
    if err:
        return {"mode": mode, "negotiated": negotiated, "error": err}
    try:
        digest, _ = tool_set_digest(tools)
    except Exception as exc:                        # not digestible: say why
        digest = f"undigestible: {exc}"
    return {"mode": mode, "negotiated": negotiated, "tools": len(tools), "pages": pages, "digest": digest, "raw": tools}


if __name__ == "__main__":
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    summary = []
    for spec in sys.argv[2:]:
        name, url = spec.split("=", 1)
        print(f"== {name}  {url}")
        rows = []
        for mode in ("modern", *("hs-" + v for v in HANDSHAKES)):
            r = read(url, mode)
            raw = r.pop("raw", None)
            if raw is not None:
                (out / f"{name.replace('/', '__')}.{mode}.tools.json").write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n")
            r["read_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            print(f"   {mode:14} negotiated {r.get('negotiated')}  tools {r.get('tools')}  {r.get('digest') or r.get('error')}")
            rows.append(r)
            time.sleep(1)
        summary.append({"name": name, "endpoint": url, "reads": rows})
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
