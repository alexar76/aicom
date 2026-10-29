"""Recheck watch packs: minting (incl. payment-replay idempotency),
spend semantics (decrement exactly once per delivered check, never
for our failure), atomicity under concurrency, the refusal matrix,
and free balance reads. Fully offline — MockTransport plays the
target, payment identity is stubbed the way the middleware exposes
it on request.state."""

import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

import app.main as main
from app.services import recheck
from app.services.recheck import PackError

OWNER = "0x097f9685D1e0752bF8B02d61E5Ce9be7eA0FBA7F"
WEB_URL = "https://93.184.216.34/story"
OTHER_URL = "https://93.184.216.34/other"


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    monkeypatch.setattr(recheck, "_BACKOFF_S", (0, 0))


@pytest.fixture()
def store(tmp_path):
    return recheck.WatchStore(str(tmp_path / "watches.db"))


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ok_handler(request):
    return httpx.Response(200, text="a page", headers={"content-type": "text/plain"})


def _buy(store, key="pay-1", url=WEB_URL, **kw):
    pack, created = store.mint_pack(key, url, **kw)
    assert created
    return pack


# --- minting -----------------------------------------------------------------

def test_mint_pack_shape_and_expiry(store):
    pack = _buy(store)
    assert pack["pack_id"].startswith("pack_")
    # 128 bits of entropy behind the prefix: 32 hex chars.
    assert len(pack["pack_id"]) == len("pack_") + 32
    assert pack["url"] == WEB_URL
    assert pack["credits_total"] == 250
    assert pack["credits_remaining"] == 250
    assert pack["expired"] is False
    assert pack["expires_at"] > pack["created_at"]
    assert store.pack_count() == 1


def test_mint_is_idempotent_on_payment_replay(store):
    first, created1 = store.mint_pack("nonce-abc", WEB_URL)
    second, created2 = store.mint_pack("nonce-abc", WEB_URL)
    assert created1 is True and created2 is False
    assert second["pack_id"] == first["pack_id"]
    assert store.pack_count() == 1
    # A different payment mints a different pack.
    third, created3 = store.mint_pack("nonce-def", WEB_URL)
    assert created3 is True and third["pack_id"] != first["pack_id"]
    assert store.pack_count() == 2


# --- spend path ----------------------------------------------------------------

@pytest.mark.asyncio
async def test_pack_spend_decrements_once_per_completed_check(store):
    pack = _buy(store)
    async with _client(_ok_handler) as client:
        first = await recheck.recheck_with_pack(
            client, store, WEB_URL, None, pack["pack_id"]
        )
        assert first["status"] == "BASELINE"
        assert first["pack_id"] == pack["pack_id"]
        assert first["pack_credits_remaining"] == 249

        second = await recheck.recheck_with_pack(
            client, store, WEB_URL, None, pack["pack_id"]
        )
        # UNCHANGED still delivered — and still consumes exactly one.
        assert second["status"] == "UNCHANGED"
        assert second["pack_credits_remaining"] == 248
    assert store.get_pack(pack["pack_id"])["credits_remaining"] == 248


@pytest.mark.asyncio
async def test_failed_check_does_not_consume_a_credit(store):
    pack = _buy(store)
    state = {"mode": "ok"}

    def handler(request):
        if state["mode"] == "500":
            return httpx.Response(500, text="boom")
        return _ok_handler(request)

    async with _client(handler) as client:
        await recheck.recheck_with_pack(client, store, WEB_URL, None, pack["pack_id"])
        assert store.get_pack(pack["pack_id"])["credits_remaining"] == 249

        state["mode"] = "500"
        with pytest.raises(Exception):
            await recheck.recheck_with_pack(
                client, store, WEB_URL, None, pack["pack_id"]
            )
        # Our failure delivered nothing: the credit came back.
        assert store.get_pack(pack["pack_id"])["credits_remaining"] == 249


@pytest.mark.asyncio
async def test_refusals_are_specific_and_decrement_nothing(store):
    pack = _buy(store)

    async with _client(_ok_handler) as client:
        with pytest.raises(PackError) as e:
            await recheck.recheck_with_pack(
                client, store, WEB_URL, None, "pack_doesnotexist"
            )
        assert e.value.code == "unknown_pack" and e.value.http_status == 404

        with pytest.raises(PackError) as e:
            await recheck.recheck_with_pack(
                client, store, OTHER_URL, None, pack["pack_id"]
            )
        assert e.value.code == "wrong_endpoint" and e.value.http_status == 403
    assert store.get_pack(pack["pack_id"])["credits_remaining"] == 250


def test_exhausted_and_expired_packs_refuse(store):
    small = _buy(store, key="pay-small", credits_total=2)
    store.reserve_credit(small["pack_id"], WEB_URL)
    store.reserve_credit(small["pack_id"], WEB_URL)
    with pytest.raises(PackError) as e:
        store.reserve_credit(small["pack_id"], WEB_URL)
    assert e.value.code == "pack_exhausted" and e.value.http_status == 402

    stale = _buy(store, key="pay-stale", ttl_days=0)
    with pytest.raises(PackError) as e:
        store.reserve_credit(stale["pack_id"], WEB_URL)
    assert e.value.code == "pack_expired" and e.value.http_status == 410
    assert store.get_pack(stale["pack_id"])["expired"] is True


def test_concurrent_spends_cannot_overdraw(store):
    pack = _buy(store, credits_total=5)
    barrier = __import__("threading").Barrier(20)

    def spend(_):
        barrier.wait()
        try:
            store.reserve_credit(pack["pack_id"], WEB_URL)
            return "ok"
        except PackError as e:
            return e.code

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(spend, range(20)))
    assert results.count("ok") == 5
    assert results.count("pack_exhausted") == 15
    assert store.get_pack(pack["pack_id"])["credits_remaining"] == 0


# --- balance -------------------------------------------------------------------

def test_balance_reads_without_spending(store):
    pack = _buy(store)
    view = store.get_pack(pack["pack_id"])
    assert view["credits_remaining"] == 250
    assert view["expires_at"] == pack["expires_at"]
    assert store.get_pack("pack_nope") is None
    assert store.get_pack(pack["pack_id"])["credits_remaining"] == 250


# --- HTTP surface ----------------------------------------------------------------

def _fake_request(nonce="0x" + "42" * 32):
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/recheck/pack",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "scheme": "https",
        "client": ("testclient", 50000),
    }
    request = Request(scope)
    request.state.payment_payload = SimpleNamespace(
        payload=SimpleNamespace(
            authorization=SimpleNamespace(
                nonce=nonce, **{"from": "0x1111111111111111111111111111111111111111"}
            ),
            signature="0xdeadbeef",
        )
    )
    return request


def test_buy_handler_mints_and_replay_returns_same_pack(monkeypatch, tmp_path):
    fresh = recheck.WatchStore(str(tmp_path / "w.db"))
    monkeypatch.setattr(main, "_recheck_store", fresh)

    req = main.RecheckPackBuyRequest(url="https://93.184.216.34/v1/verdict")
    out = asyncio.run(main.recheck_pack_buy(req, _fake_request()))
    assert out["credits_total"] == 250 and out["credits_remaining"] == 250
    assert out["expiry_days"] == 90 and out["price_units"] == 1_000_000

    replay = asyncio.run(main.recheck_pack_buy(req, _fake_request()))
    assert replay["pack_id"] == out["pack_id"]
    assert "already minted" in replay["note"]
    assert fresh.pack_count() == 1


def test_unpaid_pack_buy_challenge_is_exactly_one_dollar():
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.post("/v1/recheck/pack", json={"url": WEB_URL})
    assert r.status_code == 402
    challenge = json.loads(base64.b64decode(r.headers["payment-required"]))
    accept = challenge["accepts"][0]
    assert accept["amount"] == "1000000"
    assert accept["payTo"] == OWNER


@pytest.fixture()
def http_env(monkeypatch, tmp_path):
    fresh = recheck.WatchStore(str(tmp_path / "w.db"))
    monkeypatch.setattr(main, "_recheck_store", fresh)
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(_ok_handler))
    monkeypatch.setattr(main, "_fetch_client", lambda: mock_client)
    return fresh


def test_http_pack_spend_via_header_and_body(http_env):
    pack, _ = http_env.mint_pack("pay-http", WEB_URL)
    client = TestClient(main.app, raise_server_exceptions=False)

    r = client.post(
        "/v1/recheck",
        json={"url": WEB_URL},
        headers={"X-Recheck-Pack": pack["pack_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "BASELINE"
    assert body["pack_credits_remaining"] == 249

    r = client.post(
        "/v1/recheck", json={"url": WEB_URL, "pack_id": pack["pack_id"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["pack_credits_remaining"] == 248


def test_http_unknown_pack_refused_and_nothing_runs(http_env):
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.post(
        "/v1/recheck",
        json={"url": WEB_URL},
        headers={"X-Recheck-Pack": "pack_nope"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "unknown_pack"
    assert http_env.count() == 0  # no baseline was recorded


def test_http_balance_route(http_env):
    pack, _ = http_env.mint_pack("pay-bal", WEB_URL)
    client = TestClient(main.app, raise_server_exceptions=False)

    r = client.post(
        "/v1/recheck/pack-balance", json={"pack_id": pack["pack_id"]}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["credits_remaining"] == 250
    assert body["url"] == WEB_URL

    r = client.post("/v1/recheck/pack-balance", json={"pack_id": "pack_nope"})
    assert r.status_code == 404

    r = client.post(
        "/v1/recheck/pack-balance",
        json={"pack_id": pack["pack_id"], "url": OTHER_URL},
    )
    assert r.status_code == 404
    # Reads never spend.
    assert http_env.get_pack(pack["pack_id"])["credits_remaining"] == 250
