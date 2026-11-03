"""HTTP middleware (security headers, the x402 gate, invoke metrics) and the Prometheus
/metrics route.
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from aimarket_hub import settle
from aimarket_hub.canonical import canonical_base, canonical_href, with_canonical
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.metrics import metrics_payload, record_invoke, set_federation_peer_health
from aimarket_hub.settle import InvoiceStore


def register(
    *,
    app: FastAPI,
    config: HubConfig,
    db: HubDatabase,
    hub_invoices: InvoiceStore,
    signer: Any = None,
) -> None:
    """Attach the middleware and /metrics to ``app``."""
    # api.py's module-level helpers; imported here because api.py imports this module.
    from aimarket_hub.api import (
        _INTERNAL_NETS,
        logger,
    )

    @app.middleware("http")
    async def _security_headers_middleware(request: Request, call_next):
        """Baseline browser headers on every response, whichever nginx sits in front.

        The hub's own origin carries /start (key minting, USDC top-up) and the operator
        pages; with no header at all those pages could be framed by any site and sniffed
        into another type. ``/widget/`` is made to be embedded, so it alone may be framed.
        HSTS only when the request reached the edge over https.
        """
        response = await call_next(request)
        headers = response.headers
        # Caches do not recognize custom payment/API headers as Authorization.
        # Account data and one-time payment/key responses must never be reused
        # for a different caller, even if an upstream cache ignores those headers.
        credentials = (
            "authorization", "x-api-key", "x-payment-channel-secret",
            "x-payment-secret", "x-aimarket-mandate-proof", "x-aimarket-job-grant",
        )
        private_path = request.url.path.startswith((
            "/ai-market/v2/account", "/ai-market/v2/topups/",
            "/ai-market/v2/card-topups/", "/ai-market/v2/mandates/",
        ))
        if (request.method not in ("GET", "HEAD") or response.status_code == 402
                or private_path or any(request.headers.get(name) for name in credentials)):
            headers["Cache-Control"] = "no-store"
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if not request.url.path.startswith("/widget/"):
            headers.setdefault("X-Frame-Options", "DENY")
            headers.setdefault(
                "Content-Security-Policy", "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
            )
        if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
            headers.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.middleware("http")
    async def _canonical_link_middleware(request: Request, call_next):
        """A ``<link rel="canonical">`` on every HTML page, named under AIMARKET_HUB_URL.

        One place instead of every page handler: the home page is a file on disk, the
        others are built in four modules, and a page added later must not slip past.
        """
        response = await call_next(request)
        base = canonical_base(config.hub_url)
        if (
            base is None
            or request.method != "GET"
            or response.status_code != 200
            or not response.headers.get("content-type", "").startswith("text/html")
            or response.headers.get("content-encoding")
        ):
            return response
        body = b"".join([chunk async for chunk in response.body_iterator])
        href = canonical_href(base, request.url.path, request.query_params.get("lang"))
        page = Response(content=with_canonical(body, href), status_code=response.status_code)
        page.raw_headers = [(k, v) for k, v in response.raw_headers if k.lower() != b"content-length"]
        page.headers["content-length"] = str(len(page.body))
        return page

    @app.middleware("http")
    async def _x402_middleware(request: Request, call_next):
        """Speak x402 on every 402 this hub emits.

        One insertion point instead of ten. The hub returns `402` from ten places inside
        `invoke`, each an inline dict; editing all ten would risk missing one, and a payment
        surface that is right nine times out of ten is not a payment surface. Here the price
        is read back out of the response the handler already built (`needed`), so a new 402
        added tomorrow is covered without anyone remembering to.

        Emits both dialects: the V2 `PAYMENT-REQUIRED` header (current protocol) and the V1
        `accepts` array merged into the existing body. Existing consumers read the same keys
        they always did.
        """
        response = await call_next(request)
        if getattr(response, "status_code", 0) != 402:
            return response

        from aimarket_hub import x402

        # Bail out BEFORE touching the stream. Everything below consumes body_iterator, and a
        # consumed iterator cannot be handed back — returning the drained response object was
        # a 402 with an empty body and a stale Content-Length, i.e. the hub's own payment
        # refusal destroyed by the code meant to enrich it.
        if not x402.enabled() or getattr(request.state, "x402_passthrough", False):
            return response

        raw_headers = list(getattr(response, "raw_headers", []) or [])
        body = b""
        if hasattr(response, "body_iterator"):
            body = b"".join([chunk async for chunk in response.body_iterator])
        else:
            body = getattr(response, "body", b"") or b""

        def _rebuild(new_body: bytes, extra: dict[str, str] | None = None) -> Response:
            """Reconstruct from the ORIGINAL raw headers so duplicates (Set-Cookie, Vary)
            survive; Content-Length is dropped because the body may have changed."""
            rebuilt = Response(content=new_body, status_code=402)
            rebuilt.raw_headers = [
                (k, v) for k, v in raw_headers if k.lower() != b"content-length"
            ]
            if not any(k.lower() == b"content-type" for k, _ in rebuilt.raw_headers):
                rebuilt.raw_headers.append((b"content-type", b"application/json"))
            rebuilt.raw_headers.append((b"content-length", str(len(new_body)).encode()))
            for key, value in (extra or {}).items():
                rebuilt.raw_headers.append((key.encode(), value.encode()))
            return rebuilt

        try:

            payload: dict[str, Any] = {}
            with contextlib.suppress(Exception):
                payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict):
                payload = {}

            price = payload.get("needed")
            if price is None:
                price = payload.get("price_usd", 0)
            # Behind nginx `request.url` is the scheme uvicorn saw, which is http — so the
            # advertised resource was `http://modelmarket.dev/…` on a hub that only serves
            # https. A payer that checks what they are paying for against the URL they
            # called sees a mismatch, and an http URL in a payment offer is the kind of
            # detail a careful client refuses on. Prefer the hub's own canonical base.
            resource_url = str(request.url)
            if config.hub_url:
                base = config.hub_url.rstrip("/")
                path = request.url.path or ""
                query = f"?{request.url.query}" if request.url.query else ""
                resource_url = f"{base}{path}{query}"
            description = str(payload.get("detail") or payload.get("error") or "")[:200]

            # `_bind_listing_payee` always sets this attribute, even to "", so its
            # PRESENCE says the 402 is about a listing and its emptiness says that
            # listing has nobody to pay. Collapsing the two into a falsy string sent
            # the buyer to the operator's own wallet for a sale `settle.terms_for`
            # then refused — the buyer paid the platform and got an error back.
            about_listing = hasattr(request.state, "x402_pay_to")
            pay_to = str(getattr(request.state, "x402_pay_to", "") or "")
            payee_arg = pay_to if about_listing else None
            if (
                about_listing
                and not pay_to
                and (price or 0) > 0
                and str(payload.get("error") or "") == "payment_required"
                and x402.recipient()
            ):
                # Only when this hub HAS an operator wallet, because that is the only
                # case where the buyer was being misdirected. A hub with no wallet at
                # all never named one, so its 402 is plain "payment_required" and
                # saying anything else would change an answer that was already right.
                # No offer can be made, so say why instead of repeating the generic
                # "pay the seller payout_address" — there is no such address, and a
                # buyer who follows that advice to the platform wallet is paying for
                # a call this hub will refuse.
                payload["detail"] = (
                    "this listing is priced but names no payout address, so it cannot "
                    "be sold here; ask the publisher to declare one"
                )
                payload["error"] = "listing_not_sellable"
                return _rebuild(json.dumps(payload).encode("utf-8"))
            v2 = x402.payment_required_v2(price or 0, resource_url, description, pay_to=payee_arg)
            if v2 is None:
                return _rebuild(body)

            # Bind this 402 to one call: the nonce the buyer signs into
            # transferWithAuthorization. Without it a transfer to the seller
            # could have been made for something else.
            cap_id = str(getattr(request.state, "x402_capability_id", "") or "")
            terms_units = 0
            try:
                terms_units = int((v2.get("accepts") or [{}])[0].get("amount") or 0)
            except (TypeError, ValueError):
                terms_units = 0
            if pay_to and terms_units:
                # The nonce commits to a secret only this caller receives (settle.nonce_for_secret):
                # once the payment is mined the nonce is public, and redeeming must open it.
                payment_secret = settle.mint_secret()
                nonce = settle.nonce_for_secret(payment_secret)
                invoice = hub_invoices.mint(
                    nonce=nonce, capability_id=cap_id, pay_to=pay_to,
                    amount_units=terms_units, ttl_s=settle.invoice_ttl_s(),
                    secret=payment_secret,
                )
                for entry in v2.get("accepts") or []:
                    extra = dict(entry.get("extra") or {})
                    extra["nonce"] = nonce
                    entry["extra"] = extra
                v2["nonce"] = nonce
                payload["nonce"] = nonce
                payload["binding"] = "eip3009"
                # In this JSON body only — never in PAYMENT-REQUIRED, accepts[].extra or a
                # header, which proxies log and the A2A bridge persists with the task.
                payload["payment_secret"] = payment_secret
                payload["pay_to"] = pay_to
                payload["expires_at"] = invoice["expires_at"]

            payload.update(x402.v1_body_fields(
                price or 0, resource_url, description, pay_to=payee_arg,
            ))
            if payload.get("accepts") and pay_to and payload.get("nonce"):
                for entry in payload["accepts"]:
                    extra = dict(entry.get("extra") or {})
                    extra["nonce"] = payload["nonce"]
                    entry["extra"] = extra
            # x402 Offer and Receipt extension: a signed statement of these terms, so the buyer
            # (and anyone it shows the offer to later) can prove what was asked. Signed after the
            # nonce is set; the nonce sits in `extra`, which the offer payload does not carry.
            if signer is not None:
                with contextlib.suppress(Exception):
                    from aimarket_hub import x402_offer_receipt

                    if x402_offer_receipt.enabled():
                        offers = x402_offer_receipt.offers_extension(
                            signer, v2.get("accepts") or [], resource_url, network=x402.caip2())
                        if offers:
                            v2["extensions"] = {**(v2.get("extensions") or {}), **offers}
                            payload["extensions"] = {**(payload.get("extensions") or {}), **offers}
            extra_headers = {
                "PAYMENT-REQUIRED": x402.encode_header(v2),
                # Browsers cannot read a non-safelisted response header unless it is
                # exposed; without this an in-browser x402 client sees a 402 with no
                # payment terms at all.
                "Access-Control-Expose-Headers": "PAYMENT-REQUIRED",
            }
            if payload.get("nonce"):
                extra_headers["X-Payment-Nonce"] = str(payload["nonce"])
            return _rebuild(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                extra_headers,
            )
        except Exception as exc:  # pragma: no cover - a 402 must survive this failing
            logger.debug("x402 enrichment skipped: %s", exc)
            return _rebuild(body)

    @app.middleware("http")
    async def _invoke_metrics_middleware(request: Request, call_next):
        """Record Prometheus series for /ai-market/v2/invoke (local + federated)."""
        path = request.url.path.rstrip("/")
        if not path.endswith("/invoke"):
            return await call_next(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        cap = getattr(request.state, "aimarket_capability_id", None) or "unknown"
        if cap != "unknown" and not _listed_capability(cap):
            # The id comes from the request body. Labelled as sent, every made-up id became
            # three new series held for the life of the process — any caller could grow the
            # hub's memory and the scrape without limit. Only what the catalogue lists is named.
            cap = "unlisted"
        code = getattr(response, "status_code", 500)
        if code == 402:
            result = "payment_required"
        elif code == 429:
            result = "rate_limited"
        elif code == 403:
            result = "safety_blocked"
        elif 200 <= code < 300:
            result = "ok"
        elif code >= 500:
            result = "error"
        else:
            result = "client_error"
        record_invoke(cap, result, duration_s=time.perf_counter() - t0)
        return response

    def _refresh_federation_gauges() -> None:
        """Recompute federation peer health at scrape time.

        Read here rather than at the end of a crawl: a crawl that stops running is
        exactly one of the conditions worth alerting on, and gauges last written by
        the last successful cycle would report the federation as fine.
        """
        rejected = 0
        newest_per_peer: list[float] = []
        now = time.time()
        for peer in db.list_peers():
            if str(getattr(peer, "status", "") or "") == "key_mismatch":
                rejected += 1
            stamp = str(getattr(peer, "last_crawl", "") or "").strip()
            if not stamp:
                continue
            try:
                parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            newest_per_peer.append(now - parsed.timestamp())
        set_federation_peer_health(rejected, max(newest_per_peer) if newest_per_peer else None)

    def _listed_capability(capability_id: str) -> bool:
        try:
            return db.find_by_capability_id(capability_id) is not None
        except Exception:  # noqa: BLE001 - a metric label must never fail an invoke
            return False

    def _metrics_reader_allowed(request: Request) -> bool:
        """Who may read /metrics.

        The series name every capability this hub sells, how often each was paid for or
        refused, which MCP client families call it and how long invokes take: an
        operator's dashboard, not a public page. Prometheus scrapes it from inside (the
        container network, the host), while everything that reaches the hub through the
        public proxy carries a header nginx adds — if the proxy adds one: nginx's default
        proxy_pass does not, and behind such a front this page is public (see
        docs/observability-prometheus.md). So by default only a direct caller from a
        loopback or private address reads it. ``AIMARKET_METRICS_TOKEN`` admits a
        scraper that has to come from outside (``Authorization: Bearer …``), and
        ``AIMARKET_METRICS_PUBLIC=1`` makes the page world-readable again.
        """
        if os.environ.get("AIMARKET_METRICS_PUBLIC", "").strip().lower() in ("1", "true", "yes", "on"):
            return True
        token = os.environ.get("AIMARKET_METRICS_TOKEN", "").strip()
        auth = request.headers.get("authorization", "")
        if token and auth.startswith("Bearer "):
            import hmac

            if hmac.compare_digest(auth[7:].strip(), token):
                return True
        if any(h in request.headers for h in ("x-forwarded-for", "x-real-ip", "forwarded")):
            return False
        peer = request.client.host if request.client else ""
        try:
            address = ipaddress.ip_address(peer)
        except ValueError:
            return False
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        # Named, not `is_private`: that also admits the documentation and benchmarking
        # ranges, which are routable enough to reach a published port.
        return any(address in net for net in _INTERNAL_NETS)

    @app.get("/metrics")
    async def prometheus_metrics(request: Request) -> Response:
        if not _metrics_reader_allowed(request):
            # The same answer as a hub without the route: nothing here to find.
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        try:
            _refresh_federation_gauges()
        except Exception as exc:  # noqa: BLE001 — a scrape must never 500
            logger.warning("Could not refresh federation gauges: %s", exc)
        body, ctype = metrics_payload()
        return Response(content=body, media_type=ctype)
