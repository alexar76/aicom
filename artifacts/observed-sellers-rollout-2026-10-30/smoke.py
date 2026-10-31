"""Smoke for the observed-seller overlay, run inside the overlay image (no network, temp dirs)."""
import json, os, tempfile
os.environ.update({"AIMARKET_ADMIN_TOKEN": "smoke-admin", "AIMARKET_FEDERATION_ASSAY": "0", "AIMARKET_AUTO_CRAWL": "0",
                   "AIMARKET_ORACLE_FAMILY_URL": "off"})
os.environ.pop("AIMARKET_REALM", None)
from fastapi.testclient import TestClient
from aimarket_hub import crawler, observed_sellers as obs
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
S = "https://seller.example"; PAY = "0x1111111111111111111111111111111111111111"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DOC = {"x402Version": 2, "endpoints": [{"url": f"{S}/read-page", "method": "POST", "priceUsdCents": 0.2,
       "description": "Read Page - a URL as clean LLM-ready text."}]}
calls = []
async def fake(method, url, headers, max_bytes, json_body):
    calls.append((method, url, sorted(k.lower() for k in headers)))
    if url == S + "/.well-known/x402":
        return {"status": 200, "json": DOC, "headers": {}}
    if url.startswith(S + "/.well-known/"):
        return {"status": 404, "json": None, "headers": {}}
    return {"status": 402, "headers": {}, "json": {"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base",
            "maxAmountRequired": "2000", "asset": USDC, "payTo": PAY, "resource": url}]}}
crawler._url_is_safe = lambda url: url.startswith("https://")
obs._default_request = fake
root = tempfile.mkdtemp()
cfg = HubConfig(); cfg.db_path = f"{root}/hub.db"; cfg.signing_key_path = f"{root}/key"
db = HubDatabase(f"{root}/hub.db")
A = {"Authorization": "Bearer smoke-admin"}
with TestClient(create_app(config=cfg, db=db, signer=Signer(f"{root}/key"))) as c:
    assert db._conn.execute("SELECT COUNT(*) AS n FROM observed_sellers").fetchone()["n"] == 0
    assert c.post("/ai-market/v2/federation/observed-sellers", json={"origin": S}).status_code == 401
    r = c.post("/ai-market/v2/federation/observed-sellers", headers=A,
               json={"origin": S, "consent": {"by": "x@seller.example", "at": "2026-10-30", "how": "email"}})
    assert r.status_code == 200, r.text
    assert r.json()["seller"]["routes_served"] == 1, r.json()
    assert not any("payment" in h or "x-payment" in h for _, _, hs in calls for h in hs), calls
    found = c.get("/ai-market/v2/search", params={"intent": "read page text"}).json()
    assert found["observed"][0]["pay_to"] == PAY and found["observed"][0]["price_usd"] == 0.002, found["observed"]
    assert all(m.get("source_hub") != S for m in found["matches"])
    wk = c.get("/.well-known/ai-market.json").json()
    assert wk["observed_sellers"][0]["origin"] == S and wk["observed_sellers_url"].endswith("/federation/observed-sellers")
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "market_search", "arguments": {"intent": "read a web page as clean text"}}})
    frame = next(l[5:].strip() for l in r.text.splitlines() if l.startswith("data:"))
    assert json.loads(json.loads(frame)["result"]["content"][0]["text"])["observed"][0]["url"] == f"{S}/read-page"
    assert c.delete("/ai-market/v2/federation/observed-sellers", headers=A, params={"origin": S}).status_code == 200
    assert c.get("/ai-market/v2/federation/observed-sellers").json()["sellers"] == []
print("SMOKE OK", len(calls), "requests, none paid")
