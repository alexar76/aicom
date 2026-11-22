"""Check the stale cases from outside, the way an ARD + AID client would.

    python3 check_fixtures.py            # needs: python3, cryptography

For the live manifest and each stale case: read the AID u from _agent.modelmarket.dev over DNS-over-HTTPS,
fetch the manifest, verify the MCP entry's trustManifest against the did:web key, fetch the card, compare
its bytes with the entry digest and its streamable-http remotes[].url with the AID u. Exit 0 when every
case gives the result it is meant to give.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import urllib.request

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

BASE = "https://modelmarket.dev"
CASES = {
    "healthy": (BASE + "/.well-known/ard.json", "urn:air:modelmarket.dev:mcp:gateway", (True, True)),
    "endpoint-mismatch": (BASE + "/interop/aid/endpoint-mismatch/ard.json", None, (True, False)),
    "card-digest-mismatch": (BASE + "/interop/aid/card-digest-mismatch/ard.json", None, (False, True)),
}


def get(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "aid-stale-case-check/1", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read(), r.headers.get("content-type", "")


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def jcs(v) -> bytes:
    # RFC 8785 for what a trustManifest holds (strings and objects only): sorted keys, no spaces, UTF-8.
    return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def aid_u() -> str:
    body, _ = get("https://dns.google/resolve?name=_agent.modelmarket.dev&type=TXT")
    txt = "".join(a["data"].strip('"').replace('" "', "") for a in json.loads(body)["Answer"] if a["type"] == 16)
    return dict(p.split("=", 1) for p in txt.split(";") if "=" in p)["u"]


def main() -> int:
    u = aid_u()
    did, _ = get(BASE + "/.well-known/did.json")
    jwk = next(m["publicKeyJwk"] for m in json.loads(did)["verificationMethod"] if m["publicKeyJwk"]["kty"] == "OKP")
    key = Ed25519PublicKey.from_public_bytes(b64d(jwk["x"]))
    print(f"AID u = {u}")
    ok = True
    for name, (url, ident, (want_digest, want_endpoint)) in CASES.items():
        body, mtype = get(url)
        entries = [e for e in json.loads(body)["entries"] if e["type"] == "application/mcp-server-card+json"
                   and (ident is None or e["identifier"] == ident)]
        assert len(entries) == 1, (name, len(entries))
        e = entries[0]
        tm = dict(e["trustManifest"])
        h64, _, sig = tm.pop("signature").partition("..")
        try:
            key.verify(b64d(sig), (h64 + "." + base64.urlsafe_b64encode(jcs(tm)).rstrip(b"=").decode()).encode())
            sig_ok = tm["subject"].get("digest") == e["digest"] and tm["subject"]["identifier"] == e["identifier"]
        except Exception:
            sig_ok = False
        card, ctype = get(e["url"])
        digest_ok = "sha256:" + hashlib.sha256(card).hexdigest() == e["digest"]
        urls = [r["url"] for r in json.loads(card)["remotes"] if r.get("type") == "streamable-http"]
        endpoint_ok = urls == [u]
        good = sig_ok and digest_ok == want_digest and endpoint_ok == want_endpoint
        ok &= good
        print(f"{'OK  ' if good else 'FAIL'} {name}: trustManifest {'valid' if sig_ok else 'INVALID'}, "
              f"digest {'match' if digest_ok else 'mismatch'}, remotes url {urls} "
              f"{'==' if endpoint_ok else '!='} AID u  [manifest {mtype.split(';')[0]}, card {ctype.split(';')[0]}]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
