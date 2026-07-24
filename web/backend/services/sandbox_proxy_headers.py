"""Headers safe to forward from the factory API into sandbox upstreams."""

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
    return out
