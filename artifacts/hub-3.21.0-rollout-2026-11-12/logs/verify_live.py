"""Outside check of a hub's AI Catalog door, with none of the hub's code: rfc8785, cryptography, dilithium-py.

    uv run --no-project --with rfc8785 --with cryptography --with dilithium-py python verify_live.py https://hub.example [--unsigned]

Fetches what a stranger would and fails on the first thing that does not hold: media types, the Link relation,
the Server Card against the live MCP endpoint, every digest of the root catalogue and of a sample of the
capabilities (all of the hub's own), every signature against the DID document. An entry the hub publishes
without a Trust Manifest is a failure, not something to skip. --unsigned is for a hub that has no root did:web
(served under a path): there the documents must carry no signature at all.
"""
import base64, hashlib, json, random, sys, urllib.error, urllib.request
from urllib.parse import urlparse

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from dilithium_py.ml_dsa import ML_DSA_65

base = sys.argv[1].rstrip("/")
unsigned = "--unsigned" in sys.argv
UA = "hub321-rollout-check/1"
checks = 0


def ok(condition, what):
    global checks
    if not condition:
        print(json.dumps({"hub": base, "FAILED": what, "checks_passed": checks}))
        sys.exit(1)
    checks += 1


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def fetch(url, *, method="GET", data=None, headers=None, follow=True):
    request = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA, **(headers or {})})
    opener = urllib.request.build_opener() if follow else urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=40) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(), r.headers.get_all("Link") or []
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read(), e.headers.get_all("Link") or []


unb64 = lambda s: base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))
b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
host = urlparse(base).hostname
did = "did:web:" + host


def verify(obj, typ, keys):
    sig = obj["signature"]
    header64, empty, signature64 = sig["jws"].split(".")
    header = json.loads(unb64(header64))
    ok(empty == "" and header["typ"] == typ and header["kid"].startswith(sig["signer"] + "#") and sig["signer"] == did, f"signature header {header}")
    payload = {k: v for k, v in obj.items() if k != "additionalSignatures"}
    payload["signature"] = {k: v for k, v in sig.items() if k != "jws"}
    message = (header64 + "." + b64(rfc8785.dumps(payload))).encode()
    jwk = keys[header["kid"]]
    if header["alg"] == "ML-DSA-65":
        ok(sig["profile"].endswith("/did-web-ml-dsa-65-v1") and jwk["kty"] == "AKP", "ML-DSA profile and key")
        ok(ML_DSA_65.verify(unb64(jwk["pub"]), message, unb64(signature64)), "ML-DSA-65 signature")
    else:
        ok(header["alg"] == "EdDSA" and sig["profile"].endswith("/did-web-eddsa-v1") and jwk["kty"] == "OKP", "EdDSA profile and key")
        Ed25519PublicKey.from_public_bytes(unb64(jwk["x"])).verify(unb64(signature64), message)   # raises when invalid
        ok(True, "Ed25519 signature")
    return header["alg"]


report = {"hub": base}
status, headers, body, links = fetch(base + "/", method="HEAD")
ok(any(f'<{base}/.well-known/ai-catalog.json>; rel="ai-catalog"' in l for l in links), f"Link rel=ai-catalog on HEAD /: {links}")

keys = {}
if not unsigned:
    status, headers, body, _ = fetch(f"https://{host}/.well-known/did.json")
    ok(status == 200, f"did.json {status}")
    document = json.loads(body)
    ok(document["id"] == did, "did document id")
    keys = {m["id"]: m["publicKeyJwk"] for m in document["verificationMethod"] if m["id"] in document["assertionMethod"] and m["controller"] == did}
    report["keys"] = sorted(k.split("#")[1] for k in keys)

# The Server Card, and what the live endpoint says.
status, headers, body, _ = fetch(base + "/mcp/server-card", headers={"Accept": "application/mcp-server-card+json"})
ok(status == 200 and headers["content-type"] == "application/mcp-server-card+json", f"server card {status} {headers.get('content-type')}")
ok(headers.get("access-control-allow-origin") == "*" and "etag" in headers, "server card CORS and ETag")
card = json.loads(body)
ok(card["$schema"] == "https://static.modelcontextprotocol.io/schemas/v1/server-card.schema.json" and "tools" not in card, "server card schema, no tools")
remote = card["remotes"][0]
ok(remote["url"] == base + "/mcp" and remote["type"] == "streamable-http", f"remote {remote['url']}")
status, _, answer, _ = fetch(remote["url"], method="POST", headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                             data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                                 "protocolVersion": remote["supportedProtocolVersions"][0], "capabilities": {}, "clientInfo": {"name": "rollout-check", "version": "1"}}}).encode())
frame = next((l for l in answer.decode().splitlines() if l.startswith("data:")), answer.decode())
result = json.loads(frame[5:] if frame.startswith("data:") else frame)["result"]
ok(status == 200 and result["serverInfo"]["version"] == card["version"] and result["protocolVersion"] == remote["supportedProtocolVersions"][0],
   f"live initialize agrees with the card: {result['serverInfo']} vs {card['version']}")
report["card"] = {"name": card["name"], "version": card["version"]}

random.seed(20261112)
for path in ("/.well-known/ai-catalog.json", "/ai-catalog/v1/capabilities.json"):
    status, headers, body, _ = fetch(base + path)
    ok(status == 200 and headers["content-type"] == "application/ai-catalog+json", f"{path} {status} {headers.get('content-type')}")
    catalog = json.loads(body)
    ok(catalog["specVersion"] == "1.0" and catalog["host"]["displayName"], f"{path} specVersion and host")
    if unsigned:
        ok("signature" not in catalog and not any("trustManifests" in e for e in catalog["entries"]), f"{path} must be unsigned on this hub")
    else:
        ok(catalog["host"]["identifier"] == did, f"{path} host.identifier")
        alg = verify(catalog, "ai-catalog+jws", keys)
        report.setdefault("snapshot", {})[path] = alg
        ok(alg == ("ML-DSA-65" if any(k.endswith("#hub-ml-dsa-65") for k in keys) else "EdDSA"), f"{path}: a hub with an ML-DSA-65 key signs the snapshot with it")
    own = [e for e in catalog["entries"] if e["identifier"].startswith(f"urn:air:{host}:")]
    others = [e for e in catalog["entries"] if not e["identifier"].startswith(f"urn:air:{host}:")]
    sample = own + random.sample(others, min(len(others), 12))
    endorsed = 0
    for entry in sample:
        ok(("url" in entry) != ("data" in entry) and entry["type"], f"entry shape {entry['identifier']}")
        if "digest" in entry:
            status, _, served, _ = fetch(entry["url"])
            ok(status == 200 and entry["digest"] == "sha256:" + hashlib.sha256(served).hexdigest(), f"digest of {entry['url']} ({status})")
        if entry in own and "digest" in entry and not unsigned:
            ok(len(entry.get("trustManifests", [])) == 1, f"own entry without exactly one Trust Manifest: {entry['identifier']}")
            manifest = entry["trustManifests"][0]
            ok(manifest["contributor"] == did and manifest["subject"] == {k: entry[k] for k in ("identifier", "type", "digest", "version") if k in entry},
               f"manifest subject of {entry['identifier']}")
            ok(verify(manifest, "ai-catalog-trust-manifest+jws", keys) == "EdDSA", "entry manifests are Ed25519")
            endorsed += 1
        if entry in others:
            ok(entry["identifier"].startswith(base + "/ai-catalog/v1/ids/") and "trustManifests" not in entry, f"peer entry identifier {entry['identifier']}")
            status, hop, _, _ = fetch(entry["identifier"], follow=False)
            ok(status == 303 and hop.get("location") == entry["url"], f"identifier resolves: {status}")
    report[path] = {"entries": len(catalog["entries"]), "own": len(own), "checked": len(sample), "endorsed": endorsed}

for name in ("did-web-eddsa-v1", "did-web-ml-dsa-65-v1"):
    status, headers, body, _ = fetch(f"{base}/ai-catalog/profiles/{name}")
    ok(status == 200 and f"https://modelmarket.dev/ai-catalog/profiles/{name}".encode() in body, f"profile {name} {status}")
status, _, body, _ = fetch(base + "/ai-market/v2/health")
report["version"] = json.loads(body).get("version")
ok(report["version"] == "3.21.0", f"version {report['version']}")
report["checks"] = checks
print(json.dumps(report))
