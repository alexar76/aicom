"""Verifiable agent-revenue commitments (F4)."""

from aimarket_hub.revenue_proofs import (
    commit_revenue,
    prove_receipt,
    to_e6,
    verify_agent_revenue,
    verify_receipt,
)

RECEIPTS = [
    {"agent": "agent-alpha", "amount_usd": 1.50, "receipt_id": "r1"},
    {"agent": "agent-beta", "amount_usd": 0.25, "receipt_id": "r2"},
    {"agent": "agent-alpha", "amount_usd": 2.00, "receipt_id": "r3"},
    {"agent": "agent-alpha", "amount_usd": 0.75, "receipt_id": "r4"},
]


def test_empty_commitment_is_safe():
    c = commit_revenue([])
    assert c.root == b"\x00" * 32
    assert c.total_e6("anyone") == 0


def test_single_receipt_inclusion_verifies():
    c = commit_revenue(RECEIPTS)
    proof = prove_receipt(c, 0)
    assert verify_receipt(c.root, index=0, agent_id="agent-alpha", amount_e6=to_e6(1.50), proof=proof)


def test_tampered_amount_fails():
    c = commit_revenue(RECEIPTS)
    proof = prove_receipt(c, 0)
    # Claim a higher amount than was committed → proof must not verify.
    assert not verify_receipt(c.root, index=0, agent_id="agent-alpha", amount_e6=to_e6(99.0), proof=proof)


def test_agent_total_is_trustlessly_verifiable():
    c = commit_revenue(RECEIPTS)
    # agent-alpha earned 1.50 + 2.00 + 0.75 = 4.25 across indices 0, 2, 3.
    items = [
        {"index": i, "amount_e6": r["amount_e6"], "proof": prove_receipt(c, i)}
        for i, r in enumerate(c.rows)
        if r["agent"] == "agent-alpha"
    ]
    assert verify_agent_revenue(c.root, agent_id="agent-alpha", claimed_total_e6=to_e6(4.25), items=items)
    # Inflated claim is rejected.
    assert not verify_agent_revenue(c.root, agent_id="agent-alpha", claimed_total_e6=to_e6(5.00), items=items)


def test_replayed_leaf_cannot_double_count():
    c = commit_revenue(RECEIPTS)
    p0 = prove_receipt(c, 0)
    # Submit index 0 twice to fake 1.50 + 1.50 = 3.00 of revenue.
    items = [
        {"index": 0, "amount_e6": to_e6(1.50), "proof": p0},
        {"index": 0, "amount_e6": to_e6(1.50), "proof": p0},
    ]
    assert not verify_agent_revenue(c.root, agent_id="agent-alpha", claimed_total_e6=to_e6(3.00), items=items)


def test_cross_agent_leaf_rejected():
    c = commit_revenue(RECEIPTS)
    # index 1 belongs to agent-beta; alpha cannot claim it.
    items = [{"index": 1, "amount_e6": to_e6(0.25), "proof": prove_receipt(c, 1)}]
    assert not verify_agent_revenue(c.root, agent_id="agent-alpha", claimed_total_e6=to_e6(0.25), items=items)
