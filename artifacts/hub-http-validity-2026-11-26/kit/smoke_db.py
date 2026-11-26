"""Smoke a hub image against a COPY of a live hub database (HTTP validity change, 2026-11-26).

Run inside the image with no network. SQLite copy at SMOKE_DB_PATH or throw-away Postgres at
SMOKE_DATABASE_URL. Prints one JSON line; any failed check raises.
  SMOKE_MODE=new  migration 073 at most (capabilities.serve_until), no row count changes; the manifest
                  and both discovery documents carry a weak ETag and Cache-Control with stale-if-error,
                  and answer If-None-Match with 304; health answers.
  SMOKE_MODE=old  the image being replaced, on the same migrated copy: starts and answers (rollback).
"""
import json
import os
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp())
sqlite_path = os.environ.get("SMOKE_DB_PATH", "")
pg_url = os.environ.get("SMOKE_DATABASE_URL", "")
mode = os.environ.get("SMOKE_MODE", "new")
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
os.chdir(TMP)
if pg_url:
    os.environ["DATABASE_URL"] = pg_url
else:
    os.environ["AIMARKET_DB_PATH"] = sqlite_path
HUB = "https://smoke-hub.example"
os.environ.update({"AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0",
                   "AIMARKET_SIGNING_KEY_PATH": str(TMP / "smoke.key"), "AIMARKET_HUB_URL": HUB})
sys.path.insert(0, "/app")
import aimarket_hub  # noqa: E402

EXPECT_PKG = os.environ.get("SMOKE_EXPECT_PKG", "/app/aimarket_hub/")
assert aimarket_hub.__file__.startswith(EXPECT_PKG), aimarket_hub.__file__


def query(sql):
    if pg_url:
        import psycopg
        with psycopg.connect(pg_url) as c:
            return c.execute(sql).fetchall()
    import sqlite3
    return sqlite3.connect(sqlite_path).execute(sql).fetchall()


def counts():
    if pg_url:
        tables = [r[0] for r in query("SELECT tablename FROM pg_tables WHERE schemaname='public'")]
    else:
        tables = [r[0] for r in query("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: query(f'SELECT count(*) FROM "{t}"')[0][0] for t in tables}


report = {"mode": mode, "backend": "postgres" if pg_url else "sqlite"}
before, versions_before = counts(), {r[0] for r in query("SELECT version FROM _migrations")}

from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

config = HubConfig()
config.hub_url = HUB
if not pg_url:
    config.db_path = sqlite_path
db = HubDatabase(config.db_path)
with TestClient(create_app(config=config, db=db, signer=Signer(str(TMP / "smoke.key")))) as client:
    assert client.get("/ai-market/v2/health").status_code == 200
    manifest = client.get("/ai-market/v2/manifest")
    assert manifest.status_code == 200, manifest.status_code
    report["tools"] = len(manifest.json().get("tools") or [])
    if mode == "new":
        new_versions = {r[0] for r in query("SELECT version FROM _migrations")} - versions_before
        assert new_versions <= {73}, new_versions
        report["migrated"] = sorted(new_versions)
        cols = ([r[0] for r in query("SELECT column_name FROM information_schema.columns WHERE table_name='capabilities'")]
                if pg_url else [r[1] for r in query("PRAGMA table_info(capabilities)")])
        assert "serve_until" in cols
        after = counts()
        changed = {t: (before.get(t), n) for t, n in after.items() if before.get(t) != n and t != "_migrations"}
        assert not changed, changed
        for path in ("/ai-market/v2/manifest", "/.well-known/ai-market.json", "/.well-known/agent-marketplace"):
            first = client.get(path)
            etag, cc = first.headers.get("etag", ""), first.headers.get("cache-control", "")
            assert first.status_code == 200 and etag.startswith('W/"') and "stale-if-error=" in cc, (path, etag, cc)
            assert client.get(path, headers={"If-None-Match": etag}).status_code == 304, path
        report["cache_control_manifest"] = manifest.headers.get("cache-control")
        report["served"] = db.count_capabilities()
print(json.dumps(report))
