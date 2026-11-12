"""Record oracleinsight and PriorSeal as observed sellers on the apex hub, with their consent.

Consent: YuTao (imokokok), public GitHub comment alexar76/aimarket-hub#23, issuecomment-6789700463
(2026-11-11 07:20:45Z): "Yes, please record oracleinsight.xyz in the observed tier now. You may read its public
discovery document and perform the described unpaid probes. For Insight POST resources, please use the method
advertised in the manifest." / "Please add priorseal.xyz once the parser accepts the current resource field in its
discovery document. All four currently advertised PriorSeal paid resources are GET endpoints and need no request
body." / "If an observed payTo changes, please unlist the resource and request confirmation here before restoring it."

oracleinsight.xyz answers its discovery paths with 307 to www.oracleinsight.xyz, and the hub does not follow
redirects, so the origin recorded is https://www.oracleinsight.xyz (same seller, same domain).
No routes list = every route of the discovery document. payTo is pinned on first sight; a different one later
unlists the route until the operator re-confirms with the seller (what YuTao asked for).

Runs inside the hub container (token from its env, never printed):
    ssh factory-vps 'docker exec -i modelmarket-hub python - ORIGIN' < record.py
Undo (consent withdrawn): DELETE /ai-market/v2/federation/observed-sellers?origin=<origin> with the admin token.
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:9083/ai-market/v2/federation/observed-sellers"
H = {"Authorization": "Bearer " + os.environ["AIMARKET_ADMIN_TOKEN"], "Content-Type": "application/json"}
HOW = "public GitHub comment in alexar76/aimarket-hub#23 (issuecomment-6789700463)"
SELLERS = {
    "https://priorseal.xyz": {
        "by": "YuTao (imokokok on GitHub)", "at": "2026-11-11", "how": HOW,
        "note": "four GET resources, no request body; unlist and ask on a payTo change"},
    "https://www.oracleinsight.xyz": {
        "by": "YuTao (imokokok on GitHub)", "at": "2026-11-11", "how": HOW,
        "note": "oracleinsight.xyz; POST resources with the advertised method; unlist and ask on a payTo change"},
}
origin = sys.argv[1]
body = {"origin": origin, "consent": SELLERS[origin]}
req = urllib.request.Request(BASE, data=json.dumps(body).encode(), headers=H, method="POST")
try:
    with urllib.request.urlopen(req, timeout=600) as r:
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
    print(r.get("listed"), r.get("result"), r.get("method"), r.get("probe_method"), r.get("http_status"),
          r.get("price_usd"), r.get("network"), r.get("url"))
