"""A capped POST refuses an oversized reply BEFORE buffering it.

`safe_post` reads `resp.content` — everything the peer sends. The admission assay is the
one caller that POSTs to hosts nobody has vetted, and its advertised byte cap was applied
only after the whole body was already in memory. These pin that the cap is now a limit on
what the hub reads, not a note about what it kept.
"""

from __future__ import annotations

import socket
import gzip
import tracemalloc
import zlib

import httpx
import pytest

from aimarket_hub import crawler as crawler_module
from aimarket_hub import outbound_http
from aimarket_hub.outbound_http import ResponseTooLarge, safe_post_capped

CAP = 4096


def _public_dns(_host, port, *_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


class _CountingStream(httpx.AsyncByteStream):
    """Yields `chunks` chunks and remembers how many the reader actually pulled."""

    def __init__(self, chunks: int, chunk_size: int):
        self.chunks = chunks
        self.chunk_size = chunk_size
        self.yielded = 0

    async def __aiter__(self):
        for _ in range(self.chunks):
            self.yielded += 1
            yield b"x" * self.chunk_size


@pytest.fixture
def mocked(monkeypatch):
    """Route safe_post_capped's own client at a MockTransport, DNS pinned and safe."""
    monkeypatch.setattr(crawler_module, "_url_is_safe", lambda _url: True)
    monkeypatch.setattr(socket, "getaddrinfo", _public_dns)

    def _install(handler):
        class _Client(httpx.AsyncClient):
            def __init__(self, **kwargs):
                kwargs.pop("transport", None)
                super().__init__(transport=httpx.MockTransport(handler), **kwargs)

        monkeypatch.setattr(outbound_http.httpx, "AsyncClient", _Client)

    return _install


@pytest.mark.asyncio
async def test_small_reply_comes_back_whole(mocked) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["host"] == "peer.example"
        return httpx.Response(200, stream=_WireStream(b'{"ok": true}'))

    mocked(handler)
    status, body = await safe_post_capped(
        "https://peer.example/invoke", json={"a": 1}, max_bytes=CAP,
    )
    assert status == 200
    assert b'"ok"' in body


@pytest.mark.asyncio
async def test_declared_content_length_over_the_cap_is_refused(mocked) -> None:
    stream = _CountingStream(chunks=8, chunk_size=CAP)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-length": str(8 * CAP)}, stream=stream,
        )

    mocked(handler)
    with pytest.raises(ResponseTooLarge) as exc:
        await safe_post_capped("https://peer.example/invoke", json={}, max_bytes=CAP)
    assert exc.value.declared == 8 * CAP
    # An honest header costs nothing to refuse: not a byte of the body was read.
    assert stream.yielded == 0


@pytest.mark.asyncio
async def test_undeclared_body_stops_at_the_cap(mocked) -> None:
    stream = _CountingStream(chunks=200, chunk_size=CAP)

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream)

    mocked(handler)
    with pytest.raises(ResponseTooLarge):
        await safe_post_capped("https://peer.example/invoke", json={}, max_bytes=CAP)
    assert stream.yielded < stream.chunks


@pytest.mark.asyncio
async def test_a_private_destination_is_still_refused(mocked) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("an SSRF target was contacted")

    mocked(handler)
    monkey_safe = crawler_module._url_is_safe
    try:
        crawler_module._url_is_safe = lambda _url: False
        with pytest.raises(ValueError):
            await safe_post_capped("http://169.254.169.254/latest", json={}, max_bytes=CAP)
    finally:
        crawler_module._url_is_safe = monkey_safe


class _WireStream(httpx.AsyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


@pytest.mark.asyncio
async def test_gzip_bomb_is_refused_before_expanding_in_memory(mocked):
    # A small wire block must not allocate its entire 8 MiB decoded payload.
    wire = gzip.compress(b"x" * (8 * 1024 * 1024))
    stream = _WireStream(wire)

    async def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=stream)

    mocked(handler)
    tracemalloc.start()
    try:
        with pytest.raises(ResponseTooLarge):
            await safe_post_capped("https://peer.example/invoke", json={}, max_bytes=16384)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert stream.closed
    assert peak < 2 * 1024 * 1024, f"allocated {peak} bytes for a 16384-byte budget"


@pytest.mark.asyncio
async def test_valid_gzip_at_decoded_limit_is_supported(mocked):
    wire = gzip.compress(b"x" * CAP)
    stream = _WireStream(wire[:8], wire[8:])

    async def handler(request):
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=stream)

    mocked(handler)
    status, body = await safe_post_capped("https://peer.example/invoke", json={}, max_bytes=CAP)
    assert status == 200 and body == b"x" * CAP
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("encoding,wire", [
    ("gzip", gzip.compress(b"ok")[:-3]),
    ("gzip", gzip.compress(b"ok") + gzip.compress(b"second")),
    ("gzip", b"not-gzip"),
    ("br", b"unadvertised"),
    ("gzip, deflate", b"stacked"),
])
async def test_invalid_or_unsupported_compression_is_closed(mocked, encoding, wire):
    stream = _WireStream(wire)

    async def handler(request):
        assert request.headers["accept-encoding"] == "gzip, deflate"
        return httpx.Response(200, headers={"content-encoding": encoding}, stream=stream)

    mocked(handler)
    with pytest.raises(ValueError):
        await safe_post_capped("https://peer.example/invoke", json={}, max_bytes=CAP,
                               headers={"accept-encoding": "br"})
    assert stream.closed


@pytest.mark.asyncio
async def test_deflate_response_is_decoded_within_budget(mocked):
    stream = _WireStream(zlib.compress(b"x" * CAP))

    async def handler(request):
        return httpx.Response(200, headers={"content-encoding": "deflate"}, stream=stream)

    mocked(handler)
    status, body = await safe_post_capped("https://peer.example/invoke", json={}, max_bytes=CAP)
    assert status == 200 and body == b"x" * CAP
    assert stream.closed
