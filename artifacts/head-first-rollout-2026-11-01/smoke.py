"""Smoke for the HEAD-first overlay, run inside the overlay image (no network, temp dirs).

1. A seller that answers HEAD with a V2 402 (terms in PAYMENT-REQUIRED) is listed through the whole app (consent,
   /search, well-known, MCP market_search) and its route sees only HEAD: the POST it would serve free is never sent.
2. A route that answers HEAD 405 (POST-only) falls back to the one unpaid POST of spec §2.7 and is still quoted.
3. A route that answers HEAD 200 (the free call is spent already) is not_priced, with no second request.
No request carries a payment header.
"""
import asyncio, base64, json, os, tempfile
# The security session's images carry the live container's environment (on UNI as empty strings, which int() refuses).
# The smoke runs on defaults instead: every hub setting from the image is dropped, data goes to a temp dir.
for name in [n for n in os.environ if n.startswith(("AIMARKET_", "AIFACTORY_", "ACEX_", "HUB_", "LOTTERY_", "ALIEN_"))]:
    del os.environ[name]
root = tempfile.mkdtemp()
os.environ.update({"AIMARKET_ADMIN_TOKEN": "smoke-admin", "AIMARKET_FEDERATION_ASSAY": "0", "AIMARKET_AUTO_CRAWL": "0",
                   "AIMARKET_ORACLE_FAMILY_URL": "off", "AIMARKET_SANDBOX_DB_PATH": f"{root}/sandbox_trials.db",
                   "AIMARKET_DB_PATH": f"{root}/hub.db", "AIMARKET_SIGNING_KEY_PATH": f"{root}/key"})
from fastapi.testclient import TestClient
from aimarket_hub import crawler, observed_sellers as obs
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer
assert hasattr(obs, "_HEAD_FALLBACK_STATUSES"), obs.__file__
S = "https://seller.example"; PAY = "0x1111111111111111111111111111111111111111"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
DOC = {"x402Version": 2, "endpoints": [{"url": f"{S}/read-page", "method": "POST", "priceUsdCents": 0.2,
       "description": "Read Page - a URL as clean LLM-ready text."}]}


def v2_header(url):
    terms = {"x402Version": 2, "resource": {"url": url, "description": "Read Page"},
             "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": "2000", "asset": USDC, "payTo": PAY}]}
    return {"PAYMENT-REQUIRED": base64.b64encode(json.dumps(terms).encode()).decode()}


V1_BODY = {"x402Version": 1, "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "2000",
                                          "asset": USDC, "payTo": PAY, "resource": f"{S}/x"}]}
calls = []


async def head_first_seller(method, url, headers, max_bytes, json_body):
    calls.append((method, url, sorted(k.lower() for k in headers)))
    if url == S + "/.well-known/x402":
        return {"status": 200, "json": DOC, "headers": {}}
    if url.startswith(S + "/.well-known/"):
        return {"status": 404, "json": None, "headers": {}}
    if method == "HEAD":
        return {"status": 402, "json": None, "headers": v2_header(url)}
    return {"status": 200, "json": {"ok": True}, "headers": {}}  # served free: must never be sent


def no_payment_header(seen):
    return not any(h in ("x-payment", "payment-signature", "authorization") for _, _, hs in seen for h in hs)


crawler._url_is_safe = lambda url: url.startswith("https://")
obs._default_request = head_first_seller
cfg = HubConfig(); cfg.db_path = f"{root}/hub.db"; cfg.signing_key_path = f"{root}/key"
db = HubDatabase(f"{root}/hub.db")
A = {"Authorization": "Bearer smoke-admin"}
with TestClient(create_app(config=cfg, db=db, signer=Signer(f"{root}/key"))) as c:
    assert c.post("/ai-market/v2/federation/observed-sellers", json={"origin": S}).status_code == 401
    r = c.post("/ai-market/v2/federation/observed-sellers", headers=A,
               json={"origin": S, "consent": {"by": "x@seller.example", "at": "2026-11-01", "how": "email"}})
    assert r.status_code == 200, r.text
    assert r.json()["seller"]["routes_served"] == 1, r.json()
    route_calls = [m for m, u, _ in calls if "/.well-known/" not in u]
    assert route_calls == ["HEAD"], calls
    assert no_payment_header(calls), calls
    found = c.get("/ai-market/v2/search", params={"intent": "read page text"}).json()
    assert found["observed"][0]["pay_to"] == PAY and found["observed"][0]["price_usd"] == 0.002, found["observed"]
    wk = c.get("/.well-known/ai-market.json").json()
    assert wk["observed_sellers"][0]["origin"] == S
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "market_search", "arguments": {"intent": "read a web page as clean text"}}})
    frame = next(l[5:].strip() for l in r.text.splitlines() if l.startswith("data:"))
    assert json.loads(json.loads(frame)["result"]["content"][0]["text"])["observed"][0]["url"] == f"{S}/read-page"
    assert c.delete("/ai-market/v2/federation/observed-sellers", headers=A, params={"origin": S}).status_code == 200
    assert c.get("/ai-market/v2/federation/observed-sellers").json()["sellers"] == []


def seller(head, other):
    seen = []

    async def request(method, url, headers, max_bytes, json_body):
        seen.append((method, url, sorted(k.lower() for k in headers)))
        return head if method == "HEAD" else other
    return seen, request


seen, req = seller({"status": 405, "json": None, "headers": {}}, {"status": 402, "json": V1_BODY, "headers": {}})
probe = asyncio.run(obs.probe_route({"url": f"{S}/x", "method": "POST"}, request=req))
assert probe["result"] == "quoted" and probe["probe_method"] == "POST", probe
assert [m for m, _, _ in seen] == ["HEAD", "POST"] and no_payment_header(seen), seen

seen, req = seller({"status": 200, "json": None, "headers": {}}, {"status": 200, "json": {"ok": True}, "headers": {}})
probe = asyncio.run(obs.probe_route({"url": f"{S}/x", "method": "GET"}, request=req))
assert probe["result"] == "not_priced" and probe["probe_method"] == "HEAD", probe
assert [m for m, _, _ in seen] == ["HEAD"], seen
print("SMOKE OK: head-first listed with HEAD only, 405 fell back to one POST, a free HEAD was not asked twice")
