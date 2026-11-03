"""Verifiable agent-revenue commitments (threat-assessment F4).

CapShare valuations and shareholder payouts depend on *how much an agent earned*. Until
now that figure was the hub's word. This module makes it **auditable without trusting the
hub**: each settlement period the hub commits a Merkle root over the period's paid-invoke
receipts; anyone can then verify an agent's claimed revenue is exactly the sum of receipts
*provably included* under that root.

The trust anchor is the **signed channel-debit receipt** — already replay-protected on-chain
(EIP-712 nonce + deadline + receiptId, see `contracts/evm/src/AIMarketEscrow.sol`). A receipt
*is* revenue; this layer just commits to the set and lets shareholders/auditors check it.

Leaves use the audited OpenZeppelin/Uniswap merkle-distributor encoding from
``acex_merkle`` (double-hashed, ABI-encoded, sorted-pair) so the same root can later be
posted and verified on-chain without re-deriving anything.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aimarket_hub.acex_merkle import keccak256, make_leaf, merkle_proof, merkle_root, verify


def agent_account(agent_id: str) -> str:
    """Map an agent identifier to a 20-byte account address for the leaf.

    Real EVM payout addresses pass through; anything else is hashed to a deterministic
    pseudo-address so off-chain agent ids commit cleanly (and identically every time).
    """
    a = (agent_id or "").strip()
    if a.startswith("0x") and len(a) == 42:
        return a.lower()
    return "0x" + keccak256(a.encode()).hex()[:40]


def to_e6(amount_usd: float) -> int:
    """USD → integer micro-USD (uint256-compatible, no float in the commitment)."""
    return int(round(max(0.0, float(amount_usd)) * 1_000_000))


@dataclass
class RevenueCommitment:
    """A period's revenue commitment: ordered leaves + Merkle root + per-agent index."""

    root: bytes
    leaves: list[bytes]
    rows: list[dict[str, Any]] = field(default_factory=list)  # [{index, agent, account, amount_e6, receipt_id}]

    @property
    def root_hex(self) -> str:
        return "0x" + self.root.hex()

    def total_e6(self, agent_id: str) -> int:
        acct = agent_account(agent_id)
        return sum(r["amount_e6"] for r in self.rows if r["account"] == acct)

    def indices_for(self, agent_id: str) -> list[int]:
        acct = agent_account(agent_id)
        return [r["index"] for r in self.rows if r["account"] == acct]


def commit_revenue(receipts: list[dict[str, Any]]) -> RevenueCommitment:
    """Build a Merkle commitment over paid-invoke receipts.

    Each receipt: ``{"agent": str, "amount_usd": float, "receipt_id": str}``. Order is
    preserved and becomes the leaf index (auditors re-derive the same tree from the same
    ordered receipt list).
    """
    rows: list[dict[str, Any]] = []
    leaves: list[bytes] = []
    for i, rc in enumerate(receipts):
        agent = str(rc.get("agent") or "")
        acct = agent_account(agent)
        amount_e6 = to_e6(rc.get("amount_usd") or 0)
        leaves.append(make_leaf(i, acct, amount_e6))
        rows.append(
            {
                "index": i,
                "agent": agent,
                "account": acct,
                "amount_e6": amount_e6,
                "receipt_id": str(rc.get("receipt_id") or ""),
            }
        )
    return RevenueCommitment(root=merkle_root(leaves), leaves=leaves, rows=rows)


def prove_receipt(commitment: RevenueCommitment, index: int) -> list[bytes]:
    """Inclusion proof for one receipt leaf."""
    return merkle_proof(commitment.leaves, index)


def verify_receipt(
    root: bytes, *, index: int, agent_id: str, amount_e6: int, proof: list[bytes]
) -> bool:
    """Verify a single receipt is committed under ``root`` for ``agent_id`` at ``amount_e6``."""
    leaf = make_leaf(index, agent_account(agent_id), int(amount_e6))
    return verify(proof, root, leaf)


def verify_agent_revenue(
    root: bytes,
    *,
    agent_id: str,
    claimed_total_e6: int,
    items: list[dict[str, Any]],
) -> bool:
    """Trustless revenue check for one agent.

    ``items`` = ``[{"index": int, "amount_e6": int, "proof": list[bytes]}, ...]`` — the
    receipts the claimant says make up the agent's revenue. Returns True only when **every**
    item is provably included under ``root`` for this agent, all indices are distinct (no
    double-counting), and the amounts sum to exactly ``claimed_total_e6``. The hub's word is
    never consulted — only the root and the proofs.
    """
    seen: set[int] = set()
    total = 0
    for it in items:
        idx = int(it.get("index", -1))
        if idx in seen:
            return False  # replayed leaf — would double-count revenue
        amt = int(it.get("amount_e6", 0))
        if not verify_receipt(root, index=idx, agent_id=agent_id, amount_e6=amt, proof=list(it.get("proof") or [])):
            return False
        seen.add(idx)
        total += amt
    return total == int(claimed_total_e6)
