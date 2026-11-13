"""Run the installed fixed-GET observer against CMC without reading or writing a ledger."""

import asyncio
import hashlib
import json
import os
from pathlib import Path

from aimarket_hub import observed_sellers, x402_bridge


URL = "https://pro-api.coinmarketcap.com/x402/v3/cryptocurrency/quotes/latest?id=1,1027"
EXPECTED = "0x3C5f3a6cE224BB89D72f5EB4232ecC27F67B3eeA"
SUBSTITUTED = "0x" + "22" * 20
ROUTE = {"url": URL, "method": "GET", "source": observed_sellers.EXPLICIT_GET_SOURCE}


async def case(label, payee, explicit):
    calls = []

    async def capture(method, url, headers, max_bytes, json_body):
        assert url == URL and json_body is None
        assert not set(map(str.lower, headers)) & {"authorization", "x-api-key", "payment-signature", "x-payment"}
        answer = await observed_sellers._default_request(method, url, headers, max_bytes, json_body)
        calls.append({"method": method, "status": answer["status"]})
        return answer

    route = ROUTE if explicit else {"url": URL, "method": "GET"}
    result = await observed_sellers.probe_route(route, request=capture, expected_pay_to=payee)
    view = {k: result[k] for k in ("http_status", "result", "probe_method", "price_usd", "amount_atomic", "network",
                                  "asset", "scheme", "pay_to", "x402_version", "detail") if k in result}
    return {"case": label, "calls": calls, "result": view}


async def main():
    correct = await case("pin_from_prior_unpaid_quotes", EXPECTED, True)
    wrong = await case("substituted_pin", SUBSTITUTED, True)
    baseline = await case("head_only_without_explicit_get", EXPECTED, False)
    requests = [{"method": "HEAD", "status": 200}, {"method": "GET", "status": 402}]
    assert correct["calls"] == wrong["calls"] == requests, (correct, wrong)
    quote = correct["result"]
    assert quote["result"] == "quoted" and quote["probe_method"] == "GET"
    assert quote["pay_to"].lower() == EXPECTED.lower() and quote["asset"].lower() == x402_bridge.USDC.lower()
    assert quote["network"] == "eip155:8453" and quote["scheme"] == "exact" and quote["x402_version"] == 2
    assert quote["price_usd"] == 0.01 and quote["amount_atomic"] == "10000", quote
    assert wrong["result"]["result"] == "no_offer" and "pay_to" not in wrong["result"], wrong
    assert baseline["calls"] == requests[:1] and baseline["result"]["result"] == "not_priced", baseline
    modules = (observed_sellers, x402_bridge)
    print(json.dumps({"image": os.environ["PROBE_IMAGE"], "method": "installed probe_route and outbound HTTPS",
                      "file_sha256": {Path(m.__file__).name: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()
                                      for m in modules}, "url": URL,
                      "cases": [correct, wrong, baseline], "ledger_access": False,
                      "vendor_registration": False, "payment_signature": False}, indent=2))


asyncio.run(main())
