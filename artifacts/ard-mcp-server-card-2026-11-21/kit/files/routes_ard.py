"""The ARD door: /.well-known/ard.json, /.well-known/did.json and the registry at /ard/v1.

See aimarket_hub/ard.py for the mapping and docs/ard.md for what a client sees. Every
route here is read-only and public; nothing in it moves money or changes the catalogue.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from aimarket_hub import aid_pka, ard
from aimarket_hub.access_policy import capability_access_mode
from aimarket_hub.catalog import catalogue_display_name
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.public_cache import PublicDocumentCache
from aimarket_hub.signing import Signer

#: Cards this hub serves at its origin whose bytes the manifest pins by digest. All are
#: built once per process, so a digest taken at startup stays true. The MCP entry uses the
#: Server Card at /mcp/server-card when the hub serves it, the older card otherwise
#: (ard.own_entries). (The discovery document is listed without a digest: own_entries says why.)
_PINNED_DOCUMENTS = ("/.well-known/agent-card.json", ard.MCP_SERVER_CARD_PATH, ard.LEGACY_MCP_CARD_PATH)

_MANIFEST_MAX_AGE_S = 3600
_DESCRIPTOR_MAX_AGE_S = 300
_SIGNED_CACHE_MAX = 4096


class ArdLinkHeader:
    """Pure ASGI middleware: ``Link: <…/.well-known/ard.json>; rel="ard"`` on the root page.

    draft-jimenez-dawn-ard-initial-contact-00 §4.3.2: a client that knows only the origin
    sends ``HEAD /`` and reads this header, whatever the status. Added to ``/`` only; the
    header costs nothing, but a Link on every response would be noise in every log.
    """

    def __init__(self, app: Any, *, link: str) -> None:
        self.app = app
        self.link = link.encode("latin-1")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != "/" or scope.get("method") not in ("GET", "HEAD"):
            await self.app(scope, receive, send)
            return

        async def with_link(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*(message.get("headers") or []), (b"link", self.link)]}
            await send(message)

        await self.app(scope, receive, with_link)


async def served_bytes(app: FastAPI, path: str) -> bytes | None:
    """The exact bytes ``app`` answers at ``path``, fetched through the app itself so a digest
    covers what a client receives, not a re-serialisation of it. None when the app does not
    answer 200 there. Shared by the ARD and AI Catalog doors."""
    import logging

    try:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 0), raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://hub.internal", timeout=10) as client:
            response = await client.get(path)
        return response.content if response.status_code == 200 else None
    except Exception:  # noqa: BLE001 - a card that cannot be read is left out, not guessed
        logging.getLogger("aimarket_hub.api").warning("could not read %s for its digest", path, exc_info=True)
        return None


def register(
    *,
    app: FastAPI,
    config: HubConfig,
    db: HubDatabase,
    search: Callable[..., Awaitable[Any]],
    signer: Signer,
    wellknown_router: APIRouter,
) -> Callable[[], Awaitable[list[tuple[dict[str, Any], str]]]]:
    """Attach the ARD routes to ``wellknown_router`` and the root Link header to ``app``.

    Returns ``visible_entries``: every offer the hub's own search shows, as ``(ARD entry,
    publishing hub)`` in browse order. The AI Catalog door reads it, so both doors publish the
    same offers, descriptors and digests, and neither lists what the catalogue hides."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import _catalogue_snapshot

    base = config.hub_url.rstrip("/")
    did = ard.did_web(base)
    manifest_url = base + ard.WELL_KNOWN_PATH
    app.add_middleware(ArdLinkHeader, link=f'<{manifest_url}>; rel="ard"')
    # AID endpoint proof on /mcp, the endpoint the manifest's MCP entry leads to: a client that found
    # it through the domain's `_agent` record can check that this is the endpoint the domain named.
    aid_pka.install(app, signer=signer, hub_url=base)

    def _now() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def _problem(error: ard.ArdError) -> JSONResponse:
        return JSONResponse(error.problem(), status_code=error.status, media_type=ard.PROBLEM_MEDIA_TYPE)

    def _sign(entry: dict[str, Any]) -> dict[str, Any]:
        if not did:
            return entry
        return {**entry, "trustManifest": ard.sign_trust_manifest(signer, did, ard.subject_of(entry), _now())}

    # ── the well-known manifest ───────────────────────────────

    state: dict[str, Any] = {"manifest": None}
    manifest_lock = asyncio.Lock()

    async def _manifest() -> tuple[bytes, str]:
        """The manifest's bytes and ETag, built once per process: every entry in it is a
        document whose bytes do not change while the process runs."""
        if state["manifest"] is not None:
            return state["manifest"]
        async with manifest_lock:
            if state["manifest"] is not None:
                return state["manifest"]
            documents: dict[str, bytes] = {}
            for path in _PINNED_DOCUMENTS:
                data = await served_bytes(app, path)
                if data is not None:
                    documents[path] = data
            entries = ard.own_entries(base, config.hub_name, documents)
            body = ard.stable_bytes({"entries": [_sign(e) for e in entries]})
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            state["manifest"] = (body, etag)
            return state["manifest"]

    @wellknown_router.api_route(ard.WELL_KNOWN_PATH, methods=["GET", "HEAD"])
    async def ard_manifest(request: Request):
        """This hub's ARD manifest (draft-jimenez-dawn-ard-initial-contact-00 §4.3.1)."""
        body, etag = await _manifest()
        headers = {
            "Cache-Control": f"public, max-age={_MANIFEST_MAX_AGE_S}",
            "ETag": etag,
            "Access-Control-Allow-Origin": "*",
        }
        if request.headers.get("if-none-match", "").strip() == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type=ard.MANIFEST_MEDIA_TYPE, headers=headers)

    @wellknown_router.api_route(ard.DID_PATH, methods=["GET", "HEAD"])
    async def did_document():
        """The did:web document the ARD trustManifests name as their identity."""
        if not did:
            return _problem(ard.ArdError(404, "this hub is not served at an https origin root, "
                                              "so it has no did:web identity"))
        return Response(
            content=ard.stable_bytes(ard.did_document(did, signer.public_key_b64, signer.pq_public_key_b64)),
            media_type=ard.DID_MEDIA_TYPE,
            headers={"Cache-Control": f"public, max-age={_MANIFEST_MAX_AGE_S}",
                     "Access-Control-Allow-Origin": "*"},
        )

    # ── the catalogue as ARD entries ──────────────────────────

    signed_cache: dict[tuple[str, str], dict[str, Any]] = {}
    peer_tags: dict[str, list[str]] = {}

    def _tags(source_hub: str) -> list[str]:
        """A federated row's tags: the categories its hub declares in its well-known."""
        if not source_hub or source_hub == "local":
            return []
        if source_hub not in peer_tags:
            try:
                peer = db.get_peer(source_hub)
            except Exception:  # noqa: BLE001 - a lookup must never fail a search
                peer = None
            declared = getattr(peer, "categories", None) or []
            peer_tags[source_hub] = sorted({str(c).strip().lower() for c in declared
                                            if isinstance(c, str) and str(c).strip()})[:20]
        return peer_tags[source_hub]

    def _signed(made: ard.CapabilityEntry) -> dict[str, Any]:
        """A local entry with this hub's trustManifest; signed once per (identifier, digest)."""
        if not made.local or not did:
            return made.entry
        key = (made.entry["identifier"], made.entry["digest"])
        cached = signed_cache.get(key)
        if cached is None:
            if len(signed_cache) >= _SIGNED_CACHE_MAX:
                signed_cache.clear()
            cached = _sign(made.entry)
            signed_cache[key] = cached
        return cached

    # The sellable snapshot as ARD entries, rebuilt at most once per TTL: a catalogue walk is
    # 0.3-1 s on a crowded host, and these routes are public and unauthenticated. Built in a
    # worker thread; the builder never calls the cache (its lock is not re-entrant).
    entries_cache = PublicDocumentCache("AIMARKET_ARD_CACHE_S", 60.0)

    def _build_entries() -> dict[tuple[str, str, str], tuple[dict[str, Any], str]]:
        out: dict[tuple[str, str, str], tuple[dict[str, Any], str]] = {}
        for cap in _catalogue_snapshot(db, config):
            made = ard.capability_entry(cap, base, display_name=catalogue_display_name(cap),
                                        access_mode=capability_access_mode(cap), tags=_tags(cap.source_hub))
            out[(cap.product_id, cap.capability_id, cap.source_hub or "local")] = (_signed(made), made.source)
        return out

    async def _ranked(text: str) -> list[tuple[dict[str, Any], int, str]]:
        """``(entry, score, source)`` for every offer the hub's own search returns for
        ``text``, in its order. Empty text is the catalogue in browse order."""
        answer = await search(intent=text, limit=0)
        by_key = await run_in_threadpool(entries_cache.get, "entries", _build_entries)
        out: list[tuple[dict[str, Any], int, str]] = []
        for match in answer.get("matches", []):
            key = (match.get("product_id"), match.get("capability_id"), match.get("source_hub") or "local")
            found = by_key.get(key)
            if found is None:
                continue  # offered by search but not in the sellable snapshot: skipped, not guessed
            entry, source = found
            out.append((entry, ard.score(match.get("score") or 0.0) if text else 0, source))
        return out

    async def _json_body(request: Request) -> dict[str, Any]:
        try:
            body = json.loads(await request.body() or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise ard.ArdError(400, "the request body is not JSON") from None
        if not isinstance(body, dict):
            raise ard.ArdError(400, "the request body must be a JSON object")
        return body

    @wellknown_router.get(ard.REGISTRY_PATH)
    async def ard_registry():
        """What this registry implements. Not defined by ARD; a client may ignore it."""
        return JSONResponse({
            "registry": base + ard.REGISTRY_PATH,
            "manifest": manifest_url,
            "endpoints": {
                "search": {"method": "POST", "url": base + ard.REGISTRY_PATH + "/search"},
                "explore": {"method": "POST", "url": base + ard.REGISTRY_PATH + "/explore"},
                "agents": {"method": "GET", "url": base + ard.REGISTRY_PATH + "/agents"},
            },
            "federation": {
                "supported": list(ard.FEDERATION_MODES),
                "note": (
                    "This hub copies the catalogues of the peers it admits (AIMarket federation), "
                    "so 'auto' and 'none' both answer from the local index, which already holds "
                    "the admitted peers' entries; no query is forwarded. 'referrals' adds no "
                    "referrals for now."
                ),
            },
            "filterTerms": list(ard.FILTER_TERMS),
            "facetFields": list(ard.FACET_FIELDS),
            "score": "relevance of the hub's catalogue search (lexical and multilingual concepts), 0..100",
            "signing": {"identity": did or None, "algorithm": "EdDSA" if did else None,
                        "didDocument": base + ard.DID_PATH if did else None},
            "protocol": "aimarket-v2",
        }, headers={"Access-Control-Allow-Origin": "*"})

    @wellknown_router.post(ard.REGISTRY_PATH + "/search")
    async def ard_search(request: Request):
        """POST /search (draft-bu-dawn-ard-discovery-00 §4.2.2)."""
        try:
            body = await _json_body(request)
            query = ard.parse_query(body.get("query"), text_required=True)
            federation = body.get("federation", "auto")
            if federation not in ard.FEDERATION_MODES:
                raise ard.ArdError(400, "federation must be one of auto, referrals, none")
            fp = ard.fingerprint("search", query.text, query.filter)
            size, offset = ard.parse_page(body.get("pageSize"), body.get("pageToken"), fp)
        except ard.ArdError as error:
            return _problem(error)
        ranked = [r for r in await _ranked(query.text) if ard.matches_filter(r[0], query.filter)]
        window = ranked[offset:offset + size]
        answer: dict[str, Any] = {
            "results": [ard.search_item(e, score_value=s, source=src) for e, s, src in window],
        }
        if federation == "referrals":
            answer["referrals"] = []
        if offset + size < len(ranked):
            answer["nextPageToken"] = ard.page_token(offset + size, fp)
        return JSONResponse(answer)

    @wellknown_router.post(ard.REGISTRY_PATH + "/explore")
    async def ard_explore(request: Request):
        """POST /explore (§4.2.3): facet counts over the entries a query selects."""
        try:
            body = await _json_body(request)
            query = ard.parse_query(body.get("query"), text_required=False)
            facets = ard.parse_facets(body.get("resultType"))
        except ard.ArdError as error:
            return _problem(error)
        entries = [e for e, _s, _src in await _ranked(query.text) if ard.matches_filter(e, query.filter)]
        return JSONResponse({"resultType": "facets", "facets": ard.facet_counts(entries, facets)})

    @wellknown_router.get(ard.REGISTRY_PATH + "/agents")
    async def ard_agents(request: Request):
        """GET /agents (§4.2.4): every entry, ordered by identifier, filtered by query
        parameters named like the filter terms (repeat a parameter for OR)."""
        params = request.query_params
        try:
            raw_filter: dict[str, list[str]] = {}
            for name, value in params.multi_items():
                if name in ("pageSize", "pageToken"):
                    continue
                raw_filter.setdefault(name, []).append(value)
            flt = ard.parse_filter(raw_filter)
            fp = ard.fingerprint("agents", flt)
            size, offset = ard.parse_page(params.get("pageSize"), params.get("pageToken"), fp)
        except ard.ArdError as error:
            return _problem(error)
        entries = sorted((e for e, _s, _src in await _ranked("")), key=lambda e: e["identifier"])
        entries = [e for e in entries if ard.matches_filter(e, flt)]
        answer: dict[str, Any] = {"entries": entries[offset:offset + size]}
        if offset + size < len(entries):
            answer["nextPageToken"] = ard.page_token(offset + size, fp)
        return JSONResponse(answer, headers={"Access-Control-Allow-Origin": "*"})

    @wellknown_router.api_route(ard.REGISTRY_PATH + "/capability", methods=["GET", "HEAD"])
    async def ard_capability(product_id: str = "", capability_id: str = "", source_hub: str = "local"):
        """The descriptor an entry's ``url`` names: the bytes its ``digest`` pins."""
        snapshot = await run_in_threadpool(_catalogue_snapshot, db, config)
        cap = next((c for c in snapshot if c.product_id == product_id and c.capability_id == capability_id
                    and (c.source_hub or "local") == (source_hub or "local")), None)
        if cap is None:
            return _problem(ard.ArdError(404, "no sellable capability with that product_id, "
                                              "capability_id and source_hub"))
        made = ard.capability_entry(cap, base, display_name=catalogue_display_name(cap),
                                    access_mode=capability_access_mode(cap), tags=[])
        return Response(
            content=made.descriptor,
            media_type=ard.CAPABILITY_TYPE,
            headers={"Cache-Control": f"public, max-age={_DESCRIPTOR_MAX_AGE_S}",
                     "ETag": '"' + made.entry["digest"].split(":", 1)[1] + '"',
                     "Access-Control-Allow-Origin": "*"},
        )

    async def visible_entries() -> list[tuple[dict[str, Any], str]]:
        return [(entry, source) for entry, _score, source in await _ranked("")]

    return visible_entries
