"""Pure-Python keccak256 + Merkle tree for the ACEX on-chain revenue bridge.

No third-party deps (no web3 / eth-hash) so it runs anywhere the hub runs.

This produces the exact Merkle root + proofs that the on-chain
``PulseDistributor.sol`` verifies via OpenZeppelin ``MerkleProof``:

  leaf       = keccak256(keccak256(abi.encode(uint256 index, address account, uint256 amount)))
  inner node = keccak256(sorted(left, right))      # OZ commutative hashing

Amounts are token base units. Since the off-chain ledger stores micro-USD
(1e6) and USDC has 6 decimals, micro-USD maps 1:1 to USDC base units.
"""

from __future__ import annotations

from typing import Any

# ── Keccak-256 (Ethereum variant: 0x01 padding, NOT SHA3's 0x06) ────────────

_RHO = [
    1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
    27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
]
_PI = [
    10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
    15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
]
_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_MASK = (1 << 64) - 1


def _rotl(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(state: list[int]) -> None:
    for rc in _RC:
        # θ
        c = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(0, 25, 5):
                state[x + y] ^= d[x]
        # ρ and π
        t = state[1]
        for i in range(24):
            j = _PI[i]
            state[j], t = _rotl(t, _RHO[i]), state[j]
        # χ
        for y in range(0, 25, 5):
            row = state[y:y + 5]
            for x in range(5):
                state[y + x] = row[x] ^ ((~row[(x + 1) % 5]) & row[(x + 2) % 5])
        # ι
        state[0] ^= rc


def keccak256(data: bytes) -> bytes:
    rate = 136  # 1088-bit rate for 256-bit output
    state = [0] * 25
    # Absorb full blocks with 0x01..0x80 (Keccak) padding.
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80

    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[i * 8:i * 8 + 8], "little")
        _keccak_f(state)

    out = b"".join(state[i].to_bytes(8, "little") for i in range(4))  # 4*64 = 256 bits
    return out[:32]


# ── abi.encodePacked + leaf/tree helpers ────────────────────────────────────

def _u256(n: int) -> bytes:
    if n < 0 or n >> 256:
        raise ValueError("uint256 out of range")
    return n.to_bytes(32, "big")


def _address(addr: str) -> bytes:
    a = addr.lower()
    if a.startswith("0x"):
        a = a[2:]
    if len(a) != 40:
        raise ValueError(f"bad address: {addr}")
    return bytes.fromhex(a)


def make_leaf(index: int, account: str, amount: int) -> bytes:
    """leaf = keccak256(keccak256(abi.encode(uint256 index, address account, uint256 amount))).

    Double-hashed, ABI-encoded (not packed) leaves — the OpenZeppelin / Uniswap
    merkle-distributor canon. The double hash makes a leaf preimage impossible to
    reinterpret as an internal node (second-preimage hardening); abi.encode pads
    every field to 32 bytes so there is no ambiguity at field boundaries.
    """
    inner = _u256(index) + (b"\x00" * 12 + _address(account)) + _u256(amount)
    return keccak256(keccak256(inner))


def _hash_pair(a: bytes, b: bytes) -> bytes:
    return keccak256(a + b) if a <= b else keccak256(b + a)


def merkle_root(leaves: list[bytes]) -> bytes:
    if not leaves:
        return b"\x00" * 32
    layer = list(leaves)
    while len(layer) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                nxt.append(_hash_pair(layer[i], layer[i + 1]))
            else:
                nxt.append(layer[i])  # odd node promoted
        layer = nxt
    return layer[0]


def merkle_proof(leaves: list[bytes], index: int) -> list[bytes]:
    if index < 0 or index >= len(leaves):
        raise IndexError("leaf index out of range")
    proof: list[bytes] = []
    layer = list(leaves)
    idx = index
    while len(layer) > 1:
        nxt: list[bytes] = []
        for i in range(0, len(layer), 2):
            if i + 1 < len(layer):
                if i == idx or i + 1 == idx:
                    sibling = layer[i + 1] if i == idx else layer[i]
                    proof.append(sibling)
                nxt.append(_hash_pair(layer[i], layer[i + 1]))
            else:
                nxt.append(layer[i])
        idx //= 2
        layer = nxt
    return proof


def verify(proof: list[bytes], root: bytes, leaf: bytes) -> bool:
    """Mirror of OpenZeppelin MerkleProof.verify (commutative/sorted hashing)."""
    h = leaf
    for p in proof:
        h = _hash_pair(h, p)
    return h == root


def build_claimset(payouts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a Merkle claim set from {account, amount} payouts (amount in base units).

    ``payouts`` items must have ``account`` (0x address) and ``amount`` (int units).
    Zero-amount entries are dropped. Returns root + per-claim proofs, ready to feed
    ``PulseDistributor.postEpoch`` (root, total) and holder ``claim(...)`` calls.
    """
    items = [(p["account"], int(p["amount"])) for p in payouts if int(p["amount"]) > 0]
    # Deterministic ordering by (account) so index assignment is reproducible.
    items.sort(key=lambda x: x[0].lower())
    leaves = [make_leaf(i, acct, amt) for i, (acct, amt) in enumerate(items)]
    root = merkle_root(leaves)
    claims = []
    for i, (acct, amt) in enumerate(items):
        claims.append({
            "index": i,
            "account": acct,
            "amount": amt,
            "leaf": "0x" + leaves[i].hex(),
            "proof": ["0x" + p.hex() for p in merkle_proof(leaves, i)],
        })
    return {
        "merkle_root": "0x" + root.hex(),
        "total": sum(a for _, a in items),
        "claim_count": len(items),
        "claims": claims,
    }
