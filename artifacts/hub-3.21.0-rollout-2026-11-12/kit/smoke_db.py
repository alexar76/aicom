"""Smoke a hub image against a COPY of a live hub database (rollout 2026-11-12, hub 3.21.0).

Run inside the image with --network none. The database is a copy: SQLite at SMOKE_DB_PATH, or the
throw-away Postgres at SMOKE_DATABASE_URL. Prints one JSON line; any failed check raises.
  SMOKE_MODE=new  the 3.21.0 image: no migration is expected and no row may change; the app's routes
                  answer, and the AI Catalog door is checked end to end on this hub's own catalogue:
                  structure, every digest against the bytes served, every signature against the DID
                  document, with an ML-DSA-65 key as on the live hubs.
  SMOKE_MODE=old  the image being replaced, on the same copy: it must start and answer (rollback)
"""
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

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
config.hub_url = HUB
if not pg_url:
    config.db_path = sqlite_path
config.signing_key_path = str(TMP / "smoke.key")
db = HubDatabase(config.db_path)
# The live hubs sign hybrid; the smoke key does too, so the ML-DSA-65 path runs on this image's libraries.
signer = Signer(config.signing_key_path, pqc=(mode == "new"))
after = raw_counts()
versions_after = applied()
report["migrations"] = {"before_max": max(versions_before), "after_max": max(versions_after),
                        "added": sorted(set(versions_after) - set(versions_before))}
changed = {t: [before[t], after[t]] for t in before if t in after and before[t] != after[t] and t not in ("_migrations", "sqlite_sequence")}
report["rows_changed"] = changed
report["tables_added"] = sorted(set(after) - set(before))
# 3.21.0 has no migration: opening the database must change nothing, with either image.
assert changed == {} and versions_after == versions_before and not report["tables_added"], report
if mode == "new":
    assert aimarket_hub.__version__ == "3.21.0", aimarket_hub.__version__

app = create_app(config=config, db=db, signer=signer)
checks = {}
with TestClient(app) as client:
    for path in ("/ai-market/v2/health", "/.well-known/ai-market.json", "/ai-market/v2/federation/peers",
                 "/ai-market/v2/manifest", "/ai-market/v2/search?q=weather", "/", "/.well-known/ard.json",
                 "/.well-known/mcp/server-card.json", "/.well-known/agent-card.json"):
        r = client.get(path)
        checks[path] = r.status_code
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    if mode == "new":
        receipt = {"nonce": "smoke-1", "product_id": "p", "capability_id": "c@v1", "price_usd": 0.0,
                   "timestamp": "2026-11-12T00:00:00Z", "success": True, "latency_ms": 1}
        receipt["signature"] = signer.sign_receipt(receipt)
        r = client.post("/ai-market/v2/receipts/verify", json={"receipt": receipt})
        assert r.status_code == 200 and r.json()["valid"] is True and "pq_pinned" in r.json(), r.text[:300]
        checks["receipts/verify"] = 200

        from aimarket_hub import ai_catalog, ard

        def path_of(url: str) -> str:
            assert url.startswith(HUB + "/"), url
            parsed = urlparse(url)
            return parsed.path + (f"?{parsed.query}" if parsed.query else "")

        did_document = client.get(ard.DID_PATH).json()
        assert did_document["id"] == "did:web:smoke-hub.example"
        assert [m["publicKeyJwk"]["kty"] for m in did_document["verificationMethod"]] == ["OKP", "AKP"], did_document
        links = client.head("/").headers.get_list("link")
        assert f'<{HUB}{ai_catalog.WELL_KNOWN_PATH}>; rel="ai-catalog"' in links, links

        card_response = client.get(ai_catalog.SERVER_CARD_PATH)
        assert card_response.status_code == 200 and card_response.headers["content-type"] == ai_catalog.SERVER_CARD_TYPE
        assert ai_catalog.server_card_problems(card_response.json()) == [], card_response.text[:300]

        catalog = {"entries": 0, "digests": 0, "endorsed": 0, "peer_entries": 0}
        for path in (ai_catalog.WELL_KNOWN_PATH, ai_catalog.CAPABILITIES_PATH):
            response = client.get(path)
            assert response.status_code == 200 and response.headers["content-type"] == ai_catalog.MEDIA_TYPE, (path, response.status_code, response.text[:300])
            document = response.json()
            assert ai_catalog.problems(document) == [], (path, ai_catalog.problems(document)[:3])
            assert document["signature"]["profile"] == ai_catalog.PROFILE_ML_DSA_65, document["signature"]["profile"]
            found = ai_catalog.signature_problem(document, did_document, typ=ai_catalog.TYP_CATALOG)
            assert found == "", (path, found)
            tampered = json.loads(response.content)
            tampered["host"]["displayName"] += "!"
            assert ai_catalog.signature_problem(tampered, did_document, typ=ai_catalog.TYP_CATALOG) == "the signature does not verify"
            for entry in document["entries"]:
                catalog["entries"] += 1
                own = entry["identifier"].startswith("urn:air:smoke-hub.example:")
                if not own:
                    catalog["peer_entries"] += 1
                    assert "trustManifests" not in entry, entry["identifier"]
                    hop = client.get(path_of(entry["identifier"]), follow_redirects=False)
                    assert hop.status_code == 303 and hop.headers["location"] == entry["url"], (entry["identifier"], hop.status_code)
                if "digest" in entry:
                    served = client.get(path_of(entry["url"]))
                    assert served.status_code == 200, (entry["url"], served.status_code)
                    assert entry["digest"] == "sha256:" + hashlib.sha256(served.content).hexdigest(), entry["url"]
                    catalog["digests"] += 1
                if own and "digest" in entry:
                    (manifest,) = entry["trustManifests"]
                    found = ai_catalog.endorsement_problem(entry, manifest, did_document)
                    assert found == "", (entry["identifier"], found)
                    catalog["endorsed"] += 1
            checks[path] = 200
        # The same offers as the ARD door, which is what the hub's own search shows.
        capabilities = client.get(ai_catalog.CAPABILITIES_PATH).json()["entries"]
        agents, token = [], None
        while True:
            page = client.get(ard.REGISTRY_PATH + "/agents", params={"pageSize": 100, **({"pageToken": token} if token else {})}).json()
            agents += page["entries"]
            token = page.get("nextPageToken")
            if not token:
                break
        assert len(capabilities) == len(agents), (len(capabilities), len(agents))
        assert {e["url"] for e in capabilities} == {e["url"] for e in agents}
        catalog["capabilities"] = len(capabilities)
        for name in ("did-web-eddsa-v1", "did-web-ml-dsa-65-v1"):
            assert client.get(f"{ai_catalog.PROFILES_PATH}/{name}").status_code == 200
        report["ai_catalog"] = catalog
report["routes"] = checks
print(json.dumps(report))
