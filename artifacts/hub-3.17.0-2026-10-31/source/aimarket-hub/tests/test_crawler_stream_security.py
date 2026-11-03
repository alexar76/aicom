"""Crawler requests pin DNS and enforce response limits before buffering."""

from __future__ import annotations

import socket
from types import SimpleNamespace

import httpx
import pytest

from aimarket_hub import crawler as crawler_module
from aimarket_hub.crawler import Crawler, MAX_RESPONSE_BYTES


def _public_dns(_host, port, *_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def _bare_crawler(client: httpx.AsyncClient) -> Crawler:
    crawler = Crawler.__new__(Crawler)
    crawler.config = SimpleNamespace(hub_url="https://local-hub.example")
    crawler._http = client
    return crawler


@pytest.mark.asyncio
async def test_crawler_connects_to_the_pinned_ip(monkeypatch) -> None:
    monkeypatch.setattr(crawler_module, "_url_is_safe", lambda _url: True)
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "peer.example"
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            json={"ok": True},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await _bare_crawler(client)._safe_get("https://peer.example/manifest")

    assert response.json() == {"ok": True}


class _CountingStream(httpx.AsyncByteStream):
    def __init__(self, chunks: int, chunk_size: int):
        self.chunks = chunks
        self.chunk_size = chunk_size
        self.yielded = 0

    async def __aiter__(self):
        for _ in range(self.chunks):
            self.yielded += 1
            yield b"x" * self.chunk_size


@pytest.mark.asyncio
async def test_chunked_response_stops_at_limit_before_full_download(monkeypatch) -> None:
    monkeypatch.setattr(crawler_module, "_url_is_safe", lambda _url: True)
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)
    stream = _CountingStream(chunks=100, chunk_size=65536)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "application/json"}, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match="exceeds 2 MB"):
            await _bare_crawler(client)._safe_get("https://peer.example/manifest")

    assert stream.yielded < stream.chunks
    assert stream.yielded <= (MAX_RESPONSE_BYTES // stream.chunk_size) + 1
