"""Which URL a routed invoke is POSTed to.

Transport used to be picked by matching a peer's self-declared categories against a
hardcoded list — ("oracle", "simulation", "math-viz", "randomness-beacon") — and only
those peers were asked where to send invokes. Everything else got the legacy
/capabilities/{product}/{cap}/invoke path whatever it advertised.

GAIA, the physical-world sensor gateway, declares ["iot", "sensors", "physical-data",
"verification"] and advertises mcp_endpoint https://iot.modelmarket.dev/ai-market/v2/invoke.
The hub POSTed the legacy path, that path answers 405, and every routed invoke of a live,
priced, Ed25519-signed sensor reading came back 502 "Provider returned 405" — while the
same capability answered fine when called directly.

These tests are deliberately app-free: both available interpreters fail to build the
FastAPI app (3.9 lacks StrEnum, the 3.11 venv has a fastapi/starlette skew), so anything
asserted through a TestClient here cannot run at all.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from aimarket_hub import peer_routing


@dataclass
class FakePeer:
    url: str
    well_known_url: str = ""
    categories: list[str] = field(default_factory=list)


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


@pytest.fixture(autouse=True)
def _clear_endpoint_cache():
    peer_routing._peer_endpoint_cache.clear()
    yield
    peer_routing._peer_endpoint_cache.clear()


def _stub_safe_get(monkeypatch, handler):
    calls: list[str] = []

    async def fake_safe_get(url: str, **_kw: Any) -> FakeResponse:
        calls.append(url)
        return handler(url)

    import aimarket_hub.outbound_http as outbound

    monkeypatch.setattr(outbound, "safe_get", fake_safe_get, raising=False)
    return calls


def test_iot_peer_gets_its_advertised_endpoint(monkeypatch):
    """The regression. None of these categories are in the old allow-list."""
    peer = FakePeer(
        url="https://iot.modelmarket.dev",
        well_known_url="https://iot.modelmarket.dev/.well-known/ai-market.json",
        categories=["iot", "sensors", "physical-data", "verification"],
    )
    _stub_safe_get(
        monkeypatch,
        lambda _u: FakeResponse({"mcp_endpoint": "https://iot.modelmarket.dev/ai-market/v2/invoke"}),
    )

    endpoint = asyncio.run(peer_routing._peer_invoke_endpoint(peer))

    assert endpoint == "https://iot.modelmarket.dev/ai-market/v2/invoke"


def test_peer_advertising_nothing_falls_back_to_the_legacy_path(monkeypatch):
    peer = FakePeer(url="https://legacy.example", well_known_url="https://legacy.example/.well-known/ai-market.json")
    _stub_safe_get(monkeypatch, lambda _u: FakeResponse({"name": "legacy hub"}))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None


def test_a_negative_answer_is_cached_so_every_invoke_does_not_refetch(monkeypatch):
    peer = FakePeer(url="https://legacy.example", well_known_url="https://legacy.example/.well-known/ai-market.json")
    calls = _stub_safe_get(monkeypatch, lambda _u: FakeResponse({"name": "legacy hub"}))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None
    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None

    # One well-known fetch, not one per invoke.
    assert len(calls) == 1


def test_positive_answer_is_cached(monkeypatch):
    peer = FakePeer(url="https://iot.example", well_known_url="https://iot.example/.well-known/ai-market.json")
    calls = _stub_safe_get(monkeypatch, lambda _u: FakeResponse({"mcp_endpoint": "https://iot.example/inv"}))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) == "https://iot.example/inv"
    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) == "https://iot.example/inv"
    assert len(calls) == 1


def test_unreachable_well_known_is_not_cached(monkeypatch):
    """A peer that is briefly down must not be pinned to the legacy transport.

    Caching the fallback would keep sending a v2 peer down the legacy path for the
    whole TTL after one failed lookup — the same class of mistake as deciding the
    transport from a category label instead of asking.
    """
    peer = FakePeer(url="https://flaky.example", well_known_url="https://flaky.example/.well-known/ai-market.json")

    state = {"fail": True}

    def handler(_url: str) -> FakeResponse:
        if state["fail"]:
            raise RuntimeError("connection refused")
        return FakeResponse({"mcp_endpoint": "https://flaky.example/inv"})

    _stub_safe_get(monkeypatch, handler)

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None
    assert "https://flaky.example" not in peer_routing._peer_endpoint_cache

    state["fail"] = False
    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) == "https://flaky.example/inv"


def test_non_200_well_known_yields_no_endpoint(monkeypatch):
    peer = FakePeer(url="https://gone.example", well_known_url="https://gone.example/.well-known/ai-market.json")
    _stub_safe_get(monkeypatch, lambda _u: FakeResponse({}, status_code=404))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None


def test_peer_without_a_well_known_url_needs_no_fetch(monkeypatch):
    peer = FakePeer(url="https://bare.example")
    calls = _stub_safe_get(monkeypatch, lambda _u: FakeResponse({"mcp_endpoint": "nope"}))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None
    assert calls == []


def test_blank_advertised_endpoint_is_treated_as_absent(monkeypatch):
    peer = FakePeer(url="https://blank.example", well_known_url="https://blank.example/.well-known/ai-market.json")
    _stub_safe_get(monkeypatch, lambda _u: FakeResponse({"mcp_endpoint": "   "}))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer)) is None


def test_cache_expires(monkeypatch):
    peer = FakePeer(url="https://ttl.example", well_known_url="https://ttl.example/.well-known/ai-market.json")
    calls = _stub_safe_get(monkeypatch, lambda _u: FakeResponse({"mcp_endpoint": "https://ttl.example/inv"}))

    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer, now=1000.0)) == "https://ttl.example/inv"
    assert asyncio.run(peer_routing._peer_invoke_endpoint(peer, now=1000.0 + peer_routing._PEER_ENDPOINT_TTL_S - 1)) is not None
    assert len(calls) == 1

    asyncio.run(peer_routing._peer_invoke_endpoint(peer, now=1000.0 + peer_routing._PEER_ENDPOINT_TTL_S + 1))
    assert len(calls) == 2
