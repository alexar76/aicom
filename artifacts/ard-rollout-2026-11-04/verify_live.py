"""verify_live.py HUB [OUT_DIR] — check a live hub's ARD door from outside, with libraries that are not ours.

Initial contact (well-known, media type, Link on HEAD /), every digest against the bytes served at its url over the
public internet, every trustManifest under the key of the live did:web document (rfc8785 + cryptography), the
registry (search, descriptor digests, agents paging, explore, problem details). Writes the responses it validated
to OUT_DIR for the CDDL check. Exit 1 on any failure.
"""
import base64
import hashlib
import json
import sys
import urllib.error
import urllib.request

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

HUB = sys.argv[1].rstrip("/")
OUT = sys.argv[2] if len(sys.argv) > 2 else None
UA = {"User-Agent": "aicom-ard-verify/1 (+https://modelmarket.dev/ard)"}
failures = []


def req(method, url, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(UA, **(headers or {}))
    if data is not None:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def check(cond, what):
    print(("ok    " if cond else "FAIL  ") + what)
    if not cond:
        failures.append(what)


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def save(name, data):
    if OUT:
        with open(f"{OUT}/{name}.json", "wb") as f:
            f.write(data)


status, headers, body = req("GET", HUB + "/.well-known/ard.json")
check(status == 200, f"GET /.well-known/ard.json -> {status}")
check(headers.get("Content-Type") == "application/ard+json", f"media type {headers.get('Content-Type')}")
check("max-age" in (headers.get("Cache-Control") or ""), f"cacheable: {headers.get('Cache-Control')}")
manifest = json.loads(body)
save("manifest", body)
entries = manifest["entries"]
check(len(entries) == 4, f"{len(entries)} manifest entries")
status, headers, _ = req("HEAD", HUB + "/")
links = headers.get_all("Link") or []
check(any(f"<{HUB}/.well-known/ard.json>; rel=\"ard\"" in v for v in links), f"Link rel=ard on HEAD /: {links}")

did_status, _, did_body = req("GET", HUB + "/.well-known/did.json")
signed = did_status == 200
key = None
if signed:
    did = json.loads(did_body)
    jwk = did["verificationMethod"][0]["publicKeyJwk"]
    key = Ed25519PublicKey.from_public_bytes(unb64(jwk["x"]))
    host = HUB.split("://", 1)[1].split("/", 1)[0]
    check(did["id"] == "did:web:" + host.replace(":", "%3A"), f"did id {did['id']}")
else:
    print(f"note  no did:web document ({did_status}): entries expected unsigned")


def verify_entry(entry, label, own=True):
    """own: this hub publishes the entry, so it must be signed; a peer's entry must not be."""
    if "digest" in entry and "url" in entry:
        s, _, served = req("GET", entry["url"])
        check(s == 200 and entry["digest"] == "sha256:" + hashlib.sha256(served).hexdigest(),
              f"{label}: digest = sha256 of the bytes at {entry['url'][:70]}")
    tm = entry.get("trustManifest")
    if not signed:
        check(tm is None, f"{label}: unsigned, as a hub without did:web must be")
        return
    if not own:
        check(tm is None, f"{label}: a peer's listing, unsigned (source {entry.get('source', '')[:50]})")
        return
    check(tm is not None, f"{label}: this hub's own entry carries a trustManifest")
    if tm is None:
        return
    subject = {k: entry[k] for k in ("identifier", "type", "version", "digest") if k in entry}
    check(tm["subject"] == subject, f"{label}: trustManifest subject = entry coordinates")
    h64, empty, s64 = tm["signature"].split(".")
    body_ = {k: v for k, v in tm.items() if k != "signature"}
    try:
        key.verify(unb64(s64), (h64 + "." + b64(rfc8785.dumps(body_))).encode())
        ok = empty == "" and json.loads(unb64(h64))["alg"] == "EdDSA"
    except Exception:
        ok = False
    check(ok, f"{label}: detached EdDSA JWS verifies under the live did:web key")
    return True


for e in entries:
    verify_entry(e, e["type"])

status, headers, body = req("POST", HUB + "/ard/v1/search", {"query": {"text": "weather"}, "pageSize": 5})
check(status == 200, f"POST /ard/v1/search -> {status}")
save("search-response", body)
results = json.loads(body).get("results", [])
print(f"note  search 'weather': {len(results)} results")
sources = {}
for r in results:
    sources[r["source"]] = sources.get(r["source"], 0) + 1
print(f"note  result sources: {sources}")
for r in results[:5]:
    check(0 <= r["score"] <= 100 and r["source"].startswith("http"), f"result {r['identifier'][:60]} score {r['score']}")
    verify_entry(r, "result " + r["identifier"].split(":")[-1], own=r["source"] == HUB)
status, headers, body = req("GET", HUB + "/ard/v1/agents?pageSize=2")
check(status == 200, f"GET /ard/v1/agents -> {status}")
save("agents", body)
agents = json.loads(body)
if agents.get("nextPageToken"):
    s2, _, b2 = req("GET", HUB + "/ard/v1/agents?pageSize=2&pageToken=" + agents["nextPageToken"])
    check(s2 == 200 and json.loads(b2)["entries"][0]["identifier"] > agents["entries"][-1]["identifier"],
          "agents page 2 continues in identifier order")
status, headers, body = req("POST", HUB + "/ard/v1/explore", {"resultType": {"facets": [{"field": "publisher"}]}})
check(status == 200, f"POST /ard/v1/explore -> {status}: {json.loads(body).get('facets', {}).get('publisher', {}).get('buckets', [])[:3]}")
status, headers, body = req("POST", HUB + "/ard/v1/search", {"query": {"text": "x", "filter": {"color": "blue"}}})
check(status == 400 and headers.get("Content-Type") == "application/problem+json"
      and json.loads(body)["error"] == "INVALID_ARGUMENT", f"unknown filter -> {status} problem details")
status, _, _ = req("GET", HUB + "/ai-market/v2/health")
check(status == 200, f"health {status}")
print(("ALL OK " if not failures else f"{len(failures)} FAILURES ") + HUB)
sys.exit(1 if failures else 0)
