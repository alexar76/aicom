"""HTTP surface: the desk, the public API, the log, /check, badges, and the federation peer.

Everything here is read-only except three doors: ``/api/v1/check`` (rate-limited; writes a
digest count only when the caller opts in), the operator's ``/api/v1/admin/*`` (token), and
the hub's ``/ai-market/v2/invoke`` (the same read-only lookups as capabilities).
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from histor import __version__, badge, fingerprints, toolcost
from histor.check import MAX_MATCHES, CheckError
from histor.checkpoint import (
    COSIGNATURE_V1_TYPE,
    LOG_KEY_TYPE,
    NoteError,
    parse_signature_line,
    sign_checkpoint,
    vkey,
)
from histor.declared import public as declared_public
from histor.labels import SHORT
from histor.lookalike import default_index
from histor.receipts import AnchorRefused
from histor.service import Services, crawl_in_background, scheduler
from histor.untrusted import TooDeep, loads_limited

PRODUCT_ID = "histor"
MAX_CHECK_BYTES = 2 * 1024 * 1024


async def read_bounded_body(request: Request, limit: int) -> bytes:
    """Stop reading an untrusted stream as soon as it exceeds its budget."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > limit:
            raise HTTPException(status_code=413, detail=f"body larger than {limit} bytes")
        body.extend(chunk)
    return bytes(body)


SPA_ROUTES = ("/", "/servers", "/changes", "/log", "/check", "/about", "/stats")
VC_MEDIA = "application/vc"

CAPS = (
    # Order matters to a Hub's admission assay, which probes the first free capabilities with an
    # input built from their schemas: `changes` answers any input, so it goes first.
    {
        "capability_id": "histor.changes@v1",
        "name": "Recent MCP tool-definition changes",
        "description": (
            "The newest tool-definition changes HISTOR observed at remote MCP endpoints in the official registry: "
            "which tools were added, removed or modified, any outside address (host, e-mail, IP) that newly appeared, "
            "and a link to each full diff."
        ),
        "price_per_call_usd": 0.0,
        "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}},
    },
    {
        "capability_id": "histor.check@v1",
        "name": "Check an MCP tool set against the log",
        "description": (
            "Send an MCP endpoint (or registry name) and the tools/list you received, or its MTL/1 digest. "
            "Returns, signed: whether HISTOR observed the same set there, since when, earlier sets, the "
            "WARDEN pattern matches for it, and the stored advisory classifier verdict if HISTOR has one "
            "(any language; one model's opinion, not a log label). Says what was advertised, never that a "
            "server is safe."
        ),
        "price_per_call_usd": 0.0,
        "input_schema": {
            "type": "object",
            "properties": {
                "endpoint": {"type": "string", "description": "the MCP endpoint URL"},
                "name": {"type": "string", "description": "or the server's registry name"},
                "tools": {"type": "array", "description": "the tools array of the tools/list result you received"},
                "toolSetDigest": {"type": "string", "description": "or its MTL/1 tool-set digest (sha256-…)"},
                "contribute": {"type": "boolean", "description": "add (endpoint, digest, day) to a public count"},
            },
        },
    },
    {
        "capability_id": "histor.server@v1",
        "name": "MCP server observation record",
        "description": (
            "HISTOR's observation record for one MCP endpoint (or every endpoint of a registry name): tool-set "
            "digest, tool count, first pinned, last observed, unchanged since, change count and last status, "
            "with links to the full record and its labels."
        ),
        "price_per_call_usd": 0.0,
        "input_schema": {"type": "object", "properties": {"endpoint": {"type": "string"}, "name": {"type": "string"}}},
    },
)


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


# The desk's INVISIBLE pattern (desk.js): shown as ⟨U+…⟩ so a hidden character stays visible.
_INVISIBLE = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f­͏؜ᅟᅠ឴឵"
                        "᠋-᠏​-‏‪-‮⁠-⁯ㅤ︀-️﻿ﾠ￰-￻"
                        "\U000e0000-\U000e007f]")
PRERENDER_TOOLS = 100
PRERENDER_CHARS = 400


def _shown(text: Any, limit: int = PRERENDER_CHARS) -> str:
    """Publisher text as escaped HTML: invisible characters named, cut at ``limit``."""
    s = str(text or "")
    s = s if len(s) <= limit else s[:limit].rstrip() + " …"
    return xml_escape(_INVISIBLE.sub(lambda m: f"⟨U+{ord(m.group()):04X}⟩", s))


def _server_prerender(t: dict[str, Any], tools_json: str | None) -> str:
    """What the desk shows for one server, as plain HTML inside #view.

    Without it all /s/<id> pages were the landing page with another <title> — 99.7% the same
    text — and search engines indexed three of 39k. desk.js replaces #view on load, so a
    browser with scripts sees the desk as before; crawlers and readers without scripts get the
    record. Facts only, the publisher's text escaped: HISTOR never calls a server safe.
    """
    name = t["title"] or t["name"]
    day = lambda v: str(v)[:10] if v else "—"  # noqa: E731
    facts = (("First observed", day(t["first_pinned"])), ("Unchanged since", day(t["unchanged_since"])),
             ("Last observed", day(t["last_ok"])), ("Observations", t["ok_observations"]),
             ("Changes on record", t["changes"]), ("Tools", "—" if t["current_count"] is None else t["current_count"]))
    out = [f'<div class="detail"><h2>{_shown(name, 200)}</h2>',
           f'<p class="mono faint">{_shown(t["name"], 200)} · {_shown(t["endpoint"], 300)}</p>']
    if t["description"]:
        out.append(f'<p class="muted">{_shown(t["description"])}</p>')
    out.append('<dl class="facts">' + "".join(f"<div class=\"fact\"><dt class=\"k\">{k}</dt><dd class=\"v\">{_shown(v)}</dd></div>"
                                             for k, v in facts) + "</dl>")
    try:
        tools = json.loads(tools_json) if tools_json else []
    except ValueError:
        tools = []
    tools = [x for x in tools if isinstance(x, dict)] if isinstance(tools, list) else []
    if tools:
        out.append(f'<h3 class="block-h">Tool definitions as last observed ({len(tools)})</h3><ul class="prerender-tools">')
        out += [f"<li><code>{_shown(x.get('name'), 120)}</code> — {_shown(x.get('description'))}</li>" for x in tools[:PRERENDER_TOOLS]]
        if len(tools) > PRERENDER_TOOLS:
            out.append(f"<li>… and {len(tools) - PRERENDER_TOOLS} more</li>")
        out.append("</ul>")
    out.append('<p class="faint">The signed observations, every earlier tool set and a diff of each change: this page '
               f'with scripts on, or <code>/api/v1/servers/{t["id"]}</code>.</p></div>')
    return "".join(out)


class RateLimiter:
    """Sliding window per key. In memory: one instance serves the site, so that is enough.

    Memory is bounded for real: once more than ``max_keys`` keys exist, keys whose newest hit is
    older than the longest window are dropped — at most once a minute, so a spray of addresses
    costs one sweep per minute rather than one per request.
    """

    def __init__(self, max_keys: int = 50000, longest_window_s: float = 86400) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self.max_keys = max_keys
        self.longest_window_s = longest_window_s
        self._swept = 0.0

    def allow(self, key: str, limit: int, window_s: float) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > self.max_keys and now - self._swept > 60:
                self._swept = now
                stale = [k for k, v in self._hits.items() if not v or now - v[-1] > self.longest_window_s]
                for k in stale:
                    del self._hits[k]
            hits = self._hits[key]
            while hits and now - hits[0] > window_s:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(now)
            return True


def _xml_text(value: Any) -> str:
    """Escaped, and stripped of the characters XML 1.0 cannot carry at all (a tool name may hold them)."""
    text = "".join(ch for ch in str(value) if ch in "\t\n\r" or ("\x20" <= ch <= "\ud7ff")
                   or ("\ue000" <= ch <= "\ufffd") or ch >= "\U00010000")
    return xml_escape(text)



def _json_or_none(text: str | None) -> Any:
    try:
        return json.loads(text) if text else None
    except ValueError:
        return None

def create_app(services: Services) -> FastAPI:
    settings = services.settings
    store = services.store
    limiter = RateLimiter()
    proxies = []
    for entry in settings.trusted_proxies:
        try:
            proxies.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        thread = threading.Thread(target=scheduler, args=(services,), name="histor-scheduler", daemon=True)
        thread.start()
        yield
        services.stop.set()

    # No Swagger page: it loads its script from a CDN with inline boot code, which the production
    # CSP (script-src 'self') rightly blocks — it rendered blank. The schema itself is served.
    app = FastAPI(title="HISTOR", version=__version__, docs_url=None, redoc_url=None,
                  openapi_url="/api/openapi.json", lifespan=lifespan)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        path = request.url.path
        if path.startswith("/assets/"):
            # Page code must revalidate (a 304 is cheap) or a returning visitor keeps running last
            # week's desk against this week's API; fonts and the pinned three.js never change.
            immutable = path.startswith(("/assets/fonts/", "/assets/vendor/"))
            response.headers["Cache-Control"] = "public, max-age=604800" if immutable else "no-cache"
        if path.startswith(("/api/", "/badge/", "/.well-known/", "/ai-market/", "/feed.xml")):
            # Public, unauthenticated, read-only data: any origin may read it (the GitHub Pages
            # landing reads the live counters from here).
            response.headers.setdefault("Access-Control-Allow-Origin", "*")
        return response

    @app.options("/api/v1/check")
    @app.options("/ai-market/v2/invoke")
    def preflight() -> Response:
        # A JSON POST from another origin (the GitHub Pages desk) is preceded by this. No
        # credentials are ever accepted, so the wildcard origin is safe.
        return Response(status_code=204, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        })

    def client_ip(request: Request) -> str:
        peer = request.client.host if request.client else ""
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer or "unknown"
        if any(peer_ip in net for net in proxies):
            forwarded = request.headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[-1].strip() or peer
            real = request.headers.get("x-real-ip", "").strip()
            if real:
                return real
        return peer

    def last_crawl_error() -> str | None:
        """The newest crawl's error, from memory or — after a restart — from the runs table.

        In memory only, a failed crawl vanished from /health on the next restart, and a monitor
        polling /health never saw it (audit F24).
        """
        if services.last_error:
            return services.last_error
        last = store.last_run(finished_only=True)
        return (last or {}).get("stats", {}).get("error") if last else None

    def operator(request: Request) -> None:
        token = settings.operator_token
        given = request.headers.get("x-histor-operator", "")
        if not token:
            raise HTTPException(status_code=503, detail="operator token not configured")
        if not hmac.compare_digest(given.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="operator token required")

    # -- desk -----------------------------------------------------------------------

    index_file = settings.landing_dir / "index.html"

    def spa() -> Response:
        """The desk. One file serves both the service and GitHub Pages: relative asset paths
        work under /histor/ on Pages, and here a <base href="/"> makes them resolve from /s/<id>."""
        if not index_file.is_file():
            raise HTTPException(status_code=404, detail="landing missing")
        page = index_file.read_text(encoding="utf-8").replace("<!--HISTOR:BASE-->", '<base href="/">', 1)
        return Response(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    for route in SPA_ROUTES:
        # HEAD too: link checkers and card fetchers probe with HEAD, and 405 reads as "down".
        app.add_api_route(route, spa, methods=["GET", "HEAD"], include_in_schema=False)

    @app.get("/s/{target_id}", include_in_schema=False)
    def server_page(target_id: str) -> Response:
        """The desk, with this server's own title and description in the HTML: what a search engine
        and a link preview read. Facts only — HISTOR never calls a server safe."""
        page = spa()
        t = store.target(target_id) if re.fullmatch(r"[0-9a-f]{16}", target_id) else None
        if t is None:
            return page
        kind = "npm/PyPI package" if t["transport"] == "stdio" else "MCP server"
        name = t["title"] or t["name"]
        what = f"{t['current_count']} tools" if t["current_count"] is not None else "its tools"
        since = f", unchanged since {str(t['unchanged_since'])[:10]}" if t["unchanged_since"] else ""
        changes = f", {t['changes']} change{'s' if t['changes'] != 1 else ''} on record" if t["changes"] else ""
        title = f"{name} — {kind} record · HISTOR"
        desc = (f"What {t['endpoint']} tells AI models ({what}){since}{changes}: signed observations, a diff of every "
                f"change{', and what the package did in HISTOR’s sandbox' if t['transport'] == 'stdio' else ''}.")
        url = f"{settings.public_base}/s/{target_id}"
        html = page.body.decode("utf-8")
        html = re.sub(r"<title>.*?</title>", f"<title>{xml_escape(title)}</title>", html, count=1, flags=re.S)
        html = re.sub(r'<meta name="description" content="[^"]*"/>', f'<meta name="description" content="{xml_escape(desc, {chr(34): "&quot;"})}"/>', html, count=1)
        html = re.sub(r'<link rel="canonical" href="[^"]*"/>', f'<link rel="canonical" href="{xml_escape(url)}"/>', html, count=1)
        html = re.sub(r'<meta property="og:title" content="[^"]*"/>', f'<meta property="og:title" content="{xml_escape(title, {chr(34): "&quot;"})}"/>', html, count=1)
        html = re.sub(r'<meta property="og:description" content="[^"]*"/>', f'<meta property="og:description" content="{xml_escape(desc, {chr(34): "&quot;"})}"/>', html, count=1)
        html = re.sub(r'<meta property="og:url" content="[^"]*"/>', f'<meta property="og:url" content="{xml_escape(url)}"/>', html, count=1)
        tools = store.blob_text(t["current_toolset"], "toolset") if t["current_toolset"] else None
        html = html.replace('<div id="view" aria-live="polite"></div>',
                            f'<div id="view" aria-live="polite">{_server_prerender(t, tools)}</div>', 1)
        return Response(html, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    SITEMAP_PAGE = 40_000

    @app.get("/robots.txt", include_in_schema=False)
    def robots() -> Response:
        return Response(f"User-agent: *\nDisallow: /api/v1/admin/\nSitemap: {settings.public_base}/sitemap.xml\n",
                        media_type="text/plain")

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap_index() -> Response:
        pages = max(1, -(-store.count_observed_targets() // SITEMAP_PAGE))
        items = "".join(f"<sitemap><loc>{xml_escape(settings.public_base)}/sitemap-{n}.xml</loc></sitemap>" for n in range(pages))
        return Response('<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                        f"<sitemap><loc>{xml_escape(settings.public_base)}/sitemap-site.xml</loc></sitemap>{items}</sitemapindex>",
                        media_type="application/xml")

    @app.get("/sitemap-site.xml", include_in_schema=False)
    def sitemap_site() -> Response:
        routes = SPA_ROUTES + tuple(r for r in settings.sitemap_extra if r not in SPA_ROUTES)
        urls = "".join(f"<url><loc>{xml_escape(settings.public_base)}{xml_escape(r)}</loc></url>" for r in routes)
        return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                        media_type="application/xml")

    @app.get("/sitemap-{n}.xml", include_in_schema=False)
    def sitemap_page(n: int) -> Response:
        if n < 0 or n > 1000:
            raise HTTPException(status_code=404, detail="no such sitemap")
        rows = store.observed_target_ids(SITEMAP_PAGE, n * SITEMAP_PAGE)
        urls = "".join(f"<url><loc>{xml_escape(settings.public_base)}/s/{tid}</loc>"
                       + (f"<lastmod>{str(last)[:10]}</lastmod>" if last else "") + "</url>" for tid, last in rows)
        return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>',
                        media_type="application/xml")

    if (settings.landing_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=settings.landing_dir / "assets"), name="assets")

    # -- health + identity ----------------------------------------------------------

    @app.get("/health")
    def health() -> dict[str, Any]:
        sth = store.latest_sth()
        return {
            "ok": True,
            "service": "histor",
            "version": __version__,
            "profile": settings.profile,
            "store": store.backend_type,
            "tree_size": sth["treeSize"] if sth else 0,
            "crawl_running": services.crawler.running_since is not None,
            "last_crawl_error": last_crawl_error(),
        }

    @app.get("/api/v1/issuer")
    def issuer() -> dict[str, Any]:
        from awr import parse_did_key

        return {
            "did": services.key.did,
            "publicKeyHex": parse_did_key(services.key.did).hex(),
            "name": "HISTOR",
            "profile": "MTL/1",
            "profileUrl": "https://github.com/alexar76/aicom/blob/main/awr/adoption/mcp-trust-label/PROFILE.md",
            "warden": store.get_meta("warden_package"),
            "patternSet": store.get_meta("pattern_set"),
            "recordSet": store.get_meta("record_set"),
            "logType": "RFC 9162 Merkle tree over JCS(label); STH type histor.sth/v1",
            # histor-tlog/2: the same head as a C2SP checkpoint, and this instance as a witness.
            "checkpoint": {
                "format": "c2sp.org/tlog-checkpoint",
                "origin": settings.checkpoint_origin,
                "vkey": vkey(settings.checkpoint_origin, LOG_KEY_TYPE, services.key.public_key_bytes),
                "url": f"{settings.public_base}/checkpoint",
            },
            "witness": {
                "name": settings.cosigner_name,
                "vkey": vkey(settings.cosigner_name, COSIGNATURE_V1_TYPE, services.witness.key.public_key_bytes),
                "submission": f"{settings.public_base}/witness/v1",
                "monitoring": f"{settings.public_base}/witness/v1/logs",
                "knownLogs": sorted(services.witness.known),
            } if services.witness else None,
            "source": "https://github.com/alexar76/histor",
        }

    @app.get("/api/v1/stats")
    def stats() -> dict[str, Any]:
        run = store.last_run(finished_only=True)
        sth = store.latest_sth()
        counts = store.target_counts()
        out: dict[str, Any] = {
            "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "targets": counts,
            "changes": {
                "last24h": store.count_changes_since(_ago(1)),
                "last7d": store.count_changes_since(_ago(7)),
                "last30d": store.count_changes_since(_ago(30)),
            },
            "log": {"treeSize": sth["treeSize"], "rootHash": sth["rootHash"], "sthTimestamp": sth["timestamp"]} if sth else
                   {"treeSize": 0},
            "clientReports": {"last7d": store.client_report_total(_ago(7)[:10])},
            "crawl": {
                "running": services.crawler.running_since is not None,
                "runningSince": services.crawler.running_since,
                "progress": services.crawler.progress,
                "intervalSeconds": settings.crawl_interval_s,
                "lastError": last_crawl_error(),
                "sandboxHosts": (1 + len(settings.sandbox_extra)) if settings.sandbox_enabled else 0,
            },
            "remotePolling": {
                "enabled": settings.remote_interval_s > 0,
                "runningSince": services.crawler.remote_running_since,
                "intervalSeconds": settings.remote_interval_s,
                "changedIntervalSeconds": min(settings.remote_interval_s, settings.remote_changed_interval_s),
                "changeWindowSeconds": settings.remote_change_window_s,
                "minimumChanges": 2,
                "lastError": services.remote_error,
                **services.crawler.remote_schedule.stats(datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")),
            },
        }
        remote_run = store.last_run(kind="remote")
        if remote_run:
            out["remotePolling"]["lastRun"] = remote_run
        if run:
            s = run["stats"]
            # A run that continued a cycle after a restart, or was interrupted itself, reports the
            # cycle: what every run of it committed, not only this run's part.
            c = s.get("cycle") or {}
            out["lastRun"] = {
                "id": run["id"],
                "startedAt": run["started_at"],
                "finishedAt": run["finished_at"],
                "registryServers": s.get("registry_servers"),
                "registryEndpoints": s.get("registry_endpoints"),
                "curatedEndpoints": s.get("curated_endpoints", 0),
                "remoteSchedule": s.get("remote_schedule"),
                "notAttempted": s.get("not_attempted", {}),
                "attempted": c.get("attempted", s.get("attempted")),
                "statuses": c.get("statuses", s.get("statuses", {})),
                "labelsIssued": c.get("labels_issued", s.get("labels_issued", {})),
                "changes": c.get("changes", s.get("changes")),
                "cycle": {"startedAt": c.get("startedAt"), "runs": c.get("runs")} if c else None,
                "sandboxHosts": s.get("sandbox_hosts"),
                # Servers whose registry entry declares tool sets, and entries skipped with the reason.
                "declaredToolSets": s.get("declared_tool_sets"),
                "error": s.get("error"),
            }
        return out

    hosts_cache: dict[str, Any] = {"at": 0.0, "body": None}

    @app.get("/api/v1/stats/hosts")
    def stats_hosts(limit: int = Query(15, ge=1, le=50)) -> dict[str, Any]:
        """Endpoints per host among dialled targets. Cached: it walks every target row."""
        if hosts_cache["body"] is None or time.monotonic() - hosts_cache["at"] > 600:
            from collections import Counter
            from urllib.parse import urlsplit

            counts = Counter(
                (urlsplit(t["endpoint"]).hostname or "?")
                for t in store.all_targets() if not t["delisted"] and not t["skip_reason"]
            )
            hosts_cache.update(at=time.monotonic(), body={
                "hosts": [{"host": h, "endpoints": n} for h, n in counts.most_common(50)],
                "distinctHosts": len(counts),
            })
        body = hosts_cache["body"]
        return {"hosts": body["hosts"][:limit], "distinctHosts": body["distinctHosts"]}

    # -- servers --------------------------------------------------------------------

    def target_summary(t: dict[str, Any]) -> dict[str, Any]:
        message, state = badge.badge_state(t)
        return {
            "id": t["id"], "name": t["name"], "title": t["title"], "endpoint": t["endpoint"],
            "transport": t["transport"], "version": t["version"], "repository": t["repository"],
            "website": t["website"], "delisted": bool(t["delisted"]), "skipReason": t["skip_reason"],
            "lastStatus": t["last_status"], "lastDetail": t["last_detail"], "lastAttempt": t["last_attempt"],
            "lastObserved": t["last_ok"], "toolCount": t["current_count"], "subjectDigest": t["current_subject"],
            "toolSetDigest": t["current_toolset"], "firstPinned": t["first_pinned"],
            "unchangedSince": t["unchanged_since"], "observations": t["ok_observations"],
            "attempts": t["observations"], "changes": t["changes"],
            "blockMatches": t["block_matches"], "adviseMatches": t["advise_matches"],
            "recordMatches": t["record_matches"], "state": state, "badgeText": message,
            "classifierModel": t["classifier_model"], "classifierFlags": t["classifier_flags"],
            "packageVersion": t.get("package_version"), "packageSignals": _json_or_none(t.get("package_signals")),
            # Annotations, _meta and the other members MTL/1 does not digest (histor.extras); "" is
            # "observed, none", null "not observed since HISTOR started keeping them".
            "toolExtrasDigest": t.get("current_extras"),
        }

    @app.get("/api/v1/servers")
    def servers(q: str = Query("", max_length=200), state: str = Query("all", max_length=20),
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=10_000_000)) -> dict[str, Any]:
        total, rows = store.search_targets(q.replace("\x00", "").strip(), state=state, limit=limit, offset=offset)
        return {"total": total, "offset": offset, "limit": limit, "servers": [target_summary(r) for r in rows]}

    @app.get("/api/v1/servers/{target_id}")
    def server(target_id: str) -> Response:
        t = store.target(target_id)
        if t is None:
            raise HTTPException(status_code=404, detail="unknown server")
        history = store.history(target_id)
        # Runs of the same outcome collapse into one row: 300 identical "ok" days are one fact. Two
        # versions (package, server-reported or registry-listed) are two facts even when they served
        # the same list, so the versions are in the key.
        runs: list[dict[str, Any]] = []
        for h in reversed(history):
            key = (h["status"], h["toolset"], h["subject"], h.get("package_version"), h.get("launch"), h.get("protocol"),
                   h["server_version"], h.get("registry_version"))
            if runs and runs[-1]["key"] == key:
                runs[-1]["until"] = h["observed_at"]
                runs[-1]["count"] += 1
            else:
                runs.append({"key": key, "from": h["observed_at"], "until": h["observed_at"], "count": 1,
                             "status": h["status"], "detail": h["detail"], "toolSetDigest": h["toolset"],
                             "subjectDigest": h["subject"], "toolCount": h["tool_count"],
                             "serverName": h["server_name"], "serverVersion": h["server_version"],
                             "packageVersion": h.get("package_version"),
                             "registryVersion": h.get("registry_version"),
                             "protocolVersion": h.get("protocol") or None,
                             "launch": _json_or_none(h.get("launch"))})
        for r in runs:
            r.pop("key")
        matches = None
        pattern_set = store.get_meta("pattern_set")
        if t["current_toolset"] and pattern_set:
            with store.db.read() as tx:
                row = tx.one("SELECT matches FROM scans WHERE toolset=? AND pattern_set=?", (t["current_toolset"], pattern_set))
            matches = json.loads(row["matches"])[:MAX_MATCHES] if row else None
        descriptor = store.get_blob(t["current_subject"], "descriptor") if t["current_subject"] else None
        classifier = None
        if t["current_toolset"] and t["classifier_model"]:
            classifier = store.classification(t["current_toolset"], t["classifier_model"])
        page = {
            "server": target_summary(t),
            "description": t["description"],
            "descriptor": descriptor,
            "patternMatches": matches,
            "classifier": classifier,
            "labels": [{**lbl, "methodShort": SHORT.get(lbl["method"], lbl["method"])} for lbl in store.labels_for(target_id)],
            "timeline": list(reversed(runs))[:100],
            "changes": store.changes(limit=20, target_id=target_id),
            "toolExtras": store.get_blob(t["current_extras"], "toolextras") if t.get("current_extras") else None,
            "extrasChanges": store.extras_changes(target_id, limit=20),
            "clientReports": store.client_reports(target_id, _ago(30)[:10]),
            # What the publisher says this server lists elsewhere (histor.declared): its word, not observations.
            "declaredToolSets": [declared_public(r) for r in store.declared_toolsets(target_id)],
            "declarationFile": store.declaration_file(target_id),
        }
        if t["transport"] == "stdio":
            try:
                page["packageLookalike"] = default_index().check(t["endpoint"])
            except (OSError, ValueError):
                page["packageLookalike"] = None
        # The tool set can be megabytes: spliced in as the stored text instead of parsed and
        # re-serialised on every request.
        tools = store.blob_text(t["current_toolset"], "toolset") if t["current_toolset"] else None
        body = json.dumps(page, ensure_ascii=False)[:-1] + ',"tools":' + (tools or "null") + "}"
        return Response(body, media_type="application/json")

    # -- labels, blobs --------------------------------------------------------------

    @app.get("/api/v1/labels/{label_id}")
    def label(label_id: str) -> Response:
        row = store.label(label_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown label")
        return Response(row["body"], media_type=VC_MEDIA, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/api/v1/labels/{label_id}/proof")
    def label_proof(label_id: str, tree_size: int | None = Query(None, ge=1)) -> dict[str, Any]:
        row = store.label(label_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown label")
        sth = store.sth(tree_size) if tree_size else store.latest_sth()
        if sth is None or sth["treeSize"] <= row["leaf_index"]:
            raise HTTPException(status_code=409, detail="no signed tree head covers this label yet")
        return {
            "labelId": label_id,
            "leafIndex": row["leaf_index"],
            "leafInput": "JCS(label document)",
            "sth": sth,
            "inclusionProof": services.logbook.inclusion(row["leaf_index"], sth["treeSize"]),
        }

    def blob_route(kind: str):
        def handler(digest: str) -> Response:
            body = store.blob_text(digest, kind)
            if body is None:
                raise HTTPException(status_code=404, detail=f"unknown {kind}")
            return Response(body, media_type="application/json",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})
        return handler

    for kind, path in (("descriptor", "descriptors"), ("toolset", "toolsets"), ("pattern-set", "pattern-sets"),
                       ("record-set", "record-sets"), ("toolextras", "tool-extras")):
        app.add_api_route(f"/api/v1/{path}/{{digest:path}}", blob_route(kind), methods=["GET"])

    # -- changes --------------------------------------------------------------------

    @app.get("/api/v1/security-events")
    def security_events(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200), watch: str | None = Query(None, max_length=1800)) -> dict[str, Any]:
        from histor.security_events import events
        ids = watch.split(",") if watch else None
        if ids and (len(ids) > 100 or any(not re.fullmatch(r"[0-9a-f]{16}", v) for v in ids)):
            raise HTTPException(status_code=400, detail="watch requires target ids")
        rows = events(store, after=after, limit=limit, targets=ids)
        return {"events": rows, "nextCursor": rows[-1]["cursor"] if rows else after}

    @app.get("/security-feed.xml")
    def security_feed(watch: str | None = Query(None, max_length=1800)) -> Response:
        from histor.security_events import events
        ids = watch.split(",") if watch else None
        if ids and (len(ids) > 100 or any(not re.fullmatch(r"[0-9a-f]{16}", v) for v in ids)):
            raise HTTPException(status_code=400, detail="watch requires target ids")
        with store.db.read() as tx:
            latest = tx.one("SELECT MAX(seq) AS seq FROM security_events")
        rows = events(store, after=max(0, int((latest or {}).get("seq") or 0) - 200), limit=200, targets=ids)[-50:]
        entries = []
        for row in reversed(rows):
            event = row["event"]
            entries.append("<entry><id>urn:sha256:" + _xml_text(event["id"]) + "</id><title>" + _xml_text(event["kind"] + ": " + event["target"]) +
                           "</title><updated>" + _xml_text(event["observedAt"]) + "</updated><summary>" + _xml_text(json.dumps(event["evidence"], ensure_ascii=False)) + "</summary></entry>")
        updated = rows[-1]["event"]["observedAt"] if rows else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        body = ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><id>' + _xml_text(settings.public_base + "/security-feed.xml") +
                '</id><title>HISTOR security evidence changes</title><updated>' + _xml_text(updated) + '</updated>' + ''.join(entries) + '</feed>')
        return Response(body, media_type="application/atom+xml")

    @app.get("/api/v1/changes")
    def changes(limit: int = Query(50, ge=1, le=200), before: int | None = Query(None, ge=1)) -> dict[str, Any]:
        return {"changes": store.changes(limit=limit, before_id=before)}

    @app.get("/api/v1/changes/{change_id}")
    def change(change_id: int) -> dict[str, Any]:
        row = store.change(change_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown change")
        return row

    # -- what a tool list costs (histor.toolcost) -------------------------------------

    costs = toolcost.CostCache()

    def cost_of(digest: str | None) -> dict[str, Any] | None:
        if not digest:
            return None
        try:
            return costs.get(digest, lambda: store.blob_text(digest, "toolset"))
        except toolcost.CostUnavailable as exc:
            raise HTTPException(status_code=503, detail="this HISTOR counts no tokens (the cost extra is not installed)") from exc
        except toolcost.CostBusy as exc:
            raise HTTPException(status_code=503, detail="the token counter is busy; retry shortly",
                                headers={"Retry-After": "10"}) from exc

    def cost_diff(row: dict[str, Any]) -> dict[str, Any]:
        return toolcost.diff(cost_of(row["from_toolset"]) or toolcost.empty(), cost_of(row["to_toolset"]) or toolcost.empty())

    @app.get("/api/v1/cost/toolsets/{digest:path}")
    def toolset_cost(digest: str) -> dict[str, Any]:
        found = cost_of(digest)
        if found is None:
            raise HTTPException(status_code=404, detail="unknown toolset")
        return {"toolSetDigest": digest, **found}

    @app.get("/api/v1/changes/{change_id}/cost")
    def change_cost(change_id: int) -> dict[str, Any]:
        row = store.change(change_id)
        if row is None:
            raise HTTPException(status_code=404, detail="unknown change")
        return {"change": {"id": row["id"], "targetId": row["target_id"], "name": row["name"], "endpoint": row["endpoint"],
                           "observedAt": row["observed_at"], "fromToolSetDigest": row["from_toolset"],
                           "toToolSetDigest": row["to_toolset"], "fromPackageVersion": row.get("from_package_version"),
                           "toPackageVersion": row.get("to_package_version"),
                           "fromServerVersion": row.get("from_server_version"), "toServerVersion": row.get("to_server_version"),
                           "fromRegistryVersion": row.get("from_registry_version"),
                           "toRegistryVersion": row.get("to_registry_version")},
                **cost_diff(row)}

    @app.get("/api/v1/servers/{target_id}/cost")
    def server_cost(target_id: str, limit: int = Query(20, ge=1, le=50)) -> dict[str, Any]:
        t = store.target(target_id)
        if t is None:
            raise HTTPException(status_code=404, detail="unknown server")
        current = cost_of(t["current_toolset"])
        history = []
        for row in store.changes(limit=limit, target_id=target_id):
            d = cost_diff(row)
            history.append({"id": row["id"], "observedAt": row["observed_at"], "toolCount": d["toolCount"],
                            "totals": {k: d["totals"][k] for k in toolcost.TOTALS},
                            "added": len(d["added"]), "removed": len(d["removed"]), "changed": len(d["changed"]),
                            "cost": f"/api/v1/changes/{row['id']}/cost"})
        return {"server": target_summary(t), "toolSetDigest": t["current_toolset"],
                "current": current, "changes": history}

    @app.get("/api/v1/servers/{target_id}/fingerprints")
    def server_fingerprints(target_id: str, format: str = Query("vercel-ai", max_length=20)) -> dict[str, Any]:
        """The current tool set as per-tool fingerprints in a client's or another record's format
        (histor.fingerprints), so a client compares what it was served without converting anything."""
        if format not in fingerprints.FORMATS:
            raise HTTPException(status_code=400, detail=f"format is one of {', '.join(fingerprints.FORMATS)}")
        t = store.target(target_id)
        if t is None:
            raise HTTPException(status_code=404, detail="unknown server")
        tools = store.get_blob(t["current_toolset"], "toolset") if t["current_toolset"] else None
        if tools is None:
            raise HTTPException(status_code=404, detail="no tool set observed for this server")
        # "" is "observed, no extra members"; None is "observed before HISTOR kept them", when the
        # title and annotations these formats hash are unknown.
        extras_digest = t.get("current_extras")
        extras = store.get_blob(extras_digest, "toolextras") if extras_digest else None
        merged, over_caps = fingerprints.merged_tools(tools, extras)
        complete = [tool for tool in merged if tool.get("name") not in over_caps]
        return {"server": {"id": t["id"], "name": t["name"], "endpoint": t["endpoint"]},
                "format": format, "toolSetDigest": t["current_toolset"], "toolExtrasDigest": extras_digest,
                "lastObserved": t["last_ok"], "unchangedSince": t["unchanged_since"],
                "extrasRecorded": extras_digest is not None,
                "fingerprints": fingerprints.fingerprint_map(complete, format),
                # Tools whose extra members exceeded the storage caps: no fingerprint rather than a wrong one.
                "incomplete": over_caps}

    @app.get("/feed.xml")
    def feed(watch: str | None = Query(None, max_length=1800)) -> Response:
        """All changes, or with ``watch=<id>,<id>,…`` (up to 100 target ids, as /check and the server
        pages give them) only those servers' and packages': subscribe in any feed reader."""
        watched: list[str] | None = None
        if watch is not None:
            watched = sorted({w for w in watch.split(",") if re.fullmatch(r"[0-9a-f]{16}", w)})[:100]
            if not watched:
                raise HTTPException(status_code=400, detail="watch takes target ids (16 hex characters), comma-separated")
        items = store.changes(limit=50, target_ids=watched)
        updated = items[0]["observed_at"] if items else datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        entries = []
        for c in items:
            s = c["summary"]
            parts = []
            if s.get("newAddresses"):
                total = s.get("newAddressesTotal", len(s["newAddresses"]))
                more = f" (+{total - 10} more)" if total > 10 else ""
                parts.append(f"NEW OUTSIDE ADDRESSES: {', '.join(s['newAddresses'][:10])}{more}")
            if s["added"]:
                parts.append(f"added: {', '.join(s['added'][:10])}")
            if s["removed"]:
                parts.append(f"removed: {', '.join(s['removed'][:10])}")
            if s["modified"]:
                parts.append(f"modified: {', '.join(m['tool'] for m in s['modified'][:10])}")
            link = f"{settings.public_base}/s/{c['target_id']}"
            entries.append(
                "<entry>"
                f"<id>{_xml_text(settings.public_base)}/changes/{c['id']}</id>"
                f"<title>{_xml_text(c['name'])}: tool definitions changed</title>"
                f"<updated>{c['observed_at']}</updated>"
                f'<link href="{_xml_text(link)}"/>'
                f"<summary>{_xml_text('; '.join(parts) or 'definitions changed')} — {_xml_text(c['endpoint'])}</summary>"
                "</entry>"
            )
        self_url = f"{settings.public_base}/feed.xml" + (f"?watch={','.join(watched)}" if watched else "")
        body = (
            '<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
            f"<id>{xml_escape(self_url)}</id><title>HISTOR — MCP tool-definition changes{' (watched)' if watched else ''}</title>"
            f"<updated>{updated}</updated><author><name>HISTOR</name></author>"
            f'<link rel="self" href="{xml_escape(self_url)}"/>' + "".join(entries) + "</feed>"
        )
        return Response(body, media_type="application/atom+xml")

    # -- log ------------------------------------------------------------------------

    @app.get("/api/v1/log/sth")
    def latest_sth() -> dict[str, Any]:
        sth = store.latest_sth()
        if sth is None:
            raise HTTPException(status_code=404, detail="the log is empty")
        return sth

    @app.get("/api/v1/log/sth/{tree_size}")
    def sth_at(tree_size: int) -> dict[str, Any]:
        sth = store.sth(tree_size)
        if sth is None:
            raise HTTPException(status_code=404, detail="no signed tree head at that size")
        return sth

    def _checkpoint(sth: dict[str, Any]) -> str:
        """The STH as a C2SP checkpoint note: the log's signature line, then every cosignature
        line a witness returned for that size (histor-tlog/2 §4.4)."""
        note = sign_checkpoint(services.key, settings.checkpoint_origin, int(sth["treeSize"]),
                               bytes.fromhex(sth["rootHash"]))
        return note + "".join(store.cosignature_lines(int(sth["treeSize"])))

    @app.get("/checkpoint")
    def latest_checkpoint() -> Response:
        sth = store.latest_sth()
        if sth is None:
            raise HTTPException(status_code=404, detail="the log is empty")
        return Response(_checkpoint(sth), media_type="text/plain; charset=utf-8",
                        headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/log/checkpoint/{tree_size}")
    def checkpoint_at(tree_size: int) -> Response:
        sth = store.sth(tree_size)
        if sth is None:
            raise HTTPException(status_code=404, detail="no signed tree head at that size")
        return Response(_checkpoint(sth), media_type="text/plain; charset=utf-8",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.post("/api/v1/log/cosignatures")
    async def add_cosignatures(request: Request) -> dict[str, Any]:
        """Operator: store cosignature lines a witness returned for one of this log's heads.
        Lines are checked for shape only — a witness's key is the reader's to trust, not ours to
        vouch for — and a line for a size this log never signed is refused."""
        operator(request)
        body = await request.json()
        try:
            size = int(body["treeSize"])
            lines = [str(line) for line in body["lines"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="body is {treeSize, lines}") from exc
        if store.sth(size) is None:
            raise HTTPException(status_code=404, detail="no signed tree head at that size")
        if len(lines) > 16:
            raise HTTPException(status_code=400, detail="at most 16 lines")
        parsed = []
        for line in lines:
            try:
                bare = line.rstrip("\n")
                parsed.append((parse_signature_line(bare).name, bare + "\n"))
            except NoteError as exc:
                raise HTTPException(status_code=400, detail=f"bad signature line: {exc}") from exc
        return {"treeSize": size, "stored": store.store_cosignatures(size, parsed)}

    @app.post("/witness/v1/add-checkpoint")
    async def witness_add_checkpoint(request: Request) -> Response:
        if services.witness is None:
            raise HTTPException(status_code=404, detail="unknown log origin")
        raw = await read_bounded_body(request, 16384)
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="body is UTF-8 text") from exc
        reply = await run_in_threadpool(services.witness.add_checkpoint, body)
        return Response(reply.body, status_code=reply.status, media_type=reply.media_type)

    @app.get("/witness/v1/logs/{origin_hex}/checkpoint")
    def witness_checkpoint(origin_hex: str) -> Response:
        checkpoint = services.witness.checkpoint_for(origin_hex.lower()) if services.witness else None
        if checkpoint is None:
            raise HTTPException(status_code=404, detail="this witness has not co-signed that log")
        return Response(checkpoint, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-cache"})

    @app.get("/api/v1/log/proof/inclusion")
    def inclusion(leaf_index: int = Query(..., ge=0), tree_size: int = Query(..., ge=1)) -> dict[str, Any]:
        if leaf_index >= tree_size:
            raise HTTPException(status_code=400, detail="leaf_index must be below tree_size")
        try:
            return {"leafIndex": leaf_index, "treeSize": tree_size, "proof": services.logbook.inclusion(leaf_index, tree_size)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/log/proof/consistency")
    def consistency(first: int = Query(..., ge=1), second: int = Query(..., ge=1)) -> dict[str, Any]:
        if first > second:
            raise HTTPException(status_code=400, detail="first must not exceed second")
        try:
            return {"first": first, "second": second, "proof": services.logbook.consistency(first, second)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/log/entries")
    def entries(start: int = Query(0, ge=0), end: int | None = Query(None, ge=1)) -> dict[str, Any]:
        stop = min(end if end is not None else start + 100, start + 1000)
        return {"start": start, "entries": [
            {**e, "methodShort": SHORT.get(e["method"], e["method"])} for e in store.entries(start, stop)
        ]}

    # -- check ----------------------------------------------------------------------

    async def read_json(request: Request) -> dict[str, Any]:
        raw = await read_bounded_body(request, MAX_CHECK_BYTES)
        try:
            body = await run_in_threadpool(loads_limited, raw or b"{}")
        except TooDeep as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="body is not JSON") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="body must be a JSON object")
        return body

    def limit_key(request: Request) -> list[tuple[str, int]]:
        """The buckets a request counts against, each with its limit a minute.

        A hub routes every buyer's call from one address. Since the hubs name the buyer with an
        opaque ``X-AIMarket-Buyer`` id, each buyer gets the normal per-caller bucket, and all of
        one hub's traffic from one address shares a ceiling of ten of those.

        Both headers can be forged, so the FIRST bucket is always the bare address and is charged
        whatever the headers say. Rotating the hub or buyer value on every request mints a fresh
        sub-bucket each time — that used to mean no limit at all — but every one of those requests
        still lands in the same per-address bucket, capped at the hub ceiling.
        """
        ip = client_ip(request)
        hub = request.headers.get("x-aimarket-routing-hub", "").strip()[:200]
        if not hub:
            return [(ip, settings.check_rate_per_min)]
        buyer = "".join(c for c in request.headers.get("x-aimarket-buyer", "") if c.isalnum() or c == "-")[:64]
        buckets = [(ip, settings.check_rate_per_min * 10), (f"{ip}|{hub}", settings.check_rate_per_min * 10)]
        if buyer:
            buckets.append((f"{ip}|{hub}|{buyer}", settings.check_rate_per_min))
        return buckets

    def allow_all(kind: str, buckets: list[tuple[str, int]]) -> bool:
        # Every bucket must have room; checked narrowest-last so a refused buyer does not also
        # spend the shared ceiling for the others.
        return all(limiter.allow(f"{kind}:{key}", per_min, 60) for key, per_min in reversed(buckets))

    def run_check(body: dict[str, Any], who: list[tuple[str, int]]) -> dict[str, Any]:
        """Synchronous on purpose: callers run it in the threadpool, never on the event loop."""
        if not allow_all("check", who):
            raise HTTPException(status_code=429, detail="too many checks; slow down")
        addr = who[0][0]  # the bare address — always first, and not forgeable by a header
        key = who[-1][0]  # the narrowest identity: the buyer when a hub names one
        scan_rate = settings.check_scan_rate_per_hour

        def may_scan() -> bool:  # asked only when a fresh scan would actually run (audit F45)
            # The per-buyer budget, AND a per-address ceiling a rotated buyer id cannot escape: fresh
            # scans hold the site's only scan slot, so an unbounded caller would starve everyone.
            if scan_rate <= 0:
                return False
            if len(who) > 1 and not limiter.allow(f"scan:{key}", scan_rate, 3600):
                return False
            return limiter.allow(f"scan:{addr}", scan_rate * (10 if len(who) > 1 else 1), 3600)

        def may_contribute(target_id: str) -> bool:
            # One report per ADDRESS, target and day. The public count is a cross-client signal
            # ("some clients see a different set"); keyed on a forgeable buyer id, one caller could
            # mint any number of "clients" and fake or bury that signal for any server.
            return limiter.allow(f"report:{addr}:{target_id}", 1, 86400)

        def may_count_unlisted(host: str) -> bool:
            # Once per address, host and day: the count says how many callers asked, not how often one did.
            return limiter.allow(f"unlisted:{addr}:{host}", 1, 86400)

        try:
            return services.checker.check(body, allow_scan=may_scan, may_contribute=may_contribute,
                                          may_count_unlisted=may_count_unlisted)
        except CheckError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/check")
    async def check(request: Request) -> dict[str, Any]:
        body = await read_json(request)
        return await run_in_threadpool(run_check, body, limit_key(request))

    # -- the receipts log (histor.receipts) --------------------------------------------
    # Submissions authenticate themselves: every anchor is signed by its issuer, and only the
    # issuers the operator listed are accepted. Reads are public, like the label log's.
    receipts_log = services.receipts

    def require_receipts() -> Any:
        if receipts_log is None:
            raise HTTPException(status_code=404, detail="this instance has no receipts log")
        return receipts_log

    @app.post("/api/v1/receipts/anchors")
    async def receipt_anchors(request: Request) -> dict[str, Any]:
        log = require_receipts()
        if not log.open:
            raise HTTPException(status_code=503, detail="the receipts log accepts no issuers on this instance")
        if not limiter.allow(f"anchors:{client_ip(request)}", 120, 60):
            raise HTTPException(status_code=429, detail="too many anchor submissions")
        body = await read_json(request)
        try:
            results = await run_in_threadpool(log.submit, body.get("anchors"))
        except AnchorRefused as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"results": results, "sth": log.latest_sth()}

    @app.get("/api/v1/receipts/sth")
    def receipts_latest_sth() -> dict[str, Any]:
        sth = require_receipts().latest_sth()
        if sth is None:
            raise HTTPException(status_code=404, detail="the receipts log is empty")
        return sth

    @app.get("/api/v1/receipts/sth/{tree_size}")
    def receipts_sth_at(tree_size: int) -> dict[str, Any]:
        sth = require_receipts().sth(tree_size)
        if sth is None:
            raise HTTPException(status_code=404, detail="no signed tree head at that size")
        return sth

    @app.get("/api/v1/receipts/proof")
    def receipt_proof(digest: str = Query(..., min_length=51, max_length=51),
                      tree_size: int | None = Query(None, ge=1)) -> dict[str, Any]:
        # A digest is base64: links that forgot to percent-encode it arrive with '+' read as
        # a space. A space is never part of a digest, so reading it back as '+' is lossless.
        digest = digest.replace(" ", "+")
        try:
            proof = require_receipts().proof(digest, tree_size)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if proof is None:
            raise HTTPException(status_code=404, detail="no anchor for that receipt digest")
        return proof

    @app.get("/api/v1/receipts/proof/consistency")
    def receipts_consistency(first: int = Query(..., ge=1), second: int = Query(..., ge=1)) -> dict[str, Any]:
        if first > second:
            raise HTTPException(status_code=400, detail="first must not exceed second")
        try:
            return {"first": first, "second": second, "proof": require_receipts().consistency(first, second)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # -- badge ----------------------------------------------------------------------

    @app.get("/badge/{target_id}.svg")
    def badge_svg(target_id: str) -> Response:
        return Response(badge.render(store.target(target_id)), media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    # -- live README badges (shields.io endpoint schema) -----------------------------

    def _shield(label: str, message: str, color: str) -> JSONResponse:
        return JSONResponse({"schemaVersion": 1, "label": label, "message": message, "color": color},
                            headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/v1/badges/{name}")
    def shield(name: str) -> JSONResponse:
        """Numbers for README badges, read live: https://img.shields.io/endpoint?url=<this>."""
        if name == "log":
            sth = store.latest_sth()
            return _shield("labels in log", f"{sth['treeSize']:,}" if sth else "0", "5fe3ff")
        if name == "pinned":
            return _shield("tool sets pinned", f"{store.target_counts()['pinned']:,}", "3a7bd5")
        if name == "changes":
            return _shield("changes · 7d", f"{store.count_changes_since(_ago(7)):,}", "c98a1b")
        if name == "sth":
            sth = store.latest_sth()
            if not sth:
                return _shield("signed tree head", "none yet", "6b7280")
            then = datetime.strptime(sth["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            hours = (datetime.now(UTC) - then).total_seconds() / 3600
            age = f"{hours:.0f}h ago" if hours < 48 else f"{hours / 24:.0f}d ago"
            # A head older than two crawl intervals means the crawler stopped: say so in the colour.
            stale = settings.crawl_interval_s and hours * 3600 > 2 * settings.crawl_interval_s
            return _shield("signed tree head", age, "c98a1b" if stale else "2f9e77")
        raise HTTPException(status_code=404, detail="unknown badge")

    # -- operator -------------------------------------------------------------------

    @app.post("/api/v1/admin/crawl")
    def admin_crawl(request: Request, include_remote: bool = True) -> JSONResponse:
        operator(request)
        started = crawl_in_background(services, include_remote=include_remote)
        return JSONResponse({"started": started, "runningSince": services.crawler.running_since},
                            status_code=202 if started else 409)

    @app.get("/api/v1/admin/unlisted")
    def admin_unlisted(request: Request, days: int = Query(7, ge=1, le=90),
                       limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
        """Hosts /check was asked about that HISTOR does not list, most asked first. Operator only:
        even a host name can say which company runs which server."""
        operator(request)
        since = (datetime.now(UTC) - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        return {"since": since, "hosts": services.store.unlisted_queries(since, limit)}

    # -- federation peer -------------------------------------------------------------

    signed_cache: dict[str, tuple[float, dict[str, Any]]] = {}
    signed_lock = threading.Lock()

    def cached_signed(name: str, max_age_s: float, build) -> dict[str, Any]:
        """ML-DSA-65 is pure Python and holds the GIL for ~0.1-0.3 s: signing the discovery documents
        on every anonymous GET let one client starve the process, crawler included (audit F06)."""
        now = time.monotonic()
        with signed_lock:
            hit = signed_cache.get(name)
            if hit and now - hit[0] < max_age_s:
                return hit[1]
            document = build()
            signed_cache[name] = (now, document)
            return document

    @app.get("/.well-known/ai-market.json")
    def well_known() -> Response:
        # Static for the life of the process: signed once.
        return JSONResponse(cached_signed("well-known", float("inf"), build_well_known),
                            headers={"Cache-Control": "public, max-age=300"})

    def build_well_known() -> dict[str, Any]:
        document: dict[str, Any] = {
            "protocol": "aimarket/2",
            "protocol_versions": ["v2"],
            "name": "HISTOR",
            "hub_url": settings.public_base,
            "signer_public_key": services.provider.public_key_b64,
            "manifest_url": f"{settings.public_base}/ai-market/v2/manifest",
            "mcp_endpoint": f"{settings.public_base}/ai-market/v2/invoke",
            "provider_pubkey": services.provider.public_key_b64,
            "capabilities": [c["capability_id"] for c in CAPS],
            "capabilities_count": len(CAPS),
            "categories": ["mcp-security", "transparency-log", "tool-definitions", "awr", "mtl"],
            "issuer_did": services.key.did,
        }
        document["signature"] = services.provider.sign_object(document)
        return document

    def manifest_tools() -> list[dict[str, Any]]:
        return [{
            **cap,
            "product_id": PRODUCT_ID,
            "invoke_url": f"{settings.public_base}/ai-market/v2/invoke",
            "publisher_id": "histor",
            "provider_pubkey": services.provider.public_key_b64,
            "category": "mcp-security",
            "output_schema": {"type": "object"},
        } for cap in CAPS]

    @app.get("/ai-market/v2/manifest")
    def manifest() -> Response:
        # Re-signed at most every ten minutes; a hub accepts a manifest for a week.
        return JSONResponse(cached_signed("manifest", 600, build_manifest), headers={"Cache-Control": "public, max-age=300"})

    def build_manifest() -> dict[str, Any]:
        tools = manifest_tools()
        document: dict[str, Any] = {
            "protocol": "aimarket/2",
            "protocol_version": "v2",
            "name": "HISTOR",
            "hub_url": settings.public_base,
            "total_capabilities": len(tools),
            "capabilities_count": len(tools),
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "tools": tools,
            "by_hub": {},
        }
        document["signature"] = services.provider.sign_manifest(document)
        return document

    @app.get("/ai-market/v2/search")
    def search(q: str = "") -> dict[str, Any]:
        needle = q.lower().strip()
        tools = [t for t in manifest_tools() if not needle or needle in t["capability_id"] or needle in t["description"].lower()]
        return {"total": len(tools), "tools": tools}

    def receipt(result: dict[str, Any], capability_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        rec = {
            "nonce": "0x" + secrets.token_hex(16),
            "product_id": PRODUCT_ID,
            "capability_id": capability_id,
            "price_usd": 0.0,
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "success": 1,
            "latency_ms": 0,
        }
        rec["signature"] = services.provider.sign_hub_receipt(rec)
        return {
            "ok": True,
            "result": result,
            "provider_pubkey": services.provider.public_key_b64,
            "receipt": rec,
            "signature": services.provider.sign_result(result, capability_id=capability_id, product_id=PRODUCT_ID,
                                                       input_payload=payload),
        }

    def compact_change(c: dict[str, Any]) -> dict[str, Any]:
        """A change as a hub buyer needs it: bounded size, the full diff one link away."""
        s = c["summary"]
        return {
            "id": c["id"], "server": c["name"], "endpoint": c["endpoint"], "observedAt": c["observed_at"],
            "added": s["added"][:20], "removed": s["removed"][:20],
            "modified": [m["tool"] for m in s["modified"][:20]],
            "newAddresses": s.get("newAddresses", [])[:20],
            "newAddressesTotal": s.get("newAddressesTotal", len(s.get("newAddresses", []))),
            "detail": s.get("detail"), "label": c.get("label_id"),
            "page": f"{settings.public_base}/s/{c['target_id']}",
        }

    def do_invoke(payload: dict[str, Any], who: list[tuple[str, int]]) -> dict[str, Any]:
        cap = str(payload.get("capability_id") or "")
        inner = payload.get("input") if isinstance(payload.get("input"), dict) else payload
        if cap == "histor.check@v1":
            return receipt(run_check(inner, who), cap, inner)
        if not allow_all("invoke", who):
            raise HTTPException(status_code=429, detail="too many calls; slow down")
        if cap == "histor.server@v1":
            endpoint, name = inner.get("endpoint"), inner.get("name")
            for value in (endpoint, name):
                if value is not None and (not isinstance(value, str) or "\x00" in value or len(value) > 2000):
                    raise HTTPException(status_code=400, detail="endpoint and name must be strings")
            candidates = store.targets_by(endpoint=endpoint) if endpoint else store.targets_by(name=name or "")
            if not candidates:
                raise HTTPException(status_code=404, detail="unknown server")
            return receipt({"servers": [target_summary(t) for t in candidates[:10]]}, cap, inner)
        if cap == "histor.changes@v1":
            limit = inner.get("limit") if isinstance(inner.get("limit"), int) else 20
            return receipt({"changes": [compact_change(c) for c in store.changes(limit=max(1, min(limit, 50)))]},
                           cap, inner)
        raise HTTPException(status_code=404, detail="unknown capability")

    @app.post("/ai-market/v2/invoke")
    async def invoke(request: Request) -> dict[str, Any]:
        payload = await read_json(request)
        # Digesting, the WARDEN subprocess and the ML-DSA receipt signature all block: threadpool.
        return await run_in_threadpool(do_invoke, payload, limit_key(request))

    return app
