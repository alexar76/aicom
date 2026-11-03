"""Fold same-origin OpenAPI documents into the hub's own ``/openapi.json``.

x402 indexers (x402scan, AgentCash, and the catalogues built on them) discover an origin's paid
routes from ``https://<origin>/openapi.json`` and nothing else. On a host where the hub owns that
path, paid routes served by a sidecar on the same origin (``/x402/*`` on modelmarket.dev) are
invisible unless the hub's document lists them.

``AIMARKET_OPENAPI_MERGE_URLS`` (comma-separated) names such documents. Each one must be on the
hub's own origin (``AIMARKET_HUB_URL``): the hub only vouches for routes its origin serves. They are
fetched in the background and on a timer, never on the request path; a failed fetch keeps the
last good copy. Only relative paths the hub does not already define are added, so a sidecar can
never shadow or rewrite a hub route.
"""
from __future__ import annotations

import copy
import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

REFRESH_S = 600.0
_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

_extra: dict[str, dict[str, Any]] = {}   # source url -> {path: path item}
_cache: tuple[int, int, dict[str, Any]] | None = None
_generation = 0


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}".lower() if p.scheme and p.netloc else ""


def merge_urls(hub_url: str | None = None) -> list[str]:
    """Configured documents that live on the hub's own origin; others are refused with a warning."""
    raw = os.getenv("AIMARKET_OPENAPI_MERGE_URLS", "")
    own = _origin(hub_url if hub_url is not None else os.getenv("AIMARKET_HUB_URL", ""))
    urls = []
    for url in (u.strip() for u in raw.split(",")):
        if not url:
            continue
        if not own or _origin(url) != own:
            logger.warning("openapi merge: %s is not on the hub's origin %s; ignored", url, own or "(unset)")
            continue
        urls.append(url)
    return urls


def accepted_paths(doc: Any, source_url: str) -> dict[str, dict[str, Any]]:
    """The path items of ``doc`` the hub may publish: relative paths with at least one operation,
    from a document that, if it names a server, names the origin it was fetched from."""
    if not isinstance(doc, dict) or not isinstance(doc.get("paths"), dict):
        return {}
    servers = doc.get("servers")
    if isinstance(servers, list) and servers:
        first = servers[0].get("url", "") if isinstance(servers[0], dict) else ""
        if _origin(first) != _origin(source_url):
            logger.warning("openapi merge: %s declares server %r, not its own origin; ignored", source_url, first)
            return {}
    out = {}
    for path, item in doc["paths"].items():
        if not (isinstance(path, str) and path.startswith("/") and not path.startswith("//")
                and "://" not in path and isinstance(item, dict)):
            continue
        ops = {m: op for m, op in item.items() if m in _METHODS and isinstance(op, dict)}
        if not ops:
            continue
        for op in ops.values():
            op.setdefault("security", [])
        out[path] = ops
    return out


def set_source(url: str, paths: dict[str, dict[str, Any]]) -> None:
    global _generation
    if _extra.get(url) != paths:
        _extra[url] = paths
        _generation += 1


async def refresh(urls: list[str], client: httpx.AsyncClient | None = None) -> None:
    """Fetch every configured document; a failure keeps that source's last good paths."""
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=10.0, follow_redirects=False)
    try:
        for url in urls:
            try:
                resp = await client.get(url, headers={"accept": "application/json"})
                resp.raise_for_status()
                paths = accepted_paths(resp.json(), url)
            except Exception as exc:  # network, status, JSON: keep what we had
                logger.warning("openapi merge: %s unavailable (%s); keeping the last good copy", url, exc)
                continue
            set_source(url, paths)
    finally:
        if own_client:
            await client.aclose()


def merged(base: dict[str, Any]) -> dict[str, Any]:
    """``base`` plus the accepted foreign paths the hub does not define itself (cached)."""
    global _cache
    if not _extra:
        return base
    if _cache and _cache[0] == id(base) and _cache[1] == _generation:
        return _cache[2]
    doc = copy.copy(base)
    paths = dict(base.get("paths") or {})
    for source in _extra.values():
        for path, item in source.items():
            paths.setdefault(path, item)
    doc["paths"] = paths
    _cache = (id(base), _generation, doc)
    return doc


def reset() -> None:
    """Tests only."""
    global _cache, _generation
    _extra.clear()
    _cache = None
    _generation += 1
