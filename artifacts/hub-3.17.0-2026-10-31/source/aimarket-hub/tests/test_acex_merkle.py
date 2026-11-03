"""Tests for the pure-Python keccak256 + Merkle bridge (acex_merkle).

These verify the exact root/proof encoding that PulseDistributor.sol consumes,
so the off-chain → on-chain revenue bridge is correct without needing forge.
"""

from aimarket_hub.acex_merkle import (
    build_claimset,
    keccak256,
    make_leaf,
    merkle_proof,
    merkle_root,
    verify,
)

A = "0x" + "11" * 20
B = "0x" + "22" * 20
C = "0x" + "33" * 20


def test_keccak256_known_vectors():
    # Ethereum keccak256 (0x01 padding), not SHA3-256.
    assert keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert keccak256(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"


def test_single_leaf_root_is_leaf():
    leaf = make_leaf(0, A, 100)
    assert merkle_root([leaf]) == leaf
    assert verify([], merkle_root([leaf]), leaf)


def test_proofs_verify_and_tamper_fails():
    payouts = [
        {"account": A, "amount": 350_000},
        {"account": B, "amount": 150_000},
        {"account": C, "amount": 1},
    ]
    cs = build_claimset(payouts)
    root = bytes.fromhex(cs["merkle_root"][2:])
    assert cs["claim_count"] == 3
    assert cs["total"] == 500_001

    for cl in cs["claims"]:
        leaf = make_leaf(cl["index"], cl["account"], cl["amount"])
        proof = [bytes.fromhex(p[2:]) for p in cl["proof"]]
        assert verify(proof, root, leaf)
        # Tampered amount must not verify against the same proof.
        assert not verify(proof, root, make_leaf(cl["index"], cl["account"], cl["amount"] + 1))


def test_build_claimset_drops_zero_amounts():
    cs = build_claimset([{"account": A, "amount": 0}, {"account": B, "amount": 5}])
    assert cs["claim_count"] == 1
    assert cs["claims"][0]["account"] == B


def test_indexing_is_deterministic_by_account():
    cs1 = build_claimset([{"account": B, "amount": 2}, {"account": A, "amount": 1}])
    cs2 = build_claimset([{"account": A, "amount": 1}, {"account": B, "amount": 2}])
    assert cs1["merkle_root"] == cs2["merkle_root"]
    # A (0x11..) sorts before B (0x22..) → index 0.
    assert cs1["claims"][0]["account"] == A
