"""Scratch repro: a dust authorization over the SAME top-up nonce, placed ahead of the buyer's
in one transaction, is what topup.redeem credits; the buyer's payment is never credited.

Only the chain RPC is stubbed; settle.verify_transfer, topup.redeem, the credits ledger and the
x402 ledger are the hub's own code on a real SQLite database with all migrations.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/Users/alex/Desktop/ai_tests/aicompany/aicom/.claude/worktrees/bold-volhard-8c154f/aimarket-hub")

from aimarket_hub import credits, settle, topup  # noqa: E402
from aimarket_hub.database import HubDatabase  # noqa: E402

PAY_TO = "0x" + "a1" * 20
BUYER = "0x" + "b2" * 20
ATTACKER = "0x" + "c3" * 20
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def pad(addr: str) -> str:
    return "0x" + addr[2:].rjust(64, "0")


def test_dust_authorization_over_same_nonce_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_TOPUP_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "0")
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://stub.invalid")
    topup._VERIFY_LOG.clear()

    db = HubDatabase(str(tmp_path / "hub.db"))
    ledger = credits.CreditsLedger(db._conn)
    store = topup.TopupStore(db._conn)
    payments = settle.PaymentStore(db._conn)
    acct = ledger.create_account(label="buyer")
    q, _body, _v2 = topup.quote(store=store, account_id=acct["account_id"], amount_usd=5, hub_url="https://hub.test")
    assert q.amount_units == 5_000_000

    tx_hash = "0x" + "ee" * 32
    logs = [
        # attacker: own EIP-3009 authorization over the buyer's quote nonce, 10 base units
        {"address": USDC, "topics": [settle.AUTHORIZATION_USED_TOPIC, pad(ATTACKER), q.nonce], "data": "0x"},
        {"address": USDC, "topics": [settle.TRANSFER_TOPIC, pad(ATTACKER), pad(PAY_TO)], "data": hex(10)},
        # buyer: the real 5 USDC authorization over the same nonce
        {"address": USDC, "topics": [settle.AUTHORIZATION_USED_TOPIC, pad(BUYER), q.nonce], "data": "0x"},
        {"address": USDC, "topics": [settle.TRANSFER_TOPIC, pad(BUYER), pad(PAY_TO)], "data": hex(5_000_000)},
    ]
    receipt = {"status": "0x1", "blockNumber": "0x10", "logs": logs}

    def fake_rpc(url, method, params, timeout):
        return {"eth_chainId": hex(8453), "eth_getTransactionReceipt": receipt,
                "eth_blockNumber": "0x20"}[method]

    monkeypatch.setattr(settle, "_rpc", fake_rpc)

    out = topup.redeem(store=store, ledger=ledger, payments=payments, nonce=q.nonce, tx_hash=tx_hash,
                       claim_deposit=lambda **kw: {"ok": True})
    print("redeem answer:", out)
    after = store.get(q.nonce)
    print("quote:", after.status, "paid_units", after.paid_units, "credited_mc", after.credited_mc, "payer", after.payer)
    print("balance:", ledger.balance(acct["account_id"]))
    # The buyer moved 5_000_000 units to payTo in this tx; the hub credited the attacker's 10.
    assert after.status == topup.CREDITED
    assert after.paid_units == 10 and after.credited_mc == 1 and after.payer == ATTACKER
    assert ledger.balance(acct["account_id"]) == 0.00001
    # A second presentation of the same transaction is a replay: the 5 USDC can never be credited.
    again = topup.redeem(store=store, ledger=ledger, payments=payments, nonce=q.nonce, tx_hash=tx_hash,
                         claim_deposit=lambda **kw: {"ok": True})
    assert again["idempotent_replay"] is True and ledger.balance(acct["account_id"]) == 0.00001


def test_dust_in_separate_tx_redeemed_first_locks_out_buyer(monkeypatch, tmp_path):
    """No mempool needed: the nonce is public once the buyer's tx is mined; a 10-unit
    authorization over it in the attacker's own tx, redeemed first, closes the quote."""
    import pytest

    monkeypatch.setenv("AIMARKET_CREDITS_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_TOPUP_ENABLED", "1")
    monkeypatch.setenv("AIMARKET_X402_PAY_TO", PAY_TO)
    monkeypatch.setenv("AIMARKET_X402_CHAIN", "base")
    monkeypatch.setenv("AIMARKET_TOPUP_VERIFY_DECIMALS", "0")
    monkeypatch.setenv("AIMARKET_SETTLE_RPC_URL", "http://stub.invalid")
    topup._VERIFY_LOG.clear()
    db = HubDatabase(str(tmp_path / "hub.db"))
    ledger = credits.CreditsLedger(db._conn)
    store = topup.TopupStore(db._conn)
    payments = settle.PaymentStore(db._conn)
    acct = ledger.create_account(label="buyer")
    q, _b, _v = topup.quote(store=store, account_id=acct["account_id"], amount_usd=100, hub_url="https://hub.test")
    buyer_tx, attacker_tx = "0x" + "b1" * 32, "0x" + "a7" * 32
    receipts = {
        buyer_tx: {"status": "0x1", "blockNumber": "0x10", "logs": [
            {"address": USDC, "topics": [settle.AUTHORIZATION_USED_TOPIC, pad(BUYER), q.nonce], "data": "0x"},
            {"address": USDC, "topics": [settle.TRANSFER_TOPIC, pad(BUYER), pad(PAY_TO)], "data": hex(100_000_000)}]},
        attacker_tx: {"status": "0x1", "blockNumber": "0x11", "logs": [
            {"address": USDC, "topics": [settle.AUTHORIZATION_USED_TOPIC, pad(ATTACKER), q.nonce], "data": "0x"},
            {"address": USDC, "topics": [settle.TRANSFER_TOPIC, pad(ATTACKER), pad(PAY_TO)], "data": hex(10)}]},
    }

    def fake_rpc(url, method, params, timeout):
        if method == "eth_getTransactionReceipt":
            return receipts[params[0]]
        return {"eth_chainId": hex(8453), "eth_blockNumber": "0x20"}[method]

    monkeypatch.setattr(settle, "_rpc", fake_rpc)
    ok = lambda **kw: {"ok": True}  # noqa: E731
    first = topup.redeem(store=store, ledger=ledger, payments=payments, nonce=q.nonce, tx_hash=attacker_tx,
                         claim_deposit=ok, limit_key="ip:attacker")
    assert first["credited_usd"] == 0.00001
    with pytest.raises(topup.TopupError) as refused:
        topup.redeem(store=store, ledger=ledger, payments=payments, nonce=q.nonce, tx_hash=buyer_tx,
                     claim_deposit=ok, owner_account=acct["account_id"])
    print("buyer's 100 USDC redemption:", refused.value.status, refused.value.error)
    assert refused.value.error == "topup_already_credited"
    assert ledger.balance(acct["account_id"]) == 0.00001
