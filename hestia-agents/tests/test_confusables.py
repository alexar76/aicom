"""text.confusables@v1: the spoofs that are actually used get caught, honest names do not.

Punycode is checked against Python's own codec (RFC 3492) in both directions; the spoof
shapes are the documented ones: a Cyrillic letter inside a Latin name, the all-Cyrillic
"apple" domain, rn/m and I/l, fullwidth and mathematical letters, zero-width and bidi
characters (Trojan Source).
"""

from __future__ import annotations

import pytest

from hestia_agents.manifests import handler_source

PROTECTED = ["modelmarket", "paypal", "apple"]


@pytest.fixture(scope="module")
def ns():
    namespace: dict = {}
    exec(compile(handler_source("confusables"), "confusables", "exec"), namespace)  # noqa: S102
    return namespace


@pytest.fixture(scope="module")
def handle(ns):
    return ns["handle"]


def kinds(out):
    return {i["kind"] for i in out["issues"]}


@pytest.mark.parametrize(
    "word",
    ["bücher", "münchen", "аррӏе", "東京", "παράδειγμα", "пример", "例え", "ヒュー", "ñandú",
     "日本語ドメイン", "a-b-ü", "ελληνικά"],
)
def test_punycode_matches_pythons_codec(ns, word) -> None:
    assert ns["punycode_decode"](word.encode("punycode").decode()) == word


@pytest.mark.parametrize(
    ("text", "expected", "like"),
    [
        ("pаypal", {"mixed_script", "confusable_with"}, ["paypal"]),
        ("rnodelmarket", {"confusable_with"}, ["modelmarket"]),
        ("modeImarket", {"confusable_with"}, ["modelmarket"]),
        ("modelmarkеt", {"mixed_script", "confusable_with"}, ["modelmarket"]),
        ("ｍodelmarket", {"compatibility", "confusable_with"}, ["modelmarket"]),
        ("\U0001d426odelmarket", {"compatibility", "confusable_with"}, ["modelmarket"]),
        ("model​market", {"invisible", "confusable_with"}, ["modelmarket"]),
        ("аррӏе", {"whole_script", "confusable_with"}, ["apple"]),
        ("Ρaypal", {"mixed_script", "confusable_with"}, ["paypal"]),
    ],
)
def test_spoofs_are_high_risk(handle, text, expected, like) -> None:
    out = handle({"text": text, "against": PROTECTED})
    assert out["risk"] == "high" and expected <= kinds(out), out["issues"]
    assert out["confusable_with"] == like


def test_trojan_source_bidi(handle) -> None:
    out = handle({"text": "access‮⁦level"})
    assert "bidi_control" in kinds(out) and out["risk"] == "high"


@pytest.mark.parametrize("text", ["modelmarket", "Привет", "東京tokyo", "ゲームgame",
                                  "서울seoul", "müller", "data_v2-final"])
def test_honest_names_pass(handle, text) -> None:
    out = handle({"text": text, "against": PROTECTED})
    assert out["risk"] == "none", out["issues"]


def test_accents_alone_are_medium(handle) -> None:
    out = handle({"text": "modelmarkét", "against": PROTECTED})
    assert out["risk"] == "medium" and kinds(out) == {"confusable_ignoring_accents"}


def test_the_apple_domain(handle) -> None:
    out = handle({"text": "xn--80ak6aa92e.com", "kind": "domain", "against": ["Apple.com"]})
    assert out["displayed"] == "аррӏе.com"
    assert {"punycode", "whole_script", "confusable_with"} <= kinds(out)
    assert out["confusable_with"] == ["apple.com"]
    broken = handle({"text": "xn--ab!c.com", "kind": "domain"})
    assert broken["risk"] == "high" and "punycode" in kinds(broken)


def test_batch(handle) -> None:
    out = handle({"texts": ["paypal", "pаypal", "pay-pal"], "against": ["paypal"]})
    assert out["flagged"] == ["pаypal"]


def test_skeleton_is_case_folded_but_keeps_capital_i(ns) -> None:
    assert ns["skeleton"]("PayPal") == "paypal"
    assert ns["skeleton"]("lBM") == ns["skeleton"]("IBM") == "lbm"


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({}, "send 'text'"),
        ({"text": ""}, "1 to 253"),
        ({"text": "x" * 254}, "1 to 253"),
        ({"texts": []}, "non-empty list"),
        ({"text": "a", "kind": "url"}, "kind must be"),
        ({"text": "a", "against": "paypal"}, "against must be"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)
