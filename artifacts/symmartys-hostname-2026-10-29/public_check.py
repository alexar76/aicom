"""Verify the new public hostname and save a report containing no private state."""

import concurrent.futures
import json
import socket
import ssl
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
HOST = "https://symmartys.modelmarket.dev"
URLS = {
    "home": HOST + "/",
    "health": HOST + "/health",
    "manifest": HOST + "/ai-market/v2/manifest",
    "canonical_manifest": "https://modelmarket.dev/providers/symmartys/ai-market/v2/manifest",
    "peers": "https://modelmarket.dev/ai-market/v2/federation/peers",
    "ecosystem": "https://ecosystem.modelmarket.dev/ru/",
    "whitepaper": "https://ecosystem.modelmarket.dev/docs/ecosystem/whitepaper/ru.html",
    "knowledge": "https://ecosystem.modelmarket.dev/docs/ecosystem/knowledge-base-ru.html",
    "live": "https://monitor.modelmarket.dev/api/health",
    "uni": "https://monitor-uni.modelmarket.dev/api/health",
    "redirect": "http://symmartys.modelmarket.dev/",
}


def get(item):
    key, url = item
    with urllib.request.urlopen(url, timeout=25) as response:
        return key, (response.status, response.geturl(), response.read())


with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
    responses = dict(pool.map(get, URLS.items()))


def obj(key):
    return json.loads(responses[key][2])


assert obj("health")["service"] == "symmartys"
assert obj("health")["version"] == "0.5.0"
assert len(obj("manifest")["tools"]) == 16
for key in ("public_key", "pq_public_key"):
    assert obj("manifest")["signature"][key] == obj("canonical_manifest")["signature"][key]
for key in ("home", "ecosystem", "whitepaper", "knowledge"):
    html = responses[key][2].decode()
    assert "symmartys" in html.lower(), key
    assert HOST in html and "emporion.modelmarket.dev" not in html, key
assert responses["redirect"][1] == HOST + "/"
peers = obj("peers")
if isinstance(peers, dict):
    peers = peers["peers"]
provider = [p for p in peers if any(name in p.get("url", "") for name in ("symmartys", "emporion"))]
assert len(provider) == 1
assert provider[0]["url"] == "https://modelmarket.dev/providers/symmartys"
assert provider[0]["trusted"] and provider[0]["capabilities_count"] == 16
assert obj("live")["status"] == "ok" and obj("uni")["status"] == "ok"
assert obj("uni")["blockchain_ready"]
try:
    urllib.request.urlopen(HOST + "/ops/v1/calls", timeout=15)
except urllib.error.HTTPError as error:
    assert error.code == 404
else:
    raise AssertionError("Operator route exposed")
with socket.create_connection(("symmartys.modelmarket.dev", 443), timeout=15) as raw:
    with ssl.create_default_context().wrap_socket(raw, server_hostname="symmartys.modelmarket.dev") as tls:
        certificate = tls.getpeercert()
wheel = OUT / "dist/aimarket_symmartys-0.5.0-py3-none-any.whl"
with zipfile.ZipFile(wheel) as archive:
    metadata = archive.read(next(p for p in archive.namelist() if p.endswith(".dist-info/METADATA"))).decode()
    assert "Project-URL: Homepage, " + HOST in metadata
    assert "github.com/alexar76/emporion" not in metadata
result = {
    "date": "2026-10-29",
    "homepage": HOST + "/",
    "certificate_chain_and_hostname_verified": True,
    "certificate_expires": certificate["notAfter"],
    "public_checks": {key: {"status": value[0], "url": value[1]} for key, value in responses.items()},
    "capabilities": 16,
    "same_ed25519_and_mldsa_identity_on_both_addresses": True,
    "federation_provider_rows": 1,
    "federation_canonical_url": provider[0]["url"],
    "ops_public_status": 404,
    "package_new_homepage_verified": True,
    "github_writes": False,
    "pypi_uploads": False,
}
(OUT / "public-checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
