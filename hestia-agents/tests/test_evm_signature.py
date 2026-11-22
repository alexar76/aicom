"""evm.signature.verify@v1: keys by recovery, smart wallets by the chain.

Offline: the EIP-712 specification's own Mail example (digest, domain separator, struct hash and the
signature by its "Cow" key), its EIP-2098 compact form, and an EIP-191 personal_sign signature made
by tests/make_evm_signature_fixtures.py with the `cryptography` library.

Recorded (`evm_signature_vectors.json`, scripts/record_fetches.py, 2026-11-21): two smart wallets
that paid USDC on Base with transferWithAuthorization(..., bytes signature), found by scanning USDC's
AuthorizationUsed logs for contract authorizers, checked at the block before their payment:
  - 0x5918…271d, an ERC-1167 proxy wallet, tx 0x8b4549…5368, block 60 530 329;
  - 0x7112…7fe9, an EOA with an EIP-7702 delegate, tx 0xf2beba…c8b, block 60 530 331;
and the first one's signature over the same authorization for one unit more, which it refuses.
No ERC-6492 signature was found on chain; its unwrapping and its path are tested on built input.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import json
from pathlib import Path

import pytest
from replay import load

from hestia_agents.manifests import AGENTS, deploy_body

HERE = Path(__file__).parent
V = json.loads((HERE / "evm_signature_vectors.json").read_text(encoding="utf-8"))
F = json.loads((HERE / "evm_signature_fixtures.json").read_text(encoding="utf-8"))
SLUG = "evm-signature"
COW = "0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826"
MAIL_SIG = "0x4355c47d63924e8a72e509b65029052eb6c299d53a04e167c5775fd466751c9d07299936d304c153f6443dfa05f40ff007d72911b6f72307f996231605b915621c"
MAIL = {
    "types": {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Person": [{"name": "name", "type": "string"}, {"name": "wallet", "type": "address"}],
        "Mail": [
            {"name": "from", "type": "Person"},
            {"name": "to", "type": "Person"},
            {"name": "contents", "type": "string"},
        ],
    },
    "primaryType": "Mail",
    "domain": {
        "name": "Ether Mail",
        "version": "1",
        "chainId": 1,
        "verifyingContract": "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC",
    },
    "message": {
        "from": {"name": "Cow", "wallet": COW},
        "to": {"name": "Bob", "wallet": "0xbBbBBBBbbBBBbbbBbbBbbbbBBbBbbbbBbBbbBBbB"},
        "contents": "Hello, Bob!",
    },
}


def run(payload, fetched=None, extra=None):
    handle, asked, ns = load(SLUG, fetched or {}, extra=extra)
    return handle(payload), asked, ns


def rpc_key(url, calls):
    body = json.dumps(
        [{"jsonrpc": "2.0", "id": i, "method": m, "params": p} for i, (m, p) in enumerate(calls)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return json.dumps(
        ["POST", url, [["content-type", "application/json"]], body],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def rpc_reply(results):
    return {
        "status": 200,
        "headers": {},
        "text": json.dumps(
            [{"jsonrpc": "2.0", "id": i, "result": r} for i, r in enumerate(results)]
        ),
    }


def test_the_eip712_mail_example_recovers_to_cow_with_no_network() -> None:
    out, asked, _ = run({"signer": COW, "signature": MAIL_SIG, "typed_data": MAIL})
    assert asked == [] and out["valid"] is True and out["method"] == "ecrecover"
    assert out["digest"] == "0xbe609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2"
    assert (
        out["domain_separator"]
        == "0xf2cee375fa42b42143804025fc449deafd50cc031ca257e0b194a650a912090f"
    )
    assert (
        out["struct_hash"] == "0xc52c0ee5d84264471806290a3f2c4cecfc5490626bf912d01f240d7a274b371e"
    )


def test_the_eip712_type_string_lists_dependencies_sorted() -> None:
    _, _, ns = run({"signer": COW, "signature": MAIL_SIG, "typed_data": MAIL})
    assert (
        ns["encode_type"](MAIL["types"], "Mail")
        == "Mail(Person from,Person to,string contents)Person(string name,address wallet)"
    )


def test_the_eip2098_compact_form_verifies_the_same() -> None:
    raw = bytes.fromhex(MAIL_SIG[2:])
    r, s, v = raw[:32], int.from_bytes(raw[32:64], "big"), raw[64]
    compact = r + ((v - 27) << 255 | s).to_bytes(32, "big")
    out, asked, _ = run(
        {
            "signer": COW,
            "signature": "0x" + compact.hex(),
            "hash": "0xbe609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2",
        }
    )
    assert out["valid"] and out["method"] == "ecrecover" and asked == []


def test_a_personal_message_signed_by_another_library_recovers() -> None:
    out, asked, _ = run(
        {"signer": F["signer"], "signature": F["signature"], "message": F["message"]}
    )
    assert out["valid"] and asked == [] and out["digest"] == F["digest"]
    assert out["signed"].startswith("EIP-191 personal message")


def test_the_proxy_smart_wallet_payment_verifies_by_erc1271() -> None:
    case = V["proxy_wallet_1271"]
    out, asked, _ = run(case["payload"], case["fetched"])
    assert out["valid"] and out["method"] == "erc1271" and out["signer_has_code"] is True
    assert out["block"] == 60530328 and len(asked) == 1  # a pinned block: one batch
    assert (
        out["domain_separator"]
        == "0x02fa7265e7c5d81118673727957699e4d68f74cd74b7db77da710fe8a2c7834f"
    )  # USDC on Base
    assert "recovered" not in out  # 71 bytes: not a key's (r, s, v) form, so the chain decides


def test_the_eip7702_wallet_names_its_delegate() -> None:
    case = V["eip7702_wallet"]
    out, _, _ = run(case["payload"], case["fetched"])
    assert out["valid"] and out["method"] == "erc1271"
    assert out["eip7702_delegate"] == "0x7702cb554e6bFb442cb743A7dF23154544a7176C"


def test_the_same_wallet_refuses_another_amount() -> None:
    case = V["proxy_wallet_other_amount"]
    out, _, _ = run(case["payload"], case["fetched"])
    assert out["valid"] is False and out["verdict"] == "invalid" and out["method"] == "erc1271"
    assert "does not accept" in out["detail"]


def test_a_signature_that_does_not_recover_to_an_address_without_code_is_invalid() -> None:
    url = "https://base-rpc.hestia.modelmarket.dev"
    payload = {
        "signer": "0x0000000000000000000000000000000000000001",
        "signature": MAIL_SIG,
        "hash": "0xbe609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2",
        "block": 100,
    }
    handle, _, ns = load(SLUG, {})
    data = (
        "0x"
        + "".join(ns["VALIDATOR_BYTECODE"])
        + ns["abi_address_bytes32_bytes"](
            bytes.fromhex("00" * 19 + "01"),
            bytes.fromhex(payload["hash"][2:]),
            bytes.fromhex(MAIL_SIG[2:]),
        ).hex()
    )
    calls = [
        ("eth_chainId", []),
        ("eth_getCode", ["0x" + "00" * 19 + "01", "0x64"]),
        ("eth_call", [{"data": data}, "0x64"]),
    ]
    out, asked, _ = run(payload, {rpc_key(url, calls): rpc_reply(["0x2105", "0x", "0x00"])})
    assert out["valid"] is False and out["method"] == "ecrecover" and out["recovered"] == COW
    assert "no code" in out["detail"]


def test_an_erc6492_wrapped_signature_is_unwrapped_and_sent_whole_to_the_validator() -> None:
    _, _, ns = run({"signer": COW, "signature": MAIL_SIG, "typed_data": MAIL})
    factory = bytes.fromhex("11" * 20)
    calldata = bytes.fromhex("deadbeef") + b"\x00" * 60
    inner = bytes.fromhex(MAIL_SIG[2:]) + b"\x01"  # 66 bytes: no key form, so the chain decides
    body = (
        b"\x00" * 12
        + factory
        + (96).to_bytes(32, "big")
        + (96 + 32 + 64).to_bytes(32, "big")
        + len(calldata).to_bytes(32, "big")
        + calldata
        + len(inner).to_bytes(32, "big")
        + inner
        + b"\x00" * (-len(inner) % 32)
    )
    wrapped = body + bytes.fromhex("6492" * 16)
    assert ns["unwrap_6492"](wrapped) == (factory, calldata, inner)
    assert ns["unwrap_6492"](wrapped[:-1] + b"\x93") is None
    signer = "0x" + "22" * 20
    digest = bytes.fromhex("be609aee343fb3c4b28e1df9e632fca64fcfaede20f02e86244efddf30957bd2")
    data = (
        "0x"
        + "".join(ns["VALIDATOR_BYTECODE"])
        + ns["abi_address_bytes32_bytes"](bytes.fromhex("22" * 20), digest, wrapped).hex()
    )
    calls = [
        ("eth_chainId", []),
        ("eth_getCode", [signer, "0xa"]),
        ("eth_call", [{"data": data}, "0xa"]),
    ]
    out, _, _ = run(
        {
            "signer": signer,
            "signature": "0x" + wrapped.hex(),
            "hash": "0x" + digest.hex(),
            "block": 10,
        },
        {rpc_key("https://base-rpc.hestia.modelmarket.dev", calls): rpc_reply(["0x2105", "0x", "0x01"])},
    )
    assert (
        out["valid"]
        and out["method"] == "erc6492"
        and out["erc6492"]["factory"].lower() == "0x" + "11" * 20
    )


def test_an_rpc_on_another_chain_is_an_error_not_an_answer() -> None:
    url = "https://base-rpc.hestia.modelmarket.dev"
    payload = {"signer": "0x" + "22" * 20, "signature": "0x" + "00" * 70, "hash": "0x" + "00" * 32}
    head = rpc_key(url, [("eth_chainId", []), ("eth_blockNumber", [])])
    with pytest.raises(RuntimeError, match="serves chain 1"):
        run(payload, {head: rpc_reply(["0x1", "0x10"])})


@pytest.mark.parametrize(
    "kind, value, word",
    [
        ("int8", -1, "ff" * 32),
        ("uint8", 255, "00" * 31 + "ff"),
        ("bool", True, "00" * 31 + "01"),
        ("bytes4", "0xdeadbeef", "deadbeef" + "00" * 28),
        ("uint256", "0x10", "00" * 31 + "10"),
    ],
)
def test_eip712_atomic_encoding(kind, value, word) -> None:
    _, _, ns = run({"signer": COW, "signature": MAIL_SIG, "typed_data": MAIL})
    assert ns["encode_value"]({}, kind, value, "v").hex() == word


@pytest.mark.parametrize(
    "kind, value, message",
    [
        ("uint8", 256, "does not fit"),
        ("int8", -129, "does not fit"),
        ("bool", 1, "true or false"),
        ("bytes4", "0xdead", "4 bytes"),
        ("uint7", 1, "not a Solidity integer"),
        ("Foo", 1, "unknown type"),
    ],
)
def test_eip712_refuses_values_that_do_not_fit(kind, value, message) -> None:
    _, _, ns = run({"signer": COW, "signature": MAIL_SIG, "typed_data": MAIL})
    with pytest.raises(ValueError, match=message):
        ns["encode_value"]({}, kind, value, "v")


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"signature": MAIL_SIG, "hash": "0x" + "00" * 32}, "signer"),
        ({"signer": COW, "signature": "0x1234", "hash": "0x" + "00" * 32}, "64 to 16384"),
        ({"signer": COW, "signature": MAIL_SIG}, "exactly one"),
        ({"signer": COW, "signature": MAIL_SIG, "hash": "0x00", "message": "x"}, "exactly one"),
        (
            {
                "signer": COW.lower().replace("d", "D", 1),
                "signature": MAIL_SIG,
                "hash": "0x" + "00" * 32,
            },
            "checksum",
        ),
        (
            {"signer": COW, "signature": MAIL_SIG, "hash": "0x" + "00" * 32, "network": "solana"},
            "network",
        ),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_reaches_only_the_three_rpcs_and_the_probe_needs_none() -> None:
    meta = AGENTS[SLUG]
    assert deploy_body(SLUG)["egress_hosts"] == [
        "base-rpc.hestia.modelmarket.dev",
        "mainnet.base.org",
        "sepolia.base.org",
        "ethereum-rpc.publicnode.com",
    ]
    out, asked, _ = run(meta["probe"])
    assert out["valid"] and asked == []
