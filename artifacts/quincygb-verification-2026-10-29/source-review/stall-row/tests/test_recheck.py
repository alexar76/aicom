"""The recheck stall: BASELINE → UNCHANGED → CHANGED flows for both
target kinds, watch isolation, and the failure-honesty contract (a
failed probe raises and never overwrites the stored fingerprint).
Fully offline: MockTransport plays the targets, IP-literal URLs keep
the SSRF guard's DNS lookup local."""

import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.rpc import UpstreamError
from app.services import recheck

OWNER = "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_URL = "https://93.184.216.34/v1/verdict"
WEB_URL = "https://93.184.216.34/story"


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(recheck, "_BACKOFF_S", (0, 0))


@pytest.fixture()
def store(tmp_path):
    return recheck.WatchStore(str(tmp_path / "watches.db"))


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _challenge(amount="20000", pay_to=OWNER, description="A target service."):
    return {
        "x402Version": 2,
        "error": "Payment required",
        "resource": {
            "url": X402_URL,
            "description": description,
            "mimeType": "application/json",
        },
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
                    "output": {
                        "type": "json",
                        "schema": {
                            "type": "object",
                            "properties": {"verdict": {"type": "string"}},
                            "required": ["verdict"],
                        },
                    },
                }
            }
        },
    }


def _challenge_response(**kw) -> httpx.Response:
    challenge = _challenge(**kw)
    raw = base64.b64encode(json.dumps(challenge).encode()).decode()
    return httpx.Response(402, headers={"payment-required": raw}, json=challenge)


# --- x402 targets -------------------------------------------------------------

@pytest.mark.asyncio
async def test_x402_baseline_unchanged_then_changed(store):
    state = {"amount": "20000"}

    def handler(request):
        return _challenge_response(amount=state["amount"])

    async with _client(handler) as client:
        first = await recheck.recheck(client, store, X402_URL)
        assert first["status"] == "BASELINE"
        assert first["kind"] == "x402"
        assert first["changes"] == []
        assert first["current"]["amount"] == "20000"
        assert first["current"]["payTo"] == OWNER
        assert first["current"]["status_code"] == 402
        assert first["current"]["description_hash"]
        assert first["current"]["schema_hash"]

        second = await recheck.recheck(client, store, X402_URL)
        assert second["status"] == "UNCHANGED"
        assert second["changes"] == []

        state["amount"] = "25000"
        third = await recheck.recheck(client, store, X402_URL)
        assert third["status"] == "CHANGED"
        assert third["changes"] == [
            {"field": "amount", "before": "20000", "after": "25000"}
        ]

        fourth = await recheck.recheck(client, store, X402_URL)
        assert fourth["status"] == "UNCHANGED"


@pytest.mark.asyncio
async def test_x402_description_change_is_a_change(store):
    state = {"description": "A target service."}

    def handler(request):
        return _challenge_response(description=state["description"])

    async with _client(handler) as client:
        await recheck.recheck(client, store, X402_URL)
        state["description"] = "A target service with new terms."
        out = await recheck.recheck(client, store, X402_URL)
    assert out["status"] == "CHANGED"
    assert [c["field"] for c in out["changes"]] == ["description_hash"]


# --- web targets ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_baseline_unchanged_then_changed(store):
    state = {"body": "<html><body><h1>Version one</h1></body></html>"}

    def handler(request):
        return httpx.Response(
            200, text=state["body"], headers={"content-type": "text/html"}
        )

    async with _client(handler) as client:
        first = await recheck.recheck(client, store, WEB_URL)
        assert first["status"] == "BASELINE"
        assert first["kind"] == "web"
        assert first["current"]["status_code"] == 200
        assert len(first["current"]["body_sha256"]) == 64

        second = await recheck.recheck(client, store, WEB_URL)
        assert second["status"] == "UNCHANGED"

        state["body"] = "<html><body><h1>Version two</h1></body></html>"
        third = await recheck.recheck(client, store, WEB_URL)
        assert third["status"] == "CHANGED"
        assert [c["field"] for c in third["changes"]] == ["body_sha256"]
        assert third["changes"][0]["before"] == first["current"]["body_sha256"]


@pytest.mark.asyncio
async def test_web_post_refused_falls_back_to_get(store):
    methods = []

    def handler(request):
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(405, text="no posts")
        return httpx.Response(200, text="a plain page", headers={"content-type": "text/plain"})

    async with _client(handler) as client:
        out = await recheck.recheck(client, store, WEB_URL)
    assert out["status"] == "BASELINE"
    assert out["kind"] == "web"
    assert methods == ["POST", "GET"]


# --- watch identity ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_watch_ids_are_isolated_and_default_is_url_hash(store):
    def handler(request):
        return httpx.Response(200, text="same body", headers={"content-type": "text/plain"})

    async with _client(handler) as client:
        a1 = await recheck.recheck(client, store, WEB_URL, "watch-a")
        b1 = await recheck.recheck(client, store, WEB_URL, "watch-b")
        d1 = await recheck.recheck(client, store, WEB_URL)
        assert a1["status"] == b1["status"] == d1["status"] == "BASELINE"
        assert a1["watch_id"] == "watch-a"
        assert b1["watch_id"] == "watch-b"
        assert d1["watch_id"] == recheck.default_watch_id(WEB_URL)

        a2 = await recheck.recheck(client, store, WEB_URL, "watch-a")
        d2 = await recheck.recheck(client, store, WEB_URL)
        assert a2["status"] == d2["status"] == "UNCHANGED"
    assert store.count() == 3


# --- failure honesty ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_failed_probe_does_not_clobber_state(store):
    state = {"mode": "ok"}

    def handler(request):
        if state["mode"] == "500":
            return httpx.Response(500, text="boom")
        if state["mode"] == "down":
            raise httpx.ConnectError("connection refused", request=request)
        return httpx.Response(
            200, text="the good body", headers={"content-type": "text/plain"}
        )

    async with _client(handler) as client:
        first = await recheck.recheck(client, store, WEB_URL)
        assert first["status"] == "BASELINE"

        state["mode"] = "500"
        with pytest.raises(UpstreamError):
            await recheck.recheck(client, store, WEB_URL)

        state["mode"] = "down"
        with pytest.raises(UpstreamError):
            await recheck.recheck(client, store, WEB_URL)

        state["mode"] = "ok"
        again = await recheck.recheck(client, store, WEB_URL)
        # Still diffed against the last GOOD fingerprint — the failures
        # in between neither re-baselined nor recorded a change.
        assert again["status"] == "UNCHANGED"
    assert store.count() == 1


@pytest.mark.asyncio
async def test_hard_404_is_an_error_not_a_fingerprint(store):
    def handler(request):
        return httpx.Response(404, text="gone")

    async with _client(handler) as client:
        with pytest.raises(UpstreamError):
            await recheck.recheck(client, store, WEB_URL)
    assert store.count() == 0


@pytest.mark.asyncio
async def test_ssrf_targets_are_refused_before_fetching(store):
    def handler(request):  # pragma: no cover — must never be reached
        raise AssertionError("fetched a refused target")

    async with _client(handler) as client:
        for url in ("http://127.0.0.1:3000/secret", "ftp://example.com/file"):
            with pytest.raises(ValueError):
                await recheck.recheck(client, store, url)
    assert store.count() == 0


# --- store + paywall surface ---------------------------------------------------------

def test_store_roundtrip(tmp_path):
    s = recheck.WatchStore(str(tmp_path / "w.db"))
    assert s.get("k") is None
    s.save("k", "web", {"status_code": 200, "body_sha256": "x"}, "2026-10-24T00:00:00Z")
    got = s.get("k")
    assert got["kind"] == "web"
    assert got["fingerprint"]["body_sha256"] == "x"
    assert s.count() == 1


def test_unpaid_recheck_challenge_is_exact():
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.post("/v1/recheck", json={"url": X402_URL})
    assert r.status_code == 402
    challenge = json.loads(base64.b64decode(r.headers["payment-required"]))
    accept = challenge["accepts"][0]
    assert accept["amount"] == "5000"
    assert accept["payTo"] == OWNER
    assert accept["asset"] == USDC
    assert accept["network"] == "eip155:8453"
    assert challenge["resource"]["url"].endswith("/v1/recheck")

    health = client.get("/health").json()
    assert health["routes"] == 25
    quote = client.get("/quote").json()
    assert quote["endpoints"]["/v1/recheck"]["price_units"] == 5000
