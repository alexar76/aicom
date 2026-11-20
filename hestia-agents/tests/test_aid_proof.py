"""aid.proof.verify@v1 against proofs a production endpoint served and against a second signer.

`aid_proof_vectors.json` holds three exchanges recorded from https://modelmarket.dev/mcp on
2026-11-19 (the hub's own signer, key published in _agent.modelmarket.dev): a domain-bound
proof, an unbound one, and the 403 an endpoint gives for a domain it does not serve. The other
cases are signed here with `cryptography` and a throwaway key, by a signer written from the
text of AID v2.1.1 Appendix B, so the handler's Ed25519 and its signature base are checked
against an implementation that shares no code with it.
"""
# ruff: noqa: E501 — recorded headers and DNS answers are kept on one line

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from hestia_agents.manifests import handler_source

LIVE = json.loads((Path(__file__).parent / "aid_proof_vectors.json").read_text(encoding="utf-8"))
NOW = 1_800_000_000
KEY = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"aid-proof test key, never used").digest())
K = base64.urlsafe_b64encode(KEY.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).rstrip(b"=").decode()
KEYID = base64.urlsafe_b64encode(
    hashlib.sha256(('{"crv":"Ed25519","kty":"OKP","x":"' + K + '"}').encode()).digest()).rstrip(b"=").decode()
NONCE = base64.urlsafe_b64encode(hashlib.sha256(b"challenge").digest()).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def handle():
    namespace: dict = {}
    exec(compile(handler_source("aid-proof"), "aid-proof", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"]


def exchange(*, uri="https://agent.example.com/mcp", target=None, authority="agent.example.com",
             domain=None, status=200, method="GET", created=NOW, expires=NOW + 60, key=KEY,
             keyid=KEYID, nonce=NONCE, alg="ed25519", tag="aid-pka-v2", covered=None, pad=True):
    """A request and the response a correct signer would give, with any field bent."""
    items = covered or (['"@method";req', '"@target-uri";req', '"@authority";req']
                        + (['"aid-domain";req'] if domain else []) + ['"@status"'])
    params = (f'({" ".join(items)});created={created};expires={expires};keyid="{keyid}";'
              f'alg="{alg}";nonce="{nonce}";tag="{tag}"')
    lines = [f'"@method";req: {method}', f'"@target-uri";req: {target or uri}',
             f'"@authority";req: {authority}']
    if domain:
        lines.append(f'"aid-domain";req: {domain}')
    lines += [f'"@status": {status}', f'"@signature-params": {params}']
    signature = base64.b64encode(key.sign("\n".join(lines).encode())).decode()
    request = {"uri": uri, "nonce": NONCE, "method": method}
    if domain:
        request["aid_domain"] = domain
    return {"k": K, "request": request, "now": NOW + 1,
            "response": {"status": status, "headers": {
                "Signature-Input": "aid-pka=" + params,
                "Signature": "aid-pka=:" + (signature if pad else signature.rstrip("=")) + ":",
                "Cache-Control": "no-store"}}}


def failed(out):
    assert out["verified"] is False and out["code"] == 1003 and out["error"] == "ERR_SECURITY"
    return out["failed"]


# ------------------------------------------------------------- recorded from production


def test_the_bound_proof_modelmarket_served_verifies(handle) -> None:
    out = handle(LIVE["bound"])
    assert out["verified"] is True and out["domain_bound"] is True and out["code"] == 0
    assert out["keyid"] == "GPgQ1hgsCNYND5UeXKXx970ljHR9Tlg4dR1oMK-p9aA"
    assert '"aid-domain";req: modelmarket.dev' in out["signature_base"]
    assert all(check["ok"] for check in out["checks"])


def test_the_unbound_proof_modelmarket_served_verifies_as_unbound(handle) -> None:
    out = handle(LIVE["unbound"])
    assert out["verified"] is True and out["domain_bound"] is False
    assert "aid-domain" not in out["signature_base"]


def test_a_403_for_an_unserved_domain_is_no_proof(handle) -> None:
    out = handle(LIVE["unserved_domain"])
    assert failed(out) == ["signature_headers"]
    assert "refuses a domain it does not serve" in out["checks"][-1]["detail"]


def test_a_recorded_proof_is_stale_five_minutes_later(handle) -> None:
    late = dict(LIVE["bound"], now=LIVE["bound"]["now"] + 400)
    assert failed(handle(late)) == ["freshness"]


def test_the_record_can_stand_in_for_k(handle) -> None:
    case = {key: value for key, value in LIVE["bound"].items() if key != "k"}
    case["record"] = "v=aid2;u=https://modelmarket.dev/mcp;p=mcp;a=none;k=" + LIVE["bound"]["k"]
    assert handle(case)["verified"] is True


# ------------------------------------------------------------- a second signer


def test_unbound_and_bound_proofs_from_another_signer(handle) -> None:
    out = handle(exchange())
    assert out["verified"] is True and out["domain_bound"] is False and out["keyid"] == KEYID
    out = handle(exchange(domain="example.com"))
    assert out["verified"] is True and out["domain_bound"] is True


def test_the_rfc_8037_thumbprint_vector(handle) -> None:
    namespace: dict = {}
    exec(compile(handler_source("aid-proof"), "aid-proof", "exec"), namespace)  # noqa: S102
    assert namespace["keyid"]("11qYAYKxCrfVS_7TyWQHOg7hcvPapiMlrwIaaPcHURo") == \
        "kPrK_qmxVWaYVA9wwBF6Iuo3vVzz7TxHCTwXBygrS4k"


def test_target_uri_and_authority_follow_appendix_b5(handle) -> None:
    # fragment dropped, host lower-cased, default port dropped, query and other ports kept
    out = handle(exchange(uri="https://Agent.Example.com:443/mcp?x=1#frag",
                          target="https://agent.example.com/mcp?x=1"))
    assert out["verified"] is True
    out = handle(exchange(uri="https://agent.example.com:8443/mcp",
                          authority="agent.example.com:8443"))
    assert out["verified"] is True


def test_a_signed_401_and_a_post_are_proofs_too(handle) -> None:
    assert handle(exchange(status=401))["verified"] is True
    assert handle(exchange(method="POST"))["verified"] is True


@pytest.mark.parametrize(("bend", "check"), [
    ({"nonce": "someone-elses-challenge-0000000000000000000000"}, "nonce"),
    ({"keyid": "A" * 43}, "keyid"),
    ({"tag": "aid-pka-v1"}, "tag"),
    ({"alg": "rsa-pss-sha512"}, "alg"),
    ({"created": NOW, "expires": NOW + 301}, "window"),
    ({"created": NOW, "expires": NOW}, "window"),
    ({"created": NOW + 500, "expires": NOW + 560}, "freshness"),
    ({"status": 302}, "no_redirect"),
    ({"covered": ['"@method";req', '"@target-uri";req', '"@status"']}, "covered_components"),
    ({"covered": ['"@method";req', '"@target-uri";req', '"@authority";req', '"@status"',
                  '"date"']}, "covered_components"),
    ({"covered": ['"@method"', '"@target-uri";req', '"@authority";req', '"@status"']},
     "covered_components"),
])
def test_each_verifier_rule_fails_on_its_own(handle, bend, check) -> None:
    assert check in failed(handle(exchange(**bend)))


def test_a_signature_by_another_key_fails(handle) -> None:
    other = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"another key").digest())
    assert failed(handle(exchange(key=other))) == ["signature"]


def test_one_changed_byte_of_the_request_fails_the_signature(handle) -> None:
    case = exchange()
    case["request"]["uri"] = "https://agent.example.com/mcp2"
    assert failed(handle(case)) == ["signature"]
    case = exchange()
    case["response"]["status"] = 201
    assert failed(handle(case)) == ["signature"]


def test_missing_no_store_fails(handle) -> None:
    case = exchange()
    case["response"]["headers"]["Cache-Control"] = "max-age=0, private"
    assert failed(handle(case)) == ["cache_control"]
    case["response"]["headers"]["Cache-Control"] = "private, No-Store"
    assert handle(case)["verified"] is True


def test_a_bound_proof_needs_the_domain_the_client_sent(handle) -> None:
    case = exchange(domain="example.com")
    del case["request"]["aid_domain"]  # the client never committed to a domain: fail closed
    assert "domain_binding" in failed(handle(case))
    case = exchange(domain="example.com")
    case["request"]["aid_domain"] = "other.example"  # signed for a different domain
    assert failed(handle(case)) == ["signature"]
    case = exchange(domain="example.com")
    case["request"]["aid_domain"] = "Example.COM."  # same domain, canonical form
    assert handle(case)["domain_bound"] is True


def test_requiring_binding_refuses_an_unbound_proof(handle) -> None:
    case = exchange()
    case["require_domain_binding"] = True
    assert failed(handle(case)) == ["domain_binding"]
    case = exchange()
    case["request"]["aid_domain"] = "example.com"  # asked, and the endpoint ignored it
    out = handle(case)
    assert out["verified"] is True and out["domain_bound"] is False
    assert any("unbound proof" in warning for warning in out["warnings"])


def test_other_signature_members_and_spacing_do_not_confuse_the_parser(handle) -> None:
    case = exchange()
    headers = case["response"]["headers"]
    headers["Signature-Input"] = 'sig1=("@status" "content-type");keyid="a,b;(c)", ' + headers["Signature-Input"]
    headers["Signature"] = "sig1=:AAAA:, " + headers["Signature"]
    assert handle(case)["verified"] is True
    twice = copy.deepcopy(case)
    twice["response"]["headers"]["Signature-Input"] += ", " + exchange(nonce="x" * 43)["response"]["headers"]["Signature-Input"]
    assert failed(handle(twice)) == ["signature_headers"]


def test_malformed_headers_and_keys_are_failures_not_crashes(handle) -> None:
    for name, value in (("Signature-Input", "aid-pka=broken"), ("Signature", "aid-pka=:@@@@:"),
                        ("Signature-Input", 'aid-pka=("@method";req);created=1;expires=2')):
        case = exchange()
        case["response"]["headers"][name] = value
        assert failed(handle(case)) == ["signature_headers"], name
    extra = exchange()
    extra["response"]["headers"]["Signature-Input"] += ';extra="1"'
    assert failed(handle(extra)) == ["signature_headers"]
    for k in ("z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK", K + "=", K[:-2], ""):
        case = dict(exchange(), k=k)
        if k:
            assert failed(handle(case)) == ["key"], k
        else:
            with pytest.raises(ValueError):
                handle(case)


def test_unpadded_signature_is_accepted_with_a_warning(handle) -> None:
    out = handle(exchange(pad=False))
    assert out["verified"] is True
    assert any("padding" in warning for warning in out["warnings"])


def test_bad_input_is_refused_with_a_reason(handle) -> None:
    for bend in ({"now": None}, {"now": True}, {"request": {"uri": "http://a.example/mcp", "nonce": "n"}},
                 {"request": {"uri": "https://a.example/mcp"}}, {"response": {"status": 200}},
                 {"skew": 301}):
        with pytest.raises(ValueError):
            handle(dict(exchange(), **bend))
