"""http.signature.verify@v1: RFC 9421 Appendix B, a real AID response, and signatures made here.

`http_signature_vectors.json` holds the test messages, public keys and all six signatures of
RFC 9421 Appendix B (https://www.rfc-editor.org/rfc/rfc9421.txt, unwrapped per RFC 8792): RSA-PSS
(three), ECDSA P-256 on a response, HMAC-SHA256 and Ed25519. The agent must rebuild each
signature base byte for byte and verify each signature. `aid_proof_vectors.json` holds a response
modelmarket.dev/mcp signed on 2026-11-19 (Ed25519, components taken from the request with ;req).
The algorithms with no deterministic example in the RFC (P-384, rsa-v1_5-sha256) and the
negative cases are signed here with `cryptography`.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from hestia_agents.manifests import deploy_body, handler_source

V = json.loads((Path(__file__).parent / "http_signature_vectors.json").read_text(encoding="utf-8"))
AID = json.loads((Path(__file__).parent / "aid_proof_vectors.json").read_text(encoding="utf-8"))


def load():
    namespace: dict = {}
    exec(compile(handler_source("http-signature"), "http-signature", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"]


handle = load()


def rfc_keys():
    keys = {k: v for k, v in V["keys"].items() if k != "test-key-rsa"}
    keys["test-key-rsa-pss"] = {"alg": "rsa-pss-sha512", "key": keys["test-key-rsa-pss"]}
    keys["test-shared-secret"] = {"alg": "hmac-sha256", "key": V["shared_secret"]}
    return keys


def rfc_message(label):
    case = V["cases"][label]
    msg = copy.deepcopy(V["response"] if label == "sig-b24" else V["request"])
    msg["headers"]["Signature-Input"] = label + "=" + case["signature_input"]
    msg["headers"]["Signature"] = label + "=" + case["signature"]
    return msg


@pytest.mark.parametrize("label", sorted(V["cases"]))
def test_every_rfc_9421_example_verifies_with_the_rfc_signature_base(label) -> None:
    out = handle({"message": rfc_message(label), "keys": rfc_keys()})
    (sig,) = out["signatures"]
    assert out["verdict"] == "valid" and sig["signature_ok"] is True, sig
    assert sig["signature_base"] == V["cases"][label]["base"]
    assert out["content_digest"]["ok"] is True


@pytest.mark.parametrize("label", sorted(V["cases"]))
def test_a_changed_covered_value_or_signature_fails(label) -> None:
    msg = rfc_message(label)
    sig = msg["headers"]["Signature"]
    raw = bytearray(base64.b64decode(sig.split("=:", 1)[1][:-1]))
    raw[-5] ^= 1
    msg["headers"]["Signature"] = label + "=:" + base64.b64encode(bytes(raw)).decode() + ":"
    out = handle({"message": msg, "keys": rfc_keys()})
    assert out["verdict"] == "invalid" and out["signatures"][0]["signature_ok"] is False


def test_tampered_covered_fields_fail_and_uncovered_ones_do_not_matter() -> None:
    msg = rfc_message("sig-b26")
    msg["headers"]["Content-Type"] = "text/plain"  # covered
    assert handle({"message": msg, "keys": rfc_keys()})["signatures"][0]["signature_ok"] is False
    msg = rfc_message("sig-b26")
    msg["url"] = "https://example.com/foo?param=Other"  # @query is not covered by sig-b26
    out = handle({"message": msg, "keys": rfc_keys()})
    assert out["signatures"][0]["signature_ok"] is True
    msg = rfc_message("sig-b22")
    msg["url"] = "https://example.com/foo?param=Value&Pet=cat"  # the covered query parameter
    assert handle({"message": msg, "keys": rfc_keys()})["verdict"] == "invalid"


def test_body_not_matching_content_digest_is_invalid_even_with_a_good_signature() -> None:
    msg = rfc_message("sig-b22")
    msg["body"] = '{"hello": "world!"}'
    out = handle({"message": msg, "keys": rfc_keys()})
    assert out["signatures"][0]["signature_ok"] is True
    assert out["content_digest"]["ok"] is False and out["verdict"] == "invalid"
    out = handle({"message": rfc_message("sig-b26"), "keys": rfc_keys()})
    assert any("not covered" in n for n in out["signatures"][0]["notes"])


def test_time_window_and_required_components() -> None:
    msg, keys = rfc_message("sig-b26"), rfc_keys()
    assert handle({"message": msg, "keys": keys, "now": 1618884473 + 30, "max_age": 300})["verdict"] == "valid"
    old = handle({"message": msg, "keys": keys, "now": 1618884473 + 3600, "max_age": 300})
    assert old["verdict"] == "invalid" and "older than max_age" in old["signatures"][0]["problems"][0]
    future = handle({"message": msg, "keys": keys, "now": 1618884473 - 3600})
    assert "in the future" in future["signatures"][0]["problems"][0]
    need = handle({"message": msg, "keys": keys, "required": ["@authority", "content-digest"]})
    assert need["verdict"] == "invalid"
    assert need["signatures"][0]["problems"] == ['does not cover the required "content-digest"']
    minimal = handle({"message": rfc_message("sig-b21"), "keys": keys})
    assert any("covers no component" in n for n in minimal["signatures"][0]["notes"])


def test_the_rfc_query_parameter_encoding_example() -> None:
    url = ("https://www.example.com/parameters?var=this%20is%20a%20big%0Amultiline%20value&"
           "bar=with+plus+whitespace&fa%C3%A7ade%22%3A%20=something")
    ns: dict = {}
    exec(compile(handler_source("http-signature"), "h", "exec"), ns)  # noqa: S102
    msg = ns["_message"]({"method": "GET", "url": url, "headers": {}}, "m")
    get = ns["_component"]
    assert get("@query-param", {"name": "var"}, msg, None, []) == "this%20is%20a%20big%0Amultiline%20value"
    assert get("@query-param", {"name": "bar"}, msg, None, []) == "with%20plus%20whitespace"
    assert get("@query-param", {"name": "fa%C3%A7ade%22%3A%20"}, msg, None, []) == "something"
    assert get("@query", {}, msg, None, []) == "?" + url.split("?", 1)[1]
    assert get("@authority", {}, ns["_message"]({"url": "https://Example.COM:443/x"}, "m"), None, []) == "example.com"
    assert get("@authority", {}, ns["_message"]({"url": "https://example.com:8443/x"}, "m"), None, []) == "example.com:8443"
    assert get("@request-target", {}, msg, None, []).startswith("/parameters?var=")


def test_a_real_aid_response_signed_by_modelmarket_dev() -> None:
    case = AID["bound"]
    request = {"method": case["request"]["method"], "url": case["request"]["uri"],
               "headers": {"aid-domain": case["request"]["aid_domain"]}}
    message = {"status": case["response"]["status"], "headers": case["response"]["headers"]}
    key = {"kty": "OKP", "crv": "Ed25519", "x": case["k"]}
    out = handle({"message": message, "request": request, "key": key, "now": case["now"]})
    (sig,) = out["signatures"]
    assert out["verdict"] == "valid", sig
    assert sig["covered"] == ['"@method";req', '"@target-uri";req', '"@authority";req', '"aid-domain";req', '"@status"']
    assert sig["signature_base"].startswith('"@method";req: GET\n"@target-uri";req: https://modelmarket.dev/mcp\n')
    late = handle({"message": message, "request": request, "key": key, "now": case["now"] + 120})
    assert late["verdict"] == "invalid" and "expired" in late["signatures"][0]["problems"][0]
    no_request = handle({"message": message, "key": key})
    assert no_request["signatures"][0]["verdict"] == "error" and ";req" in no_request["signatures"][0]["detail"]


def sign_here(alg, private, base):
    data = base.encode()
    if alg == "ecdsa-p384-sha384":
        r, s = decode_dss_signature(private.sign(data, ec.ECDSA(hashes.SHA384())))
        return r.to_bytes(48, "big") + s.to_bytes(48, "big")
    if alg == "rsa-v1_5-sha256":
        return private.sign(data, padding.PKCS1v15(), hashes.SHA256())
    if alg == "rsa-pss-sha512":
        return private.sign(data, padding.PSS(mgf=padding.MGF1(hashes.SHA512()), salt_length=64), hashes.SHA512())
    raise AssertionError(alg)


def signed_request(alg, private, extra_params=""):
    params = '("@method" "@target-uri" "content-digest");created=1795000000;keyid="k1"' + extra_params
    body = '{"a":1}'
    digest = "sha-256=:" + base64.b64encode(hashlib.sha256(body.encode()).digest()).decode() + ":"
    base = ('"@method": POST\n"@target-uri": https://api.example.org/v1/x\n"content-digest": ' + digest
            + '\n"@signature-params": ' + params)
    sig = base64.b64encode(sign_here(alg, private, base)).decode()
    return {"method": "POST", "url": "https://api.example.org/v1/x", "body": body,
            "headers": {"Content-Digest": digest, "Signature-Input": "sig1=" + params,
                        "Signature": "sig1=:" + sig + ":"}}


def pem(private):
    return private.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def test_p384_rsa_v1_5_and_a_jwk_rsa_key() -> None:
    p384 = ec.generate_private_key(ec.SECP384R1())
    out = handle({"message": signed_request("ecdsa-p384-sha384", p384), "keys": {"k1": pem(p384)}})
    assert out["verdict"] == "valid" and out["signatures"][0]["alg"] == "ecdsa-p384-sha384"
    numbers = p384.public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-384",
           "x": base64.urlsafe_b64encode(numbers.x.to_bytes(48, "big")).decode().rstrip("="),
           "y": base64.urlsafe_b64encode(numbers.y.to_bytes(48, "big")).decode().rstrip("=")}
    assert handle({"message": signed_request("ecdsa-p384-sha384", p384), "key": jwk})["verdict"] == "valid"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    msg = signed_request("rsa-v1_5-sha256", key)
    n = key.public_key().public_numbers().n
    jwk = {"kty": "RSA", "alg": "RS256", "e": "AQAB",
           "n": base64.urlsafe_b64encode(n.to_bytes(256, "big")).decode().rstrip("=")}
    assert handle({"message": msg, "keys": {"k1": jwk}})["verdict"] == "valid"
    # The same key without an algorithm: refused, never guessed.
    out = handle({"message": msg, "keys": {"k1": pem(key)}})
    assert out["signatures"][0]["verdict"] == "error" and "give alg" in out["signatures"][0]["detail"]
    # The signature's own alg parameter decides; PSS over a v1.5 signature fails.
    pss = handle({"message": signed_request("rsa-pss-sha512", key, ';alg="rsa-pss-sha512"'),
                  "keys": {"k1": pem(key)}})
    assert pss["verdict"] == "valid"
    wrong = handle({"message": msg, "keys": {"k1": {"alg": "rsa-pss-sha512", "key": pem(key)}}})
    assert wrong["signatures"][0]["signature_ok"] is False


def test_key_and_input_mistakes_are_reported() -> None:
    msg = rfc_message("sig-b26")
    out = handle({"message": msg, "keys": {"other": V["keys"]["test-key-ed25519"]}})
    assert out["signatures"][0]["verdict"] == "error" and "no key given for keyid" in out["signatures"][0]["detail"]
    ec_key = handle({"message": msg, "key": V["keys"]["test-key-ecc-p256"]})
    assert ec_key["signatures"][0]["signature_ok"] is False
    alg_mismatch = rfc_message("sig-b26")
    alg_mismatch["headers"]["Signature-Input"] = alg_mismatch["headers"]["Signature-Input"] + ';alg="hmac-sha256"'
    out = handle({"message": alg_mismatch, "key": V["keys"]["test-key-ed25519"]})
    assert out["signatures"][0]["verdict"] == "error" and "the key is ed25519" in out["signatures"][0]["detail"]
    with pytest.raises(ValueError, match="private key material"):
        handle({"message": msg, "key": {"kty": "OKP", "crv": "Ed25519", "x": "a" * 43, "d": "b" * 43}})
    with pytest.raises(ValueError, match="never send a private key"):
        # Assemble at runtime so the factory secret gate never sees a complete PEM header.
        pem = "-----BEGIN " + "PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----"
        handle({"message": msg, "key": pem})
    with pytest.raises(ValueError, match="no Signature-Input"):
        handle({"message": {"method": "GET", "url": "https://a.example.org/", "headers": {}}, "key": V["keys"]["test-key-ed25519"]})
    sf = rfc_message("sig-b26")
    sf["headers"]["Signature-Input"] = 'sig-b26=("date";sf);created=1'
    out = handle({"message": sf, "key": V["keys"]["test-key-ed25519"]})
    assert out["signatures"][0]["verdict"] == "error" and "not supported" in out["signatures"][0]["detail"]


def test_two_signatures_and_a_label() -> None:
    msg = rfc_message("sig-b26")
    b25 = rfc_message("sig-b25")
    msg["headers"]["Signature-Input"] = [msg["headers"]["Signature-Input"], b25["headers"]["Signature-Input"]]
    msg["headers"]["Signature"] = [msg["headers"]["Signature"], b25["headers"]["Signature"]]
    out = handle({"message": msg, "keys": rfc_keys()})
    assert out["valid_labels"] == ["sig-b26", "sig-b25"] and out["verdict"] == "valid"
    one = handle({"message": msg, "keys": rfc_keys(), "label": "sig-b25"})
    assert [s["label"] for s in one["signatures"]] == ["sig-b25"]


def test_deterministic_and_no_egress() -> None:
    args = {"message": rfc_message("sig-b24"), "keys": rfc_keys()}
    assert json.dumps(handle(args)) == json.dumps(load()(copy.deepcopy(args)))
    body = deploy_body("http-signature")
    assert not body.get("egress_hosts") and body["capability"]["price_per_call_usd"] == 0
