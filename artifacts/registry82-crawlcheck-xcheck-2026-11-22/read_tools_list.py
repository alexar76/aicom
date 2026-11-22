import json, sys, urllib.request
URL = "https://crawlcheck.io/mcp"
UA = "aicom-histor-xcheck (+https://histor.modelmarket.dev/)"

def post(body, session=None, version=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "User-Agent": UA}
    if session: h["Mcp-Session-Id"] = session
    if version: h["MCP-Protocol-Version"] = version
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read(); sid = r.headers.get("Mcp-Session-Id"); ctype = r.headers.get("Content-Type", "")
    if not raw: return None, sid
    text = raw.decode()
    if "text/event-stream" in ctype:
        msgs = [json.loads(l[5:].strip()) for l in text.splitlines() if l.startswith("data:") and l[5:].strip()]
        msg = next((m for m in msgs if m.get("id") == body.get("id")), msgs[-1] if msgs else None)
        return msg, sid
    return json.loads(text), sid

def read(version):
    init, sid = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": version or "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "aicom-histor-xcheck", "version": "1"}}})
    negotiated = (init or {}).get("result", {}).get("protocolVersion")
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid, version and negotiated)
    tools, cursor, pages = [], None, 0
    while True:
        params = {"cursor": cursor} if cursor else {}
        res, _ = post({"jsonrpc": "2.0", "id": 2 + pages, "method": "tools/list", "params": params}, sid, version and negotiated)
        result = res["result"]; tools += result.get("tools", []); pages += 1
        cursor = result.get("nextCursor")
        if not cursor or pages > 20: break
    return negotiated, pages, tools

out = {}
for v in ("2025-11-25", "2025-06-18", None):
    neg, pages, tools = read(v)
    out[str(v)] = {"negotiated": neg, "pages": pages, "tools": tools}
    print(v, "negotiated", neg, "pages", pages, "tools", len(tools))
json.dump(out, open(sys.argv[1], "w"), ensure_ascii=False)
