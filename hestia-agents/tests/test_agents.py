"""The three agents must pass HESTIA's AST admission and be exactly reproducible.

A handler that is not deterministic makes its own Ed25519 receipt worthless, so
determinism is asserted here rather than assumed.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from hestia_agents.manifests import AGENTS, AGENTS_DIR, deploy_body, handler_source

NAMES = sorted(AGENTS)


def load(name: str):
    """Execute a handler in a bare namespace, after the hearth's own admission."""
    source = handler_source(name)
    namespace: dict = {}
    exec(compile(source, name, "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"]


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("name", NAMES)
def test_handler_passes_hestia_admission(name: str, admit) -> None:
    admit(handler_source(name))


@pytest.mark.parametrize("name", NAMES)
def test_handler_fits_the_template_field(name: str) -> None:
    # TemplateSource.handler is capped at 32_000 characters; a handler that
    # outgrows it has to become a pinned image instead.
    assert len(handler_source(name)) < 32_000


@pytest.mark.parametrize("name", NAMES)
def test_committed_manifest_matches_the_handler(name: str) -> None:
    on_disk = json.loads((AGENTS_DIR / name / "deploy.json").read_text(encoding="utf-8"))
    assert on_disk == deploy_body(name)


@pytest.mark.parametrize("name", NAMES)
def test_manifest_does_not_announce_by_default(name: str) -> None:
    assert deploy_body(name)["announce"] is False


# --------------------------------------------------------------- rules-decide

REFUND_POLICY = {
    "id": "refund@2026-09",
    "rules": [
        {
            "id": "R1-window",
            "when": [
                {"fact": "days_since_purchase", "op": "<=", "value": 14},
                {"fact": "opened", "op": "==", "value": False},
            ],
            "then": {"decision": "approve", "reason": "unopened inside 14 days"},
        },
        {
            "id": "R2-faulty",
            "when": [{"fact": "fault_reported", "op": "==", "value": True}],
            "then": {"decision": "approve", "reason": "reported fault"},
        },
    ],
    "default": {"decision": "deny", "reason": "outside the refund window"},
}


def test_decision_first_match_wins() -> None:
    handle = load("rules-decide")
    out = handle(
        {"policy": REFUND_POLICY, "facts": {"days_since_purchase": 5, "opened": False}}
    )
    assert out["decision"] == "approve"
    assert out["matched_rule"] == "R1-window"
    # Evaluation stops at the rule that fired.
    assert [t["rule"] for t in out["trace"]] == ["R1-window"]


def test_decision_trace_shows_why_each_rule_missed() -> None:
    handle = load("rules-decide")
    out = handle(
        {"policy": REFUND_POLICY, "facts": {"days_since_purchase": 40, "opened": True}}
    )
    assert out["decision"] == "deny"
    assert out["matched_rule"] is None
    assert [t["matched"] for t in out["trace"]] == [False, False]
    first = out["trace"][0]["conditions"][0]
    assert first["actual"] == 40 and first["ok"] is False


def test_decision_explains_a_missing_fact_instead_of_crashing() -> None:
    handle = load("rules-decide")
    out = handle({"policy": REFUND_POLICY, "facts": {}})
    assert out["trace"][0]["conditions"][0]["note"] == "fact is missing"
    assert out["decision"] == "deny"


def test_decision_money_comparison_is_exact() -> None:
    handle = load("rules-decide")
    policy = {
        "id": "p",
        "rules": [
            {
                "id": "over",
                "when": [{"fact": "total", "op": ">", "value": 0.3}],
                "then": {"decision": "review"},
            }
        ],
        "default": {"decision": "auto"},
    }
    # Decimal(str(x)) compares the number the caller sent, not the float that
    # 0.1 + 0.2 would have produced on the way in.
    assert handle({"policy": policy, "facts": {"total": 0.3}})["decision"] == "auto"
    assert handle({"policy": policy, "facts": {"total": 0.31}})["decision"] == "review"


def test_decision_refuses_a_policy_with_no_outcome() -> None:
    handle = load("rules-decide")
    with pytest.raises(ValueError, match="default"):
        handle({"policy": {"id": "p", "rules": []}, "facts": {}})


def test_decision_binds_policy_and_facts_by_digest() -> None:
    handle = load("rules-decide")
    args = {"policy": REFUND_POLICY, "facts": {"days_since_purchase": 5, "opened": False}}
    first = handle(args)
    changed = handle(
        {"policy": REFUND_POLICY, "facts": {"days_since_purchase": 6, "opened": False}}
    )
    assert first["policy_sha256"] == changed["policy_sha256"]
    assert first["facts_sha256"] != changed["facts_sha256"]


@pytest.mark.parametrize("name", NAMES)
def test_every_agent_is_deterministic(name: str) -> None:
    handle = load(name)
    cases = {
        "rules-decide": {
            "policy": REFUND_POLICY,
            "facts": {"days_since_purchase": 5, "opened": False},
        },
        "json-canonical": {"document": {"b": 1, "a": [1, 2], "c": "x"}},
        "commit-referee": {
            "commitment": sha256_hex(b"\x00" * 8 + b"value"),
            "salt": "",
            "value": "value",
            "layout": "lenprefix",
        },
    }
    payload = cases[name]
    first = json.dumps(handle(payload), sort_keys=True, ensure_ascii=False)
    for _ in range(5):
        assert json.dumps(handle(payload), sort_keys=True, ensure_ascii=False) == first


# ------------------------------------------------------------- json-canonical


def test_canonical_sorts_keys_and_strips_whitespace() -> None:
    handle = load("json-canonical")
    out = handle({"document": {"b": 1, "a": [1, 2], "": None}})
    assert out["canonical"] == '{"":null,"a":[1,2],"b":1}'
    assert out["byte_length"] == len(out["canonical"].encode())
    assert out["sha256"] == sha256_hex(out["canonical"].encode())


def test_canonical_key_order_is_utf16_not_code_point() -> None:
    handle = load("json-canonical")
    # U+1F600 sorts after U+FF01 by code point, but before it by UTF-16 code
    # unit (lead surrogate 0xD83D). RFC 8785 mandates UTF-16 order.
    above_bmp = chr(0x1F600)
    fullwidth = chr(0xFF01)
    out = handle({"document": {above_bmp: 1, fullwidth: 2}})
    assert out["canonical"].index(above_bmp) < out["canonical"].index(fullwidth)


def test_canonical_refuses_what_would_not_reproduce_elsewhere() -> None:
    handle = load("json-canonical")
    with pytest.raises(ValueError, match="not an integer"):
        handle({"document": {"amount": 1.5}})
    with pytest.raises(ValueError, match=r"2\^53-1"):
        handle({"document": {"id": 9007199254740992}})
    # The boundary itself is fine.
    assert handle({"document": 9007199254740991})["canonical"] == "9007199254740991"


def test_canonical_escapes_only_what_it_must() -> None:
    handle = load("json-canonical")
    # Built from chr() so the source file carries no literal control bytes.
    document = "a" + chr(0x09) + 'b "q" ' + chr(0xFC) + " " + chr(0x01)
    out = handle({"document": document})
    assert out["canonical"] == '"a\\tb \\"q\\" ' + chr(0xFC) + " \\u0001\""


def test_canonical_requires_a_document_key() -> None:
    handle = load("json-canonical")
    with pytest.raises(ValueError, match="document"):
        handle({})


# ------------------------------------------------------------ commit-referee


def test_referee_accepts_a_correct_lenprefix_reveal() -> None:
    handle = load("commit-referee")
    salt = b"x" * 16
    out = handle(
        {
            "commitment": sha256_hex(len(salt).to_bytes(8, "big") + salt + b"42"),
            "salt": salt.hex(),
            "salt_encoding": "hex",
            "value": "42",
            "layout": "lenprefix",
        }
    )
    assert out["valid"] is True
    assert out["binding"] == "non-malleable"
    assert out["findings"] == []


def test_referee_rejects_a_wrong_reveal() -> None:
    handle = load("commit-referee")
    salt = b"y" * 16
    out = handle(
        {
            "commitment": sha256_hex(len(salt).to_bytes(8, "big") + salt + b"heads"),
            "salt": salt.hex(),
            "salt_encoding": "hex",
            "value": "tails",
            "layout": "lenprefix",
        }
    )
    assert out["valid"] is False


def test_referee_flags_a_layout_that_opens_two_ways() -> None:
    """Not advice-shaped: both reveals really do verify against one commitment."""
    handle = load("commit-referee")
    commitment = sha256_hex(b"abcdef")
    first = handle(
        {"commitment": commitment, "salt": "abc", "value": "def", "layout": "concat"}
    )
    second = handle(
        {"commitment": commitment, "salt": "ab", "value": "cdef", "layout": "concat"}
    )
    assert first["valid"] is True
    assert second["valid"] is True  # same commitment, a different revealed value
    assert "malleable_layout" in [f["code"] for f in first["findings"]]

    # Binding the salt length in makes the second opening impossible.
    bound = sha256_hex(len(b"abc").to_bytes(8, "big") + b"abc" + b"def")
    opened = {"commitment": bound, "salt": "abc", "value": "def", "layout": "lenprefix"}
    reopened = {"commitment": bound, "salt": "ab", "value": "cdef", "layout": "lenprefix"}
    assert handle(opened)["valid"] is True
    assert handle(reopened)["valid"] is False


def test_referee_flags_a_separator_that_appears_in_the_salt() -> None:
    handle = load("commit-referee")
    out = handle(
        {
            "commitment": sha256_hex(b"a:b:value"),
            "salt": "a:b",
            "value": "value",
            "layout": "separator",
        }
    )
    assert out["valid"] is True
    assert "separator_in_salt" in [f["code"] for f in out["findings"]]


def test_referee_flags_a_commitment_of_the_wrong_length() -> None:
    handle = load("commit-referee")
    out = handle(
        {"commitment": "abcd", "salt": "x" * 32, "value": "v", "layout": "lenprefix"}
    )
    assert out["valid"] is False
    assert "length_mismatch" in [f["code"] for f in out["findings"]]


def test_referee_warns_about_an_unsalted_commitment() -> None:
    handle = load("commit-referee")
    out = handle({"commitment": sha256_hex(b"heads"), "value": "heads", "layout": "value"})
    assert out["valid"] is True
    assert "unsalted" in [f["code"] for f in out["findings"]]


def test_referee_rejects_bad_hex_and_unknown_layouts() -> None:
    handle = load("commit-referee")
    with pytest.raises(ValueError, match="not valid hex"):
        handle({"commitment": "aa", "salt": "zz", "salt_encoding": "hex", "value": "v"})
    with pytest.raises(ValueError, match="layout must be"):
        handle({"commitment": "aa", "value": "v", "layout": "whatever"})
