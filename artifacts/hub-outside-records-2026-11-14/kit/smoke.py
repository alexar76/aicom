"""Outside records on disposable SQLite copies: everything else the apex serves stays identical."""

from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from urllib.parse import quote, urlparse


mode = sys.argv[1]
temp = Path(tempfile.mkdtemp(prefix="outside-records-smoke-"))
os.chdir(temp)
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_", "PG")) or "DATABASE" in name:
        del os.environ[name]
os.environ.update({
    "AIMARKET_DB_PATH": "/smoke/hub.db", "AIMARKET_CHANNELS_DB_PATH": "/smoke/channels.db",
    "AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0", "AIMARKET_SKIP_SEED": "1",
    "AIMARKET_SIGNING_KEY_PATH": str(temp / "smoke.key"), "AIMARKET_CREDITS_ENABLED": "1",
    "AIMARKET_DEPOSIT_CLAIMS_DIR": str(temp / "claims"), "AIMARKET_ADMIN_TOKEN": "isolated-outside-records-smoke",
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

prefix = "/ai-market/v2"
observed = prefix + "/federation/observed-sellers"
bridge = prefix + "/x402-bridge"
db = HubDatabase("/smoke/hub.db")
OUTSIDE = ("outside_records", "outside_checks", "outside_records_note")


def digest(value):
    return sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def strip(value):
    """The listing without the new keys, so base and candidate must agree on everything else."""
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in OUTSIDE and k not in ("observed_at", "fresh")}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


config = HubConfig(hub_url="https://modelmarket.dev", hub_name="modelmarket.dev")
with TestClient(create_app(config=config, db=db)) as client:
    replies = {path: client.get(path).status_code for path in (prefix + "/health", prefix + "/account/withdrawals",
               observed, bridge)}
    assert tuple(replies.values()) == (200, 401, 200, 200), replies
    assert client.post(observed, json={"origin": "https://outside-records-smoke.invalid"}).status_code == 401
    manifest = client.get(prefix + "/manifest").json()
    listing = client.get(observed).json()
    search = client.get(prefix + "/search", params={"intent": "safety check price"}).json()
    rows = listing["sellers"]
    snapshot = {
        "manifest_count": manifest["total_capabilities"],
        "manifest_tools_digest": digest(sorted((tool["capability_id"], tool["product_id"], tool["source_hub"])
                                               for tool in manifest["tools"])),
        "observed_listing_digest": digest(strip(listing)),
        "observed_origins_and_counts": sorted((row["origin"], row["routes_served"]) for row in rows),
        "search_matches_digest": digest([(m.get("capability_id"), m.get("product_id"), m.get("source_hub"))
                                         for m in search["matches"]]),
        "search_observed_digest": digest(strip(search.get("observed") or [])),
        "bridge": {key: client.get(bridge).json().get(key) for key in ("enabled", "network", "limits", "balance_usd")},
    }
    linked = []
    if mode == "candidate":
        assert "does not run or read" in listing["outside_records_note"]
        for row in rows:
            host = urlparse(row["origin"]).hostname
            assert row["outside_records"] == [{"by": "vet402", "url": f"https://vet402.com/sellers/{host}"}], row
            for route in row["routes"]:
                want = (f"https://vet402.com/api/v1/check?url={quote(route['url'], safe='')}"
                        f"&method={(route.get('method') or 'POST').upper()}")
                assert route["outside_checks"] == [{"by": "vet402", "url": want}], route
            linked.append(row["outside_records"][0]["url"])
        assert all(r["outside_checks"] for r in search.get("observed") or [])
    else:
        assert not any(k in json.dumps(listing) for k in OUTSIDE)

assert migrations() == before
print(json.dumps({"mode": mode, "health": replies, "snapshot": snapshot, "migrations_added": 0,
                  "linked_records": linked}, sort_keys=True))
