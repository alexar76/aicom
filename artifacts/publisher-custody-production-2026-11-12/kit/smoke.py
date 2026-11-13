"""Check the candidate and the rollback image on copies of the production ledgers."""

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

mode = sys.argv[1]
assert mode in ("new", "old")
paths = {"hub": Path("/smoke/hub.db"), "channels": Path("/smoke/channels.db")}
temp = Path(tempfile.mkdtemp(prefix="publisher-custody-smoke-"))
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_", "PG")) or "DATABASE" in name:
        del os.environ[name]
os.environ.update({
    "AIMARKET_DB_PATH": str(paths["hub"]), "AIMARKET_CHANNELS_DB_PATH": str(paths["channels"]),
    "AIMARKET_CREDITS_ENABLED": "1", "AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0",
    "AIMARKET_SKIP_SEED": "1", "AIMARKET_SIGNING_KEY_PATH": str(temp / "smoke.key"),
    "AIMARKET_HUB_URL": "https://publisher-custody-smoke.invalid",
    "AIMARKET_DEPOSIT_CLAIMS_DIR": str(temp / "deposit-claims"),
})
sys.path.insert(0, "/app")


def versions(path):
    with sqlite3.connect(path) as connection:
        return {row[0] for row in connection.execute("SELECT version FROM _migrations")}


def row_counts(path):
    with sqlite3.connect(path) as connection:
        names = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return {name: connection.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                for name in names if name not in ("_migrations", "sqlite_sequence")}


before = {label: (versions(path), row_counts(path)) for label, path in paths.items()}

import aimarket_hub  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

assert aimarket_hub.__file__.startswith("/app/aimarket_hub/"), aimarket_hub.__file__
db = HubDatabase(paths["hub"])
expected = {"hub": {70, 71, 72}, "channels": {70, 72}}
changes = {}
for label, path in paths.items():
    old_versions, old_counts = before[label]
    new_versions, new_counts = versions(path), row_counts(path)
    migrations = new_versions - old_versions
    assert old_versions <= new_versions and expected[label] <= new_versions
    assert migrations == (expected[label] - old_versions if mode == "new" else set()), (label, migrations)
    assert all(new_counts.get(name) == count for name, count in old_counts.items()), label
    changes[label] = sorted(migrations)

if mode == "new":
    from eth_account import Account
    from aimarket_hub import credits
    from aimarket_hub.publisher_withdrawals import PublisherWithdrawals

    assert Account.create().address.startswith("0x")
    ledger = credits.CreditsLedger(db._conn)
    buyer, seller = ledger.create_account()["account_id"], ledger.create_account()["account_id"]
    assert "error" not in ledger.deposit(buyer, 10, reference="custody-smoke-local-copy", base_usdc=True)
    receipt = "custody-smoke-local-copy"
    assert "error" not in ledger.hold(buyer, 0.0001, receipt)
    share = credits.PublisherShare(seller, 0.00007, receipt, "synthetic smoke")
    assert ledger.capture_hold(receipt, publisher_share=share)["captured_usd"] == 0.0001
    assert ledger.capture_hold(receipt, publisher_share=share)["already"] == "captured"
    assert PublisherWithdrawals(ledger).summary(seller, 1)["withdrawable_usdc"] == 0.00007

config = HubConfig()
config.db_path = str(paths["hub"])
app = create_app(config=config, db=db)
with TestClient(app) as client:
    for path in ("/ai-market/v2/health", "/.well-known/ai-market.json"):
        reply = client.get(path)
        assert reply.status_code == 200, (path, reply.status_code)
    reply = client.get("/ai-market/v2/account/withdrawals")
    assert reply.status_code == (401 if mode == "new" else 404), reply.status_code
print(json.dumps({"mode": mode, "migration_additions": changes, "ledger_copies": True, "status": "ok"}))
