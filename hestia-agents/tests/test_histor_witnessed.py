"""histor.witnessed@v1 against answers HISTOR really gave, and against a log that lies.

`histor_witnessed_vectors.json` was recorded from https://histor.modelmarket.dev on 2026-11-20: the
signed /check answer and the server record of https://modelmarket.dev/mcp, the checkpoint at size
2 836 615 (the log's signature and seven witness cosignatures), and one of the server's labels under
it with its inclusion proof. The handler recomputes the leaf from the label with its own RFC 8785,
walks the proof to the root and checks every signature on the note under the keys it pins.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hestia_agents.manifests import AGENTS, deploy_body, handler_source

V = json.loads(
    (Path(__file__).parent / "histor_witnessed_vectors.json").read_text(encoding="utf-8")
)


class Reply:
    def __init__(self, status=200, body=None, text=None):
        self.status, self.error, self.headers = status, None, {}
        self.text = text if text is not None else json.dumps(body)

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.text)


def load(v=V, *, checkpoint=None):
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        asked.append((method, url))
        path = url.split("histor.modelmarket.dev", 1)[1]
        if path.startswith("/api/v1/check"):
            return Reply(body=v["check"])
        if path.startswith("/api/v1/changes?watch="):
            return Reply(body=v["feed"])
        if path.startswith("/api/v1/servers/"):
            return Reply(body=v["detail"])
        if path == "/api/v1/log/checkpoint/cosigned":
            return Reply(text=checkpoint if checkpoint is not None else v["checkpoint"])
        if path.endswith(f"/proof?tree_size={v['size']}"):
            return Reply(body=v["proof"])
        if path.startswith("/api/v1/labels/"):
            return Reply(body=v["label"])
        return Reply(status=404, body={})

    namespace = {"fetch": fetch}
    exec(compile(handler_source("histor-witnessed"), "histor-witnessed", "exec"), namespace)  # noqa: S102 — our own source
    return namespace, asked


def run(v=V, **kw):
    namespace, asked = load(v, **kw)
    return namespace["handle"]({"endpoint": v["endpoint"], "tool_set_digest": v["digest"]}), asked


def test_a_real_label_is_proven_under_a_head_seven_witnesses_signed() -> None:
    out, asked = run()
    assert out["verdict"] == "witnessed" and out["witnessed"] is True, out
    assert all(c["ok"] for c in out["checks"])
    assert len(out["witnesses"]) == 7
    assert {w["witness"] for w in out["witnesses"]} == {
        "Mullvad (stagemole)",
        "Markovian Protocol",
        "TrustFabric",
        "CrawlCheck",
        "GDB Security",
        "Geomys (Navigli)",
        "IPng (krabbel)",
    }
    assert (
        out["label"]["id"] == V["label_id"]
        and out["label"]["leaf_index"] == V["proof"]["leafIndex"]
    )
    assert (
        out["checkpoint"]["tree_size"] == V["size"] and out["checkpoint"]["log_signature"] is True
    )
    assert len(asked) == 5 and all(method == "GET" for method, _ in asked)


def test_the_leaf_is_the_hash_of_the_label_as_rfc_8785_writes_it() -> None:
    namespace, _ = load()
    leaf = namespace["hashlib"].sha256(b"\x00" + namespace["jcs"](V["label"]).encode()).digest()
    size, root, _, _ = namespace["check_note"](V["checkpoint"])
    path = [bytes.fromhex(h) for h in V["proof"]["inclusionProof"]]
    assert namespace["inclusion_root"](leaf, V["proof"]["leafIndex"], size, path) == root
    # one changed character in the label and it is no longer in the tree
    changed = copy.deepcopy(V["label"])
    changed["validFrom"] = changed["validFrom"].replace("Z", ".0Z")
    other = namespace["hashlib"].sha256(b"\x00" + namespace["jcs"](changed).encode()).digest()
    assert namespace["inclusion_root"](other, V["proof"]["leafIndex"], size, path) != root


def test_a_tampered_label_or_proof_fails() -> None:
    bad = copy.deepcopy(V)
    bad["label"]["credentialSubject"]["verdict"] = (
        "pass" if V["label"]["credentialSubject"]["verdict"] != "pass" else "fail"
    )
    out, _ = run(bad)
    assert out["verdict"] == "proof_failed" and [
        c["check"] for c in out["checks"] if not c["ok"]
    ] == ["inclusion"]
    bad = copy.deepcopy(V)
    bad["proof"]["inclusionProof"][3] = "00" * 32
    assert run(bad)[0]["verdict"] == "proof_failed"


def test_a_label_for_another_set_fails_the_binding() -> None:
    bad = copy.deepcopy(V)
    bad["digest"] = "sha256-" + "A" * 43 + "="
    bad["check"]["query"]["toolSetDigest"] = bad["digest"]
    bad["detail"]["timeline"][0]["toolSetDigest"] = bad["digest"]  # so the label is still picked
    out, _ = run(bad)
    assert "label_names_this_set" in [c["check"] for c in out["checks"] if not c["ok"]]


def test_forged_signatures_on_the_note_are_not_counted() -> None:
    lines = V["checkpoint"].split("\n")
    forged = "\n".join(line[:-8] + "AAAAAAA=" if line.startswith("— ") else line for line in lines)
    out, _ = run(checkpoint=forged)
    assert out["verdict"] == "proof_failed"
    failed = [c["check"] for c in out["checks"] if not c["ok"]]
    assert "log_signature" in failed and "witnesses" in failed
    log_only = "\n".join(
        line for line in lines if not line.startswith("— ") or "histor.modelmarket.dev/log" in line
    )
    out, _ = run(checkpoint=log_only)
    assert [c["check"] for c in out["checks"] if not c["ok"]] == ["witnesses"]


def test_a_set_histor_never_saw_is_not_recorded() -> None:
    other = copy.deepcopy(V)
    other["check"]["match"] = "different"
    out, asked = run(other)
    assert out["verdict"] == "not_recorded" and out["witnessed"] is False and len(asked) == 1


def test_a_label_newer_than_the_witnessed_head_says_to_ask_again() -> None:
    newer = copy.deepcopy(V)
    newer["detail"]["labels"] = [
        lab for lab in newer["detail"]["labels"] if lab["leaf_index"] > V["size"]
    ]
    newer["detail"]["changes"] = []
    newer["feed"] = {"changes": []}
    out, _ = run(newer)
    assert out["verdict"] == "no_label_under_witnessed_head"


def test_input_is_checked_and_tools_go_to_histor_by_post() -> None:
    namespace, asked = load()
    for payload in (
        {},
        {"endpoint": "https://x/mcp"},
        {"endpoint": "https://x/mcp", "tool_set_digest": "md5-x"},
    ):
        with pytest.raises(ValueError):
            namespace["handle"](payload)
    namespace["handle"]({"endpoint": V["endpoint"], "tools": [{"name": "a"}]})
    assert asked[-5][0] == "POST" and asked[-5][1].endswith("/api/v1/check")


def test_the_manifest_reaches_histor_only() -> None:
    body = deploy_body("histor-witnessed")
    assert body["egress_hosts"] == ["histor.modelmarket.dev"] and "egress_input_fields" not in body
    assert AGENTS["histor-witnessed"]["capability_id"] == "histor.witnessed@v1"


def test_without_a_cosigned_head_it_proves_against_the_log_alone_and_says_logged() -> None:
    v = copy.deepcopy(V)
    log_only = "\n".join(
        line
        for line in V["checkpoint"].split("\n")
        if not line.startswith("\u2014 ") or "histor.modelmarket.dev/log" in line
    )
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        asked.append(url)
        path = url.split("histor.modelmarket.dev", 1)[1]
        if path == "/api/v1/log/checkpoint/cosigned":
            return Reply(status=404, body={"detail": "Not Found"})
        if path == "/checkpoint":
            return Reply(text=log_only)
        if path.startswith("/api/v1/check"):
            return Reply(body=v["check"])
        if path.startswith("/api/v1/servers/"):
            return Reply(body=v["detail"])
        if path.endswith(f"/proof?tree_size={v['size']}"):
            return Reply(body=v["proof"])
        return Reply(body=v["label"])

    namespace = {"fetch": fetch}
    exec(compile(handler_source("histor-witnessed"), "histor-witnessed", "exec"), namespace)  # noqa: S102
    out = namespace["handle"]({"endpoint": v["endpoint"], "tool_set_digest": v["digest"]})
    assert out["verdict"] == "logged" and out["witnessed"] is False and out["witnesses"] == []
    assert all(c["ok"] for c in out["checks"]) and "log alone" in out["checks"][-1]["detail"]
