"""Mesh database schema — SQLite DDL (auto-translated for PostgreSQL)."""

MESH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    public_key_pem TEXT NOT NULL,
    capabilities TEXT NOT NULL,
    status TEXT NOT NULL,
    trust_score REAL NOT NULL DEFAULT 0.5,
    attestation TEXT,
    verified_at TEXT,
    product_id TEXT NOT NULL DEFAULT '',
    capability_id TEXT NOT NULL DEFAULT '',
    source_hub TEXT NOT NULL DEFAULT 'local',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    intent TEXT NOT NULL,
    budget_usd REAL NOT NULL,
    consumer_agent_id TEXT,
    status TEXT NOT NULL,
    selected_agent_id TEXT,
    total_spent_usd REAL NOT NULL DEFAULT 0,
    hops_json TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    message TEXT NOT NULL,
    task_id TEXT,
    agent_id TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);
CREATE TABLE IF NOT EXISTS escrow_holds (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    amount_usd REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

AGENT_LEGACY_COLUMNS = (
    "product_id TEXT NOT NULL DEFAULT ''",
    "capability_id TEXT NOT NULL DEFAULT ''",
    "source_hub TEXT NOT NULL DEFAULT 'local'",
)

MESH_TABLES = ("agents", "tasks", "activity", "escrow_holds")
