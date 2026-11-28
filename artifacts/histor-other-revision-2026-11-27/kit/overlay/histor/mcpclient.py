"""A read-only MCP client: ``server/discover``, legacy initialization, and ``tools/list``.

It never calls a tool, reads a resource or fetches a prompt, and it has no code path that could:
the method names are literals below. That is the whole contract with the servers HISTOR
observes — it reads what they publish to every client that connects, and no more.

Differences from the survey client in ``warden/scripts/mcp-survey/mcpclient.py``, each one a
requirement of MTL/1 or of running unattended against strangers:

* ``tools/list`` is **drained** across ``nextCursor`` pages (PROFILE.md section 5.1: a partial
  listing must not be digested);
* the connection is pinned to a checked public address (:mod:`histor.netguard`);
* one observation has ONE deadline across every request and page. A per-read timeout alone let
  an SSE keep-alive every few seconds, or a body trickled a byte at a time, hold a worker — and
  with it the whole crawl — for as long as the server liked;
* bodies are decompressed here, from the raw stream, with the size budget passed to zlib: the
  cap counts bytes we would hold, so a few hundred bytes of nested gzip cannot expand into a
  gigabyte first. At most one Content-Encoding, and only gzip or deflate;
* an SSE stream is split into lines as bytes, on CR/LF only (not on U+2028 and friends, which
  are ordinary characters inside a JSON string), with a bounded line length;
* the whole tool set is capped in bytes and in tools, across pages — the largest real set in
  the first production crawl was 1.5 MB and 1 376 tools;
* every value echoed back in a header is checked first, and anything the server does that we
  did not foresee becomes a status, never an exception out of :meth:`McpReader.list_tools`;
* redirects are not followed: the observation is of the endpoint the registry names.
"""

from __future__ import annotations

import json
import re
import time
import zlib
from dataclasses import dataclass, field
from typing import Any

import httpx

from histor import __version__
from histor.netguard import BlockedAddress, PinnedTarget, resolve_public
from histor.untrusted import TooDeep, loads_cut

PROTOCOL_VERSION = "2025-06-18"
MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)
_MODERN_ERRORS = frozenset((-32020, -32021, -32022))
_LEGACY_PROBE_ERRORS = frozenset((-32600, -32601, -32602))
_LEGACY_HTTP_STATUSES = frozenset((400, 404, 405))
# A first modern request refused with one of these and no recognized modern error in the body is a legacy
# server (MCP 2026-07-28, Streamable HTTP, Backward Compatibility: "a 4xx without a recognized modern error
# body"). 401/403 are here because legacy servers gate unknown methods behind auth while leaving initialize
# and tools/list open (mcp.kaiku.tech, 2026-11-01). Rate limits, timeouts and redirects are not.
_PROBE_HTTP_STATUSES = _LEGACY_HTTP_STATUSES | frozenset((401, 403))
_FIRST_MODERN_VERSION = "2026-07-28"  # earlier revisions open with initialize
# A 402 says why: a site that charges crawlers for each read (Cloudflare pay per crawl's crawler-price header, or
# a body that says "pay per crawl": api.groundtruths.xyz, 2026-11-02, matches "crawler" in the user agent), or
# an endpoint where every call is paid (x402). HISTOR pays for neither, and its user agent keeps naming it.
PAY_PER_CRAWL = "pay-per-crawl"
PAYMENT_REQUIRED = "payment-required"
_PAYMENT_BODY_BYTES = 16 * 1024
_PAY_PER_CRAWL_TEXT = re.compile(r"pay[\s_-]*per[\s_-]*crawl", re.I)
USER_AGENT = f"histor/{__version__} (+https://histor.modelmarket.dev/#crawler; read-only: discover + tools/list)"
MAX_BODY_BYTES = 4 * 1024 * 1024   # one response, decompressed
MAX_SET_BYTES = 3 * 1024 * 1024    # every tools/list page of one observation together
MAX_TOOLS = 5000
MAX_PAGES = 50
MAX_SSE_LINE = MAX_BODY_BYTES
_PROTOCOL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SESSION_RE = re.compile(r"^[\x21-\x7e]{1,256}$")  # MCP: visible ASCII only


@dataclass
class Observation:
    """What one connection attempt produced. ``status == "ok"`` means a fully drained tool list."""

    status: str
    detail: str = ""
    tools: list[Any] | None = None
    server_info: dict[str, Any] = field(default_factory=dict)
    protocol_version: str = ""
    pages: int = 0
    address: str = ""
    # A package observation (histor.packages): the npm/PyPI version the sandbox ran, the observer's
    # version, and what the package did there (install scripts, startup, canary tool calls).
    package_version: str = ""
    package_observer: str = ""
    behaviour: dict[str, Any] | None = None
    # Where it ran (image digest, runtime) and the configuration it was given (variable names,
    # start arguments): the conditions a reader needs to judge the observation by.
    package_conditions: dict[str, Any] | None = None
    package_supplied: dict[str, Any] | None = None
    # The server-level ``instructions`` of the handshake that produced this observation (histor.instructions).
    # ``instructions_read`` says the reader looked at it: False for a package observer that does not report it.
    instructions: Any = None
    instructions_read: bool = False


def _server_message(doc: Any) -> str:
    """The server's own words in an error body ({"message"}, {"error": {"message"}}, {"error": "…"}), bounded."""
    if not isinstance(doc, dict):
        return ""
    error = doc.get("error")
    for value in (doc.get("message"), error.get("message") if isinstance(error, dict) else error):
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            return "the server says: " + (text if len(text) <= 120 else text[:119] + "…")
    return ""


class _Stop(Exception):
    def __init__(self, status: str, detail: str = "") -> None:
        super().__init__(status)
        self.status = status
        self.detail = detail


class _HttpRejection(_Stop):
    """A bounded, parsed HTTP error from the initial modern-era probe only."""

    def __init__(self, status: int, message: Any) -> None:
        super().__init__(f"http-{status}")
        self.message = message


def _error_code(message: Any) -> int | None:
    error = message.get("error") if isinstance(message, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if type(code) is int else None


def _complete(message: Any, method: str) -> dict[str, Any]:
    if not isinstance(message, dict) or "error" in message or not isinstance(message.get("result"), dict):
        raise _Stop("protocol", f"{method} returned an error or no result")
    result = message["result"]
    # Missing resultType is complete for older implementations (§ Basic Protocol).
    kind = result.get("resultType", "complete")
    if kind == "input_required":
        raise _Stop("partial", f"{method} requires interactive input; not collected")
    if kind != "complete":
        raise _Stop("protocol", f"{method} returned an unsupported resultType")
    return result


class _DuplicateKey(ValueError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            # A duplicated member means two readers can disagree about what the server said.
            # Python keeps the last one silently; we refuse to guess.
            raise _DuplicateKey(key)
        out[key] = value
    return out


def parse_json(text: str | bytes) -> Any:
    # A server's answer is read as mcp-tool-set-digest/1 section 12 reads a tool list (untrusted.py).
    return loads_cut(text, object_pairs_hook=_strict_object)


class _Deadline:
    def __init__(self, seconds: float) -> None:
        self.at = time.monotonic() + seconds
        self.seconds = seconds

    def check(self) -> None:
        if time.monotonic() > self.at:
            raise _Stop("timeout", f"no complete answer within {self.seconds:g} s")


class _Decoder:
    """One Content-Encoding at most, decoded with the byte budget handed to zlib."""

    def __init__(self, encoding: str) -> None:
        codings = [c.strip() for c in encoding.lower().split(",") if c.strip() and c.strip() != "identity"]
        if len(codings) > 1:
            raise _Stop("protocol", f"stacked content-encodings are not accepted ({encoding})")
        self.coding = codings[0] if codings else ""
        if self.coding in ("gzip", "x-gzip"):
            self._z: Any = zlib.decompressobj(16 + zlib.MAX_WBITS)
        elif self.coding == "deflate":
            self._z = zlib.decompressobj(zlib.MAX_WBITS)
            self._raw_fallback = True
        elif self.coding:
            raise _Stop("protocol", f"content-encoding {self.coding!r} is not accepted")
        else:
            self._z = None

    def feed(self, chunk: bytes, budget: int) -> bytes:
        """Decode *chunk*, producing at most ``budget + 1`` bytes (one over means too large)."""
        if self._z is None:
            return chunk[: budget + 1]
        try:
            out = self._z.decompress(chunk, budget + 1)
        except zlib.error as exc:
            if self.coding == "deflate" and getattr(self, "_raw_fallback", False):
                # Some servers send raw deflate without the zlib header; retry once that way.
                self._raw_fallback = False
                self._z = zlib.decompressobj(-zlib.MAX_WBITS)
                return self.feed(chunk, budget)
            raise _Stop("protocol", f"{self.coding} body does not decode") from exc
        self._raw_fallback = False
        return out


def _offers_legacy(supported: list[str]) -> bool:
    """A version list naming a revision that opens with initialize, which this reader speaks."""
    return any(v < _FIRST_MODERN_VERSION for v in supported)


def _matching(message: Any, request_id: int) -> bool:
    return isinstance(message, dict) and type(message.get("id")) is int and message["id"] == request_id and (
        "result" in message or "error" in message
    )


class McpReader:
    def __init__(self, *, timeout: float = 20.0, allow_private: bool = False, transport: httpx.BaseTransport | None = None,
                 deadline: float | None = None, robots: Any = None):
        self.timeout = timeout
        self.allow_private = allow_private
        self._transport = transport
        # histor.robots.Policy for the crawler: a path the site's robots.txt disallows is not read.
        # None for a person's own one-off read (toolcost_cli, upgrade_capture), which is not crawling.
        self.robots = robots
        # One observation — initialize, the notification and every tools/list page — must finish
        # inside this, whatever the server does with the stream.
        self.deadline = deadline if deadline is not None else max(3 * timeout, 60.0)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 10.0)),
            follow_redirects=False,
            transport=self._transport,
            headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"},
        )

    def _post(self, client: httpx.Client, pinned: PinnedTarget, body: dict[str, Any], *, session: str | None,
              protocol: str | None, want_id: int | None, deadline: _Deadline,
              budget: int = MAX_BODY_BYTES, modern: bool = False, probe: bool = False) -> tuple[Any, httpx.Headers, int]:
        deadline.check()
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Host": pinned.host_header,
        }
        if protocol:
            headers["MCP-Protocol-Version"] = protocol
        if modern:
            headers["Mcp-Method"] = body["method"]
        if session and not modern:
            headers["Mcp-Session-Id"] = session
        extensions = {"sni_hostname": pinned.sni_hostname} if pinned.sni_hostname else {}
        remaining = min(self.timeout, max(0.001, deadline.at - time.monotonic()))
        request = client.build_request(
            "POST", pinned.url, content=json.dumps(body).encode(), headers=headers, extensions=extensions,
            timeout=httpx.Timeout(remaining, connect=min(remaining, 10.0)),
        )
        response = client.send(request, stream=True)
        try:
            if 300 <= response.status_code < 400:
                raise _Stop(f"http-{response.status_code}", "redirects are not followed")
            if response.status_code >= 400:
                if modern and response.status_code in (_PROBE_HTTP_STATUSES if probe else _LEGACY_HTTP_STATUSES):
                    message = self._http_error_body(response, deadline, min(budget, MAX_BODY_BYTES), want_id)
                    if probe:
                        raise _HttpRejection(response.status_code, message)
                    code = _error_code(message)
                    if code in _MODERN_ERRORS:
                        raise _Stop("protocol", f"modern {body['method']} returned MCP error {code}; no downgrade")
                if response.status_code == 402:
                    raise _Stop(*self._payment_reason(response, deadline))
                raise _Stop(f"http-{response.status_code}")
            if want_id is None:
                return None, response.headers, 0
            decoder = _Decoder(response.headers.get("content-encoding", ""))
            ctype = response.headers.get("content-type", "").lower()
            budget = min(budget, MAX_BODY_BYTES)
            if "text/event-stream" in ctype:
                message, size = self._read_sse(response, want_id, decoder, deadline, budget)
            else:
                message, size = self._read_json(response, want_id, decoder, deadline, budget, allow_batch=not modern)
            if modern and (message.get("jsonrpc") != "2.0" or ("result" in message) == ("error" in message)):
                raise _Stop("protocol", "invalid modern JSON-RPC response envelope")
            return message, response.headers, size
        finally:
            response.close()

    @classmethod
    def _payment_reason(cls, response: httpx.Response, deadline: _Deadline) -> tuple[str, str]:
        """What a 402 asks for, from its headers and the first 16 KiB of its body."""
        headers = response.headers
        try:
            body = b"".join(cls._decoded(response, _Decoder(headers.get("content-encoding", "")), deadline,
                                         _PAYMENT_BODY_BYTES, "payment response")).decode("utf-8", "replace")
        except _Stop:
            body = ""
        doc: Any = None
        if body.lstrip()[:1] == "{":
            try:
                doc = json.loads(body)
            except ValueError:
                doc = None
        price = headers.get("crawler-price") or (doc.get("price") if isinstance(doc, dict) else None)
        price = price.strip()[:40] if isinstance(price, str) and price.strip() else None
        if "crawler-price" in headers or _PAY_PER_CRAWL_TEXT.search(body):
            return PAY_PER_CRAWL, ("the site charges crawlers for each read" + (f" ({price})" if price else "")
                                   + "; HISTOR does not pay for reads")
        if "payment-required" in headers or (isinstance(doc, dict) and ("x402Version" in doc or isinstance(doc.get("accepts"), list))):
            return PAYMENT_REQUIRED, "every call to this endpoint is paid (x402); HISTOR does not pay"
        return "http-402", _server_message(doc)

    @classmethod
    def _http_error_body(cls, response: httpx.Response, deadline: _Deadline, budget: int, want_id: int | None) -> Any:
        decoder = _Decoder(response.headers.get("content-encoding", ""))
        ctype = response.headers.get("content-type", "").lower()
        if "text/event-stream" in ctype and want_id is not None:
            message, _ = cls._read_sse(response, want_id, decoder, deadline, budget)
        else:
            body = b"".join(cls._decoded(response, decoder, deadline, budget, "error response")).strip()
            if not body:
                return None
            try:
                message = cls._parse(body, "error response")
            except _Stop as exc:
                # A legacy HTTP endpoint may answer the modern probe with plain HTML/text.
                # Malformed JSON, duplicate keys, nesting/size/decompression failures are not
                # evidence of legacy semantics and must never trigger a downgrade.
                if (exc.detail == "error response is not JSON" and body[:1] not in (b"{", b"[")
                        and "json" not in ctype):
                    return None
                raise
        if isinstance(message, dict) and "error" in message and not isinstance(message["error"], dict):
            # Not JSON-RPC at all ({"error": "Bad Request", "message": ...}, api.xdata.kr): there is no
            # modern error to recognize, so it is the legacy rejection the specification falls back on.
            return None
        if isinstance(message, list) or (isinstance(message, dict) and "error" in message and (
            message.get("jsonrpc") != "2.0" or _error_code(message) is None or "result" in message
        )):
            raise _Stop("protocol", "malformed JSON-RPC error response; no downgrade")
        if isinstance(message, dict) and "result" in message:
            raise _Stop("protocol", "HTTP error carried a result; no downgrade")
        if isinstance(message, dict) and "error" in message and message.get("id") is not None and (
            type(message["id"]) is not int or message["id"] != want_id
        ) and _error_code(message) in _MODERN_ERRORS:
            # A legacy code under a foreign id is still a legacy rejection: the Python SDK answers the
            # unsupported-version case with id "server-error" (mcp.quotewise.io). A modern code must be ours.
            raise _Stop("protocol", "HTTP error did not match our request id; no downgrade")
        return message

    @staticmethod
    def _modern_body(method: str, request_id: int, protocol: str, *, cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"_meta": {
            "io.modelcontextprotocol/protocolVersion": protocol,
            "io.modelcontextprotocol/clientInfo": {"name": "histor", "version": __version__},
            "io.modelcontextprotocol/clientCapabilities": {},
        }}
        if cursor is not None:
            params["cursor"] = cursor
        return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

    def _discover(self, client: httpx.Client, pinned: PinnedTarget, deadline: _Deadline,
                  obs: Observation) -> str | None:
        """Modern discovery first; return None for a legacy server (initialize follows).

        Legacy, per the specification's HTTP rule:
        - a 400/404/405/401/403 whose body is no recognized modern error;
        - a result that is no DiscoverResult;
        - a version list holding only revisions that open with initialize.

        A recognized modern error under our id commits the observation to that era. Never
        initialize after one, after a malformed modern-looking response, or after a rate limit,
        timeout, server error or redirect. Version selection is restricted to revisions this
        reader actually implements.
        """
        protocol = MODERN_PROTOCOL_VERSIONS[0]
        attempted: set[str] = set()
        for request_id in (0, -1):  # at most one version retry, before any list page
            attempted.add(protocol)
            try:
                reply, _, _ = self._post(
                    client, pinned, self._modern_body("server/discover", request_id, protocol),
                    session=None, protocol=protocol, want_id=request_id, deadline=deadline,
                    modern=True, probe=True,
                )
            except _HttpRejection as exc:
                reply = exc.message
                code = _error_code(reply)
                if code not in _MODERN_ERRORS:
                    return None
            code = _error_code(reply)
            if code in _MODERN_ERRORS:
                if not _matching(reply, request_id):
                    raise _Stop("protocol", "modern discovery error did not match our request id; no downgrade")
                if code != -32022:
                    raise _Stop("protocol", f"modern server/discover returned MCP error {code}; no downgrade")
                data = reply["error"].get("data")
                supported = data.get("supported") if isinstance(data, dict) else None
                if not isinstance(supported, list) or len(supported) > 32 or not all(
                    isinstance(v, str) and _PROTOCOL_RE.fullmatch(v) for v in supported
                ):
                    raise _Stop("protocol", "modern discovery returned invalid supported versions; no downgrade")
                choice = next((v for v in MODERN_PROTOCOL_VERSIONS if v in supported and v not in attempted), None)
                if choice is None:
                    if _offers_legacy(supported):
                        return None  # a dual-era server whose mutual version with us is a legacy one
                    raise _Stop("protocol", "no mutually supported modern protocol version; no downgrade")
                protocol = choice
                continue
            if code in _LEGACY_PROBE_ERRORS:
                return None
            result = _complete(reply, "server/discover")
            if "supportedVersions" not in result:
                # Not a DiscoverResult: a legacy server answering every method alike (crypto.api.trendsapi.ai
                # returns a tool error to server/discover and serves tools/list after initialize).
                return None
            supported = result.get("supportedVersions")
            if not isinstance(supported, list) or len(supported) > 32 or not all(
                isinstance(v, str) and _PROTOCOL_RE.fullmatch(v) for v in supported
            ):
                raise _Stop("protocol", "modern discovery did not advertise the requested version")
            if protocol not in supported:
                if _offers_legacy(supported) and not any(v in supported for v in MODERN_PROTOCOL_VERSIONS):
                    return None
                raise _Stop("protocol", "modern discovery did not advertise the requested version")
            if not isinstance(result.get("capabilities"), dict):
                raise _Stop("protocol", "modern discovery has no capabilities object")
            self._modern_server_info(result, obs)
            obs.instructions, obs.instructions_read = result.get("instructions"), True
            obs.protocol_version = protocol
            return protocol
        raise _Stop("protocol", "modern version negotiation retry limit; no downgrade")

    @staticmethod
    def _modern_server_info(result: dict[str, Any], obs: Observation) -> None:
        meta = result.get("_meta", {})
        if not isinstance(meta, dict):
            raise _Stop("protocol", "modern response metadata is not an object")
        info = meta.get("io.modelcontextprotocol/serverInfo")
        if info is not None:
            if not isinstance(info, dict):
                raise _Stop("protocol", "modern serverInfo is not an object")
            obs.server_info = info

    @staticmethod
    def _decoded(response: httpx.Response, decoder: _Decoder, deadline: _Deadline, budget: int, what: str):
        """Decoded body chunks, never more than *budget* bytes in total, never past the deadline."""
        total = 0
        if hasattr(response, "_content"):
            # Built in memory (the test transports): httpx has already decoded it.
            source, decode = iter([response.content]), False
        else:
            source, decode = response.iter_raw(), True
        for raw in source:
            deadline.check()
            chunk = decoder.feed(raw, budget - total) if decode else raw[: budget - total + 1]
            total += len(chunk)
            if total > budget:
                raise _Stop("too-large", f"{what} exceeded {budget} bytes")
            yield chunk

    @classmethod
    def _read_json(cls, response: httpx.Response, want_id: int, decoder: _Decoder, deadline: _Deadline,
                   budget: int, *, allow_batch: bool = True) -> tuple[Any, int]:
        chunks: list[bytes] = []
        total = 0
        for chunk in cls._decoded(response, decoder, deadline, budget, "response"):
            total += len(chunk)
            chunks.append(chunk)
        body = b"".join(chunks).strip()
        if not body:
            raise _Stop("protocol", "empty response body")
        message = cls._parse(body, "response")
        if isinstance(message, list):  # a JSON-RPC batch reply
            if not allow_batch:
                raise _Stop("protocol", "modern JSON-RPC batch responses are not accepted")
            message = next((m for m in message if _matching(m, want_id)), None)
        if not _matching(message, want_id):
            raise _Stop("protocol", "no JSON-RPC response for our request id")
        return message, total

    @staticmethod
    def _parse(payload: bytes, what: str) -> Any:
        try:
            return parse_json(payload.decode("utf-8", "replace"))
        except _DuplicateKey as exc:
            raise _Stop("protocol", f"duplicate JSON member {str(exc)!r} in {what}") from exc
        except TooDeep as exc:
            raise _Stop("protocol", str(exc)) from exc
        except ValueError as exc:
            raise _Stop("protocol", f"{what} is not JSON") from exc

    @classmethod
    def _read_sse(cls, response: httpx.Response, want_id: int, decoder: _Decoder, deadline: _Deadline,
                  budget: int) -> tuple[Any, int]:
        total = 0
        buffer = b""
        data: list[bytes] = []

        def lines(final: bool):
            nonlocal buffer
            while True:
                cut = -1
                for i, byte in enumerate(buffer):
                    if byte in (10, 13):
                        cut = i
                        break
                if cut < 0:
                    if len(buffer) > MAX_SSE_LINE:
                        raise _Stop("too-large", f"an event-stream line exceeded {MAX_SSE_LINE} bytes")
                    if final and buffer:
                        line, buffer = buffer, b""
                        yield line
                    return
                if buffer[cut] == 13 and cut == len(buffer) - 1 and not final:
                    return  # a CR at the edge of a chunk may be the first half of CRLF
                line = buffer[:cut]
                step = 2 if buffer[cut] == 13 and buffer[cut + 1 : cut + 2] == b"\n" else 1
                buffer = buffer[cut + step :]
                yield line

        def event(line: bytes) -> Any:
            nonlocal data
            if line.startswith(b"data:"):
                data.append(line[5:].lstrip(b" "))
                return None
            if line == b"" and data:
                payload, data = b"\n".join(data), []
                try:
                    message = cls._parse(payload, "event")
                except _Stop as exc:
                    if exc.detail.startswith("duplicate") or "nests deeper" in exc.detail:
                        raise
                    return None  # a non-JSON event is someone else's; keep reading
                return message if _matching(message, want_id) else None
            return None

        for chunk in cls._decoded(response, decoder, deadline, budget, "event stream"):
            total += len(chunk)
            buffer += chunk
            for line in lines(final=False):
                found = event(line)
                if found is not None:
                    return found, total
        for line in [*lines(final=True), b""]:
            found = event(line)
            if found is not None:
                return found, total
        raise _Stop("protocol", "event stream ended without our response")

    def _initialize(self, client: httpx.Client, pinned: PinnedTarget, deadline: _Deadline,
                    obs: Observation) -> tuple[str | None, str]:
        """The legacy handshake: initialize and the initialized notification. Returns (session, protocol)."""
        init, headers, _ = self._post(
            client, pinned,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "histor", "version": __version__},
            }},
            session=None, protocol=None, want_id=1, deadline=deadline,
        )
        result = _complete(init, "initialize")
        info = result.get("serverInfo")
        obs.server_info = info if isinstance(info, dict) else {}
        obs.instructions, obs.instructions_read = result.get("instructions"), True
        negotiated = result.get("protocolVersion")
        obs.protocol_version = negotiated[:40] if isinstance(negotiated, str) else ""
        session = headers.get("mcp-session-id")
        if session is not None and not _SESSION_RE.fullmatch(session):
            raise _Stop("protocol", "Mcp-Session-Id is not visible ASCII")
        # Only validated date text is ever echoed back in a header.
        protocol = obs.protocol_version if _PROTOCOL_RE.fullmatch(obs.protocol_version) else PROTOCOL_VERSION
        try:
            self._post(client, pinned, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                       session=session, protocol=protocol, want_id=None, deadline=deadline)
        except (_Stop, httpx.HTTPError) as exc:
            if isinstance(exc, _Stop) and exc.status == "timeout":
                raise
            # A notification needs no answer; some legacy servers reject it.
        return session, protocol

    def _drain(self, client: httpx.Client, pinned: PinnedTarget, deadline: _Deadline, obs: Observation,
               protocol: str, session: str | None, *, modern: bool) -> list[Any]:
        """Every tools/list page. Only the first modern page may be refused as a legacy server (_HttpRejection)."""
        tools: list[Any] = []
        spent = 0
        cursor: str | None = None
        request_id = 2
        cursors: set[str] = set()
        cache_scope: str | None = None
        while True:
            params: dict[str, Any] = {"cursor": cursor} if cursor else {}
            body = (self._modern_body("tools/list", request_id, protocol, cursor=cursor) if modern else
                    {"jsonrpc": "2.0", "id": request_id, "method": "tools/list", "params": params})
            reply, _, size = self._post(
                client, pinned, body,
                session=session, protocol=protocol, want_id=request_id, deadline=deadline,
                budget=MAX_SET_BYTES - spent, modern=modern, probe=modern and obs.pages == 0,
            )
            spent += size
            obs.pages += 1
            result = _complete(reply, "tools/list")
            if modern:
                self._modern_server_info(result, obs)
                # No cache is used: TTL never changes the observation time, polling
                # schedule, or guarantees consistency of the pages fetched here.
                scope = result.get("cacheScope")
                if scope is not None:
                    if scope not in ("public", "private") or (cache_scope is not None and scope != cache_scope):
                        raise _Stop("partial", "tools/list cache scope is invalid or changed across pages")
                    cache_scope = scope
            page = result.get("tools")
            if not isinstance(page, list):
                raise _Stop("protocol", "tools/list result has no tools array")
            tools.extend(page)
            if len(tools) > MAX_TOOLS:
                raise _Stop("too-large", f"more than {MAX_TOOLS} tools")
            nxt = result.get("nextCursor")
            if nxt is None:
                return tools
            if not isinstance(nxt, str) or not nxt or nxt in cursors:
                raise _Stop("partial", "pagination cursor did not advance")
            if obs.pages >= MAX_PAGES:
                raise _Stop("partial", f"more than {MAX_PAGES} pages; not drained")
            cursor = nxt
            cursors.add(nxt)
            request_id += 1

    def list_tools(self, url: str, *, handshake_only: bool = False) -> Observation:
        """Observe *url*. Never raises for a server's behaviour; the status says what happened.

        *handshake_only* skips ``server/discover`` and opens with ``initialize``, the way a client of
        the earlier revisions reads: a server that answers both ways may list other definitions there
        (histor.crawler, the other-revision reading)."""
        obs = Observation(status="error")
        deadline = _Deadline(self.deadline)
        try:
            # Resolved once: every request of the session goes to the same checked address, so
            # a round-robin name cannot split one observation across two machines.
            pinned = resolve_public(url, allow_private=self.allow_private)
            obs.address = pinned.address
            if self.robots is not None:
                decision = self.robots.decide(url)
                if not decision.allowed:
                    raise _Stop(decision.status, decision.detail)
            with self._client() as client:
                protocol = None if handshake_only else self._discover(client, pinned, deadline, obs)
                tools: list[Any] | None = None
                if protocol is not None:
                    try:
                        tools = self._drain(client, pinned, deadline, obs, protocol, None, modern=True)
                    except _HttpRejection as exc:
                        # Discovery claimed the modern era, but the first tools/list was refused the way a
                        # legacy server refuses (marx.finance: "Unsupported protocol version: 2026-07-28",
                        # id null). Nothing has been read yet, so the legacy path is still a clean start.
                        code = _error_code(exc.message)
                        if code in _MODERN_ERRORS:
                            raise _Stop("protocol", f"modern tools/list returned MCP error {code}; no downgrade") from None
                        protocol = None
                        obs.server_info, obs.protocol_version, obs.pages = {}, "", 0
                        obs.instructions, obs.instructions_read = None, False
                if protocol is None:
                    session, protocol = self._initialize(client, pinned, deadline, obs)
                    tools = self._drain(client, pinned, deadline, obs, protocol, session, modern=False)
                obs.tools = tools
                obs.status = "ok"
        except BlockedAddress as exc:
            obs.status, obs.detail = "blocked-address", str(exc)
        except _Stop as exc:
            obs.status, obs.detail = exc.status, exc.detail
            if exc.status == "too-large" and exc.detail.startswith("response exceeded"):
                obs.detail = f"tool set exceeded {MAX_SET_BYTES} bytes" if obs.pages else exc.detail
        except httpx.TimeoutException:
            obs.status, obs.detail = "timeout", ""
        except httpx.ConnectError as exc:
            obs.status, obs.detail = "connect", type(exc).__name__
        except httpx.HTTPError as exc:
            obs.status, obs.detail = "network", type(exc).__name__
        except Exception as exc:  # noqa: BLE001 - "never raises for a server's behaviour" is the contract
            obs.status, obs.detail = "client-error", type(exc).__name__
        if obs.status != "ok":
            obs.tools = None
        return obs
