"""Headers and URL helpers for factory → sandbox upstream proxying."""

from __future__ import annotations

from fastapi import Request

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
    # Product JWTs must reach the generated API; factory cookies/CSRF stay blocked.
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        out["Authorization"] = auth
    return out
