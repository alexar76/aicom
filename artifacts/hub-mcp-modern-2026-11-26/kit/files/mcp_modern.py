"""The per-request envelope of MCP 2026-07-28 over Streamable HTTP, for a server that also keeps
the handshake revisions.

Since 2026-07-28 MCP has no ``initialize``: every request states its protocol version and the
client's capabilities in ``params._meta``, mirrors the version, the method and (for a call) the
name into HTTP headers, and the server answers each request on its own. A server that still wants
its 2024-2025 clients keeps the handshake beside it ("dual-era" in the specification's words).

This module is the part of that which does not depend on what the server offers:

* :func:`is_modern` — which of the two eras one request belongs to;
* :func:`check` — the validation the specification asks of a server before it acts, raising
  :class:`Refusal` with the HTTP status and JSON-RPC error to send;
* :func:`finish` — the fields every modern result carries.

References (revision 2026-07-28): Versioning and Compatibility; Streamable HTTP, "Request
Metadata" and "Server Validation"; Overview, "Error Codes" and "_meta"; Discovery; Caching.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, Mapping

#: Revisions this module implements, newest first.
MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)
#: Every revision from this date on carries its version per request; earlier ones open with initialize.
FIRST_MODERN_VERSION = "2026-07-28"

META_PROTOCOL = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

HEADER_MISMATCH = -32020
MISSING_REQUIRED_CLIENT_CAPABILITY = -32021
UNSUPPORTED_PROTOCOL_VERSION = -32022

#: Results that carry ``ttlMs`` and ``cacheScope`` (the CacheableResult of the schema).
CACHEABLE_METHODS = frozenset({
    "server/discover", "tools/list", "prompts/list", "resources/list", "resources/templates/list",
    "resources/read",
})
#: Requests whose ``Mcp-Name`` header mirrors a body field, and which field.
NAMED_METHODS = {"tools/call": "name", "prompts/get": "name", "resources/read": "uri"}

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SENTINEL = re.compile(r"=\?base64\?(.*)\?=", re.DOTALL)


class Refusal(Exception):
    """A request the envelope rules reject before the server does anything with it."""

    def __init__(self, status: int, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.data = status, code, message, data

    def body(self, req_id: Any) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return {"jsonrpc": "2.0", "id": req_id, "error": error}


def _shown(value: Any, limit: int = 60) -> str:
    """A caller-supplied value as it may appear in an error message: short and printable."""
    text = value if isinstance(value, str) else repr(value)
    return "".join(ch if " " <= ch <= "~" else "?" for ch in text[:limit])


def is_modern(message: Any, headers: Mapping[str, str]) -> bool:
    """Whether one JSON-RPC message is written for a per-request-metadata revision.

    The body decides: a modern request names its version or capabilities in ``_meta``, and
    ``server/discover`` exists only there. The header alone decides only when it names a
    revision of the modern era, so a handshake client that sends ``MCP-Protocol-Version:
    2025-06-18`` after ``initialize`` stays on the handshake path.
    """
    if not isinstance(message, dict):
        return False
    params = message.get("params")
    meta = params.get("_meta") if isinstance(params, dict) else None
    if isinstance(meta, dict) and (META_PROTOCOL in meta or META_CAPABILITIES in meta):
        return True
    if message.get("method") == "server/discover":
        return True
    version = (headers.get("mcp-protocol-version") or "").strip()
    return bool(_DATE.fullmatch(version)) and version >= FIRST_MODERN_VERSION


def decode_header_value(raw: str) -> str:
    """A ``Mcp-Name`` or ``Mcp-Param-*`` header value as the body would spell it.

    Plain ASCII is the value itself. ``=?base64?…?=`` is the UTF-8 text inside (Streamable
    HTTP, "Value Encoding"); the markers are case-sensitive. An undecodable payload raises
    ``ValueError``.
    """
    match = _SENTINEL.fullmatch(raw)
    if match is None:
        return raw
    try:
        return base64.b64decode(match.group(1), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("not Base64 of UTF-8 text") from exc


def _mismatch(message: str) -> Refusal:
    return Refusal(400, HEADER_MISMATCH, f"Header mismatch: {message}")


def check(message: dict[str, Any], headers: Mapping[str, str], *,
          supported: tuple[str, ...]) -> dict[str, Any]:
    """Validate one modern request; return its ``_meta``.

    Order: the version header and its body twin, then whether this server speaks that version,
    then the method and name headers, then the capabilities object. ``supported`` is every
    revision the server speaks in either era, for the UnsupportedProtocolVersion answer.
    """
    method = message.get("method")
    if not isinstance(method, str):
        raise Refusal(400, -32600, "Invalid request: method must be a string")
    params = message.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise Refusal(400, -32602, "Invalid params: params must be an object")
    meta = params.get("_meta")
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise Refusal(400, -32602, "Invalid params: _meta must be an object")

    header = (headers.get("mcp-protocol-version") or "").strip()
    body = meta.get(META_PROTOCOL)
    if not header:
        raise _mismatch("required header MCP-Protocol-Version is missing")
    if not isinstance(body, str):
        raise _mismatch(f"MCP-Protocol-Version header value '{_shown(header)}' has no matching "
                        f"{META_PROTOCOL} in the request body")
    if header != body:
        raise _mismatch(f"MCP-Protocol-Version header value '{_shown(header)}' does not match "
                        f"body value '{_shown(body)}'")
    if body not in MODERN_PROTOCOL_VERSIONS:
        raise Refusal(400, UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
                      {"supported": list(supported), "requested": _shown(body, 40)})

    sent_method = headers.get("mcp-method")
    if sent_method is None:
        raise _mismatch("required header Mcp-Method is missing")
    if sent_method.strip() != method:
        raise _mismatch(f"Mcp-Method header value '{_shown(sent_method)}' does not match "
                        f"body value '{_shown(method)}'")

    field = NAMED_METHODS.get(method)
    if field is not None:
        named = params.get(field)
        sent_name = headers.get("mcp-name")
        if sent_name is None:
            raise _mismatch("required header Mcp-Name is missing")
        try:
            decoded = decode_header_value(sent_name.strip())
        except ValueError:
            raise _mismatch("Mcp-Name header value is not valid Base64 of UTF-8 text") from None
        if not isinstance(named, str) or decoded != named:
            raise _mismatch(f"Mcp-Name header value '{_shown(decoded)}' does not match "
                            f"body value '{_shown(named)}'")

    if not isinstance(meta.get(META_CAPABILITIES), dict):
        raise Refusal(400, -32602, f"Invalid params: {META_CAPABILITIES} is required and must be an object")
    return meta


def finish(result: dict[str, Any], method: str, *, server_name: str, server_version: str,
           ttl_ms: int = 0, cache_scope: str = "private") -> dict[str, Any]:
    """Add what every modern result carries: the result type, who answered, and, for the
    cacheable methods, how long the answer may be kept and by whom."""
    result["resultType"] = "complete"
    meta = result.get("_meta")
    if not isinstance(meta, dict):
        meta = {}
        result["_meta"] = meta
    meta[META_SERVER_INFO] = {"name": server_name, "version": server_version}
    if method in CACHEABLE_METHODS:
        result["ttlMs"] = max(0, int(ttl_ms))
        result["cacheScope"] = cache_scope if cache_scope in ("public", "private") else "private"
    return result
