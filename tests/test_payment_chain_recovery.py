"""Payment audit regressions: real state machines, temporary ledgers, synthetic chain evidence."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "independent/kova-gateway/backend"))


@pytest.fixture(params=["sqlite", "postgres"])
def isolated(tmp_path, monkeypatch, request):
    backend = request.param
    pg_url = os.environ.get("PAYMENT_FIX_TEST_PG_URL")
    if backend == "postgres" and not pg_url:
        pytest.skip("temporary PostgreSQL test cluster not configured")
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("AIMARKET_DEPOSIT_CLAIMS_DIR", str(tmp_path / "claims"))
    monkeypatch.setenv("UNI_DB_BACKEND", backend)
    monkeypatch.setenv("AIFACTORY_UNI_USE_COMMERCE_DB", "0")
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_UNI_TOPUP_SPREAD_BPS", "0")
    monkeypatch.setenv("AIFACTORY_CRYPTO_ENABLED", "1")
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "audit-local-synthetic-secret-000000000000000")
    import core.uni.store as store
    if store._sqlite_conn:
        store._sqlite_conn.close()
    store._sqlite_conn = None
    if store._pg_pool:
        store._pg_pool.close()
        store._pg_pool = None
    admin = None
    if backend == "postgres":
        import uuid

        import psycopg
        from psycopg import sql
        from psycopg.conninfo import make_conninfo
        schema = "payment_fix_" + uuid.uuid4().hex
        admin = psycopg.connect(pg_url, autocommit=True)
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        monkeypatch.setenv("UNI_DATABASE_URL", make_conninfo(pg_url, options=f"-c search_path={schema}"))
    yield tmp_path
    if store._sqlite_conn:
        store._sqlite_conn.close()
        store._sqlite_conn = None
    if store._pg_pool:
        store._pg_pool.close()
        store._pg_pool = None
    if admin:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        admin.close()


@pytest.fixture
def checkout(isolated, monkeypatch):
    from eth_account import Account
    from eth_account.messages import encode_defunct

    import web.backend.services.uni_bridge as bridge
    from core.uni.wallet import UniWalletService
    from web.backend.api import payment as p
    from web.backend.services.commerce import CommerceService
    from web.backend.services.payment_claim import claim_message
    monkeypatch.setattr(p, "commerce", CommerceService(base_dir=str(isolated / "orders")))
    monkeypatch.setattr(p, "_pending_payments", {})
    monkeypatch.setattr(p, "_confirm_locks", {})
    monkeypatch.setattr(p, "PENDING_PAYMENTS_FILE", isolated / "pending.json")
    monkeypatch.setattr(p, "payment_verify_stub_enabled", lambda: False)
    monkeypatch.setattr(p, "_catalog_checkout_usdt", lambda _: 5.0)
    monkeypatch.setattr(bridge, "_svc", UniWalletService())
    buyer = p.commerce.register_customer("audit@example.test", "synthetic-local-password")
    payer = Account.create()
    tx = "0x" + "ab" * 32
    quote = {"payment_id": "pay-audit", "product_id": "prod-12345678", "amount": 5.0,
                 "currency": "USDC", "chain": "base", "status": "pending", "customer_id": buyer["id"],
                 "customer_email": buyer["email"], "wallet_address": "0x" + "12" * 20,
                 "created_at": time.time(), "expires_at": time.time() + 3600}
    quote["quote_version"] = 1
    quote["quote_seal"] = p._quote_seal(quote)
    p._pending_payments[quote["payment_id"]] = quote
    p._persist_pending_payments()
    monkeypatch.setattr(p, "_verify_evm_transaction", lambda **_: dict(
        verified=True, confirmations=100, **{"from": payer.address}, block_number=100))
    signature = payer.sign_message(encode_defunct(text=claim_message(quote, tx))).signature.hex()
    def confirm():
        return asyncio.run(p._confirm_payment(quote["payment_id"], tx, signature,
                           {"sub": buyer["id"]}, None))
    return p, quote, buyer, confirm


def test_kova_refuses_transfer_older_than_invoice(isolated, monkeypatch):
    from kova.invoices import TRANSFER_TOPIC, InvoiceBook
    from kova.provider_pool import ProviderPool
    from kova.settings import load_settings
    from kova.store import Store
    monkeypatch.setenv("KOVA_DATA_DIR", str(isolated / "kova"))
    settings = load_settings()
    book = InvoiceBook(Store(str(isolated / "kova")), settings, ProviderPool(settings))
    payer, recipient = "0x" + "11" * 20, "0x" + "22" * 20
    monkeypatch.setattr(book.pool, "call", lambda *_: "0x64")
    inv = book.create("synthetic-api-key", {"payer": payer, "recipient": recipient,
                       "amount_usdc": "5.00", "expires_in_seconds": 3600})
    created = book._row(inv["invoice_id"])
    receipt = {"status": "0x1", "blockNumber": "0x1", "logs": [{"address": book.usdc_address,
        "topics": [TRANSFER_TOPIC, "0x" + payer[2:].rjust(64, "0"),
                "0x" + recipient[2:].rjust(64, "0")], "data": hex(5_000_000)}]}
    def rpc(method, params):
        if method == "eth_getTransactionReceipt":
            return receipt
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(created["created_unix"] - 86_400)}
        return "0x70"
    monkeypatch.setattr(book.pool, "call", rpc)
    with pytest.raises(ValueError, match="predates"):
        book.status(inv["invoice_id"], "0x" + "aa" * 32)
    assert book._row(inv["invoice_id"])["state"] == "pending"


def test_saas_old_transfer_refused_then_bound_payment_issues_one_key(isolated, monkeypatch):
    from fastapi.testclient import TestClient
    from kova.invoices import TRANSFER_TOPIC, InvoiceBook
    from kova.provider_pool import ProviderPool
    from kova.settings import load_settings
    from kova.store import Store
    monkeypatch.setenv("KOVA_DATA_DIR", str(isolated / "kova-e2e"))
    settings = load_settings()
    book = InvoiceBook(Store(settings.data_dir), settings, ProviderPool(settings))
    payer, recipient = "0x" + "11" * 20, "0x" + "22" * 20
    receipt = {"status": "0x1", "blockNumber": "0x1", "logs": [{"address": book.usdc_address,
        "topics": [TRANSFER_TOPIC, "0x" + payer[2:].rjust(64, "0"),
                "0x" + recipient[2:].rjust(64, "0")], "data": hex(12_000_000)}]}
    def rpc(method, params):
        if method == "eth_getTransactionReceipt":
            return receipt
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(int(time.time()) - 86_400)}
        return "0x64"
    monkeypatch.setattr(book.pool, "call", rpc)
    monkeypatch.syspath_prepend(str(ROOT / "attested/attested-saas-gateway/src"))
    monkeypatch.setenv("AIFACTORY_DEV", "1")
    monkeypatch.setenv("AIFACTORY_PROD", "0")
    monkeypatch.setenv("SAAS_GATEWAY_DATABASE_URL", f"sqlite:///{isolated / 'saas-e2e.db'}")
    monkeypatch.setenv("SAAS_PAYMENT_RECIPIENT", recipient)
    monkeypatch.setenv("KOVA_URL", "http://localhost:8789")
    import saas_gateway.app as gateway
    monkeypatch.setattr(gateway, "cfg", gateway.settings())
    monkeypatch.setattr(gateway, "db", gateway.Database(gateway.cfg.database_url))
    def kova_transport(method, path, **kwargs):
        if method == "POST":
            return book.create("synthetic-gateway-key", kwargs["json"],
                               idempotency_key=kwargs.get("headers", {}).get("Idempotency-Key", ""))
        try:
            return book.status(path.rsplit("/", 1)[-1], (kwargs.get("params") or {}).get("tx_hash"))
        except ValueError as exc:
            from fastapi import HTTPException
            raise HTTPException(422, str(exc)) from exc
    monkeypatch.setattr(gateway, "_kova", kova_transport)
    client = TestClient(gateway.app)  # No lifespan: no background network workers.
    original_insert = gateway.db.insert
    fail_once = [True]
    def lose_checkout_after_invoice(*args):
        if fail_once.pop() if fail_once else False:
            raise RuntimeError("lost response after KOVA invoice committed")
        return original_insert(*args)
    monkeypatch.setattr(gateway.db, "insert", lose_checkout_after_invoice)
    with pytest.raises(RuntimeError, match="lost response"):
        client.post("/v1/billing/orders", headers={"Idempotency-Key": "audit-stale-payment-0001"},
                    json={"plan": "personal.pro.monthly", "payer": payer})
    created = client.post("/v1/billing/orders", headers={"Idempotency-Key": "audit-stale-payment-0001"},
                          json={"plan": "personal.pro.monthly", "payer": payer})
    assert created.status_code == 200, created.text
    order = created.json()
    with book.store.connect() as db:
        assert db.execute("SELECT count(*) FROM invoices").fetchone()[0] == 1
    assert 12_000_000 < int(order["amount_raw"]) < 12_010_000
    receipt["logs"][0]["data"] = hex(int(order["amount_raw"]))
    paid = client.post(f"/v1/billing/orders/{order['order_id']}/confirm",
        headers={"X-Checkout-Token": order["checkout_token"]}, json={"tx_hash": "0x" + "aa" * 32})
    assert paid.status_code == 422, paid.text
    assert gateway.db.get(order["order_id"])["key_id"] is None
    receipt["blockNumber"] = "0x65"
    def fresh_rpc(method, params):
        if method == "eth_getTransactionReceipt":
            return receipt
        if method == "eth_getBlockByNumber":
            return {"timestamp": hex(int(time.time()) + 1)}
        return "0x70"
    monkeypatch.setattr(book.pool, "call", fresh_rpc)
    paid = client.post(f"/v1/billing/orders/{order['order_id']}/confirm",
        headers={"X-Checkout-Token": order["checkout_token"]}, json={"tx_hash": "0x" + "aa" * 32})
    assert paid.status_code == 200, paid.text
    result = paid.json()
    assert result["state"] == "confirmed" and result["api_key"].startswith("ask_")
    assert gateway.db.key(result["api_key"])["plan"] == "personal.pro.monthly"


def test_checkout_grants_license_without_spendable_uni(checkout):
    from core.uni.wallet import UniWalletService
    p, quote, buyer, confirm = checkout
    result = confirm()
    assert result["license_key"]
    svc = UniWalletService()
    assert svc.get_wallet_by_owner(buyer["id"]) is None
    from core.uni.wallet import InsufficientFundsError
    with pytest.raises(InsufficientFundsError):
        svc.charge(buyer["id"], seller_owner_id="audit-second-seller", amount_uni=500,
                   idempotency_key="audit-second-purchase")


@pytest.mark.parametrize("new_price", [1.0, 6.0])
def test_catalog_change_honors_issued_quote(checkout, monkeypatch, new_price):
    p, quote, buyer, confirm = checkout
    monkeypatch.setattr(p, "_catalog_checkout_usdt", lambda _: new_price)
    assert confirm()["license_key"]
    assert p.commerce.get_order_by_tx_hash("0x" + "ab" * 32)["amount"] == 5.0


@pytest.mark.parametrize("field,value", [("amount", 0.01), ("quote_version", 2), ("quote_seal", "")])
def test_quote_tampering_is_refused(checkout, field, value):
    from fastapi import HTTPException
    p, quote, buyer, confirm = checkout
    quote[field] = value
    with pytest.raises(HTTPException) as exc:
        confirm()
    assert exc.value.status_code == 400
    assert not p.commerce.get_order_by_tx_hash("0x" + "ab" * 32)


def test_login_key_rotation_does_not_invalidate_paid_quote(checkout, monkeypatch):
    p, quote, buyer, confirm = checkout
    seal = quote["quote_seal"]
    monkeypatch.setenv("CUSTOMER_JWT_SECRET", "rotated-login-secret-000000000000000000000000")
    assert p._quote_seal(quote) == seal
    assert confirm()["license_key"]


@pytest.mark.parametrize("paid_on_time", [True, False])
def test_expired_quote_recovers_on_time_payment_only(checkout, monkeypatch, paid_on_time):
    from fastapi import HTTPException
    p, quote, buyer, confirm = checkout
    quote["created_at"] = time.time() - 3600
    quote["expires_at"] = time.time() - 10
    quote["quote_seal"] = p._quote_seal(quote)
    p._persist_pending_payments()
    verifier = p._verify_evm_transaction
    monkeypatch.setattr(p, "_verify_evm_transaction", lambda **kw: {
        **verifier(**kw), "block_time": quote["expires_at"] + (-1 if paid_on_time else 1)})
    p._pending_payments = {}
    p._load_pending_payments_from_disk()
    assert quote["payment_id"] in p._pending_payments
    if paid_on_time:
        assert confirm()["license_key"]
    else:
        with pytest.raises(HTTPException) as exc:
            confirm()
        assert exc.value.status_code == 409
        assert p._pending_payments[quote["payment_id"]]["claim_review"]["reason"] == "quote_paid_after_expiry"


@pytest.mark.parametrize("legacy_confirming", [False, True])
def test_crashed_confirmation_retries_after_restart(checkout, monkeypatch, legacy_confirming):
    p, quote, buyer, confirm = checkout
    verifier = p._verify_evm_transaction
    def die(**kwargs):
        raise SystemExit("synthetic process exit")
    monkeypatch.setattr(p, "_verify_evm_transaction", die)
    with pytest.raises(SystemExit):
        confirm()
    if legacy_confirming:
        quote["status"] = "confirming"
        p._persist_pending_payments()
    p._pending_payments = {}
    p._confirm_locks = {}
    p._load_pending_payments_from_disk()
    monkeypatch.setattr(p, "_verify_evm_transaction", verifier)
    assert confirm()["license_key"]
    assert len(p.commerce.get_orders_for_customer(buyer["id"])) == 1


@pytest.mark.parametrize("after_commit", [False, True])
def test_hard_exit_at_license_commit_recovers_exactly_one_order(checkout, after_commit, isolated):
    p, quote, buyer, confirm = checkout
    source = '''
import asyncio, os, sys
from pathlib import Path
from web.backend.api import payment as p
from web.backend.services.commerce import CommerceService
p.commerce = CommerceService(base_dir=str(Path(sys.argv[1]) / 'orders'))
p.PENDING_PAYMENTS_FILE = Path(sys.argv[1]) / 'pending.json'
p._pending_payments = {}
p._load_pending_payments_from_disk()
p._verify_evm_transaction = lambda **kw: dict(verified=True, confirmations=100, block_number=100)
original = p.commerce.create_order_and_license
def exit_at_commit(**kw):
    if sys.argv[4] == 'True':
        original(**kw)
    os._exit(9)
p.commerce.create_order_and_license = exit_at_commit
asyncio.run(p._confirm_payment(sys.argv[2], '0x'+'ab'*32, '', {'sub':sys.argv[3]}, None,
                              operator={'sub':'synthetic-audit-operator'}))
'''
    result = subprocess.run([sys.executable, "-c", source, str(isolated), quote["payment_id"],
                             buyer["id"], str(after_commit)], cwd=ROOT, env=dict(os.environ),
                             capture_output=True, timeout=30)
    assert result.returncode == 9, result.stderr.decode()
    p._pending_payments = {}
    p._load_pending_payments_from_disk()
    result = confirm()
    assert result["license_key"]
    assert len(p.commerce.get_orders_for_customer(buyer["id"])) == 1


def test_uni_hold_leaves_unreserved_money_spendable(isolated):
    from core.uni.wallet import InsufficientFundsError, UniWalletService
    svc = UniWalletService()
    svc.topup_from_chain("buyer", usd_amount=10, tx_hash="synthetic-topup")
    svc.hold("buyer", amount_uni=600, channel_id="audit-hold")
    wallet = svc.get_wallet_by_owner("buyer")
    assert wallet["balance_uni"] == 400
    assert wallet["hold_uni"] == 600
    assert wallet["available_uni"] == 400
    svc.charge("buyer", seller_owner_id="seller", amount_uni=400, idempotency_key="charge-400")
    with pytest.raises(InsufficientFundsError):
        svc.charge("buyer", seller_owner_id="seller", amount_uni=1, idempotency_key="charge-1")
    svc.release_hold("audit-hold")
    assert svc.economy_summary()["balance_uni_total"] == 1000


def test_regular_charge_and_hold_charge_ledger_match_wallet(isolated):
    from core.uni.store import uni_connection
    from core.uni.wallet import UniWalletService
    svc = UniWalletService()
    svc.grant("buyer", amount_uni=1000, ref="ledger-test")
    svc.hold("buyer", amount_uni=600, channel_id="ledger-hold")
    svc.charge("buyer", seller_owner_id="seller", amount_uni=100, idempotency_key="ledger-charge")
    for operation in (None, lambda: svc.spend_hold(channel_id="ledger-hold", amount_uni=100, ref="held-call")):
        if operation:
            operation()
        wallet = svc.get_wallet_by_owner("buyer")
        placeholder = "%s" if os.environ["UNI_DB_BACKEND"] == "postgres" else "?"
        with uni_connection() as conn:
            row = conn.execute("SELECT balance_after, hold_after FROM uni_ledger WHERE wallet_id="
                               + placeholder + " ORDER BY id DESC LIMIT 1", (wallet["wallet_id"],)).fetchone()
        assert row["balance_after"] == wallet["balance_uni"]
        assert row["hold_after"] == wallet["hold_uni"]


def test_uni_sqlite_withdraw_completes_with_existing_platform_wallet(isolated):
    source = '''
import faulthandler
from core.uni.wallet import UniWalletService
svc = UniWalletService()
svc.grant('buyer', amount_uni=100000, ref='audit-funded')
svc.get_or_create_platform_wallet()
faulthandler.dump_traceback_later(1.0)
print('funded; about to withdraw', flush=True)
svc.withdraw_to_chain('buyer', amount_uni=10000, payout_address='0x'+'12'*20, chain='base')
'''
    env = dict(os.environ)
    env["AIFACTORY_DATA_ROOT"] = str(isolated / "withdraw-child")
    env["UNI_DB_BACKEND"] = "sqlite"
    result = subprocess.run([sys.executable, "-c", source], cwd=ROOT, env=env,
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode()
    assert b"about to withdraw" in result.stdout



def queued_withdrawal(monkeypatch):
    """Use the real withdrawal path, with no lock bypass or direct queue insertion."""
    from core.uni.wallet import UniWalletService
    svc = UniWalletService()
    svc.grant("buyer", amount_uni=10000, ref="audit-withdraw-funded")
    result = svc.withdraw_to_chain("buyer", amount_uni=10000,
             payout_address="0x" + "12" * 20, chain="base")
    return svc, result


def test_failed_withdraw_refund_is_retried_atomically(isolated, monkeypatch):
    from core.uni.jobs import run_withdraw_dispatcher_job
    from core.uni.store import uni_connection
    from core.uni.wallet import UniWalletService
    svc, withdrawal = queued_withdrawal(monkeypatch)
    monkeypatch.setenv("AIFACTORY_UNI_WITHDRAW_DISPATCHER", "0")
    original = UniWalletService._credit_balance
    def fail_refund(*a, **kw):
        raise RuntimeError("synthetic unavailable refund writer")
    monkeypatch.setattr(UniWalletService, "_credit_balance", fail_refund)
    first = run_withdraw_dispatcher_job()
    monkeypatch.setattr(UniWalletService, "_credit_balance", original)
    placeholder = "%s" if os.environ["UNI_DB_BACKEND"] == "postgres" else "?"
    with uni_connection() as conn:
        pending = conn.execute("SELECT status FROM uni_withdrawals WHERE withdrawal_id=" + placeholder,
                               (withdrawal["withdrawal_id"],)).fetchone()
        assert pending["status"] == "refund_due"
        assert conn.execute("SELECT count(*) AS n FROM uni_ledger WHERE entry_type='refund'").fetchone()["n"] == 0
    second = run_withdraw_dispatcher_job()
    with uni_connection() as conn:
        row = conn.execute("SELECT status FROM uni_withdrawals WHERE withdrawal_id=" + placeholder,
                           (withdrawal["withdrawal_id"],)).fetchone()
    assert row["status"] == "failed"
    assert first["processed"] == 1 and first["failed_refunded"] == 0
    assert second["processed"] == 0
    assert second["failed_refunded"] == 1
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 10000
    assert run_withdraw_dispatcher_job()["failed_refunded"] == 0


def test_failed_withdraw_refund_preserves_total_money(isolated, monkeypatch):
    from core.uni.jobs import run_withdraw_dispatcher_job
    monkeypatch.setenv("AIFACTORY_UNI_WITHDRAW_FEE_BPS", "100")
    svc, withdrawal = queued_withdrawal(monkeypatch)
    monkeypatch.setenv("AIFACTORY_UNI_WITHDRAW_DISPATCHER", "0")
    assert withdrawal["fee_uni"] == 100
    result = run_withdraw_dispatcher_job()
    assert result["failed_refunded"] == 1
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 10000
    assert svc.economy_summary()["balance_uni_total"] == 10000


def test_parallel_refunders_return_money_once(isolated, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from core.uni.jobs import run_withdraw_dispatcher_job
    svc, withdrawal = queued_withdrawal(monkeypatch)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_withdraw_dispatcher_job(), range(2)))
    assert sum(r["failed_refunded"] for r in results) == 1
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 10000
    assert svc.economy_summary()["balance_uni_total"] == 10000


@pytest.mark.parametrize("already_refunded", [False, True])
def test_legacy_failed_withdrawal_and_fee_are_recovered(isolated, monkeypatch, already_refunded):
    from core.uni.jobs import run_withdraw_dispatcher_job
    from core.uni.store import uni_connection
    svc, withdrawal = queued_withdrawal(monkeypatch)
    platform = svc.get_or_create_platform_wallet()
    pg = os.environ["UNI_DB_BACKEND"] == "postgres"
    def sql(query):
        return query.replace("?", "%s") if pg else query
    with uni_connection() as conn:
        conn.execute(sql("UPDATE uni_withdrawals SET status='failed', fee_credited=1 WHERE withdrawal_id=?"),
                     (withdrawal["withdrawal_id"],))
        conn.execute(sql("UPDATE uni_wallets SET balance_uni=balance_uni+?, lifetime_in=lifetime_in+? WHERE wallet_id=?"),
                     (withdrawal["fee_uni"], withdrawal["fee_uni"], platform["wallet_id"]))
    if already_refunded:
        svc.grant("buyer", amount_uni=10000, ref=f"withdraw-reap:{withdrawal['withdrawal_id']}")
    run_withdraw_dispatcher_job()
    run_withdraw_dispatcher_job()
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 10000
    assert svc.get_or_create_platform_wallet()["balance_uni"] == 0
    assert svc.economy_summary()["balance_uni_total"] == 10000


def test_unknown_chain_payout_never_auto_refunds(isolated, monkeypatch):
    from core.uni.jobs import run_withdraw_dispatcher_job
    from core.uni.store import uni_connection
    svc, withdrawal = queued_withdrawal(monkeypatch)
    pg = os.environ["UNI_DB_BACKEND"] == "postgres"
    with uni_connection() as conn:
        query = "UPDATE uni_withdrawals SET status='sending', tx_hash=?, requested_at=0 WHERE withdrawal_id=?"
        conn.execute(query.replace("?", "%s") if pg else query, ("0x" + "ab" * 32, withdrawal["withdrawal_id"]))
    assert run_withdraw_dispatcher_job()["failed_refunded"] == 0
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 0


def test_real_process_exit_rolls_back_refund_and_retry_recovers(isolated, monkeypatch):
    from core.uni.jobs import run_withdraw_dispatcher_job
    from core.uni.store import uni_connection
    svc, withdrawal = queued_withdrawal(monkeypatch)
    pg = os.environ["UNI_DB_BACKEND"] == "postgres"
    with uni_connection() as conn:
        query = "UPDATE uni_withdrawals SET status='refund_due' WHERE withdrawal_id=?"
        conn.execute(query.replace("?", "%s") if pg else query, (withdrawal["withdrawal_id"],))
    source = '''
import os, sys
from core.uni.wallet import UniWalletService
class CrashRefund(UniWalletService):
    def _credit_balance(self, *a, **kw):
        super()._credit_balance(*a, **kw)
        os._exit(9)
CrashRefund().refund_withdrawal(sys.argv[1])
'''
    result = subprocess.run([sys.executable, "-c", source, withdrawal["withdrawal_id"]],
                            cwd=ROOT, env=dict(os.environ), capture_output=True, timeout=30)
    assert result.returncode == 9, result.stderr.decode()
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 0
    assert run_withdraw_dispatcher_job()["failed_refunded"] == 1
    assert run_withdraw_dispatcher_job()["failed_refunded"] == 0
    assert svc.economy_summary()["balance_uni_total"] == 10000

