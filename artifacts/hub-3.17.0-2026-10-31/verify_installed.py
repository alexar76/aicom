"""Verify an installed wheel outside its source tree; no paid calls or external writes."""
import json
import os
from pathlib import Path
import sys
import tempfile

installed = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(installed))
os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0", AIFACTORY_CRYPTO_ENABLED="0")
import aimarket_hub
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
from aimarket_hub.ui_assets import UI_FILES, ui_asset_path
from fastapi.testclient import TestClient

assert aimarket_hub.__version__ == "3.17.0"
assert Path(aimarket_hub.__file__).is_relative_to(installed)
for name in UI_FILES:
    path = Path(ui_asset_path(name))
    assert path.is_relative_to(installed / "aimarket_hub/static/ui"), path
    assert path.is_file()
with tempfile.TemporaryDirectory(prefix="hub-wheel-check-") as temporary:
    root = Path(temporary)
    config = HubConfig()
    config.hub_url = "http://127.0.0.1:8769"
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "hub.key")
    config.seed_list = []
    config.crawl_initial_delay_s = 86400
    db = HubDatabase(config.db_path)
    signer = Signer(config.signing_key_path)
    with TestClient(create_app(config=config, db=db, signer=signer)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "function renderObserved" in page.text
        assert "function searchEvidence" in page.text
        dictionary = client.get("/hub-ui-i18n.json")
        assert dictionary.status_code == 200
        for language in ("en", "ru", "es", "fr", "zh"):
            assert dictionary.json()["ui"][language]["search_observed"]
            assert dictionary.json()["ui"][language]["evidence_signed"]
        assert client.get("/operator").status_code == 200
        assert client.get("/plugins/demo").status_code == 200
        assert client.get("/.well-known/ai-market.json").status_code == 200
        assert 64 in {r["version"] for r in db._conn.execute("SELECT version FROM _migrations").fetchall()}
    db.close()
print(json.dumps({"version": aimarket_hub.__version__, "installedPackage": str(Path(aimarket_hub.__file__).parent), "bundledUiFiles": len(UI_FILES), "pagesAndFiveLanguages": "passed", "migration64": "passed"}))
