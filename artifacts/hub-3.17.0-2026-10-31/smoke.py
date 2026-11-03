"""Candidate-image verification, including a copy of the live SQLite database."""
import json
import os
from pathlib import Path
import shutil
import tempfile

os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0", AIFACTORY_CRYPTO_ENABLED="0")
import aimarket_hub
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from fastapi.testclient import TestClient

assert aimarket_hub.__version__ == "3.17.0"
with tempfile.TemporaryDirectory(prefix="hub-release-smoke-") as temporary:
    root = Path(temporary)
    backup = Path("/release/live-before.db")
    assert backup.is_file()
    shutil.copyfile(backup, root / "migrated.db")
    migrated = HubDatabase(root / "migrated.db")
    migrations = [r["version"] for r in migrated._conn.execute("SELECT version FROM _migrations").fetchall()]
    assert 62 in migrations and 64 in migrations
    assert "catalogue_evidence" in migrated._conn.execute("SELECT * FROM capabilities LIMIT 1").fetchone().keys()
    count = migrated.count_capabilities()
    migrated.close()
    cfg = HubConfig()
    cfg.hub_url = "http://127.0.0.1:8769"
    cfg.db_path = str(root / "fresh.db")
    cfg.signing_key_path = str(root / "fixture.key")
    cfg.seed_list = []
    cfg.crawl_initial_delay_s = 86400
    db = HubDatabase(cfg.db_path)
    with TestClient(create_app(config=cfg, db=db, signer=Signer(cfg.signing_key_path))) as client:
        page = client.get("/")
        assert page.status_code == 200 and "function renderObserved" in page.text and "function searchEvidence" in page.text
        translations = client.get("/hub-ui-i18n.json").json()["ui"]
        assert all(translations[lang]["evidence_signed"] and translations[lang]["search_observed"]
                   for lang in ("en", "ru", "es", "fr", "zh"))
        for path in ("/.well-known/ai-market.json", "/mcp", "/operator", "/plugins/demo"):
            assert client.get(path).status_code == 200, path
        assert client.get("/ai-market/v2/search?intent=weather").status_code == 200
    db.close()
print(json.dumps({"version": aimarket_hub.__version__, "liveDatabaseCopyMigrated": True,
                  "catalogueRowsPreserved": count, "migration62": True, "migration64": True,
                  "uiAndFiveLanguages": True, "network": "disabled"}))
