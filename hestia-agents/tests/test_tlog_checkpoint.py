"""tlog.checkpoint.verify@v1 against real checkpoints.

`tlog_checkpoint_vectors.json` (recorded 2026-11-20): the Go checksum database's latest checkpoint
(https://sum.golang.org/latest, verifier key from the Go source), and HISTOR's checkpoint at size
2 836 615 with seven witness cosignatures, a label's RFC 9162 inclusion proof in it, a newer
HISTOR checkpoint (3 000 827) and HISTOR's consistency proof between the two.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from hestia_agents.manifests import deploy_body, handler_source

V = json.loads((Path(__file__).parent / "tlog_checkpoint_vectors.json").read_text(encoding="utf-8"))
H = V["histor"]
WITNESSES = list(H["witness_keys"].values())


def load():
    namespace: dict = {}
    exec(compile(handler_source("tlog-checkpoint"), "tlog-checkpoint", "exec"), namespace)  # noqa: S102 — our own source
    return namespace


NS = load()
handle = NS["handle"]


def test_go_checksum_database_checkpoint_verifies() -> None:
    out = handle({"checkpoint": V["go"]["checkpoint"], "log_key": V["go"]["log_key"]})
    assert out["verdict"] == "valid" and out["origin"] == "go.sum database tree"
    assert out["log_signature"]["ok"] is True and out["witnesses"]["quorum"] == 0
    assert any("differs from the checkpoint origin" in w for w in out.get("warnings", []))
    forged = V["go"]["checkpoint"].replace("\n" + str(out["size"]) + "\n", "\n" + str(out["size"] + 1) + "\n")
    bad = handle({"checkpoint": forged, "log_key": V["go"]["log_key"]})
    assert bad["verdict"] == "invalid" and bad["log_signature"]["ok"] is False


def test_histor_checkpoint_seven_witnesses_and_an_inclusion_proof() -> None:
    out = handle({"checkpoint": H["cosigned"], "log_key": H["log_key"], "witness_keys": WITNESSES,
                  "inclusion": {"leaf_index": H["leaf_index"], "leaf": H["leaf"], "proof": H["inclusion_proof"]}})
    assert out["verdict"] == "valid", out["problems"]
    assert out["size"] == 2836615 and out["witnesses"]["cosigned"] == 7 and out["witnesses"]["met"]
    assert all(isinstance(w["cosigned_at"], int) for w in out["witnesses"]["valid"])
    assert out["inclusion"]["ok"] is True
    wrong_leaf = handle({"checkpoint": H["cosigned"], "log_key": H["log_key"],
                         "inclusion": {"leaf_index": H["leaf_index"], "leaf": H["leaf"] + " ", "proof": H["inclusion_proof"]}})
    assert wrong_leaf["verdict"] == "invalid" and "not in this tree" in wrong_leaf["inclusion"]["detail"]
    wrong_index = handle({"checkpoint": H["cosigned"], "log_key": H["log_key"],
                          "inclusion": {"leaf_index": H["leaf_index"] + 1, "leaf": H["leaf"], "proof": H["inclusion_proof"]}})
    assert wrong_index["inclusion"]["ok"] is False


def test_quorum_now_and_a_forged_cosignature() -> None:
    base = {"checkpoint": H["cosigned"], "log_key": H["log_key"], "witness_keys": WITNESSES}
    assert handle({**base, "witness_quorum": 5})["verdict"] == "valid"
    # The newer checkpoint carries the log's signature only: a quorum of 1 is not met.
    newer = handle({**base, "checkpoint": H["newer"], "witness_quorum": 1})
    assert newer["verdict"] == "invalid" and newer["witnesses"]["cosigned"] == 0
    first = handle(base)["witnesses"]["valid"][0]["cosigned_at"]
    early = handle({**base, "now": first - 3600})
    assert early["verdict"] == "invalid" and "cosigned in the future" in early["witnesses"]["missing_or_invalid"][0]["problem"]
    lines = H["cosigned"].split("\n")
    sig_line = next(i for i, line in enumerate(lines) if line.startswith("— crawlcheck.io"))
    name, b64 = lines[sig_line].rsplit(" ", 1)
    raw = bytearray(base64.b64decode(b64))
    raw[20] ^= 1
    lines[sig_line] = name + " " + base64.b64encode(bytes(raw)).decode()
    forged = handle({**base, "checkpoint": "\n".join(lines)})
    assert forged["witnesses"]["cosigned"] == 6 and forged["verdict"] == "invalid"
    assert [w["name"] for w in forged["witnesses"]["missing_or_invalid"]] == ["crawlcheck.io/witness"]


def test_consistency_from_the_cosigned_checkpoint_to_a_newer_one() -> None:
    args = {"checkpoint": H["newer"], "log_key": H["log_key"],
            "consistency": {"old_checkpoint": H["cosigned"], "proof": H["consistency_proof"]}}
    out = handle(args)
    assert out["verdict"] == "valid" and out["consistency"]["ok"] is True
    assert out["consistency"]["old_size"] == 2836615 and out["size"] == 3000827
    short = handle({**args, "consistency": {"old_checkpoint": H["cosigned"], "proof": H["consistency_proof"][:-1]}})
    assert short["verdict"] == "invalid"
    swapped = list(H["consistency_proof"])
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert handle({**args, "consistency": {"old_checkpoint": H["cosigned"], "proof": swapped}})["verdict"] == "invalid"
    old_root = handle({"checkpoint": H["cosigned"], "log_key": H["log_key"]})["root_hash"]
    by_value = handle({**args, "consistency": {"old_size": 2836615, "old_root": old_root, "proof": H["consistency_proof"]}})
    assert by_value["consistency"]["ok"] is True


def test_small_trees_built_here() -> None:
    import hashlib
    leaves = [hashlib.sha256(b"\x00" + bytes([i])).digest() for i in range(7)]
    node = NS["_node"]

    def mth(h):
        if len(h) == 1:
            return h[0]
        k = 1
        while k * 2 < len(h):
            k *= 2
        return node(mth(h[:k]), mth(h[k:]))

    # inclusion of leaf 5 in a 7-leaf tree, RFC 9162 path: leaf 4, leaf 6, MTH(0..4)
    path = [leaves[4], leaves[6], mth(leaves[:4])]
    assert NS["inclusion_root"](leaves[5], 5, 7, path) == mth(leaves)
    # consistency 3 -> 7: RFC 9162 2.1.4.1 example shape
    proof = [leaves[2], leaves[3], node(leaves[0], leaves[1]), mth(leaves[4:])]
    assert NS["consistent"](3, 7, proof, mth(leaves[:3]), mth(leaves))[0] is True
    assert NS["consistent"](4, 7, [mth(leaves[4:])], mth(leaves[:4]), mth(leaves))[0] is True
    assert NS["consistent"](7, 7, [], mth(leaves), mth(leaves))[0] is True
    assert NS["consistent"](3, 7, proof, mth(leaves[:3]), mth(leaves[:6]))[0] is False


def test_input_mistakes() -> None:
    go = V["go"]
    for bad, match in (
        ({"checkpoint": go["checkpoint"], "log_key": "nonsense"}, "verifier key"),
        ({"checkpoint": go["checkpoint"], "log_key": go["log_key"].replace("033de0ae", "033de0af")}, "key hash"),
        ({"checkpoint": go["checkpoint"].replace("\n\n", "\n"), "log_key": go["log_key"]}, "no blank line"),
        ({"checkpoint": go["checkpoint"].replace("— ", "- "), "log_key": go["log_key"]}, "em dash"),
        ({"checkpoint": go["checkpoint"], "log_key": go["log_key"], "witness_keys": WITNESSES[:2], "witness_quorum": 3}, "larger than"),
        ({"checkpoint": go["checkpoint"], "log_key": go["log_key"], "witness_keys": [WITNESSES[0], WITNESSES[0]]}, "twice"),
        ({"checkpoint": go["checkpoint"], "log_key": WITNESSES[0]}, "not a cosigner key"),
    ):
        with pytest.raises(ValueError, match=match):
            handle(bad)


def test_deterministic_and_no_egress() -> None:
    args = {"checkpoint": H["cosigned"], "log_key": H["log_key"], "witness_keys": WITNESSES}
    assert json.dumps(handle(args)) == json.dumps(load()["handle"](args))
    body = deploy_body("tlog-checkpoint")
    assert not body.get("egress_hosts") and body["capability"]["price_per_call_usd"] == 0
