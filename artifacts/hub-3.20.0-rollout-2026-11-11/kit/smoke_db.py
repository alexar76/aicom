"""Smoke a hub image against a COPY of a live hub database (rollout 2026-11-11).

Run inside the image with --network none. The database is a copy: SQLite at SMOKE_DB_PATH, or the
throw-away Postgres at SMOKE_DATABASE_URL. Prints one JSON line; any failed check raises.
  SMOKE_MODE=new  migrate to the image's latest version, compare row counts, run the app's routes
  SMOKE_MODE=old  the image being replaced, on the migrated copy: it must start and answer (rollback)
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
os.environ.update({"AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0",
                   "AIMARKET_SIGNING_KEY_PATH": str(TMP / "smoke.key"),
                   "AIMARKET_HUB_URL": "https://smoke-hub.example"})
sys.path.insert(0, "/app")

import aimarket_hub  # noqa: E402

EXPECT_PKG = os.environ.get("SMOKE_EXPECT_PKG", "/app/aimarket_hub/")  # Independent runs from a venv
assert aimarket_hub.__file__.startswith(EXPECT_PKG), aimarket_hub.__file__


def raw_counts() -> dict[str, int]:
    if pg_url:
        import psycopg
        with psycopg.connect(pg_url) as c:
            tables = [r[0] for r in c.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()]
            return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
    import sqlite3
    c = sqlite3.connect(sqlite_path)
    tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}


def applied() -> list[int]:
    if pg_url:
        import psycopg
        with psycopg.connect(pg_url) as c:
            return [r[0] for r in c.execute("SELECT version FROM _migrations ORDER BY version")]
    import sqlite3
    return [r[0] for r in sqlite3.connect(sqlite_path).execute("SELECT version FROM _migrations ORDER BY version")]


report: dict = {"mode": mode, "version": aimarket_hub.__version__, "backend": "postgres" if pg_url else "sqlite"}
before = raw_counts()
versions_before = applied()

from fastapi.testclient import TestClient  # noqa: E402

from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

config = HubConfig()
config.hub_url = "https://smoke-hub.example"
if not pg_url:
    config.db_path = sqlite_path
config.signing_key_path = str(TMP / "smoke.key")
db = HubDatabase(config.db_path)
signer = Signer(config.signing_key_path)
after = raw_counts()
versions_after = applied()
report["migrations"] = {"before_max": max(versions_before), "after_max": max(versions_after),
                        "added": sorted(set(versions_after) - set(versions_before))}
changed = {t: [before[t], after[t]] for t in before if t in after and before[t] != after[t] and t not in ("_migrations", "sqlite_sequence")}
report["rows_changed"] = changed
report["tables_added"] = sorted(set(after) - set(before))
if mode == "new":
    assert max(versions_after) >= 69 and not [v for v in (61, 62, 65, 66, 67, 68, 69) if v not in versions_after]
    # Only migration 062 may write rows: a review freeze per refunded/disputed card top-up.
    assert set(changed) <= {"credit_ledger"}, changed
else:
    assert changed == {} and versions_after == versions_before, (changed, versions_before, versions_after)

app = create_app(config=config, db=db, signer=signer)
checks = {}
with TestClient(app) as client:
    for path in ("/ai-market/v2/health", "/.well-known/ai-market.json", "/ai-market/v2/federation/peers",
                 "/ai-market/v2/manifest", "/ai-market/v2/search?q=weather", "/"):
        r = client.get(path)
        checks[path] = r.status_code
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    if mode == "new":
        receipt = {"nonce": "smoke-1", "product_id": "p", "capability_id": "c@v1", "price_usd": 0.0,
                   "timestamp": "2026-11-11T00:00:00Z", "success": True, "latency_ms": 1}
        receipt["signature"] = signer.sign_receipt(receipt)
        r = client.post("/ai-market/v2/receipts/verify", json={"receipt": receipt})
        assert r.status_code == 200 and r.json()["valid"] is True and "pq_pinned" in r.json(), r.text[:300]
        r = client.post("/ai-market/v2/invoke", headers={"X-Client-Nonce": "bad"},
                        json={"product_id": "smoke-prod", "capability_id": "smoke.cap@v1", "input": {}, "source_hub": "local"})
        assert r.status_code == 400 and r.json().get("error") == "client_nonce_invalid", r.text[:300]
        checks["receipts/verify"] = 200
        checks["nonce 400"] = 400
report["routes"] = checks
print(json.dumps(report))
