"""Actor request proofs: destination-bound intents and durable replay protection.

This file is copied into independently packaged Attested services. Keep copies
byte-identical. A proxy can relay explicitly signed targets; it cannot add one.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from urllib.parse import parse_qsl

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException

DOMAIN = "attested-actor/v2"
MAX_SKEW_SECONDS = 300
MAX_BODY_BYTES = 1_048_576
NONCE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
ACTOR = re.compile(r"^did:actor:[0-9a-f]{64}$")
HEADERS = ("x-actor-id", "x-actor-public-key", "x-actor-timestamp", "x-actor-nonce",
           "x-actor-signature", "x-actor-version", "x-actor-intent")
_SMALL_ORDER = frozenset(bytes.fromhex(h) for h in (
    "0000000000000000000000000000000000000000000000000000000000000000",
    "0100000000000000000000000000000000000000000000000000000000000000",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
))


def _decode(value: str) -> bytes:
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as error:
        raise HTTPException(401, "invalid actor proof encoding") from error


def request_target(request, audience: str) -> dict:
    """Use exact body bytes: proxies must preserve or explicitly target transformed bytes."""
    body = request.scope.get("actor_proof_body", getattr(request, "_body", b""))
    return {"audience": audience, "method": request.method.upper(),
            "path": request.scope.get("path", ""),
            "query": [list(pair) for pair in parse_qsl(
                request.scope.get("query_string", b"").decode("ascii"), keep_blank_values=True)],
            "body_sha256": hashlib.sha256(body).hexdigest()}


def verify_actor_request(request, *, audience: str, spend_nonce, now: float | None = None) -> str:
    headers = request.headers
    if headers.get("x-actor-version") != "2":
        raise HTTPException(401, "request-bound actor proof v2 is required; legacy identity proofs are refused")
    actor, timestamp, nonce = (headers.get(name, "") for name in
                               ("x-actor-id", "x-actor-timestamp", "x-actor-nonce"))
    intent = headers.get("x-actor-intent", "")
    if not ACTOR.fullmatch(actor) or not NONCE.fullmatch(nonce) or not 1 <= len(intent) <= 16_384:
        raise HTTPException(401, "invalid request-bound actor proof")
    current = time.time() if now is None else now
    try:
        issued = int(timestamp)
    except ValueError as error:
        raise HTTPException(401, "actor timestamp must be unix seconds") from error
    if abs(current - issued) > MAX_SKEW_SECONDS:
        raise HTTPException(401, "actor proof is stale or from the future")
    try:
        targets = json.loads(_decode(intent))
    except (ValueError, TypeError, UnicodeDecodeError, RecursionError) as error:
        raise HTTPException(401, "invalid actor intent") from error
    fields = {"audience", "method", "path", "query", "body_sha256"}
    if (not isinstance(targets, list) or not 1 <= len(targets) <= 4
            or any(not isinstance(target, dict) or set(target) != fields for target in targets)
            or any(not isinstance(target.get("audience"), str) for target in targets)
            or len({target["audience"] for target in targets}) != len(targets)):
        raise HTTPException(401, "actor intent needs one explicit target per destination")
    if request_target(request, audience) not in targets:
        raise HTTPException(401, "actor intent does not authorize this destination, method, path, query or body")
    public = _decode(headers.get("x-actor-public-key", ""))
    signature = _decode(headers.get("x-actor-signature", ""))
    if len(public) != 32 or len(signature) != 64:
        raise HTTPException(401, "invalid actor identity key material")
    if any((point[:31] + bytes([point[31] & 0x7f])) in _SMALL_ORDER
           for point in (public, signature[:32])):
        raise HTTPException(401, "invalid actor identity key material")
    if not hmac.compare_digest(actor[10:], hashlib.sha256(public).hexdigest()):
        raise HTTPException(401, "actor id is not bound to the public key")
    message = f"{DOMAIN}\n{actor}\n{timestamp}\n{nonce}\n{intent}".encode()
    try:
        Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
    except (InvalidSignature, ValueError) as error:
        raise HTTPException(401, "signed actor intent required") from error
    # A valid proof is spent durably only after every check passes. Unique INSERT
    # is the lock across processes/replicas; no cache eviction can revive a proof.
    if not spend_nonce(audience, actor, nonce, issued + MAX_SKEW_SECONDS + 1, int(current)):
        raise HTTPException(401, "actor proof already used")
    return actor


class ActorProofBody:
    """Capture bounded bytes once for synchronous FastAPI auth and transparent proxies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", ()))
        if scope["type"] != "http" or not any(name in headers for name in
                                               (b"x-actor-id", b"x-actor-signature")):
            await self.app(scope, receive, send)
            return
        chunks, length = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            length += len(chunk)
            if length > MAX_BODY_BYTES:
                await send({"type": "http.response.start", "status": 413,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"actor request body too large"}'})
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        scope["actor_proof_body"] = body
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)
