"""claim.audit.direct@v1: Independent pays Attested per call in USDC on Base — no prepaid account.

End to end in one process: Attested's real hub sells its two checks seller-direct (a 402 with the
seller's terms), Independent's real hub sells the audit, and the provider between them signs EIP-3009
authorizations with its own wallet and sends them to a fake Base node. The node behaves like USDC:
it recovers the EIP-712 signer and only then mines the AuthorizationUsed + Transfer logs, which the
Attested hub's own settlement code reads. Nothing is mocked between the provider's signature and the
hub's verdict.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_account.typed_transactions import TypedTransaction
from eth_utils import keccak
from fastapi.testclient import TestClient
from hexbytes import HexBytes

from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer
from tests._mandate_kit import ADMIN_TOKEN, HUB, balance, funded_account, hub
from tests.test_cross_company_example import AUDIT_URL, EXAMPLE_DIR, _Resp, audit_server

ATTESTED = "https://attested.test"
ATTESTED_WALLET = "0xb73d8bc93b791510c4733c5c5ac2015a3c2930ec"
USDC = audit_server.USDC_BASE
RPC = "http://base-rpc.test"
AUTH_USED = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
PRICES = {"claim.check@v1": 0.022, "contradiction.scan@v1": 0.009}


def _pad(address: str) -> str:
    return "0x" + address[2:].lower().rjust(64, "0")


class FakeBase:
    """Just enough of a Base node and of USDC's transferWithAuthorization to be honest about it."""

    def __init__(self, usdc_balance: int = 1_000_000):
        self.head = 1_000
        self.balance = usdc_balance
        self.nonces: dict[str, int] = {}
        self.receipts: dict[str, dict] = {}
        self.paid: list[dict] = []          # every authorization the token executed
        self.used: set[str] = set()

    def _authorization(self, data: bytes) -> dict:
        words = [data[4 + 32 * i: 4 + 32 * (i + 1)] for i in range(9)]
        auth = {"from": "0x" + words[0][-20:].hex(), "to": "0x" + words[1][-20:].hex(),
                "value": int.from_bytes(words[2], "big"), "validAfter": int.from_bytes(words[3], "big"),
                "validBefore": int.from_bytes(words[4], "big"), "nonce": "0x" + words[5].hex(),
                "v": int.from_bytes(words[6], "big"), "r": words[7], "s": words[8]}
        typed = {"types": audit_server.EIP712_TYPES, "primaryType": "TransferWithAuthorization",
                 "domain": {"name": "USD Coin", "version": "2", "chainId": 8453,
                            "verifyingContract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
                 "message": {k: auth[k] for k in ("from", "to", "value", "validAfter", "validBefore", "nonce")}}
        signer = Account.recover_message(encode_typed_data(full_message=typed),
                                         vrs=(auth["v"], auth["r"], auth["s"]))
        if data[:4].hex() != audit_server.TRANSFER_WITH_AUTHORIZATION_SELECTOR[2:]:
            raise ValueError("not transferWithAuthorization")
        if signer.lower() != auth["from"]:
            raise ValueError("FiatTokenV2: invalid signature")
        if auth["nonce"] in self.used:
            raise ValueError("FiatTokenV2: authorization is used or canceled")
        if auth["value"] > self.balance:
            raise ValueError("ERC20: transfer amount exceeds balance")
        return auth

    def __call__(self, method: str, params: list):
        if method == "eth_chainId":
            return hex(8453)
        if method == "eth_blockNumber":
            return hex(self.head)
        if method == "eth_getBlockByNumber":
            return {"baseFeePerGas": hex(5_000_000), "timestamp": hex(1_791_100_000), "number": hex(self.head)}
        if method == "eth_getTransactionCount":
            return hex(self.nonces.get(params[0].lower(), 0))
        if method == "eth_estimateGas":
            self._authorization(bytes.fromhex(params[0]["data"][2:]))
            return hex(60_000)
        if method == "eth_sendRawTransaction":
            raw = HexBytes(params[0])
            tx = TypedTransaction.from_bytes(raw).as_dict()
            sender = Account.recover_transaction(raw).lower()
            assert "0x" + bytes(tx["to"]).hex() == USDC and tx["chainId"] == 8453
            assert tx["nonce"] == self.nonces.get(sender, 0), "account nonce reused or skipped"
            auth = self._authorization(bytes(tx["data"]))
            self.nonces[sender] = tx["nonce"] + 1
            self.used.add(auth["nonce"])
            self.balance -= auth["value"]
            self.paid.append(auth)
            tx_hash = "0x" + keccak(bytes(raw)).hex()
            self.head += 2
            self.receipts[tx_hash] = {"status": "0x1", "blockNumber": hex(self.head - 1), "logs": [
                {"address": USDC, "topics": [AUTH_USED, _pad(auth["from"]), auth["nonce"]], "data": "0x"},
                {"address": USDC, "topics": [TRANSFER, _pad(auth["from"]), _pad(auth["to"])],
                 "data": hex(auth["value"])}]}
            return tx_hash
        if method == "eth_getTransactionReceipt":
            return self.receipts.get(params[0])
        raise AssertionError(method)

    def json_rpc(self, body: dict) -> dict:
        try:
            return {"jsonrpc": "2.0", "id": 1, "result": self(body["method"], body["params"])}
        except ValueError as exc:
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": str(exc)}}


def _attested_seller_hub(tmp_path, payout=ATTESTED_WALLET):
    root = tmp_path / "attested"
    root.mkdir()
    config = HubConfig()
    config.hub_url = ATTESTED
    config.db_path = str(root / "hub.db")
    config.signing_key_path = str(root / "key")
    db = HubDatabase(root / "hub.db")
    answers = {"claim.check@v1": {"status": "contested", "confidence": 0.6},
               "contradiction.scan@v1": {"contradictions": [], "method": "lexical-negation-v1"}}
    for product, cap in (("claim-check", "claim.check@v1"), ("contradiction-scan", "contradiction.scan@v1")):
        db.upsert_capability(Capability(
            capability_id=cap, product_id=product, name=cap, description="Attested check",
            price_per_call_usd=PRICES[cap], source_hub="local", invoke_url="",
            prompt_template=json.dumps(answers[cap]), payout_address=payout, publisher_id="truth-layer"))
    client = TestClient(create_app(config=config, db=db, signer=Signer(root / "key")), base_url=ATTESTED)
    client.__enter__()
    return client


@pytest.fixture()
def world(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_ORACLE_FAMILY_URL", "off")
    monkeypatch.setenv("AIMARKET_CREDITS_FREE_GRANT_USD", "0")
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_SETTLE_MIN_CONFIRMATIONS", "1")
    chain = FakeBase()

    class _RpcResp:
        def __init__(self, body):
            self._body = body

        def raise_for_status(self):
            return None

        def json(self):
            return self._body

    import aimarket_hub.settle as settle_mod

    monkeypatch.setattr(settle_mod.httpx, "post", lambda url, json=None, timeout=None, **_: _RpcResp(chain.json_rpc(json)))
    monkeypatch.setattr(settle_mod, "rpc_urls", lambda *a: [RPC])
    attested = _attested_seller_hub(tmp_path)
    wallet = Account.create()
    key_file = tmp_path / "wallet.json"
    key_file.write_text(json.dumps({"private_key": wallet.key.hex()}))
    env = {"AIMARKET_SUPPLY_REQUIRE_RESPONSE_SIG": "1",
           "AIMARKET_SUPPLY_OPERATOR_PUBLISHERS": "independent-claim-audit",
           "AIMARKET_ALLOW_LOCAL_PUBLISH": "1", "AIMARKET_SUPPLY_CHAIN_ADMISSION_MODE": "off"}
    with hub(monkeypatch, tmp_path, **env) as (client, db):
        import aimarket_hub.outbound_http as outbound

        def transport(method, url, headers, body, timeout):
            if url.startswith(RPC):
                return 200, {}, json.dumps(chain.json_rpc(json.loads(body))).encode()
            target = attested if url.startswith(ATTESTED) else client
            r = target.request(method, url.replace(ATTESTED, "") if target is attested else url,
                               headers=dict(headers), content=body)
            return r.status_code, dict(r.headers), r.content

        cfg = audit_server.Config(hub_url=HUB, key_path=tmp_path / "audit" / "provider_key",
                                  state_path=tmp_path / "audit" / "daily_spend.json",
                                  child_source_hub=ATTESTED, wallet_key_path=key_file, rpc_urls=(RPC,),
                                  child_payees=(ATTESTED_WALLET,), daily_cap_usd=0.10)
        auditor = audit_server.Auditor(cfg, transport=transport)
        auditor.wallet.sleep = lambda s: None

        async def safe_post(url, *, json=None, headers=None, timeout=30.0, invoke=False, oracle_paid=False):
            assert url == AUDIT_URL, f"the hub may only call the provider here, not {url}"
            raw = __import__("json").dumps(json or {}).encode()
            status, out_headers, out = await asyncio.to_thread(
                auditor.handle, {k: v for k, v in (headers or {}).items() if v}, raw)
            return _Resp(status, out_headers, out)

        monkeypatch.setattr(outbound, "safe_post", safe_post)
        manifest = json.loads((EXAMPLE_DIR / "capability-direct.json").read_text(encoding="utf-8"))
        manifest.update(invoke_url=AUDIT_URL, provider_pubkey=auditor.pubkey_b64)
        r = client.post("/ai-market/v2/supply/register", json=manifest,
                        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
        assert r.status_code == 200, r.text
        try:
            yield client, db, attested, chain, auditor, wallet
        finally:
            attested.__exit__(None, None, None)


def _audit(client, api_key):
    return client.post("/ai-market/v2/invoke", headers={"X-API-Key": api_key}, json={
        "product_id": "independent-claim-audit", "capability_id": "claim.audit.direct@v1",
        "input": {"claim": "The vault holds 3 BTC",
                  "evidence": [{"source_uri": "https://a.example", "excerpt_hash": "sha256:" + "a" * 64,
                                "stance": "supports", "quality": 0.8}],
                  "statements": ["The vault holds 3 BTC", "The audit found 3 BTC"]}})


def test_independent_pays_attested_per_call_in_usdc_with_no_account_there(world):
    client, db, attested, chain, auditor, wallet = world
    buyer, key = funded_account(client, db, 1.0)
    r = _audit(client, key)
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert result["funding"] == "usdc-per-call" and result["verdict"] == "contested"
    payments = {c["capability_id"]: c["payment"] for c in result["children"]}
    assert payments["claim.check@v1"]["amount_usd"] == pytest.approx(0.022)
    assert payments["contradiction.scan@v1"]["amount_usd"] == pytest.approx(0.009)
    assert {p["pay_to"] for p in payments.values()} == {ATTESTED_WALLET}
    assert all(c["receipt_nonce"] for c in result["children"])      # Attested's signed receipts
    # On chain: two authorizations from the provider's wallet, exactly the prices, to Attested,
    # on two different account nonces (the children run in parallel).
    assert sorted(a["value"] for a in chain.paid) == [9_000, 22_000]
    assert {a["from"] for a in chain.paid} == {wallet.address.lower()}
    assert chain.nonces[wallet.address.lower()] == 2
    # Attested's hub settled both itself, from the chain; Independent holds no account there.
    x402 = attested.get("/ai-market/v2/stats/live").json()["summary"]["x402"]
    assert x402["x402_settled_usd"] == pytest.approx(0.031)
    assert balance(db, buyer) == pytest.approx(1.0 - 0.05)
    assert auditor.cap.used_micro() == 31_000


def test_a_402_naming_another_payee_is_paid_nothing(world, monkeypatch):
    client, db, attested, chain, auditor, wallet = world
    monkeypatch.setattr(auditor.cfg, "child_payees", ("0x" + "11" * 20,))
    _, key = funded_account(client, db, 1.0)
    r = _audit(client, key)
    assert r.status_code == 502 and chain.paid == []
    assert auditor.cap.used_micro() == 0


def test_a_price_above_the_ceiling_is_paid_nothing(world, monkeypatch):
    client, db, attested, chain, auditor, wallet = world
    monkeypatch.setattr(auditor.cfg, "child_max_price_usd", 0.01)    # the $0.022 check exceeds it
    _, key = funded_account(client, db, 1.0)
    r = _audit(client, key)
    assert r.status_code == 502
    assert [a["value"] for a in chain.paid] == [9_000]               # only the check within the ceiling


def test_an_empty_wallet_sends_nothing(world):
    client, db, attested, chain, auditor, wallet = world
    chain.balance = 5_000
    _, key = funded_account(client, db, 1.0)
    assert _audit(client, key).status_code == 502
    assert chain.paid == [] and chain.nonces == {}


def test_without_a_wallet_the_direct_audit_says_so(tmp_path):
    cfg = audit_server.Config(hub_url=HUB, key_path=tmp_path / "k", state_path=tmp_path / "s.json")
    auditor = audit_server.Auditor(cfg, transport=lambda *a: (500, {}, b"{}"))
    status, _, body = auditor.handle({}, json.dumps({"capability_id": "claim.audit.direct@v1"}).encode())
    assert status == 503 and json.loads(body)["error"] == "wallet_not_configured"


def test_the_daily_cap_counts_and_gives_back(tmp_path):
    """DailyCap read `datetime` without importing it: the first fixed-price call raised NameError."""
    cap = audit_server.DailyCap(tmp_path / "spend.json", 0.05)
    reservation = cap.reserve(30_000)
    assert reservation is not None and cap.reserve(30_000) is None
    cap.settle(reservation, 10_000)
    assert cap.used_micro() == 10_000
