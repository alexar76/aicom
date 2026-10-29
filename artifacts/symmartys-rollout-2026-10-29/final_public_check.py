"""Read-only checks of the public SYMMARTYS cutover, without private state."""

import concurrent.futures
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
BASE = "https://modelmarket.dev/providers/symmartys"
URLS = {
    "health": BASE + "/health",
    "landing": BASE + "/",
    "manifest": BASE + "/ai-market/v2/manifest",
    "legacy_manifest": "https://modelmarket.dev/providers/emporion/ai-market/v2/manifest",
    "legacy_discovery": "https://modelmarket.dev/providers/emporion/.well-known/ai-market.json",
    "peers": "https://modelmarket.dev/ai-market/v2/federation/peers",
    "live_health": "https://monitor.modelmarket.dev/api/health",
    "uni_health": "https://monitor-uni.modelmarket.dev/api/health",
    "live_html": "https://monitor.modelmarket.dev/",
    "uni_html": "https://monitor-uni.modelmarket.dev/",
    "audit": "https://monitor.modelmarket.dev/api/federation/audit",
}


def fetch(item):
    name, url = item
    with urllib.request.urlopen(url, timeout=25) as response:
        assert response.status == 200, (name, response.status)
        body = response.read()
    return name, body


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    raw = dict(pool.map(fetch, URLS.items()))
data = {k: json.loads(v) for k, v in raw.items() if not k.endswith("html") and k != "landing"}
assert data["health"]["service"] == "symmartys"
assert data["health"]["version"] == "0.5.0"
assert data["health"]["capabilities"] == 16
manifest = data["manifest"]
assert len(manifest["tools"]) == 16
assert all(t["product_id"] == "symmartys" and t["capability_id"].startswith("symmartys.") for t in manifest["tools"])
assert data["legacy_manifest"]["tools"] == manifest["tools"]
for key in ("public_key", "pq_public_key"):
    assert data["legacy_manifest"]["signature"][key] == manifest["signature"][key]
assert BASE.encode() in raw["legacy_discovery"]

rows = data["peers"]
if isinstance(rows, dict):
    rows = rows["peers"]
provider_rows = [p for p in rows if any(name in p.get("url", "").lower() for name in ("symmartys", "emporion"))]
assert len(provider_rows) == 1
peer = provider_rows[0]
assert peer["url"] == BASE and peer["name"].startswith("SYMMARTYS")
assert peer["trusted"] and peer["status"] == "active" and peer["capabilities_count"] == 16
assert peer["trust_score"] > 0
audit_rows = [p for p in data["audit"]["rows"] if any(name in (p.get("id", "") + p.get("label", "")).lower() for name in ("symmartys", "emporion"))]
assert len(audit_rows) == 1 and audit_rows[0]["id"] == "symmartys"
assert audit_rows[0]["verdict"] == "on_map"

for realm, mode in (("live", "real"), ("uni", "universe")):
    assert data[realm + "_health"]["status"] == "ok"
    assert data[realm + "_health"]["mode"] == mode
    assert b"/assets/index-7WDukKUO.js" in raw[realm + "_html"]
assert data["uni_health"]["blockchain_ready"]

html = raw["landing"].decode()
assert "SYMMARTYS" in html
assert '<link rel="canonical" href="' + BASE + '/"' in html
assets = sorted(set(re.findall(r'(?:src|href)="((?:assets|fonts)/[^"\s]+)"', html)))
assert assets
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    asset_bodies = dict(pool.map(fetch, [(p, urllib.parse.urljoin(BASE + "/", p)) for p in assets]))
assert all(asset_bodies.values())

result = {
    "provider": {"url": BASE, "service": "symmartys", "version": "0.5.0", "capabilities": 16},
    "landing": {"http_status": 200, "canonical_url": BASE + "/", "assets_checked": assets},
    "federation": {"provider_rows": 1, "url": peer["url"], "name": peer["name"], "trusted": True, "trust_score": peer["trust_score"]},
    "legacy_route": {"same_capabilities_and_signing_identity": True, "advertises_canonical_url": True},
    "alien_monitor": {"live": "healthy", "uni": "healthy", "uni_blockchain_ready": True, "live_provider_id": "symmartys", "live_provider_verdict": "on_map", "frontend_asset": "/assets/index-7WDukKUO.js"},
    "browser": {"search_query": "symmartys", "search_hit_confirmed": True, "card_capabilities": 16, "screenshot": "alien-live-symmartys.png"},
    "github_writes": False,
}
(OUT / "final-public-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
