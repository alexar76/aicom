"""Catalogue-floor smoke inside a built hub image: no network, a temp SQLite DB, no hub settings.

Run as `docker run --rm --network none -e PYTHONPATH=/app -w /app ... python /tmp/smoke.py`.
The last line is the verdict; any failed check raises.
"""
import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

TMP = Path(tempfile.mkdtemp())
# No live settings: the image carries the hub's env names (many empty), and a DATABASE_URL would point
# the smoke at a real database. Same rule as the ARD smoke.
for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
os.chdir(TMP)
os.environ["AIMARKET_DB_PATH"] = str(TMP / "hub.db")
os.environ["AIMARKET_AUTO_CRAWL"] = "0"
os.environ["AIMARKET_FEDERATION_ASSAY"] = "0"

import httpx  # noqa: E402

import aimarket_hub  # noqa: E402
import aimarket_hub.crawler as cr  # noqa: E402

# Production starts `python -m aimarket_hub` in /app; an older wheel in site-packages must not answer.
# Independent runs from a venv, so its smoke names the patched copy it expects instead.
EXPECT_PKG = os.environ.get("SMOKE_EXPECT_PKG", "/app/aimarket_hub/")
assert aimarket_hub.__file__.startswith(EXPECT_PKG), aimarket_hub.__file__

from aimarket_hub import cli  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.crawler import Crawler  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.models import Peer  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

cr._url_is_safe = lambda url: url.startswith("https://")


def at(hours_ago: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def manifest(signer: Signer, generated_at: str, *names: str) -> dict:
    m = {"protocol_version": "v2", "generated_at": generated_at, "capabilities_count": len(names),
         "tools": [{"name": n, "capability_id": n + "@v1", "product_id": n, "description": n,
                    "input_schema": {"type": "object"}, "price_per_call_usd": 0.01} for n in names]}
    m["signature"] = signer.sign_manifest(m)
    return m


config = HubConfig()
config.hub_url = "https://smoke-hub.example"
config.db_path = os.environ["AIMARKET_DB_PATH"]
config.signing_key_path = str(TMP / "hub.key")
db = HubDatabase(config.db_path)
crawler = Crawler(config=config, db=db, signer=Signer(config.signing_key_path))
served: dict = {}


async def get(url):
    if ".well-known/" in url:
        return httpx.Response(200, json={
            "name": "Peer", "protocol_versions": ["v1", "v2"], "capabilities_count": 1,
            "manifest_url": served["base"] + "/manifest", "signer_public_key": served["key"]})
    return httpx.Response(200, json=served["m"])


crawler._safe_get = AsyncMock(side_effect=get)


def ids(url: str) -> list[str]:
    return sorted(c.capability_id for c in db.list_capabilities(source_hub=url, limit=100))


async def crawl(url: str, m: dict) -> int:
    served["m"] = m
    r = await crawler._crawl_one(url + "/.well-known/ai-market.json", 0, "smoke")
    return r["capabilities_count"]


async def main() -> str:
    assert db.get_catalogue_watermark("https://none.example") is None  # migration 066 applied
    checks = 0

    # 1. A replayed older catalogue cannot put back a withdrawn entry.
    p1, s1 = "https://peer-one.example", Signer(TMP / "p1.key")
    db.upsert_peer(Peer(url=p1, name="P1", public_key=s1.public_key_b64, trusted=True))
    served.update(base=p1, key=s1.public_key_b64)
    old, new = manifest(s1, at(3), "a", "b"), manifest(s1, at(2), "a")
    assert await crawl(p1, old) == 2
    assert await crawl(p1, new) == 1 and ids(p1) == ["a@v1"]
    assert not crawler._manifest_too_stale(old)
    assert await crawl(p1, old) == 0 and ids(p1) == ["a@v1"], ids(p1)
    assert await crawl(p1, new) == 1  # the same catalogue again
    newer = manifest(s1, at(1), "a", "c")
    assert await crawl(p1, newer) == 2 and ids(p1) == ["a@v1", "c@v1"]
    assert db.get_catalogue_watermark(p1)["generated_at"] == newer["generated_at"]
    checks += 6

    # 2. Operator reset through the CLI, then an older catalogue is accepted.
    assert cli.main(["peers", "--reset-catalogue-time", p1 + "/"]) == 0
    assert db.get_catalogue_watermark(p1) is None
    assert await crawl(p1, manifest(s1, at(4), "d")) == 1 and ids(p1) == ["d@v1"]
    checks += 2

    # 3. A new pinned key starts a new record.
    s1b = Signer(TMP / "p1b.key")
    db.upsert_peer(Peer(url=p1, name="P1", public_key=s1b.public_key_b64, trusted=True))
    served["key"] = s1b.public_key_b64
    assert await crawl(p1, manifest(s1b, at(5), "e")) == 1
    assert db.get_catalogue_watermark(p1)["public_key"] == s1b.public_key_b64
    checks += 1

    # 4. A far-future catalogue is never recorded, even with the max age switched off.
    p2, s2 = "https://peer-two.example", Signer(TMP / "p2.key")
    db.upsert_peer(Peer(url=p2, name="P2", public_key=s2.public_key_b64, trusted=True))
    served.update(base=p2, key=s2.public_key_b64)
    saved, config.manifest_max_age_s = config.manifest_max_age_s, 0
    assert await crawl(p2, manifest(s2, "2099-01-01T00:00:00Z", "f")) == 1
    assert db.get_catalogue_watermark(p2) is None
    config.manifest_max_age_s = saved
    checks += 1

    # 5. The pending-peer preview applies and records the same floor.
    p3, s3 = "https://peer-three.example", Signer(TMP / "p3.key")
    config.federation_preview_capabilities = True
    served.update(base=p3, key=s3.public_key_b64, m=manifest(s3, at(1), "g"))
    wk = {"manifest_url": p3 + "/manifest"}
    assert await crawler._preview_pending_manifest(wk, p3, s3.public_key_b64) == 1
    served["m"] = manifest(s3, at(2), "g", "h")
    assert await crawler._preview_pending_manifest(wk, p3, s3.public_key_b64) == 0
    checks += 2

    # 6. delete_peer forgets the record.
    assert db.delete_peer(p2) is True or db.get_peer(p2) is None
    db.record_catalogue_watermark(p1, public_key="k", generated_at=at(1))
    assert db.delete_peer(p1) and db.get_catalogue_watermark(p1) is None
    checks += 1

    await crawler.close()
    return f"catalogue floor smoke ok: {checks} checks, hub {aimarket_hub.__version__}"


print(asyncio.run(main()))
