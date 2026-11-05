"""Memory-market smoke inside the new image, no network, dev mode, temp SQLite: a named buyer owns its private
memory; another buyer, an empty channel header and no header read nothing and cannot write."""
import os
import tempfile

os.environ["AIFACTORY_DEV"] = "1"
os.environ.pop("AIFACTORY_PROD", None)
from types import SimpleNamespace  # noqa: E402
from fastapi import HTTPException, Request, Response  # noqa: E402
import memory_market.app as m  # noqa: E402
from memory_market.store import MemoryStore  # noqa: E402

store = MemoryStore(os.path.join(tempfile.mkdtemp(), "smoke.sqlite3"))
m.store = lambda: store
m.provider_signer = lambda: SimpleNamespace(response_headers=lambda *a, **k: {}, pq_public_key=None)


def call(cid, payload, headers=None):
    req = Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]})
    return m.invoke_capability(m.BY_CAPABILITY[cid].product_id, cid, {"input": payload}, req, Response())["result"]


A = {"X-AIMarket-Buyer-Ref": "bref-" + "a" * 32}
unit = call("memory.write@v1", {"title": "smoke", "content": "private smoke", "visibility": "private"}, A)
assert unit["owner_id"] == "aimarket:bref-" + "a" * 32
assert call("memory.read@v1", {"memory_id": unit["id"]}, A)["id"] == unit["id"]
for h in ({"X-AIMarket-Buyer-Ref": "bref-" + "b" * 32}, {}, {"X-Payment-Channel": ""}):
    try:
        call("memory.read@v1", {"memory_id": unit["id"]}, h)
        raise SystemExit(f"read leaked to {h}")
    except HTTPException as e:
        assert e.status_code == 403
    assert call("memory.search@v1", {"query": "smoke"}, h)["items"] == []
for h in ({}, {"X-Payment-Channel": ""}):
    try:
        call("memory.write@v1", {"title": "x", "content": "y"}, h)
        raise SystemExit("anonymous write accepted")
    except HTTPException as e:
        assert e.status_code == 403
print("memory-market smoke ok: owner = named buyer, others and anonymous read nothing, anonymous cannot write")
