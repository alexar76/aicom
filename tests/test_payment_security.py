"""Security regression tests for on-chain payment verification."""

from __future__ import annotations

import pytest

from web.backend.api import payment as pay
from web.backend.services.commerce import CommerceService, TxHashAlreadyUsedError


def test_solana_rejects_underpayment():
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

    def fake_post(url, json):
        class Resp:
            def json(self_inner):
                return {"result": tx_data}

        return Resp()

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json):
            return fake_post(url, json)

    import httpx

    original = httpx.Client
    httpx.Client = lambda **kw: FakeClient()
    try:
        result = pay._verify_solana_transaction(
            "5" * 88,
            "recipient222222222222222222222222222222222222",
            expected_amount=4.99,
            expected_token="SOL",
        )
    finally:
        httpx.Client = original

    assert result["verified"] is False
    assert "Insufficient" in result.get("error", "")


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

    class FakeTx:
        def get(self, k, default=None):
            if k == "to":
                return recipient
            if k == "value":
                return 10**18
            if k == "from":
                return "0x" + "a" * 40
            return default

    class FakeEth:
        block_number = 101  # only 1 confirmation

        def get_transaction(self, tx_hash):
            return FakeTx()

        def get_transaction_receipt(self, tx_hash):
            return {"status": 1, "blockNumber": 100, "logs": []}

    class FakeW3:
        eth = FakeEth()

        @staticmethod
        def from_wei(value, unit):
            return value / 10**18

    monkeypatch.setattr(pay, "_get_web3", lambda chain: FakeW3())
    monkeypatch.setattr(pay, "RECIPIENT_ADDRESS_EVM", recipient)

    result = pay._verify_evm_transaction(
        "base",
        "0x" + "c" * 64,
        "0x" + "b" * 40,
        1.0,
        "ETH",
    )
    assert result["verified"] is False
    assert result.get("pending") is True


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
