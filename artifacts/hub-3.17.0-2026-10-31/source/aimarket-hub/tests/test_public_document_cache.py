"""The hub's heavy public documents are built off the event loop and memoised.

On 2026-10-16 hub.attestedmemory.net went down twice: a monitor asked for
`/ai-market/v2/stats/live` and `/.well-known/ai-market.json` every 1.5 s, each took
0.3-0.5 s on a crowded CPU inside an `async def` on the single event loop, and `/health`
queued behind them until the edge timed out. These pin the two halves of the fix: a slow
build no longer holds `/health`, and a burst of callers costs one build per TTL.
"""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Peer
from aimarket_hub.public_cache import PublicDocumentCache
from aimarket_hub.signing import Signer

WELL_KNOWN = "/.well-known/ai-market.json"
STATS_LIVE = "/ai-market/v2/stats/live"
MANIFEST = "/ai-market/v2/manifest"
HEALTH = "/ai-market/v2/health"


@pytest.fixture
def hub():
    with tempfile.TemporaryDirectory() as tmp:
        config = HubConfig()
        config.db_path = str(Path(tmp) / "hub.db")
        config.signing_key_path = str(Path(tmp) / "key")
        db = HubDatabase(Path(tmp) / "hub.db")
        app = create_app(config=config, db=db, signer=Signer(Path(tmp) / "key"))
        yield app, db


# ── The memo itself ─────────────────────────────────────────────


def test_memo_builds_once_per_ttl(monkeypatch):
    monkeypatch.setenv("T_CACHE_S", "30")
    cache = PublicDocumentCache("T_CACHE_S", 0)
    calls = []
    assert cache.get("k", lambda: calls.append(1) or len(calls)) == 1
    assert cache.get("k", lambda: calls.append(1) or len(calls)) == 1
    assert cache.get("other", lambda: calls.append(1) or len(calls)) == 2
    assert len(calls) == 2


def test_memo_expires(monkeypatch):
    monkeypatch.setenv("T_CACHE_S", "0.05")
    cache = PublicDocumentCache("T_CACHE_S", 0)
    calls = []
    cache.get("k", lambda: calls.append(1))
    time.sleep(0.08)
    cache.get("k", lambda: calls.append(1))
    assert len(calls) == 2


def test_zero_ttl_turns_the_memo_off(monkeypatch):
    monkeypatch.setenv("T_CACHE_S", "0")
    cache = PublicDocumentCache("T_CACHE_S", 60)
    calls = []
    for _ in range(3):
        cache.get("k", lambda: calls.append(1))
    assert len(calls) == 3


def test_a_failed_build_is_not_remembered(monkeypatch):
    monkeypatch.setenv("T_CACHE_S", "30")
    cache = PublicDocumentCache("T_CACHE_S", 0)

    def boom():
        raise RuntimeError("db down")

    with pytest.raises(RuntimeError):
        cache.get("k", boom)
    assert cache.get("k", lambda: "ok") == "ok"


def test_a_burst_on_an_expired_entry_costs_one_build(monkeypatch):
    """Single-flight: twelve callers arriving together wait for one build."""
    monkeypatch.setenv("T_CACHE_S", "30")
    cache = PublicDocumentCache("T_CACHE_S", 0)
    builds = []
    start = threading.Barrier(12)

    def slow_build():
        builds.append(1)
        time.sleep(0.2)
        return "doc"

    results = []

    def caller():
        start.wait()
        results.append(cache.get("k", slow_build))

    threads = [threading.Thread(target=caller) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == ["doc"] * 12
    assert len(builds) == 1


def test_bad_ttl_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("T_CACHE_S", "soon")
    assert PublicDocumentCache("T_CACHE_S", 42).ttl_s() == 42


# ── The routes ──────────────────────────────────────────────────


def test_well_known_is_memoised_and_still_signed(hub, monkeypatch):
    monkeypatch.setenv("AIMARKET_WELL_KNOWN_CACHE_S", "60")
    app, db = hub
    with TestClient(app) as client:
        first = client.get(WELL_KNOWN).json()
        db.upsert_peer(Peer(url="https://late-peer.example", name="late"))
        second = client.get(WELL_KNOWN).json()
        assert second == first, "a cached answer must be byte-for-byte the signed one"
        assert "signature" in second
        assert client.head(WELL_KNOWN).status_code == 200


def test_well_known_reflects_changes_with_the_memo_off(hub, monkeypatch):
    monkeypatch.setenv("AIMARKET_WELL_KNOWN_CACHE_S", "0")
    app, db = hub
    with TestClient(app) as client:
        client.get(WELL_KNOWN)
        db.upsert_peer(Peer(url="https://late-peer.example", name="late"))
        peers = client.get(WELL_KNOWN).json()["peers"]
        assert any(p["url"] == "https://late-peer.example" for p in peers)


def test_stats_live_is_memoised_per_page_size(hub, monkeypatch):
    monkeypatch.setenv("AIMARKET_STATS_LIVE_CACHE_S", "30")
    app, db = hub
    builds = []
    real = db.recent_stats

    def counting(limit=50):
        builds.append(limit)
        return real(limit=limit)

    monkeypatch.setattr(db, "recent_stats", counting)
    with TestClient(app) as client:
        for _ in range(5):
            assert client.get(STATS_LIVE).status_code == 200
        client.get(f"{STATS_LIVE}?limit=10")
        client.get(f"{STATS_LIVE}?limit=10")
        # The cap at 200 is applied before the key, so oversized limits share one entry.
        client.get(f"{STATS_LIVE}?limit=500")
        client.get(f"{STATS_LIVE}?limit=900")
    assert builds == [50, 10, 200]


@pytest.mark.parametrize(
    "path, slow_attr",
    [
        (WELL_KNOWN, "list_peers"),
        (STATS_LIVE, "recent_stats"),
        (MANIFEST, "list_peers"),
    ],
)
def test_a_slow_build_does_not_hold_health(hub, monkeypatch, path, slow_attr):
    """The outage itself: /health must answer while a heavy document is being built."""
    app, db = hub
    real = getattr(db, slow_attr)

    def slow(*args, **kwargs):
        time.sleep(0.6)  # synchronous, like a DB read on a crowded CPU
        return real(*args, **kwargs)

    monkeypatch.setattr(db, slow_attr, slow)

    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://hub") as c:
            heavy = asyncio.create_task(c.get(path))
            await asyncio.sleep(0.05)  # let the heavy request get going first
            t0 = time.perf_counter()
            health = await c.get(HEALTH)
            health_s = time.perf_counter() - t0
            heavy_done_when_health_answered = heavy.done()
            assert (await heavy).status_code == 200
            return health.status_code, health_s, heavy_done_when_health_answered

    status, health_s, heavy_done = asyncio.run(scenario())
    assert status == 200
    assert not heavy_done, "health waited for the heavy build"
    assert health_s < 0.4, f"/health took {health_s:.2f}s behind {path}"
