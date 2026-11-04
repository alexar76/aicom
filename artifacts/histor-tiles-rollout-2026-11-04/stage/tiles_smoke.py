"""Candidate smoke for the tiles overlay: a disposable HISTOR, 300 synthetic labels, the tile routes over ASGI."""
import asyncio
import base64
import hashlib
import json

import httpx
from awr import canonicalize

from histor import merkle
from histor.app import create_app
from histor.config import load_settings
from histor.service import build
from histor.store import Store


def mth(leaves):
    if len(leaves) == 1:
        return leaves[0]
    k = 1
    while k * 2 < len(leaves):
        k *= 2
    return hashlib.sha256(b"\x01" + mth(leaves[:k]) + mth(leaves[k:])).digest()


async def smoke():
    import histor
    assert histor.__file__.startswith("/app/histor/"), histor.__file__  # the overlay, as production imports it
    services = build(load_settings())
    store = services.store
    with store.db.transaction() as tx:
        tx.lock_log()
        for i in range(300):
            doc = {"id": f"urn:uuid:smoke-{i:05d}", "n": i, "s": "é" * (i % 5)}
            idx = Store.append_leaf(tx, merkle.leaf_hash(canonicalize(doc)))
            tx.execute("INSERT INTO labels(id, target_id, method, verdict, subject, observed_at, issued_at, digest, "
                       "leaf_index, body) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (doc["id"], None, "m", "v", "s", "t", "t", f"d{i}", idx, json.dumps(doc, ensure_ascii=False)))
    services.logbook.publish_sth()
    try:
        transport = httpx.ASGITransport(app=create_app(services))
        async with httpx.AsyncClient(transport=transport, base_url="https://histor.modelmarket.dev") as c:
            cp = await c.get("/log/checkpoint")
            assert cp.status_code == 200 and cp.text == (await c.get("/checkpoint")).text, cp.status_code
            lines = cp.text.split("\n")
            assert lines[0] == "histor.modelmarket.dev/log" and lines[1] == "300", lines[:2]
            full = await c.get("/log/tile/0/000")
            part = await c.get("/log/tile/0/001.p/44")
            up = await c.get("/log/tile/1/000.p/1")
            bundle = await c.get("/log/tile/entries/001.p/44")
            for r in (full, part, up, bundle):
                assert r.status_code == 200 and r.headers["content-type"] == "application/octet-stream", r.status_code
            assert len(full.content) == 8192 and len(part.content) == 44 * 32 and len(up.content) == 32
            hashes = [full.content[i:i + 32] for i in range(0, 8192, 32)]
            assert up.content == mth(hashes)
            tail = [part.content[i:i + 32] for i in range(0, 44 * 32, 32)]
            data, i, n = bundle.content, 0, 0
            while i < len(data):
                ln = int.from_bytes(data[i:i + 2], "big")
                assert merkle.leaf_hash(data[i + 2:i + 2 + ln]) == tail[n]
                i, n = i + 2 + ln, n + 1
            assert n == 44
            assert mth(hashes + tail) == base64.b64decode(lines[2])
            assert (await c.get("/log/tile/0/001")).status_code == 404
            assert (await c.get("/log/tile/0/01")).status_code == 404
            assert (await c.get("/health")).status_code == 200
            issuer = (await c.get("/api/v1/issuer")).json()
            assert issuer["checkpoint"]["tiles"]["prefix"].endswith("/log/"), issuer["checkpoint"]
    finally:
        services.close()


asyncio.run(smoke())
print("Candidate tiles smoke passed: checkpoint, full/partial/level-1 tiles, entry bundle, root, 404s, health")
