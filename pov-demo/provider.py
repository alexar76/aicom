#!/usr/bin/env python3
"""Two capability providers for the Pay-on-Verified demo: one honest, one that cheats.

Both sell the same thing — `math.factor@v1`, the prime factorization of an integer — under
different products and different signing keys, so to a buyer they are two unrelated sellers.

    POST /honest/invoke   product `factorworks`: trial division, always right
    POST /cheat/invoke    product `quickfactor`: answers fast by factoring n+4 instead of n —
                          a plausible-looking answer whose product is NOT n
    GET  /<who>/healthz   capability id, product id and public key

Both are run by the hub operator, on purpose and in the open: the demo shows what the hub does
when a seller delivers garbage, and a real cheater cannot be scheduled. Responses are
Ed25519-signed and bound to the request exactly as the hub's production policy demands
(capability id + product id + sha256 of the input), so the cheat is a VALIDLY SIGNED lie — the
signature proves who said it, not that it is true. That is the gap verification closes.

Stdlib + `cryptography`. Loopback only; the public address is the hub nginx location
/providers/pov-demo/.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

CAPABILITY = "math.factor@v1"
ALL_PERSONAS = {"honest": "factorworks", "cheat": "quickfactor"}
# The cheat answers only where it is switched on. modelmarket.dev delisted it after the
# 2026-10-03 demo (docs/pay-on-verified-demo.md): a deliberately wrong seller on a live market
# is a trap for any buyer who skips verification. To rerun the demo on your own hub, set
# POV_DEMO_PERSONAS=honest,cheat.
PERSONAS = {k: v for k, v in ALL_PERSONAS.items()
            if k in {x.strip() for x in os.environ.get("POV_DEMO_PERSONAS", "honest").split(",")}}
KEY_DIR = Path(os.environ.get("POV_DEMO_KEY_DIR", "/var/lib/pov-demo"))
MAX_N = 10**12   # trial division stays well under a second


def _key(name: str) -> Ed25519PrivateKey:
    path = KEY_DIR / f"{name}.key"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    key = Ed25519PrivateKey.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    return key


KEYS = {name: _key(name) for name in ALL_PERSONAS}


def pubkey(name: str) -> str:
    raw = KEYS[name].public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode()


def factorize(n: int) -> list[int]:
    out, d = [], 2
    while d * d <= n:
        while n % d == 0:
            out.append(d)
            n //= d
        d += 1 if d == 2 else 2
    if n > 1:
        out.append(n)
    return out


def deliver(name: str, n: int) -> dict:
    if name == "honest":
        return {"n": n, "factors": factorize(n), "method": "trial division"}
    # The cheat: the factorization of a nearby number, presented as the answer. Each factor is
    # a real prime, the list looks right, and it is wrong.
    return {"n": n, "factors": factorize(n + 4), "method": "trial division"}


def canonical(capability_id: str, product_id: str, payload, result) -> bytes:
    input_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return json.dumps({
        "capability_id": capability_id or "",
        "product_id": product_id or "",
        "input_sha256": hashlib.sha256(input_json.encode()).hexdigest(),
        "result": result,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict, headers: dict | None = None) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _persona(self, suffix: str) -> str | None:
        parts = self.path.strip("/").split("/")
        return parts[0] if len(parts) == 2 and parts[0] in PERSONAS and parts[1] == suffix else None

    def do_GET(self):  # noqa: N802
        name = self._persona("healthz")
        if not name:
            return self._send(404, {"error": "not_found"})
        self._send(200, {"ok": True, "capability_id": CAPABILITY, "product_id": PERSONAS[name],
                         "provider_pubkey": pubkey(name)})

    def do_POST(self):  # noqa: N802
        name = self._persona("invoke")
        if not name:
            return self._send(404, {"error": "not_found"})
        try:
            request = json.loads(self.rfile.read(min(int(self.headers.get("content-length") or 0), 65536)) or b"{}")
            payload = request.get("input") or {}
            n = int(payload.get("n"))
        except (ValueError, TypeError, AttributeError):
            return self._send(400, {"success": False, "error": "input.n must be an integer"})
        if not 2 <= n <= MAX_N:
            return self._send(400, {"success": False, "error": f"input.n must be between 2 and {MAX_N}"})
        result = deliver(name, n)
        signature = base64.b64encode(KEYS[name].sign(canonical(
            request.get("capability_id", ""), request.get("product_id", ""), payload, result))).decode()
        self._send(200, {"success": True, "result": result}, {"X-Provider-Signature": signature})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    bind = os.environ.get("POV_DEMO_BIND", "127.0.0.1")
    port = int(os.environ.get("POV_DEMO_PORT", "9476"))
    for name, product in PERSONAS.items():
        print(f"{product} ({name}) pubkey {pubkey(name)}", flush=True)
    ThreadingHTTPServer((bind, port), Handler).serve_forever()
