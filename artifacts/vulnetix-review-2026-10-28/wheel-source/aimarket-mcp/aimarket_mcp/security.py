"""Security core for the ecosystem MCP gateway — vendored from metis's audited helpers so
the server has zero coupling but the same hardening: SSRF-safe outbound HTTP (scheme
allow-list, private-IP block, per-redirect re-validation) and untrusted-output sanitization.
"""
from __future__ import annotations

import asyncio
import html
import ipaddress
import math
import re
import socket
import weakref
import zlib
from typing import Optional, Set
from urllib.parse import urlparse, urlunparse

import httpx

_BLOCKED_HOSTS = frozenset({
    "localhost", "localhost.localdomain",
    "metadata.google.internal", "metadata.goog",
})
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_MAX_REDIRECTS = 3
_MAX_TOOL_OUTPUT = 50_000
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_CONCURRENT_REQUESTS = 8
_request_limits: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _non_public(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Private, loopback, link-local, reserved or multicast — or an IPv6 address carrying such
    an IPv4 one: IPv4-mapped, 6to4 (2002::/16) and NAT64 (64:ff9b::/96, where 64:ff9b::a00:5
    is 10.0.0.5) all reach that IPv4 address on a host that routes them, and Python calls
    the NAT64 form global."""
    if (addr.is_private or addr.is_loopback or addr.is_link_local
            or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
        return True
    if addr.version == 6:
        embedded = addr.ipv4_mapped or addr.sixtofour
        if embedded is None and addr in _NAT64:
            embedded = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
        if embedded is not None:
            return _non_public(embedded)
    return False


def _is_private_ip(hostname: str) -> bool:
    try:
        return _non_public(ipaddress.ip_address(hostname))
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(hostname, None):
            if _non_public(ipaddress.ip_address(info[4][0].split("%", 1)[0])):
                return True
    except (socket.gaierror, OSError, UnicodeError):
        return True   # fail closed on resolution failure
    return False


def validate_url(url: str, *, allowed_schemes: Optional[Set[str]] = None) -> str:
    schemes = allowed_schemes or _ALLOWED_SCHEMES
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed")
    if not parsed.hostname:
        raise ValueError("URL must include a hostname")
    host = parsed.hostname.lower()
    if host in _BLOCKED_HOSTS:
        raise ValueError(f"Hostname '{host}' is not allowed")
    if _is_private_ip(host):
        raise ValueError(f"Hostname '{host}' resolves to a private/reserved address")
    return url.strip()


def _validated_ips(hostname: str) -> list[str]:
    """Every address this name resolves to, or raise if ANY of them is non-public.

    Any, not all: a name that answers with one public and one private address is a name
    whose next resolution is a coin flip, and the coin is the attacker's.
    """
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return [hostname]
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError, UnicodeError) as exc:
        raise ValueError(f"Hostname '{hostname}' does not resolve") from exc
    out: list[str] = []
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if _non_public(addr):
            raise ValueError(f"Hostname '{hostname}' resolves to a private/reserved address")
        out.append(str(addr))
    if not out:
        raise ValueError(f"Hostname '{hostname}' does not resolve")
    return list(dict.fromkeys(out))


def pin_target(url: str) -> tuple[str, dict, dict]:
    """The URL to actually request, plus the headers and httpx extensions pinning requires.

    `validate_url` resolved the hostname and checked the answers — and then the request was
    made against the HOSTNAME, so httpx resolved it a second time at connect. Nothing
    carried the address that passed the check, which is a plain TOCTOU: a name that answers
    public once and private a moment later walks straight through, and that is the whole
    DNS-rebinding technique rather than an exotic corner of it.

    So the request goes to the validated IP with the original Host header. HTTPS used to be
    left on the hostname, on the belief that pinning breaks SNI and certificate validation;
    it does not: the ``sni_hostname`` extension sends the name in the TLS handshake and the
    certificate is verified against it. The HTTPS gap was the class of Vulnetix
    GCVE-110-PYPI-2026-021946 (signal-hunt).
    """
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        return url, {}, {}
    ips = _validated_ips(host)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return url, {}, {}                  # already an IP literal; nothing to pin
    try:
        # Host and SNI carry the ASCII form; httpx cannot put a Unicode name in a header.
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError(f"Hostname '{host}' is not a valid name") from exc
    chosen = ips[0]
    netloc = f"[{chosen}]" if ":" in chosen else chosen
    host_header = ascii_host
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
        host_header = f"{ascii_host}:{parsed.port}"
    pinned = urlunparse((
        parsed.scheme, netloc, parsed.path or "/", parsed.params, parsed.query, parsed.fragment,
    ))
    extensions = {"sni_hostname": ascii_host} if parsed.scheme == "https" else {}
    return pinned, {"Host": host_header}, extensions


def _request_limit() -> asyncio.Semaphore:
    # CLI callers and test clients can own separate event loops; a semaphore
    # bound to one loop must not be reused by another.
    loop = asyncio.get_running_loop()
    if loop not in _request_limits:
        _request_limits[loop] = asyncio.Semaphore(_MAX_CONCURRENT_REQUESTS)
    return _request_limits[loop]


def _check_limits(timeout: float, max_bytes: int) -> None:
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be finite and positive")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")


async def _read_capped_response(resp: httpx.Response, max_bytes: int) -> httpx.Response:
    """Bound decoded bytes while streaming, including a highly compressed body.

    httpx's buffered get/post allocate the whole response before a length check.
    Even aiter_bytes can inflate one compressed network chunk before yielding it.
    Feed bounded raw chunks through a decoder with an explicit output ceiling.
    """
    encoding = resp.headers.get("content-encoding", "").strip().lower()
    if encoding not in ("", "identity", "gzip", "deflate"):
        raise ValueError("Unsupported response content encoding")
    decoder = (zlib.decompressobj(31 if encoding == "gzip" else zlib.MAX_WBITS)
               if encoding in ("gzip", "deflate") else None)
    body = bytearray()

    def append(chunk: bytes) -> None:
        if len(body) + len(chunk) > max_bytes:
            raise ValueError(f"Response exceeds {max_bytes} decoded bytes")
        body.extend(chunk)

    try:
        async for raw in resp.aiter_raw(chunk_size=16_384):
            if decoder is None:
                append(raw)
                continue
            append(decoder.decompress(raw, max_bytes - len(body) + 1))
            while decoder.unconsumed_tail:
                append(decoder.decompress(decoder.unconsumed_tail, max_bytes - len(body) + 1))
            if decoder.unused_data:
                raise ValueError("Unexpected data after compressed response")
        if decoder is not None:
            # Do not use flush(): its length argument is a buffer hint, not a cap.
            while chunk := decoder.decompress(b"", max_bytes - len(body) + 1):
                append(chunk)
            if not decoder.eof:
                raise ValueError("Incomplete compressed response")
    except zlib.error as exc:
        raise ValueError("Invalid compressed response") from exc
    headers = [(key, value) for key, value in resp.headers.multi_items()
               if key.lower() not in ("content-encoding", "content-length")]
    return httpx.Response(resp.status_code, headers=headers, content=bytes(body),
                          request=resp.request, extensions=resp.extensions)


async def safe_get(url: str, *, timeout: float = 15.0, max_redirects: int = _MAX_REDIRECTS,
                   headers: Optional[dict] = None, max_bytes: int = _MAX_RESPONSE_BYTES) -> httpx.Response:
    """GET with pinned redirects, capped decoded output and a whole-request deadline."""
    _check_limits(timeout, max_bytes)
    if not isinstance(max_redirects, int) or not 0 <= max_redirects <= _MAX_REDIRECTS:
        raise ValueError(f"max_redirects must be between 0 and {_MAX_REDIRECTS}")

    async def request() -> httpx.Response:
        async with _request_limit():
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False,
                headers={"Accept-Encoding": "gzip, deflate", **(headers or {})},
            ) as client:
                current = url
                for _ in range(max_redirects + 1):
                    # DNS must not block the event loop. The checked address is
                    # still the one httpx receives, with the original Host/SNI.
                    target, pin_headers, extensions = await asyncio.to_thread(
                        lambda: pin_target(validate_url(current))
                    )
                    async with client.stream("GET", target, headers=pin_headers or None,
                                             extensions=extensions or None) as resp:
                        if resp.status_code in (301, 302, 303, 307, 308):
                            loc = resp.headers.get("location")
                            if loc:
                                current = str(httpx.URL(current).join(loc))
                                continue
                        return await _read_capped_response(resp, max_bytes)
                raise ValueError(f"Too many redirects (max {max_redirects})")

    try:
        return await asyncio.wait_for(request(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise httpx.TimeoutException("Outbound request deadline exceeded") from exc


async def safe_post(url: str, *, data=None, json=None, timeout: float = 30.0,
                    headers: Optional[dict] = None, max_bytes: int = _MAX_RESPONSE_BYTES) -> httpx.Response:
    _check_limits(timeout, max_bytes)

    async def request() -> httpx.Response:
        async with _request_limit():
            target, pin_headers, extensions = await asyncio.to_thread(
                lambda: pin_target(validate_url(url))
            )
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False,
                headers={"Accept-Encoding": "gzip, deflate", **(headers or {})},
            ) as client:
                async with client.stream("POST", target, data=data, json=json,
                                         headers=pin_headers or None,
                                         extensions=extensions or None) as resp:
                    return await _read_capped_response(resp, max_bytes)

    try:
        return await asyncio.wait_for(request(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise httpx.TimeoutException("Outbound request deadline exceeded") from exc


_ROLE_MARKER = re.compile(r"\[\s*(system|assistant|user|human|ai)\s*\]\s*", re.I)


def sanitize_tool_output(output: str, *, max_length: int = _MAX_TOOL_OUTPUT) -> str:
    """Neutralize untrusted tool/web output before it reaches the model: strip forged role
    markers (fixpoint), cap length, and wrap in an <untrusted> boundary."""
    text = output or ""
    if len(text) > max_length:
        text = text[:max_length] + "\n…[truncated]"
    for _ in range(8):                       # fixpoint — nested markers can't reconstruct
        stripped = _ROLE_MARKER.sub("", text)
        if stripped == text:
            break
        text = stripped
    return f"<untrusted>\n{text}\n</untrusted>"


_TAG = re.compile(r"<(script|style|noscript|template|svg)\b.*?</\1>", re.I | re.S)
_BLOCK = re.compile(r"</(p|div|li|h[1-6]|tr|section|article|br)>", re.I)
_ANYTAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")
_NL = re.compile(r"\n\s*\n\s*\n+")


def extract_main_text(html_text: str, *, max_chars: int = 20_000) -> str:
    """Dependency-free readability-lite: drop scripts/styles, keep block structure, unescape
    entities, collapse whitespace. Good enough to feed a model; never executes anything."""
    body = html_text
    m = re.search(r"<body\b[^>]*>(.*)</body>", body, re.I | re.S)
    if m:
        body = m.group(1)
    body = _TAG.sub(" ", body)
    body = _BLOCK.sub("\n", body)
    body = _ANYTAG.sub("", body)
    body = html.unescape(body)
    body = _WS.sub(" ", body)
    body = _NL.sub("\n\n", body)
    body = "\n".join(line.strip() for line in body.splitlines())
    body = body.strip()
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…[truncated]"
    return body
