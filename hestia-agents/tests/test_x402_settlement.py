"""x402.settlement.check@v1 against two payments that settled on Base.

`x402_settlement_vectors.json` holds what https://mainnet.base.org returned on 2026-11-20 for two
real x402 settlements: Independent's auditor paying Attested $0.022 (tx 0xd8a41fb8…, block 52 165 064,
the same payment tests/test_x402_check.py takes its signature from), and the AIMarket hub's bridge
paying CoinMarketCap $0.01 (tx 0x24f175a2…, block 56 863 462). The fake RPC answers from them.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hestia_agents.manifests import deploy_body, handler_source

V = json.loads((Path(__file__).parent / "x402_settlement_vectors.json").read_text(encoding="utf-8"))
ATTESTED = "0xd8a41fb865beba51d9e795f556dc3b77e6ce5bb20a0dceb2e0691aa791997531"
CMC = "0x24f175a2f0c56d9e1f3d3e0933a19d7964d057d22d761db0e468ec2cdc25c1d3"
PAYER = "0x9d24d267cf8d9a8b9ed104b4856cde8830c266ef"
PAY_TO = "0xb73d8bc93b791510c4733c5c5ac2015a3c2930ec"
NONCE = "0x84428e7eae7b08cac1ec9186e338e14fa5056d9f62bb9d92e1ea927370b8e779"


class Reply:
    def __init__(self, result, status=200):
        self.status, self.error, self.headers = status, None, {}
        self.text = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.text)


def load(v=V):
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        call = json
        asked.append((url, call["method"]))
        name, params = call["method"], call["params"]
        if name == "eth_chainId":
            return Reply(v["chainId"])
        if name == "eth_blockNumber":
            return Reply(v["latest"])
        if name == "eth_getTransactionReceipt":
            return Reply((v["txs"].get(params[0]) or {}).get("receipt"))
        if name == "eth_getBlockByNumber" and params[0] == "finalized":
            return Reply({"number": v["finalized"]})
        if name == "eth_getBlockByNumber":
            block = next((t["block"] for t in v["txs"].values() if t["block"]["number"] == params[0]), None)
            return Reply(block)
        raise AssertionError(name)

    namespace = {"fetch": fetch}
    exec(compile(handler_source("x402-settlement"), "x402-settlement", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked


def test_a_real_settlement_bound_to_its_authorization_is_paid_and_final() -> None:
    handle, asked = load()
    out = handle({"tx": ATTESTED, "pay_to": PAY_TO, "amount": 22000, "payer": PAYER, "nonce": NONCE})
    assert out["verdict"] == "paid" and out["paid"] is True, out
    assert all(c["ok"] for c in out["checks"]) and [c["check"] for c in out["checks"]][-1] == "authorization"
    assert out["block"] == 52165064 and out["finalized"] is True and out["payer"] == PAYER
    assert out["confirmations"] == int(V["latest"], 16) - 52165064 + 1
    assert len(asked) == 5 and {u for u, _ in asked} == {"https://mainnet.base.org"}


def test_the_hub_bridges_payment_to_coinmarketcap_by_dollars() -> None:
    handle, _ = load()
    receipt = V["txs"][CMC]["receipt"]
    pay_to = "0x" + receipt["logs"][1]["topics"][2][-40:]
    out = handle({"tx": CMC, "pay_to": pay_to, "amount_usd": "0.01"})
    assert out["verdict"] == "paid" and out["amount"] == 10000 and out["amount_usd"] == "0.01"


@pytest.mark.parametrize(("bend", "verdict", "failed"), [
    ({"amount": 21999}, "not_paid", ["transfer"]),
    ({"amount_usd": "0.023"}, "not_paid", ["transfer"]),
    ({"pay_to": "0x" + "11" * 20}, "not_paid", ["transfer"]),
    ({"payer": "0x" + "22" * 20, "nonce": NONCE}, "not_paid", ["transfer", "authorization"]),
    ({"payer": PAYER, "nonce": "0x" + "33" * 32}, "not_paid", ["authorization"]),
])
def test_anything_that_does_not_match_is_not_paid(bend, verdict, failed) -> None:
    handle, _ = load()
    base = {"tx": ATTESTED, "pay_to": PAY_TO, "amount": 22000}
    if "amount_usd" in bend:
        base.pop("amount")  # amount wins when both are given
    out = handle({**base, **bend})
    assert out["verdict"] == verdict and out["paid"] is False
    assert [c["check"] for c in out["checks"] if not c["ok"]] == failed


def test_not_final_reverted_unknown_and_another_chain() -> None:
    later = copy.deepcopy(V)
    later["finalized"] = hex(52165063)
    handle, _ = load(later)
    assert handle({"tx": ATTESTED, "pay_to": PAY_TO, "amount": 22000})["verdict"] == "paid_not_final"
    reverted = copy.deepcopy(V)
    reverted["txs"][ATTESTED]["receipt"]["status"] = "0x0"
    assert load(reverted)[0]({"tx": ATTESTED, "pay_to": PAY_TO, "amount": 22000})["verdict"] == "failed"
    handle, _ = load()
    assert handle({"tx": "0x" + "ab" * 32, "pay_to": PAY_TO, "amount": 22000})["verdict"] == "pending"
    other = copy.deepcopy(V)
    other["chainId"] = "0x1"
    assert load(other)[0]({"tx": ATTESTED, "pay_to": PAY_TO, "amount": 22000})["verdict"] == "wrong_chain"


def test_a_block_that_is_not_canonical_is_not_paid() -> None:
    forked = copy.deepcopy(V)
    forked["txs"][ATTESTED]["block"]["hash"] = "0x" + "00" * 32
    out = load(forked)[0]({"tx": ATTESTED, "pay_to": PAY_TO, "amount": 22000})
    assert out["verdict"] == "not_paid" and "canonical_block" in [c["check"] for c in out["checks"] if not c["ok"]]


def test_input_is_checked() -> None:
    handle, asked = load()
    for payload in ({}, {"tx": ATTESTED}, {"tx": "0x12", "pay_to": PAY_TO, "amount": 1},
                    {"tx": ATTESTED, "pay_to": PAY_TO}, {"tx": ATTESTED, "pay_to": PAY_TO, "amount": "1.5"},
                    {"tx": ATTESTED, "pay_to": PAY_TO, "amount_usd": "0.0000001"},
                    {"tx": ATTESTED, "pay_to": PAY_TO, "amount": 1, "nonce": NONCE},
                    {"tx": ATTESTED, "pay_to": PAY_TO, "amount": 1, "network": "ethereum"}):
        with pytest.raises(ValueError):
            handle(payload)
    assert asked == []


def test_the_manifest_reaches_the_two_public_rpcs_only() -> None:
    assert deploy_body("x402-settlement")["egress_hosts"] == ["mainnet.base.org", "sepolia.base.org"]
