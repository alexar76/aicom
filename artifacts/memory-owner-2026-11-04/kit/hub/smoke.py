"""Buyer-ref smoke inside the new hub image, no network: a throw-away hub on a temp DB, no live settings.
Two credit accounts call an operator gateway provider (safe_post stubbed): each gets one stable bref-, different
from the other; a third-party URL gets none; the hub still answers health."""
import os
import tempfile

for name in list(os.environ):
    if name.startswith(("AIMARKET_", "AIFACTORY_", "HUB_")) or "DATABASE" in name or name.startswith("PG"):
        del os.environ[name]
CAP = "smoke-capability-token-" + "x" * 32
os.environ.update(AIMARKET_AUTO_CRAWL="0", AIMARKET_FEDERATION_ASSAY="0", AIMARKET_ADMIN_TOKEN="smoke-admin",
                  AIMARKET_CREDITS_ENABLED="1", AIMARKET_ORACLE_FAMILY_URL="off", AIMARKET_SUPPLY_MIN_STAKE_USD="0",
                  AIMARKET_CREDITS_FREE_GRANT_USD="0", AIMARKET_CAPABILITY_TOKEN=CAP,
                  AIMARKET_INVOKE_HOST_GATEWAY="memory-market", AIMARKET_ALLOW_LOCAL_PUBLISH="1")
tmp = tempfile.mkdtemp()
os.chdir(tmp)

from fastapi.testclient import TestClient  # noqa: E402
import aimarket_hub.crawler as crawler  # noqa: E402
import aimarket_hub.outbound_http as outbound  # noqa: E402
from aimarket_hub import provider_buyer_ref  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402
from aimarket_hub.signing import Signer  # noqa: E402

captured = []


class _Resp:
    status_code = 200
    headers = {"content-type": "application/json"}
    text = '{"success": true}'

    @staticmethod
    def json():
        return {"success": True, "result": {"ok": True}}


async def _post(url, **kwargs):
    captured.append((url, dict(kwargs.get("headers") or {})))
    return _Resp()


outbound.safe_post = _post
crawler._url_is_safe = lambda url: url == "https://example.com/invoke"
config = HubConfig()
config.hub_url = "https://smoke.example"
config.db_path = os.path.join(tmp, "hub.db")
config.signing_key_path = os.path.join(tmp, "hub.key")
admin = {"Authorization": "Bearer smoke-admin"}
with TestClient(create_app(config=config, db=HubDatabase(config.db_path), signer=Signer(config.signing_key_path))) as c:
    def account():
        a = c.post("/ai-market/v2/accounts", json={"label": "b"}).json()
        c.post(f"/ai-market/v2/accounts/{a['account_id']}/credit", json={"amount_usd": 1.0}, headers=admin)
        return a["api_key"]

    for pid, cid, url in (("memory-write", "memory.write@v1", "http://memory-market:8810/capabilities/memory-write/memory.write@v1/invoke"),
                          ("ext-svc", "ext.svc@v1", "https://example.com/invoke")):
        r = c.post("/ai-market/v2/supply/register", headers={"X-API-Key": account()}, json={
            "product_id": pid, "capability_id": cid, "name": "n", "description": "d", "invoke_url": url,
            "price_per_call_usd": 0.001, "input_schema": {"type": "object"}, "output_schema": {"type": "object"}})
        assert r.status_code == 200, r.text
    alice, bob = account(), account()
    for key, pid, cid in ((alice, "memory-write", "memory.write@v1"), (alice, "memory-write", "memory.write@v1"),
                          (bob, "memory-write", "memory.write@v1"), (alice, "ext-svc", "ext.svc@v1")):
        r = c.post("/ai-market/v2/invoke", headers={"X-API-Key": key},
                   json={"product_id": pid, "capability_id": cid, "input": {}, "source_hub": "local"})
        assert r.status_code == 200, r.text
    assert c.get("/ai-market/v2/health").status_code == 200

refs = [h.get(provider_buyer_ref.HEADER) for _, h in captured]
assert len(refs) == 4, refs
assert refs[0] and refs[0].startswith("bref-") and refs[0] == refs[1] != refs[2], refs
assert refs[3] is None, "third-party seller got the buyer ref"
assert captured[0][1].get("X-AIMarket-Internal-Token") == CAP
print("hub buyer-ref smoke ok: stable per account, distinct across accounts, none to a third party, health 200")
