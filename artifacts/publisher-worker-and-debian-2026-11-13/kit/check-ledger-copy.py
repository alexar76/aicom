"""Run the custody-enabled Hub on a disposable copy of both production ledgers."""

import json
import os
from pathlib import Path
import sqlite3
import tempfile


temp = Path(tempfile.mkdtemp(prefix="debian-custody-smoke-"))
os.chdir(temp)
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_", "PG")) or "DATABASE" in name:
        del os.environ[name]
os.environ.update({
    "AIMARKET_DB_PATH": "/smoke/hub.db", "AIMARKET_CHANNELS_DB_PATH": "/smoke/channels.db",
    "AIMARKET_CREDITS_ENABLED": "1", "AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0",
    "AIMARKET_SKIP_SEED": "1", "AIMARKET_SIGNING_KEY_PATH": str(temp / "smoke.key"),
    "AIMARKET_HUB_URL": "https://debian-custody-smoke.invalid",
    "AIMARKET_DEPOSIT_CLAIMS_DIR": str(temp / "deposit-claims"),
})


def migration_versions(path):
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        return sorted(row[0] for row in db.execute("SELECT version FROM _migrations"))


paths = {"hub": "/smoke/hub.db", "channels": "/smoke/channels.db"}
versions = {name: migration_versions(path) for name, path in paths.items()}
assert {70, 71, 72} <= set(versions["hub"])
assert {70, 72} <= set(versions["channels"])

from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

config = HubConfig()
config.db_path = paths["hub"]
db = HubDatabase(config.db_path)
app = create_app(config=config, db=db)
with TestClient(app) as client:
    responses = {path: client.get(path).status_code for path in (
        "/ai-market/v2/health", "/.well-known/ai-market.json", "/ai-market/v2/account/withdrawals",
    )}
    assert tuple(responses.values()) == (200, 200, 401), responses
assert {name: migration_versions(path) for name, path in paths.items()} == versions
print(json.dumps({"http_status": responses, "database_migrations_added": 0, "sqlite_checks": 2}))
