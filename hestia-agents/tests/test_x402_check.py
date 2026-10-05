"""x402.authorization.check@v1 against the chain and against eth-account.

The anchor is a payment that actually settled: the transferWithAuthorization Independent's
auditor sent on Base on 2026-10-04 (tx 0xd8a41fb8…, block 52165064). USDC accepted it, so the
contract's own checks passed on exactly these fields. The seven domain separators were read
from the USDC contracts (DOMAIN_SEPARATOR()). The signed vectors are eth-account's, made
with throwaway keys nobody kept.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest

from hestia_agents.manifests import handler_source

VECTORS = json.loads((Path(__file__).parent / "x402_vectors.json").read_text(encoding="utf-8"))
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

SETTLED = {  # calldata of tx 0xd8a41fb865beba51d9e795f556dc3b77e6ce5bb20a0dceb2e0691aa791997531
    "from": "0x9d24d267cf8d9a8b9ed104b4856cde8830c266ef",
    "to": "0xb73d8bc93b791510c4733c5c5ac2015a3c2930ec",
    "value": "22000",
    "validAfter": "0",
    "validBefore": "1791120073",
    "nonce": "0x84428e7eae7b08cac1ec9186e338e14fa5056d9f62bb9d92e1ea927370b8e779",
}
SETTLED_R = "b909a9345301f4942d14fc97f72306b8ae6e4077431cb8e950194196101b3458"
SETTLED_S = "2f9cf1604c72db4a5a87ade62949449a2eff957f1d58a11954438dac229aa16f"
SETTLED_SIG = "0x" + SETTLED_R + SETTLED_S + "1c"  # v = 28
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
ON_CHAIN_SEPARATORS = {
    1: "0x06c37168a7db5138defc7866392bb87a741f9b3d104deb5094588ce041cae335",
    10: "0x26d9c34bb1a1c312f69c53b2d93b8be20faafba63af2438c6811713c9b1f933f",
    137: "0xcaa2ce1a5703ccbe253a34eb3166df60a705c561b44b192061e28f2a985be2ca",
    8453: "0x02fa7265e7c5d81118673727957699e4d68f74cd74b7db77da710fe8a2c7834f",
    42161: "0x08d11903f8419e68b1b8721bcbe2e9fc68569122a77ef18c216f10b3b5112c78",
    43114: "0xbbea200329a938bc3438984a49cb0732e66d66d7bd59c127abacc1710e77f7b3",
    84532: "0x71f17a3b2ff373b803d70a5a07c046c1a2bc8e89c09ef722fcb047abe94c9818",
}


@pytest.fixture(scope="module")
def ns():
    namespace: dict = {}
    exec(compile(handler_source("x402-check"), "x402-check", "exec"), namespace)  # noqa: S102
    return namespace


@pytest.fixture(scope="module")
def handle(ns):
    return ns["handle"]


def settled(**extra):
    return {"authorization": dict(SETTLED), "signature": SETTLED_SIG, "network": "base", **extra}


def by_name(out):
    return {c["check"]: c for c in out["checks"]}


# ------------------------------------------------------------------ the settled payment


def test_the_payment_base_accepted_checks_out(handle) -> None:
    requirements = {"scheme": "exact", "network": "base", "maxAmountRequired": "22000",
                    "payTo": SETTLED["to"], "asset": BASE_USDC,
                    "extra": {"name": "USD Coin", "version": "2", "nonce": SETTLED["nonce"]}}
    out = handle(settled(requirements=requirements, now=1791119999))
    assert out["verdict"] == "valid", out["checks"]
    assert out["signer"] == "0x9d24D267Cf8D9A8b9Ed104b4856cDe8830C266eF"
    assert out["domain_separator"] == ON_CHAIN_SEPARATORS[8453]
    assert out["token"] == "USDC on Base" and out["value_usdc"] == "0.022"
    assert {c["check"] for c in out["checks"]} == {
        "v", "low_s", "signer", "domain", "window", "pay_to", "amount", "asset", "network",
        "nonce_binding"}


@pytest.mark.parametrize("chain_id", sorted(ON_CHAIN_SEPARATORS))
def test_domain_separators_match_the_contracts(ns, chain_id: int) -> None:
    token, name, _ = ns["KNOWN_TOKENS"][chain_id]
    separator = ns["domain_separator"](name, "2", chain_id, bytes.fromhex(token[2:]))
    assert "0x" + separator.hex() == ON_CHAIN_SEPARATORS[chain_id]


def test_the_same_payment_as_an_x_payment_header(handle) -> None:
    header = {"x402Version": 1, "scheme": "exact", "network": "base",
              "payload": {"signature": SETTLED_SIG, "authorization": SETTLED}}
    encoded = base64.b64encode(json.dumps(header).encode()).decode()
    assert handle({"x_payment": encoded})["verdict"] == "valid"
    urlsafe = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    assert handle({"x_payment": urlsafe})["signer"].lower() == SETTLED["from"]
    assert handle({"payment": header})["verdict"] == "valid"


def test_calldata_v_r_s_and_caip2_network(handle) -> None:
    out = handle({"authorization": SETTLED, "v": 28, "r": "0x" + SETTLED_R, "s": "0x" + SETTLED_S,
                  "network": "eip155:8453"})
    assert out["verdict"] == "valid"


# ------------------------------------------------------------------ eth-account vectors


@pytest.mark.parametrize(
    "vector", VECTORS["signed"], ids=lambda v: v["kind"][:8] + str(v["chain_id"])
)
def test_eth_account_signatures_recover(handle, vector) -> None:
    out = handle({"authorization": vector["authorization"], "signature": vector["signature"],
                  "domain": {"chainId": vector["chain_id"], "verifyingContract": vector["token"],
                             "name": vector["name"], "version": "2"},
                  "primary_type": vector["kind"]})
    assert out["signer"] == vector["signer"]
    assert out["digest"] == vector["digest"]
    assert out["domain_separator"] == vector["domain_separator"]
    assert out["verdict"] == "valid", out["checks"]


def test_a_signature_over_the_wrong_name_is_caught(handle) -> None:
    vector = VECTORS["wrong_name_on_base"]
    out = handle({"authorization": vector["authorization"], "signature": vector["signature"],
                  "network": "base", "domain": {"name": "USDC", "version": "2"}})
    checks = by_name(out)
    assert checks["signer"]["ok"] is True, "it IS this key's signature, over the wrong domain"
    assert checks["domain"]["ok"] is False and "'USD Coin'" in checks["domain"]["detail"]
    assert out["verdict"] == "invalid"
    # Checked against the real domain instead, it is somebody else's signature.
    plain = handle({"authorization": vector["authorization"], "signature": vector["signature"],
                    "network": "base"})
    assert by_name(plain)["signer"]["ok"] is False


# ------------------------------------------------------------------ what USDC would refuse


def test_high_s_recovers_but_usdc_would_revert(handle) -> None:
    high_s = format(N - int(SETTLED_S, 16), "064x")
    sig = "0x" + SETTLED_R + high_s + "1b"  # the twin signature: n - s and the other v
    out = handle(settled(signature=sig))
    checks = by_name(out)
    assert checks["signer"]["ok"] is True
    assert checks["low_s"]["ok"] is False and out["verdict"] == "invalid"


def test_v_zero_or_one_is_flagged(handle) -> None:
    out = handle(settled(signature=SETTLED_SIG[:-2] + "01"))
    checks = by_name(out)
    assert checks["signer"]["ok"] is True and checks["v"]["ok"] is False


def test_any_altered_field_changes_the_signer(handle) -> None:
    for field, value in (("value", "22001"), ("to", "0x" + "11" * 20),
                         ("validBefore", "1791120074"), ("nonce", "0x" + "00" * 32)):
        auth = dict(SETTLED, **{field: value})
        out = handle({"authorization": auth, "signature": SETTLED_SIG, "network": "base"})
        assert by_name(out)["signer"]["ok"] is False, field


def test_a_different_chain_is_a_different_signer(handle) -> None:
    out = handle({"authorization": SETTLED, "signature": SETTLED_SIG, "network": "base-sepolia",
                  "domain": {"verifyingContract": BASE_USDC, "name": "USD Coin", "version": "2"}})
    assert by_name(out)["signer"]["ok"] is False


# ------------------------------------------------------------------ what the seller asked


@pytest.mark.parametrize(
    ("change", "check"),
    [
        ({"payTo": "0x" + "22" * 20}, "pay_to"),
        ({"maxAmountRequired": "22001"}, "amount"),
        ({"asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e"}, "asset"),
        ({"network": "base-sepolia"}, "network"),
        ({"extra": {"nonce": "0x" + "ab" * 32}}, "nonce_binding"),
    ],
)
def test_each_requirement_mismatch_fails_its_check(handle, change, check) -> None:
    requirements = {"network": "base", "maxAmountRequired": "22000", "payTo": SETTLED["to"],
                    "asset": BASE_USDC, **change}
    # What the buyer signed for (the domain) next to what the seller asked (requirements).
    out = handle(settled(requirements=requirements, domain={"verifyingContract": BASE_USDC}))
    assert by_name(out)[check]["ok"] is False and check in out["failed"]


def test_overpaying_passes_and_says_so(handle) -> None:
    out = handle(settled(requirements={"amount": "21000"}))
    assert by_name(out)["amount"]["ok"] is True
    assert "1000 units more" in by_name(out)["amount"]["detail"]


@pytest.mark.parametrize(("now", "ok", "word"), [(0, False, "not valid yet"),
                                                 (1791120073, False, "expired"),
                                                 (1791120072, True, "open")])
def test_window(handle, now, ok, word) -> None:
    check = by_name(handle(settled(now=now)))["window"]
    assert check["ok"] is ok and word in check["detail"]


def test_without_now_the_window_is_named_not_judged(handle) -> None:
    out = handle(settled())
    assert by_name(out)["window"]["ok"] is None and out["verdict"] == "valid"
    assert "the nonce is unused on chain (authorizationState)" in out["not_checked"]


# ------------------------------------------------------------------ refusals


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ({"authorization": SETTLED, "signature": SETTLED_SIG}, "network"),
        ({"authorization": SETTLED, "signature": "0x" + SETTLED_R + SETTLED_S, "network": "base"},
         "64 bytes"),
        ({"authorization": SETTLED, "network": "base"}, "signature"),
        ({"authorization": SETTLED, "signature": SETTLED_SIG, "network": "dogechain"},
         "not a known EVM network"),
        ({"authorization": SETTLED, "signature": SETTLED_SIG, "network": "base",
          "domain": {"verifyingContract": "0x" + "33" * 20}}, "domain.name"),
        ({"authorization": dict(SETTLED, value="-1"), "signature": SETTLED_SIG,
          "network": "base"}, "uint256"),
        ({"authorization": dict(SETTLED, to="0xB73d8bc93b791510c4733c5c5ac2015a3c2930eC"),
          "signature": SETTLED_SIG, "network": "base"}, "EIP-55"),
        ({"x_payment": "!!!"}, "x_payment does not decode"),
        ({"payment": {"x402Version": 1}}, "payload"),
        ({"authorization": SETTLED, "signature": SETTLED_SIG, "network": "base",
          "primary_type": "Permit"}, "primary_type"),
    ],
)
def test_bad_requests_say_why(handle, payload, match) -> None:
    with pytest.raises(ValueError, match=match):
        handle(payload)


def test_a_check_is_fast_and_reproducible(handle) -> None:
    started = time.perf_counter()
    first = handle(settled(now=1791119999))
    assert time.perf_counter() - started < 0.5
    assert handle(settled(now=1791119999)) == first
