"""Probe every remote MCP server from the registry once, without credentials: initialize + tools/list, nothing else.
No tool is ever called. Output: research/mcpscan/probe.json  {url: {status, tools, tool_names, ms, server_name, error}}
status: open (answered tools/list without auth), auth (401/403 or asks for a token), down (anything else).
usage: python3 tools/mcpscan/probe.py [workers=24]"""
import json, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "build"
UA = "free-remote-mcp-servers/1.0 (+https://github.com/diegobruegger-prog/free-remote-mcp-servers)"
HDR = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": UA, "MCP-Protocol-Version": "2025-06-18"}


def _post(url, msg, sid=None, timeout=10):
    h = dict(HDR)
    if sid:
        h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(url, data=json.dumps(msg).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read(400_000).decode("utf-8", "ignore")
        sid = r.headers.get("Mcp-Session-Id") or sid
        ctype = r.headers.get("Content-Type", "")
    if "text/event-stream" in ctype or body.lstrip().startswith(("event:", "data:")):
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    d = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("id") == msg.get("id"):
                    return d, sid
        return {}, sid
    return (json.loads(body) if body.strip() else {}), sid


def probe(url):
    t0 = time.time()
    try:
        init, sid = _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "shortformkit-mcpscan", "version": "1.0"}}})
        if "error" in init and not init.get("result"):
            msg = str(init["error"].get("message", ""))[:80]
            return {"status": "auth" if any(k in msg.lower() for k in ("auth", "token", "key", "unauthor")) else "down", "error": msg}
        info = (init.get("result") or {}).get("serverInfo") or {}
        try:
            _post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, timeout=5)
        except Exception:  # noqa: BLE001 (many servers answer 202/empty)
            pass
        tl, _ = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid)
        tools = (tl.get("result") or {}).get("tools")
        if tools is None:
            msg = str((tl.get("error") or {}).get("message", "no tools/list result"))[:80]
            return {"status": "auth" if any(k in msg.lower() for k in ("auth", "token", "key", "unauthor")) else "down", "error": msg, "server_name": info.get("name")}
        return {"status": "open", "tools": len(tools), "tool_names": [t.get("name") for t in tools][:40],
                # tool annotations (MCP 2025-03-26+): how many tools say they are read-only / destructive / open-world
                "ann": {"read_only": sum(1 for t in tools if (t.get("annotations") or {}).get("readOnlyHint") is True),
                        "destructive": sum(1 for t in tools if (t.get("annotations") or {}).get("destructiveHint") is True),
                        "annotated": sum(1 for t in tools if t.get("annotations"))}, "ms": int((time.time() - t0) * 1000),
                "server_name": info.get("name"), "server_version": info.get("version")}
    except urllib.error.HTTPError as e:
        return {"status": "auth" if e.code in (401, 402, 403) else "down", "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"status": "down", "error": type(e).__name__ + ": " + str(e)[:60]}


if __name__ == "__main__":
    rows = json.loads((OUT / "registry_remotes.json").read_text())
    # Polite: at most 5 URLs per host (gateways list thousands of paths), no temporary tunnels.
    per_host, urls = {}, []
    for u in sorted({r["url"] for r in rows if r.get("type") == "streamable-http" and not r.get("headers")}):
        h = u.split("/")[2].lower()
        if h.endswith(("trycloudflare.com", "ngrok-free.app", "ngrok.io", "ngrok.app", "loca.lt")) or h.startswith(("localhost", "127.")):
            continue
        if per_host.get(h, 0) < 5:
            per_host[h] = per_host.get(h, 0) + 1
            urls.append(u)
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    res, done = {}, 0
    with ThreadPoolExecutor(workers) as ex:
        for u, r in zip(urls, ex.map(probe, urls)):
            res[u] = r
            done += 1
            if done % 500 == 0:
                print(done, "/", len(urls), flush=True)
    res = {u: {**r, "tested": time.strftime("%Y-%m-%d")} for u, r in res.items()}
    (OUT / "probe.json").write_text(json.dumps(res, ensure_ascii=False))
    c = {}
    for r in res.values():
        c[r["status"]] = c.get(r["status"], 0) + 1
    print(len(urls), "probed:", c)
