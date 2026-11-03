"""The hub's own pages and assets: home, developers, start, hubs, examples, studio, operator,
widget, live feed and fonts, plus the paid studio, seller operations, client distribution,
pipeline provider and refunds.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from aimarket_hub import theme
from aimarket_hub.access_policy import capability_is_publicly_offerable
from aimarket_hub.api_models import StudioRunRequest
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import capability_is_fulfillable
from aimarket_hub.signing import Signer
from aimarket_hub.subcontract import JobStore


# The paths below were written relative to aimarket_hub/api.py, where this code lived.
_API_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "api.py")


def register(
    *,
    _TRUSTED_PROXIES: frozenset[str],
    _check_invoke_rate: Callable[..., Any],
    _ecosystem_policy: Callable[..., Any],
    _mcp_caller: Callable[..., Any],
    _publishable_pending_peers: Callable[..., Any],
    app: FastAPI,
    config: HubConfig,
    db: HubDatabase,
    hub_jobs: JobStore,
    late: SimpleNamespace,
    signer: Signer,
) -> None:
    """Attach the hub's pages, studio and pipeline routes to ``app``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _catalogue_route,
        _client_address,
        _trim_rate_buckets,
        logger,
    )

    # ── Landing page & Integration Examples ──────────────────

    from aimarket_hub import landing
    from aimarket_hub.theme import SITE_CSS, apply_shell
    from aimarket_hub.terminal_ssr import seed_terminal_home, snapshot as landing_snapshot

    # Rendered per app, AFTER theme.configure — a module constant built at import froze one
    # operator's address into every code sample on the page.
    docs_pages = {lang: landing.docs_html(lang=lang) for lang in landing.COPY}
    example_pages = {lang: landing.integration_examples_html(lang=lang) for lang in landing.COPY}

    hub_root = os.path.abspath(os.path.join(os.path.dirname(_API_FILE), ".."))
    from aimarket_hub.ui_assets import ui_asset_path

    terminal_home_path = ui_asset_path("terminal-home.html", hub_root)
    cap_i18n_path = ui_asset_path("cap-descriptions-i18n.json", hub_root)
    hub_ui_i18n_path = ui_asset_path("hub-ui-i18n.json", hub_root)
    studio_ui_i18n_path = ui_asset_path("studio-ui-i18n.json", hub_root)

    ui_en_cache: dict[str, Any] = {"mtime": None, "script": ""}

    def _ui_en_script() -> str:
        """ui.en of hub-ui-i18n.json as the page's inline #hub-ui-en, read again when the file
        changes. The page falls back to it when the dictionary fetch fails, so it shows English
        rather than its i18n keys."""
        try:
            mtime = os.path.getmtime(hub_ui_i18n_path)
        except OSError:
            return ""
        if ui_en_cache["mtime"] != mtime:
            try:
                with open(hub_ui_i18n_path, encoding="utf-8") as f:
                    doc = json.load(f)
                en = (doc.get("ui") or doc).get("en") or {}
                body = json.dumps(en, ensure_ascii=False, separators=(",", ":"))
                # Inside <script>, "</script" or "<!--" in a string would end or bend the element.
                ui_en_cache["script"] = body.replace("<", "\\u003c")
            except (OSError, ValueError, AttributeError):
                ui_en_cache["script"] = ""
            ui_en_cache["mtime"] = mtime
        return ui_en_cache["script"]

    def _load_terminal_home() -> str:
        """The home page, wearing this operator's name.

        The file is the design of record and carries the reference deployment's title, og
        tags and nav brand as literals; served unmodified they told every visitor to a
        stranger's hub whose page they were on.
        """
        if not os.path.isfile(terminal_home_path):
            # Damaged/incomplete installs still have a useful fallback.
            return docs_pages["en"]
        with open(terminal_home_path, encoding="utf-8") as f:
            html = f.read()
        ui_en = _ui_en_script()
        if ui_en:
            html = html.replace(
                '<script type="application/json" id="hub-ui-en">{}</script>',
                f'<script type="application/json" id="hub-ui-en">{ui_en}</script>',
                1,
            )
        name = config.hub_name.strip() or "AIMarket Hub"
        if name != "modelmarket.dev":
            html = html.replace(
                "<title>modelmarket.dev — AI Economy Protocol</title>",
                f"<title>{name} — AI Economy Protocol</title>",
            )
            html = html.replace(
                'content="modelmarket.dev — AI Economy Live"', f'content="{name} — AI Economy Live"',
            )
            html = html.replace(
                'content="https://modelmarket.dev/"', f'content="{config.hub_url.rstrip("/")}/"',
            )
            html = html.replace(
                '<span class="core"></span> modelmarket.dev</a>',
                f'<span class="core"></span> {name}</a>',
            )
            # The hero wordmark is split across spans — `<span class="grad">model</span>market…`
            # — so it survived every brand rewrite here and every third-party hub showed OUR name
            # in letters twice the size of its own. Seen on independentai.network/hub/.
            html = html.replace(
                '<h1 id="hero-brand"><span class="grad">model</span>market<span class="grad">.dev</span></h1>',
                f'<h1 id="hero-brand"><span class="grad">{name}</span></h1>',
            )
            # And the client-side translator sets document.title from the dictionary, whose
            # page_title carries the reference brand. Without this the page re-brands itself back
            # to modelmarket.dev a moment after loading, undoing the <title> rewrite above.
            html = html.replace(
                'window.__HUB_BRAND = "modelmarket.dev";',
                f'window.__HUB_BRAND = {json.dumps(name)};',
            )
            # The social card shows the modelmarket.dev name; another hub's links unfurl without it.
            html = re.sub(r'\s*<meta (?:property="og:image(?::[a-z]+)?"|name="twitter:card") content="[^"]*" />', "", html)
            if not config.ecosystem_links:
                html = re.sub(
                    r'\s*<a href="https://(?:(?:use|edu)\.modelmarket\.dev|modelmarket\.dev/(?:tools|blog)/)[^"]*"[^>]*>.*?</a>',
                    "", html,
                    flags=re.DOTALL,
                )
        html = theme.drop_missing_links(html)
        # The MCP endpoint card quotes the gateway's version. It was typed into the HTML
        # (v1.0.1) and stayed there two releases after serverInfo said 1.2.0; render it
        # from the constant the gateway itself reports.
        from aimarket_hub.mcp_gateway import SERVER_VERSION as _mcp_version
        html = re.sub(r"(Streamable HTTP · v)[0-9][0-9A-Za-z.\-]*", rf"\g<1>{_mcp_version}", html, count=1)
        try:
            summary, events = landing_snapshot(db, hub_url=config.hub_url, event_limit=12,
                                               policy=_ecosystem_policy())
            html = seed_terminal_home(html, summary, events)
        except Exception:
            logger.exception("terminal home SSR seed failed; serving the static shell")
        return html

    # The HTML handlers below are SYNC on purpose — they stat() and read() files from
    # disk, which must not happen on the event loop (it would stall concurrent
    # /invoke settlement). FastAPI dispatches sync handlers to its threadpool.
    #
    # GET and HEAD: link checkers, uptime probes and social-card fetchers send HEAD first,
    # and a 405 there reads as "site down" (2026-10-29 stranger test: HEAD / was 405).
    @app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    def landing_page():
        return HTMLResponse(
            _load_terminal_home(),
            headers={"Cache-Control": "public, max-age=30, must-revalidate"},
        )

    @app.get("/cap-descriptions-i18n.json")
    def cap_descriptions_i18n():
        """Short capability glosses in EN/RU/ES/FR/ZH for the terminal catalogue UI."""
        if not os.path.isfile(cap_i18n_path):
            raise HTTPException(status_code=404, detail="cap-descriptions-i18n.json missing")
        return FileResponse(
            cap_i18n_path,
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get("/hub-ui-i18n.json")
    def hub_ui_i18n():
        """Portal chrome strings (nav, hero, stats, feed) in EN/RU/ES/FR/ZH."""
        if not os.path.isfile(hub_ui_i18n_path):
            raise HTTPException(status_code=404, detail="hub-ui-i18n.json missing")
        return FileResponse(
            hub_ui_i18n_path,
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get("/studio-ui-i18n.json")
    def studio_ui_i18n():
        """HEPHAESTUS studio chrome strings in EN/RU/ES/FR/ZH."""
        if not os.path.isfile(studio_ui_i18n_path):
            raise HTTPException(status_code=404, detail="studio-ui-i18n.json missing")
        return FileResponse(
            studio_ui_i18n_path,
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get("/assets/site.css")
    def site_css():
        """The one stylesheet behind /developers, /examples and the demo pages.

        Served from `theme.py` rather than a file so the page chrome cannot drift between
        the templates that are Python strings and the ones that are static HTML.
        """
        return Response(
            content=SITE_CSS,
            media_type="text/css",
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.get("/developers", response_class=HTMLResponse)
    async def developers_page(lang: str = "en"):
        return HTMLResponse(docs_pages.get(lang, docs_pages["en"]))

    _start_html_path = os.path.join(os.path.dirname(os.path.abspath(_API_FILE)), "static", "start.html")
    _og_card_path = os.path.join(os.path.dirname(os.path.abspath(_API_FILE)), "static", "og-card.png")

    @app.get("/og-card.png", include_in_schema=False)
    async def og_card():
        """The 1280x640 card a link to the reference home page unfurls with (dev.to, X, chats).

        It carries the modelmarket.dev name, so only that deployment's home page points at it.
        """
        if not os.path.isfile(_og_card_path):
            return Response(status_code=404)
        return FileResponse(_og_card_path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/start", response_class=HTMLResponse)
    async def start_page():
        """Key, MCP connection and USDC top-up on one page — the onboarding door.

        A static file like the plugin demo, filled with the shared chrome on the way out. The
        page reads this hub's own manifest, so a hub with signup or top-up off says so rather
        than offering a door that refuses.
        """
        try:
            with open(_start_html_path, encoding="utf-8") as f:
                html = f.read()
        except OSError:
            return HTMLResponse("<h1>Start page not found</h1>", status_code=404)
        name = (config.hub_name or "").strip() or "AIMarket Hub"
        # The reference deployment points a newcomer at the 5-minute lesson that walks this
        # same loop; a stranger's hub does not link to another operator's school.
        learn = (
            '<p class="learn-line small"><a id="learn-link" href="https://edu.modelmarket.dev/ai-pays-ai/" '
            'data-school="https://edu.modelmarket.dev/" '
            'target="_blank" rel="noopener" data-i18n="learn">First time here? A 5-minute lesson: from a '
            'free call to paying with a key ↗</a></p>'
            if config.ecosystem_links else ""
        )
        html = html.replace("<!--LEARN-->", learn)
        html = html.replace("<!--PROVIDER_GUIDE-->", (
            "https://play.modelmarket.dev/publish" if config.ecosystem_links else "/developers"
        ))
        return HTMLResponse(
            apply_shell(
                html,
                f"Start — {name}",
                "Get an API key, connect any MCP client with it, and top it up with USDC.",
                active="start",
            ),
            headers={"Cache-Control": "public, max-age=300"},
        )

    @app.get("/hubs", response_class=HTMLResponse)
    async def hubs_page():
        """The federation as this hub sees it, for a person — and how to run a hub of your own.

        Same data as `/ai-market/v2/federation/peers` (the public view: an alias of a hub
        already admitted is withheld, exactly as there), escaped, because every name and
        address on it was written by a peer. See aimarket_hub/hubs_page.py.
        """
        from aimarket_hub import hubs_page as _hubs
        from aimarket_hub.theme import BRAND

        name = (config.hub_name or "").strip() or "This hub"
        page = _hubs.render(
            hub_name=name,
            hub_url=config.hub_url,
            source_url=str(BRAND.get("source_url") or ""),
            peers=db.list_peers(),
            pending=_publishable_pending_peers(db),
            own_count=lambda url: db.count_capabilities(source_hub=url),
            assay=db.get_peer_assay,
        )
        return HTMLResponse(
            apply_shell(
                page,
                f"Hubs — {name}",
                "Hubs this one knows, hubs knocking to join, and how to run a hub of your own.",
                active="hubs",
            ),
            headers={"Cache-Control": "public, max-age=120"},
        )

    @app.get("/examples", response_class=HTMLResponse)
    async def integration_examples(lang: str = "en"):
        return HTMLResponse(example_pages.get(lang, example_pages["en"]))

    # ── HEPHAESTUS studio ───────────────────────────────────────

    # Paid Studio is an explicit, separate entrance. The trial forwarder below keeps
    # its request and credential contract. Paid steps traverse the normal invoke app,
    # including payment verification, routing, limits and receipts, without a Hub key.
    from aimarket_hub.studio_paid import PaidStudio, attach_paid_routes

    async def _studio_paid_invoke(payload: dict, headers: dict, caller: str, *, operation_id=None):
        async def operation_scope(scope, receive, send):
            if operation_id:
                scope.setdefault('state', {})['seller_operation_id'] = operation_id
            await app(scope, receive, send)
        transport = httpx.ASGITransport(app=operation_scope, client=(caller or "127.0.0.1", 0), raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://studio.internal", timeout=None) as client:
            response = await client.post("/ai-market/v2/invoke", json=payload, headers=headers)
        try:
            answer = response.json()
        except ValueError:
            answer = {"success": False, "error": "invoke_returned_non_json"}
        if not isinstance(answer, dict):
            answer = {"success": False, "error": "invoke_returned_non_object"}
        return response.status_code, answer

    paid_studio = PaidStudio(
        db=db, config=config, signer=signer, invoke=_studio_paid_invoke,
        route_ok=lambda cap: (capability_is_fulfillable(cap) and capability_is_publicly_offerable(cap)
                              and _catalogue_route(db, config, cap).sellable),
    )
    from aimarket_hub.peer_operations import PeerOperations
    from aimarket_hub.seller_operations import SellerOperations, attach_routes as attach_seller_operations
    paid_studio.remote = PeerOperations(db)
    paid_studio.jobs = hub_jobs
    seller_operations = SellerOperations(paid_studio, _studio_paid_invoke)
    attach_seller_operations(app, seller_operations, caller=_mcp_caller, allow_request=_check_invoke_rate)
    app.state.seller_operations = seller_operations
    attach_paid_routes(app, studio=paid_studio, caller=_mcp_caller, allow_request=_check_invoke_rate)
    from aimarket_hub.pipeline_distribution import attach_routes as attach_client_distribution
    attach_client_distribution(app)
    from aimarket_hub.pipeline_provider import PipelineProvider, attach_prepare_route, capability as pipeline_capability
    pipeline_provider = PipelineProvider(paid_studio, hub_jobs)
    attach_prepare_route(app, pipeline_provider, caller=_mcp_caller, allow_request=_check_invoke_rate)
    db.upsert_capability(pipeline_capability())
    app.state.pipeline_provider = pipeline_provider
    late.pipeline_provider = pipeline_provider
    from aimarket_hub.pipeline_refunds import attach_routes as attach_refund_routes
    attach_refund_routes(app, pipeline_provider, caller=_mcp_caller, allow_request=_check_invoke_rate)

    # The studio composes a graph out of THIS hub's catalogue, so it is served from the
    # same origin as the manifest it reads — the hub's CORS is fail-closed, and a builder
    # that cannot read the catalogue is not a builder.
    _studio_run_hits: dict[str, list[float]] = {}

    def _studio_run_allowed(client: str) -> bool:
        """Free studio runs are anonymous and each one is a pipeline run on the executor:
        bound them per client address (AIMARKET_STUDIO_RUNS_PER_HOUR, default 20)."""
        try:
            ceiling = int(os.getenv("AIMARKET_STUDIO_RUNS_PER_HOUR", "20"))
        except (TypeError, ValueError):
            ceiling = 20
        if ceiling <= 0:
            return False
        now = time.time()
        hits = [t for t in _studio_run_hits.get(client, []) if t > now - 3600.0]
        if len(hits) >= ceiling:
            _studio_run_hits[client] = hits
            return False
        hits.append(now)
        _studio_run_hits[client] = hits
        if len(_studio_run_hits) > 4096:
            _trim_rate_buckets(_studio_run_hits, now - 3600.0, 4096, keep=client)
        return True

    @app.post("/studio/run")
    async def studio_run(
        body: StudioRunRequest,
        request: Request,
        x_sandbox_visitor: str | None = Header(default=None, alias="X-AIMarket-Sandbox-Visitor"),
    ):
        """Submit a studio blueprint to the pipeline executor, same-origin.

        The executor is a different service (the factory), and the browser cannot reach it
        cross-origin, so the hub forwards. This is deliberately NOT a general proxy:

          * the target comes from ``AIMARKET_PIPELINE_EXECUTOR_URL`` only, never from the
            request — a forwarder that takes its destination from the caller is an SSRF
            gadget, whatever it is called;
          * unset means 503, not a default guess;
          * the node list is shape- and size-validated here as well as by the executor, so
            this route cannot be used to post arbitrary bodies anywhere;
          * no caller credentials are forwarded. The studio's run path is the free/sandbox
            one; wallet-funded runs use the separate paid Studio routes above.
        """
        if not _studio_run_allowed(_client_address(request, _TRUSTED_PROXIES) or "anonymous"):
            return JSONResponse(status_code=429, content={
                "error": "rate_limited",
                "detail": "too many studio runs from this address — try again later",
                "protocol_version": "v2",
            })
        executor = (os.environ.get("AIMARKET_PIPELINE_EXECUTOR_URL") or "").strip().rstrip("/")
        if not executor:
            return JSONResponse(status_code=503, content={
                "error": "executor_not_configured",
                "detail": (
                    "This hub has no pipeline executor configured. Set "
                    "AIMARKET_PIPELINE_EXECUTOR_URL to the factory base URL, or POST the "
                    "blueprint to /ai-market/pipelines on the executor yourself."
                ),
                "protocol_version": "v2",
            })

        payload: dict[str, Any] = {"nodes": [n.model_dump(exclude_none=True) for n in body.nodes]}
        if body.channel_id:
            payload["channel_id"] = body.channel_id
        if body.continue_on_error:
            payload["continue_on_error"] = True

        # `post_configured`, not `safe_post`: the destination is the hub's own configuration,
        # so the caller-SSRF refusal is a false positive here — and on the first deploy it
        # blocked the only address that was actually reachable while allowing one that did
        # not resolve. See outbound_http.post_configured for the whole argument.
        from aimarket_hub.outbound_http import post_configured

        try:
            resp = await post_configured(
                f"{executor}/ai-market/pipelines",
                json=payload,
                timeout=120.0,
                # The visitor's own trial identity, and nothing else. The hub meters its
                # free allowance per visitor, so dropping this merges every caller into
                # one bucket; forwarding anything MORE would hand a stranger's credential
                # to another service.
                headers=(
                    {"X-AIMarket-Sandbox-Visitor": x_sandbox_visitor}
                    if x_sandbox_visitor else None
                ),
            )
        except Exception as exc:  # noqa: BLE001 — the executor is a separate service
            return JSONResponse(status_code=502, content={
                "error": "executor_unreachable",
                "detail": str(exc)[:300],
                "protocol_version": "v2",
            })

        try:
            out = resp.json()
        except Exception:  # noqa: BLE001
            return JSONResponse(status_code=502, content={
                "error": "executor_returned_non_json",
                "status_code": resp.status_code,
                "protocol_version": "v2",
            })
        # Where the signed bill of materials can be fetched — as a path on THIS origin, not
        # the executor's address. The executor is typically an internal name
        # (`http://aicom-app-1:8080`), and publishing it both leaks infrastructure and hands
        # the browser a link it cannot follow.
        if isinstance(out, dict) and out.get("trace_id"):
            out["trace_url"] = f"/studio/trace/{out['trace_id']}"
        return JSONResponse(status_code=resp.status_code, content=out)

    @app.get("/studio/trace/{trace_id}")
    async def studio_trace(trace_id: str):
        """Fetch one signed bill of materials through this origin.

        The page must be able to show the verifiable original rather than only its own
        summary of it, and the executor is not reachable from a browser.
        """
        executor = (os.environ.get("AIMARKET_PIPELINE_EXECUTOR_URL") or "").strip().rstrip("/")
        if not executor:
            return JSONResponse(status_code=503, content={
                "error": "executor_not_configured", "protocol_version": "v2",
            })
        if not re.fullmatch(r"tr_[0-9a-f]{6,32}", trace_id or ""):
            # The id goes into a URL on another service; only the executor's own format
            # may travel, so this cannot be steered into an arbitrary path.
            return JSONResponse(status_code=400, content={
                "error": "invalid_trace_id", "protocol_version": "v2",
            })

        from aimarket_hub.outbound_http import get_configured

        try:
            resp = await get_configured(f"{executor}/ai-market/pipelines/{trace_id}", timeout=30.0)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(status_code=502, content={
                "error": "executor_unreachable", "detail": str(exc)[:200],
                "protocol_version": "v2",
            })
        try:
            return JSONResponse(status_code=resp.status_code, content=resp.json())
        except Exception:  # noqa: BLE001
            return JSONResponse(status_code=502, content={
                "error": "executor_returned_non_json", "protocol_version": "v2",
            })

    # Resolve the built studio — repo layout, sibling layout, and the Docker one.
    studio_dir = None
    for candidate in (
        os.path.abspath(os.path.join(os.path.dirname(_API_FILE), "..", "..", "hephaestus", "studio", "dist")),
        os.path.abspath(os.path.join(os.path.dirname(_API_FILE), "..", "hephaestus", "studio", "dist")),
        "/app/hephaestus/studio/dist",
    ):
        if os.path.isdir(candidate):
            studio_dir = candidate
            break

    if studio_dir:
        app.mount("/studio", StaticFiles(directory=studio_dir, html=True), name="studio")
    else:
        @app.get("/studio", response_class=HTMLResponse)
        async def studio_not_built():
            # Say which build is missing instead of 404ing — the deployment that hits this
            # is one where the image shipped without the studio bundle.
            return HTMLResponse(
                "<h1>HEPHAESTUS studio is not built</h1>"
                "<p>Run <code>npm install &amp;&amp; npm run build</code> in "
                "<code>hephaestus/studio</code>, or deploy an image that includes "
                "<code>hephaestus/studio/dist</code>.</p>",
                status_code=503,
            )

    # ── Widget & Live Stream static serving ─────────────────────

    # Resolve widget dir — handles both repo layout (../../aimarket-widget)
    # and Docker layout (../aimarket-widget).
    widget_dir = None
    for candidate in (
        os.path.abspath(os.path.join(os.path.dirname(_API_FILE), "..", "aimarket-widget")),
        os.path.abspath(os.path.join(os.path.dirname(_API_FILE), "..", "..", "aimarket-widget")),
        "/app/aimarket-widget",
    ):
        if os.path.isdir(candidate):
            widget_dir = candidate
            break

    @app.get("/plugins/demo", response_class=HTMLResponse)
    def plugins_demo():
        hub_root = os.path.abspath(os.path.join(os.path.dirname(_API_FILE), ".."))
        demo_html = ui_asset_path("plugins-demo.html", hub_root)
        if os.path.isfile(demo_html):
            with open(demo_html, encoding="utf-8") as f:
                name = (config.hub_name or "").strip() or "AIMarket Hub"
                return HTMLResponse(
                    apply_shell(
                        f.read(),
                        f"Plugin Demo — {name}",
                        "Live playground for every plugin loaded on this hub — real routes, "
                        "real responses.",
                        active="plugins",
                    )
                )
        return HTMLResponse("<h1>Plugin demo not found</h1>", status_code=404)

    operator_html_path = ui_asset_path("operator.html", hub_root)

    def _operator_page() -> HTMLResponse:
        if not os.path.isfile(operator_html_path):
            return HTMLResponse("<h1>Operator desk not found</h1>", status_code=404)
        with open(operator_html_path, encoding="utf-8") as f:
            html = f.read()
        name = (config.hub_name or "").strip() or "AIMarket Hub"
        return HTMLResponse(
            apply_shell(
                html,
                f"Operator desk — {name}",
                "Approve exceptions or dismiss pending federation hubs. "
                "Sandbox assay auto-admits a pass. Admin token required.",
                active="operator",
            ),
            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex"},
        )

    @app.get("/operator", response_class=HTMLResponse)
    def operator_desk():
        return _operator_page()

    @app.get("/operator/", response_class=HTMLResponse)
    def operator_desk_slash():
        return _operator_page()

    @app.api_route("/widget/demo", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    def widget_demo():
        demo_html = os.path.join(widget_dir, "demo.html") if widget_dir else None
        if demo_html and os.path.isfile(demo_html):
            with open(demo_html, encoding="utf-8") as f:
                return HTMLResponse(f.read())
        return HTMLResponse("<h1>Widget demo not found</h1>", status_code=404)

    @app.api_route("/live", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False)
    def live_economy_stream():
        """Legacy URL — same immersive terminal as `/`."""
        return HTMLResponse(_load_terminal_home())

    @app.get("/widget/widget.js")
    def widget_js():
        """Serve the embed script with THIS hub's host in its allowlist.

        The widget refuses a `data-hub-url` outside same-origin, localhost or a built-in
        suffix list — a real control, since a hostile embed could otherwise point a
        visitor's invocations and affiliate header at an attacker. The list was the literal
        `["modelmarket.dev"]` in every copy, which means a fork shipped an allowlist naming
        a domain its operator does not control and not their own: any third-party page could
        embed their script pointed at the reference hub, and no third-party page could point
        it at theirs. Substituting the serving hub's own host keeps the control and puts the
        operator in charge of it.
        """
        path = os.path.join(widget_dir, "widget.js") if widget_dir else None
        if not (path and os.path.isfile(path)):
            raise HTTPException(status_code=404, detail="widget not bundled with this hub")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        host = (urlparse(config.hub_url).hostname or "").strip().lower()
        if host and not host.startswith("localhost") and host != "127.0.0.1":
            src = src.replace(
                'var HUB_ALLOW_SUFFIXES = ["modelmarket.dev"];',
                f'var HUB_ALLOW_SUFFIXES = ["{host}"];',
            )
        return Response(content=src, media_type="application/javascript")

    if widget_dir:
        app.mount("/widget", StaticFiles(directory=widget_dir, html=True), name="widget")

    # Links to pages this deployment did not ship come out of the nav and the pages.
    theme.set_missing_pages(
        href for href, present in (
            ("/studio/", bool(studio_dir)),
            ("/widget/demo", bool(widget_dir and os.path.isfile(os.path.join(widget_dir, "demo.html")))),
            ("/plugins/demo", os.path.isfile(ui_asset_path("plugins-demo.html", hub_root))),
            ("/operator", os.path.isfile(operator_html_path)),
        ) if not present
    )
    if theme.MISSING_PAGES:
        # The developer pages were rendered above, before this was known; their dicts are what
        # the /developers and /examples handlers read.
        docs_pages.update({lang: landing.docs_html(lang=lang) for lang in landing.COPY})
        example_pages.update({lang: landing.integration_examples_html(lang=lang) for lang in landing.COPY})

    # The three webfonts every page's <head> asks for, served by us. They used to come from
    # fonts.googleapis.com, which disclosed each visitor's address to Google before the first
    # byte of content rendered. Filenames carry Google's content hash, so they are immutable.
    fonts_dir = os.path.join(os.path.dirname(_API_FILE), "assets", "fonts")
    if os.path.isdir(fonts_dir):
        app.mount("/assets/fonts", StaticFiles(directory=fonts_dir), name="fonts")
