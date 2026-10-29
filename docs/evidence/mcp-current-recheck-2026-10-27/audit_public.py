"""Read-only registry and remote MCP checks; never invokes an advertised tool."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
UA = "alexar76-ecosystem-mcp-audit/2026-10-27"


def fetch(url, *, data=None, headers=None, method=None):
    request = urllib.request.Request(url, data=data, method=method,
                                    headers={"User-Agent": UA, **(headers or {})})
    try:
        response = urllib.request.urlopen(request, timeout=25)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        status, response_headers = response.status, dict(response.headers)
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            lines, size = [], 0
            while True:
                line = response.readline()
                size += len(line)
                if size > 2_000_000:
                    raise ValueError("oversized SSE response")
                if not line or not line.strip():
                    break
                lines.append(line.decode())
            body = "".join(lines)
        else:
            body = response.read(2_000_001).decode()
            if len(body) > 2_000_000:
                raise ValueError("oversized response")
    return status, response_headers, body


def registry(item):
    kind, name = item
    url = (f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='')}/latest"
           if kind == "npm" else f"https://pypi.org/pypi/{name}/json")
    status, _, body = fetch(url)
    if status != 200:
        return {"registry": kind, "name": name, "http": status}
    metadata = json.loads(body)
    (ROOT / (name.replace('@', '').replace('/', '-') + '-registry.json')).write_text(
        json.dumps(metadata, indent=2) + "\n")
    info = metadata if kind == "npm" else metadata["info"]
    return {"registry": kind, "name": name, "version": info["version"],
            "bin": info.get("bin"), "requires": info.get("requires_dist"),
            "url": url}


def parse_rpc(body):
    if body.startswith(("event:", "data:", "id:")):
        body = "\n".join(line[5:].lstrip() for line in body.splitlines()
                         if line.startswith("data:"))
    return json.loads(body) if body.strip() else None


def remote(url):
    record = {"url": url, "startedAt": datetime.now(timezone.utc).isoformat(),
              "requests": [], "toolCalls": 0}
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}

    def post(message):
        assert message["method"] in {"initialize", "notifications/initialized", "tools/list", "ping"}
        status, returned, body = fetch(url, data=json.dumps(message).encode(), headers=headers)
        reply = parse_rpc(body)
        record["requests"].append({"sent": message, "status": status,
                                   "contentType": returned.get("Content-Type", returned.get("content-type")),
                                   "reply": reply})
        for key, value in returned.items():
            if key.lower() == "mcp-session-id":
                headers["Mcp-Session-Id"] = value
        return status, reply

    try:
        status, reply = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": UA, "version": "1.0"}}})
        if status != 200 or not reply or "result" not in reply:
            raise ValueError(f"initialize failed: HTTP {status}")
        result = reply["result"]
        record["serverInfo"] = result.get("serverInfo")
        record["protocol"] = result["protocolVersion"]
        headers["MCP-Protocol-Version"] = record["protocol"]
        status, reply = post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        record["notificationAccepted"] = status == 202 and reply is None
        tools, cursors = [], set()
        for page in range(32):
            params = {"cursor": cursor} if page else {}
            status, reply = post({"jsonrpc": "2.0", "id": page + 2, "method": "tools/list", "params": params})
            if status != 200 or not reply or "result" not in reply:
                raise ValueError(f"tools/list failed: HTTP {status}")
            tools.extend(reply["result"]["tools"])
            cursor = reply["result"].get("nextCursor")
            if not cursor:
                break
            if cursor in cursors:
                raise ValueError("repeated pagination cursor")
            cursors.add(cursor)
        else:
            raise ValueError("too many tool pages")
        record["tools"] = tools
        record["status"] = "ok"
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if "Mcp-Session-Id" in headers:
            try:
                record["sessionCleanupHttp"] = fetch(url, headers=headers, method="DELETE")[0]
            except Exception as exc:
                record["cleanupError"] = str(exc)
    return record


if __name__ == "__main__":
    if sys.argv[1:] == ["registries"]:
        items = [("npm", "@alexar76/argus3"), ("npm", "argus-warden"),
                 ("npm", "@aimarket/warden"), ("pypi", "aimarket-mcp"),
                 ("pypi", "aimarket-hub"), ("pypi", "aimarket-histor"),
                 ("pypi", "aimarket-mcp-packager"), ("pypi", "aimarket-oracle-gateway")]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(registry, items))
        (ROOT / "registry-inventory.json").write_text(json.dumps(results, indent=2) + "\n")
        schema_url = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
        (ROOT / "registry-server.schema.json").write_text(fetch(schema_url)[2])
        for result in results:
            print(result["name"], result.get("version", result.get("http")))
    elif sys.argv[1:] == ["remotes"]:
        urls = {"https://modelmarket.dev/mcp", "https://modelmarket.dev/ai-market/mcp",
                "https://mcp.modelmarket.dev/mcp", "https://hub.attestedmemory.net/mcp",
                "https://independentai.network/hub/mcp"}
        for profile in ("security", "weather", "domains", "emporion"):
            urls.add(f"https://modelmarket.dev/tools/mcp/{profile}")
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(remote, sorted(urls)))
        (ROOT / "remote-probes.json").write_text(json.dumps(results, indent=2) + "\n")
        for result in results:
            print(result["url"], result["status"], len(result.get("tools", [])), result.get("error", ""))
    else:
        raise SystemExit("usage: audit_public.py registries|remotes")
