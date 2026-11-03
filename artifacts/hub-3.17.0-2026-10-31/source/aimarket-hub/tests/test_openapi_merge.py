"""Same-origin paid routes join the hub's /openapi.json (where x402 indexers look)."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from aimarket_hub import openapi_merge

HUB = "https://modelmarket.dev"
SIDECAR = f"{HUB}/x402/openapi.json"


def _doc(server: str | None = HUB, **paths):
    doc = {"openapi": "3.1.0", "info": {"title": "x", "version": "1"}, "paths": paths or {
        "/x402/weather-now": {"post": {"summary": "Weather", "x-payment-info": {"price": {"mode": "fixed", "amount": "0.001"}}}},
    }}
    if server:
        doc["servers"] = [{"url": server}]
    return doc


@pytest.fixture(autouse=True)
def _clean():
    openapi_merge.reset()
    yield
    openapi_merge.reset()


def _client(payload, status=200):
    def handler(request):
        return httpx.Response(status, json=payload)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_only_documents_on_the_hubs_origin_are_configured(monkeypatch):
    monkeypatch.setenv("AIMARKET_OPENAPI_MERGE_URLS", f"{SIDECAR}, https://evil.example/openapi.json")
    assert openapi_merge.merge_urls(HUB) == [SIDECAR]
    assert openapi_merge.merge_urls("") == []


def test_paid_paths_are_added_and_marked_public():
    asyncio.run(openapi_merge.refresh([SIDECAR], _client(_doc())))
    base = {"openapi": "3.1.0", "paths": {"/mcp": {"post": {}}}}
    out = openapi_merge.merged(base)
    assert set(out["paths"]) == {"/mcp", "/x402/weather-now"}
    assert out["paths"]["/x402/weather-now"]["post"]["security"] == []
    assert base["paths"] == {"/mcp": {"post": {}}}, "the hub's own schema is never mutated"


def test_a_sidecar_never_shadows_a_hub_route():
    asyncio.run(openapi_merge.refresh([SIDECAR], _client(_doc(**{"/mcp": {"post": {"summary": "fake"}}}))))
    base = {"paths": {"/mcp": {"post": {"summary": "real"}}}}
    assert openapi_merge.merged(base)["paths"]["/mcp"]["post"]["summary"] == "real"


def test_foreign_servers_and_absolute_paths_are_refused():
    assert openapi_merge.accepted_paths(_doc(server="https://other.example"), SIDECAR) == {}
    doc = _doc(**{"https://evil.example/x": {"get": {}}, "//evil.example/y": {"get": {}}, "/ok": {"get": {}}})
    assert set(openapi_merge.accepted_paths(doc, SIDECAR)) == {"/ok"}


def test_a_failed_fetch_keeps_the_last_good_copy():
    asyncio.run(openapi_merge.refresh([SIDECAR], _client(_doc())))
    asyncio.run(openapi_merge.refresh([SIDECAR], _client({"detail": "down"}, status=502)))
    assert "/x402/weather-now" in openapi_merge.merged({"paths": {}})["paths"]


def test_without_configuration_the_document_is_untouched():
    base = {"paths": {"/mcp": {}}}
    assert openapi_merge.merged(base) is base


def test_the_hubs_openapi_json_lists_the_merged_routes(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from aimarket_hub.api import create_app
    from aimarket_hub.config import HubConfig
    from aimarket_hub.database import HubDatabase
    from aimarket_hub.signing import Signer

    monkeypatch.setenv("AIMARKET_AUTO_CRAWL", "0")
    config = HubConfig()
    config.db_path = str(tmp_path / "hub.db")
    config.signing_key_path = str(tmp_path / "key")
    app = create_app(config=config, db=HubDatabase(tmp_path / "hub.db"), signer=Signer(tmp_path / "key"))
    with TestClient(app) as client:
        assert "/x402/weather-now" not in client.get("/openapi.json").json()["paths"]
        openapi_merge.set_source(SIDECAR, openapi_merge.accepted_paths(_doc(), SIDECAR))
        paths = client.get("/openapi.json").json()["paths"]
        assert paths["/x402/weather-now"]["post"]["security"] == []
        assert "/mcp" in paths
