"""escrow-1 on main with default idempotency: case-variant receipt + duplicated secret header."""
from __future__ import annotations
import sys
sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")
import time, sqlite3
from fastapi.testclient import TestClient

from aimarket_hub import channels
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.escrow_bridge import chain, eip712, store
from aimarket_hub.hub_routes.invoke_parts import local_delivery
from aimarket_hub.models import Capability
from aimarket_hub.signing import Signer


def _sign(depositor, escrow_channel, hub_wallet, token, amount, receipt, escrow_contract):
    from eth_account import Account
    auth = eip712.DebitAuthorization(channel_id=escrow_channel, hub=hub_wallet, token=token,
                                     amount=amount, receipt_id=receipt, nonce=0,
                                     deadline=int(time.time()) + 3 * 3600)
    sig = Account._sign_hash(eip712.debit_digest(auth, chain_id=8453, verifying_contract=escrow_contract),
                             depositor.key).signature
    payment = auth.as_message()
    payment.update(channelId=escrow_channel, receiptId=receipt, signature="0x" + sig.hex())
    return payment


def test_case_variant_with_default_idempotency(monkeypatch, tmp_path):
    from eth_account import Account
    hub_wallet = "0x" + "cc" * 20
    escrow_contract = "0x" + "ee" * 20
    escrow_channel = "0x" + "11" * 32
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
    variants = ["0x" + "ab" * 32, "0x" + "AB" * 32, "0x" + "Ab" * 32]
    try:
        with TestClient(create_app(config=config, db=db, signer=Signer(config.signing_key_path))) as client:
            db.upsert_capability(Capability(capability_id="esc.cap@v1", product_id="prod-esc",
                                            name="E", price_per_call_usd=0.02, source_hub="local",
                                            prompt_template='{"answer": "escrow"}'))
            opened = client.post("/ai-market/v2/channel/open", json={
                "deposit_usd": 5, "chain": "base", "wallet": depositor.address,
                "escrow_channel_id": escrow_channel})
            assert opened.status_code == 200, opened.text
            ch = opened.json()["channel"]
            results = []
            for i, rc in enumerate(variants):
                body = {"product_id": "prod-esc", "capability_id": "esc.cap@v1", "source_hub": "local",
                        "input": {"query": "x"},
                        "payment_authorization": _sign(depositor, escrow_channel, hub_wallet, token,
                                                       20_000, rc, escrow_contract)}
                # Plain: same secret only -> middleware keys by lowercased receipt
                headers = [("X-Payment-Channel", ch["channel_id"]),
                           ("X-Payment-Channel-Secret", ch["channel_secret"])]
                if i > 0:
                    r_plain = client.post("/ai-market/v2/invoke", headers=headers, json=body)
                    print("variant", i, "plain:", r_plain.status_code, r_plain.text[:160])
                    # duplicated secret header: app reads the first, middleware the last
                    headers = headers + [("X-Payment-Channel-Secret", f"junk{i}")]
                r = client.post("/ai-market/v2/invoke", headers=headers, json=body)
                print("variant", i, "dup-header:", r.status_code, r.headers.get("x-aimarket-idempotency"), r.text[:160])
                results.append(r.status_code)
            bridge = store.AuthorizationStore(str(tmp_path / "bridge.db"))
            rows = bridge._conn.execute("SELECT receipt_id, amount_units, status FROM debit_authorizations").fetchall()
            for row in rows:
                print(dict(row))
            led = channels._ledger.get(ch["channel_id"])
            print("ledger:", led["balance_usd"], led["used_usd"], "executions:", len(executions))
            live = bridge.active_at(escrow_channel, 0)
            print("live claim units:", live.amount_units if live else None)
    finally:
        db.close()
