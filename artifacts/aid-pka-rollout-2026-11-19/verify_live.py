"""Check a live AID v2 endpoint proof from outside, without the hub's code.

    python3 verify_live.py https://modelmarket.dev/mcp <k> [domain]

Follows AID v2.1.1 Appendix B: a fresh 32-byte nonce, a GET with Accept-Signature (and AID-Domain when a
domain is given), no redirects; then Cache-Control: no-store, the covered set, keyid = RFC 7638 thumbprint
of k, alg, nonce, tag, freshness (30 s skew), and Ed25519 over the RFC 9421 signature base rebuilt from the
request this script sent. Also checks that an AID-Domain the endpoint does not serve gets no proof.
Needs only ``cryptography``. Exit 0 when every check passes.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401
        return None


def fetch(uri: str, headers: dict[str, str]):
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(uri, headers={**headers, "User-Agent": "aid-pka-check/1"}, method="GET")
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}


def check(uri: str, k: str, domain: str | None) -> list[str]:
    problems = []
    kid = b64url(hashlib.sha256(('{"crv":"Ed25519","kty":"OKP","x":"' + k + '"}').encode()).digest())
    nonce = b64url(os.urandom(32))
    covered = '"@method";req "@target-uri";req "@authority";req ' + ('"aid-domain";req ' if domain else "") + '"@status"'
    headers = {"Accept-Signature": f'aid-pka=({covered});created;expires;keyid="{kid}";alg="ed25519";'
                                   f'nonce="{nonce}";tag="aid-pka-v2"', "Cache-Control": "no-store"}
    if domain:
        headers["AID-Domain"] = domain
    status, h = fetch(uri, headers)
    if 300 <= status < 400:
        return [f"redirect {status}"]
    if "no-store" not in [p.strip() for p in h.get("cache-control", "").split(",")]:
        problems.append(f"cache-control is {h.get('cache-control')!r}")
    m = re.fullmatch(r"aid-pka=(\(([^()]*)\)((?:;[a-z]+=(?:\"[^\"]*\"|\d+))*))", h.get("signature-input", ""))
    s = re.fullmatch(r"aid-pka=:([A-Za-z0-9+/=]+):", h.get("signature", ""))
    if not m or not s:
        return problems + [f"no aid-pka signature (status {status})"]
    params_value, items = m.group(1), m.group(2).split(" ")
    params = dict(re.findall(r';([a-z]+)=("[^"]*"|\d+)', m.group(3)))
    want = ['"@method";req', '"@target-uri";req', '"@authority";req'] + (['"aid-domain";req'] if domain else []) + ['"@status"']
    if items != want:
        problems.append(f"covered set {items}")
    for name, value in (("keyid", f'"{kid}"'), ("nonce", f'"{nonce}"'), ("tag", '"aid-pka-v2"')):
        if params.get(name) != value:
            problems.append(f"{name} {params.get(name)!r}")
    if params.get("alg", "").lower() != '"ed25519"':
        problems.append(f"alg {params.get('alg')!r}")
    created, expires, now = int(params.get("created", 0)), int(params.get("expires", 0)), int(time.time())
    if not (expires > created and expires - created <= 300) or created - now > 30 or now - expires > 30:
        problems.append(f"freshness created={created} expires={expires} now={now}")
    parts = urlsplit(uri)
    authority = (parts.hostname or "").lower() + (f":{parts.port}" if parts.port not in (None, 443, 80) else "")
    lines = [f'"@method";req: GET', f'"@target-uri";req: {uri}', f'"@authority";req: {authority}']
    if domain:
        lines.append(f'"aid-domain";req: {domain}')
    lines += [f'"@status": {status}', f'"@signature-params": {params_value}']
    try:
        Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(k + "=" * (-len(k) % 4))).verify(
            base64.b64decode(s.group(1)), "\n".join(lines).encode())
    except Exception as exc:  # noqa: BLE001
        problems.append(f"signature does not verify ({type(exc).__name__})")
    return problems


def main() -> int:
    uri, k = sys.argv[1], sys.argv[2]
    domain = sys.argv[3] if len(sys.argv) > 3 else urlsplit(uri).hostname
    ok = True
    for label, d in (("unbound", None), (f"bound to {domain}", domain)):
        p = check(uri, k, d)
        ok &= not p
        print(f"{'ok ' if not p else 'FAIL'} {label}" + ("" if not p else ": " + "; ".join(p)))
    status, h = fetch(uri, {"Accept-Signature": 'aid-pka=("@method";req "@target-uri";req "@authority";req '
                                                '"aid-domain";req "@status");created;expires;keyid="x";alg="ed25519";'
                                                f'nonce="{b64url(os.urandom(32))}";tag="aid-pka-v2"',
                            "AID-Domain": "not-served.example"})
    refused = status == 403 and "signature" not in h
    ok &= refused
    print(f"{'ok ' if refused else 'FAIL'} unserved domain -> {status}, signature {'absent' if 'signature' not in h else 'PRESENT'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
