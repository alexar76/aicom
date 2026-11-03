"""Versioned database migrations for AIMarket Hub.

Manages schema creation and upgrades across SQLite and PostgreSQL.
Each migration has up/down SQL written for SQLite. The PostgresBackend
automatically translates SQL via sqlite_to_pg().

A `_migrations` table tracks applied versions.

CLI usage:
    python -m aimarket_hub.migrations up       # Apply pending migrations
    python -m aimarket_hub.migrations down     # Roll back last migration
    python -m aimarket_hub.migrations status   # Show migration status
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any

from aimarket_hub.db_backend import DBBackend, create_backend

logger = logging.getLogger(__name__)

# ── Migration Registry ──────────────────────────────────────────────

MIGRATIONS: list[tuple[int, str, str, str]] = []


def _register(version: int, name: str, up: str, down: str) -> None:
    MIGRATIONS.append((version, name, up, down))


# Tables owned by the payment-channel ledger (channels.py). The ledger lives in its
# OWN database file (AIMARKET_CHANNELS_DB_PATH) and must therefore apply a SUBSET of
# the registry. That subset is DERIVED from the DDL below (see channel_ledger_versions)
# rather than hand-pinned to a version number: a hand-maintained pin silently skips the
# next channels migration, which is how a ledger ends up running against a schema it
# thinks it has.
CHANNEL_LEDGER_TABLES: tuple[str, ...] = (
    "channels",
    "debited_receipts",
    "consumed_deposits",
    "channel_holds",
    "channel_payout_obligations",
)


# All DDL is written for SQLite. PostgresBackend.executescript()
# translates to PostgreSQL dialect automatically (sqlite_to_pg):
#   INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
#   REAL → DOUBLE PRECISION
#   datetime('now') → NOW()
#   INSERT OR REPLACE → INSERT ... ON CONFLICT DO UPDATE
#   PRAGMA → (removed for PG)

# 001: Core hub tables (capabilities, peers)
_register(1, "001_core_tables", """
CREATE TABLE IF NOT EXISTS capabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT 'v1',
    description TEXT DEFAULT '',
    input_schema TEXT DEFAULT '{}',
    output_schema TEXT DEFAULT '{}',
    price_per_call_usd REAL DEFAULT 0.35,
    p50_latency_ms INTEGER DEFAULT 3000,
    success_rate_30d REAL DEFAULT 0.97,
    source_hub TEXT NOT NULL,
    source_hub_name TEXT DEFAULT '',
    routed_price_usd REAL,
    routing_fee_bps INTEGER DEFAULT 0,
    trust_score REAL DEFAULT 0.0,
    agent TEXT DEFAULT '',
    prompt_template TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(capability_id, product_id, source_hub)
);

CREATE INDEX IF NOT EXISTS idx_caps_source ON capabilities(source_hub);
CREATE INDEX IF NOT EXISTS idx_caps_cid ON capabilities(capability_id);

CREATE TABLE IF NOT EXISTS peers (
    url TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    capabilities_count INTEGER DEFAULT 0,
    last_crawl TEXT DEFAULT '',
    trust_score REAL DEFAULT 0.0,
    well_known_url TEXT DEFAULT '',
    manifest_url TEXT DEFAULT '',
    public_key TEXT DEFAULT '',
    depth INTEGER DEFAULT 0,
    discoverer TEXT DEFAULT '',
    status TEXT DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_peers_status ON peers(status);
""", """
DROP TABLE IF EXISTS capabilities;
DROP TABLE IF EXISTS peers;
""")

# 002: Invocation stats
_register(2, "002_invocation_stats", """
CREATE TABLE IF NOT EXISTS invocation_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    capability_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    source_hub TEXT NOT NULL,
    price_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 0,
    timestamp TEXT DEFAULT (datetime('now')),
    consumer_hub TEXT DEFAULT 'local'
);

CREATE INDEX IF NOT EXISTS idx_stats_ts ON invocation_stats(timestamp);
""", """
DROP TABLE IF EXISTS invocation_stats;
""")

# 003: Reputation events
_register(3, "003_reputation_events", """
CREATE TABLE IF NOT EXISTS reputation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    provider_hub TEXT NOT NULL,
    capability_id TEXT,
    timestamp TEXT DEFAULT (datetime('now')),
    price_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    consumer_hub TEXT NOT NULL,
    signature TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_reputation_provider ON reputation_events(provider_hub);
""", """
DROP TABLE IF EXISTS reputation_events;
""")

# 004: Payment channels
_register(4, "004_channels", """
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,
    balance_cents INTEGER NOT NULL,
    original_deposit_cents INTEGER NOT NULL,
    used_cents INTEGER NOT NULL DEFAULT 0,
    token TEXT NOT NULL DEFAULT 'USDT',
    chain TEXT NOT NULL DEFAULT 'base',
    wallet TEXT NOT NULL DEFAULT '',
    tx_hash TEXT NOT NULL DEFAULT '',
    recipient TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    opened_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT NOT NULL,
    settle_tx_hash TEXT NOT NULL DEFAULT '',
    closed_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_channels_status ON channels(status);
CREATE INDEX IF NOT EXISTS idx_channels_wallet ON channels(wallet);
CREATE INDEX IF NOT EXISTS idx_channels_expires ON channels(expires_at) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS debited_receipts (
    receipt_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
""", """
DROP TABLE IF EXISTS debited_receipts;
DROP TABLE IF EXISTS channels;
""")

# 005: Provenance receipts
_register(5, "005_provenance_receipts", """
CREATE TABLE IF NOT EXISTS provenance_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id TEXT NOT NULL UNIQUE,
    model_id TEXT NOT NULL,
    provider_hub TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_hash TEXT NOT NULL,
    parent_receipts TEXT DEFAULT '[]',
    timestamp TEXT NOT NULL,
    issuer_pubkey_b64 TEXT NOT NULL,
    proof_value TEXT NOT NULL,
    tee_attestation TEXT,
    latency_ms INTEGER DEFAULT 0,
    price_usd REAL DEFAULT 0.0,
    invocation_nonce TEXT DEFAULT '',
    reputation_score REAL,
    raw_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_prov_receipt_id ON provenance_receipts(receipt_id);
CREATE INDEX IF NOT EXISTS idx_prov_model ON provenance_receipts(model_id);
CREATE INDEX IF NOT EXISTS idx_prov_provider ON provenance_receipts(provider_hub);
CREATE INDEX IF NOT EXISTS idx_prov_timestamp ON provenance_receipts(timestamp);
""", """
DROP TABLE IF EXISTS provenance_receipts;
""")

# 006: Peer self-declared categories (federation discovery / monitor filtering)
# `down` actually drops the column (SQLite >= 3.35 / PostgreSQL) so a
# rollback→reapply round-trip is clean — a no-op down would unregister the
# migration while leaving the column, making the next `up` fail with
# "duplicate column" and aborting hub startup.
_register(6, "006_peer_categories", """
ALTER TABLE peers ADD COLUMN categories TEXT DEFAULT '[]';
""", """
ALTER TABLE peers DROP COLUMN categories;
""")

# 007: Per-channel debit secret (SHA-256 hash). Channels opened after this migration return a
# one-time `channel_secret` to the owner; debit requires it (PAYAUTH — a leaked channel id alone
# can no longer drain the channel). Legacy channels (empty hash) keep working for back-compat.
_register(7, "007_channel_secret", """
ALTER TABLE channels ADD COLUMN secret_hash TEXT NOT NULL DEFAULT '';
""", """
ALTER TABLE channels DROP COLUMN secret_hash;
""")

# 008: Operator-approved federation peers (anti-TOFU). A peer's manifests are indexed only when
# trusted=1 — set by an out-of-band seed pin or explicit operator approval. First contact (and
# every subsequent crawl) of an unapproved peer records it but never indexes, so a malicious hub
# can't inject capabilities just by being crawled twice.
_register(8, "008_peer_trusted", """
ALTER TABLE peers ADD COLUMN trusted INTEGER NOT NULL DEFAULT 0;
""", """
ALTER TABLE peers DROP COLUMN trusted;
""")

# 009: Direct invoke URL for community-published capabilities
_register(9, "009_capability_invoke_url", """
ALTER TABLE capabilities ADD COLUMN invoke_url TEXT DEFAULT '';
""", """
ALTER TABLE capabilities DROP COLUMN invoke_url;
""")

# 010: Community supply security (stake, LUMEN graph, publisher identity)
_register(10, "010_supply_security", """
ALTER TABLE capabilities ADD COLUMN publisher_id TEXT DEFAULT '';
ALTER TABLE capabilities ADD COLUMN provider_pubkey TEXT DEFAULT '';
ALTER TABLE capabilities ADD COLUMN stake_usd REAL DEFAULT 0;

CREATE TABLE IF NOT EXISTS supply_stakes (
    publisher_id TEXT PRIMARY KEY,
    amount_usd REAL NOT NULL DEFAULT 0,
    slashed_usd REAL NOT NULL DEFAULT 0,
    token TEXT DEFAULT 'USDC',
    tx_hash TEXT DEFAULT '',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS supply_publish_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publisher_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    invoke_url TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_supply_publish_pub ON supply_publish_events(publisher_id, created_at);
CREATE INDEX IF NOT EXISTS idx_supply_publish_url ON supply_publish_events(invoke_url);

CREATE TABLE IF NOT EXISTS trust_graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    weight REAL NOT NULL,
    event_type TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_trust_edges_dst ON trust_graph_edges(dst);
""", """
DROP TABLE IF EXISTS trust_graph_edges;
DROP TABLE IF EXISTS supply_publish_events;
DROP TABLE IF EXISTS supply_stakes;
""")


# 011: Self-bond — consumer-side cost/conduct bond (ARGUS self-slash enforcement).
# The agent stakes (supply_stakes) and registers a bonded spend CEILING + the client
# self-bond commitment; /self-bond/slash slashes that stake on a declared-vs-observed
# breach and federates the attestation through the same slash registry publishers use.
_register(11, "011_self_bonds", """
CREATE TABLE IF NOT EXISTS self_bonds (
    agent_id TEXT PRIMARY KEY,
    evm_address TEXT DEFAULT '',
    ceiling_usd REAL NOT NULL DEFAULT 0,
    bond_usd REAL NOT NULL DEFAULT 0,
    token TEXT DEFAULT 'USDC',
    commitment TEXT DEFAULT '',
    slashed_usd REAL NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
""", """
DROP TABLE IF EXISTS self_bonds;
""")


# 012: Consumed deposit transactions — single-use guard for channel funding.
# A verified on-chain deposit may fund exactly ONE channel. The verifier
# (web.backend...on_chain.verify_tx_payment) is stateless — it only checks
# recipient/amount/token/confirmations — so without this table a single real
# USDC deposit could be replayed to POST /channel/open unlimited times, each
# minting a channel with a full spendable balance (PAYAUTH-002, double-credit).
# The (chain, tx_hash) PRIMARY KEY makes the "claim" atomic even across worker
# processes/threads sharing the DB.
_register(12, "012_consumed_deposits", """
CREATE TABLE IF NOT EXISTS consumed_deposits (
    chain TEXT NOT NULL DEFAULT '',
    tx_hash TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    consumed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (chain, tx_hash)
);
""", """
DROP TABLE IF EXISTS consumed_deposits;
""")

_register(13, "013_capability_is_demo", """
ALTER TABLE capabilities ADD COLUMN is_demo INTEGER DEFAULT 0;
""", """
-- SQLite cannot DROP COLUMN in older versions; no-op down for is_demo
SELECT 1;
""")

# 014: Escrow holds for Pay-on-Verified settlement (auth/capture on payment channels).
# A hold reserves channel funds at invoke time (balance_cents drops immediately, so a
# pending verification can never be double-spent); capture moves the reservation into
# used_cents + debited_receipts, release restores balance. Keyed by the invoke receipt
# nonce so hold replay protection is exactly as strong as debit replay protection.
_register(14, "014_channel_holds", """
CREATE TABLE IF NOT EXISTS channel_holds (
    receipt_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'held',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_holds_channel ON channel_holds(channel_id, status);
""", """
DROP TABLE IF EXISTS channel_holds;
""")

# 015: Pay-on-Verified settlement records — one row per verified invoke, carrying the
# buyer intent + provider output for the background Metis verdict, the evolving
# verification envelope, and the final receipt served by GET /verification/{nonce}.
# Pending rows are re-queued on hub startup so a restart never strands a hold.
_register(15, "015_verified_settlements", """
CREATE TABLE IF NOT EXISTS verified_settlements (
    nonce TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    channel_id TEXT DEFAULT '',
    provider_id TEXT DEFAULT '',
    price_usd REAL DEFAULT 0,
    intent TEXT DEFAULT '',
    output_json TEXT DEFAULT '{}',
    mode TEXT DEFAULT 'fast',
    status TEXT NOT NULL DEFAULT 'pending',
    envelope_json TEXT DEFAULT '{}',
    rejection_json TEXT DEFAULT '',
    receipt_json TEXT DEFAULT '{}',
    attempts INTEGER DEFAULT 0,
    engine_attempts INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_vs_status ON verified_settlements(status);
""", """
DROP TABLE IF EXISTS verified_settlements;
""")

# 016: Slash calibration + durable federation log.
# supply_fault_events replaces the in-memory consecutive-failure counter (a restart
# must not amnesty a failure streak); supply_slash_events records every individual
# slash so the cool-down and rolling daily cap survive restarts and stay auditable;
# slash_attestations persists the federated SlashRegistry (this hub's authored
# signed log — including its monotonic seq — plus verified peer entries with their
# strong/weak evidence tier).
_register(16, "016_slash_calibration", """
CREATE TABLE IF NOT EXISTS supply_fault_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publisher_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    product_id TEXT DEFAULT '',
    capability_id TEXT DEFAULT '',
    consumer_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_supply_faults ON supply_fault_events(publisher_id, kind, created_at);

CREATE TABLE IF NOT EXISTS supply_slash_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publisher_id TEXT NOT NULL,
    amount_usd REAL NOT NULL DEFAULT 0,
    reason TEXT DEFAULT '',
    evidence_kind TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_supply_slash_pub ON supply_slash_events(publisher_id, created_at);

CREATE TABLE IF NOT EXISTS slash_attestations (
    issuer_hub TEXT NOT NULL,
    seq INTEGER NOT NULL,
    envelope_json TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'strong',
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (issuer_hub, seq)
);
""", """
DROP TABLE IF EXISTS slash_attestations;
DROP TABLE IF EXISTS supply_slash_events;
DROP TABLE IF EXISTS supply_fault_events;
""")


# 017: Honest channel accounting — payout obligations + hold resolution notes.
#
# channel_payout_obligations: a channel deposit is verified as a payment to the
# PLATFORM's settlement wallet, so the unspent remainder at close/expiry is already the
# operator's money. Nothing in this process may send value back, so the remainder is
# recorded as an explicit, queryable DEBT to the depositor instead of being logged as a
# "refund" that never happened (ACCT-001). One row per channel (channel_id PRIMARY KEY)
# keeps close + expiry-sweep idempotent.
#
# channel_holds.resolution_note: why a hold left 'held' — in particular the reaper's
# auditable record for an orphaned hold (hold committed, settlement row never written),
# which previously froze a buyer's balance forever with no reaper.
_register(17, "017_channel_payout_obligations", """
CREATE TABLE IF NOT EXISTS channel_payout_obligations (
    channel_id TEXT PRIMARY KEY,
    wallet TEXT NOT NULL DEFAULT '',
    chain TEXT NOT NULL DEFAULT '',
    token TEXT NOT NULL DEFAULT '',
    amount_cents INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL DEFAULT 'close_remainder',
    status TEXT NOT NULL DEFAULT 'owed',
    deposit_tx_hash TEXT NOT NULL DEFAULT '',
    payout_tx_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    settled_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_obligations_status ON channel_payout_obligations(status);
CREATE INDEX IF NOT EXISTS idx_obligations_wallet ON channel_payout_obligations(wallet, status);

ALTER TABLE channel_holds ADD COLUMN resolution_note TEXT NOT NULL DEFAULT '';
""", """
ALTER TABLE channel_holds DROP COLUMN resolution_note;
DROP TABLE IF EXISTS channel_payout_obligations;
""")


# 018: escrow-backed channels (opt-in bridge). A channel funded by an on-chain
# AIMarketEscrow deposit records WHICH escrow channel backs it, so the invoke path can
# check a buyer's DebitAuthorization against the right contract state and the mirror knows
# what to submit against. Empty for every transfer-funded channel, which is all of them
# until an operator enables the bridge.
_register(18, "018_channel_escrow_binding", """
ALTER TABLE channels ADD COLUMN escrow_channel TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_channels_escrow ON channels(escrow_channel);
""", """
DROP INDEX IF EXISTS idx_channels_escrow;
ALTER TABLE channels DROP COLUMN escrow_channel;
""")


# 019: supply_fault_events.consumer_id — griefing-resistant slash calibration needs
# distinct consumers. Migration 016's CREATE included the column in source, but hubs
# that applied an earlier 016 CREATE (without it) never got an ALTER. ADD COLUMN is
# idempotent in apply() via duplicate-column tolerance below.
_register(19, "019_supply_fault_consumer_id", """
ALTER TABLE supply_fault_events ADD COLUMN consumer_id TEXT DEFAULT '';
""", """
ALTER TABLE supply_fault_events DROP COLUMN consumer_id;
""")

# 020: Signed supply-chain admission decisions.  The table intentionally stores
# only the manifest digest and bounded findings, never the submitted manifest or
# its evidence URLs.  Alien Monitor can therefore read the public audit stream
# without gaining access to customer dossiers.
_register(20, "020_supply_chain_admission", """
CREATE TABLE IF NOT EXISTS supply_chain_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL UNIQUE,
    publisher_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'advisory',
    status TEXT NOT NULL DEFAULT 'unavailable',
    decision TEXT DEFAULT '',
    score INTEGER,
    risk_tier TEXT DEFAULT '',
    findings_json TEXT DEFAULT '[]',
    remediations_json TEXT DEFAULT '[]',
    owasp_risks_json TEXT DEFAULT '[]',
    signature TEXT DEFAULT '',
    auditor_pubkey TEXT DEFAULT '',
    metis_status TEXT DEFAULT 'skipped',
    metis_verification_id TEXT DEFAULT '',
    metis_detail_json TEXT DEFAULT '{}',
    error_code TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_supply_audits_created
ON supply_chain_audits(created_at);
CREATE INDEX IF NOT EXISTS idx_supply_audits_capability
ON supply_chain_audits(capability_id, product_id);
CREATE INDEX IF NOT EXISTS idx_supply_audits_metis
ON supply_chain_audits(metis_status, updated_at);
""", """
DROP TABLE IF EXISTS supply_chain_audits;
""")


# 021: What the admission gate actually verified, plus the signed observer reports
# that make a declared permission falsifiable.  Both are bounded: the audit row
# keeps counts and booleans (never an evidence URL), and a violation report keeps
# only the digest of the declaration it contradicts — never the dossier.
_register(21, "021_supply_admission_attestations", """
ALTER TABLE supply_chain_audits ADD COLUMN attestations_json TEXT DEFAULT '{}';
ALTER TABLE supply_chain_audits ADD COLUMN permissions_sha256 TEXT DEFAULT '';
ALTER TABLE supply_chain_audits ADD COLUMN permissions_json TEXT DEFAULT '{}';

CREATE TABLE IF NOT EXISTS supply_permission_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publisher_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    permission TEXT NOT NULL,
    permissions_sha256 TEXT NOT NULL,
    reporter_pubkey TEXT NOT NULL,
    signature TEXT NOT NULL,
    consumer_id TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE (capability_id, permission, permissions_sha256, reporter_pubkey)
);
CREATE INDEX IF NOT EXISTS idx_supply_violations_capability
ON supply_permission_violations(product_id, capability_id, permissions_sha256);
CREATE INDEX IF NOT EXISTS idx_supply_violations_publisher
ON supply_permission_violations(publisher_id, created_at);
""", """
DROP TABLE IF EXISTS supply_permission_violations;
ALTER TABLE supply_chain_audits DROP COLUMN permissions_json;
ALTER TABLE supply_chain_audits DROP COLUMN permissions_sha256;
ALTER TABLE supply_chain_audits DROP COLUMN attestations_json;
""")

# 022: Surface federation pin mismatches to operators. The crawler used to only
# log "public key changed! Rejecting (possible takeover)" and leave the peer
# looking healthy on /federation/peers — ATLAS stayed frozen in the catalogue
# for days with no UI signal. Persist the reject reason + advertised key; keep
# status=key_mismatch so the peers list can show it without reading logs.
_register(22, "022_peer_pin_reject", """
ALTER TABLE peers ADD COLUMN pin_reject_reason TEXT DEFAULT '';
ALTER TABLE peers ADD COLUMN advertised_public_key TEXT DEFAULT '';
""", """
ALTER TABLE peers DROP COLUMN advertised_public_key;
ALTER TABLE peers DROP COLUMN pin_reject_reason;
""")

# ── Subsystem selection ─────────────────────────────────────────────


def _touches_table(sql: str, table: str) -> bool:
    """Whether a migration's DDL references `table` as a table name.

    Word-boundary match so a COLUMN named channel_id or an index named
    idx_channels_status does not count as touching the `channels` table.
    """
    return re.search(rf"(?<![\w]){re.escape(table)}(?![\w])", sql) is not None


# Open federation (AIMARKET_FEDERATION_OPEN). Three additions, all inert while the
# flag is off:
#   * peers.first_seen        — when this hub first heard of the peer, so a newly
#                               appeared stranger can be told apart from an old one.
#   * peer_preview_capabilities — what a PENDING peer claims to offer. Deliberately a
#                               SEPARATE table, never `capabilities`: search, routing,
#                               invoke and the published manifest all read
#                               `capabilities`, so an unapproved peer's rows cannot
#                               reach any of them even if a future query forgets a
#                               filter. The isolation is structural, not a WHERE clause.
#   * federation_inbound      — who crawled US. Until now a peer could index this hub
#                               and the operator had no way to know it existed.
_register(23, "023_open_federation", """
    ALTER TABLE peers ADD COLUMN first_seen TEXT DEFAULT '';

    CREATE TABLE IF NOT EXISTS peer_preview_capabilities (
        peer_url TEXT NOT NULL,
        capability_id TEXT NOT NULL,
        product_id TEXT NOT NULL DEFAULT '',
        name TEXT DEFAULT '',
        description TEXT DEFAULT '',
        price_per_call_usd REAL DEFAULT 0,
        categories TEXT DEFAULT '[]',
        seen_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (peer_url, capability_id, product_id)
    );

    CREATE INDEX IF NOT EXISTS idx_preview_peer ON peer_preview_capabilities(peer_url);

    CREATE TABLE IF NOT EXISTS federation_inbound (
        hub_url TEXT PRIMARY KEY,
        user_agent TEXT DEFAULT '',
        first_seen TEXT DEFAULT (datetime('now')),
        last_seen TEXT DEFAULT (datetime('now')),
        hits INTEGER DEFAULT 1
    );
""", """
    DROP TABLE IF EXISTS federation_inbound;
    DROP INDEX IF EXISTS idx_preview_peer;
    DROP TABLE IF EXISTS peer_preview_capabilities;
""")


# Credits (AIMARKET_CREDITS_ENABLED) — the payment rail that needs no chain. Three tables,
# all inert while the flag is off:
#   * credit_accounts — prepaid balances in MILLICENTS. Not cents: the channel ledger bills
#                       whole cents rounded up, which cannot express the $0.0059 this
#                       ecosystem actually averages per call. `held_mc` is the reservation
#                       column, kept separate from `balance_mc` so an in-flight invoke's
#                       money is visibly neither spendable nor spent.
#   * credit_holds    — one row per reservation, keyed on the invoke's receipt id, so a
#                       hold survives a crash and can be released by id exactly once.
#   * collateral_mc   — a publisher's posted stake. Deliberately NOT `spent_mc`: collateral is
#                       money the operator is holding against future misbehaviour and may have
#                       to return, so counting it as revenue overstates earnings by the whole
#                       stake the moment somebody publishes.
#   * credit_ledger   — append-only history. The operator holds prepaid money (the same
#                       custody ACCT-001 describes for channels), so every movement needs
#                       a row that can be shown to whoever paid.
_register(24, "024_credits_rail", """
    CREATE TABLE IF NOT EXISTS credit_accounts (
        account_id TEXT PRIMARY KEY,
        key_hash TEXT NOT NULL UNIQUE,
        label TEXT DEFAULT '',
        balance_mc INTEGER NOT NULL DEFAULT 0,
        held_mc INTEGER NOT NULL DEFAULT 0,
        spent_mc INTEGER NOT NULL DEFAULT 0,
        granted_mc INTEGER NOT NULL DEFAULT 0,
        collateral_mc INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS credit_holds (
        receipt_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        amount_mc INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'held',
        created_at TEXT DEFAULT (datetime('now')),
        resolved_at TEXT DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_credit_holds_account ON credit_holds(account_id);

    CREATE TABLE IF NOT EXISTS credit_ledger (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        amount_mc INTEGER NOT NULL,
        receipt_id TEXT DEFAULT '',
        note TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_credit_ledger_account ON credit_ledger(account_id);
""", """
    DROP INDEX IF EXISTS idx_credit_ledger_account;
    DROP TABLE IF EXISTS credit_ledger;
    DROP INDEX IF EXISTS idx_credit_holds_account;
    DROP TABLE IF EXISTS credit_holds;
    DROP TABLE IF EXISTS credit_accounts;
""")



# x402 receivables (AIMARKET_X402_ACCEPT). A verified EIP-3009 authorization is money the
# payer has PROMISED on chain, not money that has arrived: submitting it needs an RPC and
# gas, and that happens out of band like the escrow sweep. One row per authorization, keyed
# on the nonce so a replay cannot buy a second call, and carrying its own settled/failed
# state so the unsettled total is a number the operator can actually see.
_register(25, "025_x402_payments", """
    CREATE TABLE IF NOT EXISTS x402_payments (
        nonce TEXT PRIMARY KEY,
        payer TEXT NOT NULL,
        amount_atomic TEXT NOT NULL DEFAULT '0',
        amount_usd REAL NOT NULL DEFAULT 0,
        asset TEXT DEFAULT '',
        network TEXT DEFAULT '',
        receipt_id TEXT DEFAULT '',
        capability_id TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'accepted',
        settle_tx_hash TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        settled_at TEXT DEFAULT ''
    );

    CREATE INDEX IF NOT EXISTS idx_x402_status ON x402_payments(status);
    CREATE INDEX IF NOT EXISTS idx_x402_payer ON x402_payments(payer);
""", """
    DROP INDEX IF EXISTS idx_x402_payer;
    DROP INDEX IF EXISTS idx_x402_status;
    DROP TABLE IF EXISTS x402_payments;
""")


# Idempotent operator/checkout top-ups. Payment processors retry webhooks and operators
# retry commands after timeouts; without a unique external reference either case credits
# the same money twice. The row is committed atomically with the balance movement.
_register(26, "026_credit_topup_references", """
    CREATE TABLE IF NOT EXISTS credit_topups (
        reference TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        amount_mc INTEGER NOT NULL,
        note TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_credit_topups_account ON credit_topups(account_id);
""", """
    DROP INDEX IF EXISTS idx_credit_topups_account;
    DROP TABLE IF EXISTS credit_topups;
""")


# Post-quarantine assay dossiers. A pending peer's well-known copy is not evidence;
# this table stores the last deterministic scorecard (crypto / origin / sandbox
# receipt). Verdict never writes ``peers.trusted``. See federation_assay.py.
_register(27, "027_peer_assays", """
    CREATE TABLE IF NOT EXISTS peer_assays (
        peer_url TEXT PRIMARY KEY,
        verdict TEXT NOT NULL,
        checks_json TEXT NOT NULL DEFAULT '[]',
        sandbox_json TEXT NOT NULL DEFAULT '{}',
        advertised_key TEXT DEFAULT '',
        ran_at TEXT DEFAULT (datetime('now')),
        note TEXT DEFAULT ''
    );
""", """
    DROP TABLE IF EXISTS peer_assays;
""")


_register(28, "028_peer_self_description", """
    -- What the peer says about itself, kept apart from what this hub determined.
    -- Every one of these is already published in /.well-known/ai-market.json and was read,
    -- used for one decision, and thrown away — so the monitor grew its own hand-written
    -- tables of the same facts, which then drifted from the peers they described.
    -- `declared_id` is a CLAIM and is never an identity: see aimarket_hub/peer_identity.py.
    -- `mcp_endpoint` is stored for display only. Routing re-resolves it live, because a
    -- stored endpoint is a stale endpoint the moment a peer moves.
    ALTER TABLE peers ADD COLUMN description TEXT DEFAULT '';
    ALTER TABLE peers ADD COLUMN hub_version TEXT DEFAULT '';
    ALTER TABLE peers ADD COLUMN declared_id TEXT DEFAULT '';
    ALTER TABLE peers ADD COLUMN mcp_endpoint TEXT DEFAULT '';
""", """
    ALTER TABLE peers DROP COLUMN mcp_endpoint;
    ALTER TABLE peers DROP COLUMN declared_id;
    ALTER TABLE peers DROP COLUMN hub_version;
    ALTER TABLE peers DROP COLUMN description;
""")


_register(29, "029_peer_pq_identity", """
    -- The peer's POST-QUANTUM public key, pinned the same way its Ed25519 key is.
    --
    -- Without this column `verify_hybrid` reads `pq_public_key` out of the signature object,
    -- which makes the PQ layer useless against the only adversary it exists for: one who can
    -- forge Ed25519 forges it against the pinned classical key and attaches an ML-DSA keypair of
    -- their own. A post-quantum signature is worth exactly what the pinning of its public key is
    -- worth.
    --
    -- It has to be collected NOW, while classical signatures can still authenticate it. After
    -- Ed25519 falls, a PQ key seen for the first time cannot be attributed to anyone.
    --
    -- `advertised_pq_public_key` mirrors `advertised_public_key`: the last key that FAILED the
    -- pin check, kept so the federation desk can show what changed instead of a healthy-looking
    -- row beside a frozen catalogue.
    ALTER TABLE peers ADD COLUMN pq_public_key TEXT DEFAULT '';
    ALTER TABLE peers ADD COLUMN advertised_pq_public_key TEXT DEFAULT '';
""", """
    ALTER TABLE peers DROP COLUMN advertised_pq_public_key;
    ALTER TABLE peers DROP COLUMN pq_public_key;
""")

_register(30, "030_peer_declared_contracts", """
    -- What the peer says it has ON CHAIN: its escrow contract, its settlement wallet and
    -- the settlement token, as read from its own well-known (JSON, bounded by
    -- contracts_declaration.sanitize).
    --
    -- Stored so we can RE-EXPORT it. A federation is cyclic, so a reader stops at the
    -- second hop and never fetches a peer's peers — which meant a stranger hub reached the
    -- map as a name, a capability count and nothing else. Its escrow is the one thing about
    -- it that anybody can verify without trusting anybody: an address either holds code and
    -- has transactions, or it does not. Passing it on turns "some hub over there" into
    -- something a viewer can open and check.
    --
    -- A claim, like every other `declared_` column, and named accordingly. The difference is
    -- that this claim is falsifiable, which is the whole point of carrying it.
    ALTER TABLE peers ADD COLUMN declared_contracts TEXT DEFAULT '{}';
""", """
    ALTER TABLE peers DROP COLUMN declared_contracts;
""")

_register(31, "031_reputation_event_replay_index", """
    -- Lookup index for the replay check in database.record_reputation_event.
    --
    -- Deliberately NOT unique: rows written before signatures were required carry an
    -- empty signature, and a unique constraint would either fail to build or force a
    -- destructive dedupe of live history. The application checks (consumer_hub,
    -- signature) before inserting; this index is what keeps that check O(log n) once
    -- the table is large.
    CREATE INDEX IF NOT EXISTS idx_reputation_sig ON reputation_events(consumer_hub, signature);
""", """
    DROP INDEX IF EXISTS idx_reputation_sig;
""")

_register(32, "032_invocation_outcome", """
    -- Incomplete-input refusals (ATLAS lat/lon required, watchbox without a bbox)
    -- used to land as success=0 and drag the public success rate. They stay on
    -- the tape as outcome='refused' and are scored separately from a real miss.
    ALTER TABLE invocation_stats ADD COLUMN outcome TEXT NOT NULL DEFAULT 'fail';
    UPDATE invocation_stats SET outcome='ok' WHERE success=1;
    UPDATE invocation_stats SET outcome='fail' WHERE success=0 AND outcome='fail';
""", """
    ALTER TABLE invocation_stats DROP COLUMN outcome;
""")


# 033: seller-direct market rail. A listing names the wallet USDC goes to;
# the hub verifies the transfer and never holds the money. Invoices bind a
# 402 nonce to one call the same way HESTIA does.
_register(33, "033_seller_direct_settle", """
    ALTER TABLE capabilities ADD COLUMN payout_address TEXT NOT NULL DEFAULT '';
    ALTER TABLE x402_payments ADD COLUMN pay_to TEXT NOT NULL DEFAULT '';
    CREATE TABLE IF NOT EXISTS settle_invoices (
        nonce TEXT PRIMARY KEY,
        capability_id TEXT NOT NULL,
        pay_to TEXT NOT NULL,
        amount_units TEXT NOT NULL,
        expires_at REAL NOT NULL,
        consumed_at REAL NOT NULL DEFAULT 0,
        tx_hash TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_x402_settle_tx ON x402_payments(settle_tx_hash);
    CREATE INDEX IF NOT EXISTS idx_settle_invoices_cap ON settle_invoices(capability_id);
""", """
    DROP INDEX IF EXISTS idx_settle_invoices_cap;
    DROP INDEX IF EXISTS idx_x402_settle_tx;
    DROP TABLE IF EXISTS settle_invoices;
    ALTER TABLE x402_payments DROP COLUMN pay_to;
    ALTER TABLE capabilities DROP COLUMN payout_address;
""")


# 034: agent mandates (aimarket-protocol/mandates.md). An owner's signed limits on what
# an agent key may spend, enforced here.
#   * mandates        — every registered mandate, keyed by its digest, with the chain
#                       position resolved at registration so admission is one lookup per link.
#   * mandate_owners  — root issuer DID → the credit account that pays for its chains.
#   * mandate_usage   — one counter per (mandate, period): `total`, `d:<UTC day>`,
#                       `p:<product>:<UTC day>`. Each is moved by a single conditional UPDATE
#                       (`spent + amount <= limit`), which is what makes a limit impossible to
#                       overrun with concurrent requests. (`period`, not `window`: WINDOW is a
#                       reserved word in PostgreSQL.)
#   * mandate_holds   — one row per (reservation, mandate). It remembers which periods it
#                       moved, so a release puts the money back into the counters it came from
#                       even after midnight has changed the current day.
#   * mandate_nonces  — request-proof replay guard; the PRIMARY KEY is the single winner.
# Amounts are µUSD in BIGINT: on PostgreSQL an INTEGER is int4, which tops out at $2,147.48
# and would turn the next reservation past it into a 500. (SQLite gives BIGINT the same
# 64-bit INTEGER affinity, so hubs that applied this before the change are unaffected, and
# no PostgreSQL hub had applied it.)
_register(34, "034_agent_mandates", """
    CREATE TABLE IF NOT EXISTS mandates (
        digest TEXT PRIMARY KEY,
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        parent_digest TEXT NOT NULL DEFAULT '',
        root_digest TEXT NOT NULL,
        root_issuer TEXT NOT NULL,
        depth INTEGER NOT NULL DEFAULT 0,
        valid_from TEXT NOT NULL,
        valid_until TEXT NOT NULL,
        document TEXT NOT NULL,
        registered_at TEXT DEFAULT (datetime('now')),
        revoked_at TEXT NOT NULL DEFAULT '',
        revoked_by TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_mandates_parent ON mandates(parent_digest);
    CREATE INDEX IF NOT EXISTS idx_mandates_root ON mandates(root_digest);

    CREATE TABLE IF NOT EXISTS mandate_owners (
        did TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        require_mandate INTEGER NOT NULL DEFAULT 0,
        linked_at TEXT DEFAULT (datetime('now'))
    );
    CREATE INDEX IF NOT EXISTS idx_mandate_owners_account ON mandate_owners(account_id);

    CREATE TABLE IF NOT EXISTS mandate_usage (
        digest TEXT NOT NULL,
        period TEXT NOT NULL,
        spent_micro BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (digest, period)
    );

    CREATE TABLE IF NOT EXISTS mandate_holds (
        receipt_id TEXT NOT NULL,
        digest TEXT NOT NULL,
        amount_micro BIGINT NOT NULL,
        periods TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'held',
        created_at TEXT DEFAULT (datetime('now')),
        resolved_at TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (receipt_id, digest)
    );
    CREATE INDEX IF NOT EXISTS idx_mandate_holds_digest ON mandate_holds(digest);

    CREATE TABLE IF NOT EXISTS mandate_nonces (
        agent TEXT NOT NULL,
        nonce TEXT NOT NULL,
        seen_at REAL NOT NULL,
        PRIMARY KEY (agent, nonce)
    );
    CREATE INDEX IF NOT EXISTS idx_mandate_nonces_seen ON mandate_nonces(seen_at);
""", """
    DROP INDEX IF EXISTS idx_mandate_nonces_seen;
    DROP TABLE IF EXISTS mandate_nonces;
    DROP INDEX IF EXISTS idx_mandate_holds_digest;
    DROP TABLE IF EXISTS mandate_holds;
    DROP TABLE IF EXISTS mandate_usage;
    DROP INDEX IF EXISTS idx_mandate_owners_account;
    DROP TABLE IF EXISTS mandate_owners;
    DROP INDEX IF EXISTS idx_mandates_root;
    DROP INDEX IF EXISTS idx_mandates_parent;
    DROP TABLE IF EXISTS mandates;
""")


# 035: subcontracting (aimarket-protocol/mandates.md §6). A provider that buys from another
# provider while serving a call.
#   * job_nodes  — the invocation tree: one row per call that joined a job.
#   * job_grants — the pass-through allowance of a job; the secret is stored hashed.
#   * credit_holds.parent_receipt_id — a child hold carved out of the job's allowance hold.
#     Releasing it returns the money to that allowance while the job is open, so a retry
#     can still be paid; capture spends it like any other hold.
_register(35, "035_subcontracting", """
    CREATE TABLE IF NOT EXISTS job_nodes (
        receipt_id TEXT PRIMARY KEY,
        job_id TEXT NOT NULL,
        parent_receipt TEXT NOT NULL DEFAULT '',
        depth INTEGER NOT NULL DEFAULT 0,
        product_id TEXT NOT NULL DEFAULT '',
        capability_id TEXT NOT NULL DEFAULT '',
        funded_by TEXT NOT NULL DEFAULT 'own',
        amount_micro BIGINT NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'running',
        receipt_digest TEXT NOT NULL DEFAULT '',
        created_at TEXT DEFAULT (datetime('now')),
        resolved_at TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_job_nodes_job ON job_nodes(job_id);
    CREATE INDEX IF NOT EXISTS idx_job_nodes_parent ON job_nodes(parent_receipt);

    CREATE TABLE IF NOT EXISTS job_grants (
        job_id TEXT PRIMARY KEY,
        grant_hash TEXT NOT NULL UNIQUE,
        root_receipt TEXT NOT NULL,
        allowance_receipt TEXT NOT NULL,
        account_id TEXT NOT NULL,
        mandate_digest TEXT NOT NULL DEFAULT '',
        allowance_micro BIGINT NOT NULL,
        max_depth INTEGER NOT NULL,
        expires_at REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT DEFAULT (datetime('now')),
        closed_at TEXT NOT NULL DEFAULT ''
    );

    -- The tree's size limits (calls per job, children per call) as counters moved by one
    -- conditional UPDATE each, not a COUNT(*) read before the insert: N concurrent joins
    -- would all read 15 and all insert.
    CREATE TABLE IF NOT EXISTS job_counters (
        counter TEXT PRIMARY KEY,
        n INTEGER NOT NULL DEFAULT 0
    );

    ALTER TABLE credit_holds ADD COLUMN parent_receipt_id TEXT NOT NULL DEFAULT '';
""", """
    ALTER TABLE credit_holds DROP COLUMN parent_receipt_id;
    DROP TABLE IF EXISTS job_counters;
    DROP TABLE IF EXISTS job_grants;
    DROP INDEX IF EXISTS idx_job_nodes_parent;
    DROP INDEX IF EXISTS idx_job_nodes_job;
    DROP TABLE IF EXISTS job_nodes;
""")


# 036: A2A tasks (a2a_tasks.py). The record a paying A2A client comes back to — pay for it,
# cancel it, read it again after a timeout. Not a ledger: money moves only in the invoke path.
#   * principal_hash — the account, mandate or anonymous caller the task belongs to, hashed;
#                      never a key or a proof.
#   * invoke_body    — base64 of the exact invoke bytes, kept only while the task can resume
#                      (waiting for payment or credentials) and emptied at a terminal state.
#   * revision       — every state change is one UPDATE conditional on it, so two follow-ups
#                      racing on one task cannot both run the invoke.
#   * the UNIQUE (principal_hash, context_id, message_id) index is the idempotency key: a
#     retried SendMessage finds its task instead of paying for a second one.
#   (`task_state`, not `state`: a keyword in PostgreSQL, if a non-reserved one.)
_register(36, "036_a2a_tasks", """
    CREATE TABLE IF NOT EXISTS a2a_tasks (
        task_id TEXT PRIMARY KEY,
        context_id TEXT NOT NULL,
        principal_hash TEXT NOT NULL,
        message_id TEXT NOT NULL,
        last_message_id TEXT NOT NULL DEFAULT '',
        task_state TEXT NOT NULL,
        product_id TEXT NOT NULL DEFAULT '',
        capability_id TEXT NOT NULL DEFAULT '',
        source_hub TEXT NOT NULL DEFAULT '',
        invoke_body TEXT NOT NULL DEFAULT '',
        invoke_sha256 TEXT NOT NULL DEFAULT '',
        x402_nonce TEXT NOT NULL DEFAULT '',
        status_json TEXT NOT NULL DEFAULT '{}',
        artifacts_json TEXT NOT NULL DEFAULT '[]',
        history_json TEXT NOT NULL DEFAULT '[]',
        metadata_json TEXT NOT NULL DEFAULT '{}',
        revision INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        expires_at REAL NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_a2a_tasks_message
        ON a2a_tasks(principal_hash, context_id, message_id);
    CREATE INDEX IF NOT EXISTS idx_a2a_tasks_principal ON a2a_tasks(principal_hash, updated_at);
    CREATE INDEX IF NOT EXISTS idx_a2a_tasks_state ON a2a_tasks(task_state, updated_at);
""", """
    DROP INDEX IF EXISTS idx_a2a_tasks_state;
    DROP INDEX IF EXISTS idx_a2a_tasks_principal;
    DROP INDEX IF EXISTS idx_a2a_tasks_message;
    DROP TABLE IF EXISTS a2a_tasks;
""")


# 037: Pay-on-Verified appeals (docs/pay-on-verified.md "Appeals"). With
# AIMARKET_APPEAL_WINDOW_S > 0 a genuine verdict on a PAID settlement is provisional: the
# invoke hold stays held until the window closes or an appeal to a second verifier resolves.
#   * verdict_json     — the first-instance verdict, written in the same statement that makes
#                        the row provisional, so finalizing it later (or after a restart)
#                        replays that verdict instead of asking a verifier again.
#   * appeal_deadline  — epoch seconds; 0 = the row was never appealable. REAL is DOUBLE
#                        PRECISION on PostgreSQL (db_backend), so the second is kept.
#   * appeal_by / appeal_rail / appeal_account / appeal_bond_usd — who appealed and where the
#                        bond is held ('channel' for the buyer, 'credits' for the seller).
#   * appeal_statement — the appellant's argument. Never served back by the public lookup,
#                        which carries only its digest.
#   * appeal_filed_at  — epoch seconds; bounds how long the appeal court may take.
#   * appeal_attempts  — calls made to the appeal court.
#   * appeal_json      — the court's outcome and the #1-vs-#2 agreement: the research record.
#   * final_json       — the decided final outcome, written by the SAME statement that claims
#                        the row into 'finalizing', so a re-run after a crash moves the money
#                        the way the winner decided and nobody decides twice.
_register(37, "037_verified_settlement_appeals", """
    ALTER TABLE verified_settlements ADD COLUMN verdict_json TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN appeal_deadline REAL NOT NULL DEFAULT 0;
    ALTER TABLE verified_settlements ADD COLUMN appeal_by TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN appeal_rail TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN appeal_account TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN appeal_bond_usd REAL NOT NULL DEFAULT 0;
    ALTER TABLE verified_settlements ADD COLUMN appeal_statement TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN appeal_filed_at REAL NOT NULL DEFAULT 0;
    ALTER TABLE verified_settlements ADD COLUMN appeal_attempts INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE verified_settlements ADD COLUMN appeal_json TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN final_json TEXT NOT NULL DEFAULT '';
    CREATE INDEX IF NOT EXISTS idx_vs_status_deadline ON verified_settlements(status, appeal_deadline);
""", """
    DROP INDEX IF EXISTS idx_vs_status_deadline;
    ALTER TABLE verified_settlements DROP COLUMN final_json;
    ALTER TABLE verified_settlements DROP COLUMN appeal_json;
    ALTER TABLE verified_settlements DROP COLUMN appeal_attempts;
    ALTER TABLE verified_settlements DROP COLUMN appeal_filed_at;
    ALTER TABLE verified_settlements DROP COLUMN appeal_statement;
    ALTER TABLE verified_settlements DROP COLUMN appeal_bond_usd;
    ALTER TABLE verified_settlements DROP COLUMN appeal_account;
    ALTER TABLE verified_settlements DROP COLUMN appeal_rail;
    ALTER TABLE verified_settlements DROP COLUMN appeal_by;
    ALTER TABLE verified_settlements DROP COLUMN appeal_deadline;
    ALTER TABLE verified_settlements DROP COLUMN verdict_json;
""")


# Migration 038 — what the job tree reports and commits to after the fact.
#   * job_nodes.work_receipt_id — the child's AWR/2 work receipt id. A parent receipt's
#     `parents` edge must carry the child RECEIPT's `id` (AWR SPEC §8.2 matches edges to
#     documents by it); the node id is the hub's bookkeeping name, which no bundle holds.
#   * job_grants.spent_micro / released_micro — how the allowance was settled, so
#     GET /jobs/{id} reports the same bill of materials the root response carried.
#   * mandates.credential_id — the credential's `id`, unique per issuer: one id, one
#     mandate, however its bytes are spelled (see MandateStore.register).
#   * mandate_holds.pending_back_micro — a give-back that arrived while its hold was still
#     open, applied by the settle that closes it (MandateStore.give_back).
_register(38, "038_job_receipts_and_settlement", """
    ALTER TABLE job_nodes ADD COLUMN work_receipt_id TEXT NOT NULL DEFAULT '';
    ALTER TABLE job_grants ADD COLUMN spent_micro BIGINT NOT NULL DEFAULT 0;
    ALTER TABLE job_grants ADD COLUMN released_micro BIGINT NOT NULL DEFAULT 0;
    ALTER TABLE job_grants ADD COLUMN settled_at TEXT NOT NULL DEFAULT '';
    ALTER TABLE mandates ADD COLUMN credential_id TEXT NOT NULL DEFAULT '';
    ALTER TABLE mandate_holds ADD COLUMN pending_back_micro BIGINT NOT NULL DEFAULT 0;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_mandates_credential_id
        ON mandates(issuer, credential_id) WHERE credential_id != '';
""", """
    ALTER TABLE mandate_holds DROP COLUMN pending_back_micro;
    DROP INDEX IF EXISTS idx_mandates_credential_id;
    ALTER TABLE mandates DROP COLUMN credential_id;
    ALTER TABLE job_grants DROP COLUMN settled_at;
    ALTER TABLE job_grants DROP COLUMN released_micro;
    ALTER TABLE job_grants DROP COLUMN spent_micro;
    ALTER TABLE job_nodes DROP COLUMN work_receipt_id;
""")


_register(39, "039_verification_worker_leases", """
    ALTER TABLE verified_settlements ADD COLUMN worker_token TEXT NOT NULL DEFAULT '';
    ALTER TABLE verified_settlements ADD COLUMN lease_until REAL NOT NULL DEFAULT 0;
""", """
    ALTER TABLE verified_settlements DROP COLUMN lease_until;
    ALTER TABLE verified_settlements DROP COLUMN worker_token;
""")


_register(40, "040_settle_invoice_secret", """
    ALTER TABLE settle_invoices ADD COLUMN secret TEXT NOT NULL DEFAULT '';
""", """
    ALTER TABLE settle_invoices DROP COLUMN secret;
""")


# 041: buying credits with USDC (aimarket_hub/topup.py, docs/credits-topup.md).
#   * credit_topup_quotes — what a top-up 402 promised: the EIP-3009 nonce the buyer signs,
#     the account the money is for, the exact amount and payee. The account is bound HERE,
#     at quote time, so a redemption credits the quoted account whoever presents it.
#     No payment secret is stored: nothing in a top-up needs one (see topup.py).
#     credited_at is epoch seconds, not datetime text: the daily limit compares it with a
#     number, which reads the same on SQLite and PostgreSQL whatever the session's zone.
#   * credit_accounts.topped_up_mc — credit bought with money, kept apart from granted_mc
#     (credit given away), which the signup-grant budget and the solvency report read.
_register(41, "041_credit_topup_quotes", """
    CREATE TABLE IF NOT EXISTS credit_topup_quotes (
        nonce TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        amount_units BIGINT NOT NULL,
        pay_to TEXT NOT NULL,
        token_contract TEXT NOT NULL,
        chain TEXT NOT NULL,
        chain_id BIGINT NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'quoted',
        tx_hash TEXT NOT NULL DEFAULT '',
        payer TEXT NOT NULL DEFAULT '',
        paid_units BIGINT NOT NULL DEFAULT 0,
        credited_mc BIGINT NOT NULL DEFAULT 0,
        reference TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '',
        redeeming_since REAL NOT NULL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now')),
        credited_at REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_topup_quotes_account ON credit_topup_quotes(account_id);
    ALTER TABLE credit_accounts ADD COLUMN topped_up_mc BIGINT NOT NULL DEFAULT 0;
""", """
    ALTER TABLE credit_accounts DROP COLUMN topped_up_mc;
    DROP INDEX IF EXISTS idx_topup_quotes_account;
    DROP TABLE IF EXISTS credit_topup_quotes;
""")


_register(42, "042_studio_paid_runs", """
    CREATE TABLE IF NOT EXISTS studio_paid_runs (
        run_id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL,
        state_json TEXT NOT NULL,
        busy INTEGER NOT NULL DEFAULT 0,
        updated_at REAL NOT NULL,
        expires_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_studio_paid_expiry ON studio_paid_runs(expires_at);
""", """
    DROP TABLE IF EXISTS studio_paid_runs;
""")


_register(43, "043_pipeline_invocations", """
    CREATE TABLE IF NOT EXISTS studio_pipeline_invocations (
        run_id TEXT PRIMARY KEY,
        context_json TEXT NOT NULL,
        busy INTEGER NOT NULL DEFAULT 1,
        response_json TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL
    );
""", """
    DROP TABLE IF EXISTS studio_pipeline_invocations;
""")


_register(44, "044_seller_operations", """
    CREATE TABLE IF NOT EXISTS seller_operations (
        operation_id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL,
        state_json TEXT NOT NULL,
        busy INTEGER NOT NULL DEFAULT 0,
        response_json TEXT NOT NULL DEFAULT '',
        updated_at REAL NOT NULL
    );
""", """
    DROP TABLE IF EXISTS seller_operations;
""")


_register(45, "045_pipeline_leases", """
    ALTER TABLE studio_pipeline_invocations ADD COLUMN lease_token TEXT NOT NULL DEFAULT '';
""", """
    ALTER TABLE studio_pipeline_invocations DROP COLUMN lease_token;
""")


_register(46, "046_pipeline_relay", """
    CREATE TABLE IF NOT EXISTS pipeline_relay_nonces (
        chain_id INTEGER NOT NULL, payer TEXT NOT NULL, next_nonce BIGINT NOT NULL,
        PRIMARY KEY (chain_id, payer)
    );
    CREATE TABLE IF NOT EXISTS pipeline_relay_budget (
        payer TEXT NOT NULL, day TEXT NOT NULL, reserved_wei BIGINT NOT NULL DEFAULT 0,
        PRIMARY KEY (payer, day)
    );
    CREATE TABLE IF NOT EXISTS pipeline_relay_payments (
        run_id TEXT NOT NULL, step_id TEXT NOT NULL, chain_id INTEGER NOT NULL,
        payer TEXT NOT NULL, nonce BIGINT NOT NULL, request_digest TEXT NOT NULL,
        payment_json TEXT NOT NULL, created_at REAL NOT NULL,
        PRIMARY KEY (run_id, step_id), UNIQUE (chain_id, payer, nonce)
    );
""", """
    DROP TABLE IF EXISTS pipeline_relay_payments;
    DROP TABLE IF EXISTS pipeline_relay_budget;
    DROP TABLE IF EXISTS pipeline_relay_nonces;
""")


_register(47, "047_pipeline_refunds", """
    CREATE TABLE IF NOT EXISTS pipeline_refunds (
        run_id TEXT NOT NULL, step_id TEXT NOT NULL, original_tx_hash TEXT NOT NULL UNIQUE,
        state_json TEXT NOT NULL, busy INTEGER NOT NULL DEFAULT 0,
        response_json TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL,
        PRIMARY KEY (run_id, step_id)
    );
""", """
    DROP TABLE IF EXISTS pipeline_refunds;
""")


_register(48, "048_studio_paid_runs_started", """
    ALTER TABLE studio_paid_runs ADD COLUMN started INTEGER NOT NULL DEFAULT 1;
""", """
    ALTER TABLE studio_paid_runs DROP COLUMN started;
""")


# What the write site knew about the caller that the row cannot show later (aimarket_hub/
# ecosystem.py): '' (the label decides when the feed is read), 'address' (an unbilled call
# straight from an ecosystem server), 'wallet' (paid by an ecosystem wallet), 'forwarded'
# (a peer hub or seller operation acting for someone else) or 'external' (matched an
# external.* entry). The address and wallet themselves are never stored. Existing rows get
# '' and keep their label-only classification: nothing to backfill from.
_register(49, "049_invocation_caller_class", """
    ALTER TABLE invocation_stats ADD COLUMN caller_class TEXT NOT NULL DEFAULT '';
""", """
    ALTER TABLE invocation_stats DROP COLUMN caller_class;
""")


# USDC that lands in the hub's top-up wallet, credited without anybody presenting it
# (aimarket_hub/deposit_watch.py):
#   * payer_wallets — a wallet whose plain transfers are an account's top-ups. One wallet, one
#     account: the address is the primary key.
#   * deposit_watch_cursor — the next block to read per chain:wallet, so a restart resumes.
#   * hub_deposits — every transfer seen, and what became of it (credited / unattributed /
#     credited_elsewhere); the unattributed ones are the operator's to-do and the alerter's page.
_register(50, "050_deposit_watch", """
    CREATE TABLE IF NOT EXISTS payer_wallets (
        address TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        linked_by TEXT NOT NULL,
        created_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_payer_wallets_account ON payer_wallets(account_id);
    CREATE TABLE IF NOT EXISTS deposit_watch_cursor (
        key TEXT PRIMARY KEY,
        next_block BIGINT NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS hub_deposits (
        tx_hash TEXT PRIMARY KEY,
        sender TEXT NOT NULL,
        amount_units BIGINT NOT NULL,
        block BIGINT NOT NULL,
        status TEXT NOT NULL,
        account_id TEXT NOT NULL DEFAULT '',
        detail TEXT NOT NULL DEFAULT '',
        seen_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_hub_deposits_status ON hub_deposits(status);
""", """
    DROP INDEX IF EXISTS idx_hub_deposits_status;
    DROP TABLE IF EXISTS hub_deposits;
    DROP TABLE IF EXISTS deposit_watch_cursor;
    DROP INDEX IF EXISTS idx_payer_wallets_account;
    DROP TABLE IF EXISTS payer_wallets;
""")


# Whether a capability's answer depends on its input (aimarket_hub/answer_dependence.py):
#   * answer_observations — one row per distinct input of a capability: digests only, never the input,
#     with when that answer was first and last seen for it.
#   * answer_probes — when the hub last asked a free federated capability itself.
_register(51, "051_answer_observations", """
    CREATE TABLE IF NOT EXISTS answer_observations (
        source_hub TEXT NOT NULL,
        product_id TEXT NOT NULL,
        capability_id TEXT NOT NULL,
        input_digest TEXT NOT NULL,
        answer_digest TEXT NOT NULL,
        answer_bytes INTEGER NOT NULL,
        first_seen DOUBLE PRECISION NOT NULL,
        last_seen DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (source_hub, product_id, capability_id, input_digest)
    );
    CREATE TABLE IF NOT EXISTS answer_probes (
        source_hub TEXT NOT NULL,
        product_id TEXT NOT NULL,
        capability_id TEXT NOT NULL,
        probed_at DOUBLE PRECISION NOT NULL,
        answered INTEGER NOT NULL,
        PRIMARY KEY (source_hub, product_id, capability_id)
    );
""", """
    DROP TABLE IF EXISTS answer_probes;
    DROP TABLE IF EXISTS answer_observations;
""")


# The caller's own public label for a call (models.normalize_purpose): "feed", "home-weather".
# PingBlip's owner read one feed as charged twice — the second gaia.weather.read was the
# hourly home-page reading. Existing rows get '' (no label was ever sent).
_register(52, "052_invocation_purpose", """
    ALTER TABLE invocation_stats ADD COLUMN purpose TEXT NOT NULL DEFAULT '';
""", """
    ALTER TABLE invocation_stats DROP COLUMN purpose;
""")

# Buyer-confirmed deliveries (deliveries.py): counters, not the seller's books. One row per
# transaction and kind; the buyer as a hash, so distinct buyers can be counted.
_register(53, "053_delivery_confirmations", """
    CREATE TABLE IF NOT EXISTS delivery_confirmations (
        id TEXT PRIMARY KEY,
        source_hub TEXT NOT NULL,
        product_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        buyer_hash TEXT NOT NULL,
        confirmed_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_delivery_confirmations_seller
        ON delivery_confirmations(source_hub, product_id, confirmed_at);
""", """
    DROP INDEX IF EXISTS idx_delivery_confirmations_seller;
    DROP TABLE IF EXISTS delivery_confirmations;
""")

# 054: Owner approval above a threshold (mandates.md §5.6). A mandate whose limits carry
# `approvalAbove` cannot spend more than that on one call until an owner of its funding
# account signs THAT call: these rows are the requests and the owners' answers.
#   * leaf_digest + body_sha256 — what was asked: the exact invoke bytes under the exact
#                                 mandate. At most one pending request per pair (partial index).
#   * max_micro                 — the ceiling the owner signs; the call may not reserve more.
#   * receipt_id                — the hold that used an approved request. Released with that
#                                 hold (the call did not happen), kept when it is captured.
# a2a_tasks.awaiting names the approval a task waits on, so the owner's answer can reach the
# task (and its push subscribers) without the agent asking.
_register(54, "054_mandate_approvals", """
    CREATE TABLE IF NOT EXISTS mandate_approvals (
        approval_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        leaf_digest TEXT NOT NULL,
        agent TEXT NOT NULL,
        capability_id TEXT NOT NULL,
        product_id TEXT NOT NULL DEFAULT '',
        source_hub TEXT NOT NULL DEFAULT '',
        body_sha256 TEXT NOT NULL,
        amount_micro BIGINT NOT NULL,
        max_micro BIGINT NOT NULL,
        threshold_micro BIGINT NOT NULL,
        status TEXT NOT NULL,
        receipt_id TEXT NOT NULL DEFAULT '',
        decided_by TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        decided_at REAL NOT NULL DEFAULT 0,
        expires_at REAL NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_mandate_approvals_pending
        ON mandate_approvals(leaf_digest, body_sha256) WHERE status = 'pending';
    CREATE INDEX IF NOT EXISTS idx_mandate_approvals_account ON mandate_approvals(account_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_mandate_approvals_receipt ON mandate_approvals(receipt_id);
    ALTER TABLE a2a_tasks ADD COLUMN awaiting TEXT NOT NULL DEFAULT '';
""", """
    ALTER TABLE a2a_tasks DROP COLUMN awaiting;
    DROP INDEX IF EXISTS idx_mandate_approvals_receipt;
    DROP INDEX IF EXISTS idx_mandate_approvals_account;
    DROP INDEX IF EXISTS idx_mandate_approvals_pending;
    DROP TABLE IF EXISTS mandate_approvals;
""")

# 055: A2A push notifications (docs/a2a.md "Push notifications"). One row per webhook a
# client registered for one of its tasks. The token and credentials are the client's own
# secrets for its webhook, kept only to be sent back to it; they leave with the task.
_register(55, "055_a2a_push_configs", """
    CREATE TABLE IF NOT EXISTS a2a_push_configs (
        task_id TEXT NOT NULL,
        config_id TEXT NOT NULL,
        url TEXT NOT NULL,
        token TEXT NOT NULL DEFAULT '',
        auth_scheme TEXT NOT NULL DEFAULT '',
        auth_credentials TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        last_status INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '',
        last_sent_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (task_id, config_id)
    );
""", """
    DROP TABLE IF EXISTS a2a_push_configs;
""")

# 056: Card top-ups through Stripe Checkout (card_topup.py, docs/credits-topup.md). One row
# per checkout the hub opened: the account it credits is bound here, never taken from Stripe's
# event, and the ledger line is referenced by the session id so a redelivered event credits once.
_register(56, "056_card_topups", """
    CREATE TABLE IF NOT EXISTS card_topups (
        topup_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        amount_cents BIGINT NOT NULL,
        charge_cents BIGINT NOT NULL,
        status TEXT NOT NULL,
        session_id TEXT NOT NULL DEFAULT '',
        checkout_url TEXT NOT NULL DEFAULT '',
        payment_intent TEXT NOT NULL DEFAULT '',
        livemode INTEGER NOT NULL DEFAULT 0,
        credited_mc BIGINT NOT NULL DEFAULT 0,
        detail TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        credited_at REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_card_topups_account ON card_topups(account_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_card_topups_intent ON card_topups(payment_intent);
""", """
    DROP INDEX IF EXISTS idx_card_topups_intent;
    DROP INDEX IF EXISTS idx_card_topups_account;
    DROP TABLE IF EXISTS card_topups;
""")

# 057: Who owed the sales tax on a card top-up (AIMARKET_CARD_TOPUP_TAX), kept on the row it was
# opened under, and the tax Stripe computed. A hub that changes the setting must not re-check an
# older checkout's figures under the new rule.
_register(57, "057_card_topup_tax", """
    ALTER TABLE card_topups ADD COLUMN tax_mode TEXT NOT NULL DEFAULT 'off';
    ALTER TABLE card_topups ADD COLUMN tax_behavior TEXT NOT NULL DEFAULT '';
    ALTER TABLE card_topups ADD COLUMN tax_cents BIGINT NOT NULL DEFAULT 0;
""", """
    ALTER TABLE card_topups DROP COLUMN tax_cents;
    ALTER TABLE card_topups DROP COLUMN tax_behavior;
    ALTER TABLE card_topups DROP COLUMN tax_mode;
""")

# 058: Where an account's owners hear about approval requests (owner_notify.py, mandates.md
# §5.6): Telegram, Slack, Jira or a signed webhook. target_json holds the channel's own secret
# (a bot token, a webhook URL, a Jira token) — used to deliver, never returned. owner_notify_refs
# remembers what a request opened in a channel (a Jira issue), so its answer lands there too.
_register(58, "058_owner_notify", """
    CREATE TABLE IF NOT EXISTS owner_notify_channels (
        channel_id TEXT PRIMARY KEY,
        account_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        target_json TEXT NOT NULL,
        created_at REAL NOT NULL,
        last_status INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT '',
        last_sent_at REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_owner_notify_account ON owner_notify_channels(account_id, created_at);
    CREATE TABLE IF NOT EXISTS owner_notify_refs (
        approval_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        external_ref TEXT NOT NULL,
        PRIMARY KEY (approval_id, channel_id)
    );
""", """
    DROP TABLE IF EXISTS owner_notify_refs;
    DROP INDEX IF EXISTS idx_owner_notify_account;
    DROP TABLE IF EXISTS owner_notify_channels;
""")

# 059: A2A tasks survive a restart of the hub that runs them (a2a.py, recover_stale). A running
# task is LEASED by its process (lease_owner/lease_until, renewed while the call runs); the
# call is marked when it is sent (invoke_started, invoke_rail); and every credit reservation or
# debit it makes is named in a2a_task_charges BEFORE the money moves. A lapsed lease then tells
# the hub, from the ledger, whether the abandoned call cost anything.
_register(59, "059_a2a_task_recovery", """
    ALTER TABLE a2a_tasks ADD COLUMN lease_owner TEXT NOT NULL DEFAULT '';
    ALTER TABLE a2a_tasks ADD COLUMN lease_until REAL NOT NULL DEFAULT 0;
    ALTER TABLE a2a_tasks ADD COLUMN invoke_started REAL NOT NULL DEFAULT 0;
    ALTER TABLE a2a_tasks ADD COLUMN invoke_rail TEXT NOT NULL DEFAULT '';
    CREATE TABLE IF NOT EXISTS a2a_task_charges (
        task_id TEXT NOT NULL,
        receipt_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        created_at REAL NOT NULL,
        PRIMARY KEY (task_id, receipt_id)
    );
""", """
    DROP TABLE IF EXISTS a2a_task_charges;
    ALTER TABLE a2a_tasks DROP COLUMN invoke_rail;
    ALTER TABLE a2a_tasks DROP COLUMN invoke_started;
    ALTER TABLE a2a_tasks DROP COLUMN lease_until;
    ALTER TABLE a2a_tasks DROP COLUMN lease_owner;
""")

# 060: A peer that sells each tool at its own URL. The spec asks a manifest tool for a name, a
# description and an input_schema; an x402 seller adds `endpoint` and answers there, with no
# AI-Market invoke route at all (mach402.dev and agent-exec.448c.org, 2026-10-21). A routed
# call to such a row goes to that URL with the bare input. Kept apart from invoke_url, which
# means "this hub executes the listing itself" and must never come from a peer.
_register(60, "060_capability_peer_endpoint", """
    ALTER TABLE capabilities ADD COLUMN peer_endpoint TEXT DEFAULT '';
""", """
    ALTER TABLE capabilities DROP COLUMN peer_endpoint;
""")

# 061: Idempotency-Key on paid invokes (aimarket_hub/idempotency.py). The first answer to a
# (credential, key) pair, kept 24 h, so a retry after a timeout replays it instead of paying
# again. `scope` is a hash of the paying credential, never the credential; times are epoch
# seconds (REAL), not text, so their age is never read through a session time zone.
_register(61, "061_invoke_idempotency", """
    CREATE TABLE IF NOT EXISTS invoke_idempotency (
        scope TEXT NOT NULL,
        idem_key TEXT NOT NULL,
        request_sha256 TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'running',
        http_status INTEGER NOT NULL DEFAULT 0,
        response_headers TEXT NOT NULL DEFAULT '[]',
        response_body TEXT NOT NULL DEFAULT '',
        created_at REAL NOT NULL,
        finished_at REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (scope, idem_key)
    );
    CREATE INDEX IF NOT EXISTS idx_invoke_idempotency_created ON invoke_idempotency(created_at);
""", """
    DROP INDEX IF EXISTS idx_invoke_idempotency_created;
    DROP TABLE IF EXISTS invoke_idempotency;
""")

# 062: Before the reversal spending guard, verified refunds/disputes only changed
# card_topups.status. Freeze those historical accounts once on upgrade too, without
# changing balances. A trusted operator can reconcile and reactivate an account;
# later restarts must not repeat that freeze. Rolling back never reactivates money.
_register(62, "062_card_reversal_review", """
    INSERT INTO credit_ledger (account_id, kind, amount_mc, receipt_id, note)
    SELECT c.account_id, 'review_freeze', 0,
           'card:' || t.topup_id || ':' || t.status,
           'Historical Stripe ' || t.status || ': operator review required'
    FROM card_topups t JOIN credit_accounts c ON c.account_id = t.account_id
    WHERE t.status IN ('refunded', 'disputed') AND c.status = 'active'
      AND NOT EXISTS (
          SELECT 1 FROM credit_ledger l
          WHERE l.account_id = c.account_id AND l.kind = 'review_freeze'
            AND l.receipt_id = 'card:' || t.topup_id || ':' || t.status
      );
    UPDATE credit_accounts SET status = 'disabled'
    WHERE status = 'active' AND account_id IN (
        SELECT account_id FROM card_topups WHERE status IN ('refunded', 'disputed')
    );
""", """
    SELECT 1;
""")

# 063: x402 sellers listed from their own discovery document, with consent (spec §2.7).
# Its own table, never `capabilities`: an observed route must not be searchable as a
# catalogue row, routable or re-exported, and keeping it out structurally (spec §2.6 (2))
# means a query that forgets a filter cannot leak it.
_register(63, "063_observed_sellers", """
    CREATE TABLE IF NOT EXISTS observed_sellers (
        origin TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        discovery_url TEXT DEFAULT '',
        allowed_routes_json TEXT DEFAULT '[]',
        pinned_pay_to TEXT DEFAULT '',
        consent_json TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        observed_at TEXT DEFAULT '',
        last_error TEXT DEFAULT '',
        routes_json TEXT DEFAULT '[]'
    );
""", """
    DROP TABLE IF EXISTS observed_sellers;
""")

_register(64, "064_catalogue_evidence", """
    ALTER TABLE capabilities ADD COLUMN catalogue_evidence TEXT NOT NULL DEFAULT '{}';
""", """
    ALTER TABLE capabilities DROP COLUMN catalogue_evidence;
""")

def channel_ledger_versions() -> list[int]:
    """Migration versions whose DDL touches a channel-ledger table.

    Derived from the registered SQL, so a NEW channels migration is picked up
    automatically — the channel ledger can never silently run on a stale schema
    because someone forgot to bump a hand-written target_version.
    """
    return sorted(
        version
        for version, _name, up, _down in MIGRATIONS
        if any(_touches_table(up, t) for t in CHANNEL_LEDGER_TABLES)
    )


SUBSYSTEM_VERSIONS: dict[str, Any] = {"channels": channel_ledger_versions}


# ── Migrations Manager ──────────────────────────────────────────────


class Migrations:
    """Apply and track database migrations."""

    def __init__(self, backend: DBBackend):
        self._backend = backend
        self._ensure_migrations_table()

    def _ensure_migrations_table(self) -> None:
        try:
            self._backend.execute(
                "CREATE TABLE IF NOT EXISTS _migrations ("
                "  version INTEGER PRIMARY KEY,"
                "  name TEXT NOT NULL,"
                "  applied_at TEXT DEFAULT (datetime('now'))"
                ")"
            )
            self._backend.commit()
        except Exception as exc:
            logger.warning("Could not create _migrations table: %s", exc)

    def applied_versions(self) -> set[int]:
        try:
            self._backend.execute("SELECT version FROM _migrations ORDER BY version")
            rows = self._backend.fetchall()
            return {r["version"] for r in rows}
        except Exception:
            return set()

    def pending(self) -> list[tuple[int, str, str, str]]:
        applied = self.applied_versions()
        return [m for m in MIGRATIONS if m[0] not in applied]

    def apply(self, target_version: int | None = None, subsystem: str = "") -> int:
        """Apply pending migrations.

        target_version: legacy upper bound (kept for existing callers).
        subsystem: apply only the migrations that subsystem's tables need — used by
            the payment-channel ledger, which owns a separate database file. The
            version set is derived from the DDL (SUBSYSTEM_VERSIONS), so it cannot
            go stale the way a hard-coded target_version does.
        """
        pending = self.pending()
        if target_version is not None:
            pending = [m for m in pending if m[0] <= target_version]
        if subsystem:
            resolver = SUBSYSTEM_VERSIONS.get(subsystem)
            if resolver is None:
                raise ValueError(f"unknown migration subsystem: {subsystem}")
            wanted = set(resolver())
            pending = [m for m in pending if m[0] in wanted]

        applied_count = 0
        for version, name, sql_up, _ in sorted(pending, key=lambda m: m[0]):
            logger.info("Applying migration %03d: %s", version, name)
            # Atomic: schema change + _migrations bookkeeping in ONE commit.
            # Previous two-commit pattern allowed crash between them, leaving
            # schema applied but not registered → next start would re-apply
            # and potentially double-INSERT seed data (EXP-77).
            try:
                self._backend.executescript(sql_up)
                self._backend.execute(
                    "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                    (version, name),
                )
                self._backend.commit()
                applied_count += 1
                logger.info("  OK %03d", version)
            except Exception as exc:
                # ALTER ADD COLUMN on a DB that already has the column (CREATE evolved
                # in source after the migration was first applied) — treat as applied
                # so a redeploy cannot abort hub startup over a no-op schema drift.
                # SQLite: "duplicate column name: …"
                # Postgres/psycopg: 'column "…" of relation "…" already exists'
                # SQLSTATE 42701 (duplicate_column) first: the message is LOCALISED on
                # PostgreSQL, so a server with lc_messages other than English ('столбец …
                # уже существует') failed the text match and aborted startup on a fresh
                # database — every fresh install hits this path, since 001's CREATE
                # already carries columns later migrations add.
                msg = str(exc).lower()
                if getattr(exc, "sqlstate", None) == "42701" or "duplicate column" in msg or (
                    "already exists" in msg and "column" in msg
                ):
                    # INFO, not WARNING: every fresh install takes this path for the columns
                    # 001 already creates, and a warning on a stranger's first run reads as
                    # a broken install (seen following the operator quickstart, 2026-10-12).
                    logger.info("  SKIP %03d (already present): %s", version, exc)
                    self._backend.execute(
                        "INSERT INTO _migrations (version, name) VALUES (?, ?)",
                        (version, name),
                    )
                    self._backend.commit()
                    applied_count += 1
                    continue
                logger.error("  FAILED %03d: %s", version, exc)
                raise
        return applied_count

    def rollback(self, steps: int = 1) -> int:
        self._backend.execute(
            "SELECT version, name FROM _migrations ORDER BY version DESC LIMIT ?",
            (steps,),
        )
        rows = self._backend.fetchall()
        rolled = 0
        for row in reversed(rows):
            version = int(row["version"])
            name = row["name"]
            for v, _n, _, sql_down in MIGRATIONS:
                if v == version:
                    logger.info("Rolling back %03d: %s", version, name)
                    self._backend.executescript(sql_down)
                    self._backend.execute(
                        "DELETE FROM _migrations WHERE version = ?",
                        (version,),
                    )
                    self._backend.commit()
                    rolled += 1
                    break
        return rolled

    def status(self) -> list[dict[str, Any]]:
        applied = self.applied_versions()
        return [
            {"version": v, "name": n, "applied": v in applied}
            for v, n, _, _ in sorted(MIGRATIONS, key=lambda m: m[0])
        ]


# ── CLI ─────────────────────────────────────────────────────────────


def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    database_url = os.environ.get("DATABASE_URL", "")
    db_path = os.environ.get("AIMARKET_DB_PATH", "data/hub.db")
    backend = create_backend(database_url=database_url, db_path=db_path)
    migrations = Migrations(backend)

    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "up":
        count = migrations.apply()
        print(f"\nApplied {count} migration(s)")
    elif cmd == "down":
        steps = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        count = migrations.rollback(steps)
        print(f"\nRolled back {count} migration(s)")
    elif cmd == "status":
        rows = migrations.status()
        print(f"\nBackend: {backend.backend_type}")
        print(f"{'Version':>8}  {'Name':<30}  {'Status'}")
        print("-" * 55)
        for r in rows:
            s = "OK" if r["applied"] else "PENDING"
            print(f"{r['version']:>8}  {r['name']:<30}  {s}")
    else:
        print("Usage: python -m aimarket_hub.migrations [up|down|status]")
        sys.exit(1)

    backend.close()


if __name__ == "__main__":
    _cli()
