"""From outside: each hub's public MCP endpoint, as a pinning client sees it.

    python3 live_tools.py [label=url ...]

initialize + tools/list twice per hub; prints serverInfo.version, the number of tools, a sha256 over the canonical
tool list (sorted by name, JSON with sorted keys), whether the two reads agree, and any direct-tool description that
still carries a dollar amount or a trial count.
"""
import hashlib, json, re, sys, urllib.request

HUBS = {
    "apex-mcp": "https://mcp.modelmarket.dev/mcp", "apex": "https://modelmarket.dev/mcp",
    "uni": "https://uni.modelmarket.dev/mcp", "lab": "https://hub.modelmarket.dev/mcp",
    "hunt": "https://hunt.modelmarket.dev/mcp", "attested": "https://hub.attestedmemory.net/mcp",
    "indep": "https://independentai.network/hub/mcp",
}
DIRECT = {"weather_now", "air_quality_now", "nearby_sensors", "fair_random", "x402_check"}


def rpc(url, body, session=None):
    headers = {"content-type": "application/json", "accept": "application/json, text/event-stream",
               "user-agent": "aicom-rollout-check/1.0"}
    if session:
        headers["mcp-session-id"] = session
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode()
        sid = r.headers.get("mcp-session-id") or session
    if not raw.strip():
        return None, sid
    if raw.lstrip().startswith("{"):
        return json.loads(raw), sid
    data = [l[5:].strip() for l in raw.splitlines() if l.startswith("data:")]
    return (json.loads(data[-1]) if data else None), sid


def read(url):
    init, sid = rpc(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "aicom-rollout-check", "version": "1"}}})
    rpc(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    listed, _ = rpc(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
    tools = sorted(listed["result"]["tools"], key=lambda t: t["name"])
    return init["result"]["serverInfo"].get("version"), tools


def digest(tools):
    return hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:12]


if __name__ == "__main__":
    targets = dict(a.split("=", 1) for a in sys.argv[1:]) or HUBS
    bad = 0
    for label, url in targets.items():
        try:
            v1, t1 = read(url)
            v2, t2 = read(url)
        except Exception as exc:  # noqa: BLE001
            print(f"{label:9} {url}  ERROR {type(exc).__name__}: {str(exc)[:120]}")
            bad += 1
            continue
        loud = [t["name"] for t in t1 if t["name"] in DIRECT
                and (re.search(r"\$\d", t.get("description", "")) or re.search(r"first \d+ priced", t.get("description", "")))]
        same = digest(t1) == digest(t2)
        print(f"{label:9} version {v1}  tools {len(t1):2}  sha {digest(t1)}  stable {'yes' if same else 'NO'}  "
              f"direct {sorted(t['name'] for t in t1 if t['name'] in DIRECT)}  amounts-in-descriptions {loud or 'none'}")
        bad += (not same)
    sys.exit(1 if bad else 0)
