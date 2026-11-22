"""crypto.price.onchain@v1 against Base as it was at block 60 400 000.

`onchain_price_vectors.json` holds what https://mainnet.base.org answered on 2026-11-21 (served to the
agent here as the hearth's pool, base-rpc.hestia.modelmarket.dev: the same JSON-RPC answers) for every
JSON-RPC batch the agent sends for ETH (600 s window), BTC (1800 s), BTC over a day, and the
WETH/USDC 0.05 % pool by address, all pinned to block 60 400 000. The fake RPC answers from it.
`token_degen`, `token_eurc` and `token_aero` hold what https://base-rpc.publicnode.com answered on
2026-11-22 at 16:30Z (keyed under the pool's name) for a token by address at block 60 800 000
(scripts/record_fetches.py; the token's reads go through Multicall3): DEGEN, whose traded USDC pool
is far too thin and whose WETH pool prices it; EURC, whose deep USDC pool did not trade in the
window, so its price is that pool's last trade; and AERO, priced through WETH with the USDC route as
the cross-check.
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
        assert url == "https://base-rpc.hestia.modelmarket.dev" and method == "POST"
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


def test_manifest_declares_the_pool_and_the_public_rpc_and_is_free() -> None:
    meta = AGENTS["onchain-price"]
    assert meta["egress_hosts"] == ["base-rpc.hestia.modelmarket.dev", "base-rpc.publicnode.com"]
    assert meta["price_per_call_usd"] == 0
    assert meta["sandbox_only"] is True
    body = deploy_body("onchain-price")
    assert body["capability"]["capability_id"] == "crypto.price.onchain@v1"
    handle, _ = load()
    assert handle(meta["probe"])["price_usd"] == "1700.931300"


def _token(case, tamper=None, payload=None):
    from replay import load as replay

    handle, asked, _ = replay("onchain-price", copy.deepcopy(V[case]["fetched"]), tamper)
    return handle(payload or V[case]["payload"]), asked


def _ok(out):
    return {c["check"]: c["ok"] for c in out["checks"]}


# Multicall3's aggregate3, read and written here independently of the handler.
def _w(text, i):
    return int(text[64 * i:64 * i + 64], 16)


def _decode(result):
    text = result[2:]
    start = _w(text, 0) // 32
    out = []
    for k in range(_w(text, start)):
        item = start + 1 + _w(text, start + 1 + k) // 32
        data = item + _w(text, item + 1) // 32
        out.append((_w(text, item) == 1, text[64 * (data + 1):64 * (data + 1) + 2 * _w(text, data)]))
    return out


def _encode(entries):
    heads, tails, offset = [], [], 32 * len(entries)
    for ok, data in entries:
        body = (format(int(ok), "064x") + format(64, "064x") + format(len(data) // 2, "064x")
                + data + "0" * ((64 - len(data) % 64) % 64))
        heads.append(format(offset, "064x"))
        tails.append(body)
        offset += len(body) // 2
    return "0x" + format(32, "064x") + format(len(entries), "064x") + "".join(heads) + "".join(tails)


def _multicall_reply(raw):
    """The JSON-RPC answers of a reply, and the index of the aggregate3 answer in it (or None)."""
    answers = json.loads(raw["text"])
    if not isinstance(answers, list):
        return answers, None
    for i, a in enumerate(answers):
        result = a.get("result") or ""
        if len(result) > 130 and int(result[2:66], 16) == 32:
            return answers, i
    return answers, None


def _edit_multicall(edit, which):
    """A tamper that rewrites the aggregate3 entries of the token batch ("token") or pool batch."""
    def tamper(url, raw):
        answers, i = _multicall_reply(raw)
        if i is None or ((len(answers) == 2) != (which == "token")):
            return raw
        entries = edit(_decode(answers[i]["result"]))
        answers[i]["result"] = _encode(entries)
        return dict(raw, text=json.dumps(answers))
    return tamper


DEGEN_WETH_03 = "0xc9034c3e7f58003e6ae0c8438e7c8f4598d5acaa"


def test_a_thin_traded_usdc_pool_does_not_outrank_a_deep_weth_pool() -> None:
    """DEGEN's USDC pool traded, but about 57 cents moves it 1 %; its WETH pool takes 1,632 dollars."""
    out, asked = _token("token_degen")
    assert set(asked) == {"https://base-rpc.hestia.modelmarket.dev"} and len(asked) == 4
    assert (out["symbol"], out["name"], out["decimals"]) == ("DEGEN", "Degen", 18)
    assert out["supply_on_base"] == "35810176131.601100956438763166" and out["quote"] == "USDC"
    assert out["route"] == "WETH pool x ETH/USDC" and out["pool"] == DEGEN_WETH_03 and out["fee_pct"] == "0.3"
    assert out["price_usd"] == "0.000700359893396" and out["price_basis"] == "twap"
    assert out["depth_1pct_usd"] == "1632.54" and out["block"] == 60800000
    usdc = next(p for p in out["pools"] if p["quote"] == "USDC" and p["fee_pct"] == "0.3")
    assert usdc["traded"] and usdc["depth_1pct_usd"] == "0.57057730" and "not a market price" in usdc["note"]
    assert _ok(out)["traded_pool"] and "routes_agree" not in _ok(out)
    assert all(p["price_unit"] == p["quote"] + " per DEGEN" for p in out["pools"])
    assert out["source"].startswith("Uniswap v3 pools on Base, read from https://base-rpc.hestia.modelmarket.dev")
    assert "anyone can deploy a token called USDC" in out["limits"]


def test_a_token_priced_through_weth_multiplies_by_eth_and_the_usdc_route_agrees() -> None:
    out, _ = _token("token_aero")
    assert (out["symbol"], out["name"]) == ("AERO", "Aerodrome")
    assert out["route"] == "WETH pool x ETH/USDC" and out["price_basis"] == "twap"
    weth = next(p for p in out["pools"] if p["pool"] == out["pool"])
    assert weth["quote"] == "WETH" and weth["traded"] and "note" not in weth
    price = Decimal(weth["twap"]) * Decimal(out["eth_usd"])
    assert abs(price - Decimal(out["price_usd"])) / price < Decimal("1e-9")
    agree = next(c for c in out["checks"] if c["check"] == "routes_agree")
    assert agree["ok"] and "0.1066 %" in agree["detail"]
    assert _ok(out)["eth_deepest_traded_pool"]


def test_the_token_price_follows_from_the_recorded_oracle_words() -> None:
    """AERO in WETH from the two tick accumulators observe() returned, decoded here."""
    out, _ = _token("token_aero")
    fetched = V["token_aero"]["fetched"]
    replies = [json.loads(raw["text"]) for raw in fetched.values()]
    pools = next(r for r in replies if isinstance(r, list) and len(r) == 1 and len(r[0].get("result", "")) > 2000)
    entries = _decode(pools[0]["result"])
    i = [p["pool"] for p in out["pools"]].index(out["pool"])
    ok, data = entries[3 * i + 2]  # liquidity, slot0, observe for each pool, in order
    assert ok
    words = [data[j:j + 64] for j in range(0, len(data), 64)]
    start = int(words[0], 16) // 32

    def signed(word):
        value = int(word, 16)
        return value - (1 << 256) if value >= 1 << 255 else value

    mean = Decimal(signed(words[start + 2]) - signed(words[start + 1])) / Decimal(1800)
    # WETH (0x4200…) sorts before AERO (0x9401…): token0 is WETH, so AERO in WETH is 1 / 1.0001^tick.
    in_weth = 1 / Decimal("1.0001") ** mean
    assert abs(in_weth - Decimal(out["pools"][i]["twap"])) / in_weth < Decimal("1e-9")


def test_when_no_deep_pool_traded_the_price_is_the_deepest_pools_last_trade() -> None:
    """EURC: its WETH pool traded, but 34 cents moves it 1 %; the USDC pool that takes 41,456 did not."""
    out, _ = _token("token_eurc")
    assert out["symbol"] == "EURC" and out["route"] == "direct USDC pool" and out["fee_pct"] == "0.05"
    assert out["price_basis"] == "last_trade" and out["price_usd"] == "1.095154506677"
    assert out["depth_1pct_usd"] == "41456.44"
    traded = next(c for c in out["checks"] if c["check"] == "traded_pool")
    assert traded["ok"] is False and "last trade" in traded["detail"]


def test_with_no_oracle_reaching_back_the_spot_price_is_given_and_flagged() -> None:
    def no_observe(entries):
        return [(False, "") if k % 3 == 2 else e for k, e in enumerate(entries)]

    # The ETH leg is its own batch and keeps its averages; only the token's pools lose theirs.
    out, _ = _token("token_aero", tamper=_edit_multicall(no_observe, "pools"))
    assert out["price_basis"] == "spot" and out["price_usd"] == out["spot_usd"]
    assert out["spot_vs_twap_pct"] is None and out["pool"] == "0x3d5d143381916280ff91407febeb52f2b60f33cf"
    assert "one swap can move" in next(c for c in out["checks"] if c["check"] == "traded_pool")["detail"]


def test_a_token_without_pools_is_refused() -> None:
    def no_pools(entries):
        return [(True, "0" * 64) if k < 8 else e for k, e in enumerate(entries)]

    with pytest.raises(ValueError, match="no Uniswap v3 pool of DEGEN with USDC or WETH"):
        _token("token_degen", tamper=_edit_multicall(no_pools, "token"))


def test_an_address_that_is_not_a_token_is_refused() -> None:
    def no_decimals(entries):
        return [(False, "") if k == 8 else e for k, e in enumerate(entries)]

    with pytest.raises(ValueError, match="does not answer decimals"):
        _token("token_degen", tamper=_edit_multicall(no_decimals, "token"))


def test_an_address_without_code_is_refused() -> None:
    def no_code(url, raw):
        answers, i = _multicall_reply(raw)
        if i is None or len(answers) != 2:
            return raw
        answers[0]["result"] = "0x"
        return dict(raw, text=json.dumps(answers))

    with pytest.raises(ValueError, match="there is no contract at 0x4ed4"):
        _token("token_degen", tamper=no_code)


def test_a_token_name_is_printable_text_of_at_most_64_characters() -> None:
    def long_name(entries):
        text = ("‮USDC\n" * 40).encode()
        data = format(32, "064x") + format(len(text), "064x") + text.hex()
        data += "0" * ((64 - len(data) % 64) % 64)
        return [(True, data) if k == 10 else e for k, e in enumerate(entries)]

    out, _ = _token("token_degen", tamper=_edit_multicall(long_name, "token"))
    assert len(out["name"]) == 64 and out["name"].startswith("USDCUSDC") and "\n" not in out["name"]


def test_a_bad_token_address_is_refused_before_any_fetch() -> None:
    from replay import load as replay

    handle, asked, _ = replay("onchain-price", {})
    with pytest.raises(ValueError, match="token must be a 0x address"):
        handle({"token": "DEGEN"})
    assert asked == []
