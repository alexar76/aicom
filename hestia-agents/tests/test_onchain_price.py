"""crypto.price.onchain@v1 against Base as it was at block 60 400 000.

`onchain_price_vectors.json` holds what https://mainnet.base.org answered on 2026-11-21 for every
JSON-RPC batch the agent sends for ETH (600 s window), BTC (1800 s), BTC over a day, and the
WETH/USDC 0.05 % pool by address, all pinned to block 60 400 000. The fake RPC answers from it.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import copy
import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from hestia_agents.manifests import AGENTS, deploy_body, handler_source

V = json.loads((Path(__file__).parent / "onchain_price_vectors.json").read_text(encoding="utf-8"))
BLOCK = 60400000
WETH_USDC_005 = "0xd0b53d9277642d899df5c87a3966a349a798f224"
WETH_USDC_03 = "0x6c561b446416e1a00e8e93e221854d6ea4171372"


class Reply:
    def __init__(self, payload, status=200):
        self.status, self.error, self.headers = status, None, {}
        self.text = json.dumps(payload)

    @property
    def ok(self):
        return 200 <= self.status < 300

    def json(self):
        return json.loads(self.text)


def load(rpc=None, tamper=None):
    rpc = V["rpc"] if rpc is None else rpc
    asked = []

    def fetch(url, method="GET", headers=None, body=None, json=None):  # noqa: A002
        assert url == "https://mainnet.base.org" and method == "POST"
        key = __import__("json").dumps(json, sort_keys=True)
        asked.append(json)
        answer = copy.deepcopy(rpc[key])
        if tamper:
            answer = tamper(json, answer)
        return Reply(answer)

    namespace = {"fetch": fetch}
    exec(compile(handler_source("onchain-price"), "onchain-price", "exec"), namespace)  # noqa: S102 — our own source
    return namespace["handle"], asked


def test_eth_is_the_time_weighted_average_of_the_deepest_pool_that_traded() -> None:
    handle, asked = load()
    out = handle({"asset": "ETH", "block": BLOCK, "window_s": 600})
    assert out["price_usd"] == "1700.931300" and out["spot_usd"] == "1695.554580"
    assert out["pool"] == WETH_USDC_03 and out["fee_pct"] == "0.3"
    assert out["block"] == BLOCK and out["window_s"] == 600 and out["quote"] == "USDC"
    assert all(c["ok"] for c in out["checks"]), out["checks"]
    assert [t["fee"] for t in out["tiers"]] == [100, 500, 3000, 10000]
    # The 1 % pool did not trade in those ten minutes: listed, never chosen, out of the cross-check.
    assert [t["traded"] for t in out["tiers"]] == [True, True, True, False]
    # Two fetches: the head, then one batch of every read; the sandbox allows six.
    assert len(asked) == 2 and len(asked[1]) == 16
    pinned = {call["params"][1] for call in asked[1]}
    assert pinned == {hex(BLOCK)}


def test_btc_inverts_the_pool_because_usdc_is_token0() -> None:
    handle, _ = load()
    out = handle({"asset": "BTC", "block": BLOCK})
    assert out["price_usd"] == "60480.157376" and out["fee_pct"] == "0.05"
    assert out["token"] == "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf"
    assert all(c["ok"] for c in out["checks"])


def test_the_price_follows_from_the_recorded_tick_accumulators() -> None:
    """Recompute the ETH answer from the raw observe() words, independently of the handler."""
    handle, asked = load()
    out = handle({"asset": "ETH", "block": BLOCK, "window_s": 600})
    batch = asked[1]
    answers = {a["id"]: a for a in V["rpc"][json.dumps(batch, sort_keys=True)]}
    index = next(i for i, call in enumerate(batch) if call["params"][0]["to"] == WETH_USDC_03
                 and call["params"][0]["data"].startswith("0x883bdbfd"))
    words = [answers[index + 1]["result"][2:][i:i + 64] for i in range(0, 64 * 6, 64)]

    def signed(word):
        value = int(word, 16)
        return value - (1 << 256) if value >= 1 << 255 else value

    old, new = signed(words[3]), signed(words[4])
    mean_tick = (new - old) / 600
    price = math.pow(1.0001, mean_tick) * 1e12  # WETH 18 decimals, USDC 6
    assert abs(price - float(out["price_usd"])) / price < 1e-9


def test_a_day_window_falls_back_to_the_pools_whose_oracle_reaches_that_far() -> None:
    handle, _ = load()
    out = handle({"asset": "BTC", "block": BLOCK, "window_s": 86400})
    assert out["price_usd"] == "58448.828715" and out["fee_pct"] == "0.3"
    refused = [t for t in out["tiers"] if t["twap_usd"] is None]
    assert len(refused) == 3 and all("observe refused" in t["note"] for t in refused)


def test_any_pool_by_address_prices_token0_in_token1_and_back() -> None:
    handle, asked = load()
    out = handle({"pool": WETH_USDC_005, "block": BLOCK})
    assert out["price"] == "1700.053984195653" and out["price_unit"] == "USDC per WETH"
    assert out["token0"]["symbol"] == "WETH" and out["token1"]["decimals"] == 6
    assert Decimal(out["price"]) * Decimal(out["inverse"]) == pytest.approx(1, rel=1e-9)
    assert [c["check"] for c in out["checks"]] == ["chain", "factory_pool"] and all(c["ok"] for c in out["checks"])
    assert len(asked) == 3


def test_a_contract_the_factory_did_not_deploy_is_refused() -> None:
    def other_pool(call, answer):
        if isinstance(call, list) and call[0]["method"] == "eth_call" and call[0]["params"][0]["data"].startswith("0x1698ee82"):
            answer = copy.deepcopy(answer)
            next(a for a in answer if a["id"] == 1)["result"] = "0x" + "0" * 24 + "11" * 20
        return answer

    handle, _ = load(tamper=other_pool)
    with pytest.raises(ValueError, match="not a pool the Uniswap v3 factory"):
        handle({"pool": WETH_USDC_005, "block": BLOCK})


def test_an_rpc_error_is_an_error_not_a_zero() -> None:
    def rate_limited(call, answer):
        if isinstance(call, list) and len(call) == 16:
            answer = copy.deepcopy(answer)
            answer[5] = {"jsonrpc": "2.0", "id": answer[5]["id"], "error": {"code": -32016, "message": "over rate limit"}}
        return answer

    handle, _ = load(tamper=rate_limited)
    with pytest.raises(RuntimeError, match="over rate limit"):
        handle({"asset": "ETH", "block": BLOCK, "window_s": 600})


def test_a_pool_whose_factory_entry_differs_is_not_used_for_an_asset() -> None:
    def moved(call, answer):
        if isinstance(call, list) and len(call) == 16:
            answer = copy.deepcopy(answer)
            for a in answer:
                if a["id"] == 9:  # getPool for the 0.3 % tier
                    a["result"] = "0x" + "0" * 24 + "22" * 20
        return answer

    handle, _ = load(tamper=moved)
    out = handle({"asset": "ETH", "block": BLOCK, "window_s": 600})
    assert out["pool"] != WETH_USDC_03
    assert not next(c for c in out["checks"] if c["check"] == "factory_pool_3000")["ok"]


def test_same_block_same_answer() -> None:
    handle, _ = load()
    first = json.dumps(handle({"asset": "ETH", "block": BLOCK, "window_s": 600}), sort_keys=True)
    for _ in range(3):
        assert json.dumps(handle({"asset": "ETH", "block": BLOCK, "window_s": 600}), sort_keys=True) == first


@pytest.mark.parametrize("payload, message", [
    ("ETH", "send an object"),
    ({}, "give asset"),
    ({"asset": "DOGE"}, "give asset"),
    ({"asset": "ETH", "window_s": 30}, "between 60 and 86400"),
    ({"asset": "ETH", "window_s": "half an hour"}, "whole number"),
    ({"asset": "ETH", "window_s": True}, "whole number"),
    ({"asset": "ETH", "block": "yesterday"}, "block number"),
    ({"pool": "0x1234"}, "0x address"),
])
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked = load()
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_declares_only_the_base_rpc_and_is_free() -> None:
    meta = AGENTS["onchain-price"]
    assert meta["egress_hosts"] == ["mainnet.base.org"] and meta["price_per_call_usd"] == 0
    assert meta["sandbox_only"] is True
    body = deploy_body("onchain-price")
    assert body["capability"]["capability_id"] == "crypto.price.onchain@v1"
    handle, _ = load()
    assert handle(meta["probe"])["price_usd"] == "1700.931300"
