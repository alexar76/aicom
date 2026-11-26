"""How long a discovery document or catalogue stays valid, said and read in plain HTTP.

Outgoing: the hub's discovery documents and signed catalogue carry ``Cache-Control`` with
``max-age`` (how long a copy may be used without asking again) and ``stale-if-error`` (RFC 5861:
how long a copy may still be used when asking again fails), plus an ``ETag`` so a reader can
revalidate with ``If-None-Match`` and get ``304``. ``stale-if-error`` is the federation bound
(``federated_max_unverified_s``): the same period this hub keeps other hubs' entries after a
failed read.

Both documents are signed and re-signed on every build, so their bytes change with each
signature and generation time. Their ETag is therefore weak (RFC 9110 §8.8.1) and computed over
the content without those fields: two responses with the same ETag list the same things.

Incoming: :func:`stated_period` reads a peer's ``Cache-Control`` into the number of seconds the
peer says its catalogue may be used, failures included, or ``None`` when it says nothing usable.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from starlette.requests import Request

_DIRECTIVE = re.compile(r"\s*([A-Za-z-]+)\s*(?:=\s*\"?(\d+)\"?)?\s*")


def cache_control(max_age_s: int, stale_if_error_s: int) -> str:
    value = f"public, max-age={max(0, int(max_age_s))}"
    if stale_if_error_s > 0:
        value += f", stale-if-error={int(stale_if_error_s)}"
    return value


def weak_etag(content: Any) -> str:
    """``W/"<sha256 of the canonical JSON of content>"``."""
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return 'W/"' + hashlib.sha256(canonical.encode("utf-8")).hexdigest() + '"'


def not_modified(request: Request | None, etag: str) -> bool:
    """True when the request's If-None-Match names ``etag`` (weak comparison, lists, ``*``)."""
    if request is None:
        return False
    header = request.headers.get("if-none-match", "")
    if not header:
        return False
    names = {part.strip().removeprefix("W/") for part in header.split(",")}
    return "*" in names or etag.removeprefix("W/") in names


def headers(etag: str, max_age_s: int, stale_if_error_s: int) -> dict[str, str]:
    return {"ETag": etag, "Cache-Control": cache_control(max_age_s, stale_if_error_s)}


def stated_period(cache_control_header: str | None) -> int | None:
    """Seconds a peer says its response may be used, a failed refresh included.

    ``max-age`` + ``stale-if-error`` when either is given; ``no-store`` or ``no-cache`` alone
    count as 0 (use only what was just read). ``None`` when the header says nothing about time,
    so the reader's own period applies. A malformed header is treated as absent.
    """
    if not cache_control_header:
        return None
    directives: dict[str, int | None] = {}
    for part in cache_control_header.split(","):
        found = _DIRECTIVE.fullmatch(part)
        if not found:
            continue
        name = found.group(1).lower()
        directives[name] = int(found.group(2)) if found.group(2) is not None else None
    max_age = directives.get("max-age")
    stale = directives.get("stale-if-error")
    if max_age is None and stale is None:
        if "no-store" in directives or "no-cache" in directives:
            return 0
        return None
    return (max_age or 0) + (stale or 0)
