"""Observed sellers: x402 sellers listed from what they already publish, with their consent.

A seller joins the federation by publishing a signed manifest and keeping it current. Two
x402 sellers we asked on 2026-10-30 (TensorFeed, SWARM) declined for the same reason: the
manifest, keeping its prices in step with the live ones and signing receipts is work, and it
pays only once buyers come back. Nobody's buyers come back yet, so the door cost more than
anything behind it.

This tier moves that work to the hub. With the seller's consent (one email, recorded by the
operator) the hub reads the seller's own x402 discovery document (``/.well-known/x402``),
sends each listed route one UNPAID request and reads the ``402``: price, asset, network and
``payTo``. Only what the live ``402`` said is listed, and only as an observation:

- nothing here is signed by the seller, and the hub does not claim it was;
- the hub never sits in the payment path: a buyer calls the seller's URL itself and pays per
  the ``402`` it receives;
- the first ``payTo`` seen (or the one the seller gave with consent) is pinned, and a route
  whose ``402`` names another recipient is withdrawn until the operator re-confirms. A
  changed recipient is what a hijacked seller looks like;
- observed routes live in their own table, never in the catalogue: they are not in
  ``/manifest``, ``/search`` ``matches``, ``/invoke`` or ``peers`` (spec §2.7).
"""

from __future__ import annotations

import calendar
import json
import logging
import math
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

from aimarket_hub import crawler as _crawler

logger = logging.getLogger(__name__)

TIER = "observed"

#: The x402 discovery convention: `/.well-known/x402`, served by some as `x402.json`.
DISCOVERY_PATHS = ("/.well-known/x402", "/.well-known/x402.json")

#: TensorFeed's discovery document is about 0.9 MB (170 routes with full schemas).
MAX_DISCOVERY_BYTES = 2_097_152
#: A 402 is an offer, not a payload.
MAX_PROBE_BYTES = 65_536

PROBE_TIMEOUT_S = 10.0

#: The only fields a consent record may carry; anything else in the request is dropped.
CONSENT_FIELDS = ("by", "at", "how", "note")


def _env_int(name: str, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default)) or default))
    except ValueError:
        return default


def enabled() -> bool:
    """On unless switched off — with no consented seller it does nothing.

    Off in the UNI realm: an observed seller is paid on a real chain, and the bubble must
    never hand a participant a real payment offer (see ``x402.asset_profile``).
    """
    if os.getenv("AIMARKET_OBSERVED_SELLERS", "1").strip().lower() in ("0", "false", "no"):
        return False
    from aimarket_hub import realm

    return not realm.is_uni()


def interval_s() -> int:
    """How often each seller is observed. At least an hour: every probe is a request the
    seller answers for free."""
    return _env_int("AIMARKET_OBSERVED_INTERVAL_S", 21_600, 3_600)


def max_routes() -> int:
    """Routes probed per seller. A consent that names routes is honoured within this cap."""
    return min(100, _env_int("AIMARKET_OBSERVED_MAX_ROUTES", 25, 1))


def ttl_s() -> int:
    """A route not re-observed within two cycles is no longer served."""
    return 2 * interval_s()


# ── Seller identity ──────────────────────────────────────────────────


def normalize_origin(url: str) -> str:
    """``https://host[:port]`` for an https URL, else ``""``. Paths are not identities."""
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        return ""
    try:
        parsed = urlparse(url)
        parsed.port  # Invalid ports and malformed bracketed hosts must fail closed.
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    if parsed.username or parsed.password:
        return ""
    return f"https://{parsed.netloc.lower()}"


def same_origin(url: str, origin: str) -> bool:
    """A route counts only on the seller's own origin (spec §3.1, the `endpoint` rule)."""
    return bool(origin) and normalize_origin(url) == origin and urlparse(url).scheme == "https"


def clean_consent(raw: Any) -> dict[str, str]:
    """The consent record as stored: who agreed, when, how. ``by`` and ``at`` are required."""
    if not isinstance(raw, dict):
        raise ValueError("consent must be an object with at least `by` and `at`")
    out = {k: str(raw.get(k) or "").strip()[:200] for k in CONSENT_FIELDS if raw.get(k)}
    if not out.get("by") or not out.get("at"):
        raise ValueError("consent needs `by` (who agreed) and `at` (when)")
    return out


def public_consent(consent: dict[str, Any]) -> dict[str, Any]:
    """What the public listing says about consent: that it exists, when and how.

    ``by`` is usually a person's email address; it stays with the operator."""
    return {
        "recorded": bool(consent.get("by") and consent.get("at")),
        "at": consent.get("at") or "",
        "how": consent.get("how") or "",
    }


# ── The seller's discovery document ─────────────────────────────────


def _price_from_endpoint(entry: dict[str, Any]) -> float | None:
    for key, scale in (("priceUsd", 1.0), ("price_usd", 1.0), ("priceUsdCents", 0.01)):
        value = entry.get(key)
        if value is None:
            continue
        if isinstance(value, bool):
            return None
        try:
            price = float(value) * scale
            return price if math.isfinite(price) and price >= 0 else None
        except (TypeError, ValueError, OverflowError):
            return None
    return None


def _price_from_accepts(accepts: Any) -> float | None:
    """USD from a USDC offer's atomic amount; ``None`` for any other asset."""
    if not isinstance(accepts, list):
        return None
    for accept in accepts:
        if not isinstance(accept, dict):
            continue
        offer = offer_terms(accept)
        if offer and offer.get("price_usd") is not None:
            return offer["price_usd"]
    return None


def _first_description(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()[:1000]
    return ""


def parse_discovery(doc: Any, origin: str) -> list[dict[str, Any]]:
    """Routes a discovery document lists on the seller's own origin, in document order.

    Five shapes are read, all seen on live sellers on 2026-10-30:

    - ``endpoints[]`` with ``url`` / ``method`` / ``description`` / ``priceUsdCents`` (SWARM);
    - ``items[]``, Bazaar style, with ``resource`` as a string or ``{url, description}`` and
      ``accepts[]`` (textokit, TensorFeed);
    - a top-level ``accepts[]`` whose entries name their ``resource`` (agent-exec);
    - ``resources[]`` as objects with ``url`` / ``method`` / ``description`` (our own gateway);
    - ``resources[]``, bare URLs: the minimum the convention asks for.

    A listed price is what the document says; the hub lists what the ``402`` says.
    """
    if not isinstance(doc, dict):
        return []
    routes: dict[str, dict[str, Any]] = {}

    def add(url: Any, method: Any = "", description: str = "", price: float | None = None) -> None:
        if not isinstance(url, str) or not same_origin(url, origin):
            return
        url = url.strip()
        route = routes.setdefault(url, {
            "url": url, "method": "", "description": "", "listed_price_usd": None,
        })
        verb = str(method or "").strip().upper()
        if verb in ("GET", "POST") and not route["method"]:
            route["method"] = verb
        if description and not route["description"]:
            route["description"] = description
        if price is not None and route["listed_price_usd"] is None:
            route["listed_price_usd"] = price

    for entry in doc.get("endpoints") or []:
        if isinstance(entry, dict):
            add(entry.get("url"), entry.get("method"),
                _first_description(entry.get("description")), _price_from_endpoint(entry))
    for item in doc.get("items") or []:
        if not isinstance(item, dict):
            continue
        resource = item.get("resource")
        url = resource.get("url") if isinstance(resource, dict) else resource
        desc = _first_description(
            resource.get("description") if isinstance(resource, dict) else "",
            item.get("description"),
            *[a.get("description") for a in (item.get("accepts") or []) if isinstance(a, dict)],
        )
        add(url, item.get("method"), desc, _price_from_accepts(item.get("accepts")))
    for accept in doc.get("accepts") or []:
        if isinstance(accept, dict):
            add(accept.get("resource"), accept.get("method"),
                _first_description(accept.get("description")), _price_from_accepts([accept]))
    for entry in doc.get("resources") or []:
        if isinstance(entry, dict):
            add(entry.get("url"), entry.get("method"),
                _first_description(entry.get("description")), _price_from_endpoint(entry))
        else:
            add(entry)
    for route in routes.values():
        route["method"] = route["method"] or "POST"
    return list(routes.values())


def select_routes(routes: list[dict[str, Any]], allowed: list[str] | None,
                  limit: int) -> list[dict[str, Any]]:
    """The routes to probe: the ones the seller consented to, else all, at most ``limit``."""
    if allowed:
        wanted = [u.strip() for u in allowed if isinstance(u, str) and u.strip()]
        by_url = {r["url"]: r for r in routes}
        return [by_url[u] for u in wanted if u in by_url][:limit]
    return routes[:limit]


def seller_name(doc: Any, origin: str) -> str:
    if isinstance(doc, dict):
        publisher = doc.get("publisher") if isinstance(doc.get("publisher"), dict) else {}
        name = _first_description(doc.get("name"), publisher.get("name"))
        if name:
            return name[:120]
    return urlparse(origin).hostname or origin


# ── The 402 ──────────────────────────────────────────────────────────


def _usdc_decimals(network: str, asset: str) -> int | None:
    """Decimals of a USDC contract this hub knows, else ``None`` (no USD price is invented)."""
    from aimarket_hub.x402 import ASSET_PROFILES, CAIP2_BY_CHAIN

    caip = CAIP2_BY_CHAIN.get(network, network)
    for (chain, symbol), profile in ASSET_PROFILES.items():
        if symbol != "USDC":
            continue
        if CAIP2_BY_CHAIN.get(chain) == caip and str(profile.get("address", "")).lower() == asset.lower():
            return int(profile.get("decimals", 6))
    return None


def offer_terms(accept: dict[str, Any]) -> dict[str, Any] | None:
    """One x402 ``accepts`` entry as listing terms, or ``None`` if it names no recipient."""
    from aimarket_hub.x402 import CAIP2_BY_CHAIN

    pay_to = str(accept.get("payTo") or "").strip()
    if not pay_to:
        return None
    network = str(accept.get("network") or "").strip()
    asset = str(accept.get("asset") or "").strip()
    raw = accept.get("maxAmountRequired", accept.get("amount"))
    # Exact USDC offers use positive uint256 atomic amounts. Python's int()
    # also accepts signs, underscores and Unicode digits, and unbounded values
    # can overflow the price conversion or bypass a buyer's positive budget.
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        return None
    text = str(raw)
    if re.fullmatch(r"[0-9]{1,78}", text) is None:
        return None
    atomic = int(text)
    if not 0 < atomic < 2 ** 256:
        return None
    decimals = _usdc_decimals(network, asset) if asset else None
    price = atomic / (10 ** decimals) if atomic is not None and decimals is not None else None
    return {
        "scheme": str(accept.get("scheme") or ""),
        "network": CAIP2_BY_CHAIN.get(network, network),
        "asset": asset,
        "amount_atomic": str(atomic) if atomic is not None else "",
        "price_usd": price,
        "pay_to": pay_to,
    }


def offer_from_402(payload: Any, headers: dict[str, Any] | None) -> dict[str, Any] | None:
    """The first usable offer of a ``402``: V1 ``accepts`` in the body, else V2 in the
    ``PAYMENT-REQUIRED`` header (the same two places the admission assay reads)."""
    from aimarket_hub.federation_assay import x402_header_offer

    body = payload if isinstance(payload, dict) else {}
    accepts = body.get("accepts")
    version = body.get("x402Version")
    header = None
    if not (isinstance(accepts, list) and accepts):
        header = x402_header_offer(headers)
        accepts = header.get("accepts") if header else None
        version = header.get("x402Version") if header else version
    if not isinstance(accepts, list):
        return None
    for accept in accepts:
        if isinstance(accept, dict):
            terms = offer_terms(accept)
            if terms:
                resource = (header or body).get("resource")
                terms["x402_version"] = version if isinstance(version, int) else None
                terms["offer_description"] = _first_description(
                    resource.get("description") if isinstance(resource, dict) else "",
                    accept.get("description"),
                )
                return terms
    return None


async def _default_request(method: str, url: str, headers: dict[str, str], max_bytes: int,
                           json_body: dict | None) -> dict[str, Any]:
    from aimarket_hub.outbound_http import ResponseTooLarge, safe_request_capped

    try:
        status, raw, reply_headers = await safe_request_capped(
            method, url, json=json_body, headers=headers, timeout=PROBE_TIMEOUT_S,
            max_bytes=max_bytes,
        )
    except ResponseTooLarge as exc:
        return {"status": 0, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - a seller being down is an observation
        return {"status": 0, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    parsed = None
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
    return {"status": status, "json": parsed, "headers": reply_headers}


def _request_headers(hub_url: str) -> dict[str, str]:
    headers = {"User-Agent": _crawler.USER_AGENT, "Accept": "application/json"}
    if hub_url:
        headers["X-AIMarket-Observer"] = hub_url
    return headers


async def fetch_discovery(origin: str, *, hub_url: str = "", request: Any = None
                          ) -> tuple[str, Any, str]:
    """``(url, document, error)`` for the first discovery path that answers JSON."""
    request = request or _default_request
    last_error = "no discovery document"
    for path in DISCOVERY_PATHS:
        url = origin + path
        reply = await request("GET", url, _request_headers(hub_url), MAX_DISCOVERY_BYTES, None)
        if reply.get("status") == 200 and isinstance(reply.get("json"), dict):
            return url, reply["json"], ""
        last_error = reply.get("error") or f"{url} answered {reply.get('status')}"
    return "", None, last_error


async def probe_route(route: dict[str, Any], *, hub_url: str = "", request: Any = None
                      ) -> dict[str, Any]:
    """One unpaid request to a route. Never carries a payment header."""
    request = request or _default_request
    method = route.get("method") or "POST"
    reply = await request(
        method, route["url"], {**_request_headers(hub_url), "Content-Type": "application/json"}
        if method == "POST" else _request_headers(hub_url),
        MAX_PROBE_BYTES, {} if method == "POST" else None,
    )
    status = int(reply.get("status") or 0)
    seen = {"http_status": status, "probed_at": _now_iso()}
    if status == 402:
        offer = offer_from_402(reply.get("json"), reply.get("headers"))
        if offer is None:
            return {**seen, "result": "no_offer", "detail": "402 named no recipient"}
        if offer.get("price_usd") is None:
            return {**seen, **offer, "result": "unknown_asset",
                    "detail": "the 402 asks for an asset this hub cannot price in USD"}
        return {**seen, **offer, "result": "quoted"}
    if status in (400, 422):
        return {**seen, "result": "input_required",
                "detail": "answered before quoting: the route validates its input first"}
    if 200 <= status < 300:
        return {**seen, "result": "not_priced", "detail": "answered without asking for payment"}
    return {**seen, "result": "unreachable",
            "detail": reply.get("error") or f"answered {status}"}


def _now_iso(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now if now is not None else time.time()))


def judge_route(route: dict[str, Any], probe: dict[str, Any], pinned_pay_to: str) -> dict[str, Any]:
    """The stored observation of one route: what was listed, what the 402 said, and whether
    it is served."""
    row = {
        "url": route["url"],
        "method": route.get("method") or "POST",
        "description": route.get("description") or probe.get("offer_description") or "",
        "listed_price_usd": route.get("listed_price_usd"),
        **{k: v for k, v in probe.items() if k != "offer_description"},
    }
    if probe.get("result") != "quoted":
        row["listed"] = False
        return row
    if pinned_pay_to and probe.get("pay_to", "").lower() != pinned_pay_to.lower():
        row.update(listed=False, result="pay_to_changed",
                   detail="the 402 names a different payTo than the pinned one; the operator "
                          "must re-confirm with the seller")
        return row
    listed_price = route.get("listed_price_usd")
    if listed_price is not None:
        row["price_matches_listing"] = abs(float(listed_price) - float(probe["price_usd"])) < 1e-9
    row["listed"] = True
    return row


async def observe_seller(seller: dict[str, Any], *, hub_url: str = "", request: Any = None,
                         now: float | None = None) -> dict[str, Any]:
    """Observe one consented seller. Returns the fields to store; writes nothing."""
    origin = seller["origin"]
    discovery_url, doc, error = await fetch_discovery(origin, hub_url=hub_url, request=request)
    observed_at = _now_iso(now)
    if doc is None:
        return {"observed_at": observed_at, "last_error": error, "discovery_url": "",
                "routes": [], "name": seller.get("name") or origin,
                "pinned_pay_to": seller.get("pinned_pay_to") or ""}
    candidates = select_routes(parse_discovery(doc, origin), seller.get("allowed_routes"), max_routes())
    pinned = seller.get("pinned_pay_to") or ""
    routes = []
    served_free = False
    for route in candidates:
        probe = await probe_route(route, hub_url=hub_url, request=request)
        if not pinned and probe.get("result") == "quoted":
            # Pinned on first sight, like a peer's key: what changes later is the signal.
            pinned = probe.get("pay_to") or ""
        routes.append(judge_route(route, probe, pinned))
        if probe.get("result") == "not_priced":
            # The seller did the work for free: a free tier (TensorFeed gives each IP 100
            # calls a day). Every further probe would spend that allowance on a listing
            # check, so the cycle stops here.
            served_free = True
            break
    probed = {r["url"] for r in routes}
    missing = [u for u in (seller.get("allowed_routes") or [])
               if u not in {c["url"] for c in candidates}]
    error = f"not in the discovery document: {', '.join(missing[:5])}" if missing else ""
    if served_free:
        skipped = sum(1 for c in candidates if c["url"] not in probed)
        error = ("a route answered without asking for payment; the rest of this cycle "
                 f"({skipped} route(s)) was skipped so as not to use the seller's free calls")
    if not candidates:
        error = "the discovery document lists no route on the seller's own origin"
    return {
        "observed_at": observed_at,
        "last_error": error,
        "discovery_url": discovery_url,
        "routes": routes,
        "name": seller.get("name") or seller_name(doc, origin),
        "pinned_pay_to": pinned,
    }


# ── What is served ───────────────────────────────────────────────────


def _parse_iso(value: str) -> float | None:
    try:
        return float(calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return None


def is_fresh(observed_at: str, now: float | None = None) -> bool:
    stamp = _parse_iso(observed_at)
    return stamp is not None and (now if now is not None else time.time()) - stamp <= ttl_s()


def is_due(seller: dict[str, Any], now: float | None = None) -> bool:
    stamp = _parse_iso(seller.get("observed_at") or "")
    return stamp is None or (now if now is not None else time.time()) - stamp >= interval_s()


HOW_TO_BUY = (
    "Call the url yourself and pay per the 402 it returns. This hub is not in the payment "
    "path and holds no seller signature: refuse if that 402 names another payTo than pay_to "
    "here, or asks for more than amount_atomic."
)


def served_routes(sellers: list[dict[str, Any]], *, hub_url: str = "",
                  now: float | None = None) -> list[dict[str, Any]]:
    """Every route a buyer may be shown: listed on its last observation, and that observation
    is fresh."""
    out = []
    for seller in sellers:
        if not is_fresh(seller.get("observed_at") or "", now):
            continue
        for route in seller.get("routes") or []:
            if not route.get("listed"):
                continue
            out.append({
                "tier": TIER,
                "url": route["url"],
                "method": route.get("method") or "POST",
                "seller": seller["origin"],
                "seller_name": seller.get("name") or seller["origin"],
                "description": route.get("description") or "",
                "price_usd": route.get("price_usd"),
                "amount_atomic": route.get("amount_atomic") or "",
                "asset": route.get("asset") or "",
                "network": route.get("network") or "",
                "pay_to": route.get("pay_to") or "",
                "x402_version": route.get("x402_version"),
                "observed_at": route.get("probed_at") or seller.get("observed_at") or "",
                "observed_by": hub_url,
                "signed_by_seller": False,
                "how_to_buy": HOW_TO_BUY,
            })
    return out


def public_seller(seller: dict[str, Any], *, hub_url: str = "", now: float | None = None
                  ) -> dict[str, Any]:
    """One seller as the public listing shows it: every probed route with its result, so a
    route that is not served says why."""
    fresh = is_fresh(seller.get("observed_at") or "", now)
    served = {r["url"] for r in served_routes([seller], hub_url=hub_url, now=now)}
    return {
        "origin": seller["origin"],
        "name": seller.get("name") or seller["origin"],
        "tier": TIER,
        "status": "observed",
        "discovery_url": seller.get("discovery_url") or "",
        "observed_at": seller.get("observed_at") or "",
        "observed_by": hub_url,
        "fresh": fresh,
        "pinned_pay_to": seller.get("pinned_pay_to") or "",
        "consent": public_consent(seller.get("consent") or {}),
        "last_error": seller.get("last_error") or "",
        "routes": [{**r, "served": r["url"] in served} for r in seller.get("routes") or []],
        "routes_served": len(served),
    }


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(t) > 2}


def search_routes(routes: list[dict[str, Any]], intent: str, *, budget: float | None = None,
                  limit: int = 10) -> list[dict[str, Any]]:
    """Observed routes for a search, ranked by how many words of the intent they carry.

    Plain word overlap on the seller's own text and URL path, not the catalogue's semantic
    ranker: these rows are not catalogue rows, and an empty intent lists them in order.
    """
    wanted = _tokens(intent or "")
    scored = []
    for route in routes:
        if budget is not None and route.get("price_usd") is not None and route["price_usd"] > budget:
            continue
        if not wanted:
            scored.append((0.0, route))
            continue
        have = _tokens(f"{route.get('description', '')} {urlparse(route['url']).path} "
                       f"{route.get('seller_name', '')}")
        hits = len(wanted & have)
        if hits:
            scored.append((hits / len(wanted), route))
    scored.sort(key=lambda pair: -pair[0])
    return [{**route, "score": round(score, 3)} for score, route in scored[:max(0, limit)]]


# ── The cycle ────────────────────────────────────────────────────────


async def observe_due(db: Any, *, hub_url: str = "", origin: str = "", force: bool = False,
                      request: Any = None, now: float | None = None) -> dict[str, Any]:
    """Observe every seller whose last observation is older than the interval. ``origin``
    takes that seller now; ``force`` takes every seller now (both are the operator asking).
    Sellers are taken one at a time, routes one at a time: the point is to cost each seller
    as little as possible."""
    summary: dict[str, Any] = {"observed": 0, "routes_served": 0, "errors": {}}
    if not enabled():
        summary["disabled"] = True
        return summary
    for seller in db.list_observed_sellers():
        if origin and seller["origin"] != origin:
            continue
        if not origin and not force and not is_due(seller, now):
            continue
        try:
            observation = await observe_seller(seller, hub_url=hub_url, request=request, now=now)
        except Exception as exc:  # noqa: BLE001 - one seller must never stop the cycle
            logger.warning("observed seller %s: observation failed: %s", seller["origin"], exc)
            summary["errors"][seller["origin"]] = str(exc)[:200]
            continue
        db.save_observed_seller_observation(seller["origin"], observation)
        summary["observed"] += 1
        summary["routes_served"] += sum(1 for r in observation["routes"] if r.get("listed"))
        if observation.get("last_error"):
            summary["errors"][seller["origin"]] = observation["last_error"]
    return summary
