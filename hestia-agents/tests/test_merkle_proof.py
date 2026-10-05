"""merkle.proof@v1 against outside answers, not against itself.

Known answers: the Certificate Transparency test-vector roots (RFC 6962 data used by
every CT implementation), the root printed in @openzeppelin/merkle-tree's own README,
and leaf hashes from eth-abi. Then the two implementations in this repository that
already secure real things — HISTOR's log (RFC 9162) and the ACEX distributor's tree —
are run side by side with the handler over every index of many tree sizes.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import pytest

from hestia_agents.manifests import handler_source

MONOREPO = Path(__file__).resolve().parent.parent.parent

CT_LEAVES = ["", "00", "10", "2021", "3031", "40414243", "5051525354555657",
             "606162636465666768696a6b6c6d6e6f"]
CT_ROOTS = [
    "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
]
OZ_README_VALUES = [
    ["0x1111111111111111111111111111111111111111", "5000000000000000000"],
    ["0x2222222222222222222222222222222222222222", "2500000000000000000"],
]
OZ_README_ROOT = "0xd4dee0beab2d53f2cc83e567171bd2820e49898130a22622b10ead383e90bd77"
# keccak256(keccak256(eth_abi.encode(types, values))), computed with eth-abi 5.
ABI_LEAVES = [
    (["address", "uint256"], ["0x1111111111111111111111111111111111111111", 5000000000000000000],
     "0xeb02c421cfa48976e66dfb29120745909ea3a0f843456c263cf8f1253483e283"),
    (["uint256", "address", "uint256"], [0, "0x9d24D267Cf8D9A8b9Ed104b4856cDe8830C266eF", 31000],
     "0x35d1da0ea638f164ab20ba29d0b3b292cb178316654e6504af932776c11db638"),
    (["string", "bool", "int8", "bytes4"], ["héllo, Merkle", True, -5, "0xdeadbeef"],
     "0xe45ef109956126f64b6e2ceaff29e30a8e102c4cdf7ca9cf5df60d5183a86cc2"),
    (["bytes", "uint16", "bytes32"], ["0x0102030405", 65535, "0x" + "ab" * 32],
     "0x841a99c32f7d7d33d62eb8e9ad09ee1505d36721b5bf259aa646d07007c41140"),
]


@pytest.fixture(scope="module")
def ns():
    namespace: dict = {}
    exec(compile(handler_source("merkle-proof"), "merkle-proof", "exec"), namespace)  # noqa: S102
    return namespace


@pytest.fixture(scope="module")
def handle(ns):
    return ns["handle"]


def _import_sibling(path: Path, module: str):
    if not path.is_dir():
        pytest.skip(f"{path.name} is not beside this package")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    return pytest.importorskip(module)


# ------------------------------------------------------------------ known answers


def test_keccak256_known_answers(ns) -> None:
    keccak = ns["keccak256"]
    assert keccak(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    abc = "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    assert keccak(b"abc").hex() == abc
    # Across the 136-byte rate boundary, where a padding bug would show.
    for size in (135, 136, 137, 272):
        assert len(keccak(b"\x61" * size)) == 32


@pytest.mark.parametrize("n", range(1, 9))
def test_certificate_transparency_vector_roots(handle, n: int) -> None:
    out = handle({"op": "root", "leaves": CT_LEAVES[:n]})
    assert out == {"scheme": "rfc6962", "tree_size": n, "root": CT_ROOTS[n - 1]}


def test_empty_rfc6962_tree_is_the_hash_of_nothing(handle) -> None:
    assert handle({"op": "root", "leaves": []})["root"] == hashlib.sha256(b"").hexdigest()


def test_openzeppelin_readme_root(handle) -> None:
    out = handle({"op": "root", "scheme": "openzeppelin", "types": ["address", "uint256"],
                  "values": OZ_README_VALUES})
    assert out["root"] == OZ_README_ROOT


@pytest.mark.parametrize(("types", "values", "leaf"), ABI_LEAVES)
def test_abi_leaf_hashes_match_eth_abi(handle, types, values, leaf) -> None:
    out = handle({"op": "prove", "scheme": "openzeppelin", "types": types, "values": [values],
                  "index": 0})
    assert out["leaf_hash"] == leaf
    assert out["root"] == leaf and out["proof"] == []


# ------------------------------------------------------------------ RFC 6962 vs HISTOR


def _hex_leaves(n: int) -> list[str]:
    return [hashlib.sha256(b"leaf %d" % i).hexdigest()[: 2 * (i % 7)] for i in range(n)]


def test_rfc6962_matches_histor_for_every_index(handle) -> None:
    merkle = _import_sibling(MONOREPO / "histor", "histor.merkle")
    for n in range(1, 41):
        leaves = _hex_leaves(n)
        hashes = [merkle.leaf_hash(bytes.fromhex(v)) for v in leaves]
        stored = {}

        def read(level, index, hashes=hashes, stored=stored):
            key = (level, index)
            if key not in stored:
                width = 1 << level
                part = hashes[index * width:(index + 1) * width]
                while len(part) > 1:
                    part = [merkle.node_hash(part[i], part[i + 1]) for i in range(0, len(part), 2)]
                stored[key] = part[0]
            return stored[key]

        root = merkle.tree_root(n, read).hex()
        assert handle({"op": "root", "leaves": leaves})["root"] == root
        for index in range(n):
            proof = handle({"op": "prove", "leaves": leaves, "index": index})
            assert proof["proof"] == [h.hex() for h in merkle.inclusion_proof(index, n, read)]
            checked = handle({"op": "verify", "leaf": leaves[index], "index": index,
                              "tree_size": n, "proof": proof["proof"], "root": root})
            assert checked["valid"] is True and checked["computed_root"] == root
        for old in range(1, n + 1):
            cons = handle({"op": "consistency", "leaves": leaves, "old_size": old})
            assert cons["proof"] == [h.hex() for h in merkle.consistency_proof(old, n, read)]
            ok = handle({"op": "verify_consistency", "old_size": old, "new_size": n,
                         "old_root": cons["old_root"], "new_root": cons["new_root"],
                         "proof": cons["proof"]})
            assert ok["valid"] is True, (old, n, ok)


def test_rfc6962_rejects_a_tampered_proof_and_a_rewritten_log(handle) -> None:
    leaves = _hex_leaves(13)
    proof = handle({"op": "prove", "leaves": leaves, "index": 5})
    bad = list(proof["proof"])
    bad[1] = "00" * 32
    out = handle({"op": "verify", "leaf": leaves[5], "index": 5, "tree_size": 13, "proof": bad,
                  "root": proof["root"]})
    assert out["valid"] is False and out["reason"] == "proof leads to a different root"
    short = handle({"op": "verify", "leaf": leaves[5], "index": 5, "tree_size": 13,
                    "proof": proof["proof"][:-1], "root": proof["root"]})
    assert short["valid"] is False and short["computed_root"] is None
    # The same 9 first leaves, then a different history: not an extension.
    cons = handle({"op": "consistency", "leaves": leaves, "old_size": 9})
    rewritten = handle({"op": "root", "leaves": leaves[:8] + ["ff"]})["root"]
    out = handle({"op": "verify_consistency", "old_size": 9, "new_size": 13,
                  "old_root": rewritten, "new_root": cons["new_root"], "proof": cons["proof"]})
    assert out["valid"] is False and "old root" in out["reason"]


def test_rfc6962_json_leaves_are_jcs_like_histor_labels(handle) -> None:
    label = {"subject": "mcp:example", "b": [1, 2], "a": "é"}
    canonical = '{"a":"é","b":[1,2],"subject":"mcp:example"}'.encode()
    out = handle({"op": "prove", "leaves": [label], "leaf_format": "json", "index": 0})
    assert out["leaf_hash"] == hashlib.sha256(b"\x00" + canonical).hexdigest()
    with pytest.raises(ValueError, match="not an integer"):
        handle({"op": "root", "leaves": [{"x": 1.5}], "leaf_format": "json"})


def test_rfc6962_utf8_leaves_and_leaf_hash_verify(handle) -> None:
    out = handle({"op": "prove", "leaves": ["a", "b", "c"], "leaf_format": "utf8", "index": 2})
    checked = handle({"op": "verify", "leaf_hash": out["leaf_hash"], "index": 2, "tree_size": 3,
                      "proof": out["proof"], "root": "0x" + out["root"]})
    assert checked["valid"] is True


# ------------------------------------------------------------------ OpenZeppelin


def _bytes32_leaves(n: int) -> list[str]:
    return ["0x" + hashlib.sha256(b"oz %d" % i).hexdigest() for i in range(n)]


def test_layers_layout_matches_the_acex_distributor(handle) -> None:
    acex = _import_sibling(MONOREPO / "aimarket-hub", "aimarket_hub.acex_merkle")
    for n in range(1, 34):
        leaves = _bytes32_leaves(n)
        raw = [bytes.fromhex(v[2:]) for v in leaves]
        root = "0x" + acex.merkle_root(raw).hex()
        assert handle({"op": "root", "scheme": "openzeppelin", "layout": "layers",
                       "leaves": leaves})["root"] == root
        for index in range(n):
            out = handle({"op": "prove", "scheme": "openzeppelin", "layout": "layers",
                          "leaves": leaves, "index": index})
            assert out["proof"] == ["0x" + p.hex() for p in acex.merkle_proof(raw, index)]


@pytest.mark.parametrize("sort_leaves", [True, False])
def test_standard_layout_proves_every_leaf(handle, sort_leaves: bool) -> None:
    for n in range(1, 34):
        leaves = _bytes32_leaves(n)
        root = handle({"op": "root", "scheme": "openzeppelin", "leaves": leaves,
                       "sort_leaves": sort_leaves})["root"]
        for index in range(n):
            out = handle({"op": "prove", "scheme": "openzeppelin", "leaves": leaves,
                          "index": index, "sort_leaves": sort_leaves})
            assert out["root"] == root
            checked = handle({"op": "verify", "scheme": "openzeppelin", "leaf": leaves[index],
                              "proof": out["proof"], "root": root})
            assert checked["valid"] is True


def test_typed_verify_and_a_wrong_amount(handle) -> None:
    out = handle({"op": "prove", "scheme": "openzeppelin", "types": ["address", "uint256"],
                  "values": OZ_README_VALUES, "index": 1})
    ok = handle({"op": "verify", "scheme": "openzeppelin", "types": ["address", "uint256"],
                 "value": OZ_README_VALUES[1], "proof": out["proof"], "root": OZ_README_ROOT})
    assert ok["valid"] is True
    inflated = handle({"op": "verify", "scheme": "openzeppelin", "types": ["address", "uint256"],
                       "value": [OZ_README_VALUES[1][0], "2500000000000000001"],
                       "proof": out["proof"], "root": OZ_README_ROOT})
    assert inflated["valid"] is False


def test_eip55_checksum_is_enforced_on_mixed_case(handle) -> None:
    good = "0x9d24D267Cf8D9A8b9Ed104b4856cDe8830C266eF"
    bad = "0x9d24D267Cf8D9A8b9Ed104b4856cDe8830C266Ef"
    handle({"op": "root", "scheme": "openzeppelin", "types": ["address"], "values": [[good]]})
    handle({"op": "root", "scheme": "openzeppelin", "types": ["address"],
            "values": [[good.lower()]]})
    with pytest.raises(ValueError, match="EIP-55"):
        handle({"op": "root", "scheme": "openzeppelin", "types": ["address"], "values": [[bad]]})


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"op": "nope"}, "op must be"),
        ({"op": "root", "scheme": "sha1"}, "scheme must be"),
        ({"op": "root", "leaves": ["zz"]}, "not hex"),
        ({"op": "root", "leaves": ["abc"]}, "odd number"),
        ({"op": "prove", "leaves": ["00"], "index": 1}, "outside"),
        ({"op": "prove", "leaves": ["00"], "index": True}, "non-negative integer"),
        ({"op": "verify", "index": 0, "tree_size": 1, "proof": [], "root": "00"}, "32 bytes"),
        ({"op": "consistency", "leaves": ["00"], "old_size": 2}, "old_size"),
        ({"op": "consistency", "scheme": "openzeppelin", "leaves": []}, "no consistency"),
        ({"op": "root", "scheme": "openzeppelin", "leaves": []}, "at least one leaf"),
        ({"op": "root", "scheme": "openzeppelin", "types": ["uint8"], "values": [[256]]}, "fit"),
        ({"op": "root", "scheme": "openzeppelin", "types": ["uint256"], "values": [[1.5]]},
         "integer"),
        ({"op": "root", "scheme": "openzeppelin", "types": ["tuple"], "values": [[1]]},
         "unsupported ABI type"),
        ({"op": "root", "scheme": "openzeppelin", "layout": "flat", "leaves": []}, "layout"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)


def test_limits(handle, ns) -> None:
    with pytest.raises(ValueError, match="at most"):
        handle({"op": "root", "scheme": "openzeppelin",
                "leaves": ["0x" + "00" * 32] * (ns["MAX_OZ_LEAVES"] + 1)})
    with pytest.raises(ValueError, match="longer than"):
        handle({"op": "verify", "scheme": "openzeppelin", "leaf": "0x" + "00" * 32,
                "proof": ["0x" + "00" * 32] * (ns["MAX_PROOF"] + 1), "root": "0x" + "00" * 32})


def test_the_largest_typed_tree_fits_the_call_budget(handle, ns) -> None:
    values = [["0x" + ("%040x" % (i + 1)), i * 1000] for i in range(ns["MAX_OZ_LEAVES"])]
    started = time.perf_counter()
    out = handle({"op": "prove", "scheme": "openzeppelin", "types": ["address", "uint256"],
                  "values": values, "index": 777})
    elapsed = time.perf_counter() - started
    assert len(out["proof"]) == 10
    # The hearth gives a call 10 s; a sandboxed interpreter may run this a few times slower.
    assert elapsed < 3.0, elapsed


def test_answers_are_reproducible(handle) -> None:
    payload = {"op": "prove", "leaves": _hex_leaves(9), "index": 4}
    assert handle(payload) == handle(payload)
