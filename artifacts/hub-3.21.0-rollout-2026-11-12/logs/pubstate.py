"""Public state of a hub, before/after a rollout: version, counts, binding on a free invoke."""
import json, sys, urllib.request
base = sys.argv[1].rstrip("/")
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base + path, headers={"User-Agent": "hub321-rollout-check/1"}), timeout=40) as r:
        return json.load(r), dict(r.headers)
out = {"hub": base}
h, _ = get("/ai-market/v2/health"); out["version"] = h.get("version") or h.get("server_version"); out["health"] = h.get("status")
wk, _ = get("/.well-known/ai-market.json"); out["capabilities"] = wk.get("capabilities_count")
p, _ = get("/ai-market/v2/federation/peers"); peers = p.get("peers", p if isinstance(p, list) else [])
out["peers"] = len(peers); out["active_peers"] = sum(1 for x in peers if x.get("status") == "active")
body = json.dumps({"product_id": "prod-logos", "capability_id": "logos.federation.summary@v1", "input": {},
                   "source_hub": "https://logos.modelmarket.dev"}).encode()
req = urllib.request.Request(base + "/ai-market/v2/invoke", data=body, headers={
    "Content-Type": "application/json", "X-Client-Nonce": "rollout-check-0001", "User-Agent": "hub321-rollout-check/1"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        ans = json.load(r); echo = r.headers.get("X-Client-Nonce-Echo")
    out["invoke"] = ans.get("success"); out["binding"] = "receipt_binding" in ans; out["echo"] = echo
    if out["binding"]:
        vreq = urllib.request.Request(base + "/ai-market/v2/receipts/verify", data=json.dumps({
            "receipt": ans["receipt"], "response": ans, "input": {}, "client_nonce": "rollout-check-0001"}).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "hub321-rollout-check/1"})
        with urllib.request.urlopen(vreq, timeout=40) as r:
            v = json.load(r)
        out["verify"] = {"valid": v.get("valid"), "signer": v.get("signer"), "pq_pinned": v.get("pq_pinned"),
                         "binding_valid": (v.get("binding") or {}).get("valid")}
except Exception as exc:
    out["invoke_error"] = str(exc)[:160]
print(json.dumps(out))
