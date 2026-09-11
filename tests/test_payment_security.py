"""Security regression tests for on-chain payment verification."""

from __future__ import annotations

import pytest

from web.backend.api import payment as pay
from web.backend.services.commerce import CommerceService, TxHashAlreadyUsedError


class _FakePool:
    """Stands in for `chain_net.RpcPool`.

    Both verifiers were rewritten to go through a health-checked RPC pool —
    `pool.call(method, params)` for Solana, `pool.run(fetch)` for EVM — and these two
    tests were still stubbing what the old code used (`httpx.Client`, `pay._get_web3`).
    So the Solana test measured a real network call that failed ("Transaction not found
    on Solana", not the underpayment refusal it asserts) and the EVM one could not even
    monkeypatch its target. The min-confirmations and underpayment refusals on the money
    path had had no coverage since that refactor.
    """

    def __init__(self, *, call_result=None, run_result=None):
        self._call_result = call_result
        self._run_result = run_result

    def call(self, method, params):
        return self._call_result

    def run(self, fn):
        return self._run_result


def test_solana_rejects_underpayment(monkeypatch):
    meta = {
        "err": None,
        "preBalances": [5_000_000_000, 1_000_000_000],
        "postBalances": [4_999_000_000, 1_000_100_000],  # +0.0001 SOL to recipient
        "preTokenBalances": [],
        "postTokenBalances": [],
    }
    tx_data = {
        "slot": 100,
        "confirmations": 10,
        "meta": meta,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "sender1111111111111111111111111111111111111"},
                    {"pubkey": "recipient222222222222222222222222222222222222"},
                ]
            }
        },
    }
    monkeypatch.setattr(pay, "_pool_for_chain", lambda chain: _FakePool(call_result=tx_data))

    result = pay._verify_solana_transaction(
        "5" * 88,
        "recipient222222222222222222222222222222222222",
        expected_amount=4.99,
        expected_token="SOL",
    )

    assert result["verified"] is False
    assert "Insufficient" in result.get("error", ""), result


def test_solana_rejects_when_recipient_balance_unknown():
    """No verified=True fallback when balance index cannot be resolved."""
    result = pay._verify_solana_transaction(
        "not-a-real-tx",
        "recipient222222222222222222222222222222222222",
        expected_amount=1.0,
        expected_token="SOL",
    )
    assert result["verified"] is False


def test_evm_requires_min_confirmations(monkeypatch):
    recipient = "0x" + "b" * 40

    class FakeTx(dict):
        pass

    tx = FakeTx({"to": recipient, "value": 10**18, "from": "0x" + "a" * 40})
    receipt = {"status": 1, "blockNumber": 100, "logs": []}
    current_block = 101  # exactly 1 confirmation, below MIN_CONFIRMATIONS

    assert pay.MIN_CONFIRMATIONS > 1, "this test needs a bar above one confirmation"
    monkeypatch.setattr(
        pay,
        "_pool_for_chain",
        lambda chain: _FakePool(run_result=(tx, receipt, current_block)),
    )
    monkeypatch.setattr(pay, "RECIPIENT_ADDRESS_EVM", recipient)

    result = pay._verify_evm_transaction(
        "base",
        "0x" + "c" * 64,
        recipient,
        1.0,
        "ETH",
    )
    assert result["verified"] is False
    assert result.get("pending") is True, result
    assert result.get("confirmations") == 1, result


def test_commerce_tx_hash_replay_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    svc = CommerceService(base_dir=str(tmp_path / "store"))
    customer = svc.register_customer("payer@example.com", "password-12345")

    svc.create_order_and_license(
        customer_id=customer["id"],
        customer_email=customer["email"],
        payment_id="pay-a",
        product_id="prod-1",
        amount=5.0,
        currency="USDT",
        tx_hash="0xdeadbeef",
    )

    with pytest.raises(TxHashAlreadyUsedError):
        svc.create_order_and_license(
            customer_id=customer["id"],
            customer_email=customer["email"],
            payment_id="pay-b",
            product_id="prod-2",
            amount=5.0,
            currency="USDT",
            tx_hash="0xdeadbeef",
        )


def test_commerce_tx_hash_unique_index_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path))
    svc = CommerceService(base_dir=str(tmp_path / "store"))
    rows = svc.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_orders_tx_hash_unique'"
    ).fetchall()
    assert len(rows) == 1
