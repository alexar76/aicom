"""Record textokit (tienda.textokit.store) as an observed seller on the apex hub, with its consent.

Consent: Martin Pisacreta, DEV comment 3jn8c (2026-11-02 13:33:42Z) under article 4804987, answering our 3je30:
"you have our consent to list every paid route in tienda.textokit.store/.well-known/x402 as an observed seller
(your section 8b). payTo is the agent wallet 0x6b5aF9924f4CD35643c11a9fd1C983f77261A6E1 on Base and we don't plan
to change it; unpaid probes every few hours are fine."

Every paid route = no `routes` list (the hub takes all routes of the discovery document, cap 25; it lists 20).
payTo is pinned from the consent, not from first sight.

Runs inside the hub container (token from its env, never printed), like the 10-30 selftest.py:
    ssh factory-vps 'docker exec -i modelmarket-hub python -' < record.py
Undo (consent withdrawn):
    DELETE /ai-market/v2/federation/observed-sellers?origin=https://tienda.textokit.store with the admin token.
"""
import json
import os
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9083/ai-market/v2/federation/observed-sellers"
H = {"Authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"], "Content-Type": "application/json"}
BODY = {
    "origin": "https://tienda.textokit.store",
    "consent": {"by": "Martin Pisacreta (martinpisacreta on DEV)", "at": "2026-11-02",
                "how": "public DEV comment 3jn8c under article 4804987",
                "note": "every paid route in /.well-known/x402; unpaid probes every few hours are fine"},
    "pay_to": "0x6b5aF9924f4CD35643c11a9fd1C983f77261A6E1",
}

req = urllib.request.Request(BASE, data=json.dumps(BODY).encode(), headers=H, method="POST")
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        status, out = r.status, json.loads(r.read() or b"{}")
except urllib.error.HTTPError as e:
    status, out = e.code, json.loads(e.read() or b"{}")
seller = out.get("seller") or {}
routes = (out.get("observation") or {}).get("routes") or seller.get("routes") or []
print("POST", status, out.get("status") or out.get("detail") or "")
print("seller", json.dumps({k: seller.get(k) for k in ("name", "pinned_pay_to", "observed_at", "last_error",
                                                         "routes_served", "consent")}))
print("routes", len(routes), "listed", sum(1 for r in routes if r.get("listed")))
for r in routes:
    print(r.get("listed"), r.get("result"), r.get("probe_method"), r.get("price_usd"), r.get("url"))
with urllib.request.urlopen(BASE, timeout=30) as r:
    public = json.loads(r.read())
print("public sellers", [(s.get("origin"), len(s.get("routes") or [])) for s in public.get("sellers", [])])
