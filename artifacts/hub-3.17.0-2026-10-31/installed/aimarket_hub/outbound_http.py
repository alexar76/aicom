"""SSRF-safe outbound HTTP for hub invoke and federation."""

from __future__ import annotations

import asyncio
import os
import zlib
from ipaddress import ip_address
from urllib.parse import urlparse, urlunparse

import httpx

from aimarket_hub import crawler as _crawler


def _url_is_safe(url: str) -> bool:
    # Dynamic delegation, NOT `from crawler import _url_is_safe`: an import-time
    # binding freezes whichever function crawler held when THIS module was first
    # imported, so a monkeypatch on crawler._url_is_safe would apply only for
    # some import orders (the test_cross_hub_integration vs
    # test_invoke_host_gateway collection-order flake).
    return _crawler._url_is_safe(url)


def invoke_gateway_hosts() -> tuple[str, ...]:
    """Operator-named hosts this hub may invoke (docker service names, host-gateway).

    ``AIMARKET_INVOKE_HOST_GATEWAY`` is a comma-separated list so one hub can
    reach more than one local provider (AEGIS ``api`` and KOVA ``kova-api``).
    """
    raw = os.environ.get("AIMARKET_INVOKE_HOST_GATEWAY", "").strip()
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def resolve_invoke_url(url: str) -> str:
    """Rewrite localhost invoke_url so Hub in Docker can reach host-side providers.

    Publishers still register ``http://127.0.0.1:PORT/invoke`` (dev manifest).
    When ``AIMARKET_INVOKE_HOST_GATEWAY`` is set (e.g. ``host.docker.internal``),
    outbound calls use the first gateway hostname instead.
    """
    gateways = invoke_gateway_hosts()
    if not gateways or not url:
        return url
    parsed = urlparse(url)
    if parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        return url
    gateway = gateways[0]
    port = parsed.port
    netloc = f"{gateway}:{port}" if port else gateway
    return urlunparse(parsed._replace(netloc=netloc))


def invoke_url_is_safe(url: str) -> bool:
    """SSRF check for provider invoke_url (allows configured host gateway)."""
    parsed = urlparse(url)
    if os.environ.get("AIMARKET_ALLOW_LOCAL_PUBLISH", "").strip() == "1":
        if parsed.hostname in ("127.0.0.1", "localhost", "::1"):
            return url.startswith(("http://", "https://")) and "\r" not in url and "\n" not in url
    host = (parsed.hostname or "").lower()
    if host and host in invoke_gateway_hosts():
        return url.startswith(("http://", "https://")) and "\r" not in url and "\n" not in url
    return _url_is_safe(url)


def assert_url_safe(url: str) -> None:
    if not _url_is_safe(url):
        raise ValueError(f"unsafe outbound URL: {url}")


def assert_invoke_url_safe(url: str) -> None:
    if not invoke_url_is_safe(url):
        raise ValueError(f"unsafe invoke URL: {url}")


# httpx honours the request-level ``sni_hostname`` extension (driving both TLS SNI
# and certificate hostname validation) from 0.23 onward; only then can https be
# pinned to an IP without breaking cert validation. Older httpx → https left unpinned.
_HTTPS_PIN_OK = tuple(int(p) for p in (httpx.__version__.split(".") + ["0", "0"])[:2]) >= (0, 23)


def _pin_target(url: str, *, allow_hosts: set[str] | None = None) -> tuple[str, dict[str, str], dict[str, str]]:
    """Close the SSRF DNS-rebinding window: resolve the host to a validated IP ONCE
    and connect to that pinned IP, so the connection cannot be re-pointed to a
    private/metadata IP between validation and connect.

    Returns (target_url, extra_headers, extensions). The target host is rewritten to
    the pinned IP with the original ``Host`` header; for https a ``sni_hostname``
    extension keeps TLS SNI + certificate validation on the real hostname. Raises
    ValueError if any resolved address is on the blocklist (SSRF caught).

    Returns the URL unchanged only for literal-IP hosts and explicitly-allowed
    operator hosts (localhost / configured invoke gateway). DNS failure and an
    httpx version too old for HTTPS pinning fail closed: falling back to a normal
    hostname request would recreate the DNS-rebinding window this function closes.
    """
    import socket

    parsed = urlparse(url)
    host = parsed.hostname
    if not host or parsed.scheme not in ("http", "https"):
        return url, {}, {}
    if allow_hosts and host in allow_hosts:
        return url, {}, {}  # intentionally-allowed localhost / host-gateway
    try:
        ip_address(host)
        return url, {}, {}  # already a literal IP (validated upstream)
    except ValueError:
        pass
    if parsed.scheme == "https" and not _HTTPS_PIN_OK:
        raise ValueError("installed httpx cannot safely pin HTTPS destinations")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise ValueError(f"cannot safely resolve outbound host {host}") from exc
    safe_ip: str | None = None
    for _family, _, _, _, sockaddr in infos:
        try:
            addr = ip_address(sockaddr[0])
        except ValueError:
            continue
        # The same rule as the validation lookup (crawler._addr_is_blocked), not a shorter
        # list: this is the answer actually connected to, so a name that answered a public
        # address first and 198.18.0.10 now must be refused here, not only there.
        if _crawler._addr_is_blocked(addr):
            raise ValueError(f"host {host} resolves to a blocked network ({sockaddr[0]})")
        if safe_ip is None:
            safe_ip = sockaddr[0]
    if safe_ip is None:
        raise ValueError(f"outbound host {host} resolved to no usable address")
    netloc = f"[{safe_ip}]" if ":" in safe_ip else safe_ip
    if parsed.port:
        netloc += f":{parsed.port}"
    headers = {"Host": parsed.netloc}
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}
    return urlunparse(parsed._replace(netloc=netloc)), headers, extensions


def _checked_target(url: str, *, invoke: bool = False) -> tuple[str, dict[str, str], dict[str, str]]:
    """Validate an outbound URL and pin it (``_pin_target``). Both steps resolve the host
    with a blocking getaddrinfo, so async callers run this off the event loop."""
    target = resolve_invoke_url(url) if invoke else url
    if invoke:
        assert_invoke_url_safe(target)
    else:
        assert_url_safe(target)
    # Pin the validated IP (http + https) to defeat DNS rebinding. On the invoke path
    # the intentionally-allowed localhost / host-gateway targets are exempted so dev
    # and Docker gateways keep working; every other target (federation + external
    # providers) is pinned.
    return _pin_target(target, allow_hosts=_invoke_allow_hosts() if invoke else None)


def prepare_safe_request(url: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """Validate an attacker-influenced URL and return its pinned request target."""
    return _checked_target(url)


async def prepare_safe_request_async(url: str, *, invoke: bool = False) -> tuple[str, dict[str, str], dict[str, str]]:
    """``prepare_safe_request`` off the event loop. The name is often the caller's own (a
    webhook, a peer, a provider): on the loop, its slow nameserver would stall every
    request the hub is serving until it answered."""
    return await asyncio.to_thread(_checked_target, url, invoke=invoke)


def _invoke_allow_hosts() -> set[str]:
    """Hosts the invoke path intentionally allows and must NOT pin/block: loopback
    when local publish is enabled, plus any configured host gateway."""
    allow: set[str] = set()
    if os.environ.get("AIMARKET_ALLOW_LOCAL_PUBLISH", "").strip() == "1":
        allow |= {"127.0.0.1", "localhost", "::1"}
    allow.update(invoke_gateway_hosts())
    return allow


async def post_configured(
    url: str,
    *,
    json: dict | None = None,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """POST to a destination this hub was CONFIGURED with, not one a caller chose.

    The private-host refusal in ``_url_is_safe`` exists to stop a caller steering an
    outbound request at something internal. It is the wrong check for an address that came
    from the hub's own environment: an operator who sets
    ``AIMARKET_PIPELINE_EXECUTOR_URL=http://aicom-app-1:8080`` is naming a neighbour on the
    hub's own docker network on purpose, and refusing it produced the worst possible
    outcome — the reachable address was blocked while the address the guard allowed
    (``host.docker.internal``) did not resolve inside the container at all.

    So the check here is what actually protects anything at this point: a real http(s) URL
    with no header injection. The destination must never be taken from a request body — the
    single caller of this function reads it from the environment, and the route's tests pin
    that a body cannot supply one. No IP pinning either: pinning is a DNS-rebinding defence
    for attacker-influenced names, and it would break docker's service DNS for no gain.
    """
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError(f"configured destination is not an http(s) URL: {url!r}")
    if any(c in url for c in "\r\n\t"):
        raise ValueError("configured destination contains control characters")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.post(url, json=json, headers=headers or None)


async def get_configured(url: str, *, timeout: float = 30.0) -> httpx.Response:
    """GET a destination this hub was configured with. See `post_configured` for why the
    caller-SSRF rule is the wrong check for an operator-named address."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise ValueError(f"configured destination is not an http(s) URL: {url!r}")
    if any(c in url for c in "\r\n\t"):
        raise ValueError("configured destination contains control characters")
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.get(url)


async def safe_get(url: str, *, timeout: float = 10.0) -> httpx.Response:
    target, pin_headers, ext = await prepare_safe_request_async(url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        return await client.get(target, headers=pin_headers or None, extensions=ext or None)


async def safe_post(
    url: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    invoke: bool = False,
    oracle_paid: bool = False,
) -> httpx.Response:
    from aimarket_hub import oracle_paid_tier

    # Only the admitted-call flag can select a configured grant. Strip even a
    # caller-supplied spelling of the header; it is never payment evidence.
    transport_url = resolve_invoke_url(url) if invoke else url
    grant = oracle_paid_tier.headers_for(url, transport_url=transport_url, admitted=oracle_paid)
    target, pin_headers, ext = await prepare_safe_request_async(url, invoke=invoke)
    out_headers = {k: v for k, v in (headers or {}).items() if k.lower() != oracle_paid_tier.HEADER.lower()}
    out_headers.update(grant)
    out_headers.update(pin_headers)
    # A configured bearer grant must not be exposed to an ambient HTTP proxy.
    transport_options = {"trust_env": False} if grant else {}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, **transport_options) as client:
        return await client.post(target, json=json, headers=out_headers, extensions=ext or None)


class ResponseTooLarge(Exception):
    """A capped POST refused a reply before buffering all of it."""

    def __init__(self, limit: int, declared: int | None = None) -> None:
        self.limit = limit
        self.declared = declared
        super().__init__(
            f"response exceeds {limit} bytes"
            + (f" (declared {declared})" if declared else "")
        )


async def safe_post_capped(
    url: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_bytes: int,
    invoke: bool = False,
    with_headers: bool = False,
) -> tuple[int, bytes] | tuple[int, bytes, dict[str, str]]:
    """`safe_post`, but never buffer more than ``max_bytes`` of the reply.

    ``with_headers=True`` also returns the response headers (lower-cased names): an x402 V2
    seller puts its whole payment offer in ``PAYMENT-REQUIRED`` and answers the 402 with an
    empty body, so a caller that reads only the body sees no offer at all.

    ``safe_post`` reads ``resp.content``: the whole body, however large. That is fine for
    a provider this hub chose to route to, and wrong for the admission assay, whose entire
    job is to POST to hubs nobody has vetted yet. The cap the assay advertised was applied
    *after* the body was already in memory, so an unadmitted peer could answer a probe with
    a gigabyte and be refused only once the hub had swallowed it.

    Declared Content-Length is checked first and a stream that overruns the budget is cut
    off mid-body — an honest header is a cheap refusal, a dishonest one costs `max_bytes`.
    """
    status, body, reply_headers = await safe_request_capped(
        "POST", url, json=json, headers=headers, timeout=timeout, max_bytes=max_bytes,
        invoke=invoke,
    )
    if with_headers:
        return status, body, reply_headers
    return status, body


async def safe_request_capped(
    method: str,
    url: str,
    *,
    json: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    max_bytes: int,
    invoke: bool = False,
) -> tuple[int, bytes, dict[str, str]]:
    """`safe_post_capped` for any method, always with the reply headers (lower-cased).

    GET is what reading a stranger's discovery document needs (observed_sellers.py): the
    same pinned, size-capped transport as the assay's POST, never `safe_get`'s whole body.
    """
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    target, pin_headers, ext = await prepare_safe_request_async(url, invoke=invoke)
    # HTTPX's aiter_bytes decompresses each wire chunk without an output limit,
    # before yielding it to our counter. Decode raw bytes ourselves with a budget.
    out_headers = {k: v for k, v in (headers or {}).items() if k.lower() != "accept-encoding"}
    out_headers.update({**pin_headers, "Accept-Encoding": "gzip, deflate"})
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        request = client.build_request(
            method, target, json=json, headers=out_headers, extensions=ext or None
        )
        resp = await client.send(request, stream=True, follow_redirects=False)
        try:
            declared = resp.headers.get("content-length")
            if declared:
                try:
                    declared_len = int(declared)
                except ValueError as exc:
                    raise ValueError("Invalid Content-Length") from exc
                if declared_len < 0 or declared_len > max_bytes:
                    raise ResponseTooLarge(max_bytes, declared_len)
            encoding = resp.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("identity", "gzip", "deflate"):
                raise ValueError("Unsupported Content-Encoding for bounded response")
            decoder = None if encoding == "identity" else zlib.decompressobj(
                16 + zlib.MAX_WBITS if encoding == "gzip" else zlib.MAX_WBITS
            )
            body = bytearray()
            wire_bytes = 0
            async for chunk in resp.aiter_raw(chunk_size=16384):
                wire_bytes += len(chunk)
                if wire_bytes > max_bytes:
                    raise ResponseTooLarge(max_bytes)
                try:
                    decoded = decoder.decompress(chunk, max_bytes - len(body) + 1) if decoder else chunk
                except zlib.error as exc:
                    raise ValueError("Invalid compressed response") from exc
                body.extend(decoded)
                if len(body) > max_bytes:
                    raise ResponseTooLarge(max_bytes)
                # Reject concatenated streams/trailing garbage rather than silently
                # accepting a prefix. No unbounded decompress/flush fallback.
                if decoder and (decoder.unused_data or decoder.unconsumed_tail):
                    raise ValueError("Unexpected trailing compressed response data")
            if decoder and not decoder.eof:
                raise ValueError("Truncated compressed response")
            return resp.status_code, bytes(body), {k.lower(): v for k, v in resp.headers.items()}
        finally:
            await resp.aclose()
