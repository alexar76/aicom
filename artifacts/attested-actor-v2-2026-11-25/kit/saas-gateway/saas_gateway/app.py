from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field


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


def production_mode() -> bool:
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


EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
ORDER_ID = re.compile(r"^saas_[0-9a-f]{32}$")
PLANS = {
    "personal.pro.monthly": {"product": "personal", "name": "Personal Pro", "price": "12.00", "period_days": 30},
    "team.standard.monthly": {"product": "team", "name": "Team Standard", "price": "49.00", "period_days": 30},
    "expert.query": {"product": "expert-market", "name": "Expert query", "price": "0.50", "period_days": 1},
    "expert.pass.7d": {"product": "expert-market", "name": "Expert 7-day pass", "price": "29.00", "period_days": 7},
}
TRIALS = {
    "personal": {"plan": "personal.trial.7d", "name": "Personal Trial", "period_days": 7},
    "team": {"plan": "team.trial.14d", "name": "Team Trial", "period_days": 14},
    "expert-market": {"plan": "expert.trial.1d", "name": "Expert Market Trial", "period_days": 1},
}


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_key: str
    kova_url: str
    kova_api_key: str
    public_origin: str
    payment_recipient: str
    team_auth_secret: str
    edge_token: str
    key_derivation_secret: str
    reconcile_seconds: int
    key_reveal_hours: int


def settings() -> Settings:
    value = Settings(
        database_url=os.getenv("SAAS_GATEWAY_DATABASE_URL") or os.getenv("DATABASE_URL", ""),
        api_key=os.getenv("SAAS_GATEWAY_API_KEY", "change-me"),
        kova_url=os.getenv("KOVA_URL", "http://localhost:8789").rstrip("/"),
        kova_api_key=os.getenv("KOVA_API_KEY", ""),
        public_origin=os.getenv("SAAS_PUBLIC_ORIGIN", "http://localhost:9400").rstrip("/"),
        payment_recipient=os.getenv("SAAS_PAYMENT_RECIPIENT", ""),
        team_auth_secret=os.getenv("SAAS_TEAM_AUTH_SECRET", ""),
        edge_token=os.getenv("SAAS_EDGE_TOKEN", ""),
        key_derivation_secret=os.getenv("SAAS_KEY_DERIVATION_SECRET") or secrets.token_urlsafe(48),
        reconcile_seconds=max(5, min(int(os.getenv("SAAS_RECONCILE_SECONDS", "15")), 300)),
        key_reveal_hours=max(1, min(int(os.getenv("SAAS_KEY_REVEAL_HOURS", "48")), 168)),
    )
    if production_mode():
        if _is_weak_secret(value.api_key):
            raise RuntimeError("SAAS_GATEWAY_API_KEY must be a random 32+ character secret")
        if not value.database_url.startswith(("postgresql://", "postgres://")):
            raise RuntimeError("SAAS_GATEWAY_DATABASE_URL must be PostgreSQL in production")
        kova_key = (value.kova_api_key or "").strip()
        if (
            not kova_key
            or kova_key.lower() in {"change-me", "dev-secret"}
            or kova_key.lower().startswith("replace-with")
        ):
            raise RuntimeError("KOVA_API_KEY is required in production")
        if _is_weak_secret(value.team_auth_secret):
            raise RuntimeError("SAAS_TEAM_AUTH_SECRET must be a random 32+ character secret")
        if _is_weak_secret(value.edge_token):
            raise RuntimeError("SAAS_EDGE_TOKEN must be a random 32+ character secret")
        if _is_weak_secret(value.key_derivation_secret):
            raise RuntimeError("SAAS_KEY_DERIVATION_SECRET must be a random 32+ character secret")
        if not EVM_ADDRESS.fullmatch(value.payment_recipient):
            raise RuntimeError("SAAS_PAYMENT_RECIPIENT must be a valid EVM address in production")
        if not value.public_origin.startswith("https://"):
            raise RuntimeError("SAAS_PUBLIC_ORIGIN must be HTTPS in production")
    parsed = urlparse(value.kova_url)
    if parsed.username or parsed.password or not parsed.hostname:
        raise RuntimeError("KOVA_URL must be an URL without embedded credentials")
    return value


def _is_weak_secret(value: str) -> bool:
    text = (value or "").strip()
    lowered = text.lower()
    if len(text) < 32:
        return True
    if lowered in {"change-me", "dev-secret", "dev-only-change-me"}:
        return True
    if lowered.startswith("replace-with") or lowered.startswith("dev-"):
        return True
    if lowered.endswith("-change-me") or "change-me" in lowered:
        return True
    return False


class Database:
    def __init__(self, dsn: str):
        import sqlite3

        self.pg = None
        self.sqlite = None
        self.lock = threading.RLock()
        if dsn.startswith(("postgresql://", "postgres://")):
            from psycopg.rows import dict_row
            from psycopg_pool import ConnectionPool
            self.pg = ConnectionPool(dsn, min_size=1, max_size=10, kwargs={"row_factory": dict_row})
        else:
            path = dsn.removeprefix("sqlite:///") if dsn else "./data/saas-gateway.sqlite3"
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.sqlite = sqlite3.connect(path, check_same_thread=False)
            self.sqlite.row_factory = sqlite3.Row
        self.migrate()

    @property
    def is_postgres(self) -> bool:
        return self.pg is not None

    def _sql(self, value: str) -> str:
        return value.replace("?", "%s") if self.is_postgres else value

    def migrate(self) -> None:
        with self.transaction() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS saas_orders (
                    order_id TEXT PRIMARY KEY,
                    checkout_token_hash TEXT NOT NULL,
                    product TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    payer TEXT NOT NULL,
                    amount_usdc TEXT NOT NULL,
                    invoice_id TEXT UNIQUE NOT NULL,
                    idempotency_hash TEXT UNIQUE,
                    state TEXT NOT NULL DEFAULT 'pending',
                    tx_hash TEXT,
                    entitlement_id TEXT,
                    created_at TEXT NOT NULL,
                confirmed_at TEXT
            )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saas_keys (
                    key_id TEXT PRIMARY KEY,
                    key_hash TEXT UNIQUE NOT NULL,
                    key_prefix TEXT NOT NULL,
                    product TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    entitlement_id TEXT UNIQUE NOT NULL,
                    issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                    revoked_at TEXT,
                    last_used_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saas_trials (
                    trial_id TEXT PRIMARY KEY,
                    actor_fingerprint TEXT NOT NULL,
                    product TEXT NOT NULL,
                    plan TEXT NOT NULL,
                    key_id TEXT UNIQUE NOT NULL,
                    claimed_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    UNIQUE (actor_fingerprint, product)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saas_teams (
                    team_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_actor_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saas_team_members (
                    team_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (team_id, actor_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saas_rate_limits (
                    rate_key TEXT PRIMARY KEY,
                    window_started INTEGER NOT NULL,
                    hit_count INTEGER NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS saas_team_memories (
                    team_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (team_id, memory_id)
                )
            """)
            conn.execute("CREATE TABLE IF NOT EXISTS actor_proof_nonces_v2 (audience TEXT NOT NULL, actor_id TEXT NOT NULL, nonce TEXT NOT NULL, expires_at BIGINT NOT NULL, PRIMARY KEY (audience, actor_id, nonce))")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_actor_proof_expiry ON actor_proof_nonces_v2(expires_at)")
            if self.is_postgres:
                conn.execute("ALTER TABLE saas_keys ADD COLUMN IF NOT EXISTS last_used_at TEXT")
                conn.execute("ALTER TABLE saas_keys ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'paid'")
                conn.execute("ALTER TABLE saas_keys ADD COLUMN IF NOT EXISTS trial_id TEXT")
                conn.execute("ALTER TABLE saas_keys ADD COLUMN IF NOT EXISTS request_count BIGINT NOT NULL DEFAULT 0")
                conn.execute("ALTER TABLE saas_orders ADD COLUMN IF NOT EXISTS idempotency_hash TEXT")
                conn.execute("ALTER TABLE saas_orders ADD COLUMN IF NOT EXISTS key_id TEXT")
                conn.execute("ALTER TABLE saas_orders ADD COLUMN IF NOT EXISTS key_reveal_until TEXT")
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_saas_orders_idempotency ON saas_orders(idempotency_hash) WHERE idempotency_hash IS NOT NULL")
            else:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(saas_keys)").fetchall()}
                if "last_used_at" not in columns:
                    conn.execute("ALTER TABLE saas_keys ADD COLUMN last_used_at TEXT")
                if "source" not in columns:
                    conn.execute("ALTER TABLE saas_keys ADD COLUMN source TEXT NOT NULL DEFAULT 'paid'")
                if "trial_id" not in columns:
                    conn.execute("ALTER TABLE saas_keys ADD COLUMN trial_id TEXT")
                if "request_count" not in columns:
                    conn.execute("ALTER TABLE saas_keys ADD COLUMN request_count INTEGER NOT NULL DEFAULT 0")
                order_columns = {row[1] for row in conn.execute("PRAGMA table_info(saas_orders)").fetchall()}
                if "idempotency_hash" not in order_columns:
                    conn.execute("ALTER TABLE saas_orders ADD COLUMN idempotency_hash TEXT")
                if "key_id" not in order_columns:
                    conn.execute("ALTER TABLE saas_orders ADD COLUMN key_id TEXT")
                if "key_reveal_until" not in order_columns:
                    conn.execute("ALTER TABLE saas_orders ADD COLUMN key_reveal_until TEXT")
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_saas_orders_idempotency ON saas_orders(idempotency_hash)")

    def spend_actor_nonce(self, audience: str, actor_id: str, nonce: str, expires_at: int, current: int) -> bool:
        with self.transaction() as conn:
            conn.execute(self._sql("DELETE FROM actor_proof_nonces_v2 WHERE expires_at < ?"), (current,))
            return conn.execute(self._sql(
                "INSERT INTO actor_proof_nonces_v2 (audience, actor_id, nonce, expires_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT (audience, actor_id, nonce) DO NOTHING"),
                (audience, actor_id, nonce, expires_at)).rowcount == 1

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        if self.is_postgres:
            assert self.pg is not None
            with self.pg.connection() as connection:
                yield connection
            return
        assert self.sqlite is not None
        with self.lock:
            try:
                yield self.sqlite
                self.sqlite.commit()
            except Exception:
                self.sqlite.rollback()
                raise

    def insert(self, values: tuple[Any, ...]) -> None:
        with self.transaction() as conn:
            if len(values) == 9:
                conn.execute(self._sql(
                    "INSERT INTO saas_orders (order_id, checkout_token_hash, product, plan, payer, amount_usdc, invoice_id, created_at, idempotency_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"), values)
            else:
                conn.execute(self._sql(
                    "INSERT INTO saas_orders (order_id, checkout_token_hash, product, plan, payer, amount_usdc, invoice_id, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"), values)

    def get_by_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        query = self._sql("SELECT * FROM saas_orders WHERE invoice_id=?")
        with self.transaction() as conn:
            row = conn.execute(query, (invoice_id,)).fetchone()
            return dict(row) if row else None

    def get_by_idempotency(self, idempotency_hash: str) -> dict[str, Any] | None:
        query = self._sql("SELECT * FROM saas_orders WHERE idempotency_hash=?")
        with self.transaction() as conn:
            row = conn.execute(query, (idempotency_hash,)).fetchone()
            return dict(row) if row else None

    def issue_trial_key(
        self,
        trial_id: str,
        actor_fingerprint: str,
        product: str,
        plan: str,
        key_id: str,
        raw_key: str,
        entitlement: str,
        claimed_at: str,
        expires_at: str,
    ) -> bool:
        with self.transaction() as conn:
            inserted = conn.execute(self._sql(
                "INSERT INTO saas_trials (trial_id, actor_fingerprint, product, plan, key_id, claimed_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT (actor_fingerprint, product) DO NOTHING",
            ), (trial_id, actor_fingerprint, product, plan, key_id, claimed_at, expires_at))
            if inserted.rowcount != 1:
                return False
            conn.execute(self._sql(
                "INSERT INTO saas_keys (key_id, key_hash, key_prefix, product, plan, entitlement_id, issued_at, expires_at, source, trial_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'trial', ?)",
            ), (key_id, _hash(raw_key), raw_key[:16], product, plan, entitlement, claimed_at, expires_at, trial_id))
            return True

    def trial(self, actor_fingerprint: str, product: str) -> dict[str, Any] | None:
        query = self._sql(
            "SELECT t.*, k.entitlement_id, k.revoked_at FROM saas_trials t "
            "JOIN saas_keys k ON k.key_id=t.key_id "
            "WHERE t.actor_fingerprint=? AND t.product=?"
        )
        with self.transaction() as conn:
            row = conn.execute(query, (actor_fingerprint, product)).fetchone()
            return dict(row) if row else None

    def get(self, order_id: str) -> dict[str, Any] | None:
        query = "SELECT * FROM saas_orders WHERE order_id = ?"
        if self.is_postgres:
            assert self.pg is not None
            with self.pg.connection() as conn:
                row = conn.execute(query.replace("?", "%s"), (order_id,)).fetchone()
                return dict(row) if row else None
        assert self.sqlite is not None
        with self.lock:
            row = self.sqlite.execute(query, (order_id,)).fetchone()
            return dict(row) if row else None

    def update(self, order_id: str, tx_hash: str, entitlement: str) -> None:
        with self.transaction() as conn:
            conn.execute(self._sql(
                "UPDATE saas_orders SET state='confirmed', tx_hash=?, entitlement_id=?, confirmed_at=? WHERE order_id=?",
            ), (tx_hash, entitlement, _now(), order_id))

    def issue_key(self, order_id: str, tx_hash: str, raw_key: str, key_id: str,
                  product: str, plan: str, entitlement: str, issued_at: str,
                  expires_at: str, reveal_until: str) -> bool:
        with self.transaction() as conn:
            lock = " FOR UPDATE" if self.is_postgres else ""
            row = conn.execute(self._sql("SELECT state FROM saas_orders WHERE order_id=?" ) + lock, (order_id,)).fetchone()
            if not row or row["state"] != "pending":
                return False
            conn.execute(self._sql(
                "UPDATE saas_orders SET state='confirmed', tx_hash=?, entitlement_id=?, key_id=?, confirmed_at=?, key_reveal_until=? WHERE order_id=?",
            ), (tx_hash, entitlement, key_id, issued_at, reveal_until, order_id))
            conn.execute(self._sql(
                "INSERT INTO saas_keys (key_id, key_hash, key_prefix, product, plan, entitlement_id, issued_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ), (key_id, _hash(raw_key), raw_key[:16], product, plan, entitlement, issued_at, expires_at))
            return True

    def pending_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        query = self._sql("SELECT * FROM saas_orders WHERE state='pending' ORDER BY created_at LIMIT ?")
        with self.transaction() as conn:
            return [dict(row) for row in conn.execute(query, (limit,)).fetchall()]

    def set_order_state(self, order_id: str, state: str) -> None:
        with self.transaction() as conn:
            conn.execute(self._sql("UPDATE saas_orders SET state=? WHERE order_id=? AND state='pending'"), (state, order_id))

    def ping(self) -> None:
        with self.transaction() as conn:
            conn.execute("SELECT 1").fetchone()

    def key(self, raw_key: str) -> dict[str, Any] | None:
        assert self.pg is not None if self.is_postgres else True
        query = self._sql(
            "SELECT key_id, key_prefix, product, plan, entitlement_id, issued_at, expires_at, revoked_at, last_used_at, source, trial_id, request_count "
            "FROM saas_keys WHERE key_hash=?"
        )
        if self.is_postgres:
            with self.pg.connection() as conn:  # type: ignore[union-attr]
                row = conn.execute(query, (_hash(raw_key),)).fetchone()
                return dict(row) if row else None
        assert self.sqlite is not None
        with self.lock:
            row = self.sqlite.execute(query, (_hash(raw_key),)).fetchone()
            return dict(row) if row else None

    def touch_key(self, raw_key: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                self._sql("UPDATE saas_keys SET last_used_at=?, request_count=COALESCE(request_count,0)+1 WHERE key_hash=?"),
                (_now(), _hash(raw_key)),
            )

    def admin_overview(self) -> dict[str, Any]:
        with self.transaction() as conn:
            orders = conn.execute(self._sql(
                "SELECT state, COUNT(*) AS n FROM saas_orders GROUP BY state"
            )).fetchall()
            keys = conn.execute(self._sql(
                "SELECT "
                "COUNT(*) AS total, "
                "SUM(CASE WHEN revoked_at IS NULL AND expires_at > ? THEN 1 ELSE 0 END) AS active, "
                "SUM(CASE WHEN source='trial' THEN 1 ELSE 0 END) AS trials, "
                "SUM(CASE WHEN COALESCE(source,'paid')!='trial' THEN 1 ELSE 0 END) AS paid, "
                "SUM(COALESCE(request_count,0)) AS requests "
                "FROM saas_keys"
            ), (_now(),)).fetchone()
            recent = conn.execute(self._sql(
                "SELECT order_id, product, plan, payer, amount_usdc, state, created_at, confirmed_at, key_id "
                "FROM saas_orders ORDER BY created_at DESC LIMIT 8"
            )).fetchall()
        by_state = {str(row["state"]): int(row["n"]) for row in orders}
        key_row = dict(keys) if keys else {}
        return {
            "orders_by_state": by_state,
            "keys": {
                "total": int(key_row.get("total") or 0),
                "active": int(key_row.get("active") or 0),
                "trials": int(key_row.get("trials") or 0),
                "paid": int(key_row.get("paid") or 0),
                "requests": int(key_row.get("requests") or 0),
            },
            "recent_orders": [dict(row) for row in recent],
        }

    def admin_orders(self, limit: int = 200) -> list[dict[str, Any]]:
        query = self._sql(
            "SELECT order_id, product, plan, payer, amount_usdc, invoice_id, state, tx_hash, "
            "entitlement_id, key_id, created_at, confirmed_at, key_reveal_until "
            "FROM saas_orders ORDER BY created_at DESC LIMIT ?"
        )
        with self.transaction() as conn:
            return [dict(row) for row in conn.execute(query, (max(1, min(limit, 500)),)).fetchall()]

    def admin_keys(self, limit: int = 200) -> list[dict[str, Any]]:
        query = self._sql(
            "SELECT key_id, key_prefix, product, plan, entitlement_id, issued_at, expires_at, "
            "revoked_at, last_used_at, COALESCE(source,'paid') AS source, trial_id, "
            "COALESCE(request_count,0) AS request_count "
            "FROM saas_keys ORDER BY issued_at DESC LIMIT ?"
        )
        with self.transaction() as conn:
            return [dict(row) for row in conn.execute(query, (max(1, min(limit, 500)),)).fetchall()]

    def revoke_key(self, raw_key: str) -> bool:
        with self.transaction() as conn:
            result = conn.execute(self._sql("UPDATE saas_keys SET revoked_at=? WHERE key_hash=? AND revoked_at IS NULL"), (_now(), _hash(raw_key)))
            return result.rowcount == 1

    def rotate_key(self, raw_key: str, replacement: tuple[Any, ...]) -> dict[str, Any] | None:
        with self.transaction() as conn:
            lock = " FOR UPDATE" if self.is_postgres else ""
            row = conn.execute(self._sql("SELECT key_id, product, plan, entitlement_id, expires_at, revoked_at, source, trial_id FROM saas_keys WHERE key_hash=?") + lock, (_hash(raw_key),)).fetchone()
            if not row or row["revoked_at"] or row["expires_at"] <= _now():
                return None
            conn.execute(self._sql("UPDATE saas_keys SET revoked_at=? WHERE key_hash=?"), (_now(), _hash(raw_key)))
            conn.execute(self._sql(
                "INSERT INTO saas_keys (key_id, key_hash, key_prefix, product, plan, entitlement_id, issued_at, expires_at, source, trial_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ), replacement)
            return {"product": row["product"], "plan": row["plan"], "entitlement_id": replacement[5], "expires_at": row["expires_at"]}

    def consume_rate_limit(self, key: str, limit: int, window: int = 60) -> bool:
        now = int(time.time())
        with self.transaction() as conn:
            if self.is_postgres:
                conn.execute(self._sql("INSERT INTO saas_rate_limits (rate_key, window_started, hit_count) VALUES (?, ?, 0) ON CONFLICT(rate_key) DO NOTHING"), (key, now))
            lock = " FOR UPDATE" if self.is_postgres else ""
            row = conn.execute(self._sql("SELECT window_started, hit_count FROM saas_rate_limits WHERE rate_key=?") + lock, (key,)).fetchone()
            if not row or now - int(row["window_started"]) >= window:
                if row:
                    conn.execute(self._sql("UPDATE saas_rate_limits SET window_started=?, hit_count=1 WHERE rate_key=?"), (now, key))
                else:
                    conn.execute(self._sql("INSERT INTO saas_rate_limits (rate_key, window_started, hit_count) VALUES (?, ?, 1)"), (key, now))
                return True
            if int(row["hit_count"]) >= limit:
                return False
            conn.execute(self._sql("UPDATE saas_rate_limits SET hit_count=hit_count+1 WHERE rate_key=?"), (key,))
            return True

    def create_team(self, team_id: str, name: str, actor_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(self._sql("INSERT INTO saas_teams (team_id, name, owner_actor_id, created_at) VALUES (?, ?, ?, ?)"), (team_id, name, actor_id, _now()))
            conn.execute(self._sql("INSERT INTO saas_team_members (team_id, actor_id, role, created_at) VALUES (?, ?, 'owner', ?)"), (team_id, actor_id, _now()))

    def team(self, team_id: str) -> dict[str, Any] | None:
        with self.transaction() as conn:
            row = conn.execute(self._sql("SELECT * FROM saas_teams WHERE team_id=?"), (team_id,)).fetchone()
            return dict(row) if row else None

    def team_member(self, team_id: str, actor_id: str) -> dict[str, Any] | None:
        with self.transaction() as conn:
            row = conn.execute(self._sql("SELECT * FROM saas_team_members WHERE team_id=? AND actor_id=?"), (team_id, actor_id)).fetchone()
            return dict(row) if row else None

    def add_member(self, team_id: str, actor_id: str, role: str) -> None:
        with self.transaction() as conn:
            conn.execute(self._sql("INSERT INTO saas_team_members (team_id, actor_id, role, created_at) VALUES (?, ?, ?, ?) ON CONFLICT(team_id, actor_id) DO UPDATE SET role=excluded.role WHERE saas_team_members.role <> 'owner'"), (team_id, actor_id, role, _now()))

    def remove_member(self, team_id: str, actor_id: str) -> bool:
        with self.transaction() as conn:
            result = conn.execute(self._sql("DELETE FROM saas_team_members WHERE team_id=? AND actor_id=?"), (team_id, actor_id))
            return result.rowcount == 1

    def register_team_memory(self, team_id: str, memory_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(self._sql("INSERT INTO saas_team_memories (team_id, memory_id, created_at) VALUES (?, ?, ?) ON CONFLICT(team_id, memory_id) DO NOTHING"), (team_id, memory_id, _now()))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _expires(days: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + days * 86400))


def _future(seconds: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + seconds))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _derive(label: str, context: str) -> bytes:
    return hmac.new(cfg.key_derivation_secret.encode(), f"{label}:{context}".encode(), hashlib.sha256).digest()


def _derived_token(label: str, context: str, prefix: str) -> str:
    encoded = base64.urlsafe_b64encode(_derive(label, context)).rstrip(b"=").decode()
    return prefix + encoded


def _checkout_secret(idempotency_hash: str) -> str:
    return _derived_token("checkout", idempotency_hash, "chk_")


def _paid_key(order_id: str) -> str:
    return _derived_token("paid-key", order_id, "ask_")


def _trial_key(actor_fingerprint: str, product: str) -> str:
    return _derived_token("trial-key", f"{actor_fingerprint}:{product}", "ask_")


def _derived_id(label: str, context: str, prefix: str) -> str:
    return prefix + _derive(label, context).hex()[:32]


def _amount(value: str) -> str:
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise HTTPException(422, "invalid plan amount") from error
    if not number.is_finite() or number <= 0 or number.as_tuple().exponent < -6:
        raise HTTPException(422, "invalid plan amount")
    return format(number, "f")


def _auth(token: str | None, current: Settings) -> None:
    if not token or not hmac.compare_digest(token, current.api_key):
        raise HTTPException(401, "gateway authentication required")


def _checkout_token(request: Request) -> str:
    token = request.headers.get("x-checkout-token", "")
    if len(token) < 32:
        raise HTTPException(401, "checkout token required")
    return token


def _service_auth(token: str | None) -> None:
    if not token or not hmac.compare_digest(token, cfg.api_key):
        raise HTTPException(401, "gateway service authentication required")


def _client_ip(request: Request) -> str:
    source = request.client.host if request.client else "unknown"
    edge_token = request.headers.get("x-attested-edge-token", "")
    forwarded = request.headers.get("x-attested-client-ip", "").strip()
    if edge_token and hmac.compare_digest(edge_token, cfg.edge_token) and forwarded:
        try:
            source = str(ipaddress.ip_address(forwarded))
        except ValueError:
            pass
    return source[:128]


def _rate_limit(request: Request, bucket: str, limit: int) -> None:
    source = _client_ip(request)
    if not db.consume_rate_limit(f"{bucket}:{source}", limit):
        raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": "60"})


def _b64url(value: str, label: str) -> bytes:
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError):
        raise HTTPException(401, f"invalid actor {label}") from None
    return decoded


def _verified_actor(request: Request) -> str:
    from .actor_auth import verify_actor_request
    return verify_actor_request(request, audience=os.getenv("SAAS_ACTOR_AUDIENCE", "attested-saas-gateway"),
                                spend_nonce=db.spend_actor_nonce)


def _active_product_key(request: Request, product: str) -> tuple[str, dict[str, Any]]:
    raw = request.headers.get("x-saas-key", "")
    if len(raw) < 40:
        raise HTTPException(401, "SaaS API key required")
    row = db.key(raw)
    if not row or row["revoked_at"] or row["expires_at"] <= _now():
        raise HTTPException(401, "SaaS API key is invalid or expired")
    if row["product"] != product:
        raise HTTPException(403, "SaaS API key is not valid for this product")
    db.touch_key(raw)
    return raw, row


def _kova(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    headers = dict(kwargs.pop("headers", {}))
    headers["X-API-Key"] = cfg.kova_api_key
    headers["User-Agent"] = "attested-saas-gateway/1"
    for attempt in range(2):
        try:
            response = httpx.request(method, f"{cfg.kova_url}{path}", headers=headers, timeout=15, **kwargs)
            if response.status_code in {502, 503, 504} and attempt == 0:
                time.sleep(0.25)
                continue
            if response.status_code >= 400:
                raise HTTPException(503 if response.status_code >= 500 else 422, "payment adapter could not process request")
            return response.json()
        except HTTPException:
            raise
        except httpx.HTTPError as error:
            if attempt == 0:
                time.sleep(0.25)
                continue
            raise HTTPException(503, "payment adapter unavailable") from error
    raise HTTPException(503, "payment adapter unavailable")


class OrderRequest(BaseModel):
    plan: str = Field(min_length=1, max_length=80)
    payer: str = Field(min_length=42, max_length=42)


class ConfirmRequest(BaseModel):
    tx_hash: str = Field(min_length=66, max_length=66)


class TeamRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class MemberRequest(BaseModel):
    actor_id: str = Field(pattern=r"^did:actor:[0-9a-f]{64}$")
    role: str = Field(default="member", pattern=r"^(member|admin)$")


class TrialRequest(BaseModel):
    product: str = Field(pattern=r"^(personal|team|expert-market)$")


cfg = settings()
db = Database(cfg.database_url)
_reconcile_stop = threading.Event()


@asynccontextmanager
async def lifespan(_: FastAPI) -> Iterator[None]:
    _reconcile_stop.clear()
    worker = threading.Thread(target=_reconcile_forever, name="saas-payment-reconciler", daemon=True)
    worker.start()
    yield
    _reconcile_stop.set()
    worker.join(timeout=1)


app = FastAPI(title="Attested SaaS Gateway", version="1.0.0", lifespan=lifespan)
from .actor_auth import ActorProofBody
app.add_middleware(ActorProofBody)


@app.get("/healthz")
def health() -> dict[str, Any]:
    try:
        db.ping()
    except Exception as error:
        raise HTTPException(503, "database unavailable") from error
    return {
        "status": "ok",
        "service": "attested-saas-gateway",
        "database": "postgresql" if db.is_postgres else "sqlite",
        "billing": "kova",
        "reconciliation": "background",
    }


@app.get("/v1/products")
def products() -> dict[str, Any]:
    return {"products": [
        {"id": "personal", "path": "/memory", "name": "Personal Attested Memory"},
        {"id": "team", "path": "/teams", "name": "Team Memory OS"},
        {"id": "expert-market", "path": "/market", "name": "Expert Memory Market"},
    ], "plans": [{"code": code, **spec} for code, spec in PLANS.items()], "trials": [{"product": product, **spec} for product, spec in TRIALS.items()]}


@app.post("/v1/trials", status_code=201)
def create_trial(body: TrialRequest, request: Request) -> dict[str, Any]:
    """Issue one short-lived product key per verified actor and product."""
    _rate_limit(request, "create-trial", 5)
    actor_id = _verified_actor(request)
    spec = TRIALS[body.product]
    fingerprint = _hash(actor_id)
    existing = db.trial(fingerprint, body.product)
    raw_key = _trial_key(fingerprint, body.product)
    if existing:
        if existing["revoked_at"] or existing["expires_at"] <= _now():
            raise HTTPException(409, "this actor already used the trial for this product")
        return {
            "trial_id": existing["trial_id"],
            "product": body.product,
            "plan": existing["plan"],
            "source": "trial",
            "api_key": raw_key,
            "key_id": existing["key_id"],
            "expires_at": existing["expires_at"],
            "recovered": True,
            "next_step": "upgrade through POST /v1/billing/orders before expiry",
        }
    trial_id = _derived_id("trial-id", f"{fingerprint}:{body.product}", "trial_")
    key_id = _derived_id("trial-key-id", f"{fingerprint}:{body.product}", "key_")
    claimed_at = _now()
    expires_at = _expires(int(spec["period_days"]))
    issued = db.issue_trial_key(
        trial_id, fingerprint, body.product, spec["plan"], key_id, raw_key,
        _derived_id("trial-entitlement", f"{fingerprint}:{body.product}", "ent_"), claimed_at, expires_at,
    )
    if not issued:
        raise HTTPException(409, "this actor already used the trial for this product")
    return {
        "trial_id": trial_id,
        "product": body.product,
        "plan": spec["plan"],
        "source": "trial",
        "api_key": raw_key,
        "key_id": key_id,
        "expires_at": expires_at,
        "warning": "store this trial API key securely; the same signed actor can recover it while active",
        "next_step": "upgrade through POST /v1/billing/orders before expiry",
    }


@app.post("/v1/billing/orders")
def create_order(body: OrderRequest, request: Request) -> dict[str, Any]:
    _rate_limit(request, "create-order", 12)
    spec = PLANS.get(body.plan)
    if spec is None:
        raise HTTPException(422, "unknown plan")
    if not EVM_ADDRESS.fullmatch(body.payer):
        raise HTTPException(422, "payer must be a valid EVM address")
    idempotency = request.headers.get("idempotency-key", "").strip()
    if len(idempotency) < 16 or len(idempotency) > 200:
        raise HTTPException(400, "Idempotency-Key header is required (16-200 characters)")
    idempotency_hash = _hash(idempotency)
    token = _checkout_secret(idempotency_hash)
    existing_order = db.get_by_idempotency(idempotency_hash)
    if existing_order:
        if existing_order["plan"] != body.plan or existing_order["payer"] != body.payer.lower():
            raise HTTPException(409, "this Idempotency-Key belongs to a different checkout")
        invoice = _kova("GET", f"/v1/invoices/{existing_order['invoice_id']}")
        return _checkout_response(existing_order, token, invoice, recovered=True)
    invoice_payload = {"payer": body.payer, "recipient": cfg.payment_recipient, "amount_usdc": _amount(spec["price"]), "expires_in_seconds": 3600, "unique_amount": True}
    if not EVM_ADDRESS.fullmatch(invoice_payload["recipient"]):
        raise HTTPException(503, "SAAS_PAYMENT_RECIPIENT is not configured")
    try:
        adapter_idempotency = _hash(f"attested-saas-gateway:{idempotency}")
        invoice = _kova("POST", "/v1/invoices", headers={"Idempotency-Key": adapter_idempotency}, json=invoice_payload)
    except HTTPException:
        raise
    if invoice.get("amount_binding") != "unique_amount":
        raise HTTPException(503, "payment adapter does not support order-bound amounts")
    existing = db.get_by_invoice(str(invoice.get("invoice_id", "")))
    if existing:
        if (existing["idempotency_hash"] != idempotency_hash or existing["plan"] != body.plan
                or existing["payer"] != body.payer.lower()):
            raise HTTPException(409, "payment invoice already belongs to a different checkout")
        return _checkout_response(existing, token, invoice, recovered=True)
    order_id = _derived_id("order-id", idempotency_hash, "saas_")
    try:
        db.insert((order_id, _hash(token), spec["product"], body.plan, body.payer.lower(), invoice["amount_usdc"], invoice["invoice_id"], _now(), idempotency_hash))
    except Exception:
        raced_order = db.get_by_idempotency(idempotency_hash)
        if not raced_order:
            raise
        if raced_order["plan"] != body.plan or raced_order["payer"] != body.payer.lower():
            raise HTTPException(409, "this Idempotency-Key belongs to a different checkout")
        return _checkout_response(raced_order, token, invoice, recovered=True)
    return _checkout_response(db.get(order_id) or {}, token, invoice)


def _checkout_response(row: dict[str, Any], token: str, invoice: dict[str, Any], recovered: bool = False) -> dict[str, Any]:
    recipient = invoice.get("recipient") or invoice.get("pay_to") or cfg.payment_recipient
    token_address = invoice.get("token_address", "")
    amount_raw = invoice.get("amount_raw", "")
    response = {
        "order_id": row["order_id"],
        "checkout_token": token,
        "state": row.get("state", "pending"),
        "product": row["product"],
        "plan": row["plan"],
        "invoice_id": row["invoice_id"],
        "amount_usdc": invoice.get("amount_usdc", row["amount_usdc"]),
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


def _owned_order(order_id: str, request: Request) -> dict[str, Any]:
    if not ORDER_ID.fullmatch(order_id):
        raise HTTPException(404, "order not found")
    row = db.get(order_id)
    if not row or not hmac.compare_digest(row["checkout_token_hash"], _hash(_checkout_token(request))):
        raise HTTPException(404, "order not found")
    return row


def _order_public(row: dict[str, Any], include_key: bool = True) -> dict[str, Any]:
    response = {key: row.get(key) for key in ("order_id", "product", "plan", "payer", "amount_usdc", "invoice_id", "state", "tx_hash", "entitlement_id", "key_id", "created_at", "confirmed_at")}
    if include_key and row.get("state") == "confirmed" and row.get("key_reveal_until", "") >= _now():
        raw_key = _paid_key(row["order_id"])
        stored = db.key(raw_key)
        if stored and not stored["revoked_at"] and stored["key_id"] == row.get("key_id"):
            response["api_key"] = raw_key
            response["key_reveal_until"] = row["key_reveal_until"]
            response["warning"] = "store this API key securely; recovery closes after the reveal window"
    return response


def _issue_paid_key(order_id: str, row: dict[str, Any], tx_hash: str) -> dict[str, Any] | None:
    entitlement = _derived_id("paid-entitlement", order_id, "ent_")
    raw_key = _paid_key(order_id)
    key_id = _derived_id("paid-key-id", order_id, "key_")
    issued_at = _now()
    expires_at = _expires(int(PLANS[row["plan"]]["period_days"]))
    reveal_until = _future(cfg.key_reveal_hours * 3600)
    if not db.issue_key(order_id, tx_hash.lower(), raw_key, key_id, row["product"], row["plan"], entitlement, issued_at, expires_at, reveal_until):
        return None
    return _order_public(db.get(order_id) or row)


def _sync_order(row: dict[str, Any], tx_hash: str | None = None) -> dict[str, Any]:
    params = {"tx_hash": tx_hash} if tx_hash else None
    invoice = _kova("GET", f"/v1/invoices/{row['invoice_id']}", params=params)
    if invoice.get("state") == "confirmed" and invoice.get("tx_hash"):
        if invoice.get("amount_binding") != "unique_amount":
            raise HTTPException(409, "Payment needs operator review; keep this order and do not pay again")
        _issue_paid_key(row["order_id"], row, str(invoice["tx_hash"]))
    elif invoice.get("state") in {"expired", "cancelled"}:
        db.set_order_state(row["order_id"], str(invoice["state"]))
    return db.get(row["order_id"]) or row


@app.get("/v1/billing/orders/{order_id}")
def get_order(order_id: str, request: Request) -> dict[str, Any]:
    _rate_limit(request, "order-status", 30)
    row = _owned_order(order_id, request)
    if row["state"] == "pending":
        row = _sync_order(row)
    return _order_public(row)


@app.post("/v1/billing/orders/{order_id}/confirm")
def confirm_order(order_id: str, body: ConfirmRequest, request: Request) -> dict[str, Any]:
    _rate_limit(request, "confirm-order", 30)
    row = _owned_order(order_id, request)
    if row["state"] == "pending":
        row = _sync_order(row, body.tx_hash)
    return _order_public(row)


@app.get("/v1/keys/introspect")
def introspect_key(
    x_saas_key: str | None = Header(default=None),
    x_saas_internal_token: str | None = Header(default=None),
    product: str | None = None,
) -> dict[str, Any]:
    _service_auth(x_saas_internal_token)
    if not x_saas_key or len(x_saas_key) < 40:
        raise HTTPException(401, "SaaS API key required")
    row = db.key(x_saas_key)
    if not row or row["revoked_at"] or row["expires_at"] <= _now():
        raise HTTPException(401, "SaaS API key is invalid or expired")
    if product and row["product"] != product:
        raise HTTPException(403, "SaaS API key is not valid for this product")
    db.touch_key(x_saas_key)
    return {"active": True, **row}


def _requested_product(request: Request) -> str:
    product = request.query_params.get("product") or request.headers.get("x-product", "")
    if product not in {"personal", "team", "expert-market"}:
        raise HTTPException(400, "product query parameter or X-Product header is required")
    return product


@app.get("/v1/keys/me")
def key_me(request: Request) -> dict[str, Any]:
    _, row = _active_product_key(request, _requested_product(request))
    return {"active": True, **row}


@app.post("/v1/keys/rotate")
def rotate_key(request: Request) -> dict[str, Any]:
    raw, row = _active_product_key(request, _requested_product(request))
    replacement = "ask_" + secrets.token_urlsafe(32)
    key_id = "key_" + secrets.token_hex(16)
    values = (key_id, _hash(replacement), replacement[:16], row["product"], row["plan"], "ent_" + secrets.token_hex(16), _now(), row["expires_at"], row.get("source", "paid"), row.get("trial_id"))
    rotated = db.rotate_key(raw, values)
    if not rotated:
        raise HTTPException(409, "key is no longer active")
    return {"active": True, "api_key": replacement, "key_id": key_id, **rotated, "warning": "save this API key now; it is shown only once"}


@app.post("/v1/keys/revoke")
def revoke_key(request: Request) -> dict[str, Any]:
    raw, _ = _active_product_key(request, _requested_product(request))
    if not db.revoke_key(raw):
        raise HTTPException(409, "key is already revoked")
    return {"active": False, "revoked": True}


def _team_key(request: Request) -> str:
    _active_product_key(request, "team")
    return _verified_actor(request)


@app.post("/v1/teams")
def create_team(body: TeamRequest, request: Request) -> dict[str, Any]:
    actor = _team_key(request)
    team_id = "team_" + secrets.token_hex(12)
    db.create_team(team_id, body.name.strip(), actor)
    return {"team_id": team_id, "name": body.name.strip(), "role": "owner", "actor_id": actor}


@app.post("/v1/teams/{team_id}/members")
def add_team_member(team_id: str, body: MemberRequest, request: Request) -> dict[str, Any]:
    actor = _team_key(request)
    team = db.team(team_id)
    if not team:
        raise HTTPException(404, "team not found")
    membership = db.team_member(team_id, actor)
    if not membership or membership["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "team admin access required")
    if body.actor_id == team["owner_actor_id"]:
        raise HTTPException(400, "team owner role cannot be changed")
    db.add_member(team_id, body.actor_id, body.role)
    return {"team_id": team_id, "actor_id": body.actor_id, "role": body.role}


@app.delete("/v1/teams/{team_id}/members/{member_actor_id}")
def remove_team_member(team_id: str, member_actor_id: str, request: Request) -> dict[str, Any]:
    actor = _team_key(request)
    team = db.team(team_id)
    membership = db.team_member(team_id, actor)
    if not team or not membership or membership["role"] not in {"owner", "admin"}:
        raise HTTPException(403, "team admin access required")
    if member_actor_id == team["owner_actor_id"]:
        raise HTTPException(400, "team owner cannot be removed")
    if not db.remove_member(team_id, member_actor_id):
        raise HTTPException(404, "team member not found")
    return {"team_id": team_id, "actor_id": member_actor_id, "removed": True}


@app.get("/v1/teams/{team_id}/assertion")
def team_assertion(team_id: str, request: Request) -> dict[str, Any]:
    actor = _team_key(request)
    if not db.team_member(team_id, actor):
        raise HTTPException(403, "actor is not a team member")
    expires = int(time.time()) + 300
    payload = f"{team_id}|{actor}|{expires}"
    signature = hmac.new(cfg.team_auth_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {"team_id": team_id, "actor_id": actor, "expires_at": expires, "assertion": f"{payload}|{signature}"}


def _admin_bearer(authorization: str | None) -> None:
    token = (authorization or "").removeprefix("Bearer ").strip()
    _auth(token, cfg)


@app.get("/v1/admin/overview")
def admin_overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _admin_bearer(authorization)
    return {"service": "attested-saas-gateway", **db.admin_overview()}


@app.get("/v1/admin/orders")
def admin_orders(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    _admin_bearer(authorization)
    rows = db.admin_orders(limit)
    return {"count": len(rows), "orders": rows}


@app.get("/v1/admin/keys")
def admin_keys(authorization: str | None = Header(default=None), limit: int = 200) -> dict[str, Any]:
    _admin_bearer(authorization)
    rows = db.admin_keys(limit)
    return {"count": len(rows), "keys": rows}


def _reconcile_forever() -> None:
    while not _reconcile_stop.wait(cfg.reconcile_seconds):
        for row in db.pending_orders():
            try:
                _sync_order(row)
            except Exception:
                continue
