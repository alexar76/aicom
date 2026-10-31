"""Live self-test on our own origin: record consent for one own route, observe, read back, delete."""
import json, os, urllib.request
BASE = "http://127.0.0.1:9083/ai-market/v2/federation/observed-sellers"
H = {"Authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"], "Content-Type": "application/json"}
def call(method, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
st, out = call("POST", BASE, {"origin": "https://modelmarket.dev",
    "consent": {"by": "operator self-test", "at": "2026-10-30", "how": "own origin, rollout self-test"},
    "routes": ["https://modelmarket.dev/x402/x402-check"]})
print("POST", st, json.dumps({k: out.get(k) for k in ("status",)}), json.dumps(out.get("observation", {}).get("routes"), indent=None)[:900])
print("seller", json.dumps({k: (out.get("seller") or {}).get(k) for k in ("routes_served", "pinned_pay_to", "last_error", "observed_at")}))
with urllib.request.urlopen("http://127.0.0.1:9083/ai-market/v2/search?intent=check+an+x402+payment+route", timeout=30) as r:
    print("search observed", [(o["url"], o["price_usd"], o["network"]) for o in json.loads(r.read()).get("observed", [])])
st, out = call("DELETE", BASE + "?origin=https://modelmarket.dev")
print("DELETE", st)
with urllib.request.urlopen(BASE, timeout=30) as r:
    print("after delete sellers", json.loads(r.read())["sellers"])
