"""Expert Memory Market — a storefront where the expert actually gets paid.

Version 1 listed memories and sold a flat pass through the SaaS Gateway. The
author's side did not exist: no publisher, no wallet, no take rate, no payout.
This version adds it, and deliberately adds none of the machinery — that already
exists in **Attested Meter**, which registers publishers, splits every captured
charge and issues signed payout instructions.

So this service holds no ledger and no admin token. It does three things:

* **ranks** listings by what the network actually knows about them — Truth state,
  provenance attestation and reader scores — instead of by recency;
* **prices** are read from the Meter price list, where the publisher set them
  with their own key;
* **reads** are metered: the buyer presents their own Meter account key, the
  charge is reserved before the fetch and captured only if the Memory Market
  actually served the content. A refused read costs nothing.

The flat 7-day pass keeps working exactly as before. It is a subscription to the
storefront, and it does **not** split to publishers — a flat fee cannot be
attributed to an author without inventing the attribution. Per-read is the path
that pays them, and `/v1/listings` says so per item.
"""
from __future__ import annotations

import os
import time
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

HUB = os.getenv("MEMORY_MARKET_URL", "http://localhost:8810").rstrip("/")
API_KEY = os.getenv("MEMORY_MARKET_API_KEY", "")
GATEWAY = os.getenv("SAAS_GATEWAY_URL", "http://localhost:9400").rstrip("/")
GATEWAY_TOKEN = os.getenv("SAAS_GATEWAY_API_KEY", "")
METER = os.getenv("METER_URL", "").rstrip("/")
PUBLIC_ORIGIN = os.getenv("EXPERT_PUBLIC_ORIGIN", "https://attestedmemory.net/market").rstrip("/")

app = FastAPI(title="Expert Memory Market", version="2.0.0",
              description="Ranked expert memory, metered per read, split to the publisher.")

#: `expert.read:<memory_id>` — the operation a publisher prices in Meter for one
#: of their memories. The namespace matters: Meter refuses a publisher who tries
#: to price an operation that already belongs to someone else.
OPERATION_PREFIX = "expert.read:"


def operation_for(memory_id: str) -> str:
    return f"{OPERATION_PREFIX}{memory_id}"


# ──────────────────────────────── ranking ────────────────────────────────────

TRUTH_WEIGHT = {"supported": 0.40, "unverified": 0.0, "contested": -0.15, "rejected": -0.60}


def rank(item: dict[str, Any]) -> dict[str, Any]:
    """Score a listing from what the network knows — and show the working.

    Every term comes from a field the catalogue already publishes. Nothing here
    is inferred from popularity or from how recently someone paid, because those
    are exactly the signals a seller can manufacture. A rejected claim scores
    below an unverified one on purpose: being wrong is worse than being unproven.
    """
    truth = item.get("truth") or {}
    provenance = item.get("provenance") or {}
    reasons: list[dict[str, Any]] = []

    status = str(truth.get("status") or "unverified")
    confidence = float(truth.get("confidence") or 0)
    confidence = min(max(confidence, 0.0), 1.0)
    base = TRUTH_WEIGHT.get(status, 0.0)
    truth_term = base * (0.5 + 0.5 * confidence) if base > 0 else base
    reasons.append({"signal": "truth", "state": status, "confidence": round(confidence, 3),
                    "points": round(truth_term, 4)})

    attested = str(provenance.get("status") or "unattested") == "attested"
    provenance_term = (0.25 if attested else 0.0) + (0.05 if provenance.get("lineage_root") else 0.0)
    reasons.append({"signal": "provenance", "state": provenance.get("status") or "unattested",
                    "lineage": bool(provenance.get("lineage_root")), "points": round(provenance_term, 4)})

    average = item.get("average_score")
    count = int(item.get("score_count") or 0)
    if average is None or count == 0:
        rating_term = 0.0
    else:
        # Confidence-weighted: one five-star rating is not evidence, ten are some.
        rating_term = ((float(average) - 3.0) / 2.0) * 0.20 * min(count, 10) / 10.0
    reasons.append({"signal": "ratings", "average": average, "count": count,
                    "points": round(rating_term, 4)})

    freshness_term = 0.0
    created = str(item.get("updated_at") or item.get("created_at") or "")
    if created:
        try:
            age_days = (time.time() - time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
            freshness_term = round(max(0.0, 0.10 * (1 - min(age_days, 180) / 180)), 4)
        except ValueError:
            freshness_term = 0.0
    reasons.append({"signal": "freshness", "points": freshness_term})

    total = truth_term + provenance_term + rating_term + freshness_term
    return {"rank_score": round(total, 4), "rank_reasons": reasons}


# ───────────────────────────── upstream clients ──────────────────────────────

def _actor_headers(request: Request) -> dict[str, str]:
    forwarded = {}
    for source, target in (("x-actor-id", "X-Actor-ID"),
                           ("x-actor-public-key", "X-Actor-Public-Key"),
                           ("x-actor-timestamp", "X-Actor-Timestamp"),
                           ("x-actor-nonce", "X-Actor-Nonce"),
                           ("x-actor-signature", "X-Actor-Signature"),
                           ("x-actor-version", "X-Actor-Version"),
                           ("x-actor-intent", "X-Actor-Intent")):
        value = request.headers.get(source)
        if value:
            forwarded[target] = value
    return forwarded


def _market_headers(request: Request) -> dict[str, str]:
    return {"Authorization": f"Bearer {API_KEY}", **_actor_headers(request)}


def _pass_headers(request: Request) -> dict[str, str]:
    """The flat 7-day pass, unchanged: the gateway says whether the key is live."""
    saas_key = request.headers.get("x-saas-key", "")
    if not saas_key:
        raise HTTPException(401, "SaaS API key required")
    try:
        check = httpx.get(f"{GATEWAY}/v1/keys/introspect", params={"product": "expert-market"},
                          headers={"X-SaaS-Key": saas_key, "X-SaaS-Internal-Token": GATEWAY_TOKEN},
                          timeout=5)
    except httpx.HTTPError as error:
        raise HTTPException(503, "SaaS Gateway unavailable") from error
    if check.status_code >= 400:
        raise HTTPException(401, "SaaS API key is invalid or expired")
    return _market_headers(request)


def _catalog(request: Request, query: str, limit: int, headers: dict[str, str]) -> dict[str, Any]:
    try:
        response = httpx.get(f"{HUB}/v1/catalog", params={"q": query, "limit": limit},
                             headers=headers, timeout=15)
    except httpx.HTTPError as error:
        raise HTTPException(503, "Memory Market unavailable") from error
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "listing search failed")
    return dict(response.json())


def _prices() -> dict[str, dict[str, Any]]:
    """The Meter price list, keyed by operation. Public and keyless by design."""
    if not METER:
        return {}
    try:
        response = httpx.get(f"{METER}/v1/prices", timeout=8)
        if response.status_code >= 400:
            return {}
        return {str(item["operation"]): item for item in response.json().get("operations", [])}
    except (httpx.HTTPError, ValueError, KeyError):
        return {}


def _meter(method: str, path: str, key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not METER:
        raise HTTPException(503, "METER_URL is not configured; per-read purchase is unavailable")
    try:
        response = httpx.request(method, f"{METER}{path}", json=payload,
                                 headers={"x-api-key": key}, timeout=15)
    except httpx.HTTPError as error:
        raise HTTPException(503, "metering service unavailable") from error
    if response.status_code >= 400:
        detail = "metering refused the request"
        try:
            body = response.json()
            if isinstance(body, dict) and isinstance(body.get("detail"), str):
                detail = body["detail"]
        except ValueError:
            pass
        raise HTTPException(response.status_code if response.status_code < 500 else 503, detail)
    return dict(response.json())


# ────────────────────────────────── routes ───────────────────────────────────

class ReadRequest(BaseModel):
    memory_id: str = Field(min_length=1, max_length=200)


@app.get("/healthz")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "product": "expert-memory-market",
        "version": "2.0.0",
        "hub": HUB,
        "metering": bool(METER),
        "ranking": "truth · provenance · ratings · freshness",
    }


def _enrich(items: list[dict[str, Any]], prices: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in items:
        memory_id = str(item.get("id") or "")
        price = prices.get(operation_for(memory_id))
        row = dict(item, **rank(item))
        row["operation"] = operation_for(memory_id)
        row["purchasable"] = price is not None
        row["price_usdc"] = price["price_usdc"] if price else None
        row["publisher_id"] = price.get("publisher_id") if price else None
        # Said per item rather than once in a footnote: the pass is a subscription
        # to the storefront and splits to nobody; the per-read path pays the author.
        row["pays_publisher"] = bool(price and price.get("publisher_id"))
        enriched.append(row)
    enriched.sort(key=lambda row: row["rank_score"], reverse=True)
    return enriched


@app.get("/v1/listings")
def listings_v2(request: Request, q: str = "", limit: int = 30) -> dict[str, Any]:
    """Ranked listings. Keyless: browsing is how anyone decides whether to buy."""
    catalog = _catalog(request, q, max(1, min(limit, 100)), _market_headers(request))
    items = _enrich(list(catalog.get("items") or []), _prices())
    return {
        "query": q,
        "total": catalog.get("total", len(items)),
        "count": len(items),
        "items": items,
        "ranking": {
            "signals": ["truth", "provenance", "ratings", "freshness"],
            "note": "every term comes from a published catalogue field, and each listing "
                    "carries its own breakdown in rank_reasons",
        },
        "purchase": {
            "per_read": f"{PUBLIC_ORIGIN}/v1/read",
            "meter": METER or None,
            "note": "the flat pass is a subscription to this storefront and splits to nobody; "
                    "a per-read purchase pays the memory's publisher",
        },
    }


@app.get("/v1/listings/{memory_id}")
def listing_v2(memory_id: str, request: Request) -> dict[str, Any]:
    try:
        response = httpx.get(f"{HUB}/v1/catalog/{memory_id}", headers=_market_headers(request), timeout=15)
    except httpx.HTTPError as error:
        raise HTTPException(503, "Memory Market unavailable") from error
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "listing unavailable")
    item = dict(response.json())
    # A listing page must not leak the thing being sold.
    item.pop("content", None)
    return _enrich([item], _prices())[0]


@app.post("/v1/read")
def metered_read(body: ReadRequest, request: Request) -> dict[str, Any]:
    """Buy one read. Reserved before the fetch, captured only if it was served.

    The buyer's own Meter account key does the paying, so this service never
    holds anyone's balance — and a read the Memory Market refuses is released,
    not billed. That ordering is the whole contract: charge after delivery and a
    503 upstream becomes someone's money.
    """
    key = request.headers.get("x-meter-key", "")
    if len(key) < 40:
        raise HTTPException(401, "a Meter account key is required (x-meter-key)")
    operation = operation_for(body.memory_id)
    reservation = _meter("POST", "/v1/meter/authorize", key, {"operation": operation, "units": 1})
    try:
        response = httpx.get(f"{HUB}/v1/memories/{body.memory_id}",
                             headers=_market_headers(request), timeout=20)
    except httpx.HTTPError as error:
        _meter("POST", "/v1/meter/release", key,
               {"authorization_id": reservation["authorization_id"], "reason": "market unreachable"})
        raise HTTPException(503, "Memory Market unavailable") from error
    if response.status_code >= 400 or "content" not in (response.json() or {}):
        _meter("POST", "/v1/meter/release", key,
               {"authorization_id": reservation["authorization_id"],
                "reason": f"market refused with {response.status_code}"})
        raise HTTPException(response.status_code if response.status_code >= 400 else 402,
                            "the market did not serve this memory; nothing was charged")
    memory = dict(response.json())
    charge = _meter("POST", "/v1/meter/capture", key,
                    {"authorization_id": reservation["authorization_id"]})
    return {"memory": memory, "charge": charge, "operation": operation}


@app.get("/v1/publishers/{publisher_id}")
def publisher(publisher_id: str) -> dict[str, Any]:
    if not METER:
        raise HTTPException(503, "METER_URL is not configured")
    try:
        response = httpx.get(f"{METER}/v1/publishers/{publisher_id}", timeout=8)
    except httpx.HTTPError as error:
        raise HTTPException(503, "metering service unavailable") from error
    if response.status_code >= 400:
        raise HTTPException(404, "publisher not found")
    return dict(response.json())


@app.get("/v1/publishing")
def how_to_publish() -> dict[str, Any]:
    """What an expert has to do to get paid — in the order they have to do it."""
    return {
        "steps": [
            {"step": 1, "what": "register as a publisher with your signed actor identity",
             "call": f"POST {METER or 'https://meter.attestedmemory.net'}/v1/publishers",
             "body": {"label": "your desk", "payout_address": "0x… on Base"}},
            {"step": 2, "what": "price one of your memories with the key you were given",
             "call": f"POST {METER or 'https://meter.attestedmemory.net'}/v1/publishers/me/prices",
             "body": {"operation": f"{OPERATION_PREFIX}<memory_id>", "price_usdc": "2.00"}},
            {"step": 3, "what": "it is now purchasable here; every read accrues your share",
             "call": f"POST {PUBLIC_ORIGIN}/v1/read"},
            {"step": 4, "what": "watch what you have earned",
             "call": f"GET {METER or 'https://meter.attestedmemory.net'}/v1/publishers/me"},
        ],
        "split": "70% to the publisher, 30% platform; a Publisher Pro key makes it 85/15",
        "payout": "above the minimum the operator issues a signed attested.payout/v1 "
                  "instruction and records the transaction hash against it",
        "note": "this storefront never holds your balance or your key — Meter does the "
                "accounting and you keep the credential",
    }


@app.get("/v1/stats")
def stats(request: Request) -> dict[str, Any]:
    prices = _prices()
    expert_prices = {op: row for op, row in prices.items() if op.startswith(OPERATION_PREFIX)}
    publishers = {row.get("publisher_id") for row in expert_prices.values() if row.get("publisher_id")}
    return {
        "product": "expert-memory-market",
        "priced_memories": len(expert_prices),
        "publishers": len(publishers),
        "metering": bool(METER),
    }


# ───────────────────────── v1 surface, unchanged ─────────────────────────────
# The pass-holder routes the existing landing calls. Kept byte-compatible: a
# storefront that breaks its own product page to ship a better one has shipped
# nothing.

@app.get("/api/listings")
def listings(request: Request, q: str = "", limit: int = 30) -> Any:
    return _catalog(request, q, max(1, min(limit, 100)), _pass_headers(request))


@app.get("/api/listings/{memory_id}")
def listing(memory_id: str, request: Request) -> Any:
    response = httpx.get(f"{HUB}/v1/memories/{memory_id}", headers=_pass_headers(request), timeout=15)
    if response.status_code >= 400:
        raise HTTPException(response.status_code, "listing unavailable")
    return response.json()
