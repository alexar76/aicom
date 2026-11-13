"""Run fixed-GET observation and paid bridge checks on disposable ledger copies."""

import asyncio
import base64
import json
import os
from pathlib import Path
import sqlite3
import tempfile


MODE = os.sys.argv[1]
TEMP = Path(tempfile.mkdtemp(prefix="hub-x402-smoke-"))
os.chdir(TEMP)
for key in list(os.environ):
    if key.startswith(("AIMARKET_", "AIFACTORY_", "HUB_", "PG")) or "DATABASE" in key:
        del os.environ[key]
ORIGIN = "https://fixed-get-smoke.invalid"
ENDPOINT = ORIGIN + "/quotes"
URL = ENDPOINT + "?id=1,1027"
PAYEE = "0x" + "11" * 20
ADMIN = {"Authorization": "Bearer isolated-smoke-operator"}
os.environ.update({
    "AIMARKET_DB_PATH": "/smoke/hub.db", "AIMARKET_CHANNELS_DB_PATH": "/smoke/channels.db",
    "AIMARKET_CREDITS_ENABLED": "1", "AIMARKET_AUTO_CRAWL": "0", "AIMARKET_FEDERATION_ASSAY": "0",
    "AIMARKET_SKIP_SEED": "1", "AIMARKET_SIGNING_KEY_PATH": str(TEMP / "smoke.key"),
    "AIMARKET_HUB_URL": "https://x402-observer-smoke.invalid", "AIMARKET_DEPOSIT_CLAIMS_DIR": str(TEMP / "claims"),
    "AIMARKET_ADMIN_TOKEN": ADMIN["Authorization"].split()[1], "AIMARKET_OBSERVED_EXPLICIT_GET_ORIGINS": ORIGIN,
})


def migrations(path):
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA quick_check").fetchone() == ("ok",)
        return sorted(row[0] for row in db.execute("SELECT version FROM _migrations"))


paths = ["/smoke/hub.db", "/smoke/channels.db"]
before = [migrations(path) for path in paths]

from fastapi.testclient import TestClient  # noqa: E402
from aimarket_hub import observed_sellers, x402_bridge  # noqa: E402
from aimarket_hub.api import create_app  # noqa: E402
from aimarket_hub.config import HubConfig  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402

config = HubConfig()
config.db_path = paths[0]
db = HubDatabase(config.db_path)
with TestClient(create_app(config=config, db=db)) as client:
    replies = {path: client.get(path).status_code for path in (
        "/ai-market/v2/health", "/ai-market/v2/account/withdrawals", "/ai-market/v2/federation/observed-sellers",
        "/ai-market/v2/x402-bridge",
    )}
    assert tuple(replies.values()) == (200, 401, 200, 200), replies
    denied = client.post("/ai-market/v2/federation/observed-sellers", json={"origin": ORIGIN})
    assert denied.status_code == 401, denied.status_code
assert [migrations(path) for path in paths] == before

report = {"mode": MODE, "health": replies, "operator_auth_required": True, "migrations_added": 0}
if MODE == "candidate":
    challenge = {"x402Version": 2, "resource": {"url": ENDPOINT}, "accepts": [{
        "scheme": "exact", "network": "eip155:8453", "asset": x402_bridge.USDC, "amount": "10000",
        "payTo": PAYEE, "maxTimeoutSeconds": 30,
        "extra": {"name": "USD Coin", "version": "2", "assetTransferMethod": "eip3009"},
    }]}
    header = {"payment-required": base64.b64encode(json.dumps(challenge).encode()).decode()}
    calls = []

    async def fixture(method, url, headers, max_bytes, json_body):
        assert not set(map(str.lower, headers)) & {"payment-signature", "x-payment", "authorization"}
        calls.append((method, url))
        if url.endswith(("/.well-known/x402", "/.well-known/x402.json")):
            return {"status": 404}
        assert url == URL and json_body is None
        return {"status": 200} if method == "HEAD" else {"status": 402, "headers": header}

    seller = {"origin": ORIGIN, "pinned_pay_to": PAYEE, "allowed_routes": [URL],
              "consent": {"by": "synthetic seller", "at": "2026-11-13T00:00:00Z", "confirmed_pay_to": PAYEE}}
    observed = asyncio.run(observed_sellers.observe_seller(seller, request=fixture))
    route, = observed_sellers.served_routes([{**seller, **observed}])
    assert route["source"] == observed_sellers.EXPLICIT_GET_SOURCE
    assert route["method"] == "GET" and route["url"] == URL and route["amount_atomic"] == "10000"
    assert [method for method, _ in calls] == ["GET", "GET", "HEAD", "GET"]
    assert x402_bridge.choose_offer({}, header, limit_usd=0.01, expected_pay_to=PAYEE,
                                    explicit_get_url=URL).amount_atomic == 10000
    for price, pin, target in ((0.00999, PAYEE, URL), (0.01, "0x" + "22" * 20, URL), (0.01, PAYEE, ORIGIN + "/other")):
        try:
            x402_bridge.choose_offer({}, header, limit_usd=price, expected_pay_to=pin, explicit_get_url=target)
        except x402_bridge.BridgeRefused:
            continue
        raise AssertionError("mismatching price, pin or resource was accepted")
    os.environ.pop("AIMARKET_OBSERVED_EXPLICIT_GET_ORIGINS")
    assert observed_sellers.served_routes([{**seller, **observed}]) == []
    report["fixed_get"] = {"unsigned_request_sequence": [method for method, _ in calls], "price_atomic": 10000,
                           "wrong_terms_refused": 3, "removing_opt_in_hides_route": True}
    from aimarket_hub import settle

    tx, block, nonce = ("0x" + pair * 32 for pair in ("aa", "bb", "cc"))
    payer = "0x" + "33" * 20
    payer_topic = "0x" + payer[2:].zfill(64)
    payee_topic = "0x" + PAYEE[2:].zfill(64)
    offer = x402_bridge.choose_offer({}, header, limit_usd=0.01, expected_pay_to=PAYEE, explicit_get_url=URL)
    alias = {"success": True, "txHash": tx, "networkId": "eip155:8453", "x402FlowId": "synthetic"}
    assert x402_bridge._cmc_settlement_tx(alias, wallet=payer, offer=offer) == tx
    assert not x402_bridge._cmc_settlement_tx({**alias, "transaction": block}, wallet=payer, offer=offer)
    facts = {"address": x402_bridge.USDC, "transactionHash": tx, "blockHash": block, "blockNumber": "0x80"}
    logs = [{**facts, "logIndex": "0x4", "data": "0x", "topics": [settle.AUTHORIZATION_USED_TOPIC, payer_topic, nonce]},
            {**facts, "logIndex": "0x5", "data": f"0x{10000:064x}",
             "topics": [settle.TRANSFER_TOPIC, payer_topic, payee_topic]}]

    def rpc(method, params):
        return {"eth_chainId": "0x2105", "eth_getTransactionReceipt": {**facts, "status": "0x1", "logs": logs},
                "eth_getBlockByNumber": {"number": "0x80", "hash": block}}[method]

    assert x402_bridge._cmc_paid_on_base(tx, wallet=payer, nonce=nonce, offer=offer, rpc=rpc)
    assert not x402_bridge._cmc_paid_on_base(tx, wallet=payer, nonce=tx, offer=offer, rpc=rpc)
    report["cmc_receipt"] = {"alias_and_exact_chain_payment_verified": True,
                             "conflicting_hash_rejected": True, "different_nonce_rejected": True}
print(json.dumps(report, sort_keys=True))
