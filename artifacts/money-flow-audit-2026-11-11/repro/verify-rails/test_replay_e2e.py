"""E2E: a delivered escrow call; the buyer replays its authorization with a wrong secret."""
from __future__ import annotations
import sys
sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")
import time
from contextlib import contextmanager
from fastapi.testclient import TestClient

from aimarket_hub import channels
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.escrow_bridge import chain, eip712, store
from aimarket_hub.hub_routes.invoke_parts import local_delivery
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer


def test_replay_with_wrong_secret_abandons_delivered_claim(monkeypatch, tmp_path):
    from eth_account import Account
    hub_wallet = "0x" + "cc" * 20
    escrow_contract = "0x" + "ee" * 20
    escrow_channel = "0x" + "11" * 32
    receipt = "0x" + "22" * 32
    token = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
    depositor = Account.from_key("0x" + "42" * 32)
    for k, v in {
        "AIFACTORY_CRYPTO_ENABLED": "1", "AIMARKET_ESCROW_BRIDGE_ENABLED": "1",
        "AIMARKET_ESCROW_BRIDGE_DB_PATH": str(tmp_path / "bridge.db"),
        "AIMARKET_VERIFY_SETTLEMENTS_DB_PATH": str(tmp_path / "hub.db"),
        "AIMARKET_ESCROW_CONTRACT": escrow_contract, "AIMARKET_ESCROW_HUB_ADDRESS": hub_wallet,
        "AIMARKET_ESCROW_COLLECT_INTERVAL_S": "0", "AIMARKET_ORACLE_FAMILY_URL": "off",
    }.items():
        monkeypatch.setenv(k, v)
    onchain = chain.EscrowChannel(
        channel_id=escrow_channel, depositor=depositor.address, hub=hub_wallet, token=token,
        deposit_amount=5_000_000, balance=5_000_000, used_amount=0,
        expires_at=int(time.time()) + 3600 * 5, nonce=0, status=0)
    monkeypatch.setattr(chain, "chain_id", lambda: 8453)
    monkeypatch.setattr(chain, "escrow_address", lambda: escrow_contract)
    monkeypatch.setattr(chain, "read_channel", lambda *a, **k: onchain)

    executions = []

    async def execute(d, call, local):
        executions.append(local.nonce)
        return {"answer": "escrow"}
    monkeypatch.setattr(local_delivery, "_local_execute", execute)

    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(config.db_path)
    monkeypatch.setattr(channels, "_ledger", channels.ChannelLedger(str(tmp_path / "channels.db")))

    auth = eip712.DebitAuthorization(channel_id=escrow_channel, hub=hub_wallet, token=token,
                                     amount=20_000, receipt_id=receipt, nonce=0,
                                     deadline=int(time.time()) + 3 * 3600)
    sig = Account._sign_hash(eip712.debit_digest(auth, chain_id=8453, verifying_contract=escrow_contract),
                             depositor.key).signature
    payment = auth.as_message()
    payment.update(channelId=escrow_channel, receiptId=receipt, signature="0x" + sig.hex())
    body = {"product_id": "prod-esc", "capability_id": "esc.cap@v1", "source_hub": "local",
            "input": {"query": "x"}, "payment_authorization": payment}
    try:
        with TestClient(create_app(config=config, db=db, signer=Signer(config.signing_key_path))) as client:
            db.upsert_capability(Capability(capability_id=body["capability_id"], product_id="prod-esc",
                                            name="E", price_per_call_usd=0.02, source_hub="local",
                                            prompt_template='{"answer": "escrow"}'))
            opened = client.post("/ai-market/v2/channel/open", json={
                "deposit_usd": 5, "chain": "base", "wallet": depositor.address,
                "escrow_channel_id": escrow_channel})
            assert opened.status_code == 200, opened.text
            ch = opened.json()["channel"]
            good = {"X-Payment-Channel": ch["channel_id"], "X-Payment-Channel-Secret": ch["channel_secret"]}
            r1 = client.post("/ai-market/v2/invoke", headers=good, json=body)
            print("first:", r1.status_code, r1.headers.get("x-aimarket-idempotency"))
            assert r1.status_code == 200, r1.text
            bridge = store.AuthorizationStore(str(tmp_path / "bridge.db"))
            print("after delivery:", bridge.get(receipt).status, "unresolved:", len(bridge.unresolved()))
            assert bridge.get(receipt).status == store.PENDING
            led = channels._ledger.get(ch["channel_id"])
            print("ledger after delivery:", led["balance_usd"], led["used_usd"])

            # Same request, same secret: idempotency answers it (safe)
            r2 = client.post("/ai-market/v2/invoke", headers=good, json=body)
            print("same-secret replay:", r2.status_code, r2.headers.get("x-aimarket-idempotency"))
            print("status:", bridge.get(receipt).status)

            # Same request, WRONG secret: bypasses idempotency, reaches verify_and_store
            bad = {"X-Payment-Channel": ch["channel_id"], "X-Payment-Channel-Secret": "wrong"}
            r3 = client.post("/ai-market/v2/invoke", headers=bad, json=body)
            print("wrong-secret replay:", r3.status_code, r3.text[:300])
            row = bridge.get(receipt)
            print("status after wrong-secret replay:", row.status, "|", row.last_error,
                  "| unresolved:", len(bridge.unresolved()), "| executions:", len(executions))
            assert row.status == store.ABANDONED
            assert bridge.unresolved() == []
    finally:
        db.close()

def test_where():
    import aimarket_hub
    print("PKG", aimarket_hub.__file__)
