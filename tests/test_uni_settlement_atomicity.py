"""Real-store atomicity at the wallet/ledger/signed-receipt boundary."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.test_payment_chain_recovery import isolated

pytestmark = pytest.mark.component_integration


def snapshot():
    from core.uni.store import uni_connection

    with uni_connection() as conn:
        return {table: sorted(json.dumps(dict(row), sort_keys=True) for row in conn.execute(
            f"SELECT * FROM {table}").fetchall()) for table in (
                "uni_wallets", "uni_ledger", "uni_holds", "uni_withdrawals", "uni_receipts")}


def setup_wallet():
    from core.uni.wallet import UniWalletService

    svc = UniWalletService()
    svc.grant("buyer", amount_uni=1000, ref="seed", meta={})
    svc.get_or_create_wallet("seller")
    svc.get_or_create_platform_wallet()
    return svc


def refuse_receipts():
    from core.uni.store import uni_connection

    with uni_connection() as conn:
        if os.environ["UNI_DB_BACKEND"] == "postgres":
            conn.execute("""CREATE FUNCTION refuse_receipt() RETURNS trigger LANGUAGE plpgsql AS
                $$ BEGIN RAISE EXCEPTION 'injected receipt write failure'; END $$""")
            conn.execute("""CREATE TRIGGER refuse_receipt BEFORE INSERT ON uni_receipts
                FOR EACH ROW EXECUTE FUNCTION refuse_receipt()""")
        else:
            conn.execute("""CREATE TRIGGER refuse_receipt BEFORE INSERT ON uni_receipts
                BEGIN SELECT RAISE(ABORT, 'injected receipt write failure'); END""")


def allow_receipts():
    from core.uni.store import uni_connection

    with uni_connection() as conn:
        conn.execute("DROP TRIGGER refuse_receipt ON uni_receipts" if os.environ["UNI_DB_BACKEND"] == "postgres"
                     else "DROP TRIGGER refuse_receipt")


@pytest.mark.parametrize("operation", ["charge", "grant", "spend", "withdraw"])
@pytest.mark.parametrize("failure", ["sign", "write"])
def test_failed_receipt_rolls_back_money_ledger_and_work(isolated, monkeypatch, operation, failure):
    import core.uni.signing as signing
    from core.uni.receipts import get_receipt_by_idempotency_key, verify_receipt

    svc = setup_wallet()
    monkeypatch.setenv("AIFACTORY_UNI_MIN_WITHDRAW_UNI", "1")
    if operation == "spend":
        svc.hold("buyer", amount_uni=800, channel_id="channel", seller_ref="seller")
    calls = {
        "charge": lambda: svc.charge("buyer", seller_owner_id="seller", amount_uni=500, idempotency_key="charge"),
        "grant": lambda: svc.grant("buyer", amount_uni=500, ref="new-grant", meta={}),
        "spend": lambda: svc.spend_hold(channel_id="channel", amount_uni=500, ref="invoice"),
        "withdraw": lambda: svc.withdraw_to_chain("buyer", amount_uni=500, payout_address="0x" + "ab" * 20, chain="base"),
    }
    before = snapshot()
    with monkeypatch.context() as patch:
        if failure == "sign":
            def broken_signer(_):
                raise RuntimeError("injected receipt signing failure")
            patch.setattr(signing, "sign_payload", broken_signer)
        else:
            refuse_receipts()
        with pytest.raises(Exception, match="injected receipt"):
            calls[operation]()
        assert snapshot() == before, "financial state committed without a signed receipt"
    if failure == "write":
        allow_receipts()
    result = calls[operation]()
    receipt = result.get("receipt") or get_receipt_by_idempotency_key("withdraw:" + result["withdrawal_id"])
    assert receipt and verify_receipt(receipt)
    after = snapshot()
    assert len(after["uni_receipts"]) == len(before["uni_receipts"]) + 1
    assert len(after["uni_ledger"]) == len(before["uni_ledger"]) + 1


def test_receipt_retry_returns_the_stored_signed_payload(isolated):
    from core.uni.receipts import get_receipt_by_idempotency_key, issue_receipt, verify_receipt

    svc = setup_wallet()
    wallet = svc.get_wallet_by_owner("buyer")["wallet_id"]
    args = {"wallet_id": wallet, "kind": "test", "amount_uni": 7, "meta": {}, "idempotency_key": "receipt-retry"}
    first = issue_receipt(**args)
    retry = issue_receipt(**args)
    assert retry == first == get_receipt_by_idempotency_key("receipt-retry")
    assert verify_receipt(retry)


def test_long_idempotency_keys_with_a_shared_prefix_keep_distinct_receipts(isolated):
    svc = setup_wallet()
    prefix = "same-prefix-" * 15
    first = svc.grant("buyer", amount_uni=10, ref=prefix + "a", meta={})
    second = svc.grant("buyer", amount_uni=20, ref=prefix + "b", meta={})
    assert first["receipt"]["id"] != second["receipt"]["id"]
    assert first["receipt"]["amount_uni"] == "10"
    assert second["receipt"]["amount_uni"] == "20"
    retry = svc.grant("buyer", amount_uni=10, ref=prefix + "a", meta={})
    assert retry["receipt"] == first["receipt"]
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 1030


def test_concurrent_charge_retries_debit_once_and_share_receipt(isolated):
    svc = setup_wallet()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: svc.charge(
            "buyer", seller_owner_id="seller", amount_uni=200, idempotency_key="parallel"), range(8)))
    assert len({r["receipt"]["id"] for r in results}) == 1
    assert sum(not r.get("duplicate", False) for r in results) == 1
    assert svc.get_wallet_by_owner("buyer")["balance_uni"] == 800
    assert svc.get_wallet_by_owner("seller")["balance_uni"] == 190
    assert svc.get_or_create_platform_wallet()["balance_uni"] == 10


def test_retry_of_depleted_hold_returns_original_receipt(isolated):
    svc = setup_wallet()
    svc.hold("buyer", amount_uni=500, channel_id="all", seller_ref="seller")
    first = svc.spend_hold(channel_id="all", amount_uni=500, ref="invoice")
    before = snapshot()
    retry = svc.spend_hold(channel_id="all", amount_uni=500, ref="invoice")
    assert retry["duplicate"] is True
    assert retry["receipt"] == first["receipt"]
    assert snapshot() == before


@pytest.mark.parametrize("operation", ["charge", "grant", "spend", "withdraw"])
def test_hard_exit_after_receipt_insert_cannot_commit_partial_money(isolated, monkeypatch, operation):
    svc = setup_wallet()
    monkeypatch.setenv("AIFACTORY_UNI_MIN_WITHDRAW_UNI", "1")
    if operation == "spend":
        svc.hold("buyer", amount_uni=800, channel_id="crash", seller_ref="seller")
    before = snapshot()
    code = '''
import os
from core.uni.wallet import UniWalletService
from core.uni import receipts
original = receipts.issue_receipt
def stop_after_insert(**kwargs):
    original(**kwargs)
    os._exit(9)
receipts.issue_receipt = stop_after_insert
svc = UniWalletService()
operation = os.environ['AUDIT_SETTLEMENT_OPERATION']
if operation == 'charge':
    svc.charge('buyer', seller_owner_id='seller', amount_uni=500, idempotency_key='crash')
elif operation == 'grant':
    svc.grant('buyer', amount_uni=500, ref='crash', meta={})
elif operation == 'spend':
    svc.spend_hold(channel_id='crash', amount_uni=500, ref='crash')
else:
    svc.withdraw_to_chain('buyer', amount_uni=500, payout_address='test', chain='base')
'''
    child = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
        env={**os.environ, "AUDIT_SETTLEMENT_OPERATION": operation}, timeout=20)
    assert child.returncode == 9, child.stderr
    assert snapshot() == before, "process exit committed a partial settlement"
