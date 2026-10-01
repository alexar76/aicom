"""Synthetic chain receipts and temporary ledgers; no real transfers."""
import asyncio
import time
from types import SimpleNamespace

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import HTTPException
from hexbytes import HexBytes

from web.backend.services.payment_claim import claim_message, verify_claim, canonical_tx_hash


@pytest.fixture
def pay(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "synthetic-test-secret-000000000000000")
    from web.backend.api import payment
    from web.backend.services.commerce import CommerceService
    monkeypatch.setattr(payment, "commerce", CommerceService(base_dir=str(tmp_path / "store")))
    monkeypatch.setattr(payment, "_pending_payments", {})
    monkeypatch.setattr(payment, "_confirm_locks", {})
    monkeypatch.setattr(payment, "PENDING_PAYMENTS_FILE", tmp_path / "pending.json")
    monkeypatch.setattr(payment, "payment_verify_stub_enabled", lambda: False)
    return payment


@pytest.mark.parametrize("wire_type", [str, HexBytes])
@pytest.mark.parametrize("amount,expected", [(5_000_000, True), (1, False)])
def test_erc20_real_rpc_receipt(pay, monkeypatch, wire_type, amount, expected):
    recipient, payer = "0x" + "12" * 20, "0x" + "34" * 20
    log = {"address": pay.TOKEN_ADDRESSES["base"]["USDC"],
        "topics": [HexBytes(pay.TRANSFER_EVENT_SIG), HexBytes("0x" + "00" * 12 + payer[2:]),
                   HexBytes("0x" + "00" * 12 + recipient[2:])],
        "data": wire_type("0x" + amount.to_bytes(32, "big").hex())}
    pool = SimpleNamespace(run=lambda f: ({"from": payer}, {"status": 1, "blockNumber": 100, "logs": [log]}, 200))
    monkeypatch.setattr(pay, "_pool_for_chain", lambda c: pool)
    assert pay._verify_evm_transaction("base", "0x" + "ab" * 32, recipient, 5, "USDC")["verified"] is expected


@pytest.mark.parametrize("status,verified", [
    ({"confirmationStatus": "finalized", "confirmations": None, "err": None}, True),
    ({"confirmationStatus": "processed", "confirmations": 0, "err": None}, False),
    ({"confirmationStatus": "finalized", "confirmations": None, "err": {"failure": 1}}, False),
    ({}, False),
])
def test_solana_uses_signature_status_and_token_payer(pay, monkeypatch, status, verified):
    recipient, payer = "Recipient", "Payer"
    mint = pay.SOLANA_USDC_MINT
    def balance(owner, amount):
        return {"owner": owner, "mint": mint, "uiTokenAmount": {"uiAmount": amount}}
    tx = {"slot": 100, "meta": {"err": None,
        "preTokenBalances": [balance(payer, 10)],
        "postTokenBalances": [balance(payer, 5), balance(recipient, 5)]},
        "transaction": {"message": {"accountKeys": [
            {"pubkey": "FeeSponsor", "signer": True}, {"pubkey": payer, "signer": True}]}}}
    calls = []
    def call(method, params):
        calls.append(method)
        return tx if method == "getTransaction" else {"value": [status]}
    monkeypatch.setattr(pay, "_pool_for_chain", lambda c: SimpleNamespace(call=call))
    result = pay._verify_solana_transaction("A" * 88, recipient, 5, "USDC")
    assert result["verified"] is verified
    assert calls == ["getTransaction", "getSignatureStatuses"]
    if verified:
        assert result["from"] == payer


def test_solana_native_binds_to_debited_signed_account(pay, monkeypatch):
    recipient, payer, sponsor = "Recipient", "Payer", "Sponsor"
    tx = {"slot": 100, "meta": {"err": None,
        "preBalances": [1_000_000_000, 10_000_000_000, 0],
        "postBalances": [999_900_000, 4_999_900_000, 5_000_000_000],
        "preTokenBalances": [], "postTokenBalances": []},
        "transaction": {"message": {"accountKeys": [
            {"pubkey": sponsor, "signer": True}, {"pubkey": payer, "signer": True},
            {"pubkey": recipient, "signer": False}]}}}
    def call(method, params):
        return tx if method == "getTransaction" else {"value": [{"confirmationStatus": "finalized", "err": None}]}
    monkeypatch.setattr(pay, "_pool_for_chain", lambda c: SimpleNamespace(call=call))
    result = pay._verify_solana_transaction("A" * 88, recipient, 4.99, "SOL")
    assert result["verified"] and result["from"] == payer


def test_evm_case_alias_rejected_even_by_database(pay):
    import sqlite3
    from web.backend.services.commerce import TxHashAlreadyUsedError
    svc = pay.commerce
    customer = svc.register_customer("buyer@example.test", "synthetic-password")
    args = dict(customer_id=customer["id"], customer_email=customer["email"],
        product_id="prod-12345678", amount=5, currency="USDC")
    tx = "0x" + "ab" * 32
    svc.create_order_and_license(payment_id="pay-a", tx_hash=tx, **args)
    with pytest.raises(TxHashAlreadyUsedError):
        svc.create_order_and_license(payment_id="pay-b", tx_hash=tx.upper(), **args)
    # Exercise the database constraint independent of the Python precheck.
    with pytest.raises(sqlite3.IntegrityError):
        svc.conn.execute("""INSERT INTO orders SELECT 'new-order', customer_id, customer_email,
            'new-payment', product_id, amount, currency, upper(tx_hash), status, 'new-license',
            created_at, referral_source FROM orders LIMIT 1""")
    svc.conn.rollback()
    assert svc.conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
    assert canonical_tx_hash("Aa" * 40) == "Aa" * 40


@pytest.mark.parametrize("signer_kind,expected", [("payer", 200), ("attacker", 403), ("missing", 400)])
def test_checkout_requires_actual_payer_signature(pay, monkeypatch, signer_kind, expected):
    from web.backend.schemas.api_requests import ConfirmPaymentRequest
    import web.backend.services.uni_bridge as bridge
    buyer = pay.commerce.register_customer("buyer@example.test", "synthetic-password")
    payer, attacker = Account.create(), Account.create()
    tx = "0x" + "ab" * 32
    payment = {"payment_id": "pay-audit", "product_id": "prod-12345678", "amount": 5.0,
        "currency": "USDC", "chain": "base", "status": "pending", "customer_id": buyer["id"],
        "customer_email": buyer["email"], "wallet_address": "0x" + "12" * 20,
        "created_at": time.time(), "expires_at": time.time() + 3600}
    pay._pending_payments["pay-audit"] = payment
    monkeypatch.setattr(pay, "_catalog_checkout_usdt", lambda p: 5.0)
    monkeypatch.setattr(pay, "_verify_evm_transaction", lambda **kw: {
        "verified": True, "confirmations": 100, "from": payer.address, "block_number": 100})
    monkeypatch.setattr(bridge, "credit_payment_confirm", lambda **kw: None)
    wallet = payer if signer_kind == "payer" else attacker
    sig = wallet.sign_message(encode_defunct(text=claim_message(payment, tx))).signature.hex()
    if signer_kind == "missing":
        sig = ""
    async def run():
        return await pay.confirm_payment("pay-audit", ConfirmPaymentRequest(tx_hash=tx, payer_signature=sig),
            customer={"sub": buyer["id"], "email": buyer["email"]}, test_confirmations=None)
    if expected == 200:
        assert asyncio.run(run())["status"] == "confirmed"
        assert pay.commerce.get_order_by_tx_hash(tx)["customer_id"] == buyer["id"]
    else:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(run())
        assert exc.value.status_code == expected
        assert pay.commerce.get_order_by_tx_hash(tx) is None


def test_proof_cannot_move_to_another_checkout():
    payer = Account.create()
    payment = dict(payment_id="pay-1", customer_id="buyer-1", product_id="prod-1",
        chain="base", currency="USDC", amount=5.0, wallet_address="0x" + "12" * 20)
    tx = "0x" + "ab" * 32
    signature = payer.sign_message(encode_defunct(text=claim_message(payment, tx))).signature.hex()
    assert verify_claim(payment, tx, signature, payer.address)
    for key, value in {"customer_id": "buyer-2", "payment_id": "pay-2", "amount": 6.0,
                       "wallet_address": "0x" + "34" * 20}.items():
        assert not verify_claim({**payment, key: value}, tx, signature, payer.address)
    assert not verify_claim(payment, "0x" + "cd" * 32, signature, payer.address)
