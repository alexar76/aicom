"""Per-tool fingerprints in other projects' formats, computed from what HISTOR stored.

HISTOR's own digest is the MTL/1 tool-set digest (histor.subject). Clients and other records pin
tools their own way, and a lookup is only useful in the format the caller already has:

* ``vercel-ai`` — ``fingerprintTools`` of the Vercel AI SDK (``ai`` 7, ``src/generate-text/
  tool-fingerprint.ts``) for a tool built by ``@ai-sdk/mcp`` ``tools()``: description (tagged),
  the input schema with ``properties`` defaulted and ``additionalProperties: false`` forced (the MCP
  client does that before the SDK sees it), and ``title ?? annotations.title``. SHA-256, base64url.
* ``heldfast`` — the tool digest of heldfast's lockfile (docs/LOCK.md): name, title, description,
  input_schema, annotations, output_schema (omitted when ``{}``), icons (omitted when empty).
  SHA-256 of RFC 8785, lowercase hex.
* ``agentavow-v1`` — ``agentavow.mcp-tool-definition.v1``: name, title, description, inputSchema,
  outputSchema and annotations, missing or null members omitted, under ``{profile, tool}``.
  ``sha256:`` + hex. Keys of the map are AgentAvow's ``tool:<name>`` encoding.

Each was checked against the project's own material (research-data/interop-digests-2026-10-31):
heldfast's golden tools, AgentAvow's signed DeepWiki digests and key vectors, and ``fingerprintTools``
itself on 6,882 stored tools. ``tests/test_fingerprints.py`` pins vectors produced by those runs.

The AWR canonicalizer refuses fractions (MTL/1 withholds a digest it cannot reproduce); these
formats do not, so this module carries its own RFC 8785 / ECMAScript serialization.
"""

from __future__ import annotations

import base64
import hashlib
from decimal import Decimal
from typing import Any

FORMATS = ("vercel-ai", "heldfast", "agentavow-v1")
AVOW_PROFILE = "agentavow.mcp-tool-definition.v1"
AVOW_FIELDS = ("name", "title", "description", "inputSchema", "outputSchema", "annotations")
MAX_SAFE_INTEGER = 2**53 - 1


class _Undefined:
    """JavaScript ``undefined`` as a value: the Vercel serializer writes it as the bare word."""


UNDEFINED = _Undefined()


def _number(value: int | float) -> str:
    """ECMAScript Number::toString, which is what RFC 8785 section 3.2.2.3 prescribes."""
    if isinstance(value, int):
        if abs(value) <= MAX_SAFE_INTEGER:
            return str(value)
        value = float(value)  # what JSON.parse makes of it
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError("NaN and Infinity are not JSON")
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    digits_tuple = Decimal(repr(abs(value))).normalize().as_tuple()
    digits = "".join(map(str, digits_tuple.digits))
    k = len(digits)
    n = digits_tuple.exponent + k  # value = 0.digits × 10^n
    if k <= n <= 21:
        return sign + digits + "0" * (n - k)
    if 0 < n <= 21:
        return sign + digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * (-n) + digits
    e = n - 1
    mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
    return f"{sign}{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"


_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _string(value: str) -> str:
    """JSON.stringify of a string (well-formed: a lone surrogate is escaped, not refused)."""
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif code < 0x20 or 0xD800 <= code <= 0xDFFF:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16(key: str) -> bytes:
    return key.encode("utf-16-be", "surrogatepass")


def canonical(value: Any) -> str:
    """RFC 8785 text of ``value``; ``UNDEFINED`` (not JSON) is written as ``undefined``."""
    if value is UNDEFINED:
        return "undefined"
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return _number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonical(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(_string(k) + ":" + canonical(value[k]) for k in sorted(value, key=_utf16)) + "}"
    raise TypeError(f"not JSON: {type(value).__name__}")


def _sha256(text: str) -> bytes:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).digest()


def vercel_ai(tool: dict[str, Any]) -> str:
    description = tool.get("description")
    tagged = {"type": "string", "value": description} if isinstance(description, str) else {"type": "none"}
    schema = dict(tool["inputSchema"]) if isinstance(tool.get("inputSchema"), dict) else {}
    if schema.get("properties") is None:
        schema["properties"] = {}
    schema["additionalProperties"] = False
    title = tool.get("title")
    if title is None and isinstance(tool.get("annotations"), dict):
        title = tool["annotations"].get("title")
    body = {"description": tagged, "inputSchema": schema, "title": UNDEFINED if title is None else title}
    return base64.urlsafe_b64encode(_sha256(canonical(body))).decode("ascii").rstrip("=")


def heldfast(tool: dict[str, Any]) -> str:
    def text(key: str) -> str:
        return str(tool.get(key) or "")

    schema = tool.get("input_schema")
    if schema is None:
        schema = tool.get("inputSchema")
    body: dict[str, Any] = {
        "name": text("name"), "title": text("title"), "description": text("description"),
        "input_schema": schema if isinstance(schema, dict) else {},
        "annotations": tool["annotations"] if isinstance(tool.get("annotations"), dict) else {},
    }
    output = tool.get("output_schema")
    if output is None:
        output = tool.get("outputSchema")
    if isinstance(output, dict) and output:
        body["output_schema"] = output
    if isinstance(tool.get("icons"), list) and tool["icons"]:
        body["icons"] = tool["icons"]
    return _sha256(canonical(body)).hex()


def agentavow_v1(tool: dict[str, Any]) -> str:
    restricted = {k: tool[k] for k in AVOW_FIELDS if tool.get(k) is not None}
    return "sha256:" + _sha256(canonical({"profile": AVOW_PROFILE, "tool": restricted})).hex()


def agentavow_key(name: str) -> str:
    """``tool:`` + the name with bytes outside 0x21-0x7E, ``%`` and ``=`` percent-encoded; past 128
    characters cut to 96 + ``~`` + 16 hex of SHA-256 over the raw name."""
    out = []
    for ch in name:
        if 0x21 <= ord(ch) <= 0x7E and ch not in "%=":
            out.append(ch)
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8", "surrogatepass"))
    body = "".join(out)
    if len(body) > 128:
        body = body[:96] + "~" + hashlib.sha256(name.encode("utf-8", "surrogatepass")).hexdigest()[:16]
    return "tool:" + body


def merged_tools(tools: list[dict[str, Any]], extras: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[str]]:
    """The stored tool set with each tool's extra members put back, and the names whose extras were
    not stored (over the size caps), whose fingerprints in title/annotation formats would be wrong."""
    per_tool = (extras or {}).get("tools") or {}
    incomplete = sorted(set((extras or {}).get("omitted") or []) | set((extras or {}).get("oversized") or {}))
    return [{**t, **per_tool.get(t.get("name"), {})} for t in tools], incomplete


def fingerprint_map(tools: list[dict[str, Any]], fmt: str) -> dict[str, str]:
    """``{key: fingerprint}`` for a list of full tool definitions, keyed as the format keys them."""
    if fmt == "vercel-ai":
        return {t["name"]: vercel_ai(t) for t in tools}
    if fmt == "heldfast":
        return {t["name"]: heldfast(t) for t in tools}
    if fmt == "agentavow-v1":
        return {agentavow_key(t["name"]): agentavow_v1(t) for t in tools}
    raise ValueError(f"unknown format {fmt!r}; one of {', '.join(FORMATS)}")
