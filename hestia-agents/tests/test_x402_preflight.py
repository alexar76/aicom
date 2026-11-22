"""x402.preflight@v1: one unpaid request, then what an agent should know before it signs.

`x402_preflight_vectors.json` holds what four calls received on 2026-11-22 (scripts/record_fetches.py;
re-recorded when the payee window became 24 hours of 0.2-second Base blocks, 432,000 blocks in nine ranges):
two sellers the modelmarket.dev hub observes with their consent, one answering x402 V1 in its body
(tienda.textokit.store) and one V2 in the PAYMENT-REQUIRED header (aemb.pro), each with the Base
RPC's view of its payTo and the hub's seller list (cut to these two sellers); a free page; a 404.
The other cases change one field of the recorded V1 402.
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

V = json.loads((Path(__file__).parent / "x402_preflight_vectors.json").read_text(encoding="utf-8"))
SLUG = "x402-preflight"
SELLER = "https://tienda.textokit.store/api/translate-es"


def run(case, change=None, payload=None, tamper=None):
    fetched = copy.deepcopy(V[case]["fetched"])
    if change is not None:
        for key, raw in fetched.items():
            if json.loads(key)[1] == SELLER:
                doc = json.loads(raw["text"])
                change(doc["accepts"][0], doc)
                raw["text"] = json.dumps(doc)
    handle, asked, ns = load(SLUG, fetched, tamper)
    return handle(payload or V[case]["payload"]), asked, ns


def failed(out):
    return [c["check"] for c in out["checks"] if not c["ok"]]


def test_a_v1_seller_with_a_payment_in_the_last_day_looks_payable() -> None:
    out, asked, _ = run("textokit_v1")
    assert out["x402_version"] == 1 and out["verdict"] == "looks_payable"
    assert failed(out) == []
    offer = out["offers"][0]
    assert (
        offer["amount_usd"] == "0.003"
        and offer["asset_name"] == "USDC"
        and offer["eip712"] == {"name": "USD Coin", "version": "2"}
    )
    payee = out["payee"]
    assert payee["kind"] == "key" and payee["usdc_transfers_in"] == 1 and payee["window_hours"] == 24
    first, last = payee["window_blocks"]
    assert last - first + 1 == 24 * 18000  # Base: 0.2 s a block
    # the block that opens the window is a day older than the head (to the second, give or take a block)
    assert payee["window_from_time"] is not None
    assert (
        out["hub_listing"]["listed"] is True and out["hub_listing"]["pinned_pay_to_matches"] is True
    )
    assert len(asked) == 4


def test_a_v2_header_offer_reads_the_same_way() -> None:
    out, _, _ = run("aemb_v2")
    assert out["x402_version"] == 2 and out["checked_offer"] == 0
    assert [o["network"] for o in out["offers"]] == ["eip155:8453", "eip155:42161"]
    assert "amount_usd" not in out["offers"][1]  # Arbitrum USDC is listed, not priced here
    assert out["payee"]["kind"] == "eip7702_delegated"


def test_free_and_missing_pages() -> None:
    assert run("free_page")[0]["verdict"] == "no_payment_required"
    out, _, _ = run("not_found")
    assert out["verdict"] == "not_x402" and "404" in out["detail"]


def _logs(fill):
    """A tamper: the payee's log queries are the RPC answers that are lists; `fill` gives each one."""

    def tamper(url, raw):
        if "base-rpc.hestia" in url:
            doc = json.loads(raw["text"])
            n = 0
            for item in doc:
                if isinstance(item.get("result"), list):
                    item["result"] = fill(n)
                    n += 1
            raw = dict(raw, text=json.dumps(doc))
        return raw

    return tamper


def test_a_payee_with_payments_looks_payable() -> None:
    two = [
        {"topics": ["0x0", "0x" + "0" * 24 + "11" * 20, "0x0"], "data": hex(3000)},
        {"topics": ["0x0", "0x" + "0" * 24 + "22" * 20, "0x0"], "data": hex(3000)},
    ]
    out, _, _ = run("textokit_v1", tamper=_logs(lambda n: two if n == 0 else []))
    assert out["verdict"] == "looks_payable" and failed(out) == []
    assert out["payee"]["distinct_payers"] == 2 and out["payee"]["usdc_received"] == "0.006"


def test_a_payee_nobody_paid_in_a_day_is_review_first() -> None:
    out, _, _ = run("textokit_v1", tamper=_logs(lambda n: []))
    assert out["verdict"] == "review_first" and failed(out) == ["payee_has_payments"]
    assert out["payee"]["usdc_transfers_in"] == 0


@pytest.mark.parametrize(
    "change, check",
    [
        (lambda a, d: a.update(extra={"name": "USDC", "version": "2"}), "eip712_domain"),
        (
            lambda a, d: a.update(asset="0x0000000000000000000000000000000000000bad"),
            "asset_is_usdc",
        ),
        (lambda a, d: a.update(maxAmountRequired="5000000"), "within_budget"),
        (lambda a, d: a.update(payTo="0x0000000000000000000000000000000000000000"), "pay_to"),
        (lambda a, d: a.update(payTo="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"), "pay_to"),
    ],
)
def test_each_refusal(change, check) -> None:
    out, _, _ = run("textokit_v1", change)
    assert out["verdict"] == "do_not_pay" and check in failed(out)


@pytest.mark.parametrize(
    "change, check",
    [
        (lambda a, d: a.update(resource="https://elsewhere.example/api"), "resource_on_this_host"),
        (lambda a, d: a.update(maxTimeoutSeconds=86400), "timeout"),
    ],
)
def test_each_review(change, check) -> None:
    out, _, _ = run("textokit_v1", change)
    assert out["verdict"] == "review_first" and check in failed(out)


def test_a_payto_other_than_the_one_the_hub_pinned_is_flagged() -> None:
    other = "0x00000000000000000000000000000000000000aa"

    def change(accept, doc):
        accept["payTo"] = other

    handle_fetched = copy.deepcopy(V["textokit_v1"]["fetched"])
    # The chain calls are keyed by the payTo they ask about; answer them for the new one.
    for key in list(handle_fetched):
        k = json.loads(key)
        if "base-rpc.hestia" in k[1] and "6b5af9924f4cd35643c11a9fd1c983f77261a6e1" in (k[3] or ""):
            new_key = json.dumps(
                [
                    k[0],
                    k[1],
                    k[2],
                    k[3].replace("6b5af9924f4cd35643c11a9fd1c983f77261a6e1", other[2:]),
                ],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            handle_fetched[new_key] = handle_fetched.pop(key)
    for key, raw in handle_fetched.items():
        if json.loads(key)[1] == SELLER:
            doc = json.loads(raw["text"])
            change(doc["accepts"][0], doc)
            raw["text"] = json.dumps(doc)
    handle, _, _ = load(SLUG, handle_fetched)
    out = handle(V["textokit_v1"]["payload"])
    assert (
        "hub_pinned_pay_to" in failed(out) and out["hub_listing"]["pinned_pay_to_matches"] is False
    )


def test_budget_is_the_callers() -> None:
    payload = dict(V["textokit_v1"]["payload"], max_usd="0.001")
    out, _, _ = run("textokit_v1", payload=payload)
    assert out["verdict"] == "do_not_pay" and "within_budget" in failed(out)


def test_header_offers_decode_base64_and_base64url() -> None:
    _, _, ns = run("free_page")
    doc = {"x402Version": 2, "accepts": [{"scheme": "exact"}]}
    raw = json.dumps(doc).encode()
    for encode in (base64.b64encode, base64.urlsafe_b64encode):
        assert ns["header_offer"]({"payment-required": encode(raw).decode().rstrip("=")}) == doc


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"url": "http://example.com/x"}, "https"),
        ({"url": "https://example.com/x", "method": "DELETE"}, "GET, POST or HEAD"),
        ({"url": "https://example.com/x", "body": {"a": 1}}, "POST only"),
        ({"url": "https://example.com/x", "max_usd": "free"}, "decimal"),
        ({"url": "https://example.com/x", "max_usd": "0"}, "above 0"),
        ({"url": "https://example.com/x", "window_hours": 48}, "1 to 24"),
    ],
)
def test_bad_input_is_refused_before_any_fetch(payload, message) -> None:
    handle, asked, _ = load(SLUG, {})
    with pytest.raises(ValueError, match=message):
        handle(payload)
    assert asked == []


def test_manifest_reaches_the_named_host_the_base_rpcs_and_the_hub() -> None:
    body = deploy_body(SLUG)
    assert body["egress_hosts"] == [
        "base-rpc.hestia.modelmarket.dev",
        "base-rpc.publicnode.com",
        "base-sepolia-rpc.publicnode.com",
        "modelmarket.dev",
    ]
    assert body["egress_input_fields"] == ["url"] and AGENTS[SLUG]["price_per_call_usd"] == 0
