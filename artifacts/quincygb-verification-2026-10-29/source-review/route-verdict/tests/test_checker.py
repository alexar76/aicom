"""Offline end-to-end tests for the check pipeline.

A MockTransport plays all three hosts (the target, the CDP merchant
lookup, the PayAI listing-status), so the whole pipeline — probe, parse,
schema score, catalog presence, verdict, persistence, diff — runs with
zero network. Two sequential checks against a mutable challenge pin the
diff behaviour the service sells.
"""

import asyncio

import httpx
import jsonschema

from app.checker import run_check
from app.discovery import CHECK_OUTPUT_SCHEMA
from app.store import CheckStore

TARGET_URL = "https://target.example.com/v1/thing"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAY_TO = "0x1111111111111111111111111111111111111111"

FULL_OUTPUT = {
    "type": "json",
    "example": {"verdict": "OK"},
    "schema": {
        "type": "object",
        "properties": {"verdict": {"type": "string"}, "score": {"type": "number"}},
    },
}


def challenge(amount="20000", pay_to=PAY_TO, output=None):
    return {
        "x402Version": 2,
        "error": "Payment required",
        "resource": {"url": TARGET_URL, "description": "A target thing."},
        "accepts": [
            {
                "scheme": "exact",
                "network": "eip155:8453",
                "asset": USDC,
                "amount": amount,
                "payTo": pay_to,
                "maxTimeoutSeconds": 300,
            }
        ],
        "extensions": {
            "bazaar": {
                "info": {
                    "input": {"type": "http", "method": "POST", "bodyType": "json", "body": {}},
                    "output": output if output is not None else FULL_OUTPUT,
                }
            }
        },
    }


def make_client(target, *, cdp_resources=(), payai_status=404):
    """target: a challenge dict, an httpx.Response, or a callable."""

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host == "api.cdp.coinbase.com":
            return httpx.Response(
                200,
                json={
                    "pagination": {"total": len(cdp_resources)},
                    "resources": list(cdp_resources),
                },
            )
        if host == "facilitator.payai.network":
            return httpx.Response(payai_status, json={"status": "listed"} if payai_status == 200 else {"error": "no row"})
        if isinstance(target, httpx.Response):
            return target
        if callable(target):
            return target(request)
        return httpx.Response(402, json=target)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def run(url, store, client, **kw):
    return asyncio.run(run_check(url, store, client=client, **kw))


def test_healthy_listed_target_is_trusted(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))
    cdp_row = {
        "resource": TARGET_URL,
        "l30DaysUniquePayers": 42,
        "l30DaysTotalCalls": 130,
        "lastCalledAt": "2026-10-20T00:00:00Z",
    }
    client = make_client(challenge(), cdp_resources=[cdp_row], payai_status=200)
    result = run(TARGET_URL, store, client)
    jsonschema.validate(instance=result, schema=CHECK_OUTPUT_SCHEMA)
    assert result["verdict"] == "TRUSTED"
    assert result["score"] == 100.0
    assert result["reasons"] == []
    assert result["liveness"]["alive"] is True
    assert result["liveness"]["http_status"] == 402
    assert result["terms"]["price_usdc"] == "$0.02"
    assert result["terms"]["pay_to"] == PAY_TO
    assert result["schema_quality"]["hollow"] is False
    assert result["catalog"]["cdp_bazaar"]["status"] == "listed"
    assert result["catalog"]["cdp_bazaar"]["unique_payers_30d"] == 42
    assert result["catalog"]["cdp_bazaar"]["total_calls_30d"] == 130
    assert result["catalog"]["payai"]["status"] == "listed"
    assert result["diff"]["prior_check"] is False
    assert result["diff"]["summary"] == "no prior check on record"
    assert store.count(TARGET_URL) == 1


def test_hollow_unlisted_target_is_caution_with_itemized_reasons(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))
    hollow_output = {"type": "json", "example": {"anything": 1}}
    client = make_client(challenge(output=hollow_output))
    result = run(TARGET_URL, store, client)
    jsonschema.validate(instance=result, schema=CHECK_OUTPUT_SCHEMA)
    # 100 - 20 hollow - 10 CDP not listed - 5 PayAI not listed
    assert result["score"] == 65.0
    assert result["verdict"] == "CAUTION"
    names = [r["name"] for r in result["reasons"]]
    assert "hollow discovery schema" in names
    assert "not listed in CDP Bazaar" in names
    assert "not listed in PayAI index" in names
    assert result["schema_quality"]["hollow"] is True


def test_price_change_shows_in_diff_and_deducts(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))
    state = {"amount": "20000"}

    def target_handler(request):
        return httpx.Response(402, json=challenge(amount=state["amount"]))

    client = make_client(target_handler, payai_status=200)
    first = run(TARGET_URL, store, client, now="2026-10-21T00:00:00+00:00")
    assert first["diff"]["prior_check"] is False

    state["amount"] = "30000"
    second = run(TARGET_URL, store, client, now="2026-10-22T00:00:00+00:00")
    changes = {c["field"]: c for c in second["diff"]["changes"]}
    assert "price" in changes
    assert changes["price"]["before"] == "20000"
    assert changes["price"]["after"] == "30000"
    deductions = {r["name"]: r["deduction"] for r in second["reasons"]}
    assert deductions["price changed since last check"] == 5
    assert second["terms"]["price_usdc"] == "$0.03"


def test_payto_change_is_a_bigger_deduction(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))
    state = {"pay_to": PAY_TO}

    def target_handler(request):
        return httpx.Response(402, json=challenge(pay_to=state["pay_to"]))

    client = make_client(target_handler, payai_status=200)
    run(TARGET_URL, store, client, now="2026-10-21T00:00:00+00:00")
    state["pay_to"] = "0x2222222222222222222222222222222222222222"
    second = run(TARGET_URL, store, client, now="2026-10-22T00:00:00+00:00")
    fields = {c["field"] for c in second["diff"]["changes"]}
    assert "pay_to" in fields
    deductions = {r["name"]: r["deduction"] for r in second["reasons"]}
    assert deductions["payTo changed since last check"] == 15


def test_unreachable_target_is_avoid(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))

    def handler(request):
        if request.url.host == "target.example.com":
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.host == "facilitator.payai.network":
            return httpx.Response(404, json={"error": "no row"})
        return httpx.Response(200, json={"pagination": {"total": 0}, "resources": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = run(TARGET_URL, store, client)
    jsonschema.validate(instance=result, schema=CHECK_OUTPUT_SCHEMA)
    assert result["liveness"]["alive"] is False
    assert result["liveness"]["http_status"] is None
    assert result["verdict"] == "AVOID"
    assert result["score"] == 0.0
    assert result["reasons"][0]["name"] == "endpoint unreachable"
    # No payTo could be parsed, so CDP presence is honestly "unknown".
    assert result["catalog"]["cdp_bazaar"]["status"] == "unknown"


def test_free_200_endpoint_has_no_valid_challenge(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))
    client = make_client(httpx.Response(200, json={"hello": "world"}))
    result = run(TARGET_URL, store, client)
    names = [r["name"] for r in result["reasons"]]
    assert "no valid x402 challenge" in names
    assert result["score"] == 55.0  # 100 - 45
    assert result["verdict"] == "CAUTION"
    assert result["terms"]["found"] is False


def test_bad_url_raises_value_error(tmp_path):
    store = CheckStore(str(tmp_path / "checks.db"))
    client = make_client(challenge())
    try:
        run("ftp://nope", store, client)
    except ValueError as e:
        assert "http(s)" in str(e)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
