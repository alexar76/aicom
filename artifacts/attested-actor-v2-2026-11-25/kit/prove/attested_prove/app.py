"""Attested Prove — receipts, passports, dual provenance and nullifier claims.

Four surfaces over one signing key:

* **Receipt API.** Sign any agent action into an `attested.receipt/v1` document
  with a permanent, keyless verification URL. Issuing costs money; verifying is
  free forever, because a receipt nobody can check is worth nothing.
* **Agent Passport.** A signed reputation slice derived from those receipts, with
  an expiry and a knock gate a hub or monitor can call before it lets an agent in.
* **Dual provenance.** An oracle-signed observation of the *world* bound to an
  agent's *decision*, so "the sensor said X" and "the agent did Y" verify as one
  document instead of two unrelated claims.
* **ZK nullifier claims.** Prove membership of a registered set once, without
  revealing which member — a linkable ring signature over Ed25519, not a SNARK,
  and the API says which it is (see `nullifier.py`).

The commercial line is deliberate: **pay to write, free to read.** Verification,
gate checks and ring listings never need a key, because those are exactly the
calls a relying party makes about someone else's agent.
"""
from __future__ import annotations

import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Iterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import nullifier as nz
from .core import (
    ACTOR_ID,
    OBJECT_OUTPUT,
    AIMarket,
    Billing,
    Capability,
    Database,
    Kova,
    Plan,
    Signer,
    canonical,
    load_settings,
    normalize_key,
    now,
    rate_limit,
    sha256_hex,
    verified_actor,
    verify_signature,
)

SERVICE = "attested-prove"
VERSION = "1.0.0"
PREFIX = "PROVE"

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS receipts (
        receipt_id TEXT PRIMARY KEY,
        key_id TEXT,
        subject_actor TEXT NOT NULL,
        action TEXT NOT NULL,
        resource TEXT NOT NULL,
        digest TEXT NOT NULL,
        document TEXT NOT NULL,
        signature TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS passports (
        passport_id TEXT PRIMARY KEY,
        actor_id TEXT NOT NULL,
        tier TEXT NOT NULL,
        document TEXT NOT NULL,
        signature TEXT NOT NULL,
        issued_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        revoked_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS world_attestations (
        attestation_id TEXT PRIMARY KEY,
        oracle_key TEXT NOT NULL,
        subject TEXT NOT NULL,
        observation_digest TEXT UNIQUE NOT NULL,
        document TEXT NOT NULL,
        signature TEXT NOT NULL,
        observed_at TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memory_bindings (
        binding_id TEXT PRIMARY KEY,
        attestation_id TEXT NOT NULL,
        memory_id TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        decision TEXT NOT NULL,
        receipt_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nullifier_scopes (
        scope TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        owner_key_id TEXT,
        open_registration INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nullifier_members (
        scope TEXT NOT NULL,
        public_key TEXT NOT NULL,
        label TEXT NOT NULL DEFAULT '',
        registered_at TEXT NOT NULL,
        PRIMARY KEY (scope, public_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nullifier_spends (
        scope TEXT NOT NULL,
        key_image TEXT NOT NULL,
        claim TEXT NOT NULL,
        ring_size INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (scope, key_image)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_receipts_subject ON receipts(subject_actor, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_passports_actor ON passports(actor_id, issued_at)",
)

PLANS = (
    Plan("prove.issuer.monthly", "Receipt Issuer", "49.00", 30,
         "Issue signed receipts, passports and dual-provenance bindings. Verification stays free.",
         scope="issuer"),
    Plan("prove.privacy.monthly", "Privacy Desk", "149.00", 30,
         "Run nullifier scopes: create rings, register members, one-time anonymous claims.",
         scope="privacy"),
)

TIERS = (
    ("sealed", 200, 30),
    ("established", 50, 7),
    ("observed", 5, 1),
    ("new", 0, 0),
)

cfg = load_settings(SERVICE, PREFIX, extra_keys=("ORACLE_KEYS", "PASSPORT_DAYS", "MAX_RING",
                                                 "GATE_MIN_RECEIPTS", "CAPABILITY_TOKEN",
                                                 "AIMARKET_HUB_URL", "PUBLISHER_TOKEN",
                                                 "INVOKE_BASE"))
db = Database(cfg.database_url or "sqlite:///./data/attested-prove.sqlite3", SCHEMA)
kova = Kova(cfg)
billing = Billing(cfg, db, kova, PLANS)
signer = Signer(cfg.signing_key_path, pqc=cfg.pqc)

PASSPORT_DAYS = max(1, min(int(cfg.extra.get("PASSPORT_DAYS") or 7), 90))
MAX_RING = max(2, min(int(cfg.extra.get("MAX_RING") or 64), 256))
GATE_MIN_RECEIPTS = max(0, int(cfg.extra.get("GATE_MIN_RECEIPTS") or 1))
ORACLE_KEYS = {normalize_key(item) for item in (cfg.extra.get("ORACLE_KEYS") or "").replace(",", " ").split() if item.strip()}
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


# ───────────────────────────────── requests ──────────────────────────────────

class ReceiptRequest(BaseModel):
    subject_actor: str = Field(pattern=r"^did:actor:[0-9a-f]{64}$")
    action: str = Field(min_length=2, max_length=120)
    resource: str = Field(min_length=1, max_length=300)
    payload: dict[str, Any] | None = None
    attributes: dict[str, Any] | None = None


class PassportRequest(BaseModel):
    actor_id: str = Field(pattern=r"^did:actor:[0-9a-f]{64}$")
    audience: str = Field(default="*", max_length=200)


class VerifyRequest(BaseModel):
    document: dict[str, Any]
    signature: dict[str, Any]


class WorldRequest(BaseModel):
    document: dict[str, Any]
    signature: dict[str, Any]
    subject: str = Field(min_length=1, max_length=200)


class BindRequest(BaseModel):
    attestation_id: str = Field(min_length=8, max_length=80)
    memory_id: str = Field(min_length=1, max_length=200)
    decision: str = Field(min_length=1, max_length=2000)


class ScopeRequest(BaseModel):
    scope: str = Field(min_length=3, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]{2,79}$")
    label: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=400)
    open_registration: bool = False


class MemberRequest(BaseModel):
    public_key: str = Field(min_length=64, max_length=64)
    label: str = Field(default="", max_length=120)


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=1, max_length=400)
    proof: dict[str, Any]


def _admin(authorization: str | None) -> None:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, cfg.admin_token):
        raise HTTPException(401, "operator authentication required")


# ─────────────────── the ecosystem's view of this service ────────────────────

CAPABILITIES = (
    Capability("attested-prove", "receipt.verify@v1", "Verify a receipt",
               "Verify a signed document offline — no lookup, no key — and say whether this "
               "service issued it.", 0.0, "provenance/verification",
               {"type": "object", "required": ["document", "signature"],
                "properties": {"document": {"type": "object"}, "signature": {"type": "object"}}},
               OBJECT_OUTPUT),
    Capability("attested-prove", "passport.gate@v1", "Agent knock gate",
               "Decide whether an agent may enter: valid passport, receipt history and tier, "
               "with the reasons for a refusal.", 0.0, "trust/reputation",
               {"type": "object", "required": ["actor_id"],
                "properties": {"actor_id": {"type": "string"}}}, OBJECT_OUTPUT),
    Capability("attested-prove", "nullifier.scope@v1", "Read a nullifier scope",
               "The public ring of a one-time anonymous claim scope, its size and what has "
               "already been spent.", 0.0, "privacy/zero-knowledge",
               {"type": "object", "required": ["scope"],
                "properties": {"scope": {"type": "string"}}}, OBJECT_OUTPUT),
)

aimarket = AIMarket(
    cfg, signer, CAPABILITIES,
    name="Attested Prove",
    description="Signed receipts with permanent keyless verification, agent passports, dual "
                "provenance and one-time anonymous claims.",
    invoke_base=cfg.extra.get("INVOKE_BASE") or cfg.public_origin,
    publisher_id="attested-prove",
)

def _dispatch(capability_id: str, payload: dict[str, Any], request: Request) -> Any:
    """Everything reachable here is already free and keyless over HTTP.

    Issuing costs a key and stays behind one: the ecosystem gets the read side,
    which is the half a relying party actually needs.
    """
    if capability_id == "receipt.verify@v1":
        return verify_receipt(VerifyRequest(document=payload.get("document") or {},
                                            signature=payload.get("signature") or {}))
    if capability_id == "passport.gate@v1":
        return knock_gate(str(payload.get("actor_id") or ""))
    return read_scope(str(payload.get("scope") or ""))

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


app = FastAPI(title="Attested Prove", version=VERSION, lifespan=lifespan,
              description="Receipts, agent passports, dual provenance and one-time anonymous claims.")
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
        "billing": "kova",
        "signing": "ed25519+ml-dsa-65" if cfg.pqc else "ed25519",
        "nullifier": "lsag-ed25519",
        "pinned_oracle_keys": len(ORACLE_KEYS),
    }


@app.get("/.well-known/attested-prove.json")
def well_known() -> dict[str, Any]:
    document = {
        "type": "attested.service/v1", "service": SERVICE, "version": VERSION,
        "origin": cfg.public_origin,
        "receipt_type": "attested.receipt/v1",
        "passport_type": "attested.passport/v1",
        "nullifier_algorithm": "lsag-ed25519",
        "pinned_oracle_keys": sorted(ORACLE_KEYS),
        "issued_at": now(),
    }
    return {**document, "signature": signer.sign(document)}


# ─────────────────────────────────  receipts  ────────────────────────────────

@app.post("/v1/receipts", status_code=201)
def issue_receipt(body: ReceiptRequest, request: Request) -> dict[str, Any]:
    """Sign an action into a document with a permanent public verification URL."""
    key = billing.active_key(request, scope="issuer")
    rate_limit(billing, request, "issue-receipt", 240)
    payload_digest = sha256_hex(canonical(body.payload)) if body.payload is not None else ""
    receipt_id = billing.ident(
        "receipt", f"{key['key_id']}:{body.subject_actor}:{body.action}:{body.resource}:{payload_digest}:{time.time_ns()}",
        "rcpt_")
    document = {
        "type": "attested.receipt/v1",
        "receipt_id": receipt_id,
        "issuer": cfg.public_origin,
        "subject": body.subject_actor,
        "action": body.action,
        "resource": body.resource,
        "payload_digest": payload_digest,
        "attributes": body.attributes or {},
        "issued_at": now(),
    }
    signature = signer.sign(document)
    db.execute(
        "INSERT INTO receipts (receipt_id, key_id, subject_actor, action, resource, digest, document, "
        "signature, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (receipt_id, key["key_id"], body.subject_actor, body.action, body.resource,
         sha256_hex(canonical(document)), canonical(document), canonical(signature), now()))
    return _public_receipt(db.one("SELECT * FROM receipts WHERE receipt_id=?", (receipt_id,)) or {})


def _public_receipt(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        raise HTTPException(404, "receipt not found")
    document = json.loads(str(row["document"]))
    signature = json.loads(str(row["signature"]))
    return {
        "receipt_id": row["receipt_id"],
        "subject": row["subject_actor"],
        "action": row["action"],
        "resource": row["resource"],
        "digest": row["digest"],
        "document": document,
        "signature": signature,
        "issuer_public_key": signature.get("public_key"),
        "verified": verify_signature(document, signature, signer.public_key),
        "created_at": row["created_at"],
        "verify_url": f"{cfg.public_origin}/verify/{row['receipt_id']}",
    }


@app.get("/v1/receipts/{receipt_id}")
def read_receipt(receipt_id: str) -> dict[str, Any]:
    return _public_receipt(db.one("SELECT * FROM receipts WHERE receipt_id=?", (receipt_id,)) or {})


@app.get("/v1/receipts")
def list_receipts(subject: str, limit: int = 50) -> dict[str, Any]:
    if not ACTOR_ID.fullmatch(subject):
        raise HTTPException(422, "subject must be a did:actor identity")
    rows = db.all(
        "SELECT receipt_id, action, resource, digest, created_at FROM receipts "
        "WHERE subject_actor=? ORDER BY created_at DESC LIMIT ?", (subject, max(1, min(limit, 200))))
    return {"subject": subject, "count": len(rows), "receipts": rows}


@app.post("/v1/receipts/verify")
def verify_receipt(body: VerifyRequest) -> dict[str, Any]:
    """Offline verification: no lookup, no key, works on a document you were handed."""
    valid = verify_signature(body.document, body.signature)
    ours = valid and body.signature.get("public_key") == signer.public_key
    return {
        "verified": valid,
        "issued_by_this_service": bool(ours),
        "public_key": body.signature.get("public_key"),
        "pq_present": bool(body.signature.get("pq_value")),
        "type": body.document.get("type"),
    }


@app.get("/verify/{receipt_id}", response_class=HTMLResponse, include_in_schema=False)
def verify_page(receipt_id: str) -> HTMLResponse:
    row = db.one("SELECT * FROM receipts WHERE receipt_id=?", (receipt_id,))
    if not row:
        return HTMLResponse("<!doctype html><meta charset=utf-8><title>Not found</title>"
                            "<body style='background:#05080d;color:#e7eef7;font:15px system-ui;padding:60px'>"
                            "<h1>No such receipt</h1><p>This identifier has never been issued here.</p>",
                            status_code=404)
    receipt = _public_receipt(row)
    template_path = os.path.join(WEB_ROOT, "verify.html") if WEB_ROOT else ""
    if not template_path or not os.path.isfile(template_path):
        # No page assets on this deployment — still answer with the verdict rather
        # than a 500, because /verify/{id} is a URL printed on other people's receipts.
        return HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>Receipt</title>"
            "<body style='background:#05080d;color:#e7eef7;font:15px system-ui;padding:60px'>"
            f"<h1>{'Signature verifies' if receipt['verified'] else 'Signature does NOT verify'}</h1>"
            f"<pre>{json.dumps(receipt, indent=2)}</pre>",
            status_code=200)
    template = open(template_path, encoding="utf-8").read()
    return HTMLResponse(template.replace("__RECEIPT__", json.dumps(receipt).replace("<", "\\u003c")))


# ──────────────────────────────── passports ──────────────────────────────────

def _reputation(actor_id: str) -> dict[str, Any]:
    """The slice a passport carries: derived from receipts, never asserted."""
    summary = db.one(
        "SELECT COUNT(*) AS receipts, MIN(created_at) AS first_seen, MAX(created_at) AS last_seen "
        "FROM receipts WHERE subject_actor=?", (actor_id,)) or {}
    actions = db.all(
        "SELECT action, COUNT(*) AS n FROM receipts WHERE subject_actor=? GROUP BY action "
        "ORDER BY n DESC LIMIT 10", (actor_id,))
    bindings = db.one(
        "SELECT COUNT(*) AS n FROM memory_bindings WHERE actor_id=?", (actor_id,)) or {}
    count = int(summary.get("receipts") or 0)
    first_seen = str(summary.get("first_seen") or "")
    age_days = 0
    if first_seen:
        try:
            age_days = int((time.time() - time.mktime(time.strptime(first_seen, "%Y-%m-%dT%H:%M:%SZ"))) // 86400)
        except ValueError:
            age_days = 0
    tier = "new"
    for name, min_receipts, min_days in TIERS:
        if count >= min_receipts and age_days >= min_days:
            tier = name
            break
    return {
        "receipts": count,
        "distinct_actions": len(actions),
        "top_actions": [{"action": row["action"], "count": int(row["n"])} for row in actions],
        "world_bindings": int(bindings.get("n") or 0),
        "first_seen": first_seen or None,
        "last_seen": summary.get("last_seen"),
        "age_days": age_days,
        "tier": tier,
    }


@app.post("/v1/passports", status_code=201)
def issue_passport(body: PassportRequest, request: Request) -> dict[str, Any]:
    key = billing.active_key(request, scope="issuer")
    rate_limit(billing, request, "issue-passport", 60)
    slice_ = _reputation(body.actor_id)
    passport_id = billing.ident("passport", f"{body.actor_id}:{time.time_ns()}", "pass_")
    expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + PASSPORT_DAYS * 86400))
    document = {
        "type": "attested.passport/v1",
        "passport_id": passport_id,
        "issuer": cfg.public_origin,
        "subject": body.actor_id,
        "audience": body.audience,
        "reputation": slice_,
        "issued_at": now(),
        "expires_at": expires_at,
    }
    signature = signer.sign(document)
    db.execute(
        "INSERT INTO passports (passport_id, actor_id, tier, document, signature, issued_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (passport_id, body.actor_id, slice_["tier"], canonical(document), canonical(signature),
         now(), expires_at))
    return {"passport_id": passport_id, "document": document, "signature": signature,
            "verify_url": f"{cfg.public_origin}/v1/passports/{passport_id}",
            "note": "a passport states what the receipts show; it never asserts anything else"}


@app.get("/v1/passports/{passport_id}")
def read_passport(passport_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM passports WHERE passport_id=?", (passport_id,))
    if not row:
        raise HTTPException(404, "passport not found")
    document = json.loads(str(row["document"]))
    signature = json.loads(str(row["signature"]))
    stamp = now()
    return {
        "passport_id": passport_id, "subject": row["actor_id"], "tier": row["tier"],
        "document": document, "signature": signature,
        "verified": verify_signature(document, signature, signer.public_key),
        "expired": str(row["expires_at"]) <= stamp,
        "revoked": bool(row["revoked_at"]),
        "valid": (not row["revoked_at"]) and str(row["expires_at"]) > stamp,
    }


@app.post("/v1/passports/{passport_id}/revoke")
def revoke_passport(passport_id: str, request: Request,
                    authorization: str | None = Header(default=None)) -> dict[str, Any]:
    try:
        billing.active_key(request, scope="issuer")
    except HTTPException:
        _admin(authorization)
    changed = db.execute(
        "UPDATE passports SET revoked_at=? WHERE passport_id=? AND revoked_at IS NULL", (now(), passport_id))
    if changed != 1:
        raise HTTPException(404, "passport not found or already revoked")
    return {"passport_id": passport_id, "revoked_at": now()}


@app.post("/v1/passports/verify")
def verify_passport(body: VerifyRequest) -> dict[str, Any]:
    """What a relying party actually calls: offline, keyless, expiry-aware."""
    valid = verify_signature(body.document, body.signature, signer.public_key)
    expires_at = str(body.document.get("expires_at", ""))
    fresh = bool(expires_at) and expires_at > now()
    passport_id = str(body.document.get("passport_id", ""))
    revoked = False
    if passport_id:
        row = db.one("SELECT revoked_at FROM passports WHERE passport_id=?", (passport_id,))
        revoked = bool(row and row["revoked_at"])
    return {
        "verified": valid, "fresh": fresh, "revoked": revoked,
        "accept": bool(valid and fresh and not revoked),
        "subject": body.document.get("subject"),
        "tier": (body.document.get("reputation") or {}).get("tier"),
        "expires_at": expires_at or None,
    }


@app.get("/v1/gate/{actor_id}")
def knock_gate(actor_id: str) -> dict[str, Any]:
    """The knock gate a hub, monitor or factory calls before letting an agent in.

    Free and keyless on purpose: the caller is asking about *someone else's*
    agent, and a gate that costs money is a gate nobody puts in front of anything.
    """
    if not ACTOR_ID.fullmatch(actor_id):
        raise HTTPException(422, "actor_id must be a did:actor identity")
    stamp = now()
    row = db.one(
        "SELECT * FROM passports WHERE actor_id=? AND revoked_at IS NULL AND expires_at > ? "
        "ORDER BY issued_at DESC LIMIT 1", (actor_id, stamp))
    slice_ = _reputation(actor_id)
    reasons = []
    if not row:
        reasons.append("no valid passport")
    if slice_["receipts"] < GATE_MIN_RECEIPTS:
        reasons.append(f"fewer than {GATE_MIN_RECEIPTS} receipts")
    return {
        "actor_id": actor_id,
        "allow": not reasons,
        "reasons": reasons,
        "tier": slice_["tier"],
        "receipts": slice_["receipts"],
        "passport_id": row["passport_id"] if row else None,
        "passport_expires_at": row["expires_at"] if row else None,
        "checked_at": stamp,
    }


# ─────────────────── dual provenance: world + memory ─────────────────────────

@app.post("/v1/world/attest", status_code=201)
def world_attest(body: WorldRequest, request: Request) -> dict[str, Any]:
    """Accept an oracle-signed observation of the physical world.

    The oracle key must be **pinned** in `PROVE_ORACLE_KEYS`. A self-asserted key
    in the signature block proves only that whoever wrote the document also wrote
    the signature — which is not a fact about the world.
    """
    billing.active_key(request, scope="issuer")
    public_key = str(body.signature.get("public_key", ""))
    if not ORACLE_KEYS:
        raise HTTPException(503, "PROVE_ORACLE_KEYS is not configured; no oracle can be trusted yet")
    if normalize_key(public_key) not in ORACLE_KEYS:
        raise HTTPException(403, "observation is not signed by a pinned oracle key")
    if not verify_signature(body.document, body.signature, public_key):
        raise HTTPException(403, "oracle signature does not verify")
    digest = sha256_hex(canonical(body.document))
    existing = db.one("SELECT * FROM world_attestations WHERE observation_digest=?", (digest,))
    if existing:
        return _public_attestation(existing)
    attestation_id = billing.ident("world", digest, "wrl_")
    db.execute(
        "INSERT INTO world_attestations (attestation_id, oracle_key, subject, observation_digest, "
        "document, signature, observed_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (attestation_id, public_key, body.subject, digest, canonical(body.document),
         canonical(body.signature), str(body.document.get("observed_at") or ""), now()))
    return _public_attestation(db.one("SELECT * FROM world_attestations WHERE attestation_id=?",
                                      (attestation_id,)) or {})


def _public_attestation(row: dict[str, Any]) -> dict[str, Any]:
    if not row:
        raise HTTPException(404, "attestation not found")
    document = json.loads(str(row["document"]))
    signature = json.loads(str(row["signature"]))
    return {
        "attestation_id": row["attestation_id"], "subject": row["subject"],
        "oracle_public_key": row["oracle_key"], "observation_digest": row["observation_digest"],
        "document": document, "signature": signature,
        "verified": verify_signature(document, signature, str(row["oracle_key"])),
        "observed_at": row["observed_at"] or None, "created_at": row["created_at"],
    }


@app.get("/v1/world/{attestation_id}")
def read_attestation(attestation_id: str) -> dict[str, Any]:
    return _public_attestation(
        db.one("SELECT * FROM world_attestations WHERE attestation_id=?", (attestation_id,)) or {})


@app.post("/v1/memory/bind", status_code=201)
def bind_memory(body: BindRequest, request: Request) -> dict[str, Any]:
    """Bind "the world said X" to "this agent decided Y" as one signed receipt."""
    key = billing.active_key(request, scope="issuer")
    actor = verified_actor(request)
    attestation = db.one("SELECT * FROM world_attestations WHERE attestation_id=?", (body.attestation_id,))
    if not attestation:
        raise HTTPException(404, "attestation not found")
    binding_id = billing.ident("binding", f"{body.attestation_id}:{body.memory_id}:{actor}", "bind_")
    existing = db.one("SELECT * FROM memory_bindings WHERE binding_id=?", (binding_id,))
    if existing:
        return {"binding_id": binding_id, "receipt": read_receipt(str(existing["receipt_id"])),
                "recovered": True}
    receipt_id = billing.ident("receipt", f"bind:{binding_id}", "rcpt_")
    document = {
        "type": "attested.receipt/v1",
        "receipt_id": receipt_id,
        "issuer": cfg.public_origin,
        "subject": actor,
        "action": "world.bind",
        "resource": body.memory_id,
        "payload_digest": sha256_hex(canonical({"decision": body.decision})),
        "attributes": {
            "binding_id": binding_id,
            "world_attestation_id": body.attestation_id,
            "world_observation_digest": attestation["observation_digest"],
            "world_oracle_public_key": attestation["oracle_key"],
            "world_subject": attestation["subject"],
            "decision": body.decision,
        },
        "issued_at": now(),
    }
    signature = signer.sign(document)
    db.execute(
        "INSERT INTO receipts (receipt_id, key_id, subject_actor, action, resource, digest, document, "
        "signature, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (receipt_id, key["key_id"], actor, "world.bind", body.memory_id,
         sha256_hex(canonical(document)), canonical(document), canonical(signature), now()))
    db.execute(
        "INSERT INTO memory_bindings (binding_id, attestation_id, memory_id, actor_id, decision, "
        "receipt_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (binding_id, body.attestation_id, body.memory_id, actor, body.decision, receipt_id, now()))
    return {"binding_id": binding_id, "receipt": read_receipt(receipt_id), "recovered": False}


# ─────────────────────────── nullifier claims (ZK) ───────────────────────────

@app.post("/v1/nullifiers/scopes", status_code=201)
def create_scope(body: ScopeRequest, request: Request) -> dict[str, Any]:
    key = billing.active_key(request, scope="privacy")
    inserted = db.execute(
        "INSERT INTO nullifier_scopes (scope, label, description, owner_key_id, open_registration, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (scope) DO NOTHING",
        (body.scope, body.label, body.description, key["key_id"],
         1 if body.open_registration else 0, now()))
    if inserted != 1:
        raise HTTPException(409, "that scope already exists")
    return _public_scope(body.scope)


def _public_scope(scope: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM nullifier_scopes WHERE scope=?", (scope,))
    if not row:
        raise HTTPException(404, "scope not found")
    members = db.all("SELECT public_key, label, registered_at FROM nullifier_members WHERE scope=? "
                     "ORDER BY registered_at", (scope,))
    spends = db.one("SELECT COUNT(*) AS n FROM nullifier_spends WHERE scope=?", (scope,)) or {}
    ring_size = len(members)
    return {
        "scope": row["scope"], "label": row["label"], "description": row["description"],
        "open_registration": bool(row["open_registration"]),
        "ring": [member["public_key"] for member in members],
        "ring_size": ring_size,
        "members": members,
        "spent": int(spends.get("n") or 0),
        "remaining": max(0, ring_size - int(spends.get("n") or 0)),
        "anonymity_set": ring_size,
        "privacy_note": ("a claim hides the signer among the whole ring; with a ring of "
                         f"{ring_size} the set is {ring_size}, and a ring of one hides nothing"),
        "created_at": row["created_at"],
    }


@app.get("/v1/nullifiers/scopes/{scope}")
def read_scope(scope: str) -> dict[str, Any]:
    """Public on purpose: a verifier must be able to rebuild the ring itself."""
    return _public_scope(scope)


@app.get("/v1/nullifiers/scopes")
def list_scopes() -> dict[str, Any]:
    rows = db.all("SELECT scope, label, description, open_registration, created_at "
                  "FROM nullifier_scopes ORDER BY created_at DESC LIMIT 200")
    for row in rows:
        size = db.one("SELECT COUNT(*) AS n FROM nullifier_members WHERE scope=?", (row["scope"],)) or {}
        row["ring_size"] = int(size.get("n") or 0)
        row["open_registration"] = bool(row["open_registration"])
    return {"count": len(rows), "scopes": rows}


@app.post("/v1/nullifiers/scopes/{scope}/members", status_code=201)
def register_member(scope: str, body: MemberRequest, request: Request) -> dict[str, Any]:
    row = db.one("SELECT * FROM nullifier_scopes WHERE scope=?", (scope,))
    if not row:
        raise HTTPException(404, "scope not found")
    if not row["open_registration"]:
        key = billing.active_key(request, scope="privacy")
        if str(row["owner_key_id"] or "") != str(key["key_id"]):
            raise HTTPException(403, "this scope is closed and belongs to another privacy key")
    else:
        rate_limit(billing, request, "register-member", 30)
    try:
        raw = bytes.fromhex(body.public_key)
    except ValueError:
        raise HTTPException(422, "public_key must be 32 bytes of hex") from None
    point = nz.decompress(raw)
    if point is None or not nz.in_prime_order_subgroup(point):
        raise HTTPException(422, "public_key is not a valid Ed25519 point in the prime-order subgroup")
    size = db.one("SELECT COUNT(*) AS n FROM nullifier_members WHERE scope=?", (scope,)) or {}
    if int(size.get("n") or 0) >= MAX_RING:
        raise HTTPException(409, f"this scope already holds the maximum ring size of {MAX_RING}")
    inserted = db.execute(
        "INSERT INTO nullifier_members (scope, public_key, label, registered_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (scope, public_key) DO NOTHING",
        (scope, body.public_key.lower(), body.label, now()))
    if inserted != 1:
        raise HTTPException(409, "this key is already registered for the scope")
    return _public_scope(scope)


@app.get("/v1/nullifiers/scopes/{scope}/challenge")
def claim_challenge(scope: str, claim: str) -> dict[str, Any]:
    """The exact bytes a claim must be signed over. Recomputed on submission."""
    _public_scope(scope)
    message = canonical({"scope": scope, "claim": claim})
    return {
        "scope": scope, "claim": claim, "message": message,
        "message_sha256": sha256_hex(message),
        "algorithm": "lsag-ed25519",
        "note": "sign these exact bytes with a ring signature over the scope's ring",
    }


@app.post("/v1/nullifiers/claim")
def spend_claim(body: ClaimRequest, request: Request) -> dict[str, Any]:
    """One claim per key per scope — anonymously, and free to submit.

    The proof carries its own ring, so it is checked twice: the signature must
    close, *and* every ring member must actually be registered for the scope.
    Skipping the second check would let anyone bring a ring of their own keys and
    prove membership of nothing.
    """
    rate_limit(billing, request, "claim", 60)
    proof = body.proof
    scope = str(proof.get("scope", ""))
    row = db.one("SELECT * FROM nullifier_scopes WHERE scope=?", (scope,))
    if not row:
        raise HTTPException(404, "scope not found")
    registered = {str(member["public_key"]).lower()
                  for member in db.all("SELECT public_key FROM nullifier_members WHERE scope=?", (scope,))}
    supplied_ring = proof.get("ring")
    if not isinstance(supplied_ring, list) or not 1 <= len(supplied_ring) <= MAX_RING:
        raise HTTPException(422, f"the proof needs a ring of 1-{MAX_RING} keys")
    ring = [str(item).lower() for item in supplied_ring]
    unknown = [item for item in ring if item not in registered]
    if unknown:
        raise HTTPException(403, "the proof's ring contains keys that are not registered for this scope")
    message = canonical({"scope": scope, "claim": body.claim}).encode()
    if not nz.verify(message, proof):
        raise HTTPException(403, "the ring signature does not verify for this claim")
    # Uniqueness belongs to the decoded group element. Hex case and whitespace
    # are alternate encodings of the same nullifier, not new spending rights.
    key_image = bytes.fromhex(str(proof["key_image"])).hex()
    inserted = db.execute(
        "INSERT INTO nullifier_spends (scope, key_image, claim, ring_size, created_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT (scope, key_image) DO NOTHING",
        (scope, key_image, body.claim, len(ring), now()))
    if inserted != 1:
        existing = db.one("SELECT * FROM nullifier_spends WHERE scope=? AND key_image=?", (scope, key_image))
        raise HTTPException(409, {
            "detail": "this nullifier has already been spent in this scope",
            "first_claim": (existing or {}).get("claim"),
            "first_spent_at": (existing or {}).get("created_at"),
        })
    return {
        "accepted": True, "scope": scope, "claim": body.claim,
        "key_image": key_image, "anonymity_set": len(ring),
        "spent_at": now(),
        "note": "the signer is one of the ring; which one is not recoverable from this record",
    }


@app.get("/v1/nullifiers/scopes/{scope}/spends")
def list_spends(scope: str, limit: int = 200) -> dict[str, Any]:
    _public_scope(scope)
    rows = db.all("SELECT key_image, claim, ring_size, created_at FROM nullifier_spends "
                  "WHERE scope=? ORDER BY created_at DESC LIMIT ?", (scope, max(1, min(limit, 500))))
    return {"scope": scope, "count": len(rows), "spends": rows}


# ────────────────────────── stats, admin, web ────────────────────────────────

@app.get("/v1/stats")
def stats() -> dict[str, Any]:
    receipts = db.one("SELECT COUNT(*) AS n, COUNT(DISTINCT subject_actor) AS actors FROM receipts") or {}
    passports = db.one(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN revoked_at IS NULL AND expires_at > ? THEN 1 ELSE 0 END) AS valid "
        "FROM passports", (now(),)) or {}
    return {
        "service": SERVICE, "generated_at": now(),
        "receipts": int(receipts.get("n") or 0),
        "subjects": int(receipts.get("actors") or 0),
        "passports": int(passports.get("n") or 0),
        "passports_valid": int(passports.get("valid") or 0),
        "world_attestations": int((db.one("SELECT COUNT(*) AS n FROM world_attestations") or {}).get("n") or 0),
        "memory_bindings": int((db.one("SELECT COUNT(*) AS n FROM memory_bindings") or {}).get("n") or 0),
        "nullifier_scopes": int((db.one("SELECT COUNT(*) AS n FROM nullifier_scopes") or {}).get("n") or 0),
        "nullifier_spends": int((db.one("SELECT COUNT(*) AS n FROM nullifier_spends") or {}).get("n") or 0),
        "signing": "ed25519+ml-dsa-65" if cfg.pqc else "ed25519",
    }


@app.get("/v1/admin/receipts")
def admin_receipts(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    _admin(authorization)
    rows = db.all("SELECT receipt_id, key_id, subject_actor, action, resource, created_at FROM receipts "
                  "ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 1000)),))
    return {"count": len(rows), "receipts": rows}


@app.get("/v1/admin/passports")
def admin_passports(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    _admin(authorization)
    rows = db.all("SELECT passport_id, actor_id, tier, issued_at, expires_at, revoked_at FROM passports "
                  "ORDER BY issued_at DESC LIMIT ?", (max(1, min(limit, 1000)),))
    stamp = now()
    for row in rows:
        row["valid"] = not row["revoked_at"] and str(row["expires_at"]) > stamp
    return {"count": len(rows), "passports": rows}


@app.get("/v1/admin/scopes")
def admin_scopes(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin(authorization)
    rows = db.all("SELECT scope, label, owner_key_id, open_registration, created_at FROM nullifier_scopes "
                  "ORDER BY created_at DESC LIMIT 500")
    for row in rows:
        size = db.one("SELECT COUNT(*) AS n FROM nullifier_members WHERE scope=?", (row["scope"],)) or {}
        spent = db.one("SELECT COUNT(*) AS n FROM nullifier_spends WHERE scope=?", (row["scope"],)) or {}
        row["ring_size"] = int(size.get("n") or 0)
        row["spent"] = int(spent.get("n") or 0)
        row["open_registration"] = bool(row["open_registration"])
    return {"count": len(rows), "scopes": rows}


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
