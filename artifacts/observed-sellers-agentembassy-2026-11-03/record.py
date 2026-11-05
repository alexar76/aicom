"""Record Agent Embassy (aemb.pro) as an observed seller on the apex hub, with its consent.

Consent: Agent Embassy (agentembassy on DEV), DEV comment 3k05n (2026-11-03 16:31:29Z) under article 4804987:
"Flagship route: check_url_custom — POST aemb.pro/v1/check/ping — $0.001 per call, USDC on Base via x402. ...
payTo 0xD004278bC57FE4B9F743ABf17d713ed4169A88E9. Consent: I operate this endpoint and consent to AIMarket
crawling, probing, and listing it, including paid test calls at the listed price."

The consent names one endpoint, so `routes` lists only that one; the other 24 routes in
aemb.pro/.well-known/x402.json wait until the operator says to list them. payTo is pinned from the consent.

Runs inside the hub container (token from its env, never printed), like the textokit record of 2026-11-02:
    ssh factory-vps 'docker exec -i modelmarket-hub python -' < record.py
Undo (consent withdrawn):
    DELETE /ai-market/v2/federation/observed-sellers?origin=https://aemb.pro with the admin token.
"""
import json
import os
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9083/ai-market/v2/federation/observed-sellers"
H = {"Authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"], "Content-Type": "application/json"}
BODY = {
    "origin": "https://aemb.pro",
    "name": "Agent Embassy",
    "consent": {"by": "Agent Embassy (agentembassy on DEV)", "at": "2026-11-03",
                "how": "public DEV comment 3k05n under article 4804987",
                "note": "the flagship route POST /v1/check/ping; probing and paid test calls at the listed price"},
    "routes": ["https://aemb.pro/v1/check/ping"],
    "pay_to": "0xD004278bC57FE4B9F743ABf17d713ed4169A88E9",
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
