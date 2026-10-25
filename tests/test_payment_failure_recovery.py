"""Failure injection at real checkout/store boundaries; no external transfers."""
from __future__ import annotations

import json
import sqlite3
import time
from types import SimpleNamespace

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_payment_chain_recovery import isolated

pytestmark = pytest.mark.component_integration
TX = "0x" + "ab" * 32


@pytest.fixture
def checkout_http(isolated, monkeypatch):
    from web.backend.api import payment as p
    from web.backend.services import customer_auth
    from web.backend.services.commerce import CommerceService
    from web.backend.services.payment_claim import claim_message

    store = CommerceService(base_dir=str(isolated / "checkout"))
    monkeypatch.setattr(p, "commerce", store)
    monkeypatch.setattr(customer_auth, "_commerce", store)
    monkeypatch.setattr(p, "_pending_payments", {})
    monkeypatch.setattr(p, "_confirm_locks", {})
    monkeypatch.setattr(p, "PENDING_PAYMENTS_FILE", isolated / "pending.json")
    monkeypatch.setattr(p, "payment_verify_stub_enabled", lambda: False)
    buyer = store.register_customer("recovery@example.test", "synthetic-password")
    payer = Account.create()
    quote = {"payment_id": "pay-failure", "product_id": "prod-12345678", "amount": 5.0,
                 "currency": "USDC", "chain": "base", "status": "pending", "customer_id": buyer["id"],
                 "customer_email": buyer["email"], "wallet_address": "0x" + "12" * 20,
                 "created_at": time.time(), "expires_at": time.time() + 3600,
                 "site": "https://checkout.example.test", "quote_version": 1}
    quote["quote_seal"] = p._quote_seal(quote)
    p._pending_payments[quote["payment_id"]] = quote
    p._persist_pending_payments()
    signature = payer.sign_message(encode_defunct(text=claim_message(quote, TX))).signature.hex()
    real_verifier = p._verify_evm_transaction
    def verifier(**_):
        return dict(verified=True, confirmations=100, **{"from": payer.address}, block_number=100)
    monkeypatch.setattr(p, "_verify_evm_transaction", verifier)
    app = FastAPI()
    app.include_router(p.router)
    token = store.create_token(buyer["id"], buyer["email"])
    with TestClient(app, raise_server_exceptions=False) as client:
        def confirm(tx_hash=TX, headers=None):
            return client.post(f"/api/payment/confirm/{quote['payment_id']}",
                               headers=headers if headers is not None else {"Authorization": f"Bearer {token}"},
                               json={"tx_hash": tx_hash, "payer_signature": signature})

        yield SimpleNamespace(p=p, store=store, buyer=buyer, quote=quote, confirm=confirm,
                              verifier=verifier, real_verifier=real_verifier, root=isolated,
                              client=client, headers={"Authorization": f"Bearer {token}"})
    store.conn.close()


def assert_one_license(env, response):
    assert response.status_code == 200, response.text
    order = env.store.get_order_by_tx_hash(TX)
    assert response.json()["order_id"] == order["id"]
    assert response.json()["license_key"] == order["license_key"]
    assert env.store.conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
    assert env.store.conn.execute("SELECT count(*) FROM licenses").fetchone()[0] == 1


@pytest.mark.parametrize("after_commit", [False, True])
def test_ambiguous_order_failure_keeps_claim_and_recovers_once(checkout_http, monkeypatch, after_commit):
    from web.backend.services.ai_market_protocol.channels import claim_transfer

    env = checkout_http
    create = env.store.create_order_and_license

    def fail(**kwargs):
        if after_commit:
            create(**kwargs)
        raise OSError("synthetic private storage path /secrets/database")

    monkeypatch.setattr(env.store, "create_order_and_license", fail)
    first = env.confirm()
    assert first.status_code == 503, first.text
    assert "/secrets/" not in first.text
    assert env.p._pending_payments[env.quote["payment_id"]]["status"] != "confirmed"
    competing = claim_transfer(chain="base", tx_hash=TX, door="web-uni-topup", claim_id="other-topup")
    assert competing["ok"] is False
    monkeypatch.setattr(env.store, "create_order_and_license", create)
    env.p._pending_payments = {}
    env.p._confirm_locks = {}
    env.p._load_pending_payments_from_disk()
    assert_one_license(env, env.confirm())


@pytest.mark.parametrize("failure_at", ["checkpoint", "cleanup"])
def test_pending_write_failure_preserves_immediate_retry(checkout_http, monkeypatch, failure_at):
    env = checkout_http
    write = env.p.write_json_atomic

    def disk_full(*args, **kwargs):
        if failure_at == "checkpoint" or not args[1]:
            raise OSError("synthetic disk full /private/checkout")
        return write(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(env.p, "write_json_atomic", disk_full)
        first = env.confirm()
        assert first.status_code == 503, first.text
        assert "/private/" not in first.text
        assert env.quote["payment_id"] in env.p._pending_payments
        assert (env.store.get_order_by_tx_hash(TX) is not None) == (failure_at == "cleanup")
    assert env.p.write_json_atomic is write
    assert_one_license(env, env.confirm())


@pytest.mark.parametrize("damage", ["missing", "truncated"])
def test_unavailable_quote_key_is_not_replaced_and_backup_recovers(checkout_http, damage):
    env = checkout_http
    path = env.root / "checkout_quote.key"
    backup = path.read_bytes()
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(b"truncated")
    first = env.confirm()
    assert first.status_code == 503, first.text
    assert not path.exists() if damage == "missing" else path.read_bytes() == b"truncated"
    assert env.store.get_order_by_tx_hash(TX) is None
    path.write_bytes(backup)
    assert_one_license(env, env.confirm())


def test_legacy_confirmed_without_order_cannot_claim_success(checkout_http):
    env = checkout_http
    env.quote["status"] = "confirmed"
    env.p._persist_pending_payments()
    assert_one_license(env, env.confirm())


@pytest.mark.parametrize("error", [sqlite3.OperationalError, sqlite3.IntegrityError])
def test_database_error_between_order_and_license_rolls_back(checkout_http, monkeypatch, error):
    env = checkout_http
    execute = env.store.conn.execute

    def fail_license(sql, *args, **kwargs):
        if "INSERT INTO licenses" in sql:
            raise error("synthetic write failure")
        return execute(sql, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(env.store.conn, "execute", fail_license)
        first = env.confirm()
        assert first.status_code == 503, first.text
        assert execute("SELECT count(*) FROM orders").fetchone()[0] == 0
        assert execute("SELECT count(*) FROM licenses").fetchone()[0] == 0
        # Another request's commit must not publish a half-order.
        env.store.conn.commit()
    assert_one_license(env, env.confirm())


def test_rpc_outage_is_retryable_without_marking_transfer_failed(checkout_http, monkeypatch, caplog):
    env = checkout_http

    class OfflinePool:
        def run(self, _operation):
            raise env.p.chain_net.AllEndpointsDown("https://rpc.example.test/private-api-key")

    with monkeypatch.context() as patch:
        patch.setattr(env.p, "_verify_evm_transaction", env.real_verifier)
        patch.setattr(env.p, "_pool_for_chain", lambda _: OfflinePool())
        first = env.confirm()
        assert first.status_code == 503, first.text
        assert "private-api-key" not in first.text
        assert "private-api-key" not in caplog.text
        assert env.quote["status"] == "pending"
        assert json.loads(env.p.PENDING_PAYMENTS_FILE.read_text())[env.quote["payment_id"]]["status"] == "pending"
        assert env.store.get_order_by_tx_hash(TX) is None
    assert_one_license(env, env.confirm())


@pytest.mark.parametrize("failure", [TimeoutError("private RPC token"), ValueError("private RPC token"), None])
def test_unexpected_rpc_error_does_not_disclose_or_consume_payment(checkout_http, monkeypatch, failure, caplog):
    env = checkout_http

    def broken(**_):
        if failure is not None:
            raise failure
        return None

    with monkeypatch.context() as patch:
        patch.setattr(env.p, "_verify_evm_transaction", broken)
        first = env.confirm()
        assert first.status_code == 503, first.text
        assert "private RPC token" not in first.text
        assert "private RPC token" not in caplog.text
        assert env.quote["status"] == "pending"
        assert env.store.get_order_by_tx_hash(TX) is None
    assert_one_license(env, env.confirm())


def test_claim_store_outage_does_not_deliver_and_retry_recovers(checkout_http, monkeypatch):
    env = checkout_http

    def unavailable(**_):
        raise OSError("private claim store path")

    with monkeypatch.context() as patch:
        patch.setattr(env.p, "claim_transfer", unavailable)
        first = env.confirm()
        assert first.status_code == 503, first.text
        assert "private claim store" not in first.text
        assert env.quote["status"] == "pending"
        assert env.store.get_order_by_tx_hash(TX) is None
    assert_one_license(env, env.confirm())


@pytest.mark.parametrize("field,value", [
    ("product_id", "prod-other"), ("amount", 0.01), ("currency", "USDT"),
    ("wallet_address", "0x" + "34" * 20), ("created_at", 1),
    ("expires_at", 9999999999), ("site", "https://attacker.example.test"),
])
def test_mutating_sealed_terms_cannot_deliver(checkout_http, field, value):
    env = checkout_http
    env.quote[field] = value
    assert env.confirm().status_code == 400
    assert env.store.get_order_by_tx_hash(TX) is None


@pytest.mark.parametrize("reason,status", [
    ("disabled", 503), ("anonymous", 401), ("foreign-customer", 403),
    ("missing-quote", 404), ("empty-hash", 422), ("invalid-hash", 422),
])
def test_unauthorized_or_invalid_request_never_delivers(checkout_http, monkeypatch, reason, status):
    env = checkout_http
    headers, tx = None, TX
    if reason == "disabled":
        monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "0")
    elif reason == "anonymous":
        headers = {}
    elif reason == "foreign-customer":
        token = env.store.create_token("other-customer", "other@example.test")
        headers = {"Authorization": f"Bearer {token}"}
    elif reason == "missing-quote":
        env.p._pending_payments.clear()
    else:
        tx = " " if reason == "empty-hash" else "invalid"
    assert env.confirm(tx_hash=tx, headers=headers).status_code == status
    assert env.store.get_order_by_tx_hash(TX) is None


@pytest.mark.parametrize("status", ["pending", "pending_confirmation"])
def test_retry_cannot_replace_an_already_pinned_transfer(checkout_http, status):
    env = checkout_http
    env.quote.update(status=status, tx_hash="0x" + "cd" * 32)
    assert env.confirm().status_code == 400
    assert env.store.get_order_by_tx_hash(TX) is None


def test_invalid_receipt_is_a_rejection_without_a_license(checkout_http, monkeypatch):
    env = checkout_http
    monkeypatch.setattr(env.p, "_verify_evm_transaction", lambda **_: {"verified": False, "error": "receipt failed"})
    response = env.confirm()
    assert response.status_code == 400
    assert env.quote["status"] == "failed"
    assert env.store.get_order_by_tx_hash(TX) is None


@pytest.mark.parametrize("body", ["", "[]", "null", "invalid"])
def test_damaged_legacy_claim_history_fails_closed_and_recovers(checkout_http, body):
    from web.backend.services.ai_market_protocol.channels import payment_tx_path

    env = checkout_http
    path = payment_tx_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    assert env.confirm().status_code == 503
    assert env.store.get_order_by_tx_hash(TX) is None
    path.write_text("{}")
    assert_one_license(env, env.confirm())


@pytest.mark.parametrize("body", ["", "[]", "null", "invalid", '{"quote": null}'])
def test_corrupt_pending_history_is_preserved_until_restored(checkout_http, body):
    env = checkout_http
    path = env.p.PENDING_PAYMENTS_FILE
    backup = path.read_bytes()
    path.write_text(body)
    assert env.confirm().status_code == 503
    assert path.read_text() == body
    assert env.store.get_order_by_tx_hash(TX) is None
    path.write_bytes(backup)
    assert_one_license(env, env.confirm())


def test_unavailable_legacy_uni_history_cannot_be_assumed_unspent(checkout_http, monkeypatch):
    from core.uni import receipts

    env = checkout_http

    def unavailable(_):
        raise OSError("synthetic legacy ledger unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(receipts, "find_topup_receipt", unavailable)
        assert env.confirm().status_code == 503
        assert env.store.get_order_by_tx_hash(TX) is None
    assert_one_license(env, env.confirm())


def test_new_quote_cannot_replace_a_lost_key_for_existing_quotes(checkout_http):
    from fastapi import HTTPException

    env = checkout_http
    path = env.root / "checkout_quote.key"
    backup = path.read_bytes()
    path.unlink()
    with pytest.raises(HTTPException) as exc:
        env.p._quote_seal({**env.quote, "payment_id": "new-checkout"})
    assert exc.value.status_code == 503
    assert not path.exists()
    path.write_bytes(backup)
    assert_one_license(env, env.confirm())


def test_order_writer_is_idempotent_after_a_committed_response(checkout_http):
    env = checkout_http
    first = env.confirm()
    assert_one_license(env, first)
    quote = env.quote
    repeated = env.store.create_order_and_license(
        customer_id=env.buyer["id"], customer_email=env.buyer["email"],
        payment_id=quote["payment_id"], product_id=quote["product_id"],
        amount=quote["amount"], currency=quote["currency"], tx_hash=TX)
    assert repeated["id"] == first.json()["order_id"]
    assert repeated["license_key"] == first.json()["license_key"]
    assert env.store.conn.execute("SELECT count(*) FROM licenses").fetchone()[0] == 1


def test_database_constraint_catches_a_duplicate_missed_by_the_precheck(checkout_http, monkeypatch):
    from web.backend.services.commerce import TxHashAlreadyUsedError

    env = checkout_http
    assert_one_license(env, env.confirm())
    lookup = env.store.get_order_by_tx_hash
    calls = []

    def stale_read(tx_hash):
        calls.append(tx_hash)
        return None if len(calls) == 1 else lookup(tx_hash)

    monkeypatch.setattr(env.store, "get_order_by_tx_hash", stale_read)
    with pytest.raises(TxHashAlreadyUsedError):
        env.store.create_order_and_license(
            customer_id=env.buyer["id"], customer_email=env.buyer["email"], payment_id="competing-payment",
            product_id=env.quote["product_id"], amount=5, currency="USDC", tx_hash=TX.upper())
    assert len(calls) == 2
    assert env.store.conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 1
    assert env.store.conn.execute("SELECT count(*) FROM licenses").fetchone()[0] == 1


@pytest.mark.parametrize("amount", ["invalid", float("nan"), float("inf"), 0, -1])
def test_invalid_legacy_amount_cannot_deliver(checkout_http, amount):
    env = checkout_http
    env.quote.pop("quote_version")
    env.quote.pop("quote_seal")
    env.quote["amount"] = amount
    assert env.confirm().status_code == 400
    assert env.store.get_order_by_tx_hash(TX) is None


@pytest.mark.parametrize("fail_license", [False, True])
def test_non_chain_order_still_commits_or_rolls_back_as_a_unit(checkout_http, monkeypatch, fail_license):
    env = checkout_http
    execute = env.store.conn.execute

    def write(statement, *args, **kwargs):
        if fail_license and "INSERT INTO licenses" in statement:
            raise sqlite3.IntegrityError("synthetic license constraint")
        return execute(statement, *args, **kwargs)

    monkeypatch.setattr(env.store.conn, "execute", write)
    args = {"customer_id": env.buyer["id"], "customer_email": env.buyer["email"], "payment_id": "non-chain",
                "product_id": env.quote["product_id"], "amount": 0, "currency": "", "tx_hash": ""}
    if fail_license:
        with pytest.raises(sqlite3.IntegrityError):
            env.store.create_order_and_license(**args)
    else:
        assert env.store.create_order_and_license(**args)["license_key"]
    for table in ("orders", "licenses"):
        assert execute(f"SELECT count(*) FROM {table}").fetchone()[0] == (0 if fail_license else 1)


def test_solana_checkout_joins_rpc_proof_claim_and_license(checkout_http, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from tests.test_payment_claim_crypto import base58
    from web.backend.services.payment_claim import claim_message

    env = checkout_http
    key = Ed25519PrivateKey.generate()
    payer = base58(key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw))
    recipient = base58(b"\x12" * 32)
    env.quote.update(chain="solana", wallet_address=recipient)
    env.quote["quote_seal"] = env.p._quote_seal(env.quote)
    env.p._persist_pending_payments()
    tx_hash = "A" * 88
    signature = key.sign(claim_message(env.quote, tx_hash).encode()).hex()

    def balance(owner, amount):
        return {"owner": owner, "mint": env.p.SOLANA_USDC_MINT,
                "uiTokenAmount": {"amount": amount, "decimals": 6, "uiAmount": None}}

    tx = {"slot": 100, "meta": {"err": None,
          "preTokenBalances": [balance(payer, "10000000")],
          "postTokenBalances": [balance(payer, "5000000"), balance(recipient, "5000000")]},
          "transaction": {"message": {"accountKeys": [{"pubkey": payer, "signer": True}]}}}

    def call(method, _params):
        return tx if method == "getTransaction" else {"value": [{"confirmationStatus": "finalized", "err": None}]}

    monkeypatch.setattr(env.p, "_pool_for_chain", lambda _: SimpleNamespace(call=call))
    response = env.client.post(f"/api/payment/confirm/{env.quote['payment_id']}", headers=env.headers,
                               json={"tx_hash": tx_hash, "payer_signature": signature})
    assert response.status_code == 200, response.text
    order = env.store.get_order_by_tx_hash(tx_hash)
    assert response.json()["license_key"] == order["license_key"]
    assert order["customer_id"] == env.buyer["id"]
    assert env.store.conn.execute("SELECT count(*) FROM licenses").fetchone()[0] == 1
    competing = env.p.claim_transfer(chain="solana", tx_hash=tx_hash, door="web-uni-topup", claim_id="replay")
    assert competing["ok"] is False


@pytest.mark.parametrize("amount", [float("nan"), float("inf"), -5, "invalid"])
def test_solana_malformed_recipient_balance_never_verifies(monkeypatch, amount):
    from web.backend.api import payment as p

    def balance(owner, value):
        return {"owner": owner, "mint": p.SOLANA_USDC_MINT, "uiTokenAmount": {"uiAmount": value}}

    tx = {"slot": 100, "meta": {"err": None,
          "preTokenBalances": [balance("payer", 10)],
          "postTokenBalances": [balance("payer", 5), balance("recipient", amount)]},
          "transaction": {"message": {"accountKeys": [{"pubkey": "payer", "signer": True}]}}}

    def call(method, _params):
        return tx if method == "getTransaction" else {"value": [{"confirmationStatus": "finalized", "err": None}]}

    monkeypatch.setattr(p, "_pool_for_chain", lambda _: SimpleNamespace(call=call))
    assert p._verify_solana_transaction("A" * 88, "recipient", 5, "USDC")["verified"] is False


def test_solana_rpc_credentials_are_not_logged(monkeypatch, caplog):
    from web.backend.api import payment as p

    def unavailable(*_):
        raise TimeoutError("https://rpc.example.test/private-solana-api-key")

    monkeypatch.setattr(p, "_pool_for_chain", lambda _: SimpleNamespace(call=unavailable))
    result = p._verify_solana_transaction("A" * 88, "recipient", 5, "USDC")
    assert result["verified"] is False and result["unavailable"] is True
    assert "private-solana-api-key" not in caplog.text
    assert "private-solana-api-key" not in json.dumps(result)


@pytest.mark.parametrize("raw,decimals,verified", [
    ("5000000", 6, True), ("0", 6, False), ("NaN", 6, False),
    ("-5000000", 6, False), (str(2**64), 6, False),
    ("5000000", "6", False), ("5000000", True, False), ("5000000", -1, False),
])
def test_solana_uses_validated_raw_token_balances(monkeypatch, raw, decimals, verified):
    from web.backend.api import payment as p

    def balance(owner, amount, places=6):
        return {"owner": owner, "mint": p.SOLANA_USDC_MINT,
                "uiTokenAmount": {"amount": amount, "decimals": places, "uiAmount": None}}

    tx = {"slot": 100, "meta": {"err": None,
          "preTokenBalances": [balance("payer", "10000000")],
          "postTokenBalances": [balance("payer", "5000000"), balance("recipient", raw, decimals)]},
          "transaction": {"message": {"accountKeys": [{"pubkey": "payer", "signer": True}]}}}

    def call(method, _params):
        return tx if method == "getTransaction" else {"value": [{"confirmationStatus": "finalized", "err": None}]}

    monkeypatch.setattr(p, "_pool_for_chain", lambda _: SimpleNamespace(call=call))
    result = p._verify_solana_transaction("A" * 88, "recipient", 5, "USDC")
    assert result["verified"] is verified
    if verified:
        assert result["amount"] == 5 and result["from"] == "payer"
