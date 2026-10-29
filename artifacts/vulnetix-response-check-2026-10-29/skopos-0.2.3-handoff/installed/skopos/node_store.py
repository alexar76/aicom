"""Credentials, enrollment tickets and replay state for push-mode nodes.

The table here is what makes a report trustworthy: ``key_id`` arrives in a
header, this module resolves it to a ``server_name``, and that resolved name is
the only one the ingest path ever sees. Nothing a node writes in its document
can change which server it is reporting as.

Secrets are HMAC keys, so SKOPOS has to be able to read them back — hashing them
the way a password would be hashed is not an option. They are therefore sealed
with AES-GCM under a key held outside the database, which means a leaked dump or
a stolen replica is not by itself a set of working fleet credentials. If no
sealing key is configured the secrets are stored in the clear and the dashboard
says so; that is a deliberate, visible degradation rather than a silent one.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .db_connection import DbConnection
from .db import now_utc_iso

logger = logging.getLogger("skopos.node")

#: How long an enrollment ticket is good for. Long enough to paste an installer
#: into a terminal, short enough that a ticket left in a scrollback is stale.
TICKET_TTL_MINUTES = 30

_PLAIN_PREFIX = "plain:"
_SEALED_PREFIX = "gcm:"

_warned_about_plaintext = False


NODE_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS node_credentials (
  key_id TEXT PRIMARY KEY,
  server_name TEXT NOT NULL,
  secret_sealed TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT,
  last_seen_at_utc TEXT,
  last_seq INTEGER NOT NULL DEFAULT 0,
  last_ip TEXT,
  agent_version TEXT,
  clock_skew_s INTEGER,
  reports_total INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_node_credentials_server
  ON node_credentials(server_name);

CREATE TABLE IF NOT EXISTS node_tickets (
  ticket_sha256 TEXT PRIMARY KEY,
  server_name TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  claimed_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS node_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_utc TEXT NOT NULL,
  key_id TEXT,
  server_name TEXT,
  kind TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_node_events_ts ON node_events(ts_utc);
"""

NODE_SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS node_credentials (
  key_id TEXT PRIMARY KEY,
  server_name TEXT NOT NULL,
  secret_sealed TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT,
  last_seen_at_utc TEXT,
  last_seq BIGINT NOT NULL DEFAULT 0,
  last_ip TEXT,
  agent_version TEXT,
  clock_skew_s INTEGER,
  reports_total BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_node_credentials_server
  ON node_credentials(server_name);

CREATE TABLE IF NOT EXISTS node_tickets (
  ticket_sha256 TEXT PRIMARY KEY,
  server_name TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  claimed_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS node_events (
  id BIGSERIAL PRIMARY KEY,
  ts_utc TEXT NOT NULL,
  key_id TEXT,
  server_name TEXT,
  kind TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_node_events_ts ON node_events(ts_utc);
"""


def init_node_db(con: DbConnection) -> None:
    script = NODE_SCHEMA_POSTGRES if con.backend == "postgresql" else NODE_SCHEMA_SQLITE
    con.executescript(script)
    con.commit()


# --- Sealing ----------------------------------------------------------------

def sealing_key() -> bytes | None:
    """The AES key used to wrap node secrets, if the operator configured one."""
    raw = os.environ.get("SKOPOS_NODE_SECRET_KEY", "").strip()
    if not raw:
        path = os.environ.get("SKOPOS_NODE_SECRET_KEY_FILE", "").strip()
        if path and os.path.isfile(path):
            raw = open(path, encoding="utf-8").read().strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception:
        logger.warning("SKOPOS_NODE_SECRET_KEY is not valid base64; ignoring it")
        return None
    if len(key) not in (16, 24, 32):
        logger.warning("SKOPOS_NODE_SECRET_KEY must decode to 16, 24 or 32 bytes")
        return None
    return key


def secrets_are_sealed() -> bool:
    return sealing_key() is not None


def seal_secret(secret: bytes) -> str:
    key = sealing_key()
    if key is None:
        global _warned_about_plaintext
        if not _warned_about_plaintext:
            logger.warning(
                "Node secrets are being stored unencrypted. Set SKOPOS_NODE_SECRET_KEY "
                "(base64 of 32 random bytes) so a database dump is not a set of "
                "working fleet credentials."
            )
            _warned_about_plaintext = True
        return _PLAIN_PREFIX + base64.b64encode(secret).decode("ascii")

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    blob = AESGCM(key).encrypt(nonce, secret, None)
    return _SEALED_PREFIX + base64.b64encode(nonce + blob).decode("ascii")


def open_secret(sealed: str) -> bytes:
    if sealed.startswith(_PLAIN_PREFIX):
        return base64.b64decode(sealed[len(_PLAIN_PREFIX) :])
    if not sealed.startswith(_SEALED_PREFIX):
        raise ValueError("unrecognised secret encoding")
    key = sealing_key()
    if key is None:
        raise ValueError(
            "This deployment holds sealed node secrets but SKOPOS_NODE_SECRET_KEY "
            "is not set. Restore the key or re-enroll the affected nodes."
        )

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(sealed[len(_SEALED_PREFIX) :])
    return AESGCM(key).decrypt(raw[:12], raw[12:], None)


# --- Credentials ------------------------------------------------------------

@dataclass(frozen=True)
class NodeCredential:
    key_id: str
    server_name: str
    secret: bytes
    revoked: bool
    last_seq: int


def issue_credential(con: DbConnection, server_name: str) -> tuple[str, bytes]:
    """Mint a new (key_id, secret) for a server and store the sealed secret."""
    init_node_db(con)
    key_id = "nk_" + secrets.token_hex(12)
    secret = secrets.token_bytes(32)
    con.execute(
        "INSERT INTO node_credentials(key_id, server_name, secret_sealed, created_at_utc) "
        "VALUES (?,?,?,?)",
        (key_id, server_name, seal_secret(secret), now_utc_iso()),
    )
    record_event(con, kind="enrolled", key_id=key_id, server_name=server_name)
    con.commit()
    return key_id, secret


def get_credential(con: DbConnection, key_id: str) -> NodeCredential | None:
    row = con.execute(
        "SELECT key_id, server_name, secret_sealed, revoked_at_utc, last_seq "
        "FROM node_credentials WHERE key_id = ?",
        (key_id,),
    ).fetchone()
    if not row:
        return None
    data = row if isinstance(row, dict) else {
        "key_id": row[0], "server_name": row[1], "secret_sealed": row[2],
        "revoked_at_utc": row[3], "last_seq": row[4],
    }
    try:
        secret = open_secret(data["secret_sealed"])
    except Exception:
        logger.exception("Could not unseal the secret for %s", key_id)
        return None
    return NodeCredential(
        key_id=data["key_id"],
        server_name=data["server_name"],
        secret=secret,
        revoked=bool(data["revoked_at_utc"]),
        last_seq=int(data["last_seq"] or 0),
    )


def claim_seq(con: DbConnection, key_id: str, seq: int) -> bool:
    """Accept a report's sequence number, exactly once.

    The comparison and the write are one statement so two copies of the same
    report — or two hosts sharing a cloned credential — cannot both win. A
    ``False`` return means replay, reorder, or a clone; the caller decides.
    """
    cur = con.execute(
        "UPDATE node_credentials SET last_seq = ? "
        "WHERE key_id = ? AND last_seq < ? AND revoked_at_utc IS NULL",
        (int(seq), key_id, int(seq)),
    )
    accepted = int(getattr(cur, "rowcount", 0) or 0) == 1
    con.commit()
    return accepted


def record_report(
    con: DbConnection,
    key_id: str,
    *,
    ip: str | None,
    agent_version: str | None,
    clock_skew_s: int | None,
) -> None:
    con.execute(
        "UPDATE node_credentials SET last_seen_at_utc = ?, last_ip = ?, "
        "agent_version = ?, clock_skew_s = ?, reports_total = reports_total + 1 "
        "WHERE key_id = ?",
        (now_utc_iso(), ip, agent_version, clock_skew_s, key_id),
    )
    con.commit()


def revoke_credential(con: DbConnection, key_id: str) -> bool:
    init_node_db(con)
    cur = con.execute(
        "UPDATE node_credentials SET revoked_at_utc = ? "
        "WHERE key_id = ? AND revoked_at_utc IS NULL",
        (now_utc_iso(), key_id),
    )
    revoked = int(getattr(cur, "rowcount", 0) or 0) == 1
    if revoked:
        record_event(con, kind="revoked", key_id=key_id, server_name=None)
    con.commit()
    return revoked


def list_credentials(con: DbConnection, *, server_name: str | None = None) -> list[dict]:
    init_node_db(con)
    sql = (
        "SELECT key_id, server_name, created_at_utc, revoked_at_utc, last_seen_at_utc, "
        "last_seq, last_ip, agent_version, clock_skew_s, reports_total "
        "FROM node_credentials"
    )
    params: tuple = ()
    if server_name:
        sql += " WHERE server_name = ?"
        params = (server_name,)
    sql += " ORDER BY created_at_utc DESC"
    rows = con.execute(sql, params).fetchall()
    out = []
    for r in rows:
        out.append(dict(r) if isinstance(r, dict) else {
            "key_id": r[0], "server_name": r[1], "created_at_utc": r[2],
            "revoked_at_utc": r[3], "last_seen_at_utc": r[4], "last_seq": r[5],
            "last_ip": r[6], "agent_version": r[7], "clock_skew_s": r[8],
            "reports_total": r[9],
        })
    return out


# --- Enrollment tickets -----------------------------------------------------

def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode("utf-8")).hexdigest()


def create_ticket(con: DbConnection, server_name: str, *, ttl_minutes: int = TICKET_TTL_MINUTES) -> str:
    """Mint a single-use enrollment ticket.

    Only its hash is stored, so a database dump does not yield usable tickets and
    the value genuinely exists only in the installer the operator is holding.
    """
    init_node_db(con)
    ticket = "et_" + secrets.token_urlsafe(24)
    expires = datetime.now(tz=timezone.utc) + timedelta(minutes=ttl_minutes)
    con.execute(
        "INSERT INTO node_tickets(ticket_sha256, server_name, created_at_utc, expires_at_utc) "
        "VALUES (?,?,?,?)",
        (_ticket_hash(ticket), server_name, now_utc_iso(), expires.isoformat()),
    )
    con.commit()
    return ticket


def claim_ticket(con: DbConnection, ticket: str) -> str | None:
    """Burn a ticket and return the server it was minted for, or None.

    The claim is a conditional UPDATE rather than a SELECT followed by a write,
    so two installers racing on the same ticket cannot both succeed.
    """
    init_node_db(con)
    cur = con.execute(
        "UPDATE node_tickets SET claimed_at_utc = ? "
        "WHERE ticket_sha256 = ? AND claimed_at_utc IS NULL AND expires_at_utc > ?",
        (now_utc_iso(), _ticket_hash(ticket), now_utc_iso()),
    )
    if int(getattr(cur, "rowcount", 0) or 0) != 1:
        con.commit()
        return None
    row = con.execute(
        "SELECT server_name FROM node_tickets WHERE ticket_sha256 = ?",
        (_ticket_hash(ticket),),
    ).fetchone()
    con.commit()
    if not row:
        return None
    return row["server_name"] if isinstance(row, dict) else row[0]


# --- Audit trail ------------------------------------------------------------

def record_event(
    con: DbConnection,
    *,
    kind: str,
    key_id: str | None,
    server_name: str | None,
    detail: str | None = None,
) -> None:
    """Append to the node audit trail.

    Deliberately never records request bodies or headers — this table must not
    become the place where a fleet's auth logs and enrollment secrets end up.
    """
    try:
        con.execute(
            "INSERT INTO node_events(ts_utc, key_id, server_name, kind, detail) "
            "VALUES (?,?,?,?,?)",
            (now_utc_iso(), key_id, server_name, kind, (detail or "")[:500] or None),
        )
    except Exception:
        logger.exception("Could not record node event %s", kind)


def recent_events(con: DbConnection, *, limit: int = 100) -> list[dict]:
    init_node_db(con)
    rows = con.execute(
        "SELECT ts_utc, key_id, server_name, kind, detail FROM node_events "
        "ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [
        dict(r) if isinstance(r, dict) else {
            "ts_utc": r[0], "key_id": r[1], "server_name": r[2], "kind": r[3], "detail": r[4]
        }
        for r in rows
    ]
