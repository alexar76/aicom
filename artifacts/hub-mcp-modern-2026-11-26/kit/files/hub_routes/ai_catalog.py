"""The AI Catalog door: /.well-known/ai-catalog.json, the nested catalogue of capabilities and
the MCP Server Card at /mcp/server-card.

See aimarket_hub/ai_catalog.py for the mapping and docs/ai-catalog.md for what a client sees.
Every route here is read-only and public; nothing in it moves money or changes the catalogue.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from importlib import resources
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from aimarket_hub import ai_catalog, ard
from aimarket_hub.config import HubConfig
from aimarket_hub.hub_routes.ard import ArdLinkHeader, served_bytes
from aimarket_hub.public_cache import ttl_from_env
from aimarket_hub.signing import Signer

#: The cards whose bytes the catalogue pins by digest. Both are built once per process.
_PINNED_DOCUMENTS = (ai_catalog.SERVER_CARD_PATH, ai_catalog.A2A_CARD_PATH)

_CARD_MAX_AGE_S = 3600
_CATALOG_MAX_AGE_S = 3600
_CAPABILITIES_MAX_AGE_S = 300
_PROFILE_MAX_AGE_S = 86400
_SIGNED_CACHE_MAX = 4096
_PROFILE_NAMES = ("did-web-eddsa-v1", "did-web-ml-dsa-65-v1")

#: What the Server Card extension asks of a hosted card (docs/discovery.md, "CORS Requirements"),
#: so a browser client can read the card and revalidate it with If-None-Match.
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET",
    "Access-Control-Allow-Headers": "Content-Type, If-None-Match",
    "Access-Control-Expose-Headers": "ETag",
}

ArdEntries = Callable[[], Awaitable[list[tuple[dict[str, Any], str]]]]


def _etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest() + '"'


def _matches(request: Request, etag: str) -> bool:
    """True when If-None-Match names this representation (a list, weak tags and ``*`` included)."""
    header = request.headers.get("if-none-match", "")
    if not header:
        return False
    names = {part.strip().removeprefix("W/") for part in header.split(",")}
    return "*" in names or etag in names


def register(
    *,
    app: FastAPI,
    config: HubConfig,
    signer: Signer,
    wellknown_router: APIRouter,
    ard_entries: ArdEntries,
) -> None:
    """Attach the AI Catalog routes to ``wellknown_router`` and the root Link header to ``app``.

    ``ard_entries`` is the ARD door's browse listing (hub_routes/ard.py): the offers the hub's
    own search shows, with the same descriptors and digests, so the two doors never disagree
    about an offer and neither lists one the catalogue hides.
    """
    from aimarket_hub import mcp_gateway
    from aimarket_hub.api import logger

    base = config.hub_url.rstrip("/")
    catalog_url = base + ai_catalog.WELL_KNOWN_PATH
    # The identity signatures are made under: the hub's did:web. The two profiles take a root
    # did:web without a port (as the specification's own profile does), so a hub served under a
    # path, over http or on a port publishes its catalogues unsigned rather than under a name no
    # verifier accepts.
    did = ard.did_web(base)
    if "%3A" in did:
        did = ""
    ml_dsa_65 = signer.sign_pq if signer.pq_public_key_b64 else None

    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _endorsed(entry: dict[str, Any]) -> dict[str, Any]:
        """``entry`` with this hub's Trust Manifest, when the hub publishes it and pins its bytes."""
        if not did or "digest" not in entry or ard.urn_publisher(entry["identifier"]) != did[len("did:web:"):]:
            return entry
        return {**entry, "trustManifests": [
            ai_catalog.trust_manifest(entry, did=did, issued_at=_now(), signature=signer.sign)]}

    def _snapshot(document: dict[str, Any]) -> dict[str, Any]:
        if not did:
            return document
        return ai_catalog.sign_catalog(document, did=did, issued_at=_now(), ed25519=signer.sign, ml_dsa_65=ml_dsa_65)
    app.add_middleware(ArdLinkHeader, link=f'<{catalog_url}>; rel="{ai_catalog.LINK_RELATION}"')

    def _problem(status: int, detail: str) -> JSONResponse:
        return JSONResponse(ard.ArdError(status, detail).problem(), status_code=status,
                            media_type=ard.PROBLEM_MEDIA_TYPE, headers={"Access-Control-Allow-Origin": "*"})

    def _document(request: Request, body: bytes, etag: str, media_type: str, max_age: int) -> Response:
        headers = {"Cache-Control": f"public, max-age={max_age}", "ETag": etag, **_CORS}
        if _matches(request, etag):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type=media_type, headers=headers)

    # ── the MCP Server Card ───────────────────────────────────

    card = ai_catalog.server_card(
        base,
        hub_name=config.hub_name,
        server_name=mcp_gateway.SERVER_NAME,
        server_version=mcp_gateway.SERVER_VERSION,
        protocol_versions=mcp_gateway.EVERY_PROTOCOL_VERSION,
        name_override=os.getenv("AIMARKET_MCP_SERVER_CARD_NAME", "").strip(),
        key_page=base + "/start",
    )
    card_problems = ai_catalog.server_card_problems(card)
    if card_problems:  # a bug here must not publish a card clients would reject
        logger.error("AI Catalog: the MCP Server Card is not valid and is not served: %s", card_problems)
    card_body = ard.stable_bytes(card)
    card_etag = _etag(card_body)

    @wellknown_router.api_route(ai_catalog.SERVER_CARD_PATH, methods=["GET", "HEAD"])
    async def mcp_server_card(request: Request):
        """This hub's MCP endpoint as a Server Card (SEP-2127), at ``<streamable-http-url>/server-card``."""
        if card_problems:
            return _problem(500, "this hub built a Server Card that does not match the schema")
        return _document(request, card_body, card_etag, ai_catalog.SERVER_CARD_TYPE, _CARD_MAX_AGE_S)

    # ── the catalogue at the well-known URI ───────────────────

    state: dict[str, Any] = {"catalog": None}
    catalog_lock = asyncio.Lock()

    async def _catalog() -> tuple[bytes, str] | None:
        """The catalogue's bytes and ETag, built once per process: every digest in it is of a
        document whose bytes do not change while the process runs."""
        if state["catalog"] is not None:
            return state["catalog"]
        async with catalog_lock:
            if state["catalog"] is not None:
                return state["catalog"]
            documents: dict[str, bytes] = {}
            for path in _PINNED_DOCUMENTS:
                data = await served_bytes(app, path)
                if data is not None:
                    documents[path] = data
            entries = [_endorsed(e) for e in ai_catalog.root_entries(base, config.hub_name, documents)]
            document = await run_in_threadpool(_snapshot, ai_catalog.catalog(base, config.hub_name, entries))
            found = ai_catalog.problems(document)
            if found:
                logger.error("AI Catalog: the catalogue is not valid and is not served: %s", found)
                return None
            body = ard.stable_bytes(document)
            state["catalog"] = (body, _etag(body))
            return state["catalog"]

    @wellknown_router.api_route(ai_catalog.WELL_KNOWN_PATH, methods=["GET", "HEAD"])
    async def ai_catalog_document(request: Request):
        """This hub's AI Catalog (https://ai-catalog.io/, section "Well-Known URI")."""
        built = await _catalog()
        if built is None:
            return _problem(500, "this hub built a catalogue that does not match the specification")
        return _document(request, built[0], built[1], ai_catalog.MEDIA_TYPE, _CATALOG_MAX_AGE_S)

    # ── what the hub sells, as a nested catalogue ─────────────

    # Rendered at most once per TTL. The entries come from the hub's own search (the ARD door's
    # browse listing), so an offer the catalogue hides is not listed here either; the search runs
    # only when the document is rebuilt, never per request.
    rendered: dict[str, Any] = {"at": 0.0, "value": None}
    capabilities_lock = asyncio.Lock()
    # Signed once per release and once per content: an entry's manifest is kept for its
    # (identifier, version, digest), and the snapshot signature for the unsigned document's bytes,
    # so the same catalogue is the same bytes (and the same ETag) however often it is rebuilt.
    endorsed_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
    snapshot_cache: dict[str, Any] = {"of": None, "document": None}

    def _endorsed_once(entry: dict[str, Any]) -> dict[str, Any]:
        key = (entry["identifier"], entry.get("version", ""), entry.get("digest", ""))
        cached = endorsed_cache.get(key)
        if cached is None:
            if len(endorsed_cache) >= _SIGNED_CACHE_MAX:
                endorsed_cache.clear()
            cached = endorsed_cache[key] = _endorsed(entry)
        return cached

    def _render(visible: list[tuple[dict[str, Any], str]]) -> tuple[bytes, str, dict[str, str]]:
        entries = [_endorsed_once(ai_catalog.capability_entry(entry, source, base, config.hub_name))
                   for entry, source in visible]
        entries.sort(key=lambda e: e["identifier"])
        document = ai_catalog.catalog(base, config.hub_name, entries)
        content = hashlib.sha256(ard.stable_bytes(document)).hexdigest()
        if snapshot_cache["of"] != content:
            snapshot_cache["of"], snapshot_cache["document"] = content, _snapshot(document)
        document = snapshot_cache["document"]
        found = ai_catalog.problems(document)
        if found:
            raise ValueError("; ".join(found[:5]))
        body = ard.stable_bytes(document)
        prefix = base + ai_catalog.IDS_PATH + "/"
        ids = {e["identifier"][len(prefix):]: e["url"] for e in entries if e["identifier"].startswith(prefix)}
        return body, _etag(body), ids

    def _fresh() -> tuple[bytes, str, dict[str, str]] | None:
        ttl = ttl_from_env("AIMARKET_AI_CATALOG_CACHE_S", 60.0)
        if rendered["value"] is not None and ttl > 0 and time.monotonic() - rendered["at"] < ttl:
            return rendered["value"]
        return None

    async def _capabilities() -> tuple[bytes, str, dict[str, str]]:
        value = _fresh()
        if value is not None:
            return value
        async with capabilities_lock:
            value = _fresh()  # somebody may have rebuilt it while we waited for the lock
            if value is not None:
                return value
            value = await run_in_threadpool(_render, await ard_entries())  # an error caches nothing
            rendered["at"], rendered["value"] = time.monotonic(), value
            return value

    @wellknown_router.api_route(ai_catalog.CAPABILITIES_PATH, methods=["GET", "HEAD"])
    async def ai_catalog_capabilities(request: Request):
        """Every sellable capability as a Catalog Entry; the catalogue above links here."""
        try:
            body, etag, _ids = await _capabilities()
        except ValueError as error:
            logger.error("AI Catalog: the capabilities catalogue is not valid and is not served: %s", error)
            return _problem(500, "this hub built a catalogue that does not match the specification")
        return _document(request, body, etag, ai_catalog.MEDIA_TYPE, _CAPABILITIES_MAX_AGE_S)

    @wellknown_router.api_route(ai_catalog.IDS_PATH + "/{name}", methods=["GET", "HEAD"])
    async def ai_catalog_identifier(name: str):
        """An identifier this hub assigned to a capability it copies from a peer: redirects to
        the capability's descriptor."""
        try:
            _body, _etag_value, ids = await _capabilities()
        except ValueError:
            ids = {}
        target = ids.get(name)
        if target is None:
            return _problem(404, "no capability in this hub's catalogue has that identifier")
        return RedirectResponse(target, status_code=303, headers={"Access-Control-Allow-Origin": "*"})

    # ── the signer profiles' definitions ──────────────────────

    profiles = {
        name: resources.files("aimarket_hub").joinpath(f"static/ai-catalog/profiles/{name}.md").read_bytes()
        for name in _PROFILE_NAMES
    }

    @wellknown_router.api_route(ai_catalog.PROFILES_PATH + "/{name}", methods=["GET", "HEAD"])
    async def ai_catalog_profile(name: str, request: Request):
        """The definition of a signer profile these catalogues name (a profile defined outside the
        AI Catalog specification is identified by a URL that serves its definition)."""
        body = profiles.get(name)
        if body is None:
            return _problem(404, "no signer profile with that name")
        return _document(request, body, _etag(body), "text/markdown; charset=utf-8", _PROFILE_MAX_AGE_S)
