"""Check the external directory and incumbent public routes on disposable SQLite copies."""

from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile


mode = sys.argv[1]
temp = Path(tempfile.mkdtemp(prefix="external-directory-smoke-"))
os.chdir(temp)
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_", "PG")) or "DATABASE" in name:
        del os.environ[name]
os.environ.update({
    "AIMARKET_DB_PATH": "/smoke/hub.db", "AIMARKET_CHANNELS_DB_PATH": "/smoke/channels.db",
    "AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0", "AIMARKET_SKIP_SEED": "1",
    "AIMARKET_SIGNING_KEY_PATH": str(temp / "smoke.key"), "AIMARKET_CREDITS_ENABLED": "1",
    "AIMARKET_DEPOSIT_CLAIMS_DIR": str(temp / "claims"), "AIMARKET_ADMIN_TOKEN": "isolated-directory-smoke",
})


def migrations():
    report = []
    for path in ("/smoke/hub.db", "/smoke/channels.db"):
        with sqlite3.connect(path) as db:
            assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
            report.append(tuple(db.execute("SELECT version FROM _migrations ORDER BY version")))
    return report


before = migrations()
from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.ui_assets import ui_asset_path  # noqa: E402

prefix = "/ai-market/v2"
directory = prefix + "/external-services"
observed = prefix + "/federation/observed-sellers"
bridge = prefix + "/x402-bridge"
expected = {"coinmarketcap": ("GET", 0.01, "per_request"), "tavily": ("POST", 0.01, "per_request"),
            "laso": ("GET", 5, "minimum_load")}
db = HubDatabase("/smoke/hub.db")


def app_client(hub_url, hub_name):
    config = HubConfig(hub_url=hub_url, hub_name=hub_name)
    return TestClient(create_app(config=config, db=db))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def keys(rows):
    return {row["id"] for row in rows}


assert ui_asset_path("terminal-home.html", "/app") == "/app/terminal-home.html"
with app_client("https://modelmarket.dev", "modelmarket.dev") as client:
    replies = {path: client.get(path).status_code for path in (prefix + "/health", prefix + "/account/withdrawals",
               observed, bridge)}
    assert tuple(replies.values()) == (200, 401, 200, 200), replies
    assert client.post(observed, json={"origin": "https://modelmarket-directory-smoke.invalid"}).status_code == 401
    assert client.post(directory, json={}).status_code in (404, 405)
    home = client.get("/")
    assert home.status_code == 200 and home.text.count('<p class="apex-tools">') == 1
    manifest = client.get(prefix + "/manifest").json()
    assert "external" not in manifest
    observed_rows = client.get(observed).json()["sellers"]
    assert {row["origin"] for row in observed_rows}.isdisjoint({"https://pro-api.coinmarketcap.com",
        "https://x402.tavily.com", "https://laso.finance"})
    search = client.get(prefix + "/search", params={"intent": "prepaid card"}).json()
    baseline_bridge = client.get(bridge).json()
    snapshot = {
        "manifest_count": manifest["total_capabilities"],
        "manifest_tools_digest": digest(sorted((tool["capability_id"], tool["product_id"], tool["source_hub"])
                                               for tool in manifest["tools"])),
        "observed_origins_and_counts": sorted((row["origin"], row["routes_served"]) for row in observed_rows),
        "search_matches_digest": digest([(match.get("capability_id"), match.get("product_id"), match.get("source_hub"))
                                         for match in search["matches"]]),
        "bridge": {key: baseline_bridge.get(key) for key in ("enabled", "network", "limits", "balance_usd")},
    }
    if mode == "candidate":
        result = client.get(directory)
        assert result.status_code == 200
        rows = result.json()["external"]
        assert len(rows) == 3 and {row["id"]: (row["method"], row["published_price_usd"], row["price_basis"])
                                   for row in rows} == expected
        assert all(row["hub_invoke"] is False and row["payment_recipient"] == "provider" for row in rows)
        assert keys(search["external"]) == {"laso"}
        assert client.get(prefix + "/search", params={"intent": "prepaid card", "budget": 0.05}).json()["external"] == []
        assert keys(client.get(prefix + "/search", params={"intent": "web search"}).json()["external"]) == {"tavily"}
        assert keys(client.get(prefix + "/search", params={"intent": "CMC"}).json()["external"]) == {"coinmarketcap"}
        assert client.get(prefix + "/search", params={"intent": "CMC", "hub": "local"}).json()["external"] == []
        assert 'id="external-directory"' in home.text and directory in home.text
        ui = client.get("/hub-ui-i18n.json").json()["ui"]
        assert all(ui[lang][key] for lang in ("en", "ru", "es", "fr", "zh") for key in ("external_title", "external_note"))
    else:
        assert client.get(directory).status_code == 404 and "external" not in search

if mode == "candidate":
    with app_client("https://directory-other-hub.invalid", "Another Hub") as client:
        assert client.get(directory).status_code == 404
        assert "external" not in client.get(prefix + "/search", params={"intent": "Laso"}).json()
        assert 'id="external-directory"' not in client.get("/").text

assert migrations() == before
print(json.dumps({"mode": mode, "health": replies, "snapshot": snapshot, "migrations_added": 0,
                  "external_references": list(expected) if mode == "candidate" else [],
                  "five_locales": mode == "candidate", "non_apex_excluded": mode == "candidate"}, sort_keys=True))
