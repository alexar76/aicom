"""x402.seller.record@v1: what an x402 payee has actually been paid on Base.

`x402_seller_vectors.json` holds what the Base RPC (base-rpc.publicnode.com, recorded under the hearth
pool's name base-rpc.hestia.modelmarket.dev) and, for one case, the seller answered on 2026-11-22
(scripts/record_fetches.py) for three sellers the modelmarket.dev hub observes with their
consent, over the window ending at Base block 60 800 000 (0.2-second blocks: 18,000 an hour):
  - oracleinsight: 0x5FBbbC…D231, 24 hours, no USDC received;
  - textokit_url: the payee read from tienda.textokit.store's x402 V1 402 ($0.003 per call), 24 hours,
    one transfer of $0.001;
  - aemb: 0xD00427…88E9, 48 hours, recorded while another job on the same address was reading the
    same RPC: part of the window answered 429, so the answer is incomplete and says so.
The busier cases add made-up Transfer logs to the recorded replies; everything else is as recorded.
"""
# ruff: noqa: E501 — recorded values

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from replay import load

from hestia_agents.manifests import AGENTS, deploy_body

V = json.loads((Path(__file__).parent / "x402_seller_vectors.json").read_text(encoding="utf-8"))
SLUG = "x402-seller"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
ORACLE = "0x5fbbbcbf2ade44f5c604e5e55f11945e1addd231"


def _log(payer, pay_to, atomic, block, ts, n):
    return {
        "address": USDC,
        "topics": [TRANSFER, "0x" + payer[2:].zfill(64), "0x" + pay_to[2:].zfill(64)],
        "data": "0x" + format(atomic, "064x"),
        "blockNumber": hex(block),
        "blockTimestamp": hex(ts),
        "transactionHash": "0x" + format(n, "064x"),
        "logIndex": "0x1",
        "removed": False,
    }


def _with_logs(logs_by_range):
    """A tamper that puts `logs` into the eth_getLogs answer whose fromBlock is the key."""

    def tamper(url, raw):
        if "base-rpc.hestia" not in url:
            return raw
        answers = json.loads(raw["text"])
        request = None
        for key, rec in V["oracleinsight"]["fetched"].items():
            if rec is raw or rec.get("text") == raw.get("text"):
                request = json.loads(json.loads(key)[3])
        if request is None:
            return raw
        for call, answer in zip(request, answers, strict=False):
            if call["method"] == "eth_getLogs":
                start = int(call["params"][0]["fromBlock"], 16)
                if start in logs_by_range:
                    answer["result"] = logs_by_range[start]
        raw = dict(raw)
        raw["text"] = json.dumps(answers)
        return raw

    return tamper


def run(case, payload=None, tamper=None):
    handle, asked, _ = load(SLUG, copy.deepcopy(V[case]["fetched"]), tamper)
    return handle(payload or V[case]["payload"]), asked


def test_a_payee_nobody_paid_reads_a_day_by_block_time() -> None:
    out, asked = run("oracleinsight")
    assert out["activity"] == "none" and out["transfers"] == 0 and out["total_usd"] == "0"
    assert out["window"] == {
        **out["window"],
        "hours": 24,
        "from_block": 60368001,
        "to_block": 60800000,
        "covered_hours": 24.0,
        "from_at": "2026-11-21T12:26:15Z",
        "to_at": "2026-11-22T12:26:15Z",
        "complete": True,
        "missing": [],
    }
    covered = sorted((r["from_block"], r["to_block"]) for r in out["window"]["read"])
    assert covered[0][0] == 60368001 and covered[-1][1] == 60800000
    assert all(b - a + 1 <= 50000 for a, b in covered)
    assert all(covered[i][1] + 1 == covered[i + 1][0] for i in range(len(covered) - 1))
    assert len(asked) <= 6
    assert out["notes"] == ["No USDC reached this address on Base in the window (24.0 h by block time)."]


def test_the_payee_and_price_come_from_the_sellers_402() -> None:
    out, asked = run("textokit_url")
    assert asked[0] == "https://tienda.textokit.store/api/translate-es"
    assert out["pay_to"] == "0x6b5af9924f4cd35643c11a9fd1c983f77261a6e1"
    assert out["offer"]["amount_usd"] == "0.003" and out["price_usd"] == "0.003"
    assert out["transfers"] == 1 and out["total_usd"] == "0.001" and out["at_price"] == 0
    assert out["activity"] == "one_payer"
    assert out["top_payers"][0]["address"] == "0x82cef1cdc34d65cf690235dc24e823a6585a6f86"
    assert "Every payment came from one address." in out["notes"]


def _first_range():
    return min(r["from_block"] for r in run("oracleinsight")[0]["window"]["read"])


def test_a_busy_payee_is_counted_by_payer_amount_and_day() -> None:
    start = _first_range()
    a, b, c, d = ("0x" + x * 40 for x in "abcd")
    day0 = 1763337600  # 2025-11-17T00:00:00Z
    logs = [
        _log(a, ORACLE, 10000, start + 1, day0 + 10, 1),
        _log(a, ORACLE, 10000, start + 2, day0 + 20, 2),
        _log(b, ORACLE, 10000, start + 3, day0 + 86400 + 5, 3),
        _log(c, ORACLE, 250000, start + 4, day0 + 86400 + 9, 4),
        _log(c, ORACLE, 250000, start + 4, day0 + 86400 + 9, 4),  # the same log twice counts once
        _log(d, ORACLE, 10000, start + 5, day0 + 86400 + 20, 5),
    ]
    out, _ = run(
        "oracleinsight",
        {**V["oracleinsight"]["payload"], "amount_usd": "0.01"},
        _with_logs({start: logs}),
    )
    assert out["transfers"] == 5 and out["payers"] == 4 and out["returning_payers"] == 1
    assert out["total_usd"] == "0.29" and out["at_price"] == 4 and out["price_usd"] == "0.01"
    assert out["activity"] == "spread" and out["busiest_payer_share_pct"] == 40.0
    assert out["top_payers"][0] == {
        "address": a,
        "transfers": 2,
        "usd": "0.02",
        "share_of_usd_pct": 6.9,
    }
    assert out["common_amounts"] == [
        {"usd": "0.01", "transfers": 4},
        {"usd": "0.25", "transfers": 1},
    ]
    assert out["by_hour"] == [
        {"hour": "2025-11-17T00Z", "transfers": 2, "usd": "0.02"},
        {"hour": "2025-11-18T00Z", "transfers": 3, "usd": "0.27"},
    ]
    assert out["first_at"] == "2025-11-17T00:00:10Z" and out["last_at"] == "2025-11-18T00:00:20Z"
    assert out["notes"] == []


def test_half_the_payments_from_one_payer_is_concentrated_by_definition() -> None:
    start = _first_range()
    a, b, c = ("0x" + x * 40 for x in "abc")
    logs = [
        _log(a, ORACLE, 1, start + 1, 1763337601, 1),
        _log(a, ORACLE, 1, start + 2, 1763337602, 2),
        _log(b, ORACLE, 1, start + 3, 1763337603, 3),
        _log(c, ORACLE, 1, start + 4, 1763337604, 4),
    ]
    out, _ = run("oracleinsight", tamper=_with_logs({start: logs}))
    assert out["activity"] == "concentrated" and out["busiest_payer_share_pct"] == 50.0


def test_one_payer_making_most_payments_is_concentrated() -> None:
    start = _first_range()
    a, b = "0x" + "a" * 40, "0x" + "b" * 40
    logs = [_log(a, ORACLE, 1000, start + i, 1763337600 + i, i) for i in range(1, 5)]
    logs.append(_log(b, ORACLE, 1000, start + 9, 1763337609, 9))
    out, _ = run("oracleinsight", tamper=_with_logs({start: logs}))
    assert out["activity"] == "concentrated" and out["busiest_payer_share_pct"] == 80.0
    assert "One address made 4 of 5 payments." in out["notes"]


def test_logs_that_are_not_usdc_to_this_payee_are_not_counted() -> None:
    start = _first_range()
    good = _log("0x" + "a" * 40, ORACLE, 1000, start + 1, 1763337601, 1)
    other_token = dict(good, address="0x" + "1" * 40, transactionHash="0x" + "2" * 64)
    other_payee = _log("0x" + "a" * 40, "0x" + "e" * 40, 1000, start + 2, 1763337602, 3)
    removed = dict(good, removed=True, transactionHash="0x" + "4" * 64)
    out, _ = run(
        "oracleinsight", tamper=_with_logs({start: [good, other_token, other_payee, removed]})
    )
    assert out["transfers"] == 1


def test_an_unread_range_makes_the_window_incomplete_not_empty() -> None:
    def refuse_second_batch(url, raw):
        if "base-rpc.hestia" in url and '"fromBlock": "0x39b3b31"' not in raw.get("text", ""):
            answers = json.loads(raw["text"])
            if any(isinstance(x.get("result"), list) for x in answers) and len(answers) == 2:
                for x in answers:
                    x.pop("result", None)
                    x["error"] = {"code": -32602, "message": "query exceeds max results 20000"}
                raw = dict(raw, text=json.dumps(answers))
        return raw

    out, _ = run("oracleinsight", tamper=refuse_second_batch)
    assert out["window"]["complete"] is False and out["window"]["missing"]
    assert out["window"]["missing"][0]["reason"].startswith("query exceeds max results")
    assert out["notes"][0].startswith("Some block ranges could not be read")


def test_another_chain_is_refused() -> None:
    def other_chain(url, raw):
        if "base-rpc.hestia" in url and "0x2105" in raw.get("text", ""):
            raw = dict(raw, text=raw["text"].replace('"0x2105"', '"0x1"'))
        return raw

    with pytest.raises(RuntimeError, match="not Base mainnet"):
        run("oracleinsight", tamper=other_chain)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "give pay_to"),
        ({"pay_to": "0x123"}, "pay_to must be a 0x address"),
        ({"pay_to": "0x" + "0" * 40}, "zero address"),
        ({"pay_to": ORACLE, "days": 7}, "days is 1 or 2; give hours"),
        ({"pay_to": ORACLE, "days": True}, "days is 1 or 2"),
        ({"pay_to": ORACLE, "hours": 49}, "hours must be a whole number from 1 to 48"),
        ({"pay_to": ORACLE, "hours": 0}, "hours must be a whole number from 1 to 48"),
        ({"pay_to": ORACLE, "to_block": "latest"}, "to_block must be a block number"),
        ({"pay_to": ORACLE, "amount_usd": "0.0000001"}, "at most 6 decimals"),
        ({"url": "http://example.com/x"}, "url must be an https URL"),
        (
            {"url": "https://example.com/x", "method": "GET", "body": {}},
            "a body goes with POST only",
        ),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_without_the_hearths_rpc_pool_it_reads_the_public_rpc() -> None:
    pool = "https://base-rpc.hestia.modelmarket.dev"
    fetched = {}
    for key, raw in V["oracleinsight"]["fetched"].items():
        fetched[key.replace(pool, "https://base-rpc.publicnode.com")] = raw
        fetched[key] = {"refused": "base-rpc.hestia.modelmarket.dev does not resolve"}
    handle, asked, _ = load(SLUG, fetched)
    out = handle(V["oracleinsight"]["payload"])
    assert asked[0] == pool and set(asked[1:]) == {"https://base-rpc.publicnode.com"}
    assert len(asked) <= 6 and out["window"]["complete"] and out["activity"] == "none"
    assert out == run("oracleinsight")[0]


def test_manifest_reaches_one_rpc_and_the_called_url_and_is_priced() -> None:
    body = deploy_body(SLUG)
    assert body["egress_hosts"] == ["base-rpc.hestia.modelmarket.dev", "base-rpc.publicnode.com"]
    assert AGENTS[SLUG]["egress_input_fields"] == ["url"]
    assert body["capability"]["price_per_call_usd"] == 0.003
    assert body["capability"]["capability_id"] == "x402.seller.record@v1"


def test_a_window_the_rpc_refused_in_part_is_a_floor_and_says_so() -> None:
    out, asked = run("aemb")
    assert out["window"]["hours"] == 48 and out["window"]["covered_hours"] == 48.0
    assert out["window"]["complete"] is False and out["window"]["missing"]
    assert all("429" in m["reason"] for m in out["window"]["missing"])
    assert out["notes"][0].startswith("Some block ranges could not be read")
    assert len(asked) <= 6


def test_two_days_is_48_hours() -> None:
    payload = {k: v for k, v in V["aemb"]["payload"].items() if k != "hours"}
    out, _ = run("aemb", {**payload, "days": 2})
    assert out["window"]["hours"] == 48 and out["window"]["from_block"] == 60800000 - 48 * 18000 + 1
