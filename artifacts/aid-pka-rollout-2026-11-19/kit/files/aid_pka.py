"""AID v2 endpoint proof (PKA) for the hub's MCP endpoint.

Agent Identity & Discovery v2.1.1 (https://aid.agentcommunity.org/docs/specification), Appendix B.
A domain publishes ``_agent.<domain> TXT "v=aid2;u=https://<host>/mcp;p=mcp;k=<key>"``. A client that
found the endpoint that way sends an RFC 9421 request for a response signature::

    Accept-Signature: aid-pka=("@method";req "@target-uri";req "@authority";req "@status");created;expires;
                      keyid="<jwk-thumbprint>";alg="ed25519";nonce="<client challenge>";tag="aid-pka-v2"
    AID-Domain: example.com            (optional: asks for a domain-bound proof, Appendix B.7)

and the endpoint answers whatever it answers, plus ``Signature-Input``, ``Signature`` and
``Cache-Control: no-store``. The signature covers the method, the target URI, the authority, the
``aid-domain`` header when the client sent one, and the status — so the client learns that the endpoint
it reached holds the key in DNS and, with ``aid-domain``, that the endpoint agrees to serve that domain.
An ``AID-Domain`` this hub does not serve gets 403 and no signature (B.7): the proof for that domain
fails, as the specification intends.

The request context is signed as the outside world sees it — the scheme, host and base path of
``hub_url`` — not the proxy-local values the app receives behind nginx (B.5).

The key is not the hub's signing key. It is derived from it with HKDF (``Signer.derived_ed25519_seed``,
info ``aimarket-hub/aid-pka-v2``): the signing input here contains a nonce the client chose, and the hub
key that signs receipts and manifests never signs such input. No new secret has to be provisioned; the
public key for the DNS record is printed by ``python -m aimarket_hub.aid_pka`` and logged at startup.

Switch it off with ``AIMARKET_AID_PKA=0``. ``AIMARKET_AID_DOMAINS`` (comma-separated) adds domains,
besides the host of ``hub_url``, for which the endpoint signs a domain-bound proof.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

logger = logging.getLogger("aimarket_hub.aid_pka")

#: HKDF ``info`` for the endpoint-proof key. Changing it changes the key, and the DNS record with it.
KEY_INFO = b"aimarket-hub/aid-pka-v2"
LABEL = "aid-pka"
TAG = "aid-pka-v2"
#: How long a proof is valid. AID: MUST NOT exceed 300 seconds, SHOULD be 60 or less.
VALIDITY_S = 60
BASE_COMPONENTS = ('"@method";req', '"@target-uri";req', '"@authority";req')
DOMAIN_COMPONENT = '"aid-domain";req'
STATUS_COMPONENT = '"@status"'
#: A nonce this endpoint will echo: an RFC 8941 string without the two characters that need escaping.
#: AID clients send unpadded base64url of at least 32 random bytes (43 characters).
_NONCE = re.compile(r'[\x20\x21\x23-\x5b\x5d-\x7e]{16,512}')
_DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def private_key(signer: Any) -> Ed25519PrivateKey:
    """The endpoint-proof key of the hub whose ``Signer`` this is."""
    return Ed25519PrivateKey.from_private_bytes(signer.derived_ed25519_seed(KEY_INFO))


def public_k(key: Ed25519PrivateKey) -> str:
    """The AID ``k`` value: the RFC 8037 JWK ``x`` member, unpadded base64url of the raw public key."""
    return _b64url(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw))


def keyid(k: str) -> str:
    """RFC 7638 JWK thumbprint of the Ed25519 key ``k`` (AID Appendix B.2)."""
    canonical = '{"crv":"Ed25519","kty":"OKP","x":"%s"}' % k
    return _b64url(hashlib.sha256(canonical.encode("utf-8")).digest())


def txt_record(uri: str, k: str, *, proto: str = "mcp", auth: str = "none", desc: str = "") -> str:
    """The ``_agent`` TXT value for ``uri`` with this key, short keys, as AID recommends."""
    parts = ["v=aid2", f"u={uri}", f"p={proto}", f"a={auth}"]
    if desc:
        parts.append(f"s={desc}")
    parts.append(f"k={k}")
    return ";".join(parts)


# ── the request ─────────────────────────────────────────────


def _split_top_level(value: str, sep: str) -> list[str]:
    """Split an RFC 8941 field on ``sep`` outside strings and inner lists."""
    out, buf, depth, in_str, esc = [], [], 0, False, False
    for ch in value:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == sep and depth == 0:
            out.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    out.append("".join(buf).strip())
    return [p for p in out if p]


def _sf_string(raw: str) -> str | None:
    if len(raw) < 2 or raw[0] != '"' or raw[-1] != '"':
        return None
    body, out, esc = raw[1:-1], [], False
    for ch in body:
        if esc:
            if ch not in '"\\':
                return None
            out.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            return None
        else:
            out.append(ch)
    return None if esc else "".join(out)


@dataclass(frozen=True)
class ProofRequest:
    nonce: str
    domain: str | None  # the AID-Domain value as sent, when the client asked for a bound proof
    domain_problem: str | None  # why that domain gets 403, when it does


def requested_proof(headers: list[tuple[bytes, bytes]], served: frozenset[str]) -> ProofRequest | None:
    """The proof a request asks for, or None when it asks for none this endpoint can give.

    None for: no ``aid-pka`` member in ``Accept-Signature``, another tag, or a nonce that is
    missing or not a plain RFC 8941 string. Such a request is answered as if nothing were asked."""
    accept: list[str] = []
    domains: list[str] = []
    for name, value in headers:
        lname = name.lower()
        if lname == b"accept-signature":
            accept.append(value.decode("latin-1"))
        elif lname == b"aid-domain":
            domains.append(value.decode("latin-1").strip())
    member = None
    for item in _split_top_level(", ".join(accept), ","):
        key, _, rest = item.partition("=")
        if key.strip() == LABEL:
            member = rest
    if member is None:
        return None
    pieces = _split_top_level(member, ";")
    params: dict[str, str] = {}
    for piece in pieces[1:]:
        k, _, v = piece.partition("=")
        params[k.strip()] = v.strip()
    if _sf_string(params.get("tag", "")) != TAG:
        return None
    nonce = _sf_string(params.get("nonce", ""))
    if nonce is None or not _NONCE.fullmatch(nonce):
        return None
    if not domains:
        return ProofRequest(nonce=nonce, domain=None, domain_problem=None)
    if len(domains) > 1:
        return ProofRequest(nonce=nonce, domain=domains[0], domain_problem="more than one AID-Domain header")
    domain = domains[0]
    if not _DOMAIN.fullmatch(domain):
        return ProofRequest(nonce=nonce, domain=domain,
                            domain_problem="AID-Domain must be a lowercase A-label host without port or trailing dot")
    if domain not in served:
        return ProofRequest(nonce=nonce, domain=domain, domain_problem=f"this endpoint does not serve {domain}")
    return ProofRequest(nonce=nonce, domain=domain, domain_problem=None)


# ── the signature ───────────────────────────────────────────


def signature_params(*, bound: bool, created: int, expires: int, kid: str, nonce: str) -> str:
    covered = [*BASE_COMPONENTS, *([DOMAIN_COMPONENT] if bound else []), STATUS_COMPONENT]
    return (f'({" ".join(covered)});created={created};expires={expires};keyid="{kid}";'
            f'alg="ed25519";nonce="{nonce}";tag="{TAG}"')


def signature_base(*, method: str, target_uri: str, authority: str, domain: str | None, status: int,
                   params: str) -> bytes:
    """RFC 9421 §2.5 signature base for the AID covered set: one line per component, the
    ``@signature-params`` line last, no trailing newline."""
    lines = [f'"@method";req: {method}', f'"@target-uri";req: {target_uri}', f'"@authority";req: {authority}']
    if domain is not None:
        lines.append(f'"aid-domain";req: {domain}')
    lines.append(f'"@status": {status}')
    lines.append(f'"@signature-params": {params}')
    return "\n".join(lines).encode("utf-8")


def public_origin(hub_url: str) -> tuple[str, str, str]:
    """``(scheme, authority, base path)`` of the hub as clients reach it. The authority is
    lowercase and carries the port only when it is not the scheme's default (B.5)."""
    parts = urlsplit(hub_url.strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    default = {"https": 443, "http": 80}.get(scheme)
    authority = host if port in (None, default) else f"{host}:{port}"
    return scheme, authority, parts.path.rstrip("/")


class AidPkaSigner:
    """Pure ASGI middleware: signs responses on ``paths`` for clients that ask (AID Appendix B)."""

    def __init__(self, app: Any, *, key: Ed25519PrivateKey, hub_url: str, paths: tuple[str, ...] = ("/mcp",),
                 domains: frozenset[str] = frozenset(), clock: Any = time.time) -> None:
        self.app = app
        self.key = key
        self.kid = keyid(public_k(key))
        self.scheme, self.authority, self.base_path = public_origin(hub_url)
        self.paths = paths
        self.domains = domains
        self.clock = clock

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") not in self.paths:
            await self.app(scope, receive, send)
            return
        request = requested_proof(scope.get("headers") or [], self.domains)
        if request is None:
            await self.app(scope, receive, send)
            return
        if request.domain_problem is not None:
            body = json.dumps({"error": "aid_domain_not_served", "detail": request.domain_problem}).encode()
            await send({"type": "http.response.start", "status": 403, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store")]})
            await send({"type": "http.response.body", "body": body})
            return
        query = scope.get("query_string") or b""
        target_uri = f"{self.scheme}://{self.authority}{self.base_path}{scope['path']}"
        if query:
            target_uri += "?" + query.decode("latin-1")
        method = str(scope.get("method") or "GET").upper()

        async def signed(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                created = int(self.clock())
                params = signature_params(bound=request.domain is not None, created=created,
                                          expires=created + VALIDITY_S, kid=self.kid, nonce=request.nonce)
                base = signature_base(method=method, target_uri=target_uri, authority=self.authority,
                                      domain=request.domain, status=int(message["status"]), params=params)
                signature = base64.b64encode(self.key.sign(base)).decode("ascii")
                headers = [(n, v) for n, v in (message.get("headers") or [])
                           if n.lower() not in (b"cache-control", b"signature-input", b"signature")]
                headers += [(b"cache-control", b"no-store"),
                            (b"signature-input", f"{LABEL}={params}".encode("latin-1")),
                            (b"signature", f"{LABEL}=:{signature}:".encode("latin-1"))]
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, signed)


def install(app: Any, *, signer: Any, hub_url: str, paths: tuple[str, ...] = ("/mcp",)) -> str | None:
    """Add the middleware to ``app`` unless ``AIMARKET_AID_PKA`` is off. Returns ``k`` (or None)."""
    if (os.environ.get("AIMARKET_AID_PKA") or "1").strip().lower() in ("0", "off", "false", "no"):
        return None
    _, authority, _ = public_origin(hub_url)
    host = authority.split(":", 1)[0]
    extra = {d.strip().lower() for d in (os.environ.get("AIMARKET_AID_DOMAINS") or "").split(",") if d.strip()}
    key = private_key(signer)
    app.add_middleware(AidPkaSigner, key=key, hub_url=hub_url, paths=paths, domains=frozenset({host, *extra}))
    k = public_k(key)
    logger.info("AID endpoint proof on %s: k=%s keyid=%s", ", ".join(paths), k, keyid(k))
    return k


def main(argv: list[str] | None = None) -> int:
    """Print ``k``, its keyid and the ``_agent`` TXT value for this hub's key."""
    import argparse

    from aimarket_hub.signing import Signer

    parser = argparse.ArgumentParser(prog="python -m aimarket_hub.aid_pka", description=main.__doc__)
    parser.add_argument("--key-path", default=os.environ.get("AIMARKET_SIGNING_KEY_PATH", "data/hub_signing_key"))
    parser.add_argument("--uri", default="https://modelmarket.dev/mcp")
    parser.add_argument("--desc", default="")
    args = parser.parse_args(argv)
    if not os.path.exists(args.key_path):
        parser.error(f"no key at {args.key_path}")
    k = public_k(private_key(Signer(args.key_path)))
    print(f"k      {k}\nkeyid  {keyid(k)}\nTXT    {txt_record(args.uri, k, desc=args.desc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
