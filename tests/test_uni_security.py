"""UNI wallet security regressions (audit C/H items)."""

from __future__ import annotations

import json
import re
import uuid

import pytest

from core.uni.wallet import InsufficientFundsError, UniWalletService


@pytest.fixture
def uni_svc(tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("AIFACTORY_UNI_ENABLED", "1")
    monkeypatch.setenv("AIFACTORY_UNI_TOPUP_SPREAD_BPS", "0")
    import core.uni.store as uni_store

    uni_store._sqlite_conn = None
    return UniWalletService()


def test_topup_idempotent_no_double_balance(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    tx = f"0x{uuid.uuid4().hex}"
    a = uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=tx, chain="base", token="USDT")
    b = uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=tx, chain="base", token="USDT")
    assert a["wallet"]["balance_uni"] == 1000
    assert b.get("duplicate") is True
    assert b["wallet"]["balance_uni"] == 1000


def test_hold_conditional_rejects_overdraft(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=1.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    with pytest.raises(InsufficientFundsError):
        uni_svc.hold(owner, amount_uni=200, channel_id=f"ch_{uuid.uuid4().hex[:8]}")


def test_available_uni_is_balance_minus_hold(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=5.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    ch = f"ch_{uuid.uuid4().hex[:8]}"
    uni_svc.hold(owner, amount_uni=300, channel_id=ch)
    w = uni_svc.get_wallet_by_owner(owner)
    assert w["balance_uni"] == 200
    assert w["hold_uni"] == 300
    assert w["available_uni"] == 0


def test_spend_hold_duplicate_not_free(uni_svc):
    owner = f"cust-{uuid.uuid4().hex[:8]}"
    uni_svc.topup_from_chain(owner, usd_amount=10.0, tx_hash=f"0x{uuid.uuid4().hex}", chain="base", token="USDT")
    ch = f"ch_{uuid.uuid4().hex[:8]}"
    uni_svc.hold(owner, amount_uni=500, channel_id=ch)
    ref = "prod/cap/nonce1"
    first = uni_svc.spend_hold(channel_id=ch, amount_uni=100, ref=ref)
    second = uni_svc.spend_hold(channel_id=ch, amount_uni=100, ref=ref)
    assert first.get("ok") is True
    assert second.get("duplicate") is True
    assert second.get("ok") is False


def test_receipt_signature_roundtrip():
    from core.tracing import span
    from core.uni.receipts import issue_receipt, verify_receipt

    with span("test_receipt", attributes={"test": True}):
        r = issue_receipt(
            wallet_id="uni_wal_test",
            kind="grant",
            amount_uni=42,
            meta={"note": "test"},
            idempotency_key=f"test-{uuid.uuid4().hex}",
        )
    assert verify_receipt(r) is True
    payload = json.loads(r.get("payload_json") or "{}")
    if payload.get("trace_id"):
        assert re.fullmatch(r"[0-9a-f]{32}", str(payload["trace_id"]))
    r["amount_uni"] = "999"
    assert verify_receipt(r) is False
