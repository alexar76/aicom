"""Observed sellers (spec §2.7): an x402 seller listed from its own discovery document.

The tier exists so that saying yes costs a seller one email. What these tests defend is
the other side of that bargain: the hub lists only what a live 402 said, pins the
recipient, keeps the rows out of its catalogue, and drops them when consent goes.
"""

import asyncio
import base64
import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from aimarket_hub import observed_sellers as obs
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.signing import Signer

ADMIN_TOKEN = "test-admin-token-not-for-production"
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
SELLER = "https://seller.example"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAY_TO = "0x1111111111111111111111111111111111111111"
OTHER_PAY_TO = "0x2222222222222222222222222222222222222222"
CONSENT = {"by": "contact@seller.example", "at": "2026-10-30", "how": "email"}

# The four discovery shapes seen on live sellers on 2026-10-30, trimmed.
SWARM_SHAPE = {
    "version": 1, "x402Version": 2, "name": "Seller",
    "resources": [f"{SELLER}/services/site-check", f"{SELLER}/services/read-page"],
    "endpoints": [
        {"url": f"{SELLER}/services/site-check", "method": "POST",
         "description": "Site Check - is a URL up, its status and TLS errors.", "priceUsdCents": 0.2},
        {"url": f"{SELLER}/services/read-page", "method": "POST",
         "description": "Read Page - a URL as clean LLM-ready text.", "priceUsdCents": 0.2},
        {"url": "https://elsewhere.example/steal", "method": "POST", "description": "foreign"},
    ],
}
ITEMS_SHAPE = {
    "x402Version": 1,
    "resources": [f"{SELLER}/api/translate-es"],
    "items": [{
        "resource": f"{SELLER}/api/translate-es", "type": "http",
        "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "3000",
                     "asset": USDC_BASE, "payTo": PAY_TO, "description": "Translate to Spanish"}],
    }, {
        "resource": {"url": f"{SELLER}/api/premium/routing", "description": "Model routing"},
        "method": "GET", "accepts": [],
    }],
}
ACCEPTS_SHAPE = {
    "version": 1,
    "resources": [f"{SELLER}/execute"],
    "accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "1000",
                 "resource": f"{SELLER}/execute", "description": "Run code in a sandbox",
                 "asset": USDC_BASE, "payTo": PAY_TO}],
}


def _v1_402(amount="2000", pay_to=PAY_TO, asset=USDC_BASE):
    return {"status": 402, "json": {"x402Version": 1, "accepts": [{
        "scheme": "exact", "network": "base", "maxAmountRequired": amount,
        "asset": asset, "payTo": pay_to, "resource": f"{SELLER}/x",
    }]}, "headers": {}}


def _v2_402(amount="2000", pay_to=PAY_TO):
    offer = {"x402Version": 2, "resource": {"url": f"{SELLER}/x", "description": "from the 402"},
             "accepts": [{"scheme": "exact", "network": "eip155:8453", "amount": amount,
                          "asset": USDC_BASE, "payTo": pay_to}]}
    header = base64.b64encode(json.dumps(offer).encode()).decode()
    return {"status": 402, "json": {}, "headers": {"payment-required": header}}


class FakeSeller:
    """A seller's origin: a discovery document and a reply per route. Records every request."""

    def __init__(self, doc, replies, default=None):
        self.doc = doc
        self.replies = replies
        self.default = default or _v1_402()
        self.calls = []

    async def __call__(self, method, url, headers, max_bytes, json_body):
        self.calls.append({"method": method, "url": url, "headers": dict(headers), "json": json_body})
        if url == SELLER + "/.well-known/x402":
            if self.doc is None:
                return {"status": 404, "json": None, "headers": {}}
            return {"status": 200, "json": self.doc, "headers": {}}
        if url.startswith(SELLER + "/.well-known/"):
            return {"status": 404, "json": None, "headers": {}}
        return self.replies.get(url, self.default)


def run(coro):
    return asyncio.run(coro)


# ── Reading what the seller publishes ────────────────────────────────


def test_endpoints_shape_keeps_own_origin_and_listed_price():
    routes = obs.parse_discovery(SWARM_SHAPE, SELLER)
    assert [r["url"] for r in routes] == [f"{SELLER}/services/site-check", f"{SELLER}/services/read-page"]
    assert routes[0]["method"] == "POST"
    assert routes[0]["listed_price_usd"] == pytest.approx(0.002)
    assert routes[0]["description"].startswith("Site Check")


def test_items_shape_reads_string_and_object_resources():
    routes = obs.parse_discovery(ITEMS_SHAPE, SELLER)
    assert routes[0]["url"] == f"{SELLER}/api/translate-es"
    assert routes[0]["listed_price_usd"] == pytest.approx(0.003)
    assert routes[0]["description"] == "Translate to Spanish"
    assert routes[1]["method"] == "GET"
    assert routes[1]["description"] == "Model routing"


def test_top_level_accepts_shape():
    routes = obs.parse_discovery(ACCEPTS_SHAPE, SELLER)
    assert routes == [{"url": f"{SELLER}/execute", "method": "POST",
                       "description": "Run code in a sandbox", "listed_price_usd": 0.001}]


def test_resource_objects_shape():
    doc = {"x402Version": 2, "resources": [
        {"url": f"{SELLER}/x402/check", "method": "POST", "description": "A check"},
        f"{SELLER}/bare",
    ]}
    routes = obs.parse_discovery(doc, SELLER)
    assert routes[0] == {"url": f"{SELLER}/x402/check", "method": "POST",
                         "description": "A check", "listed_price_usd": None}
    assert routes[1]["url"] == f"{SELLER}/bare"


def test_a_route_on_another_origin_or_plain_http_is_ignored():
    doc = {"resources": ["https://elsewhere.example/a", f"http://seller.example/b",
                         f"{SELLER}.evil.example/c", f"{SELLER}/ok"]}
    assert [r["url"] for r in obs.parse_discovery(doc, SELLER)] == [f"{SELLER}/ok"]


def test_consented_routes_select_and_order():
    routes = obs.parse_discovery(SWARM_SHAPE, SELLER)
    chosen = obs.select_routes(routes, [f"{SELLER}/services/read-page"], limit=25)
    assert [r["url"] for r in chosen] == [f"{SELLER}/services/read-page"]
    assert len(obs.select_routes(routes, None, limit=1)) == 1


# ── Reading the 402 ──────────────────────────────────────────────────


def test_v1_and_v2_offers_read_the_same_terms():
    v1 = obs.offer_from_402(_v1_402()["json"], {})
    v2 = obs.offer_from_402({}, _v2_402()["headers"])
    for offer in (v1, v2):
        assert offer["pay_to"] == PAY_TO
        assert offer["network"] == "eip155:8453"
        assert offer["amount_atomic"] == "2000"
        assert offer["price_usd"] == pytest.approx(0.002)
    assert v2["x402_version"] == 2
    assert v2["offer_description"] == "from the 402"


def test_no_usd_price_is_invented_for_an_unknown_asset():
    offer = obs.offer_from_402(_v1_402(asset="0x" + "ab" * 20)["json"], {})
    assert offer["price_usd"] is None


def test_an_offer_without_a_recipient_is_no_offer():
    body = {"accepts": [{"scheme": "exact", "network": "base", "maxAmountRequired": "10"}]}
    assert obs.offer_from_402(body, {}) is None


@pytest.mark.parametrize("amount", ["-1", "0", "+2", "1_000", "１２", "9" * 400,
                                    str(2 ** 256), True, 1.5, None])
def test_invalid_amount_cannot_be_listed_as_a_payable_offer(amount):
    assert obs.offer_from_402(_v1_402(amount=amount)["json"], {}) is None


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity", -0.1, True])
def test_discovery_price_is_finite_and_nonnegative(price):
    routes = obs.parse_discovery({"endpoints": [{"url": SELLER + "/x", "priceUsd": price}]}, SELLER)
    assert routes[0]["listed_price_usd"] is None


@pytest.mark.parametrize("url", ["https://[broken/x", "https://seller.example:bad/x",
                                "https://seller.example/\x00x"])
def test_malformed_discovery_url_does_not_abort_the_seller(url):
    routes = obs.parse_discovery({"resources": [url, SELLER + "/ok"]}, SELLER)
    assert [r["url"] for r in routes] == [SELLER + "/ok"]


@pytest.mark.parametrize("reply,result", [
    (_v1_402(), "quoted"),
    (_v2_402(), "quoted"),
    ({"status": 402, "json": {"error": "pay"}, "headers": {}}, "no_offer"),
    (_v1_402(asset="0x" + "ab" * 20), "unknown_asset"),
    ({"status": 422, "json": {}, "headers": {}}, "input_required"),
    ({"status": 200, "json": {"ok": True}, "headers": {}}, "not_priced"),
    ({"status": 0, "error": "ConnectError: refused"}, "unreachable"),
])
def test_probe_results(reply, result):
    seller = FakeSeller(SWARM_SHAPE, {}, default=reply)
    probe = run(obs.probe_route({"url": f"{SELLER}/x", "method": "POST"}, hub_url="https://hub.example",
                                request=seller))
    assert probe["result"] == result


def test_a_probe_is_unpaid_and_says_who_is_asking():
    seller = FakeSeller(SWARM_SHAPE, {})
    run(obs.probe_route({"url": f"{SELLER}/x", "method": "POST"}, hub_url="https://hub.example",
                        request=seller))
    call = seller.calls[-1]
    assert call["json"] == {}
    names = {k.lower() for k in call["headers"]}
    assert not names & {"x-payment", "payment-signature", "authorization"}
    assert call["headers"]["X-AIMarket-Observer"] == "https://hub.example"
    run(obs.probe_route({"url": f"{SELLER}/y", "method": "GET"}, request=seller))
    assert seller.calls[-1]["method"] == "GET" and seller.calls[-1]["json"] is None


# ── Observing a seller ───────────────────────────────────────────────


def test_first_recipient_is_pinned_and_a_changed_one_is_withdrawn():
    seller = FakeSeller(SWARM_SHAPE, {})
    first = run(obs.observe_seller({"origin": SELLER}, request=seller))
    assert first["pinned_pay_to"] == PAY_TO
    assert all(r["listed"] for r in first["routes"])
    assert first["routes"][0]["price_matches_listing"] is True

    seller.default = _v1_402(pay_to=OTHER_PAY_TO)
    second = run(obs.observe_seller({"origin": SELLER, "pinned_pay_to": first["pinned_pay_to"]},
                                    request=seller))
    assert second["pinned_pay_to"] == PAY_TO
    assert [r["result"] for r in second["routes"]] == ["pay_to_changed", "pay_to_changed"]
    assert not any(r["listed"] for r in second["routes"])


def test_the_402_price_is_listed_even_when_the_document_says_otherwise():
    seller = FakeSeller(SWARM_SHAPE, {}, default=_v1_402(amount="5000"))
    seen = run(obs.observe_seller({"origin": SELLER}, request=seller))
    route = seen["routes"][0]
    assert route["listed"] and route["price_usd"] == pytest.approx(0.005)
    assert route["price_matches_listing"] is False


def test_only_consented_routes_are_probed_and_a_missing_one_is_reported():
    seller = FakeSeller(SWARM_SHAPE, {})
    seen = run(obs.observe_seller({"origin": SELLER, "allowed_routes": [
        f"{SELLER}/services/read-page", f"{SELLER}/services/gone"]}, request=seller))
    assert [r["url"] for r in seen["routes"]] == [f"{SELLER}/services/read-page"]
    assert "gone" in seen["last_error"]
    probed = [c["url"] for c in seller.calls if "/.well-known/" not in c["url"]]
    assert probed == [f"{SELLER}/services/read-page"]


def test_a_free_answer_stops_the_cycle_so_the_sellers_free_calls_are_not_spent():
    first, second = f"{SELLER}/services/site-check", f"{SELLER}/services/read-page"
    seller = FakeSeller(SWARM_SHAPE, {first: {"status": 200, "json": {"ok": True}, "headers": {}}})
    seen = run(obs.observe_seller({"origin": SELLER}, request=seller))
    assert [r["result"] for r in seen["routes"]] == ["not_priced"]
    assert "skipped" in seen["last_error"]
    assert second not in [c["url"] for c in seller.calls]


def test_no_discovery_document_lists_nothing():
    seen = run(obs.observe_seller({"origin": SELLER}, request=FakeSeller(None, {})))
    assert seen["routes"] == [] and seen["last_error"]


def test_a_stale_observation_is_not_served():
    seller = FakeSeller(SWARM_SHAPE, {})
    seen = run(obs.observe_seller({"origin": SELLER}, request=seller, now=1_800_000_000))
    record = {"origin": SELLER, **seen}
    assert obs.served_routes([record], now=1_800_000_000 + 60)
    assert obs.served_routes([record], now=1_800_000_000 + obs.ttl_s() + 1) == []


def test_search_ranks_by_intent_words_and_honours_budget():
    seller = FakeSeller(SWARM_SHAPE, {})
    seen = run(obs.observe_seller({"origin": SELLER}, request=seller, now=1_800_000_000))
    routes = obs.served_routes([{"origin": SELLER, **seen}], now=1_800_000_000)
    hits = obs.search_routes(routes, "read a web page as text")
    assert hits[0]["url"].endswith("/read-page")
    assert obs.search_routes(routes, "read page", budget=0.001) == []
    assert obs.search_routes(routes, "quantum chemistry") == []


# ── Through the hub ──────────────────────────────────────────────────


@contextmanager
def _hub(monkeypatch, tmp_path, seller):
    import aimarket_hub.crawler as crawler

    monkeypatch.setenv("AIMARKET_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("AIMARKET_FEDERATION_ASSAY", "0")
    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    # `.example` never resolves and the SSRF guard resolves DNS; the guard itself is tested elsewhere.
    monkeypatch.setattr(crawler, "_url_is_safe",
                        lambda url: url.startswith(("http://", "https://")) and "localhost" not in url)
    monkeypatch.setattr(obs, "_default_request", seller)
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    db = HubDatabase(tmp_path / "hub.db")
    app = create_app(config=config, db=db, signer=Signer(tmp_path / "key"))
    with TestClient(app) as client:
        yield client


def _add(client, **extra):
    return client.post("/ai-market/v2/federation/observed-sellers", headers=ADMIN,
                       json={"origin": SELLER, "consent": CONSENT, **extra})


def test_recording_consent_needs_the_operator(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, FakeSeller(SWARM_SHAPE, {})) as client:
        r = client.post("/ai-market/v2/federation/observed-sellers",
                        json={"origin": SELLER, "consent": CONSENT})
        assert r.status_code == 401
        assert client.get("/ai-market/v2/federation/observed-sellers").json()["sellers"] == []


@pytest.mark.parametrize("body,detail", [
    ({"origin": "http://seller.example", "consent": CONSENT}, "https"),
    ({"origin": SELLER}, "consent"),
    ({"origin": SELLER, "consent": {"how": "email"}}, "by"),
    ({"origin": SELLER, "consent": CONSENT, "routes": ["https://elsewhere.example/x"]}, "not on"),
])
def test_bad_requests_are_refused(monkeypatch, tmp_path, body, detail):
    with _hub(monkeypatch, tmp_path, FakeSeller(SWARM_SHAPE, {})) as client:
        r = client.post("/ai-market/v2/federation/observed-sellers", headers=ADMIN, json=body)
        assert r.status_code == 400 and detail in r.text


def test_a_consented_seller_is_listed_searchable_apart_and_withdrawn(monkeypatch, tmp_path):
    seller = FakeSeller(SWARM_SHAPE, {})
    with _hub(monkeypatch, tmp_path, seller) as client:
        r = _add(client, routes=[f"{SELLER}/services/site-check", f"{SELLER}/services/read-page"])
        assert r.status_code == 200, r.text
        assert r.json()["seller"]["routes_served"] == 2

        listing = client.get("/ai-market/v2/federation/observed-sellers").json()
        public = listing["sellers"][0]
        assert public["pinned_pay_to"] == PAY_TO
        assert public["consent"] == {"recorded": True, "at": "2026-10-30", "how": "email"}
        assert "contact@seller.example" not in json.dumps(listing)

        found = client.get("/ai-market/v2/search", params={"intent": "read page text"}).json()
        assert found["observed"][0]["url"] == f"{SELLER}/services/read-page"
        assert found["observed"][0]["signed_by_seller"] is False
        assert all(m.get("source_hub") != SELLER for m in found["matches"])

        manifest = client.get("/ai-market/v2/manifest").json()
        assert SELLER not in json.dumps(manifest.get("tools") or [])
        wk = client.get("/.well-known/ai-market.json").json()
        assert wk["observed_sellers"][0]["origin"] == SELLER
        assert wk["observed_sellers"][0]["routes_served"] == 2
        assert all(p.get("url") != SELLER for p in wk.get("peers") or [])

        r = client.delete("/ai-market/v2/federation/observed-sellers", headers=ADMIN,
                          params={"origin": SELLER})
        assert r.status_code == 200
        assert client.get("/ai-market/v2/federation/observed-sellers").json()["sellers"] == []
        assert client.get("/ai-market/v2/search", params={"intent": "read page"}).json()["observed"] == []


def test_reposting_without_pay_to_keeps_the_pin(monkeypatch, tmp_path):
    seller = FakeSeller(SWARM_SHAPE, {})
    with _hub(monkeypatch, tmp_path, seller) as client:
        assert _add(client).status_code == 200
        seller.default = _v1_402(pay_to=OTHER_PAY_TO)
        r = _add(client)
        assert r.json()["seller"]["pinned_pay_to"] == PAY_TO
        assert r.json()["seller"]["routes_served"] == 0
        r = _add(client, pay_to=OTHER_PAY_TO)
        assert r.json()["seller"]["pinned_pay_to"] == OTHER_PAY_TO
        assert r.json()["seller"]["routes_served"] == 2


def test_an_agent_on_mcp_is_told_to_call_the_seller_itself(monkeypatch, tmp_path):
    with _hub(monkeypatch, tmp_path, FakeSeller(SWARM_SHAPE, {})) as client:
        assert _add(client).status_code == 200
        r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "market_search", "arguments": {"intent": "read a web page as clean text"}}})
        frame = next(line[5:].strip() for line in r.text.splitlines() if line.startswith("data:"))
        body = json.loads(json.loads(frame)["result"]["content"][0]["text"])
    assert body["observed"][0]["url"] == f"{SELLER}/services/read-page"
    assert body["observed"][0]["pay_to"] == PAY_TO
    assert "market_invoke" in body["observed_note"]
    if not body["matches"]:
        assert "observed" in body["note"]
