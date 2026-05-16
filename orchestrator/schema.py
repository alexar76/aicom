"""
SQLite Schema Definitions
=========================
Table definitions for the SQLite-backed pipeline state persistence.
Designed to mirror the structure of the JSON state file while adding
relational capabilities (indexes, foreign keys) for queryability.
"""

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    idea TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'IDEA',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    spec TEXT,              -- JSON string
    architecture TEXT,      -- JSON string
    tags TEXT,              -- JSON array as string
    category TEXT,
    monetization_scheme TEXT,  -- JSON string
    evolution_history TEXT,    -- JSON array as string
    error TEXT,
    current_task_id TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    product_id TEXT NOT NULL,
    agent_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    state TEXT,             -- PipelineState string value (e.g. "idea_received")
    assigned_to TEXT,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    input TEXT,             -- JSON string
    output TEXT,            -- JSON string
    error TEXT,
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0,  -- NEW: tracks LLM JSON parse retries
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_product_id ON tasks(product_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_products_state ON products(state);
CREATE INDEX IF NOT EXISTS idx_products_workspace_id ON products(workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_id ON tasks(workspace_id);
"""

# PostgreSQL — same logical model; upserts use ON CONFLICT in application code.
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    idea TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'IDEA',
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL,
    spec TEXT,
    architecture TEXT,
    tags TEXT,
    category TEXT,
    monetization_scheme TEXT,
    evolution_history TEXT,
    error TEXT,
    current_task_id TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL DEFAULT 'default',
    product_id TEXT NOT NULL REFERENCES products(id),
    agent_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    state TEXT,
    assigned_to TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    started_at DOUBLE PRECISION,
    completed_at DOUBLE PRECISION,
    input TEXT,
    output TEXT,
    error TEXT,
    priority INTEGER DEFAULT 0,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_tasks_product_id ON tasks(product_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_products_state ON products(state);
CREATE INDEX IF NOT EXISTS idx_products_workspace_id ON products(workspace_id);
CREATE INDEX IF NOT EXISTS idx_tasks_workspace_id ON tasks(workspace_id);
"""
