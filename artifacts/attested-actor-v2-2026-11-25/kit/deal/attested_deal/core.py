"""Shared runtime for the Attested SaaS services.

This module is *identical* in `attested-deal`, `attested-meter` and
`attested-prove`. Each product is an independent repository, so the runtime is
copied rather than imported across trees; `tests/test_core_parity.py` in every
product asserts the copies have not drifted.

It provides the four things every Attested SaaS surface needs and nothing else:

* configuration that fails closed under ``AIFACTORY_PROD``;
* a PostgreSQL/SQLite database wrapper with the shared billing schema;
* the KOVA USDC-on-Base checkout rail (payer-bound invoice -> issued API key);
* Ed25519 (optionally hybrid ML-DSA-65) signing over canonical JSON.

Money is stored as **integer micro-USD** everywhere. Floats never touch an
amount: a receipt signed over ``0.1 + 0.2`` is a receipt that fails to verify on
the other side of the wire.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from fastapi import APIRouter, Header, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_HASH = re.compile(r"^0x[0-9a-f]{64}$")
ORDER_ID = re.compile(r"^ord_[0-9a-f]{32}$")
ACTOR_ID = re.compile(r"^did:actor:[0-9a-f]{64}$")
MICRO = 1_000_000
logger = logging.getLogger(__name__)


# ─────────────────────────────── configuration ───────────────────────────────

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


@dataclass(frozen=True)
class Settings:
    service: str
    prefix: str
    database_url: str
    admin_token: str
    service_token: str
    kova_url: str
    kova_api_key: str
    payment_recipient: str
    public_origin: str
    key_derivation_secret: str
    signing_key_path: str
    pqc: bool
    reconcile_seconds: int
    key_reveal_hours: int
    hub_url: str
    extra: dict[str, str] = field(default_factory=dict)


def _prod() -> bool:
    """Fail CLOSED: production unless the operator says otherwise.

    Every gate here used to switch on ``AIFACTORY_PROD`` being SET, so a deployment that
    forgot the variable — or copied an ``.env.example`` carrying ``AIFACTORY_PROD=0`` —
    ran with no actor verification and no capability authentication, silently. Now an
    explicit ``AIFACTORY_PROD=1`` always wins, and only an explicit ``AIFACTORY_DEV=1``
    turns the checks off. Unset means production.
    """
    if os.getenv("AIFACTORY_PROD", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return os.getenv("AIFACTORY_DEV", "").strip().lower() not in {"1", "true", "yes"}


def is_weak_secret(value: str) -> bool:
    text = (value or "").strip()
    lowered = text.lower()
    if len(text) < 32:
        return True
    if lowered in {"change-me", "dev-secret", "dev-only-change-me"}:
        return True
    if lowered.startswith(("replace-with", "dev-")):
        return True
    return "change-me" in lowered


def load_settings(service: str, prefix: str, extra_keys: Sequence[str] = ()) -> Settings:
    def env(name: str, default: str = "") -> str:
        return os.getenv(f"{prefix}_{name}", default)

    value = Settings(
        service=service,
        prefix=prefix,
        database_url=env("DATABASE_URL") or os.getenv("DATABASE_URL", ""),
        admin_token=env("ADMIN_TOKEN", "change-me"),
        service_token=env("SERVICE_TOKEN", "change-me"),
        kova_url=(env("KOVA_URL") or os.getenv("KOVA_URL", "http://127.0.0.1:8789")).rstrip("/"),
        kova_api_key=env("KOVA_API_KEY") or os.getenv("KOVA_API_KEY", ""),
        payment_recipient=env("PAYMENT_RECIPIENT") or os.getenv("SAAS_PAYMENT_RECIPIENT", ""),
        public_origin=env("PUBLIC_ORIGIN", "http://127.0.0.1:9440").rstrip("/"),
        key_derivation_secret=env("KEY_DERIVATION_SECRET") or secrets.token_urlsafe(48),
        signing_key_path=env("SIGNING_KEY_PATH", f"./data/{service}.key"),
        pqc=env("PQC", "").strip().lower() in {"1", "true", "yes"},
        reconcile_seconds=max(5, min(int(env("RECONCILE_SECONDS", "15") or 15), 300)),
        key_reveal_hours=max(1, min(int(env("KEY_REVEAL_HOURS", "48") or 48), 168)),
        hub_url=(env("HUB_URL") or os.getenv("ATTESTED_HUB_URL", "")).rstrip("/"),
        extra={key: env(key) for key in extra_keys},
    )
    if _prod():
        for label, secret in (
            ("ADMIN_TOKEN", value.admin_token),
            ("SERVICE_TOKEN", value.service_token),
            ("KEY_DERIVATION_SECRET", value.key_derivation_secret),
        ):
            if is_weak_secret(secret):
                raise RuntimeError(f"{prefix}_{label} must be a random 32+ character secret")
        if hmac.compare_digest(value.admin_token, value.service_token):
            raise RuntimeError(f"{prefix}_ADMIN_TOKEN and {prefix}_SERVICE_TOKEN must differ")
        if not value.database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError(f"{prefix}_DATABASE_URL must be PostgreSQL in production")
        kova_key = value.kova_api_key.strip().lower()
        if not kova_key or kova_key in {"change-me", "dev-secret"} or kova_key.startswith("replace-with"):
            raise RuntimeError("KOVA_API_KEY is required in production")
        if not EVM_ADDRESS.fullmatch(value.payment_recipient):
            raise RuntimeError(f"{prefix}_PAYMENT_RECIPIENT must be a valid EVM address in production")
        if not value.public_origin.startswith("https://"):
            raise RuntimeError(f"{prefix}_PUBLIC_ORIGIN must be HTTPS in production")
    parsed = urlparse(value.kova_url)
    if parsed.username or parsed.password or not parsed.hostname:
        raise RuntimeError("KOVA_URL must be a URL without embedded credentials")
    return value


# ──────────────────────────────── primitives ─────────────────────────────────

def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def future(seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(payload: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace, no float amounts.

    Integers only for money — see the module docstring. A float anywhere in a
    signed document is rejected here rather than at the verifier, which is the
    only place where the two sides can still be made to agree.
    """
    def check(node: Any) -> None:
        if isinstance(node, float):
            raise HTTPException(422, "signed documents must not contain floating point numbers")
        if isinstance(node, dict):
            for item in node.values():
                check(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                check(item)

    check(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def micro_from_usd(value: str | int | Decimal) -> int:
    """'1.25' -> 1250000. Rejects anything finer than a micro-dollar."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(422, "invalid amount") from error
    if not number.is_finite() or number <= 0:
        raise HTTPException(422, "amount must be positive")
    scaled = number * MICRO
    if scaled != scaled.to_integral_value():
        raise HTTPException(422, "amount is finer than one micro-dollar")
    micro = int(scaled)
    if micro > 10**15:
        raise HTTPException(422, "amount is out of range")
    return micro


def usd_from_micro(micro: int) -> str:
    sign = "-" if micro < 0 else ""
    whole, fraction = divmod(abs(int(micro)), MICRO)
    return f"{sign}{whole}.{fraction:06d}"


def b64url(value: str, label: str) -> bytes:
    """Decode base64url **or** standard base64, padded or not.

    The family emits both: this service writes url-safe unpadded, while GAIA and
    several oracles publish standard base64 with `+`, `/` and `=`. A pinned key
    in the "wrong" alphabet does not raise — it simply never matches, and the
    attestation is refused forever with a message that blames the signer.
    """
    text = (value or "").strip()
    padded = text + "=" * (-len(text) % 4)
    for altchars in (b"-_", b"+/"):
        try:
            return base64.b64decode(padded, altchars=altchars, validate=True)
        except (ValueError, TypeError):
            continue
    raise HTTPException(422, f"invalid {label} encoding")


def normalize_key(value: str) -> str:
    """Canonical base64url-unpadded form, so two spellings of one key compare equal."""
    try:
        return b64url_encode(b64url(value, "key"))
    except HTTPException:
        return (value or "").strip()


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ───────────────────────────────── signing ───────────────────────────────────

class Signer:
    """Ed25519 always, ML-DSA-65 additively when ``pqc`` is on.

    The hybrid shape (``pq_algorithm`` / ``pq_public_key`` / ``pq_value`` over
    the *same* canonical string) matches ``aimarket_hub.signing`` so hubs and
    oracles in the family can verify what this service produces. The ML-DSA key
    is a FILE at ``<key_path>_mldsa`` — a seed environment variable does not
    cover it, so a service without a persistent volume gets a new PQ identity on
    every restart.
    """

    def __init__(self, key_path: str, pqc: bool = False):
        self.path = Path(key_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(self.path.read_text().strip()))
        else:
            self._key = Ed25519PrivateKey.generate()
            self.path.write_text(self._key.private_bytes_raw().hex())
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
        self.pqc = pqc
        self._pq: tuple[bytes, bytes] | None = None
        if pqc:
            self._pq = self._load_or_make_pq()

    def _load_or_make_pq(self) -> tuple[bytes, bytes]:
        try:
            from dilithium_py.ml_dsa import ML_DSA_65
        except ImportError as error:  # a signer ahead of its verifiers de-federates itself
            raise RuntimeError("PQC is enabled but dilithium-py is not installed") from error
        pq_path = Path(str(self.path) + "_mldsa")
        if pq_path.exists():
            public_hex, secret_hex = pq_path.read_text().split()
            return bytes.fromhex(public_hex), bytes.fromhex(secret_hex)
        public, secret = ML_DSA_65.keygen()
        pq_path.write_text(f"{public.hex()}\n{secret.hex()}")
        try:
            pq_path.chmod(0o600)
        except OSError:
            pass
        return public, secret

    @property
    def public_key(self) -> str:
        return b64url_encode(self._key.public_key().public_bytes_raw())

    def sign_text(self, message: str) -> dict[str, Any]:
        """Sign a raw canonical STRING, in **standard** base64.

        The AIMarket provider protocol signs a hand-built canonical string and
        encodes with `+`/`/`/`=`; this service's own documents sign canonical
        JSON and encode url-safe. Emitting the wrong alphabet here does not
        raise — the hub simply never verifies the manifest, and the provider
        quietly fails to federate. So the two are separate methods on purpose.
        """
        raw = message.encode()
        block: dict[str, Any] = {
            "algorithm": "ed25519",
            "public_key": base64.b64encode(self._key.public_key().public_bytes_raw()).decode(),
            "value": base64.b64encode(self._key.sign(raw)).decode(),
        }
        if self._pq is not None:
            from dilithium_py.ml_dsa import ML_DSA_65
            public, secret = self._pq
            block["pq_algorithm"] = "ml-dsa-65"
            block["pq_public_key"] = base64.b64encode(public).decode()
            block["pq_value"] = base64.b64encode(ML_DSA_65.sign(secret, raw)).decode()
        return block

    def sign(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = canonical(payload).encode()
        block: dict[str, Any] = {
            "algorithm": "ed25519",
            "public_key": self.public_key,
            "value": b64url_encode(self._key.sign(message)),
        }
        if self._pq is not None:
            from dilithium_py.ml_dsa import ML_DSA_65
            public, secret = self._pq
            block["pq_algorithm"] = "ml-dsa-65"
            block["pq_public_key"] = b64url_encode(public)
            block["pq_value"] = b64url_encode(ML_DSA_65.sign(secret, message))
        return block


def verify_signature(payload: dict[str, Any], block: dict[str, Any], pinned_public_key: str | None = None) -> bool:
    """Classic first, then PQ if present. Fail closed on a PQ value we cannot check."""
    advertised = str(block.get("public_key", ""))
    if pinned_public_key and not hmac.compare_digest(normalize_key(advertised),
                                                     normalize_key(pinned_public_key)):
        return False
    try:
        raw_key = b64url(advertised, "public key")
        raw_signature = b64url(str(block.get("value", "")), "signature")
    except HTTPException:
        return False
    if len(raw_key) != 32 or len(raw_signature) != 64:
        return False
    if _ed25519_small_order(raw_key) or _ed25519_small_order(raw_signature[:32]):
        return False
    message = canonical(payload).encode()
    try:
        Ed25519PublicKey.from_public_bytes(raw_key).verify(raw_signature, message)
    except (InvalidSignature, ValueError):
        return False
    if not block.get("pq_value"):
        return True
    if block.get("pq_algorithm") != "ml-dsa-65":
        return False
    try:
        from dilithium_py.ml_dsa import ML_DSA_65
    except ImportError:
        return False
    try:
        return bool(ML_DSA_65.verify(
            b64url(str(block.get("pq_public_key", "")), "pq public key"),
            message,
            b64url(str(block["pq_value"]), "pq signature"),
        ))
    except (HTTPException, ValueError):
        return False


def verified_actor(request: Request, *, now: float | None = None) -> str:
    """Verify a destination-bound v2 proof, never a reusable identity bearer."""
    from .actor_auth import verify_actor_request

    state = request.app.state
    return verify_actor_request(request, audience=state.actor_audience,
                                spend_nonce=state.spend_actor_nonce, now=now)


# ──────────────────────────────── database ───────────────────────────────────

BILLING_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS billing_orders (
        order_id TEXT PRIMARY KEY,
        checkout_token_hash TEXT NOT NULL,
        purpose TEXT NOT NULL,
        plan TEXT NOT NULL,
        ref TEXT,
        payer TEXT NOT NULL,
        amount_micro BIGINT NOT NULL,
        invoice_id TEXT UNIQUE NOT NULL,
        idempotency_hash TEXT UNIQUE NOT NULL,
        state TEXT NOT NULL DEFAULT 'pending',
        tx_hash TEXT,
        key_id TEXT,
        key_reveal_until TEXT,
        created_at TEXT NOT NULL,
        confirmed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS billing_keys (
        key_id TEXT PRIMARY KEY,
        key_hash TEXT UNIQUE NOT NULL,
        key_prefix TEXT NOT NULL,
        subject TEXT NOT NULL,
        plan TEXT NOT NULL,
        scope TEXT NOT NULL DEFAULT 'default',
        order_id TEXT,
        issued_at TEXT NOT NULL,
        expires_at TEXT,
        revoked_at TEXT,
        last_used_at TEXT,
        request_count BIGINT NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS billing_rate_limits (
        rate_key TEXT PRIMARY KEY,
        window_started BIGINT NOT NULL,
        hit_count BIGINT NOT NULL
    )
    """,
    "CREATE TABLE IF NOT EXISTS actor_proof_nonces_v2 (audience TEXT NOT NULL, actor_id TEXT NOT NULL, nonce TEXT NOT NULL, "
    "expires_at BIGINT NOT NULL, PRIMARY KEY (audience, actor_id, nonce))",
    "CREATE INDEX IF NOT EXISTS idx_actor_proof_expiry ON actor_proof_nonces_v2(expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_billing_orders_state ON billing_orders(state)",
    "CREATE INDEX IF NOT EXISTS idx_billing_keys_subject ON billing_keys(subject)",
)


class Database:
    def __init__(self, dsn: str, schema: Sequence[str] = ()):
        import sqlite3

        self.pg = None
        self.sqlite = None
        self.lock = threading.RLock()
        self._transaction_local = threading.local()
        if dsn.startswith(("postgresql://", "postgres://")):
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool

            self.pg = ConnectionPool(dsn, min_size=1, max_size=10, kwargs={"row_factory": dict_row})
        else:
            path = dsn.removeprefix("sqlite:///") if dsn else "./data/attested.sqlite3"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.sqlite = sqlite3.connect(path, check_same_thread=False)
            self.sqlite.row_factory = sqlite3.Row
            self.sqlite.execute("PRAGMA journal_mode=WAL")
            self.sqlite.execute("PRAGMA busy_timeout=5000")
        self.migrate(tuple(BILLING_SCHEMA) + tuple(schema))

    @property
    def is_postgres(self) -> bool:
        return self.pg is not None

    def sql(self, statement: str) -> str:
        return statement.replace("?", "%s") if self.is_postgres else statement

    def migrate(self, statements: Sequence[str]) -> None:
        with self.transaction() as conn:
            for statement in statements:
                conn.execute(statement)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        active = getattr(self._transaction_local, "connection", None)
        if active is not None:
            # Domain handlers call execute/one/all themselves. Keep those calls
            # on the outer transaction so confirmation and credit roll back together.
            yield active
            return
        if self.is_postgres:
            assert self.pg is not None
            with self.pg.connection() as connection:
                self._transaction_local.connection = connection
                try:
                    yield connection
                finally:
                    del self._transaction_local.connection
            return
        assert self.sqlite is not None
        with self.lock:
            try:
                self._transaction_local.connection = self.sqlite
                yield self.sqlite
                self.sqlite.commit()
            except Exception:
                self.sqlite.rollback()
                raise
            finally:
                del self._transaction_local.connection

    def execute(self, statement: str, params: tuple[Any, ...] = ()) -> int:
        with self.transaction() as conn:
            return int(conn.execute(self.sql(statement), params).rowcount)

    def one(self, statement: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.transaction() as conn:
            row = conn.execute(self.sql(statement), params).fetchone()
            return dict(row) if row else None

    def all(self, statement: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.transaction() as conn:
            return [dict(row) for row in conn.execute(self.sql(statement), params).fetchall()]

    def ping(self) -> None:
        with self.transaction() as conn:
            conn.execute("SELECT 1")

    def spend_actor_nonce(self, audience: str, actor_id: str, nonce: str, expires_at: int, current: int) -> bool:
        with self.transaction() as conn:
            conn.execute(self.sql("DELETE FROM actor_proof_nonces_v2 WHERE expires_at < ?"), (current,))
            return conn.execute(self.sql(
                "INSERT INTO actor_proof_nonces_v2 (audience, actor_id, nonce, expires_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (audience, actor_id, nonce) DO NOTHING"),
                (audience, actor_id, nonce, expires_at)).rowcount == 1

    def consume_rate_limit(self, rate_key: str, limit: int, window: int = 60) -> bool:
        bucket = int(time.time()) // window * window
        with self.transaction() as conn:
            conn.execute(self.sql(
                "INSERT INTO billing_rate_limits (rate_key, window_started, hit_count) VALUES (?, ?, 0) "
                "ON CONFLICT (rate_key) DO NOTHING"), (rate_key, bucket))
            row = conn.execute(self.sql(
                "SELECT window_started, hit_count FROM billing_rate_limits WHERE rate_key=?"), (rate_key,)).fetchone()
            started = int(row["window_started"]) if row else bucket
            hits = int(row["hit_count"]) if row else 0
            if started != bucket:
                started, hits = bucket, 0
            if hits >= limit:
                return False
            conn.execute(self.sql(
                "UPDATE billing_rate_limits SET window_started=?, hit_count=? WHERE rate_key=?"),
                (bucket, hits + 1, rate_key))
        return True


# ────────────────────────────── KOVA payment rail ────────────────────────────

class Kova:
    """The exact-amount USDC-on-Base rail shared by the whole Attested family.

    The service never sees a payer private key and never custodies funds. An
    invoice is bound to the **payer address** the buyer declares: KOVA watches
    finalized ``Transfer`` logs into the operator recipient and reports
    ``confirmed`` when that exact amount arrives from that address. It also
    refuses to open a second live invoice with the same payer, recipient and
    amount, which is what keeps two open quotes from being confused for each
    other. This class is the only place that talks to it.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = dict(kwargs.pop("headers", {}))
        headers["X-API-Key"] = self.settings.kova_api_key
        headers["User-Agent"] = f"{self.settings.service}/1"
        url = f"{self.settings.kova_url}{path}"
        for attempt in range(2):
            try:
                if self._client is not None:
                    response = self._client.request(method, url, headers=headers, timeout=15, **kwargs)
                else:
                    response = httpx.request(method, url, headers=headers, timeout=15, **kwargs)
                if response.status_code in {502, 503, 504} and attempt == 0:
                    time.sleep(0.25)
                    continue
                if response.status_code >= 500:
                    raise HTTPException(503, "payment adapter could not process request")
                if response.status_code >= 400:
                    # A 4xx from KOVA is the buyer's problem, and KOVA words it for
                    # buyers ("an active invoice already uses this payer, recipient
                    # and amount"). Swallowing that into a generic message leaves
                    # someone staring at a checkout with nothing to act on.
                    detail = "payment adapter could not process request"
                    try:
                        body = response.json()
                        if isinstance(body, dict) and isinstance(body.get("detail"), str):
                            detail = body["detail"][:200]
                    except ValueError:
                        pass
                    raise HTTPException(422, detail)
                return dict(response.json())
            except HTTPException:
                raise
            except httpx.HTTPError as error:
                if attempt == 0:
                    time.sleep(0.25)
                    continue
                raise HTTPException(503, "payment adapter unavailable") from error
        raise HTTPException(503, "payment adapter unavailable")

    def open_invoice(self, payer: str, amount_micro: int, idempotency: str) -> dict[str, Any]:
        if not EVM_ADDRESS.fullmatch(self.settings.payment_recipient):
            raise HTTPException(503, f"{self.settings.prefix}_PAYMENT_RECIPIENT is not configured")
        return self.request("POST", "/v1/invoices", headers={"Idempotency-Key": idempotency}, json={
            "payer": payer,
            "recipient": self.settings.payment_recipient,
            "amount_usdc": usd_from_micro(amount_micro),
            "expires_in_seconds": 3600,
        })

    def invoice(self, invoice_id: str, tx_hash: str | None = None) -> dict[str, Any]:
        params = {"tx_hash": tx_hash} if tx_hash else None
        return self.request("GET", f"/v1/invoices/{invoice_id}", params=params)


# ─────────────────────────────── billing plane ───────────────────────────────

@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price_usd: str
    period_days: int
    summary: str
    scope: str = "default"


class OrderRequest(BaseModel):
    plan: str = Field(min_length=1, max_length=80)
    payer: str = Field(min_length=42, max_length=42)


class ConfirmRequest(BaseModel):
    tx_hash: str = Field(min_length=66, max_length=66)


PaidHandler = Callable[[dict[str, Any], str], None]


class Billing:
    """Checkout, key issuance, reconciliation and the operator's admin views.

    ``purpose`` separates a plan subscription from a domain payment (funding a
    deal, staking a bond, topping a meter up). Domain code registers a handler
    per purpose and gets called exactly once, inside the same transaction that
    flips the order to ``confirmed`` — so a handler that raises leaves the order
    pending and the next reconciler pass retries it, rather than taking the
    buyer's money and forgetting why.
    """

    def __init__(self, settings: Settings, db: Database, kova: Kova, plans: Sequence[Plan]):
        self.settings = settings
        self.db = db
        self.kova = kova
        self.plans = {plan.code: plan for plan in plans}
        self.handlers: dict[str, PaidHandler] = {}
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None

    # -- derivation ----------------------------------------------------------
    def derive(self, label: str, context: str) -> bytes:
        return hmac.new(
            self.settings.key_derivation_secret.encode(),
            f"{label}:{context}".encode(),
            hashlib.sha256,
        ).digest()

    def token(self, label: str, context: str, prefix: str) -> str:
        return prefix + b64url_encode(self.derive(label, context))

    def ident(self, label: str, context: str, prefix: str) -> str:
        return prefix + self.derive(label, context).hex()[:32]

    def checkout_token(self, idempotency_hash: str) -> str:
        return self.token("checkout", idempotency_hash, "chk_")

    def api_key(self, order_id: str) -> str:
        return self.token("api-key", order_id, "atk_")

    # -- orders --------------------------------------------------------------
    def open_order(
        self,
        *,
        purpose: str,
        plan: str,
        payer: str,
        amount_micro: int,
        idempotency: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        if not EVM_ADDRESS.fullmatch(payer):
            raise HTTPException(422, "payer must be a valid EVM address")
        if len(idempotency) < 16 or len(idempotency) > 200:
            raise HTTPException(400, "Idempotency-Key header is required (16-200 characters)")
        idempotency_hash = sha256_hex(f"{self.settings.service}:{idempotency}")
        token = self.checkout_token(idempotency_hash)
        existing = self.db.one("SELECT * FROM billing_orders WHERE idempotency_hash=?", (idempotency_hash,))
        if existing:
            if (existing["plan"] != plan or existing["payer"] != payer.lower()
                    or int(existing["amount_micro"]) != amount_micro
                    or existing["purpose"] != purpose or existing["ref"] != ref):
                raise HTTPException(409, "this Idempotency-Key belongs to a different checkout")
            return self.checkout(existing, token, self.kova.invoice(existing["invoice_id"]), recovered=True)
        # The adapter is shared by all three products. Its idempotency key must
        # have the same service boundary as our own checkout key.
        invoice = self.kova.open_invoice(payer, amount_micro, idempotency_hash)
        invoice_id = str(invoice.get("invoice_id", "")).strip()
        if not invoice_id:
            raise HTTPException(503, "payment adapter returned no invoice")
        clash = self.db.one("SELECT * FROM billing_orders WHERE invoice_id=?", (invoice_id,))
        if clash:
            if (clash["idempotency_hash"] != idempotency_hash or clash["purpose"] != purpose
                    or clash["ref"] != ref or clash["plan"] != plan or clash["payer"] != payer.lower()
                    or int(clash["amount_micro"]) != amount_micro):
                raise HTTPException(409, "payment invoice already belongs to a different checkout")
            return self.checkout(clash, token, invoice, recovered=True)
        order_id = self.ident("order", idempotency_hash, "ord_")
        try:
            self.db.execute(
                "INSERT INTO billing_orders (order_id, checkout_token_hash, purpose, plan, ref, payer, "
                "amount_micro, invoice_id, idempotency_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, sha256_hex(token), purpose, plan, ref, payer.lower(),
                 amount_micro, invoice_id, idempotency_hash, now()),
            )
        except Exception:
            raced = self.db.one("SELECT * FROM billing_orders WHERE idempotency_hash=?", (idempotency_hash,))
            if not raced:
                raise
            if (raced["purpose"] != purpose or raced["ref"] != ref or raced["plan"] != plan
                    or raced["payer"] != payer.lower() or int(raced["amount_micro"]) != amount_micro):
                raise HTTPException(409, "this Idempotency-Key belongs to a different checkout")
            return self.checkout(raced, token, invoice, recovered=True)
        row = self.db.one("SELECT * FROM billing_orders WHERE order_id=?", (order_id,)) or {}
        return self.checkout(row, token, invoice)

    def checkout(self, row: dict[str, Any], token: str, invoice: dict[str, Any], recovered: bool = False) -> dict[str, Any]:
        recipient = invoice.get("recipient") or invoice.get("pay_to") or self.settings.payment_recipient
        token_address = invoice.get("token_address", "")
        amount_raw = invoice.get("amount_raw", "")
        response = {
            "order_id": row["order_id"],
            "checkout_token": token,
            "state": row.get("state", "pending"),
            "purpose": row.get("purpose"),
            "plan": row.get("plan"),
            "ref": row.get("ref"),
            "invoice_id": row.get("invoice_id"),
            "amount_usdc": invoice.get("amount_usdc", usd_from_micro(int(row.get("amount_micro", 0)))),
            "amount_raw": amount_raw,
            "pay_to": recipient,
            "token_address": token_address,
            "chain": "base",
            "chain_id": 8453,
            "expires_at": invoice.get("expires_at"),
            "required_confirmations": invoice.get("required_confirmations"),
            "recovered": recovered,
        }
        if token_address and recipient and amount_raw:
            response["eip681"] = f"ethereum:{token_address}@8453/transfer?address={recipient}&uint256={amount_raw}"
        return response

    def owned_order(self, order_id: str, request: Request) -> dict[str, Any]:
        if not ORDER_ID.fullmatch(order_id):
            raise HTTPException(404, "order not found")
        token = request.headers.get("x-checkout-token", "")
        if len(token) < 32:
            raise HTTPException(401, "checkout token required")
        row = self.db.one("SELECT * FROM billing_orders WHERE order_id=?", (order_id,))
        if not row or not hmac.compare_digest(str(row["checkout_token_hash"]), sha256_hex(token)):
            raise HTTPException(404, "order not found")
        return row

    def settle(self, row: dict[str, Any], tx_hash: str | None = None) -> dict[str, Any]:
        """Ask KOVA about a pending order and apply the outcome exactly once."""
        if row["state"] != "pending":
            return row
        invoice = self.kova.invoice(str(row["invoice_id"]), tx_hash)
        state = str(invoice.get("state", ""))
        if state == "confirmed" and invoice.get("tx_hash"):
            self.apply_payment(str(row["order_id"]), str(invoice["tx_hash"]).lower())
        elif state in {"expired", "cancelled"}:
            self.db.execute(
                "UPDATE billing_orders SET state=? WHERE order_id=? AND state='pending'",
                (state, row["order_id"]),
            )
        return self.db.one("SELECT * FROM billing_orders WHERE order_id=?", (row["order_id"],)) or row

    def apply_payment(self, order_id: str, tx_hash: str) -> dict[str, Any] | None:
        """Flip pending -> confirmed once, then run the purpose handler.

        The state flip is the lock: a second caller (the reconciler racing a
        buyer's poll) updates zero rows and returns without re-crediting.
        """
        with self.db.transaction():
            return self._apply_payment(order_id, tx_hash)

    def _apply_payment(self, order_id: str, tx_hash: str) -> dict[str, Any] | None:
        if not TX_HASH.fullmatch(tx_hash):
            raise HTTPException(422, "invalid transaction hash")
        row = self.db.one("SELECT * FROM billing_orders WHERE order_id=?", (order_id,))
        if not row:
            return None
        plan = self.plans.get(str(row["plan"]))
        key_id = self.ident("key", order_id, "key_") if plan else None
        reveal_until = future(self.settings.key_reveal_hours * 3600)
        changed = self.db.execute(
            "UPDATE billing_orders SET state='confirmed', tx_hash=?, confirmed_at=?, key_id=?, key_reveal_until=? "
            "WHERE order_id=? AND state='pending'",
            (tx_hash, now(), key_id, reveal_until, order_id),
        )
        if changed != 1:
            return self.db.one("SELECT * FROM billing_orders WHERE order_id=?", (order_id,))
        if plan is not None:
            self.db.execute(
                "INSERT INTO billing_keys (key_id, key_hash, key_prefix, subject, plan, scope, order_id, issued_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (key_id) DO NOTHING",
                (key_id, sha256_hex(self.api_key(order_id)), self.api_key(order_id)[:12],
                 str(row["payer"]), plan.code, plan.scope, order_id, now(),
                 future(plan.period_days * 86400)),
            )
        handler = self.handlers.get(str(row["purpose"]))
        if handler is not None:
            handler(dict(row), tx_hash)
        return self.db.one("SELECT * FROM billing_orders WHERE order_id=?", (order_id,))

    def public_order(self, row: dict[str, Any]) -> dict[str, Any]:
        response = {
            key: row.get(key)
            for key in ("order_id", "purpose", "plan", "ref", "payer", "invoice_id",
                        "state", "tx_hash", "key_id", "created_at", "confirmed_at")
        }
        response["amount_usdc"] = usd_from_micro(int(row.get("amount_micro", 0)))
        if row.get("state") == "confirmed" and str(row.get("key_reveal_until") or "") >= now() and row.get("key_id"):
            raw = self.api_key(str(row["order_id"]))
            stored = self.db.one("SELECT * FROM billing_keys WHERE key_hash=?", (sha256_hex(raw),))
            if stored and not stored["revoked_at"]:
                response["api_key"] = raw
                response["key_reveal_until"] = row["key_reveal_until"]
                response["warning"] = "store this API key securely; recovery closes after the reveal window"
        return response

    # -- keys ----------------------------------------------------------------
    def key_row(self, raw_key: str) -> dict[str, Any] | None:
        return self.db.one("SELECT * FROM billing_keys WHERE key_hash=?", (sha256_hex(raw_key),))

    def active_key(self, request: Request, scope: str | None = None) -> dict[str, Any]:
        raw = request.headers.get("x-api-key", "") or request.headers.get("x-attested-key", "")
        if len(raw) < 40:
            raise HTTPException(401, "API key required")
        row = self.key_row(raw)
        if not row or row["revoked_at"] or (row["expires_at"] and str(row["expires_at"]) <= now()):
            raise HTTPException(401, "API key is invalid or expired")
        if scope and str(row["scope"]) != scope:
            raise HTTPException(403, "API key is not valid for this scope")
        self.db.execute(
            "UPDATE billing_keys SET last_used_at=?, request_count=request_count+1 WHERE key_id=?",
            (now(), row["key_id"]),
        )
        return row

    # -- reconciler ----------------------------------------------------------
    def start(self) -> None:
        self._stop.clear()
        self._worker = threading.Thread(target=self._reconcile, name="attested-reconciler", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=1)

    def _reconcile(self) -> None:
        while not self._stop.wait(self.settings.reconcile_seconds):
            try:
                pending = self.db.all(
                    "SELECT * FROM billing_orders WHERE state='pending' ORDER BY created_at LIMIT 100")
            except Exception:
                continue
            for row in pending:
                try:
                    self.settle(row)
                except Exception:
                    continue

    # -- routers -------------------------------------------------------------
    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/v1/plans")
        def plans() -> dict[str, Any]:
            return {"plans": [
                {"code": plan.code, "name": plan.name, "price_usd": plan.price_usd,
                 "period_days": plan.period_days, "summary": plan.summary, "scope": plan.scope}
                for plan in self.plans.values()
            ], "currency": "USDC", "chain": "base", "chain_id": 8453}

        @router.post("/v1/billing/orders")
        def create_order(body: OrderRequest, request: Request) -> dict[str, Any]:
            rate_limit(self, request, "create-order", 12)
            plan = self.plans.get(body.plan)
            if plan is None:
                raise HTTPException(422, "unknown plan")
            return self.open_order(
                purpose="plan",
                plan=plan.code,
                payer=body.payer,
                amount_micro=micro_from_usd(plan.price_usd),
                idempotency=request.headers.get("idempotency-key", "").strip(),
            )

        @router.get("/v1/billing/orders/{order_id}")
        def read_order(order_id: str, request: Request) -> dict[str, Any]:
            rate_limit(self, request, "order-status", 30)
            return self.public_order(self.settle(self.owned_order(order_id, request)))

        @router.post("/v1/billing/orders/{order_id}/confirm")
        def confirm(order_id: str, body: ConfirmRequest, request: Request) -> dict[str, Any]:
            rate_limit(self, request, "confirm-order", 30)
            row = self.owned_order(order_id, request)
            return self.public_order(self.settle(row, body.tx_hash.lower()))

        @router.get("/v1/keys/me")
        def key_me(request: Request) -> dict[str, Any]:
            row = self.active_key(request)
            return {key: row[key] for key in ("key_id", "key_prefix", "subject", "plan", "scope",
                                              "issued_at", "expires_at", "request_count")}

        return router

    def admin_router(self) -> APIRouter:
        router = APIRouter()

        def guard(authorization: str | None) -> None:
            token = (authorization or "").removeprefix("Bearer ").strip()
            if not token or not hmac.compare_digest(token, self.settings.admin_token):
                raise HTTPException(401, "operator authentication required")

        @router.get("/v1/admin/overview")
        def overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
            guard(authorization)
            return {"service": self.settings.service, **self.overview()}

        @router.get("/v1/admin/orders")
        def orders(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
            guard(authorization)
            rows = self.db.all(
                "SELECT order_id, purpose, plan, ref, payer, amount_micro, state, tx_hash, key_id, "
                "created_at, confirmed_at FROM billing_orders ORDER BY created_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),))
            for row in rows:
                row["amount_usdc"] = usd_from_micro(int(row.pop("amount_micro")))
            return {"count": len(rows), "orders": rows}

        @router.get("/v1/admin/keys")
        def keys(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
            guard(authorization)
            rows = self.db.all(
                "SELECT key_id, key_prefix, subject, plan, scope, order_id, issued_at, expires_at, "
                "revoked_at, last_used_at, request_count FROM billing_keys ORDER BY issued_at DESC LIMIT ?",
                (max(1, min(limit, 1000)),))
            stamp = now()
            for row in rows:
                row["active"] = not row["revoked_at"] and (not row["expires_at"] or str(row["expires_at"]) > stamp)
            return {"count": len(rows), "keys": rows}

        @router.post("/v1/admin/keys/{key_id}/revoke")
        def revoke(key_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
            guard(authorization)
            changed = self.db.execute(
                "UPDATE billing_keys SET revoked_at=? WHERE key_id=? AND revoked_at IS NULL", (now(), key_id))
            if changed != 1:
                raise HTTPException(404, "key not found or already revoked")
            return {"key_id": key_id, "revoked_at": now()}

        return router

    def overview(self) -> dict[str, Any]:
        stamp = now()
        states = self.db.all("SELECT state, COUNT(*) AS n FROM billing_orders GROUP BY state")
        revenue = self.db.one(
            "SELECT COALESCE(SUM(amount_micro),0) AS micro, COUNT(*) AS n FROM billing_orders WHERE state='confirmed'")
        keys = self.db.one(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN revoked_at IS NULL AND (expires_at IS NULL OR expires_at > ?) THEN 1 ELSE 0 END) AS active, "
            "COALESCE(SUM(request_count),0) AS requests FROM billing_keys", (stamp,)) or {}
        recent = self.db.all(
            "SELECT order_id, purpose, plan, ref, payer, amount_micro, state, created_at, confirmed_at "
            "FROM billing_orders ORDER BY created_at DESC LIMIT 10")
        for row in recent:
            row["amount_usdc"] = usd_from_micro(int(row.pop("amount_micro")))
        return {
            "generated_at": stamp,
            "orders_by_state": {str(row["state"]): int(row["n"]) for row in states},
            "settled_orders": int((revenue or {}).get("n") or 0),
            "settled_usdc": usd_from_micro(int((revenue or {}).get("micro") or 0)),
            "keys_total": int(keys.get("total") or 0),
            "keys_active": int(keys.get("active") or 0),
            "key_requests": int(keys.get("requests") or 0),
            "recent_orders": recent,
        }


def client_ip(request: Request) -> str:
    """The address the abuse buckets key on — the hop OUR proxy saw, not the caller's claim.

    This read ``split(",")[0]``: the LEFT-most X-Forwarded-For entry. nginx sets the header
    with ``$proxy_add_x_forwarded_for``, which APPENDS the real peer to whatever the client
    sent, so the left-most value was attacker-typed and every request could name a fresh
    address and get a fresh, empty rate-limit bucket. The right-most hop is the one nginx
    itself observed and cannot be forged from outside; with no header at all (direct
    peer) the socket address stands.
    """
    source = request.client.host if request.client else "unknown"
    try:
        peer = ipaddress.ip_address(source.split("%")[0])
        from_proxy = peer.is_loopback or peer.is_private or peer.is_link_local
    except ValueError:
        from_proxy = False
    # Only our own proxy's header counts: a caller that reaches the port directly writes a
    # one-hop X-Forwarded-For itself, and its right-most entry is then its own invention.
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()] if from_proxy else []
    if hops:
        try:
            source = str(ipaddress.ip_address(hops[-1]))
        except ValueError:
            pass
    return source[:128]


def rate_limit(billing: Billing, request: Request, bucket: str, limit: int) -> None:
    if not billing.db.consume_rate_limit(f"{bucket}:{client_ip(request)}", limit):
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})


# ─────────────────────── AIMarket provider surface ───────────────────────────

@dataclass(frozen=True)
class Capability:
    """One entry in the ecosystem's supply side.

    `price_usd` is a float because the AIMarket provider protocol says so. That
    is the family's contract, not this service's: everything *this* service signs
    stays integer micro-USD, and `canonical()` still refuses a float.
    """

    product_id: str
    capability_id: str
    name: str
    description: str
    price_usd: float
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


OBJECT_OUTPUT: dict[str, Any] = {"type": "object", "additionalProperties": True}


# Retry a failed publish after 1, 5, 15, 30 minutes, then hourly; re-publish every 6 h.
PUBLISH_RETRY_SECONDS = (60.0, 300.0, 900.0, 1800.0, 3600.0)
PUBLISH_REFRESH_SECONDS = 6 * 3600.0


class AIMarket:
    """Publishes this service as a provider the hub — and the monitor — can see.

    A service that does not publish a manifest is invisible to the ecosystem no
    matter how healthy it is: the monitor draws what the hub's signed declaration
    contains, nothing else. Registration is best-effort and never blocks startup;
    a hub that is down means the provider is missing from the map, not that the
    product stops taking money.
    """

    def __init__(self, settings: Settings, signer: Signer, capabilities: Sequence[Capability],
                 name: str, description: str, invoke_base: str, publisher_id: str):
        self.settings = settings
        self.signer = signer
        self.capabilities = tuple(capabilities)
        self.by_id = {item.capability_id: item for item in self.capabilities}
        self.name = name
        self.description = description
        self.invoke_base = invoke_base.rstrip("/")
        self.publisher_id = publisher_id

    def discovery_card(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "protocol_versions": ["v2"],
            "hub_version": "provider-0.2.0",
            "manifest_url": f"{self.settings.public_origin}/ai-market/v2/manifest",
            "products_count": len(self.capabilities),
            "capabilities_count": len(self.capabilities),
            "categories": sorted({item.category for item in self.capabilities}),
            "signer_public_key": base64.b64encode(
                self.signer._key.public_key().public_bytes_raw()).decode(),
        }

    def tool(self, capability: Capability) -> dict[str, Any]:
        return {
            "product_id": capability.product_id,
            "capability_id": capability.capability_id,
            "name": capability.name,
            "version": "v1",
            "description": capability.description,
            "invoke_url": f"{self.invoke_base}/capabilities/{capability.product_id}/{capability.capability_id}/invoke",
            "price_per_call_usd": capability.price_usd,
            "publisher": self.publisher_id,
            "publisher_id": self.publisher_id,
            "provider_pubkey": base64.b64encode(
                self.signer._key.public_key().public_bytes_raw()).decode(),
            "input_schema": capability.input_schema,
            "output_schema": capability.output_schema,
            "category": capability.category,
            "p50_latency_ms": 45,
            "success_rate_30d": 0.99,
        }

    def signed_manifest(self) -> dict[str, Any]:
        generated_at = now()
        tools = [self.tool(item) for item in self.capabilities]
        payload: dict[str, Any] = {
            "protocol_version": "v2",
            "generated_at": generated_at,
            "base_url": self.invoke_base,
            "products_count": len(tools),
            "capabilities_count": len(tools),
            "tools": tools,
        }
        tools_hash = hashlib.sha256(
            json.dumps(tools, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        by_hub_hash = hashlib.sha256(b"{}").hexdigest()
        # Byte-for-byte the family's canonical string. It is not JSON and not
        # sorted-by-accident: a verifier reproduces exactly this or nothing.
        line = (f"capabilities_count:{len(tools)}|generated_at:{generated_at}"
                f"|protocol_version:v2|tools_hash:{tools_hash}|by_hub_hash:{by_hub_hash}")
        payload["signature"] = self.signer.sign_text(line)
        return payload

    def capability_guard(self, request: Request) -> None:
        """Only the hub invokes capabilities, and only in production is it checked.

        Mirrors `require_capability_access` in the hub's own providers: outside
        production the gate is open so a developer can drive it by hand.
        """
        if not _prod():
            return
        expected = self.settings.extra.get("CAPABILITY_TOKEN", "") or os.getenv(
            "AIMARKET_CAPABILITY_TOKEN", "")
        supplied = request.headers.get("x-aimarket-internal-token", "")
        if len(expected) < 32 or not supplied or not hmac.compare_digest(expected, supplied):
            raise HTTPException(401, "capability gateway authentication required")

    def router(self, dispatch: Callable[[str, dict[str, Any], Request], Any]) -> APIRouter:
        router = APIRouter()

        @router.get("/.well-known/ai-market.json")
        def discovery() -> dict[str, Any]:
            return self.discovery_card()

        @router.get("/ai-market/v2/manifest")
        def manifest() -> dict[str, Any]:
            return self.signed_manifest()

        @router.post("/capabilities/{product_id}/{capability_id}/invoke")
        def invoke(product_id: str, capability_id: str, body: dict[str, Any],
                   request: Request, response: Response) -> dict[str, Any]:
            self.capability_guard(request)
            capability = self.by_id.get(capability_id)
            if capability is None or capability.product_id != product_id:
                raise HTTPException(404, "unknown capability")
            payload = body.get("input", body)
            if not isinstance(payload, dict):
                raise HTTPException(422, "input must be an object")
            result = jsonable_encoder(dispatch(capability_id, payload, request))
            # The Hub's existing request-bound provider protocol: sign the exact
            # JSON result and bind it to the requested product/capability/input.
            input_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            bound = json.dumps({
                "capability_id": capability_id,
                "product_id": product_id,
                "input_sha256": hashlib.sha256(input_json.encode("utf-8")).hexdigest(),
                "result": result,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            response.headers["X-Provider-Signature"] = self.signer.sign_text(bound)["value"]
            return {"result": result}

        return router

    def register(self) -> int:
        """Publish every capability to the hub. Best effort, never fatal — but LOUD.

        A swallowed failure here is the worst kind: the service is healthy, the
        landing works, money still flows, and the product is simply absent from
        the ecosystem map with nothing anywhere saying why. So every outcome is
        logged, including the two "nothing to do" cases.
        """
        hub, token = self._publish_config()
        if not hub:
            logger.warning("%s: no hub URL configured — this provider will not appear on the map",
                           self.settings.service)
            return 0
        if not token:
            logger.warning("%s: no publisher token configured — the hub keys credentials by "
                           "publisher id, so %s needs its own", self.settings.service, self.publisher_id)
            return 0
        published = 0
        for capability in self.capabilities:
            try:
                response = httpx.post(f"{hub}/ai-market/v2/supply/register",
                                      json=self.tool(capability),
                                      headers={"Authorization": f"Bearer {token}"}, timeout=8)
                if response.status_code >= 400:
                    logger.warning("%s: hub refused %s with %s: %s", self.settings.service,
                                   capability.capability_id, response.status_code,
                                   response.text[:200])
                    continue
                published += 1
            except httpx.HTTPError as error:
                logger.warning("%s: could not publish %s: %s", self.settings.service,
                               capability.capability_id, error)
        logger.info("%s: published %d/%d capabilities to %s as %s", self.settings.service,
                    published, len(self.capabilities), hub, self.publisher_id)
        return published

    def _publish_config(self) -> tuple[str, str]:
        hub = (self.settings.extra.get("AIMARKET_HUB_URL") or os.getenv("AIMARKET_HUB_URL", "")).rstrip("/")
        token = self.settings.extra.get("PUBLISHER_TOKEN") or os.getenv("AIMARKET_PUBLISHER_TOKEN", "")
        return hub, token

    def keep_registered(self, stop: threading.Event,
                        retry: Sequence[float] = PUBLISH_RETRY_SECONDS,
                        refresh: float = PUBLISH_REFRESH_SECONDS) -> None:
        """register(), for the life of the process — not once at startup.

        Once was not enough. A hub that was down or restarting at that moment, or that
        did not yet hold this publisher's credential, left the listing frozen until
        somebody restarted the service, and nothing but one log line said so. A partial
        or failed publish is retried on a widening schedule (the last step repeats); a
        complete one is repeated every `refresh` seconds so the hub's copy never lags the
        code. The credential itself is kept in step on the host by
        deploy/reconcile_publishers.sh; this makes the listing follow without anyone.
        A service with no hub or no token configured says so once and stops — retrying a
        missing setting only repeats the warning.
        """
        hub, token = self._publish_config()
        if not hub or not token:
            self.register()
            return
        failures = 0
        while not stop.is_set():
            if self.register() == len(self.capabilities):
                failures, wait = 0, refresh
            else:
                wait = retry[min(failures, len(retry) - 1)]
                failures += 1
            stop.wait(wait)

    def start_publishing(self) -> threading.Event:
        """keep_registered() on a daemon thread; set the returned event to stop it."""
        stop = threading.Event()
        threading.Thread(target=self.keep_registered, args=(stop,), name="aimarket-register",
                         daemon=True).start()
        return stop
