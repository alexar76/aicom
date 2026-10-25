"""Headers and URL helpers for factory → sandbox upstream proxying."""

from __future__ import annotations

from fastapi import Request


def _is_factory_bearer(request: Request, token: str) -> bool:
    """Keep both factory issuers' credentials out of generated applications.

    Signature identification deliberately ignores expiry/revocation: even an
    expired session's claims belong to the factory. If either issuer cannot be
    checked, refusing forwarding is safer than handing it to an untrusted app.
    """
    import jwt
    from jwt.exceptions import PyJWTError

    from web.backend.services.commerce import _resolve_customer_jwt_secret

    try:
        security = request.app.state.security_manager
        issuers = (
            (security.secret_key, security.jwt_algorithm),
            (_resolve_customer_jwt_secret(), "HS256"),
        )
    except (AttributeError, KeyError, RuntimeError, OSError):
        return True
    for secret, algorithm in issuers:
        try:
            jwt.decode(token, secret, algorithms=[algorithm], options={
                "verify_exp": False, "verify_nbf": False, "verify_iat": False,
                "verify_aud": False, "verify_sub": False, "verify_jti": False,
            })
        except PyJWTError:
            continue
        return True
    return False

# Never forward session/auth from the operator browser into LLM-generated sandboxes.
_BLOCKED_PREFIXES = (
    "authorization",
    "cookie",
    "x-csrf-token",
    "x-csrf",
    "proxy-authorization",
    "set-cookie",
)

_BLOCKED_EXACT = frozenset(
    {
        "host",
        "connection",
        "content-length",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
    }
)


def sandbox_proxy_upstream_url(host: str, port: int, path: str, query: str = "") -> str:
    """Build the upstream URL, preserving the requested path exactly."""
    cleaned = (path or "").lstrip("/")
    url = f"http://{host}:{int(port)}/{cleaned}"
    if query:
        return f"{url}?{query}"
    return url


def sandbox_proxy_slash_variant(url: str) -> str | None:
    """Return the same URL without its trailing path slash, or ``None``.

    Generated SPAs often request ``/api/v1/accounts/`` while the router serves
    ``/api/v1/accounts``. Normally FastAPI would redirect, but a product's SPA
    catch-all matches the slash form first and answers 404. The proxy retries
    the slash-less variant *only after* the original 404s, so products that
    genuinely serve trailing-slash routes keep working.
    """
    head, sep, query = url.partition("?")
    if not head.endswith("/"):
        return None
    stripped = head.rstrip("/")
    # Never collapse the origin root ("http://host:port/") into a path-less URL.
    if stripped.count("/") < 3:
        return None
    return stripped + sep + query


def sandbox_proxy_forward_headers(request: Request) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in request.headers.items():
        lk = key.lower()
        if lk in _BLOCKED_EXACT:
            continue
        if lk.startswith("x-forwarded-"):
            continue
        if any(lk == p or lk.startswith(f"{p}-") for p in _BLOCKED_PREFIXES):
            continue
        out[key] = value
    # Only an independent product token may reach generated code. The factory
    # admin Bearer used to authorize this proxy is not a product credential.
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer ") and not _is_factory_bearer(request, auth[7:].strip()):
        out["Authorization"] = auth
    return out
