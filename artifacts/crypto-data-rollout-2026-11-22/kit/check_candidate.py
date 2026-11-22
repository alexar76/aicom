"""Run inside the candidate image (RPC pool rollout 2026-11-22), as its own user, from /app, no network: build the app
on a scratch data dir and check what this rollout adds before anything live is touched."""
import asyncio, hashlib, json, tempfile
from pathlib import Path
import httpx
from fastapi.testclient import TestClient
from hestia.app import build_app, _rpc_pool
from hestia.config import Settings
from hestia.egress import Egress, EgressRequest, EgressRefused

tmp = Path(tempfile.mkdtemp())
c = TestClient(build_app(Settings.for_test(tmp)))
out = {"health": c.get("/health").json().get("ok")}
catalog = c.get("/agents/catalog.json").json()
bad = [a["slug"] for a in catalog["agents"]
       if hashlib.sha256(c.get("/agents/" + a["source_file"]).content).hexdigest() != a["handler_sha256"]]
out["catalog_agents"], out["catalog_bad"] = len(catalog["agents"]), bad
pool = _rpc_pool("default")
out["pool_hosts"] = sorted(pool.hosts)
out["pool_off"] = _rpc_pool("0") is None
seen = []
def handler(req):
    seen.append(req.headers["host"])
    body = json.loads(req.content)
    return httpx.Response(200, json=[{"jsonrpc": "2.0", "id": x["id"], "result": "0x6"} for x in body])
e = Egress(resolve=lambda h: ["93.184.215.14"], transport=httpx.MockTransport(handler), rpc_pool=pool, rpc_calls_per_minute=5)
name = "base-rpc.hestia.modelmarket.dev"
body = json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []},
                   {"jsonrpc": "2.0", "id": 2, "method": "eth_call", "params": [{"to": "0x" + "1" * 40, "data": "0x"}, "0x10"]}])
req = EgressRequest.parse({"url": "https://" + name + "/", "method": "POST", "body": body}, [name])
r = json.loads(asyncio.run(e.fetch("t", req))["text"])
r2 = json.loads(asyncio.run(e.fetch("t", req))["text"])
out["pool_answer"] = [r[0]["result"], r[1]["result"], r2 == r, len(seen)]
try:
    asyncio.run(e.fetch("t", req)); out["budget"] = "not enforced"
except EgressRefused as x:
    out["budget"] = str(x)[:60]
print(json.dumps(out))
