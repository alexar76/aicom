from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import re
import logging
import os
import time
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .clients import TrustClients, commitment
from .aimarket import BY_CAPABILITY, CAPABILITIES, register, signed_protocol_manifest
from .config import Settings, get_settings, production_mode
from .models import (
    Catalog, Grant, GrantCreate, HubStats, MemoryCreate, MemorySummary, MemoryUnit, PaymentConfirm,
    PaymentOrder, PaymentOrderCreate, ScoreCreate, ScoreResult, VerifyMemory,
)
from .payments import PaymentDesk, PaymentError, RpcUnavailable
from .store import MemoryStore
from .signing import ProviderSigner

hub_published = 0
logger = logging.getLogger(__name__)

SERVICE_MAP = (
    {"id": "memory-market", "name": "Memory Market", "role": "primary", "url": None, "capabilities": 5},
    {"id": "truth-layer", "name": "Truth Layer", "role": "evidence", "url": "truth", "capabilities": 4},
    {"id": "provenance-ledger", "name": "Provenance Ledger", "role": "lineage", "url": "provenance", "capabilities": 3},
)


# Ed25519 points of small order (orders 1, 2, 4, 8; sign bit cleared), as libsodium checks them.
# `cryptography` (OpenSSL) accepts, under such a key, a signature valid for EVERY message, and no
# secret exists for these keys — so a key or R among them is refused before verifying. 2026-10-12.
_ED25519_SMALL_ORDER = frozenset(bytes.fromhex(h) for h in (
    "0000000000000000000000000000000000000000000000000000000000000000",
    "0100000000000000000000000000000000000000000000000000000000000000",
    "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
    "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
    "ecffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "edffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
    "eeffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff7f",
))


def _ed25519_small_order(point: bytes) -> bool:
    return len(point) == 32 and (point[:31] + bytes([point[31] & 0x7F])) in _ED25519_SMALL_ORDER


@lru_cache
def provider_signer() -> ProviderSigner:
    return ProviderSigner(get_settings().provider_key_file)


def _attest_payment(order: PaymentOrder) -> None:
    settings = get_settings()
    unit = store().get_unchecked(order.memory_id)
    # lineage.get@v1 is open to any hub caller, so the receipt must not name the buyer or the
    # transaction (that linked a wallet to what it bought). It commits to both: the market, and the
    # buyer who knows their order, transaction and actor id, can show the settlement it records.
    receipt = TrustClients(settings).attest(
        unit, "shared", "memory-market:payment",
        {"settlement": commitment(f"{order.order_id}|{(order.tx_hash or '').lower()}|{order.grantee_id}"),
         "asset": "USDC", "chain": "base"},
    )
    if receipt:
        store().set_provenance(unit.id, receipt["id"], receipt["chain_root"], created=False)


@lru_cache
def payment_desk() -> PaymentDesk:
    return PaymentDesk(store(), get_settings(), on_settle=_attest_payment)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if production_mode():
        settings = get_settings()
        if len(os.getenv("AIMARKET_CAPABILITY_TOKEN", "")) < 32:
            raise RuntimeError("AIMARKET_CAPABILITY_TOKEN must be configured in production")
        provider_signer()
        store()
    async def publish() -> None:
        global hub_published
        hub_published = await register(provider_signer())

    async def watch_payments() -> None:
        while True:
            try:
                await asyncio.to_thread(payment_desk().poll_once)
            except Exception as error:
                logger.warning("payment scanner: %s", error)
            await asyncio.sleep(get_settings().payment_poll_seconds)

    tasks = [asyncio.create_task(publish())]
    if payment_desk().enabled:
        tasks.append(asyncio.create_task(watch_payments()))
    yield
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(title="Attested Memory Market", version="0.2.0", lifespan=lifespan)
from .actor_auth import ActorProofBody
app.add_middleware(ActorProofBody)


def team_context(
    x_team_id: str | None = Header(default=None),
    x_team_assertion: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str | None:
    if not x_team_id and not x_team_assertion:
        return None
    if not x_team_id or not x_team_assertion or not x_actor_id:
        raise HTTPException(status_code=401, detail="complete team access assertion required")
    parts = x_team_assertion.split("|")
    if len(parts) != 4 or parts[0] != x_team_id or parts[1] != x_actor_id:
        raise HTTPException(status_code=401, detail="invalid team access assertion")
    try:
        expires = int(parts[2])
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid team access assertion") from None
    if expires < int(time.time()):
        raise HTTPException(status_code=401, detail="expired team access assertion")
    payload = "|".join(parts[:3])
    expected = hmac.new(settings.team_auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts[3]):
        raise HTTPException(status_code=401, detail="invalid team access assertion")
    return x_team_id


@lru_cache
def store() -> MemoryStore:
    return MemoryStore(get_settings().db_path)


def _b64url(value: str, label: str) -> bytes:
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True,
        )
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail=f"invalid actor {label}") from None
    return decoded


def _production_actor(request: Request, settings: Settings) -> str:
    from .actor_auth import verify_actor_request
    authorization = request.headers.get("authorization", "")
    if not hmac.compare_digest(authorization, f"Bearer {settings.api_key}"):
        raise HTTPException(401, "authenticated actor required")
    return verify_actor_request(request, audience=os.getenv("MEMORY_MARKET_ACTOR_AUDIENCE", "memory-market"),
                                spend_nonce=store().connection.spend_actor_nonce)


def optional_actor(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
    x_actor_public_key: str | None = Header(default=None),
    x_actor_timestamp: str | None = Header(default=None),
    x_actor_nonce: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str | None:
    if not x_actor_id:
        return None
    if len(x_actor_id) > 120:
        raise HTTPException(status_code=400, detail="X-Actor-ID is too long")
    if production_mode():
        return _production_actor(request, settings)
    return x_actor_id


def require_actor(
    request: Request,
    authorization: str | None = Header(default=None),
    x_actor_id: str | None = Header(default=None),
    x_actor_signature: str | None = Header(default=None),
    x_actor_public_key: str | None = Header(default=None),
    x_actor_timestamp: str | None = Header(default=None),
    x_actor_nonce: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    expected_authorization = f"Bearer {settings.api_key}"
    if not authorization or not hmac.compare_digest(authorization, expected_authorization):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")
    if not x_actor_id or len(x_actor_id) > 120:
        raise HTTPException(status_code=400, detail="X-Actor-ID is required")
    if production_mode():
        _production_actor(request, settings)
    return x_actor_id


def require_capability_access(request: Request) -> None:
    # Fail CLOSED. This used to check `AIFACTORY_PROD` and return early when it was unset,
    # so a deployment that forgot the flag ran with no capability authentication at all.
    # Only an explicit AIFACTORY_DEV=1 relaxes it now (see config.production_mode).
    if not production_mode():
        return
    expected = os.getenv("AIMARKET_CAPABILITY_TOKEN", "").strip()
    supplied = request.headers.get("x-aimarket-internal-token", "")
    if len(expected) < 32 or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=401, detail="capability gateway authentication required")


@app.get("/healthz")
def health(response: Response, settings: Settings = Depends(get_settings)) -> dict:
    database_ok = True
    try:
        store().connection.execute("SELECT 1")
    except Exception:
        database_ok = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database_ok else "degraded", "service": "memory-market",
        "truth_connected": bool(settings.truth_url),
        "provenance_connected": bool(settings.provenance_url),
        "payment_enabled": bool(settings.payment_recipient),
        "payment_rail": "base-usdc-exact-transfer" if settings.payment_recipient else "closed",
        "hub_published": hub_published,
        "database": {"backend": "postgresql" if store().connection.is_postgres else "sqlite", "healthy": database_ok},
        "capabilities": len(CAPABILITIES),
        "pqc": "hybrid-ml-dsa-65" if provider_signer().pq_public_key else "classical-only",
    }


@app.get("/v1/network")
def network(settings: Settings = Depends(get_settings)) -> dict:
    urls = {"truth": settings.truth_url, "provenance": settings.provenance_url}
    nodes = []
    with httpx.Client(timeout=0.8) as client:
        for spec in SERVICE_MAP:
            item = {key: value for key, value in spec.items() if key != "url"}
            if spec["id"] == "memory-market":
                item.update({"status": "online", "pqc": bool(provider_signer().pq_public_key), "published": hub_published})
            else:
                try:
                    service_health = client.get(f"{urls[str(spec['url'])].rstrip('/')}/healthz").json()
                    item.update({
                        "status": "online" if service_health.get("status") == "ok" else "degraded",
                        "pqc": str(service_health.get("pqc", "")).startswith("hybrid"),
                        "published": int(service_health.get("hub_published", 0)),
                    })
                except Exception:
                    item.update({"status": "offline", "pqc": False, "published": 0})
            nodes.append(item)

        hub = {"status": "offline", "advertised_capabilities": 0, "ecosystem": []}
        if settings.hub_url:
            try:
                document = client.get(f"{settings.hub_url.rstrip('/')}/.well-known/ai-market.json").json()
                hub = {
                    "status": "online",
                    "advertised_capabilities": int(document.get("capabilities_count", 0)),
                    "ecosystem": document.get("ecosystem", {}).get("nodes", []),
                }
            except Exception:
                pass

    roots = [root.strip() for root in os.getenv(
        "AIMARKET_BOOTSTRAP_HUB_URLS",
        "https://modelmarket.dev,https://independentai.network/hub",
    ).split(",") if root.strip()]
    return {
        "hub": hub, "nodes": nodes, "capabilities": sum(item["capabilities"] for item in nodes),
        "crypto": {"mode": "hybrid", "algorithms": ["Ed25519", "ML-DSA-65"], "required": True},
        "federation": [{"url": root, "state": "configured"} for root in roots],
    }


@app.get("/v1/stats", response_model=HubStats)
def stats(actor_id: str | None = Depends(optional_actor), settings: Settings = Depends(get_settings)) -> HubStats:
    return store().stats(actor_id, bool(settings.payment_recipient))


_TRUTH_STATUSES = ("unverified", "supported", "contested", "rejected")


def _truth_filter(value: object) -> tuple[str, ...] | None:
    """``truth`` on a catalog or search: empty = the default (all but ``rejected``), ``any`` = no
    filter, else a comma-separated list of Truth Layer statuses. An unknown status is a 422, not an
    empty result that looks like "nothing matched"."""
    from .store import DEFAULT_TRUTH

    if value is None or (isinstance(value, str) and not value.strip()):
        return DEFAULT_TRUTH
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="truth must be a comma-separated string")
    if value.strip().casefold() == "any":
        return None
    wanted = tuple(dict.fromkeys(part.strip().casefold() for part in value.split(",") if part.strip()))
    unknown = [status for status in wanted if status not in _TRUTH_STATUSES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"unknown truth status {', '.join(unknown)}; "
                                                    f"use {', '.join(_TRUTH_STATUSES)} or any")
    return wanted


@app.get("/v1/catalog", response_model=Catalog)
def catalog(
    q: str = Query(default="", max_length=200), limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0), actor_id: str | None = Depends(optional_actor), team_id: str | None = Depends(team_context),
    truth: str = Query(default="", max_length=80, description="Truth Layer statuses to include, comma-separated, "
                       "or any; default: all but rejected"),
) -> Catalog:
    items, total = store().catalog(q, actor_id, limit, offset, team_id, _truth_filter(truth))
    return Catalog(items=items, total=total, query=q)


@app.get("/v1/catalog/{memory_id}", response_model=MemorySummary)
def catalog_entry(memory_id: str, actor_id: str | None = Depends(optional_actor),
                  team_id: str | None = Depends(team_context)) -> MemorySummary:
    """Public sale metadata, including the author, without delivering paid content."""
    try:
        unit = store().get_unchecked(memory_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None
    if unit.visibility not in {"public", "paid"} and not store().can_read(unit, actor_id, team_id):
        raise HTTPException(status_code=404, detail="memory not found")
    return store().listing(unit, actor_id, team_id)


@app.post("/v1/memories", response_model=MemoryUnit, status_code=201)
def create_memory(
    request: MemoryCreate, actor_id: str = Depends(require_actor), settings: Settings = Depends(get_settings)
) -> MemoryUnit:
    unit = store().create(request, actor_id)
    receipt = TrustClients(settings).attest(unit, "created", actor_id)
    if receipt:
        store().set_provenance(unit.id, receipt["id"], receipt["chain_root"], created=True)
    return store().get_unchecked(unit.id)


@app.get("/v1/memories/{memory_id}", response_model=MemoryUnit)
def read_memory(memory_id: str, actor_id: str | None = Depends(optional_actor), team_id: str | None = Depends(team_context)) -> MemoryUnit:
    try:
        unit = store().get_unchecked(memory_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None
    if not store().can_read(unit, actor_id, team_id):
        if unit.visibility == "paid":
            return JSONResponse(
                status_code=402,
                content={
                    "detail": "confirmed USDC payment or explicit access grant required",
                    "memory_id": unit.id, "price_usdc": unit.price_usdc,
                    "payment": {
                        "enabled": payment_desk().enabled, "rail_url": "/v1/billing/rail",
                        "create_order_url": "/v1/billing/orders",
                    },
                },
                headers={"Payment-Required": "grant-or-settlement"},
            )
        raise HTTPException(status_code=403, detail="memory is not visible to this actor")
    return unit


@app.post("/v1/memories/{memory_id}/grants", response_model=Grant)
def share_memory(memory_id: str, request: GrantCreate, actor_id: str = Depends(require_actor)) -> Grant:
    try:
        return store().grant(memory_id, request.grantee_id, actor_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from None


@app.delete("/v1/memories/{memory_id}/grants/{grantee_id:path}", response_model=Grant)
def revoke_memory_grant(memory_id: str, grantee_id: str, actor_id: str = Depends(require_actor)) -> Grant:
    try:
        return store().revoke(memory_id, grantee_id, actor_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from None


@app.put("/v1/memories/{memory_id}/score", response_model=ScoreResult)
def score_memory(memory_id: str, request: ScoreCreate, actor_id: str = Depends(require_actor)) -> ScoreResult:
    try:
        return store().score(memory_id, actor_id, request.score)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None


@app.post("/v1/memories/{memory_id}/verify", response_model=MemoryUnit)
def verify_memory(
    memory_id: str, request: VerifyMemory, actor_id: str = Depends(require_actor),
    settings: Settings = Depends(get_settings),
) -> MemoryUnit:
    try:
        unit = store().get_unchecked(memory_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None
    if unit.owner_id != actor_id:
        raise HTTPException(status_code=403, detail="only the owner can request verification")
    result = TrustClients(settings).verify(unit, request)
    if result is None:
        raise HTTPException(status_code=503, detail="truth layer unavailable; memory remains unverified")
    store().set_truth(unit.id, result["status"], result["confidence"], result["evidence_pack_id"])
    updated = store().get_unchecked(unit.id)
    # The pack holds the claim, which for a unit that is not public can repeat its content; the
    # receipt (readable by anyone through lineage.get@v1) then carries a hash of the pack id.
    pack = result["evidence_pack_id"]
    receipt = TrustClients(settings).attest(
        updated, "verified", "truth-layer",
        {"status": result["status"], "confidence": result["confidence"],
         **({"evidence_pack_id": pack} if updated.visibility == "public" else {"evidence_pack_ref": commitment(pack)})},
    )
    if receipt:
        store().set_provenance(unit.id, receipt["id"], receipt["chain_root"], created=False)
    return store().get_unchecked(unit.id)


@app.get("/v1/billing/rail")
def payment_rail() -> dict:
    return payment_desk().rail()


def _consume_payment_ip_rate(request: Request) -> None:
    source_ip = (request.client.host if request.client else "unknown")[:128]
    if not store().connection.insert_or_update_rate_limit(source_ip, int(time.time())):
        raise HTTPException(
            status_code=429, detail="payment request rate limit exceeded", headers={"Retry-After": "60"},
        )


@app.post("/v1/billing/orders", response_model=PaymentOrder, status_code=201)
def create_payment_order(
    request: PaymentOrderCreate, http_request: Request, actor_id: str = Depends(require_actor),
) -> PaymentOrder:
    if request.grantee_id != actor_id:
        raise HTTPException(status_code=403, detail="grantee_id must match the authenticated actor")
    _consume_payment_ip_rate(http_request)
    try:
        return payment_desk().create(request.memory_id, request.grantee_id)
    except PaymentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RpcUnavailable as error:
        raise HTTPException(status_code=503, detail=f"Base RPC unavailable: {error}") from None
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None


def _payment_actor(order_id: str, actor_id: str) -> None:
    try:
        row = store().payment_order(order_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="payment order not found") from None
    if row["grantee_id"] != actor_id:
        raise HTTPException(status_code=403, detail="payment order belongs to another actor")


@app.get("/v1/billing/orders/{order_id}", response_model=PaymentOrder)
def get_payment_order(order_id: str, actor_id: str = Depends(require_actor)) -> PaymentOrder:
    _payment_actor(order_id, actor_id)
    try:
        return payment_desk().get(order_id)
    except PaymentError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@app.post("/v1/billing/orders/{order_id}/confirm", response_model=PaymentOrder)
def confirm_payment_order(
    order_id: str, request: PaymentConfirm, http_request: Request,
    actor_id: str = Depends(require_actor),
) -> PaymentOrder:
    _payment_actor(order_id, actor_id)
    _consume_payment_ip_rate(http_request)
    try:
        return payment_desk().confirm(order_id, request.tx_hash)
    except PaymentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except RpcUnavailable as error:
        raise HTTPException(status_code=503, detail=f"Base RPC unavailable: {error}") from None


_BUYER_REF = re.compile(r"bref-[0-9a-f]{32}")
_NEEDS_BUYER = (
    "this capability needs a buyer the hub can name: call it with an X-API-Key credit "
    "account (or a verified payment); trial and anonymous calls can read public memories only"
)


def _aimarket_actor(request: Request) -> str | None:
    """The buyer the hub vouches for on this invoke, or None for an anonymous caller.

    The hub sends `X-AIMarket-Buyer-Ref` (aimarket_hub/provider_buyer_ref.py) only to its
    operator's own providers, next to the internal token this route already requires, and
    only when it authenticated the buyer: a credit account, a verified x402 payer or a held
    payment channel. The owner used to be a hash of `X-Payment-Channel`, which was empty for
    every buyer on credits, x402 or a trial — all of them one shared owner, reading each
    other's private memories — and keyed per hub process for channel buyers, so it changed
    on every hub restart. None now means: public memories only, no writes.
    """
    ref = (request.headers.get("x-aimarket-buyer-ref") or "").strip()
    if not _BUYER_REF.fullmatch(ref):
        return None
    return "aimarket:" + ref


def _public_base(default_port: int) -> str:
    """Where this service can be REACHED from outside, for its own well-known.

    `AIMARKET_INVOKE_BASE` is where the co-located hub DIALS this service — a container
    hostname on a single-host deploy (`http://memory-market:8810`). Using it to describe
    ourselves handed that hostname to everyone who fetched our well-known: a manifest URL
    that resolves on exactly one machine in the world.

    One variable cannot answer both "where do I call you" and "where are you", so
    `AIMARKET_PUBLIC_BASE` answers the second and falls back to the first. A deployment that
    sets nothing behaves exactly as before.
    """
    public = os.getenv("AIMARKET_PUBLIC_BASE", "").strip()
    if public.startswith(("http://", "https://")):
        return public.rstrip("/")
    return os.getenv("AIMARKET_INVOKE_BASE", f"http://localhost:{default_port}").rstrip("/")


@app.get("/.well-known/ai-market.json")
def well_known() -> dict:
    signer = provider_signer()
    provider_base = _public_base(8810)
    return {
        "name": "Memory Market", "description": "Portable attested memory for agents.",
        "protocol_versions": ["v2"], "hub_version": "provider-0.2.0",
        "manifest_url": f"{provider_base}/ai-market/v2/manifest",
        "products_count": len(CAPABILITIES), "capabilities_count": len(CAPABILITIES),
        "categories": sorted({item.category for item in CAPABILITIES}),
        "signer_public_key": signer.public_key, "pq_public_key": signer.pq_public_key,
    }


@app.get("/ai-market/v2/manifest")
def protocol_manifest() -> dict:
    return signed_protocol_manifest(provider_signer())


@app.post("/capabilities/{product_id}/{capability_id}/invoke", dependencies=[Depends(require_capability_access)])
def invoke_capability(product_id: str, capability_id: str, body: dict, request: Request, response: Response) -> dict:
    capability = BY_CAPABILITY.get(capability_id)
    if capability is None or capability.product_id != product_id:
        raise HTTPException(status_code=404, detail="unknown capability")
    payload = body.get("input", body)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="input must be an object")
    actor = _aimarket_actor(request)
    if actor is None and capability_id not in ("memory.read@v1", "memory.search@v1"):
        raise HTTPException(status_code=403, detail=_NEEDS_BUYER)
    try:
        if capability_id == "memory.write@v1":
            allowed = {key: payload[key] for key in ("title", "content", "tags", "visibility", "price_usdc", "source_refs", "parent_memory_ids") if key in payload}
            unit = store().create(MemoryCreate.model_validate(allowed), actor)
            # The REST write asks the ledger for a receipt; this one did not, so units written
            # through the hub had no provenance at all. A ledger that is down leaves the unit
            # unattested for python -m memory_market.reconcile_provenance to finish.
            receipt = TrustClients(get_settings()).attest(unit, "created", actor)
            if receipt:
                store().set_provenance(unit.id, receipt["id"], receipt["chain_root"], created=True)
                unit = store().get_unchecked(unit.id)
            result = unit.model_dump(mode="json")
        elif capability_id == "memory.read@v1":
            unit = store().get_unchecked(str(payload.get("memory_id") or ""))
            if not store().can_read(unit, actor):
                raise HTTPException(status_code=403, detail="memory requires an access grant")
            result = unit.model_dump(mode="json")
        elif capability_id == "memory.search@v1":
            limit = max(1, min(int(payload.get("limit", 20)), 100))
            items, total = store().catalog(str(payload.get("query") or ""), actor, limit, 0,
                                           truth=_truth_filter(payload.get("truth")))
            result = {"items": [item.model_dump(mode="json") for item in items], "total": total}
        elif capability_id == "memory.share@v1":
            memory_id, grantee_id = str(payload.get("memory_id") or ""), str(payload.get("grantee_id") or "")
            if payload.get("revoke") is True:
                grant = store().revoke(memory_id, grantee_id, actor)
            else:
                grant = store().grant(memory_id, grantee_id, actor)
            result = grant.model_dump(mode="json")
        else:
            score = int(payload.get("score", 0))
            if not 1 <= score <= 5:
                raise ValueError("score must be between 1 and 5")
            scored = store().score(str(payload.get("memory_id") or ""), actor, score)
            result = scored.model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail="memory not found") from None
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None
    except (ValueError, PermissionError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    for key, value in provider_signer().response_headers(capability_id, product_id, payload, result).items():
        response.headers[key] = value
    return {"success": True, "result": result, "crypto": {"hybrid": provider_signer().pq_public_key is not None}}


static_directory = Path(os.getenv(
    "MEMORY_MARKET_STATIC_DIR", str(Path(__file__).resolve().parents[2] / "static")
))
app.mount("/", StaticFiles(directory=static_directory, html=True), name="console")
