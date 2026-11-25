"""Attested Meter — pay-per-call metering for memory and capabilities.

Agents do not want a subscription; they want to pay for the context they
actually read. This service is the x402-shaped meter in front of the Attested
Memory plane:

* **Prepaid accounts.** Exact USDC on Base tops a balance up. No card, no
  account manager, no invoice email — the invoice is bound to the address you
  declare as the payer.
* **Reserve → capture → release.** The allowance is taken at entry and handed
  back when the upstream refuses, so a failed call never costs the caller and a
  slow caller never gets a free one.
* **A price list, not a price guess.** Every metered path resolves its price
  through the same table; there is no second entry point that can quote its own.
* **Publisher splits.** Each captured charge accrues to the publisher of the
  thing that was read, and payouts leave a signed instruction behind.

The x402 surface answers `402` with a machine-readable challenge. It is
deliberately labelled `attested-exact`, **not** the canonical `exact` scheme:
canonical x402 settles an EIP-3009 authorization through a facilitator, and this
service holds no key and settles nothing. It verifies a finalized transfer of an
exact amount from a declared payer address instead. Calling that `exact` would be
a lie a client could act on. See `docs/x402.md`.
"""
from __future__ import annotations

import hmac
import json
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Iterator

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import (
    EVM_ADDRESS,
    OBJECT_OUTPUT,
    AIMarket,
    Billing,
    Capability,
    Database,
    Kova,
    Plan,
    Signer,
    canonical,
    client_ip,
    load_settings,
    micro_from_usd,
    now,
    rate_limit,
    sha256_hex,
    usd_from_micro,
    verified_actor,
    verify_signature,
)

SERVICE = "attested-meter"
VERSION = "1.0.0"
PREFIX = "METER"

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS meter_accounts (
        account_id TEXT PRIMARY KEY,
        owner_actor TEXT UNIQUE NOT NULL,
        label TEXT NOT NULL,
        balance_micro BIGINT NOT NULL DEFAULT 0,
        reserved_micro BIGINT NOT NULL DEFAULT 0,
        lifetime_spent_micro BIGINT NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meter_ops (
        op_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        operation TEXT NOT NULL,
        units BIGINT NOT NULL,
        unit_price_micro BIGINT NOT NULL,
        amount_micro BIGINT NOT NULL,
        publisher_id TEXT,
        publisher_micro BIGINT NOT NULL DEFAULT 0,
        state TEXT NOT NULL DEFAULT 'reserved',
        reference TEXT,
        created_at TEXT NOT NULL,
        settled_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meter_prices (
        operation TEXT PRIMARY KEY,
        unit_price_micro BIGINT NOT NULL,
        unit TEXT NOT NULL DEFAULT 'call',
        publisher_id TEXT,
        description TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meter_publishers (
        publisher_id TEXT PRIMARY KEY,
        payout_address TEXT NOT NULL,
        label TEXT NOT NULL,
        share_bps INTEGER NOT NULL,
        accrued_micro BIGINT NOT NULL DEFAULT 0,
        paid_micro BIGINT NOT NULL DEFAULT 0,
        pro_key_id TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meter_payouts (
        payout_id TEXT PRIMARY KEY,
        publisher_id TEXT NOT NULL,
        amount_micro BIGINT NOT NULL,
        document TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at TEXT NOT NULL,
        executed_at TEXT,
        execution_tx TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_meter_ops_account ON meter_ops(account_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_meter_ops_state ON meter_ops(state)",
)

PLANS = (
    Plan("meter.pro.monthly", "Publisher Pro", "99.00", 30,
         "Halves the platform take rate on everything you publish, from 30% to 15%.", scope="publisher"),
)

DEFAULT_PRICES = (
    ("memory.read", 400, "call", "One attested Memory Unit read, provenance included."),
    ("memory.write", 1200, "call", "One attested Memory Unit write with a signed receipt."),
    ("memory.search", 900, "call", "Semantic search across the memory catalogue."),
    ("truth.check", 700, "call", "One Truth Layer claim state lookup."),
    ("provenance.verify", 300, "call", "One provenance receipt verification."),
)

cfg = load_settings(SERVICE, PREFIX, extra_keys=("MEMORY_MARKET_URL", "MEMORY_MARKET_API_KEY",
                                                 "TAKE_BPS", "PRO_TAKE_BPS", "MIN_TOPUP_USDC",
                                                 "MIN_PAYOUT_USDC", "CAPABILITY_TOKEN",
                                                 "AIMARKET_HUB_URL", "PUBLISHER_TOKEN",
                                                 "INVOKE_BASE"))
db = Database(cfg.database_url or "sqlite:///./data/attested-meter.sqlite3", SCHEMA)
kova = Kova(cfg)
billing = Billing(cfg, db, kova, PLANS)
signer = Signer(cfg.signing_key_path, pqc=cfg.pqc)

TAKE_BPS = max(0, min(int(cfg.extra.get("TAKE_BPS") or 3000), 5000))
PRO_TAKE_BPS = max(0, min(int(cfg.extra.get("PRO_TAKE_BPS") or 1500), TAKE_BPS))
MIN_TOPUP_MICRO = micro_from_usd(cfg.extra.get("MIN_TOPUP_USDC") or "1.00")
MIN_PAYOUT_MICRO = micro_from_usd(cfg.extra.get("MIN_PAYOUT_USDC") or "5.00")
MEMORY_MARKET_URL = (cfg.extra.get("MEMORY_MARKET_URL") or "").rstrip("/")
MEMORY_MARKET_KEY = cfg.extra.get("MEMORY_MARKET_API_KEY") or ""
def _web_root() -> str:
    """Find the landing assets whether we run from source or from a wheel.

    In the container the package is installed into site-packages, so a path
    derived from `__file__` climbs out of the venv and lands nowhere near
    `/app/web` — the landing pages simply stop being served, with a bare 404 and
    no error anywhere. Resolution is therefore explicit and checked: the first
    candidate that actually contains index.html wins.
    """
    candidates = [os.getenv(f"{PREFIX}_WEB_ROOT", "").strip(),
                  os.path.join(os.getcwd(), "web"),
                  os.path.join(os.path.dirname(os.path.dirname(
                      os.path.dirname(os.path.abspath(__file__)))), "web"),
                  "/app/web"]
    for candidate in candidates:
        if candidate and os.path.isfile(os.path.join(candidate, "index.html")):
            return candidate
    return ""


WEB_ROOT = _web_root()


def _seed_prices() -> None:
    for operation, price, unit, description in DEFAULT_PRICES:
        db.execute(
            "INSERT INTO meter_prices (operation, unit_price_micro, unit, description, updated_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (operation) DO NOTHING",
            (operation, price, unit, description, now()))


_seed_prices()


# ─────────────────────────────── price plane ─────────────────────────────────

def price_of(operation: str) -> dict[str, Any]:
    """The single source of truth for what anything costs.

    Every metered path goes through here. A REST twin that computed its own
    price would be a way to buy the same call cheaper, so there is exactly one.
    """
    row = db.one("SELECT * FROM meter_prices WHERE operation=?", (operation,))
    if not row:
        raise HTTPException(404, f"operation '{operation}' is not on the price list")
    return row


def _publisher(publisher_id: str | None) -> dict[str, Any] | None:
    if not publisher_id:
        return None
    return db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,))


def _take_bps(publisher: dict[str, Any] | None) -> int:
    if not publisher:
        return 10000
    if publisher.get("pro_key_id"):
        key = db.one("SELECT * FROM billing_keys WHERE key_id=?", (publisher["pro_key_id"],))
        if key and not key["revoked_at"] and (not key["expires_at"] or str(key["expires_at"]) > now()):
            return PRO_TAKE_BPS
    return TAKE_BPS


# ────────────────────────────────  accounts  ─────────────────────────────────

class AccountRequest(BaseModel):
    label: str = Field(default="agent", min_length=1, max_length=80)


class TopupRequest(BaseModel):
    payer: str = Field(min_length=42, max_length=42)
    amount_usdc: str = Field(min_length=1, max_length=32)


class AuthorizeRequest(BaseModel):
    operation: str = Field(min_length=2, max_length=120)
    units: int = Field(default=1, ge=1, le=100000)
    reference: str | None = Field(default=None, max_length=200)


class CaptureRequest(BaseModel):
    authorization_id: str = Field(min_length=8, max_length=80)
    units: int | None = Field(default=None, ge=0, le=100000)


class ReleaseRequest(BaseModel):
    authorization_id: str = Field(min_length=8, max_length=80)
    reason: str = Field(default="upstream refused", max_length=200)


class PriceRequest(BaseModel):
    operation: str = Field(min_length=2, max_length=120)
    price_usdc: str = Field(min_length=1, max_length=32)
    unit: str = Field(default="call", max_length=24)
    publisher_id: str | None = Field(default=None, max_length=80)
    description: str = Field(default="", max_length=300)


class PublisherRequest(BaseModel):
    label: str = Field(min_length=2, max_length=80)
    payout_address: str = Field(min_length=42, max_length=42)
    share_bps: int = Field(default=7000, ge=0, le=10000)


class SelfPublisherRequest(BaseModel):
    label: str = Field(min_length=2, max_length=80)
    payout_address: str = Field(min_length=42, max_length=42)


class OwnPriceRequest(BaseModel):
    operation: str = Field(min_length=2, max_length=120)
    price_usdc: str = Field(min_length=1, max_length=32)
    unit: str = Field(default="call", max_length=24)
    description: str = Field(default="", max_length=300)


class MemoryRequest(BaseModel):
    memory_id: str | None = Field(default=None, max_length=200)
    query: str | None = Field(default=None, max_length=2000)
    body: dict[str, Any] | None = None


class ExecutionRequest(BaseModel):
    execution_tx: str = Field(min_length=66, max_length=66)


def _account_key(account_id: str) -> str:
    return billing.token("account-key", account_id, "amk_")


def _account(request: Request) -> dict[str, Any]:
    key = billing.active_key(request, scope="account")
    row = db.one("SELECT * FROM meter_accounts WHERE account_id=?", (str(key["subject"]),))
    if not row:
        raise HTTPException(401, "account key does not resolve to an account")
    return row


def _public_account(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": row["account_id"],
        "label": row["label"],
        "owner_actor": row["owner_actor"],
        "balance_usdc": usd_from_micro(int(row["balance_micro"])),
        "reserved_usdc": usd_from_micro(int(row["reserved_micro"])),
        "available_usdc": usd_from_micro(int(row["balance_micro"]) - int(row["reserved_micro"])),
        "lifetime_spent_usdc": usd_from_micro(int(row["lifetime_spent_micro"])),
        "created_at": row["created_at"],
    }


def _on_topup(order: dict[str, Any], tx_hash: str) -> None:
    account_id = str(order.get("ref") or "")
    db.execute(
        "UPDATE meter_accounts SET balance_micro=balance_micro+? WHERE account_id=?",
        (int(order["amount_micro"]), account_id))


billing.handlers["meter.topup"] = _on_topup


_sweeper_stop = threading.Event()


def _sweeper() -> None:
    """Reserves are an allowance held on the caller's behalf, not a penalty."""
    while not _sweeper_stop.wait(120):
        try:
            sweep_reserves()
        except Exception:
            continue


# ─────────────────── the ecosystem's view of this service ────────────────────

CAPABILITIES = (
    Capability("attested-meter", "meter.quote@v1", "Quote a metered call",
               "Price an operation in exact USDC before calling it, from the one price list "
               "every metered path resolves.", 0.0, "payments/metering",
               {"type": "object", "required": ["operation"],
                "properties": {"operation": {"type": "string"}, "units": {"type": "integer"}}},
               OBJECT_OUTPUT),
    Capability("attested-meter", "meter.prices@v1", "Price list",
               "The whole catalogue of metered operations with their exact per-unit price.",
               0.0, "payments/metering", {"type": "object", "properties": {}}, OBJECT_OUTPUT),
)

aimarket = AIMarket(
    cfg, signer, CAPABILITIES,
    name="Attested Meter",
    description="Pay-per-call metering for attested memory: prepaid USDC on Base, "
                "reserve-capture-release fairness and publisher splits.",
    invoke_base=cfg.extra.get("INVOKE_BASE") or cfg.public_origin,
    publisher_id="attested-meter",
)

def _dispatch(capability_id: str, payload: dict[str, Any], request: Request) -> Any:
    """Quotes only. Authorising and capturing a charge needs an account key, and
    an account key belongs to the caller, not to the hub relaying for them."""
    if capability_id == "meter.prices@v1":
        return prices()
    units = max(1, min(int(payload.get("units", 1) or 1), 100000))
    price = price_of(str(payload.get("operation") or ""))
    return {
        "operation": price["operation"],
        "units": units,
        "unit_price_usdc": usd_from_micro(int(price["unit_price_micro"])),
        "total_usdc": usd_from_micro(_op_amount(price, units)),
        "currency": "USDC", "chain_id": 8453,
        "authorize": f"{cfg.public_origin}/v1/meter/authorize",
    }

@asynccontextmanager
async def lifespan(_: FastAPI) -> Iterator[None]:
    billing.start()
    _sweeper_stop.clear()
    worker = threading.Thread(target=_sweeper, name="meter-reserve-sweeper", daemon=True)
    worker.start()
    # Publishing is best effort, as in Deal and Prove. Meter never started this
    # thread, so its listing on the hub froze at whatever a hand-run registration
    # left behind — and a service that never tries also never logs a refusal,
    # which read as "Meter registered fine" while the other two were being refused.
    publishing = aimarket.start_publishing()
    yield
    publishing.set()
    _sweeper_stop.set()
    worker.join(timeout=1)
    billing.stop()


app = FastAPI(title="Attested Meter", version=VERSION, lifespan=lifespan,
              description="Pay-per-call metering for attested memory, settled in USDC on Base.")
from .actor_auth import ActorProofBody
app.add_middleware(ActorProofBody)
app.state.actor_audience = os.getenv(f"{PREFIX}_ACTOR_AUDIENCE", SERVICE)
app.state.spend_actor_nonce = lambda *args: db.spend_actor_nonce(*args)
app.include_router(billing.router())
app.include_router(aimarket.router(_dispatch))
app.include_router(billing.admin_router())


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    try:
        db.ping()
    except Exception as error:
        raise HTTPException(503, "database unavailable") from error
    return {
        "status": "ok", "service": SERVICE, "version": VERSION,
        "database": "postgresql" if db.is_postgres else "sqlite",
        "billing": "kova", "take_bps": TAKE_BPS, "pro_take_bps": PRO_TAKE_BPS,
        "signing": "ed25519+ml-dsa-65" if cfg.pqc else "ed25519",
        "upstream_memory": bool(MEMORY_MARKET_URL),
    }


@app.get("/.well-known/attested-meter.json")
def well_known() -> dict[str, Any]:
    document = {
        "type": "attested.service/v1", "service": SERVICE, "version": VERSION,
        "origin": cfg.public_origin, "payment_scheme": "attested-exact",
        "asset": "USDC", "chain_id": 8453, "pay_to": cfg.payment_recipient,
        "take_bps": TAKE_BPS, "issued_at": now(),
    }
    return {**document, "signature": signer.sign(document)}


@app.get("/v1/prices")
def prices() -> dict[str, Any]:
    rows = db.all("SELECT * FROM meter_prices ORDER BY operation")
    return {"currency": "USDC", "chain_id": 8453, "operations": [{
        "operation": row["operation"],
        "unit": row["unit"],
        "price_usdc": usd_from_micro(int(row["unit_price_micro"])),
        "publisher_id": row["publisher_id"],
        "description": row["description"],
    } for row in rows]}


@app.post("/v1/accounts", status_code=201)
def create_account(body: AccountRequest, request: Request) -> dict[str, Any]:
    """One account per signed actor. The key is derived, so it is recoverable."""
    actor = verified_actor(request)
    account_id = billing.ident("account", actor, "acct_")
    raw_key = _account_key(account_id)
    existing = db.one("SELECT * FROM meter_accounts WHERE account_id=?", (account_id,))
    if existing is None:
        db.execute(
            "INSERT INTO meter_accounts (account_id, owner_actor, label, created_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (account_id) DO NOTHING",
            (account_id, actor, body.label, now()))
        db.execute(
            "INSERT INTO billing_keys (key_id, key_hash, key_prefix, subject, plan, scope, issued_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (key_id) DO NOTHING",
            (billing.ident("account-key-id", account_id, "key_"), sha256_hex(raw_key), raw_key[:12],
             account_id, "meter.account", "account", now()))
        existing = db.one("SELECT * FROM meter_accounts WHERE account_id=?", (account_id,))
    return {
        "account": _public_account(existing or {}),
        "api_key": raw_key,
        "recovered": bool(existing and existing["created_at"] != now()),
        "note": "the same signed actor always recovers the same account and key",
    }


@app.get("/v1/accounts/me")
def read_account(request: Request) -> dict[str, Any]:
    return _public_account(_account(request))


@app.post("/v1/accounts/topup")
def topup(body: TopupRequest, request: Request) -> dict[str, Any]:
    account = _account(request)
    amount_micro = micro_from_usd(body.amount_usdc)
    if amount_micro < MIN_TOPUP_MICRO:
        raise HTTPException(422, f"minimum top-up is {usd_from_micro(MIN_TOPUP_MICRO)} USDC")
    idempotency = request.headers.get("idempotency-key", "").strip()
    if len(idempotency) < 16:
        raise HTTPException(400, "Idempotency-Key header is required (16-200 characters)")
    return billing.open_order(
        purpose="meter.topup", plan="meter.credit", payer=body.payer,
        amount_micro=amount_micro, idempotency=f"topup:{idempotency}", ref=str(account["account_id"]),
    )


# ───────────────────── reserve → capture → release ───────────────────────────

def _reserve(account_id: str, amount_micro: int) -> None:
    """Take the allowance at entry. Anything else lets a caller spend twice."""
    changed = db.execute(
        "UPDATE meter_accounts SET reserved_micro=reserved_micro+? "
        "WHERE account_id=? AND balance_micro-reserved_micro>=?",
        (amount_micro, account_id, amount_micro))
    if changed != 1:
        raise HTTPException(402, "insufficient balance; top up at POST /v1/accounts/topup")


def _op_amount(price: dict[str, Any], units: int) -> int:
    return int(price["unit_price_micro"]) * int(units)


def authorize(account: dict[str, Any], operation: str, units: int, reference: str | None) -> dict[str, Any]:
    price = price_of(operation)
    amount = _op_amount(price, units)
    op_id = billing.ident("op", f"{account['account_id']}:{operation}:{time.time_ns()}", "op_")
    _reserve(str(account["account_id"]), amount)
    try:
        db.execute(
            "INSERT INTO meter_ops (op_id, account_id, operation, units, unit_price_micro, amount_micro, "
            "publisher_id, reference, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (op_id, account["account_id"], operation, units, int(price["unit_price_micro"]), amount,
             price["publisher_id"], reference, now()))
    except Exception:
        db.execute("UPDATE meter_accounts SET reserved_micro=reserved_micro-? WHERE account_id=?",
                   (amount, account["account_id"]))
        raise
    return {
        "authorization_id": op_id,
        "operation": operation,
        "units": units,
        "unit_price_usdc": usd_from_micro(int(price["unit_price_micro"])),
        "reserved_usdc": usd_from_micro(amount),
        "state": "reserved",
        "expires_note": "capture or release; an unreleased reserve is swept after "
                        f"{RESERVE_TTL_SECONDS // 60} minutes",
    }


def capture(op_id: str, units: int | None) -> dict[str, Any]:
    row = db.one("SELECT * FROM meter_ops WHERE op_id=?", (op_id,))
    if not row:
        raise HTTPException(404, "authorization not found")
    if row["state"] != "reserved":
        raise HTTPException(409, f"authorization is already '{row['state']}'")
    reserved = int(row["amount_micro"])
    used_units = int(row["units"]) if units is None else min(int(units), int(row["units"]))
    charged = int(row["unit_price_micro"]) * used_units
    publisher = _publisher(row["publisher_id"])
    take_bps = _take_bps(publisher)
    publisher_micro = charged * (10000 - take_bps) // 10000 if publisher else 0
    with db.transaction() as conn:
        changed = conn.execute(db.sql(
            "UPDATE meter_ops SET state='captured', units=?, amount_micro=?, publisher_micro=?, settled_at=? "
            "WHERE op_id=? AND state='reserved'"),
            (used_units, charged, publisher_micro, now(), op_id)).rowcount
        if changed != 1:
            raise HTTPException(409, "authorization changed state concurrently")
        conn.execute(db.sql(
            "UPDATE meter_accounts SET reserved_micro=reserved_micro-?, balance_micro=balance_micro-?, "
            "lifetime_spent_micro=lifetime_spent_micro+? WHERE account_id=?"),
            (reserved, charged, charged, row["account_id"]))
        if publisher and publisher_micro:
            conn.execute(db.sql(
                "UPDATE meter_publishers SET accrued_micro=accrued_micro+? WHERE publisher_id=?"),
                (publisher_micro, publisher["publisher_id"]))
    return {
        "authorization_id": op_id, "state": "captured", "units": used_units,
        "charged_usdc": usd_from_micro(charged),
        "refunded_usdc": usd_from_micro(reserved - charged),
        "publisher_usdc": usd_from_micro(publisher_micro),
        "platform_bps": take_bps,
    }


def release(op_id: str, reason: str) -> dict[str, Any]:
    """The refusal path. A call the upstream did not serve costs nothing."""
    row = db.one("SELECT * FROM meter_ops WHERE op_id=?", (op_id,))
    if not row:
        raise HTTPException(404, "authorization not found")
    if row["state"] != "reserved":
        raise HTTPException(409, f"authorization is already '{row['state']}'")
    with db.transaction() as conn:
        changed = conn.execute(db.sql(
            "UPDATE meter_ops SET state='released', settled_at=?, reference=? WHERE op_id=? AND state='reserved'"),
            (now(), reason[:200], op_id)).rowcount
        if changed != 1:
            raise HTTPException(409, "authorization changed state concurrently")
        conn.execute(db.sql(
            "UPDATE meter_accounts SET reserved_micro=reserved_micro-? WHERE account_id=?"),
            (int(row["amount_micro"]), row["account_id"]))
    return {"authorization_id": op_id, "state": "released",
            "returned_usdc": usd_from_micro(int(row["amount_micro"])), "reason": reason[:200]}


RESERVE_TTL_SECONDS = 900


def sweep_reserves() -> int:
    """A caller that vanishes mid-call must not freeze its own balance forever."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - RESERVE_TTL_SECONDS))
    stale = db.all("SELECT op_id FROM meter_ops WHERE state='reserved' AND created_at < ? LIMIT 200", (cutoff,))
    swept = 0
    for row in stale:
        try:
            release(str(row["op_id"]), "reserve expired")
            swept += 1
        except HTTPException:
            continue
    return swept


@app.post("/v1/meter/authorize")
def authorize_route(body: AuthorizeRequest, request: Request) -> dict[str, Any]:
    account = _account(request)
    return authorize(account, body.operation, body.units, body.reference)


@app.post("/v1/meter/capture")
def capture_route(body: CaptureRequest, request: Request) -> dict[str, Any]:
    account = _account(request)
    row = db.one("SELECT account_id FROM meter_ops WHERE op_id=?", (body.authorization_id,))
    if not row or str(row["account_id"]) != str(account["account_id"]):
        raise HTTPException(404, "authorization not found")
    return capture(body.authorization_id, body.units)


@app.post("/v1/meter/release")
def release_route(body: ReleaseRequest, request: Request) -> dict[str, Any]:
    account = _account(request)
    row = db.one("SELECT account_id FROM meter_ops WHERE op_id=?", (body.authorization_id,))
    if not row or str(row["account_id"]) != str(account["account_id"]):
        raise HTTPException(404, "authorization not found")
    return release(body.authorization_id, body.reason)


@app.get("/v1/meter/usage")
def usage(request: Request, limit: int = 100) -> dict[str, Any]:
    account = _account(request)
    rows = db.all(
        "SELECT op_id, operation, units, amount_micro, state, created_at, settled_at FROM meter_ops "
        "WHERE account_id=? ORDER BY created_at DESC LIMIT ?",
        (account["account_id"], max(1, min(limit, 500))))
    for row in rows:
        row["amount_usdc"] = usd_from_micro(int(row.pop("amount_micro")))
    return {"account": _public_account(account), "count": len(rows), "operations": rows}


# ─────────────────────────────── x402 surface ────────────────────────────────

def x402_challenge(operation: str, units: int, detail: str) -> JSONResponse:
    price = price_of(operation)
    amount = _op_amount(price, units)
    return JSONResponse(status_code=402, content={
        "x402Version": 1,
        "error": detail,
        "accepts": [{
            "scheme": "attested-exact",
            "network": "base",
            "chainId": 8453,
            "asset": "USDC",
            "payTo": cfg.payment_recipient,
            "maxAmountRequired": usd_from_micro(amount),
            "resource": f"{cfg.public_origin}/v1/x402/{operation}",
            "description": str(price["description"] or operation),
            "mimeType": "application/json",
            "maxTimeoutSeconds": 3600,
            "extra": {
                "note": "not the canonical x402 'exact' scheme: this rail verifies a finalized "
                        "transfer of an exact amount from a declared payer address, it does "
                        "not settle an EIP-3009 authorization through a facilitator",
                "topup": f"{cfg.public_origin}/v1/accounts/topup",
                "account": f"{cfg.public_origin}/v1/accounts",
                "prices": f"{cfg.public_origin}/v1/prices",
            },
        }],
    }, headers={"WWW-Authenticate": 'attested-exact realm="attested-meter"'})


@app.get("/v1/x402/{operation}")
def x402_quote(operation: str, request: Request, units: int = 1) -> Any:
    """Answers 402 with a machine-readable challenge until the account can pay."""
    price = price_of(operation)
    try:
        account = _account(request)
    except HTTPException:
        return x402_challenge(operation, units, "no meter account key presented")
    amount = _op_amount(price, units)
    available = int(account["balance_micro"]) - int(account["reserved_micro"])
    if available < amount:
        return x402_challenge(operation, units, "insufficient balance")
    return {
        "operation": operation, "units": units,
        "price_usdc": usd_from_micro(amount),
        "available_usdc": usd_from_micro(available),
        "authorize": f"{cfg.public_origin}/v1/meter/authorize",
    }


# ─────────────────────── metered memory (the wedge) ──────────────────────────

ACTOR_HEADERS = ("x-actor-id", "x-actor-public-key", "x-actor-signature",
                 "x-actor-timestamp", "x-actor-nonce", "x-actor-version", "x-actor-intent")


def _memory_call(method: str, path: str, payload: dict[str, Any] | None = None,
                 params: dict[str, Any] | None = None,
                 actor: dict[str, str] | None = None) -> dict[str, Any]:
    """Call Memory Market with ITS contract, not one invented here.

    The market authenticates with `Authorization: Bearer <api key>` **plus** the
    caller's own destination-bound actor intent. The Memory target signs the
    final method/path/query/body; this service cannot expand it or re-sign. So the caller's
    identity is forwarded verbatim and the meter only pays for the call.
    """
    if not MEMORY_MARKET_URL:
        raise HTTPException(503, "METER_MEMORY_MARKET_URL is not configured")
    headers = {"content-type": "application/json"}
    if MEMORY_MARKET_KEY:
        headers["Authorization"] = f"Bearer {MEMORY_MARKET_KEY}"
    headers.update(actor or {})
    try:
        response = httpx.request(method, f"{MEMORY_MARKET_URL}{path}",
                                 content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() if payload is not None else None,
                                 params=params, headers=headers, timeout=20)
    except httpx.HTTPError as error:
        raise HTTPException(502, "memory market unreachable") from error
    if response.status_code >= 400:
        raise HTTPException(502, f"memory market refused with {response.status_code}")
    return dict(response.json())


def _forwarded_actor(request: Request, account: dict[str, Any], required: bool) -> dict[str, str]:
    """Forward the caller's identity — and only the caller's own.

    An account key is derived from a signed actor, so a request that presents a
    *different* actor is either a mistake or an attempt to have one account pay
    for another identity's writes. Both are refused rather than billed.
    """
    supplied = {name: request.headers[name] for name in ACTOR_HEADERS if name in request.headers}
    if not supplied:
        if required:
            raise HTTPException(401, "this operation needs your signed actor headers to forward upstream")
        return {}
    if supplied.get("x-actor-id") != str(account["owner_actor"]):
        raise HTTPException(403, "the forwarded actor is not the one this account belongs to")
    return supplied


def _metered(request: Request, operation: str, method: str, path: str,
             payload: dict[str, Any] | None = None, params: dict[str, Any] | None = None,
             actor_required: bool = False) -> dict[str, Any]:
    account = _account(request)
    actor = _forwarded_actor(request, account, actor_required)
    reservation = authorize(account, operation, 1, path)
    try:
        result = _memory_call(method, path, payload, params, actor)
    except HTTPException:
        release(reservation["authorization_id"], "upstream refused")
        raise
    settlement = capture(reservation["authorization_id"], 1)
    return {"result": result, "charge": settlement}


@app.post("/v1/memory/read")
def memory_read(body: MemoryRequest, request: Request) -> dict[str, Any]:
    if not body.memory_id:
        raise HTTPException(422, "memory_id is required")
    return _metered(request, "memory.read", "GET", f"/v1/memories/{body.memory_id}")


@app.post("/v1/memory/write")
def memory_write(body: MemoryRequest, request: Request) -> dict[str, Any]:
    if not body.body:
        raise HTTPException(422, "body is required")
    return _metered(request, "memory.write", "POST", "/v1/memories", payload=body.body,
                    actor_required=True)


@app.post("/v1/memory/search")
def memory_search(body: MemoryRequest, request: Request) -> dict[str, Any]:
    if not body.query:
        raise HTTPException(422, "query is required")
    return _metered(request, "memory.search", "GET", "/v1/catalog",
                    params={"q": body.query, "limit": 30})


# ───────────────────────── publishers and payouts ────────────────────────────

def _publisher_key(publisher_id: str) -> str:
    return billing.token("publisher-key", publisher_id, "pbk_")


def _owner(request: Request) -> dict[str, Any]:
    key = billing.active_key(request, scope="publisher-owner")
    row = db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (str(key["subject"]),))
    if not row:
        raise HTTPException(401, "publisher key does not resolve to a publisher")
    return row


@app.post("/v1/publishers", status_code=201)
def self_register_publisher(body: SelfPublisherRequest, request: Request) -> dict[str, Any]:
    """Register as a publisher without the operator.

    Self-serve on purpose: the alternative is a storefront holding this service's
    ADMIN token so it can create publishers on someone's behalf — and that token
    can also mint payouts. One publisher key that can only price its own
    operations is a far smaller thing to hand out.
    """
    rate_limit(billing, request, "self-publisher", 10)
    actor = verified_actor(request)
    if not EVM_ADDRESS.fullmatch(body.payout_address):
        raise HTTPException(422, "payout_address must be a valid EVM address")
    publisher_id = billing.ident("self-publisher", actor, "pub_")
    raw_key = _publisher_key(publisher_id)
    existing = db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,))
    if existing is None:
        db.execute(
            "INSERT INTO meter_publishers (publisher_id, payout_address, label, share_bps, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (publisher_id) DO NOTHING",
            (publisher_id, body.payout_address.lower(), body.label, 10000 - TAKE_BPS, now()))
        db.execute(
            "INSERT INTO billing_keys (key_id, key_hash, key_prefix, subject, plan, scope, issued_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (key_id) DO NOTHING",
            (billing.ident("publisher-key-id", publisher_id, "key_"), sha256_hex(raw_key),
             raw_key[:12], publisher_id, "meter.publisher", "publisher-owner", now()))
        existing = db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,))
    return {
        "publisher": _public_publisher(existing or {}),
        "api_key": raw_key,
        "note": "the same signed actor always recovers the same publisher and key",
    }


@app.get("/v1/publishers/me")
def read_own_publisher(request: Request) -> dict[str, Any]:
    return _public_publisher(_owner(request))


@app.post("/v1/publishers/me/prices")
def set_own_price(body: OwnPriceRequest, request: Request) -> dict[str, Any]:
    """Price your own operation — and only your own.

    An operation already owned by someone else, or by the platform (no publisher
    at all, like `memory.read`), is refused. Without that check a publisher could
    reprice a competitor's capability, or take over a platform one, from a key
    that is meant to control nothing but its own listings.
    """
    rate_limit(billing, request, "own-price", 60)
    publisher = _owner(request)
    price_micro = micro_from_usd(body.price_usdc)
    current = db.one("SELECT * FROM meter_prices WHERE operation=?", (body.operation,))
    if current is not None and str(current["publisher_id"] or "") != str(publisher["publisher_id"]):
        raise HTTPException(403, "this operation belongs to another publisher")
    if body.operation.startswith("expert.read:"):
        memory_id = body.operation.removeprefix("expert.read:")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", memory_id):
            raise HTTPException(422, "invalid expert memory id")
        summary = _memory_call("GET", f"/v1/catalog/{memory_id}")
        owner = str(summary.get("owner_id") or "")
        if not owner or billing.ident("self-publisher", owner, "pub_") != publisher["publisher_id"]:
            raise HTTPException(403, "only the memory author can price this expert read")
    changed = db.execute(
        "INSERT INTO meter_prices (operation, unit_price_micro, unit, publisher_id, description, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (operation) DO UPDATE SET "
        "unit_price_micro=EXCLUDED.unit_price_micro, unit=EXCLUDED.unit, "
        "description=EXCLUDED.description, updated_at=EXCLUDED.updated_at "
        "WHERE meter_prices.publisher_id=EXCLUDED.publisher_id",
        (body.operation, price_micro, body.unit, publisher["publisher_id"], body.description, now()))
    if changed != 1:
        raise HTTPException(403, "this operation belongs to another publisher")
    return {"operation": body.operation, "price_usdc": usd_from_micro(price_micro),
            "publisher_id": publisher["publisher_id"], "updated_at": now()}


@app.post("/v1/admin/publishers", status_code=201)
def create_publisher(body: PublisherRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    if not EVM_ADDRESS.fullmatch(body.payout_address):
        raise HTTPException(422, "payout_address must be a valid EVM address")
    publisher_id = billing.ident("publisher", body.payout_address.lower(), "pub_")
    db.execute(
        "INSERT INTO meter_publishers (publisher_id, payout_address, label, share_bps, created_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (publisher_id) DO NOTHING",
        (publisher_id, body.payout_address.lower(), body.label, body.share_bps, now()))
    return _public_publisher(db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,)) or {})


def _public_publisher(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        raise HTTPException(404, "publisher not found")
    accrued = int(row["accrued_micro"])
    paid = int(row["paid_micro"])
    return {
        "publisher_id": row["publisher_id"], "label": row["label"],
        "payout_address": row["payout_address"],
        "accrued_usdc": usd_from_micro(accrued), "paid_usdc": usd_from_micro(paid),
        "payable_usdc": usd_from_micro(max(0, accrued - paid)),
        "platform_bps": _take_bps(row), "pro": bool(row.get("pro_key_id")),
        "created_at": row["created_at"],
    }


@app.get("/v1/publishers/{publisher_id}")
def read_publisher(publisher_id: str) -> dict[str, Any]:
    return _public_publisher(db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,)) or {})


@app.post("/v1/publishers/{publisher_id}/pro")
def bind_pro_key(publisher_id: str, request: Request) -> dict[str, Any]:
    """A Publisher Pro key halves the platform take on everything you publish."""
    key = billing.active_key(request, scope="publisher")
    row = db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,))
    if not row:
        raise HTTPException(404, "publisher not found")
    other = db.one("SELECT publisher_id FROM meter_publishers WHERE pro_key_id=? AND publisher_id<>?",
                   (key["key_id"], publisher_id))
    if other:
        raise HTTPException(409, "this Pro key is already bound to another publisher")
    db.execute("UPDATE meter_publishers SET pro_key_id=? WHERE publisher_id=?", (key["key_id"], publisher_id))
    return _public_publisher(db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,)) or {})


@app.post("/v1/admin/prices")
def set_price(body: PriceRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    price_micro = micro_from_usd(body.price_usdc)
    if body.publisher_id and not db.one("SELECT publisher_id FROM meter_publishers WHERE publisher_id=?",
                                        (body.publisher_id,)):
        raise HTTPException(404, "publisher not found")
    db.execute(
        "INSERT INTO meter_prices (operation, unit_price_micro, unit, publisher_id, description, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (operation) DO UPDATE SET "
        "unit_price_micro=EXCLUDED.unit_price_micro, unit=EXCLUDED.unit, "
        "publisher_id=EXCLUDED.publisher_id, description=EXCLUDED.description, updated_at=EXCLUDED.updated_at",
        (body.operation, price_micro, body.unit, body.publisher_id, body.description, now()))
    return {"operation": body.operation, "price_usdc": usd_from_micro(price_micro),
            "publisher_id": body.publisher_id, "updated_at": now()}


@app.post("/v1/admin/payouts", status_code=201)
def create_payout(publisher_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    row = db.one("SELECT * FROM meter_publishers WHERE publisher_id=?", (publisher_id,))
    if not row:
        raise HTTPException(404, "publisher not found")
    payable = int(row["accrued_micro"]) - int(row["paid_micro"])
    if payable < MIN_PAYOUT_MICRO:
        raise HTTPException(409, f"payable balance is below the {usd_from_micro(MIN_PAYOUT_MICRO)} USDC minimum")
    payout_id = billing.ident("payout", f"{publisher_id}:{row['paid_micro']}", "pay_")
    document = {
        "type": "attested.payout/v1", "payout_id": payout_id, "service": SERVICE,
        "issuer": cfg.public_origin, "publisher_id": publisher_id,
        "payee": row["payout_address"], "asset": "USDC", "chain_id": 8453,
        "amount_micro": payable, "accrued_micro": int(row["accrued_micro"]),
        "previously_paid_micro": int(row["paid_micro"]), "issued_at": now(),
    }
    signature = signer.sign(document)
    with db.transaction() as conn:
        inserted = conn.execute(db.sql(
            "INSERT INTO meter_payouts (payout_id, publisher_id, amount_micro, document, signature, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (payout_id) DO NOTHING"),
            (payout_id, publisher_id, payable, canonical(document), canonical(signature), now())).rowcount
        if inserted != 1:
            raise HTTPException(409, "a payout for this balance already exists")
        conn.execute(db.sql("UPDATE meter_publishers SET paid_micro=paid_micro+? WHERE publisher_id=?"),
                     (payable, publisher_id))
    return {"payout_id": payout_id, "amount_usdc": usd_from_micro(payable),
            "document": document, "signature": signature,
            "note": "signed instruction; the operator executes and records the transaction hash"}


@app.get("/v1/payouts/{payout_id}")
def read_payout(payout_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM meter_payouts WHERE payout_id=?", (payout_id,))
    if not row:
        raise HTTPException(404, "payout not found")
    document = json.loads(str(row["document"]))
    signature = json.loads(str(row["signature"]))
    return {
        "payout_id": payout_id, "publisher_id": row["publisher_id"],
        "amount_usdc": usd_from_micro(int(row["amount_micro"])),
        "document": document, "signature": signature,
        "verified": verify_signature(document, signature, signer.public_key),
        "executed_at": row["executed_at"], "execution_tx": row["execution_tx"],
    }


@app.post("/v1/admin/payouts/{payout_id}/execute")
def execute_payout(payout_id: str, body: ExecutionRequest,
                   authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    changed = db.execute(
        "UPDATE meter_payouts SET executed_at=?, execution_tx=? WHERE payout_id=? AND executed_at IS NULL",
        (now(), body.execution_tx.lower(), payout_id))
    if changed != 1:
        raise HTTPException(409, "payout not found or already executed")
    return read_payout(payout_id)


@app.get("/v1/admin/payouts")
def list_payouts(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    _admin(authorization)
    rows = db.all(
        "SELECT p.payout_id, p.publisher_id, p.amount_micro, p.created_at, p.executed_at, p.execution_tx, "
        "b.label, b.payout_address FROM meter_payouts p LEFT JOIN meter_publishers b "
        "ON b.publisher_id=p.publisher_id ORDER BY p.created_at DESC LIMIT ?", (max(1, min(limit, 1000)),))
    for row in rows:
        row["amount_usdc"] = usd_from_micro(int(row.pop("amount_micro")))
    return {"count": len(rows), "payouts": rows,
            "unexecuted": sum(1 for row in rows if not row["executed_at"])}


@app.get("/v1/admin/publishers")
def list_publishers(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    rows = db.all("SELECT * FROM meter_publishers ORDER BY accrued_micro DESC")
    return {"count": len(rows), "publishers": [_public_publisher(row) for row in rows]}


@app.get("/v1/admin/accounts")
def list_accounts(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    _admin(authorization)
    rows = db.all("SELECT * FROM meter_accounts ORDER BY lifetime_spent_micro DESC LIMIT ?",
                  (max(1, min(limit, 1000)),))
    return {"count": len(rows), "accounts": [_public_account(row) for row in rows]}


@app.post("/v1/admin/sweep")
def sweep(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    return {"released": sweep_reserves()}


def _admin(authorization: str | None) -> None:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, cfg.admin_token):
        raise HTTPException(401, "operator authentication required")


# ──────────────────────────────── public stats ───────────────────────────────

@app.get("/v1/stats")
def stats() -> dict[str, Any]:
    ops = db.one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN state='captured' THEN amount_micro ELSE 0 END),0) AS charged, "
        "COALESCE(SUM(CASE WHEN state='released' THEN 1 ELSE 0 END),0) AS released, "
        "COALESCE(SUM(publisher_micro),0) AS publisher FROM meter_ops") or {}
    balance = db.one("SELECT COALESCE(SUM(balance_micro),0) AS micro, COUNT(*) AS n FROM meter_accounts") or {}
    return {
        "service": SERVICE, "generated_at": now(),
        "metered_calls": int(ops.get("n") or 0),
        "released_calls": int(ops.get("released") or 0),
        "charged_usdc": usd_from_micro(int(ops.get("charged") or 0)),
        "publisher_share_usdc": usd_from_micro(int(ops.get("publisher") or 0)),
        "accounts": int(balance.get("n") or 0),
        "prepaid_balance_usdc": usd_from_micro(int(balance.get("micro") or 0)),
        "take_bps": TAKE_BPS,
        "operations_priced": len(db.all("SELECT operation FROM meter_prices")),
    }


# ─────────────────────────────────── web ─────────────────────────────────────

if WEB_ROOT:
    app.mount("/assets", StaticFiles(directory=WEB_ROOT), name="assets")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(os.path.join(WEB_ROOT, "index.html"))

    # The landing links its policy notes as /docs/<name>.md. They ship beside web/ (the
    # Dockerfile copies docs/), and only the files found there are served.
    _NOTES_DIR = os.path.join(os.path.dirname(WEB_ROOT), "docs")
    _NOTES = ({f[:-3]: os.path.join(_NOTES_DIR, f) for f in os.listdir(_NOTES_DIR)
               if f.endswith(".md")} if os.path.isdir(_NOTES_DIR) else {})

    @app.get("/docs/{name}.md", include_in_schema=False)
    def policy_note(name: str) -> FileResponse:
        if name not in _NOTES:
            raise HTTPException(404, "no such note")
        return FileResponse(_NOTES[name], media_type="text/markdown; charset=utf-8")

    @app.get("/admin", include_in_schema=False)
    def admin_page() -> FileResponse:
        return FileResponse(os.path.join(WEB_ROOT, "admin.html"))
