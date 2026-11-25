"""Attested Deal — escrow that releases on proof, not on trust.

Four surfaces, one ledger:

* **Escrow (pay-on-proof).** A buyer funds a deal with exact USDC on Base. The
  money is released only when a *machine-checkable* proof of the agreed outcome
  exists: a Provenance receipt, a verified Truth claim, or an attestation signed
  by a key the deal named up front.
* **Truth Desk.** Either party can contest. A dispute freezes settlement and is
  closed by a signed arbiter outcome — release, refund or split.
* **Memory Bond / Slash.** A publisher stakes USDC behind a memory. A challenger
  who gets the claim refuted takes the slashed share.
* **Sandbox Trials → Trusted Slot.** A bounded, paid trial an agent must pass
  before a deal that requires a trusted counterparty will accept it.

**What this service does and does not do with money.** It never holds a private
key and never moves funds. Buyers pay the operator's recipient address through
the KOVA rail; a release produces a *signed settlement instruction* naming payee,
amount and the proof that unlocked it. Executing that instruction is a separate,
deliberate step by the operator, recorded back against the settlement. The
product being sold is the condition engine and its audit trail — see
`docs/settlement.md`, which says the same thing to buyers.
"""
from __future__ import annotations

import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Iterator

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .core import (
    ACTOR_ID,
    EVM_ADDRESS,
    OBJECT_OUTPUT,
    AIMarket,
    Billing,
    Capability,
    Database,
    Kova,
    Plan,
    Signer,
    b64url,
    b64url_encode,
    canonical,
    client_ip,
    load_settings,
    micro_from_usd,
    normalize_key,
    now,
    rate_limit,
    sha256_hex,
    usd_from_micro,
    verified_actor,
    verify_signature,
)

SERVICE = "attested-deal"
VERSION = "1.0.0"
PREFIX = "DEAL"

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS deals (
        deal_id TEXT PRIMARY KEY,
        buyer TEXT NOT NULL,
        seller TEXT NOT NULL,
        seller_actor TEXT,
        title TEXT NOT NULL,
        amount_micro BIGINT NOT NULL,
        fee_bps INTEGER NOT NULL,
        condition_kind TEXT NOT NULL,
        condition_ref TEXT NOT NULL,
        condition_issuer TEXT,
        hold_seconds BIGINT NOT NULL DEFAULT 0,
        deadline TEXT NOT NULL,
        require_trusted_slot INTEGER NOT NULL DEFAULT 0,
        state TEXT NOT NULL DEFAULT 'draft',
        order_id TEXT,
        funded_tx TEXT,
        proof_document TEXT,
        release_after TEXT,
        settlement_id TEXT,
        created_at TEXT NOT NULL,
        funded_at TEXT,
        settled_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS deal_events (
        event_id TEXT PRIMARY KEY,
        deal_id TEXT NOT NULL,
        seq BIGINT NOT NULL,
        kind TEXT NOT NULL,
        actor TEXT,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS settlements (
        settlement_id TEXT PRIMARY KEY,
        deal_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        payee TEXT NOT NULL,
        amount_micro BIGINT NOT NULL,
        fee_micro BIGINT NOT NULL,
        document TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at TEXT NOT NULL,
        executed_at TEXT,
        execution_tx TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS disputes (
        dispute_id TEXT PRIMARY KEY,
        deal_id TEXT NOT NULL,
        opened_by TEXT NOT NULL,
        reason TEXT NOT NULL,
        evidence TEXT,
        state TEXT NOT NULL DEFAULT 'open',
        outcome TEXT,
        arbiter TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bonds (
        bond_id TEXT PRIMARY KEY,
        publisher TEXT NOT NULL,
        publisher_actor TEXT,
        memory_id TEXT NOT NULL,
        claim_id TEXT,
        amount_micro BIGINT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        order_id TEXT,
        created_at TEXT NOT NULL,
        bonded_at TEXT,
        closed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bond_challenges (
        challenge_id TEXT PRIMARY KEY,
        bond_id TEXT NOT NULL,
        challenger TEXT NOT NULL,
        challenger_actor TEXT NOT NULL,
        claim_id TEXT NOT NULL,
        evidence TEXT,
        state TEXT NOT NULL DEFAULT 'open',
        settlement_id TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sandbox_trials (
        trial_id TEXT PRIMARY KEY,
        agent_actor TEXT NOT NULL,
        scope TEXT NOT NULL,
        budget_micro BIGINT NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        order_id TEXT,
        verdict TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        expires_at TEXT,
        decided_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trusted_slots (
        actor_id TEXT NOT NULL,
        scope TEXT NOT NULL,
        trial_id TEXT NOT NULL,
        granted_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        PRIMARY KEY (actor_id, scope)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_deals_state ON deals(state)",
    "CREATE INDEX IF NOT EXISTS idx_deal_events_deal ON deal_events(deal_id, seq)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_deal_events_seq ON deal_events(deal_id, seq)",
    "CREATE INDEX IF NOT EXISTS idx_settlements_deal ON settlements(deal_id)",
)

PLANS = (
    Plan("deal.desk.monthly", "Deal Desk", "79.00", 30,
         "Unlimited proof-gated escrow deals, Truth Desk disputes and signed settlements.", scope="desk"),
    Plan("deal.sandbox.trial", "Sandbox trial slot", "9.00", 14,
         "One bounded sandbox trial; a pass grants a trusted slot for 90 days.", scope="sandbox"),
)

CONDITION_KINDS = {"provenance_receipt", "truth_claim", "attestation", "buyer_accept"}


# ─────────────────────────────── configuration ───────────────────────────────

cfg = load_settings(SERVICE, PREFIX, extra_keys=("PROVE_URL", "TRUTH_URL", "TRUTH_TOKEN", "FEE_BPS",
                                                 "SLASH_BPS", "ARBITER_KEYS", "VERIFIER_KEYS",
                                                 "TRUSTED_SLOT_DAYS", "CAPABILITY_TOKEN",
                                                 "AIMARKET_HUB_URL", "PUBLISHER_TOKEN",
                                                 "INVOKE_BASE"))
db = Database(cfg.database_url or "sqlite:///./data/attested-deal.sqlite3", SCHEMA)
kova = Kova(cfg)
billing = Billing(cfg, db, kova, PLANS)
signer = Signer(cfg.signing_key_path, pqc=cfg.pqc)

FEE_BPS = max(0, min(int(cfg.extra.get("FEE_BPS") or 250), 500))
SLASH_BPS = max(0, min(int(cfg.extra.get("SLASH_BPS") or 5000), 10000))
TRUSTED_SLOT_DAYS = max(1, min(int(cfg.extra.get("TRUSTED_SLOT_DAYS") or 90), 365))
PROVE_URL = (cfg.extra.get("PROVE_URL") or "").rstrip("/")
TRUTH_URL = (cfg.extra.get("TRUTH_URL") or cfg.hub_url).rstrip("/")
TRUTH_TOKEN = cfg.extra.get("TRUTH_TOKEN") or ""


def _key_set(raw: str) -> set[str]:
    """Pinned keys, canonicalised — a set of raw strings would never match a key
    published in the other base64 alphabet."""
    return {normalize_key(item) for item in (raw or "").replace(",", " ").split() if item.strip()}


ARBITER_KEYS = _key_set(cfg.extra.get("ARBITER_KEYS", ""))
VERIFIER_KEYS = _key_set(cfg.extra.get("VERIFIER_KEYS", ""))
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


# ──────────────────────────────── proof plane ────────────────────────────────

class ProofChecker:
    """Resolves a deal's release condition against the service that owns it.

    Injected so tests do not need a live Prove or Truth deployment; production
    talks HTTP. A condition the checker cannot *positively* verify is never a
    release — an unreachable verifier fails closed, because the alternative is
    paying out on a network error.
    """

    #: The Truth Layer answers `unverified | supported | contested | rejected`.
    #: This service speaks `verified | refuted`, so the mapping lives here — in one
    #: place — rather than being re-guessed at every call site.
    TRUTH_STATES = {
        "supported": "verified",
        "rejected": "refuted",
        "contested": "contested",
        "unverified": "unverified",
    }

    def __init__(self, prove_url: str, truth_url: str, truth_token: str = "",
                 client: httpx.Client | None = None):
        self.prove_url = prove_url
        self.truth_url = truth_url
        self.truth_token = truth_token
        self._client = client

    def _get(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, timeout=10)
            else:
                response = httpx.get(url, headers=headers, timeout=10)
        except httpx.HTTPError as error:
            raise HTTPException(503, "proof service unavailable") from error
        if response.status_code == 404:
            raise HTTPException(404, "proof not found")
        if response.status_code in {401, 403}:
            raise HTTPException(503, "this desk is not authorised to read the proof service")
        if response.status_code >= 400:
            raise HTTPException(503, "proof service could not answer")
        return dict(response.json())

    def receipt(self, receipt_id: str) -> dict[str, Any]:
        if not self.prove_url:
            raise HTTPException(503, "DEAL_PROVE_URL is not configured")
        return self._get(f"{self.prove_url}/v1/receipts/{receipt_id}")

    def claim(self, pack_id: str) -> dict[str, Any]:
        """Resolve a Truth Layer **evidence pack** and normalise its verdict.

        The Truth Layer has no `GET /v1/claims/{id}` — verification is a POST that
        *creates* a pack, and the durable, re-readable artefact is
        `GET /v1/evidence-packs/{id}`, behind the hub's internal service token. A
        deal must reference a pack that already exists: letting the desk submit
        the claim itself would let one party choose both the question and the
        evidence.
        """
        if not self.truth_url:
            raise HTTPException(503, "DEAL_TRUTH_URL is not configured")
        headers = {"x-aimarket-internal-token": self.truth_token} if self.truth_token else None
        pack = self._get(f"{self.truth_url}/v1/evidence-packs/{pack_id}", headers)
        result = pack.get("result") or {}
        raw = str(result.get("status", ""))
        return {
            "state": self.TRUTH_STATES.get(raw, "unknown"),
            "truth_status": raw,
            "pack_id": pack.get("id", pack_id),
            "claim_hash": pack.get("claim_hash"),
            "confidence": result.get("confidence"),
            "evidence_count": result.get("evidence_count"),
        }


proofs = ProofChecker(PROVE_URL, TRUTH_URL, TRUTH_TOKEN)


def _check_condition(deal: dict[str, Any], body: "EvidenceRequest", actor: str) -> dict[str, Any]:
    """Return the proof document that unlocks this deal, or raise."""
    kind = str(deal["condition_kind"])
    reference = str(deal["condition_ref"])
    if kind == "provenance_receipt":
        if body.reference != reference:
            raise HTTPException(409, "evidence does not reference the receipt this deal names")
        receipt = proofs.receipt(reference)
        if not receipt.get("verified"):
            raise HTTPException(409, "the referenced receipt does not verify")
        issuer = str(receipt.get("issuer_public_key", ""))
        expected = str(deal.get("condition_issuer") or "")
        if expected and not hmac.compare_digest(issuer, expected):
            raise HTTPException(409, "the receipt was issued by a different key than the deal names")
        return {"kind": kind, "receipt_id": reference, "issuer_public_key": issuer,
                "digest": receipt.get("digest"), "checked_at": now()}
    if kind == "truth_claim":
        if body.reference != reference:
            raise HTTPException(409, "evidence does not reference the evidence pack this deal names")
        claim = proofs.claim(reference)
        state = str(claim.get("state", ""))
        if state != "verified":
            raise HTTPException(409, f"claim state is '{state or 'unknown'}', not 'verified'")
        return {"kind": kind, "evidence_pack_id": reference, "claim_state": state,
                "truth_status": claim.get("truth_status"), "claim_hash": claim.get("claim_hash"),
                "confidence": claim.get("confidence"), "checked_at": now()}
    if kind == "attestation":
        if not body.document or not body.signature:
            raise HTTPException(422, "an attestation condition requires document and signature")
        expected = str(deal.get("condition_issuer") or "")
        allowed = {normalize_key(expected)} if expected else VERIFIER_KEYS
        if not allowed:
            raise HTTPException(503, "no attestation verifier key is configured")
        public_key = normalize_key(str(body.signature.get("public_key", "")))
        if public_key not in allowed:
            raise HTTPException(403, "attestation is not signed by an accepted verifier key")
        if str(body.document.get("deal_id", "")) != str(deal["deal_id"]):
            raise HTTPException(409, "attestation is bound to a different deal")
        if str(body.document.get("outcome", "")) != "fulfilled":
            raise HTTPException(409, "attestation does not state the deal was fulfilled")
        if not verify_signature(body.document, body.signature, public_key):
            raise HTTPException(403, "attestation signature does not verify")
        return {"kind": kind, "verifier_public_key": public_key,
                "document_digest": sha256_hex(canonical(body.document)), "checked_at": now()}
    if kind == "buyer_accept":
        if actor != str(deal["buyer"]).lower() and actor != str(deal.get("seller_actor") or ""):
            raise HTTPException(403, "only the buyer can accept a buyer_accept deal")
        if actor != str(deal["buyer"]).lower():
            raise HTTPException(403, "only the buyer can accept a buyer_accept deal")
        return {"kind": kind, "accepted_by": actor, "checked_at": now()}
    raise HTTPException(500, "unknown condition kind")


# ───────────────────────────────── requests ──────────────────────────────────

class DealRequest(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    seller: str = Field(min_length=42, max_length=42)
    seller_actor: str | None = Field(default=None, pattern=r"^did:actor:[0-9a-f]{64}$")
    buyer: str = Field(min_length=42, max_length=42)
    amount_usdc: str = Field(min_length=1, max_length=32)
    condition_kind: str = Field(pattern=r"^(provenance_receipt|truth_claim|attestation|buyer_accept)$")
    condition_ref: str = Field(min_length=1, max_length=200)
    condition_issuer: str | None = Field(default=None, max_length=200)
    deadline_hours: int = Field(default=168, ge=1, le=8760)
    hold_seconds: int = Field(default=0, ge=0, le=604800)
    require_trusted_slot: bool = False


class EvidenceRequest(BaseModel):
    reference: str = Field(default="", max_length=200)
    document: dict[str, Any] | None = None
    signature: dict[str, Any] | None = None


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=1000)
    evidence: dict[str, Any] | None = None


class ArbiterRequest(BaseModel):
    document: dict[str, Any]
    signature: dict[str, Any]


class BondRequest(BaseModel):
    memory_id: str = Field(min_length=3, max_length=200)
    claim_id: str | None = Field(default=None, max_length=200)
    publisher: str = Field(min_length=42, max_length=42)
    amount_usdc: str = Field(min_length=1, max_length=32)


class ChallengeRequest(BaseModel):
    claim_id: str = Field(min_length=3, max_length=200)
    challenger: str = Field(min_length=42, max_length=42)
    evidence: dict[str, Any] | None = None


class TrialRequest(BaseModel):
    scope: str = Field(min_length=2, max_length=80)
    payer: str = Field(min_length=42, max_length=42)
    budget_usdc: str = Field(default="1.00", max_length=32)


class VerdictRequest(BaseModel):
    document: dict[str, Any]
    signature: dict[str, Any]


class ExecutionRequest(BaseModel):
    execution_tx: str = Field(min_length=66, max_length=66)


# ────────────────────────────────── ledger ───────────────────────────────────

def _event(deal_id: str, kind: str, actor: str | None, payload: dict[str, Any]) -> None:
    row = db.one("SELECT COALESCE(MAX(seq), 0) AS seq FROM deal_events WHERE deal_id=?", (deal_id,))
    seq = int((row or {}).get("seq") or 0) + 1
    db.execute(
        "INSERT INTO deal_events (event_id, deal_id, seq, kind, actor, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (billing.ident("event", f"{deal_id}:{seq}", "evt_"), deal_id, seq, kind, actor,
         canonical(payload), now()),
    )


def _deal(deal_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM deals WHERE deal_id=?", (deal_id,))
    if not row:
        raise HTTPException(404, "deal not found")
    return row


def _public_deal(row: dict[str, Any]) -> dict[str, Any]:
    amount = int(row["amount_micro"])
    fee = amount * int(row["fee_bps"]) // 10000
    response = {
        key: row.get(key)
        for key in ("deal_id", "buyer", "seller", "seller_actor", "title", "condition_kind",
                    "condition_ref", "condition_issuer", "deadline", "state", "order_id",
                    "funded_tx", "release_after", "settlement_id", "created_at", "funded_at", "settled_at")
    }
    response["amount_usdc"] = usd_from_micro(amount)
    response["fee_usdc"] = usd_from_micro(fee)
    response["payout_usdc"] = usd_from_micro(amount - fee)
    response["fee_bps"] = int(row["fee_bps"])
    response["require_trusted_slot"] = bool(row["require_trusted_slot"])
    if row.get("proof_document"):
        response["proof"] = json.loads(str(row["proof_document"]))
    return response


def _settle(deal: dict[str, Any], kind: str, payee: str, amount_micro: int, fee_micro: int,
            proof: dict[str, Any]) -> dict[str, Any]:
    """Write a signed settlement instruction and freeze the deal on it."""
    settlement_id = billing.ident("settlement", f"{deal['deal_id']}:{kind}", "stl_")
    document = {
        "type": "attested.settlement/v1",
        "settlement_id": settlement_id,
        "service": SERVICE,
        "issuer": cfg.public_origin,
        "deal_id": deal["deal_id"],
        "kind": kind,
        "payee": payee.lower(),
        "asset": "USDC",
        "chain_id": 8453,
        "amount_micro": int(amount_micro),
        "fee_micro": int(fee_micro),
        "proof": proof,
        "issued_at": now(),
    }
    signature = signer.sign(document)
    inserted = db.execute(
        "INSERT INTO settlements (settlement_id, deal_id, kind, payee, amount_micro, fee_micro, "
        "document, signature, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (settlement_id) DO NOTHING",
        (settlement_id, deal["deal_id"], kind, payee.lower(), int(amount_micro), int(fee_micro),
         canonical(document), canonical(signature), now()),
    )
    if inserted == 1:
        _event(str(deal["deal_id"]), f"settlement.{kind}", None,
               {"settlement_id": settlement_id, "payee": payee.lower(), "amount_micro": int(amount_micro)})
    return {"settlement_id": settlement_id, "document": document, "signature": signature}


def _public_settlement(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "settlement_id": row["settlement_id"],
        "deal_id": row["deal_id"],
        "kind": row["kind"],
        "payee": row["payee"],
        "amount_usdc": usd_from_micro(int(row["amount_micro"])),
        "fee_usdc": usd_from_micro(int(row["fee_micro"])),
        "document": json.loads(str(row["document"])),
        "signature": json.loads(str(row["signature"])),
        "created_at": row["created_at"],
        "executed_at": row["executed_at"],
        "execution_tx": row["execution_tx"],
        "verify_url": f"{cfg.public_origin}/v1/settlements/{row['settlement_id']}",
    }


def _trusted(actor_id: str, scope: str) -> bool:
    row = db.one(
        "SELECT expires_at FROM trusted_slots WHERE actor_id=? AND scope=?", (actor_id, scope))
    return bool(row and str(row["expires_at"]) > now())


def _role(deal_id: str, request: Request) -> str:
    """Buyer and seller authority without accounts.

    Each side gets one HMAC-derived token when the deal is created. There is no
    login, no password reset and nothing to phish: the token *is* the party, the
    same way the declared payer address is the identity on the payment rail.
    """
    token = request.headers.get("x-deal-token", "")
    if len(token) < 32:
        raise HTTPException(401, "deal token required")
    for role in ("buyer", "seller"):
        if hmac.compare_digest(token, billing.token(f"{role}-token", deal_id, f"{role[0]}dt_")):
            return role
    raise HTTPException(403, "deal token does not belong to this deal")


def _on_deal_funded(order: dict[str, Any], tx_hash: str) -> None:
    deal_id = str(order.get("ref") or "")
    changed = db.execute(
        "UPDATE deals SET state='funded', funded_at=?, funded_tx=?, order_id=? "
        "WHERE deal_id=? AND state='draft'",
        (now(), tx_hash, order["order_id"], deal_id),
    )
    if changed == 1:
        _event(deal_id, "funded", None, {"tx_hash": tx_hash, "order_id": order["order_id"]})


def _on_bond_staked(order: dict[str, Any], tx_hash: str) -> None:
    bond_id = str(order.get("ref") or "")
    changed = db.execute(
        "UPDATE bonds SET state='bonded', bonded_at=?, order_id=? WHERE bond_id=? AND state='pending'",
        (now(), order["order_id"], bond_id),
    )
    if changed != 1:
        return


def _on_trial_paid(order: dict[str, Any], tx_hash: str) -> None:
    trial_id = str(order.get("ref") or "")
    db.execute(
        "UPDATE sandbox_trials SET state='active', started_at=?, expires_at=?, order_id=? "
        "WHERE trial_id=? AND state='pending'",
        (now(), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 14 * 86400)),
         order["order_id"], trial_id),
    )


billing.handlers["deal.fund"] = _on_deal_funded
billing.handlers["bond.stake"] = _on_bond_staked
billing.handlers["sandbox.trial"] = _on_trial_paid


# ─────────────────── the ecosystem's view of this service ────────────────────

CAPABILITIES = (
    Capability("attested-deal", "deal.status@v1", "Deal status",
               "Read the public state of a proof-gated escrow deal: amount, fee, condition, "
               "deadline and settlement.", 0.0, "commerce/escrow",
               {"type": "object", "required": ["deal_id"],
                "properties": {"deal_id": {"type": "string"}}}, OBJECT_OUTPUT),
    Capability("attested-deal", "settlement.verify@v1", "Verify settlement",
               "Verify a signed attested.settlement/v1 instruction and report whether it has "
               "been executed on chain yet.", 0.0, "commerce/settlement",
               {"type": "object", "required": ["settlement_id"],
                "properties": {"settlement_id": {"type": "string"}}}, OBJECT_OUTPUT),
    Capability("attested-deal", "slot.check@v1", "Trusted slot check",
               "Report whether an agent holds an active trusted slot earned through a paid "
               "sandbox trial.", 0.0, "trust/reputation",
               {"type": "object", "required": ["actor_id"],
                "properties": {"actor_id": {"type": "string"}, "scope": {"type": "string"}}},
               OBJECT_OUTPUT),
)

aimarket = AIMarket(
    cfg, signer, CAPABILITIES,
    name="Attested Deal",
    description="Escrow that releases on proof: verified receipts, Truth verdicts and named "
                "attestations, with signed settlements and no custody.",
    invoke_base=cfg.extra.get("INVOKE_BASE") or cfg.public_origin,
    publisher_id="attested-deal",
)

def _dispatch(capability_id: str, payload: dict[str, Any], request: Request) -> Any:
    """Capabilities are read-only on purpose.

    Everything that moves money keeps its own checkout and its own party token;
    the ecosystem gets the surface that answers questions about a deal, not one
    that can open or release one on someone's behalf.
    """
    if capability_id == "deal.status@v1":
        return _public_deal(_deal(str(payload.get("deal_id") or "")))
    if capability_id == "settlement.verify@v1":
        return read_settlement(str(payload.get("settlement_id") or ""))
    return read_slots(str(payload.get("actor_id") or ""))

@asynccontextmanager
async def lifespan(_: FastAPI) -> Iterator[None]:
    billing.start()
    # Publishing is best effort: a hub that is down means this provider is
    # missing from the ecosystem map, not that the product stops taking money.
    # It is also continuous — retried until the hub accepts it, then refreshed.
    publishing = aimarket.start_publishing()
    yield
    publishing.set()
    billing.stop()


app = FastAPI(title="Attested Deal", version=VERSION, lifespan=lifespan,
              description="Escrow that releases on proof, not on trust.")
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
        "status": "ok",
        "service": SERVICE,
        "version": VERSION,
        "database": "postgresql" if db.is_postgres else "sqlite",
        "billing": "kova",
        "signing": "ed25519+ml-dsa-65" if cfg.pqc else "ed25519",
        "fee_bps": FEE_BPS,
        "proof_backends": {"prove": bool(PROVE_URL), "truth": bool(TRUTH_URL)},
    }


@app.get("/.well-known/attested-deal.json")
def well_known() -> dict[str, Any]:
    document = {
        "type": "attested.service/v1",
        "service": SERVICE,
        "version": VERSION,
        "origin": cfg.public_origin,
        "settlement_type": "attested.settlement/v1",
        "asset": "USDC",
        "chain_id": 8453,
        "fee_bps": FEE_BPS,
        "arbiter_keys": sorted(ARBITER_KEYS),
        "verifier_keys": sorted(VERIFIER_KEYS),
        "issued_at": now(),
    }
    return {**document, "signature": signer.sign(document)}


# ──────────────────────────────────  deals  ──────────────────────────────────

@app.post("/v1/deals", status_code=201)
def create_deal(body: DealRequest, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "create-deal", 20)
    if not EVM_ADDRESS.fullmatch(body.buyer) or not EVM_ADDRESS.fullmatch(body.seller):
        raise HTTPException(422, "buyer and seller must be valid EVM addresses")
    if body.buyer.lower() == body.seller.lower():
        raise HTTPException(422, "buyer and seller must differ")
    amount_micro = micro_from_usd(body.amount_usdc)
    if amount_micro < 100_000:
        raise HTTPException(422, "minimum deal amount is 0.10 USDC")
    fee_bps = FEE_BPS
    try:
        key = billing.active_key(request, scope="desk")
        fee_bps = max(0, FEE_BPS // 2)
        desk_key_id = str(key["key_id"])
    except HTTPException:
        desk_key_id = ""
    if body.require_trusted_slot:
        if not body.seller_actor:
            raise HTTPException(422, "require_trusted_slot needs seller_actor")
        if not _trusted(body.seller_actor, "deal"):
            raise HTTPException(409, "seller has no active trusted slot; run a sandbox trial first")
    idempotency = request.headers.get("idempotency-key", "").strip()
    if len(idempotency) < 16:
        raise HTTPException(400, "Idempotency-Key header is required (16-200 characters)")
    deal_id = billing.ident("deal", sha256_hex(f"{SERVICE}:{idempotency}"), "deal_")
    deadline = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + body.deadline_hours * 3600))
    existing = db.one("SELECT * FROM deals WHERE deal_id=?", (deal_id,))
    if existing is None:
        db.execute(
            "INSERT INTO deals (deal_id, buyer, seller, seller_actor, title, amount_micro, fee_bps, "
            "condition_kind, condition_ref, condition_issuer, hold_seconds, deadline, "
            "require_trusted_slot, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (deal_id, body.buyer.lower(), body.seller.lower(), body.seller_actor, body.title,
             amount_micro, fee_bps, body.condition_kind, body.condition_ref, body.condition_issuer,
             body.hold_seconds, deadline, 1 if body.require_trusted_slot else 0, now()),
        )
        _event(deal_id, "created", None, {
            "buyer": body.buyer.lower(), "seller": body.seller.lower(),
            "amount_micro": amount_micro, "condition_kind": body.condition_kind,
            "condition_ref": body.condition_ref, "fee_bps": fee_bps,
            "desk_key": desk_key_id or None,
        })
    checkout = billing.open_order(
        purpose="deal.fund", plan="deal.escrow", payer=body.buyer,
        amount_micro=amount_micro, idempotency=f"deal:{idempotency}", ref=deal_id,
    )
    row = _deal(deal_id)
    return {
        "deal": _public_deal(row),
        "buyer_token": billing.token("buyer-token", deal_id, "bdt_"),
        "seller_token": billing.token("seller-token", deal_id, "sdt_"),
        "checkout": checkout,
        "next_step": "send the exact USDC amount; the deal funds itself when the transfer finalizes",
    }


@app.get("/v1/deals/{deal_id}")
def read_deal(deal_id: str, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "read-deal", 60)
    row = _deal(deal_id)
    if row["state"] == "draft" and row.get("order_id") is None:
        order = db.one("SELECT * FROM billing_orders WHERE purpose='deal.fund' AND ref=?", (deal_id,))
        if order and order["state"] == "pending":
            billing.settle(order)
            row = _deal(deal_id)
    return _public_deal(row)


@app.get("/v1/deals/{deal_id}/events")
def read_events(deal_id: str) -> dict[str, Any]:
    _deal(deal_id)
    rows = db.all("SELECT seq, kind, actor, payload, created_at FROM deal_events WHERE deal_id=? ORDER BY seq",
                  (deal_id,))
    for row in rows:
        row["payload"] = json.loads(str(row["payload"]))
    return {"deal_id": deal_id, "count": len(rows), "events": rows}


@app.post("/v1/deals/{deal_id}/evidence")
def submit_evidence(deal_id: str, body: EvidenceRequest, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "evidence", 30)
    role = _role(deal_id, request)
    row = _deal(deal_id)
    if row["state"] != "funded":
        raise HTTPException(409, f"deal is '{row['state']}', evidence is only accepted while funded")
    if str(row["deadline"]) <= now():
        raise HTTPException(409, "the deal deadline has passed; the buyer may refund")
    actor = str(row["buyer"]) if role == "buyer" else str(row["seller"])
    proof = _check_condition(row, body, actor)
    release_after = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + int(row["hold_seconds"])))
    changed = db.execute(
        "UPDATE deals SET state='proved', proof_document=?, release_after=? WHERE deal_id=? AND state='funded'",
        (canonical(proof), release_after, deal_id),
    )
    if changed != 1:
        raise HTTPException(409, "deal changed state while the proof was being checked")
    _event(deal_id, "proved", role, proof)
    return {"deal": _public_deal(_deal(deal_id)), "release_after": release_after}


@app.post("/v1/deals/{deal_id}/release")
def release_deal(deal_id: str, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "release", 30)
    _role(deal_id, request)
    row = _deal(deal_id)
    if row["state"] != "proved":
        raise HTTPException(409, f"deal is '{row['state']}', only a proved deal can be released")
    if str(row["release_after"] or "") > now():
        raise HTTPException(409, f"release hold is active until {row['release_after']}")
    amount = int(row["amount_micro"])
    fee = amount * int(row["fee_bps"]) // 10000
    proof = json.loads(str(row["proof_document"] or "{}"))
    settlement = _settle(row, "release", str(row["seller"]), amount - fee, fee, proof)
    db.execute("UPDATE deals SET state='released', settled_at=?, settlement_id=? WHERE deal_id=? AND state='proved'",
               (now(), settlement["settlement_id"], deal_id))
    return {"deal": _public_deal(_deal(deal_id)), "settlement": settlement}


@app.post("/v1/deals/{deal_id}/refund")
def refund_deal(deal_id: str, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "refund", 30)
    role = _role(deal_id, request)
    if role != "buyer":
        raise HTTPException(403, "only the buyer can claim a refund")
    row = _deal(deal_id)
    if row["state"] != "funded":
        raise HTTPException(409, f"deal is '{row['state']}', only an unproved funded deal can be refunded")
    if str(row["deadline"]) > now():
        raise HTTPException(409, f"the seller still has until {row['deadline']} to prove delivery")
    settlement = _settle(row, "refund", str(row["buyer"]), int(row["amount_micro"]), 0,
                         {"kind": "deadline", "deadline": row["deadline"], "checked_at": now()})
    db.execute("UPDATE deals SET state='refunded', settled_at=?, settlement_id=? WHERE deal_id=? AND state='funded'",
               (now(), settlement["settlement_id"], deal_id))
    return {"deal": _public_deal(_deal(deal_id)), "settlement": settlement}


# ─────────────────────────────── truth desk ──────────────────────────────────

@app.post("/v1/deals/{deal_id}/dispute", status_code=201)
def open_dispute(deal_id: str, body: DisputeRequest, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "dispute", 20)
    role = _role(deal_id, request)
    row = _deal(deal_id)
    if row["state"] not in {"funded", "proved"}:
        raise HTTPException(409, f"deal is '{row['state']}' and can no longer be contested")
    dispute_id = billing.ident("dispute", deal_id, "dsp_")
    inserted = db.execute(
        "INSERT INTO disputes (dispute_id, deal_id, opened_by, reason, evidence, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (dispute_id) DO NOTHING",
        (dispute_id, deal_id, role, body.reason,
         canonical(body.evidence) if body.evidence else None, now()),
    )
    if inserted != 1:
        raise HTTPException(409, "this deal already has an open dispute")
    db.execute("UPDATE deals SET state='contested' WHERE deal_id=?", (deal_id,))
    _event(deal_id, "contested", role, {"dispute_id": dispute_id, "reason": body.reason})
    return {
        "dispute_id": dispute_id,
        "deal_id": deal_id,
        "state": "open",
        "opened_by": role,
        "arbiter_keys": sorted(ARBITER_KEYS),
        "settlement_note": "settlement is frozen until a named arbiter signs an outcome",
    }


@app.get("/v1/disputes/{dispute_id}")
def read_dispute(dispute_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM disputes WHERE dispute_id=?", (dispute_id,))
    if not row:
        raise HTTPException(404, "dispute not found")
    row["evidence"] = json.loads(str(row["evidence"])) if row["evidence"] else None
    return row


@app.post("/v1/disputes/{dispute_id}/settle")
def settle_dispute(dispute_id: str, body: ArbiterRequest, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "settle-dispute", 20)
    dispute = db.one("SELECT * FROM disputes WHERE dispute_id=?", (dispute_id,))
    if not dispute:
        raise HTTPException(404, "dispute not found")
    if dispute["state"] != "open":
        raise HTTPException(409, "dispute is already resolved")
    public_key = normalize_key(str(body.signature.get("public_key", "")))
    if public_key not in ARBITER_KEYS:
        raise HTTPException(403, "outcome is not signed by a named arbiter key")
    if str(body.document.get("dispute_id", "")) != dispute_id:
        raise HTTPException(409, "outcome is bound to a different dispute")
    outcome = str(body.document.get("outcome", ""))
    if outcome not in {"release", "refund", "split"}:
        raise HTTPException(422, "outcome must be release, refund or split")
    if not verify_signature(body.document, body.signature, public_key):
        raise HTTPException(403, "arbiter signature does not verify")
    row = _deal(str(dispute["deal_id"]))
    amount = int(row["amount_micro"])
    fee = amount * int(row["fee_bps"]) // 10000
    proof = {"kind": "arbiter", "dispute_id": dispute_id, "arbiter_public_key": public_key,
             "outcome": outcome, "document_digest": sha256_hex(canonical(body.document)),
             "checked_at": now()}
    if outcome == "release":
        settlement = _settle(row, "release", str(row["seller"]), amount - fee, fee, proof)
        state = "released"
    elif outcome == "refund":
        settlement = _settle(row, "refund", str(row["buyer"]), amount, 0, proof)
        state = "refunded"
    else:
        seller_share = int(body.document.get("seller_micro", (amount - fee) // 2))
        if seller_share < 0 or seller_share > amount - fee:
            raise HTTPException(422, "seller_micro is outside the deal amount")
        settlement = _settle(row, "split", str(row["seller"]), seller_share, fee,
                             {**proof, "buyer_micro": amount - fee - seller_share})
        state = "split"
    db.execute("UPDATE disputes SET state='resolved', outcome=?, arbiter=?, resolved_at=? WHERE dispute_id=?",
               (outcome, public_key, now(), dispute_id))
    db.execute("UPDATE deals SET state=?, settled_at=?, settlement_id=? WHERE deal_id=?",
               (state, now(), settlement["settlement_id"], row["deal_id"]))
    _event(str(row["deal_id"]), f"dispute.{outcome}", public_key, proof)
    return {"dispute_id": dispute_id, "outcome": outcome,
            "deal": _public_deal(_deal(str(row["deal_id"]))), "settlement": settlement}


# ─────────────────────────────── settlements ─────────────────────────────────

@app.get("/v1/settlements/{settlement_id}")
def read_settlement(settlement_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM settlements WHERE settlement_id=?", (settlement_id,))
    if not row:
        raise HTTPException(404, "settlement not found")
    public = _public_settlement(row)
    public["verified"] = verify_signature(public["document"], public["signature"], signer.public_key)
    return public


@app.post("/v1/admin/settlements/{settlement_id}/execute")
def execute_settlement(settlement_id: str, body: ExecutionRequest,
                       authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, cfg.admin_token):
        raise HTTPException(401, "operator authentication required")
    changed = db.execute(
        "UPDATE settlements SET executed_at=?, execution_tx=? WHERE settlement_id=? AND executed_at IS NULL",
        (now(), body.execution_tx.lower(), settlement_id))
    if changed != 1:
        raise HTTPException(409, "settlement not found or already executed")
    row = db.one("SELECT * FROM settlements WHERE settlement_id=?", (settlement_id,)) or {}
    _event(str(row.get("deal_id")), "settlement.executed", None,
           {"settlement_id": settlement_id, "execution_tx": body.execution_tx.lower()})
    return _public_settlement(row)


@app.get("/v1/admin/settlements")
def pending_settlements(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, cfg.admin_token):
        raise HTTPException(401, "operator authentication required")
    rows = db.all(
        "SELECT settlement_id, deal_id, kind, payee, amount_micro, fee_micro, created_at, executed_at, "
        "execution_tx FROM settlements ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 1000)),))
    for row in rows:
        row["amount_usdc"] = usd_from_micro(int(row.pop("amount_micro")))
        row["fee_usdc"] = usd_from_micro(int(row.pop("fee_micro")))
    return {"count": len(rows), "settlements": rows,
            "unexecuted": sum(1 for row in rows if not row["executed_at"])}


# ────────────────────────── memory bonds and slashing ────────────────────────

@app.post("/v1/bonds", status_code=201)
def create_bond(body: BondRequest, request: Request) -> dict[str, Any]:
    """Stake USDC behind a memory. Lying costs the publisher, not the reader."""
    rate_limit(billing, request, "create-bond", 20)
    actor = verified_actor(request)
    amount_micro = micro_from_usd(body.amount_usdc)
    if amount_micro < 1_000_000:
        raise HTTPException(422, "minimum bond is 1.00 USDC")
    idempotency = request.headers.get("idempotency-key", "").strip()
    if len(idempotency) < 16:
        raise HTTPException(400, "Idempotency-Key header is required (16-200 characters)")
    bond_id = billing.ident("bond", sha256_hex(f"{SERVICE}:{idempotency}"), "bond_")
    if db.one("SELECT bond_id FROM bonds WHERE bond_id=?", (bond_id,)) is None:
        db.execute(
            "INSERT INTO bonds (bond_id, publisher, publisher_actor, memory_id, claim_id, amount_micro, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (bond_id, body.publisher.lower(), actor, body.memory_id, body.claim_id, amount_micro, now()),
        )
    checkout = billing.open_order(
        purpose="bond.stake", plan="deal.bond", payer=body.publisher,
        amount_micro=amount_micro, idempotency=f"bond:{idempotency}", ref=bond_id,
    )
    return {"bond": _public_bond(db.one("SELECT * FROM bonds WHERE bond_id=?", (bond_id,)) or {}),
            "checkout": checkout}


def _public_bond(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        raise HTTPException(404, "bond not found")
    return {
        "bond_id": row["bond_id"], "publisher": row["publisher"], "memory_id": row["memory_id"],
        "claim_id": row["claim_id"], "amount_usdc": usd_from_micro(int(row["amount_micro"])),
        "state": row["state"], "slash_bps": SLASH_BPS, "created_at": row["created_at"],
        "bonded_at": row["bonded_at"], "closed_at": row["closed_at"],
    }


@app.get("/v1/bonds/{bond_id}")
def read_bond(bond_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM bonds WHERE bond_id=?", (bond_id,))
    if not row:
        raise HTTPException(404, "bond not found")
    if row["state"] == "pending":
        order = db.one("SELECT * FROM billing_orders WHERE purpose='bond.stake' AND ref=?", (bond_id,))
        if order and order["state"] == "pending":
            billing.settle(order)
            row = db.one("SELECT * FROM bonds WHERE bond_id=?", (bond_id,)) or row
    return _public_bond(row)


@app.post("/v1/bonds/{bond_id}/challenge", status_code=201)
def challenge_bond(bond_id: str, body: ChallengeRequest, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "challenge", 20)
    actor = verified_actor(request)
    bond = db.one("SELECT * FROM bonds WHERE bond_id=?", (bond_id,))
    if not bond:
        raise HTTPException(404, "bond not found")
    if bond["state"] != "bonded":
        raise HTTPException(409, f"bond is '{bond['state']}' and cannot be challenged")
    if actor == str(bond["publisher_actor"] or ""):
        raise HTTPException(403, "a publisher cannot challenge its own bond")
    challenge_id = billing.ident("challenge", f"{bond_id}:{actor}", "chg_")
    inserted = db.execute(
        "INSERT INTO bond_challenges (challenge_id, bond_id, challenger, challenger_actor, claim_id, "
        "evidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (challenge_id) DO NOTHING",
        (challenge_id, bond_id, body.challenger.lower(), actor, body.claim_id,
         canonical(body.evidence) if body.evidence else None, now()),
    )
    if inserted != 1:
        raise HTTPException(409, "this actor already challenged this bond")
    db.execute("UPDATE bonds SET state='challenged' WHERE bond_id=? AND state='bonded'", (bond_id,))
    return {"challenge_id": challenge_id, "bond_id": bond_id, "state": "open",
            "resolution": "POST /v1/challenges/{id}/resolve reads the Truth claim and slashes on 'refuted'"}


@app.post("/v1/challenges/{challenge_id}/resolve")
def resolve_challenge(challenge_id: str, request: Request) -> dict[str, Any]:
    """The Truth Layer decides, not the desk: the claim state is the verdict."""
    rate_limit(billing, request, "resolve-challenge", 20)
    challenge = db.one("SELECT * FROM bond_challenges WHERE challenge_id=?", (challenge_id,))
    if not challenge:
        raise HTTPException(404, "challenge not found")
    if challenge["state"] != "open":
        raise HTTPException(409, "challenge is already resolved")
    bond = db.one("SELECT * FROM bonds WHERE bond_id=?", (challenge["bond_id"],))
    if not bond:
        raise HTTPException(404, "bond not found")
    claim = proofs.claim(str(challenge["claim_id"]))
    state = str(claim.get("state", ""))
    amount = int(bond["amount_micro"])
    if state == "refuted":
        slashed = amount * SLASH_BPS // 10000
        settlement = _settle(
            {"deal_id": str(bond["bond_id"]), "amount_micro": amount, "fee_bps": 0},
            "slash", str(challenge["challenger"]), slashed, amount - slashed,
            {"kind": "truth_claim", "evidence_pack_id": challenge["claim_id"], "claim_state": state,
             "truth_status": claim.get("truth_status"), "bond_id": bond["bond_id"], "checked_at": now()},
        )
        db.execute("UPDATE bonds SET state='slashed', closed_at=? WHERE bond_id=?", (now(), bond["bond_id"]))
        db.execute("UPDATE bond_challenges SET state='upheld', settlement_id=?, resolved_at=? WHERE challenge_id=?",
                   (settlement["settlement_id"], now(), challenge_id))
        return {"challenge_id": challenge_id, "outcome": "slashed", "claim_state": state,
                "settlement": settlement}
    if state == "verified":
        db.execute("UPDATE bonds SET state='bonded' WHERE bond_id=?", (bond["bond_id"],))
        db.execute("UPDATE bond_challenges SET state='dismissed', resolved_at=? WHERE challenge_id=?",
                   (now(), challenge_id))
        return {"challenge_id": challenge_id, "outcome": "dismissed", "claim_state": state}
    raise HTTPException(409, f"claim state is '{state or 'unknown'}'; the challenge stays open until Truth decides")


# ─────────────────────── sandbox trials → trusted slots ──────────────────────

@app.post("/v1/trials", status_code=201)
def create_trial(body: TrialRequest, request: Request) -> dict[str, Any]:
    """No agent reaches a trusted slot without a paid, bounded trial first."""
    rate_limit(billing, request, "create-trial", 10)
    actor = verified_actor(request)
    budget_micro = micro_from_usd(body.budget_usdc)
    idempotency = request.headers.get("idempotency-key", "").strip()
    if len(idempotency) < 16:
        raise HTTPException(400, "Idempotency-Key header is required (16-200 characters)")
    trial_id = billing.ident("trial", sha256_hex(f"{SERVICE}:{idempotency}"), "trl_")
    if db.one("SELECT trial_id FROM sandbox_trials WHERE trial_id=?", (trial_id,)) is None:
        db.execute(
            "INSERT INTO sandbox_trials (trial_id, agent_actor, scope, budget_micro, created_at) "
            "VALUES (?, ?, ?, ?, ?)", (trial_id, actor, body.scope, budget_micro, now()))
    plan = billing.plans["deal.sandbox.trial"]
    checkout = billing.open_order(
        purpose="sandbox.trial", plan=plan.code, payer=body.payer,
        amount_micro=micro_from_usd(plan.price_usd), idempotency=f"trial:{idempotency}", ref=trial_id,
    )
    return {"trial": _public_trial(db.one("SELECT * FROM sandbox_trials WHERE trial_id=?", (trial_id,)) or {}),
            "checkout": checkout,
            "verifier_keys": sorted(VERIFIER_KEYS),
            "next_step": "run the bounded workload, then POST the signed verdict to /v1/trials/{id}/verdict"}


def _public_trial(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        raise HTTPException(404, "trial not found")
    return {
        "trial_id": row["trial_id"], "agent_actor": row["agent_actor"], "scope": row["scope"],
        "budget_usdc": usd_from_micro(int(row["budget_micro"])), "state": row["state"],
        "created_at": row["created_at"], "started_at": row["started_at"],
        "expires_at": row["expires_at"], "decided_at": row["decided_at"],
        "verdict": json.loads(str(row["verdict"])) if row["verdict"] else None,
    }


@app.get("/v1/trials/{trial_id}")
def read_trial(trial_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM sandbox_trials WHERE trial_id=?", (trial_id,))
    if not row:
        raise HTTPException(404, "trial not found")
    if row["state"] == "pending":
        order = db.one("SELECT * FROM billing_orders WHERE purpose='sandbox.trial' AND ref=?", (trial_id,))
        if order and order["state"] == "pending":
            billing.settle(order)
            row = db.one("SELECT * FROM sandbox_trials WHERE trial_id=?", (trial_id,)) or row
    return _public_trial(row)


@app.post("/v1/trials/{trial_id}/verdict")
def submit_verdict(trial_id: str, body: VerdictRequest, request: Request) -> dict[str, Any]:
    rate_limit(billing, request, "trial-verdict", 20)
    row = db.one("SELECT * FROM sandbox_trials WHERE trial_id=?", (trial_id,))
    if not row:
        raise HTTPException(404, "trial not found")
    if row["state"] != "active":
        raise HTTPException(409, f"trial is '{row['state']}', a verdict is only accepted while active")
    if str(row["expires_at"] or "") <= now():
        db.execute("UPDATE sandbox_trials SET state='expired', decided_at=? WHERE trial_id=?", (now(), trial_id))
        raise HTTPException(409, "the trial window has closed")
    public_key = normalize_key(str(body.signature.get("public_key", "")))
    if public_key not in VERIFIER_KEYS:
        raise HTTPException(403, "verdict is not signed by a named verifier key")
    if str(body.document.get("trial_id", "")) != trial_id:
        raise HTTPException(409, "verdict is bound to a different trial")
    if not verify_signature(body.document, body.signature, public_key):
        raise HTTPException(403, "verdict signature does not verify")
    passed = body.document.get("result") == "pass"
    state = "passed" if passed else "failed"
    db.execute("UPDATE sandbox_trials SET state=?, verdict=?, decided_at=? WHERE trial_id=? AND state='active'",
               (state, canonical({"document": body.document, "signature": body.signature}), now(), trial_id))
    granted = None
    if passed:
        expires_at = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + TRUSTED_SLOT_DAYS * 86400))
        db.execute(
            "INSERT INTO trusted_slots (actor_id, scope, trial_id, granted_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT (actor_id, scope) DO UPDATE SET "
            "trial_id=EXCLUDED.trial_id, granted_at=EXCLUDED.granted_at, expires_at=EXCLUDED.expires_at",
            (str(row["agent_actor"]), str(row["scope"]), trial_id, now(), expires_at))
        granted = {"actor_id": row["agent_actor"], "scope": row["scope"], "expires_at": expires_at}
    return {"trial": _public_trial(db.one("SELECT * FROM sandbox_trials WHERE trial_id=?", (trial_id,)) or {}),
            "trusted_slot": granted}


@app.get("/v1/slots/{actor_id}")
def read_slots(actor_id: str) -> dict[str, Any]:
    if not ACTOR_ID.fullmatch(actor_id):
        raise HTTPException(422, "actor_id must be a did:actor identity")
    rows = db.all("SELECT scope, trial_id, granted_at, expires_at FROM trusted_slots WHERE actor_id=?", (actor_id,))
    stamp = now()
    for row in rows:
        row["active"] = str(row["expires_at"]) > stamp
    return {"actor_id": actor_id, "slots": rows, "trusted": any(row["active"] for row in rows)}


# ──────────────────────────────── public stats ───────────────────────────────

@app.get("/v1/stats")
def stats() -> dict[str, Any]:
    deals = db.all("SELECT state, COUNT(*) AS n, COALESCE(SUM(amount_micro),0) AS micro FROM deals GROUP BY state")
    settled = db.one(
        "SELECT COUNT(*) AS n, COALESCE(SUM(amount_micro),0) AS micro, COALESCE(SUM(fee_micro),0) AS fee "
        "FROM settlements") or {}
    return {
        "service": SERVICE,
        "generated_at": now(),
        "deals_by_state": {str(row["state"]): int(row["n"]) for row in deals},
        "escrowed_usdc": usd_from_micro(sum(int(row["micro"]) for row in deals
                                            if row["state"] in {"funded", "proved", "contested"})),
        "settlements": int(settled.get("n") or 0),
        "settled_usdc": usd_from_micro(int(settled.get("micro") or 0)),
        "protocol_fees_usdc": usd_from_micro(int(settled.get("fee") or 0)),
        "bonds_open": int((db.one("SELECT COUNT(*) AS n FROM bonds WHERE state IN ('bonded','challenged')") or {}).get("n") or 0),
        "trusted_slots": int((db.one("SELECT COUNT(*) AS n FROM trusted_slots WHERE expires_at > ?", (now(),)) or {}).get("n") or 0),
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

    @app.get("/track", include_in_schema=False)
    def track_page() -> FileResponse:
        return FileResponse(os.path.join(WEB_ROOT, "track.html"))
