"""The deposit verifier against a REAL USDC transfer on Base.

The synthetic receipts in `test_deposit_verify.py` pin the decode logic; this pins the
thing that actually matters — that the verifier can talk to Base, find a real payment in a
real receipt, and name the wallet that made it. First run 2026-09-07 against
`0xa28b2fb0…3666`: 223 295.895118 USDC, payer `0xb2cc224c…`, 50 confirmations, verified.

Marked `live` and skipped without network, so it never breaks an offline suite:
    pytest -m live tests/test_deposit_verify_live.py
"""

from __future__ import annotations

import os

import pytest

from aimarket_hub.deposit_verify import TRANSFER_TOPIC, verify_deposit

pytestmark = pytest.mark.live

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
RPC = os.environ.get("AIMARKET_DEPOSIT_RPC_URL") or "https://base-rpc.publicnode.com"


def _rpc(method: str, params: list):
    httpx = pytest.importorskip("httpx")
    resp = httpx.post(
        RPC, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=30
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(str(body["error"])[:160])
    return body.get("result")


@pytest.fixture(scope="module")
def a_real_usdc_payment() -> dict:
    """A recent Base transaction that moved USDC exactly once, straight off the chain.

    Not a pinned hash: a fixed transaction eventually falls out of every public node's
    history, and a test that needs archive access is a test that fails for the wrong
    reason. This finds a fresh one each run — which also means it re-proves the RPC path.
    """
    try:
        head = int(_rpc("eth_blockNumber", []), 16)
        logs = _rpc("eth_getLogs", [{
            "fromBlock": hex(head - 40), "toBlock": hex(head - 20),
            "address": USDC_BASE, "topics": [TRANSFER_TOPIC],
        }])
    except Exception as exc:
        pytest.skip(f"Base RPC unavailable: {exc}")
    by_tx: dict[str, list] = {}
    for log in logs or []:
        by_tx.setdefault(log["transactionHash"], []).append(log)
    single = [(tx, entries[0]) for tx, entries in by_tx.items() if len(entries) == 1]
    if not single:
        pytest.skip("no single-transfer USDC tx in the sampled window")
    tx_hash, log = single[0]
    return {
        "tx_hash": tx_hash,
        "payer": "0x" + log["topics"][1][-40:],
        "recipient": "0x" + log["topics"][2][-40:],
        "usdc": int(log["data"], 16) / 10 ** 6,
    }


def test_a_real_payment_verifies_and_names_its_payer(a_real_usdc_payment):
    payment = a_real_usdc_payment
    check = verify_deposit(
        tx_hash=payment["tx_hash"], amount_usd=payment["usdc"], chain="base",
        token="USDC", recipient=payment["recipient"], min_confirmations=2,
    )
    assert check.ok, check.error
    assert check.sender == payment["payer"].lower()
    assert check.confirmations >= 2
    assert check.paid_units == check.expected_units


def test_a_stranger_cannot_claim_a_real_payment(a_real_usdc_payment):
    """The whole point of binding the payer: this tx is public, the hash is quotable."""
    check = verify_deposit(
        tx_hash=a_real_usdc_payment["tx_hash"], amount_usd=1.0, chain="base",
        token="USDC", recipient="0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
        min_confirmations=2,
    )
    assert not check.ok
    assert "moved no USDC to the configured recipient" in check.error


def test_asking_for_more_than_was_paid_is_refused(a_real_usdc_payment):
    payment = a_real_usdc_payment
    check = verify_deposit(
        tx_hash=payment["tx_hash"], amount_usd=payment["usdc"] * 2 + 1, chain="base",
        token="USDC", recipient=payment["recipient"], min_confirmations=2,
    )
    assert not check.ok
    assert "short" in check.error
