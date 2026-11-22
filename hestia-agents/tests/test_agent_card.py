"""agent.card.verify@v1: A2A Agent Card structure and JWS signatures.

`agent_card_fixtures.json` is made by tests/make_agent_card_fixtures.py: the A2A specification's
own example card (section 8.4.1) signed four ways with throwaway keys by the `cryptography` library,
which shares no code with the agent. The JWS primitives are also held to published vectors:
RFC 8037 Appendix A.4 (EdDSA). `agent_card_vectors.json` holds cards as their hosts served them on
2026-11-21 (scripts/record_fetches.py), when present.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

import pytest
from replay import load

from hestia_agents.manifests import AGENTS, deploy_body

HERE = Path(__file__).parent
F = json.loads((HERE / "agent_card_fixtures.json").read_text(encoding="utf-8"))
SLUG = "agent-card"
CARD_URL = "https://example.com/.well-known/agent-card.json"


def call(payload, fetched=None, extra=None):
    handle, asked, ns = load(SLUG, fetched or {}, extra=extra)
    return handle(payload), asked, ns


def jwks_reply(keys):
    return {
        "status": 200,
        "headers": {"content-type": "application/json"},
        "text": json.dumps(keys),
    }


def key_of(url):
    return json.dumps(["GET", url, [["accept", "application/json"]], None], separators=(",", ":"))


def test_all_four_algorithms_verify_and_name_the_payload_form_they_cover() -> None:
    out, asked, _ = call({"card": F["card"], "keys": F["jwks"], "url": CARD_URL})
    assert out["verdict"] == "signed_verified" and asked == []
    rows = {r["kid"]: r for r in out["signatures"]}
    assert all(r["verified"] for r in rows.values())
    assert rows["ed-1"]["payload"] == "as served"
    for kid in ("es-1", "rs-1", "ps-1"):
        assert rows[kid]["payload"] == "empty values removed (a2a-python signing.py)"
    assert out["protocol_version"] == "1.0" and out["problems"] == []


def test_the_canonical_payload_equals_an_independent_serialisation() -> None:
    _, _, ns = call({"card": F["card"]})
    forms = dict(ns["payload_variants"](F["card"]))
    assert forms["as served"].decode() == F["payload_served"]
    assert forms["empty values removed (a2a-python signing.py)"].decode() == F["payload_cleaned"]


def test_the_jwks_is_read_from_jku_on_the_cards_host() -> None:
    fetched = {key_of(CARD_URL): jwks_reply(F["card"]), key_of(F["jku"]): jwks_reply(F["jwks"])}
    out, asked, _ = call({"url": CARD_URL}, fetched)
    assert out["verdict"] == "signed_verified"
    assert asked == [CARD_URL, F["jku"]]  # one read of the JWKS for four signatures
    assert {r["key_source"] for r in out["signatures"]} == {"jwks_on_card_host"}
    assert all(r["anchored"] for r in out["signatures"])


def test_a_jku_on_another_host_is_read_only_when_named() -> None:
    card = copy.deepcopy(F["card"])
    elsewhere = "https://keys.example.net/jwks.json"
    for sig in card["signatures"]:
        header = json.loads(base64.urlsafe_b64decode(sig["protected"] + "=="))
        header["jku"] = elsewhere
        sig["protected"] = (
            base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
    out, asked, _ = call({"card": card, "url": CARD_URL})
    assert out["verdict"] == "signature_failed" and asked == []
    assert "not the card's host" in out["signatures"][0]["detail"]
    # Named as jwks, it is read. The signatures were made over the old headers, so they fail now:
    # the header is part of what is signed.
    out, asked, _ = call(
        {"card": card, "url": CARD_URL, "jwks": elsewhere},
        {key_of(elsewhere): jwks_reply(F["jwks"])},
    )
    assert asked == [elsewhere] and not any(r["verified"] for r in out["signatures"])


def test_one_changed_field_fails_every_signature() -> None:
    card = copy.deepcopy(F["card"])
    card["supportedInterfaces"][0]["url"] = "https://attacker.example/a2a/v1"
    out, _, _ = call({"card": card, "keys": F["jwks"], "url": CARD_URL})
    assert out["verdict"] == "signature_failed"
    assert all("over any of the 3 payload forms" in r["detail"] for r in out["signatures"])


def test_a_key_of_the_wrong_type_or_use_is_refused() -> None:
    jwks = copy.deepcopy(F["jwks"])
    jwks["keys"][0]["use"] = "enc"
    out, _, _ = call({"card": F["card"], "keys": jwks})
    assert "use is enc" in out["signatures"][0]["detail"]
    jwks = copy.deepcopy(F["jwks"])
    jwks["keys"][1]["kid"] = "es-1"  # two keys with one kid
    out, _, _ = call({"card": F["card"], "keys": jwks})
    assert "more than one key" in out["signatures"][0]["detail"]


def test_a_private_key_in_the_jwks_is_refused() -> None:
    jwks = copy.deepcopy(F["jwks"])
    jwks["keys"][0]["d"] = "AAAA"
    out, _, _ = call({"card": F["card"], "keys": jwks})
    assert "private" in out["signatures"][0]["detail"]


def test_algorithms_limit_what_is_accepted_and_none_is_never_accepted() -> None:
    out, _, _ = call({"card": F["card"], "keys": F["jwks"], "algorithms": ["EdDSA"]})
    assert [r["verified"] for r in out["signatures"]] == [False, True, False, False]
    assert out["verdict"] == "signed_verified"
    with pytest.raises(ValueError, match="algorithms"):
        call({"card": F["card"], "algorithms": ["none"]})
    with pytest.raises(ValueError, match="algorithms"):
        call({"card": F["card"], "algorithms": ["HS256"]})


def test_alg_in_the_unprotected_header_is_refused() -> None:
    card = copy.deepcopy(F["card"])
    card["signatures"][1]["header"] = {"alg": "none"}
    out, _, _ = call({"card": card, "keys": F["jwks"]})
    assert (
        "protected header" in out["signatures"][1]["detail"]
        and not out["signatures"][1]["verified"]
    )


def test_an_unsigned_card_and_a_malformed_one() -> None:
    card = {k: v for k, v in F["card"].items() if k != "signatures"}
    out, _, _ = call({"card": card})
    assert out["verdict"] == "unsigned" and out["signatures"] == []
    broken = dict(card)
    del broken["skills"]
    broken["supportedInterfaces"] = [{"url": "http://example.com/a2a", "protocolBinding": "SOAP"}]
    out, _, _ = call({"card": broken})
    assert out["verdict"] == "malformed"
    assert "missing required field skills" in out["problems"]
    assert any("not an absolute https URL" in p for p in out["problems"])
    assert any("SOAP" in w for w in out["warnings"])


def test_a_03_card_is_read_with_its_url_and_additional_interfaces() -> None:
    card = {
        "name": "Old",
        "description": "A 0.3 card.",
        "url": "https://example.com/a2a",
        "version": "1",
        "protocolVersion": "0.3.0",
        "preferredTransport": "JSONRPC",
        "capabilities": {},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [{"id": "s", "name": "S", "description": "d"}],
        "additionalInterfaces": [{"url": "https://grpc.example.com", "transport": "GRPC"}],
    }
    out, _, _ = call({"card": card, "url": "https://example.com"})
    assert out["protocol_version"] == "0.3.0" and out["verdict"] == "unsigned"
    assert [
        (i["url"], i["binding"], i["preferred"], i["on_card_host"]) for i in out["interfaces"]
    ] == [
        ("https://example.com/a2a", "JSONRPC", True, True),
        ("https://grpc.example.com", "GRPC", False, True),
    ]


def test_a_domain_tries_agent_card_then_the_pre_10_name() -> None:
    card = {k: v for k, v in F["card"].items() if k != "signatures"}
    fetched = {
        key_of(CARD_URL): {"status": 404, "headers": {}, "text": "not found"},
        key_of("https://example.com/.well-known/agent.json"): jwks_reply(card),
    }
    out, asked, _ = call({"url": "example.com"}, fetched)
    assert asked == [CARD_URL, "https://example.com/.well-known/agent.json"]
    assert out["source"].endswith("/agent.json") and "pre-1.0" in out["warnings"][0]
    fetched[key_of("https://example.com/.well-known/agent.json")] = {
        "status": 404,
        "headers": {},
        "text": "",
    }
    out, _, _ = call({"url": "example.com"}, fetched)
    assert out["verdict"] == "not_found" and [t["status"] for t in out["fetched"]] == [404, 404]


def test_rfc_8037_a4_eddsa_vector() -> None:
    _, _, ns = call({"card": {}})
    key = ns["parse_jwk"](
        {"kty": "OKP", "crv": "Ed25519", "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"}, "k"
    )
    signing_input = b"eyJhbGciOiJFZERTQSJ9.RXhhbXBsZSBvZiBFZDI1NTE5IHNpZ25pbmc"
    signature = ns["b64url_decode"](
        "hgyY0il_MGCjP0JzlnLWG1PPOt7-09PGcvMg3AIbQR6dWbhijcNR4ki4iylGjg5BhVsPt9g7sVvpAr_MuM0KAg",
        "s",
    )
    assert ns["verify_jws"](key, "EdDSA", signing_input, signature)[0] is True
    assert ns["verify_jws"](key, "EdDSA", signing_input + b"x", signature)[0] is False
    # RFC 8037 A.3: the thumbprint of that key.
    assert (
        ns["jwk_thumbprint"](
            {"kty": "OKP", "crv": "Ed25519", "x": "11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo"}
        )
        == "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k"
    )


@pytest.mark.parametrize(
    "value, text",
    [
        (1.0, "1"),
        (0.5, "0.5"),
        (1e21, "1e+21"),
        (1e20, "100000000000000000000"),
        (1e-7, "1e-7"),
        (0.000001, "0.000001"),
        (-2.5e-10, "-2.5e-10"),
        (123456789.125, "123456789.125"),
        (0.0, "0"),
    ],
)
def test_jcs_numbers_follow_ecmascript(value, text) -> None:
    _, _, ns = call({"card": {}})
    assert ns["jcs"](value) == text


def test_jcs_sorts_keys_by_utf16_code_units() -> None:
    _, _, ns = call({"card": {}})
    # U+1F600 (a surrogate pair, D83D...) sorts before U+FB33 in UTF-16 order, after it by code point.
    assert ns["jcs"]({"דּ": 1, "\U0001f600": 2}) == '{"\U0001f600":2,"דּ":1}'


@pytest.mark.parametrize(
    "payload, message",
    [
        ({}, "give url"),
        ({"url": "http://example.com"}, "https"),
        ({"url": "https://user@example.com/card"}, "https"),
        ({"url": "example"}, "domain"),
        ({"card": []}, "card must be"),
        ({"card": {}, "keys": [1]}, "JWKS"),
        ({"card": {}, "jwks": "http://x.example/jwks"}, "https"),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_reaches_only_hosts_the_caller_names_and_is_free() -> None:
    meta = AGENTS[SLUG]
    body = deploy_body(SLUG)
    assert meta["capability_id"] == "agent.card.verify@v1" and meta["price_per_call_usd"] == 0
    assert "egress_hosts" not in body and body["egress_input_fields"] == ["url", "jwks"]
    out, asked, _ = call(meta["probe"])
    assert out["verdict"] == "unsigned" and asked == []


VECTORS = HERE / "agent_card_vectors.json"


@pytest.mark.skipif(not VECTORS.exists(), reason="no recorded live cards")
def test_recorded_live_cards_reproduce_their_verdicts() -> None:
    cases = json.loads(VECTORS.read_text(encoding="utf-8"))
    for name, case in cases.items():
        handle, _, _ = load(SLUG, case["fetched"])
        assert handle(case["payload"])["verdict"] == case["verdict"], name


# ------------------------------------------------------------------ key forms found on signed cards


def did_doc_reply():
    return {"status": 200, "headers": {}, "text": json.dumps(F["did_document"])}


def test_did_web_did_key_embedded_es256k_and_unencoded_payload_each_verify() -> None:
    fetched = {
        key_of("https://example.com/.well-known/did.json"): did_doc_reply(),
        key_of("https://example.com/.well-known/jwks.json"): jwks_reply(F["jwks"]),
    }
    out, asked, _ = call({"card": F["card_dids"], "url": CARD_URL}, fetched)
    rows = out["signatures"]
    assert [r["verified"] for r in rows] == [True, True, True, True]
    assert [r["key_source"] for r in rows] == [
        "did_web_on_card_host",
        "did_key",
        "embedded",
        "conventional_jwks",
    ]
    assert [r["anchored"] for r in rows] == [True, False, False, True]
    assert rows[2]["alg"] == "ES256K" and rows[3]["unencoded_payload"] is True
    assert out["verdict"] == "signed_verified"
    assert asked == [
        "https://example.com/.well-known/did.json",
        "https://example.com/.well-known/jwks.json",
    ]


def test_only_self_certifying_keys_make_the_card_self_asserted() -> None:
    card = dict(
        F["card_dids"], signatures=F["card_dids"]["signatures"][1:3]
    )  # did:key and embedded jwk
    out, asked, _ = call({"card": card, "url": CARD_URL})
    assert out["verdict"] == "signed_self_asserted" and asked == []
    assert all(r["verified"] and not r["anchored"] for r in out["signatures"])


def test_did_key_decodes_to_the_signers_key() -> None:
    _, _, ns = call({"card": {}})
    jwk = ns["multikey_jwk"](F["did_key"])
    assert (
        jwk["kty"] == "OKP"
        and jwk["crv"] == "Ed25519"
        and len(ns["b64url_decode"](jwk["x"], "x")) == 32
    )
    with pytest.raises(ValueError, match="base58"):
        ns["multikey_jwk"]("z0OIl")


def test_a_did_web_on_another_host_needs_to_be_named() -> None:
    card = copy.deepcopy(F["card_dids"])
    card["signatures"] = card["signatures"][:1]
    out, asked, _ = call({"card": card, "url": "https://other.example/.well-known/agent-card.json"})
    assert asked == [] and "not the card's host" in out["signatures"][0]["detail"]


def test_a_did_document_for_another_did_is_refused() -> None:
    doc = dict(F["did_document"], id="did:web:evil.example")
    fetched = {
        key_of("https://example.com/.well-known/did.json"): {
            "status": 200,
            "headers": {},
            "text": json.dumps(doc),
        }
    }
    card = dict(F["card_dids"], signatures=F["card_dids"]["signatures"][:1])
    out, _, _ = call({"card": card, "url": CARD_URL}, fetched)
    assert "id is did:web:evil.example" in out["signatures"][0]["detail"]


def test_headers_that_overlap_or_name_unknown_crit_are_refused() -> None:
    card = copy.deepcopy(F["card"])
    card["signatures"] = card["signatures"][:1]
    card["signatures"][0]["header"] = {"kid": "es-1"}
    out, _, _ = call({"card": card, "keys": F["jwks"]})
    assert "disjoint" in out["signatures"][0]["detail"]
    head = (
        base64.urlsafe_b64encode(
            json.dumps({"alg": "ES256", "kid": "es-1", "crit": ["exp"], "exp": 1}).encode()
        )
        .decode()
        .rstrip("=")
    )
    card["signatures"] = [{"protected": head, "signature": "AAAA"}]
    out, _, _ = call({"card": card, "keys": F["jwks"]})
    assert "only RFC 7797" in out["signatures"][0]["detail"]


def test_a_jku_on_a_parent_domain_tells_the_caller_what_to_name() -> None:
    card = copy.deepcopy(F["card"])
    card["signatures"] = card["signatures"][:1]
    out, _, _ = call({"card": card, "url": "https://agent.example.com/.well-known/agent-card.json"})
    assert out["signatures"][0]["next"] == {"jwks": F["jku"]}


def test_es256k_rfc_8812_curve_arithmetic() -> None:
    _, _, ns = call({"card": {}})
    c = ns["CURVES"]["secp256k1"]
    gx, gy = c["g"]
    assert (gy * gy - gx**3 - 7) % c["p"] == 0
    # 2G computed with a = 0 doubling equals G + G through the addition formula's own doubling.
    two = ns["_jdouble"]((gx, gy, 1), c["p"], 0)
    z = pow(two[2], c["p"] - 2, c["p"])
    x2 = two[0] * z * z % c["p"]
    assert x2 == 0xC6047F9441ED7D6D3045406E95C07CD85C778E4B8CEF3CA7ABAC09B95C709EE5
