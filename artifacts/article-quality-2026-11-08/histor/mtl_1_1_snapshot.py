#!/usr/bin/env python3
"""MTL/1 subject construction — the normative digest computation of PROFILE.md sections 4-5.

DRAFT ON DISK.  Nothing in this directory is sent, published, submitted or posted
anywhere; the user reviews and distributes it themselves.

This module builds the two digests an MCP Trust Label commits to:

  * the **tool-set digest** -- SHA-256 over the RFC 8785 canonical form of the
    normalised tool-definition array (PROFILE.md section 5);
  * the **subject digest** -- SHA-256 over the RFC 8785 canonical form of the
    MCP Server Descriptor (PROFILE.md section 4).

The subject digest uses ``awr.canonicalize`` from the AWR/2 reference implementation,
unchanged.  The tool-set digest is RFC 8785 with every JSON number read as an IEEE 754 double
(PROFILE.md section 5.4, MTL/1.1): a value whose integers all lie inside +/-(2^53-1) gets
AWR/2's own bytes, so no digest issued under MTL/1.0 moves; fractions, exponents and larger
integers, which 1.0 refused with ``MTL-NUM-001``, are written in the ECMAScript form RFC 8785
section 3.2.2.3 names.  ``MTL-NUM-001`` remains only for a number with no double (``1e400``).

Run ``python mtl_subject.py --help`` for the CLI.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from base64 import b64encode
from hashlib import sha256
from typing import Any, Dict, List, Optional, Sequence, Tuple

from awr import AwrError, canonical_sri, canonicalize

# ---------------------------------------------------------------------------
# Reason codes local to this profile.  PROFILE.md section 11.
# ---------------------------------------------------------------------------

MTL_SUBJ_001 = "MTL-SUBJ-001"  # tool entry is not an object, or name missing/empty
# MTL/1.0 refused an empty set (SUBJ-002) and duplicate names (SUBJ-003); MTL/1.1 digests
# both.  The codes stay so that labels issued under 1.0 still read.
MTL_SUBJ_002 = "MTL-SUBJ-002"
MTL_SUBJ_003 = "MTL-SUBJ-003"
MTL_NUM_001 = "MTL-NUM-001"    # a number with no IEEE 754 double (1e400): not digestible

MAX_SAFE_INTEGER = 2 ** 53 - 1

#: Fields of an MCP tool definition that MTL/1 digests.  ``name``, ``description`` and
#: ``inputSchema`` are always present in the normalised entry; ``outputSchema`` appears iff
#: the observed tool object carried it.  Everything else the server sends is dropped.
DIGESTED_FIELDS = ("name", "description", "inputSchema", "outputSchema")


class MtlError(Exception):
    """A tool set or descriptor that MTL/1 cannot digest."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail


def utf16_sort_key(text: str) -> bytes:
    """Sort key giving RFC 8785 section 3.2.3 order: UTF-16 code units as unsigned ints.

    Comparing UTF-16 **big-endian** byte sequences lexicographically is equivalent to
    comparing the code-unit sequences as unsigned 16-bit integers, because the high byte
    is compared first.  This is deliberately *not* ``str.__lt__`` (code points) and not a
    locale collation: ``"Z_tool".localeCompare("a_tool")`` is ``1`` in JavaScript while
    code-unit order gives ``-1``, and the two disagree on any set containing both cases.
    """
    return text.encode("utf-16-be")


def normalise_tool(tool: Any) -> Dict[str, Any]:
    """One tool object reduced to the fields MTL/1 digests (PROFILE.md section 5.2)."""
    if not isinstance(tool, dict):
        raise MtlError(MTL_SUBJ_001, "tool entry is not a JSON object: %r" % (tool,))
    name = tool.get("name")
    if not isinstance(name, str) or not name:
        raise MtlError(MTL_SUBJ_001, "tool entry has no non-empty string name: %r" % (tool,))

    entry: Dict[str, Any] = {
        "name": name,
        "description": tool.get("description") if isinstance(tool.get("description"), str) else "",
        "inputSchema": tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {},
    }
    # Present iff the observed object carried it: absence and {} are different tool sets.
    if isinstance(tool.get("outputSchema"), dict):
        entry["outputSchema"] = tool["outputSchema"]
    return entry


def es_number(value: float) -> str:
    """RFC 8785 section 3.2.2.3: a double in ECMAScript ``Number.prototype.toString`` form.

    ``repr`` yields the shortest round-tripping digits, the same digits ECMAScript chooses;
    only the placement of the point and of the exponent is ECMAScript's own.
    """
    if not math.isfinite(value):
        raise ValueError("%r has no JSON form" % (value,))
    if value == 0:
        return "0"  # -0 included
    sign = "-" if value < 0 else ""
    mantissa, _, exp = repr(abs(value)).partition("e")
    whole, _, frac = mantissa.partition(".")
    digits = whole + frac
    lead = len(digits) - len(digits.lstrip("0"))
    s = digits.strip("0")
    k = len(s)
    n = len(whole) + (int(exp) if exp else 0) - lead  # value = 0.s x 10^n
    if k <= n <= 21:
        return sign + s + "0" * (n - k)
    if 0 < n <= 21:
        return sign + s[:n] + "." + s[n:]
    if -6 < n <= 0:
        return sign + "0." + "0" * -n + s
    e = n - 1
    return sign + (s if k == 1 else s[0] + "." + s[1:]) + "e" + ("+" if e >= 0 else "-") + str(abs(e))


def _serialize(value: Any, out: List[str]) -> None:
    # Strings and member names go through awr.canonicalize, so escaping and the lone-surrogate
    # refusal are the AWR/2 canonicalizer's own.
    if value is None or isinstance(value, bool):
        out.append("null" if value is None else ("true" if value else "false"))
    elif isinstance(value, int):
        # Beyond 2^53-1 JSON.parse already holds the nearest double; float() rounds the same way.
        out.append(str(value) if -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER else es_number(float(value)))
    elif isinstance(value, float):
        out.append(es_number(value))
    elif isinstance(value, str):
        out.append(canonicalize(value).decode("utf-8"))
    elif isinstance(value, list):
        out.append("[")
        for index, item in enumerate(value):
            if index:
                out.append(",")
            _serialize(item, out)
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        for index, key in enumerate(sorted(value, key=utf16_sort_key)):
            if index:
                out.append(",")
            out.append(canonicalize(key).decode("utf-8"))
            out.append(":")
            _serialize(value[key], out)
        out.append("}")
    else:
        raise TypeError("%s is not a JSON value" % type(value).__name__)


def canonical_tool_bytes(value: Any) -> bytes:
    """RFC 8785 bytes of a tool set or entry, every JSON number read as an IEEE 754 double."""
    try:
        return canonicalize(value)
    except AwrError as exc:
        if exc.code not in ("AWR-CANON-001", "AWR-CANON-002"):
            raise
    out: List[str] = []
    _serialize(value, out)
    return "".join(out).encode("utf-8")


def canonical_tool_set(tools: Sequence[Any]) -> List[Dict[str, Any]]:
    """The normalised, sorted tool array MTL/1 digests.  May be empty; may repeat a name.

    Entries sort by ``name`` (UTF-16 code units).  Entries that share a name sort by their
    canonical bytes, so the digest never depends on the order the server listed them in.
    """
    entries = [normalise_tool(tool) for tool in tools]
    if len({entry["name"] for entry in entries}) == len(entries):
        entries.sort(key=lambda entry: utf16_sort_key(entry["name"]))
    else:
        entries.sort(key=lambda entry: (utf16_sort_key(entry["name"]), canonical_tool_bytes(entry)))
    return entries


def tool_set_digest(tools: Sequence[Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """``(sri, canonical_entries)`` for *tools*.

    Raises :class:`MtlError` with ``MTL-NUM-001`` only for a number that has no IEEE 754
    double (``1e400``), which RFC 8785 cannot write either.
    """
    entries = canonical_tool_set(tools)
    try:
        canonical = canonical_tool_bytes(entries)
    except (ValueError, OverflowError) as exc:
        raise MtlError(MTL_NUM_001, "a tool schema contains a number with no IEEE 754 double") from exc
    return "sha256-" + b64encode(sha256(canonical).digest()).decode("ascii"), entries


def build_descriptor(
    *,
    server_name: str,
    registry: str,
    tools: Sequence[Any],
    server_version: Optional[str] = None,
    transport: Optional[str] = None,
    package: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> Tuple[Dict[str, Any], Optional[str], Optional[MtlError]]:
    """``(descriptor, tool_set_sri, hazard)`` per PROFILE.md section 4.

    *hazard* is ``None`` on the digestible path.  When it is an :class:`MtlError` the
    descriptor still identifies the server and its tool **names**, carries no
    ``toolSet.digestSRI``, and the label built over it MUST be ``inconclusive``.

    Optional members are **omitted**, never ``null``: presence changes the canonical bytes.
    """
    if not isinstance(server_name, str) or not server_name:
        raise MtlError(MTL_SUBJ_001, "server.name must be a non-empty string")
    if not isinstance(registry, str) or not registry:
        raise MtlError(MTL_SUBJ_001, "server.registry must be a non-empty string")

    names = sorted((normalise_tool(t)["name"] for t in tools), key=utf16_sort_key)

    hazard: Optional[MtlError] = None
    sri: Optional[str] = None
    try:
        sri, _ = tool_set_digest(tools)
    except MtlError as exc:
        if exc.code != MTL_NUM_001:
            raise
        hazard = exc

    server: Dict[str, Any] = {"name": server_name, "registry": registry}
    if server_version:
        server["version"] = server_version

    tool_set: Dict[str, Any] = {"count": len(names), "names": names}
    if sri is not None:
        tool_set["digestSRI"] = sri

    descriptor: Dict[str, Any] = {"mtl": "1", "server": server, "toolSet": tool_set}

    artifact: Dict[str, Any] = {}
    if transport:
        artifact["transport"] = transport
    if package:
        artifact["package"] = package
    if endpoint:
        artifact["endpoint"] = endpoint
    if artifact:
        descriptor["artifact"] = artifact

    return descriptor, sri, hazard


def descriptor_digest(descriptor: Dict[str, Any]) -> str:
    """The subject digest: SRI over the RFC 8785 canonical form of the descriptor."""
    return canonical_sri(descriptor)


def subject_urn(descriptor: Dict[str, Any]) -> str:
    """``urn:awr:mtl:1:subject:sha256:<lowercase hex>`` -- PROFILE.md section 4.4."""
    from hashlib import sha256

    return "urn:awr:mtl:1:subject:sha256:" + sha256(canonicalize(descriptor)).hexdigest()


def subject_reference(descriptor: Dict[str, Any]) -> Dict[str, str]:
    """The ``verifiedWork`` digest reference an MTL label carries (PROFILE.md section 6.1)."""
    return {"id": subject_urn(descriptor), "digestSRI": descriptor_digest(descriptor)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute the MTL/1 subject descriptor and its digests from an MCP "
        "tools/list response.",
    )
    parser.add_argument(
        "tools_file",
        help='JSON file: either a tools/list result ({"tools":[...]}) or a bare array',
    )
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--server-version")
    parser.add_argument("--transport", choices=("stdio", "streamable-http", "sse"))
    parser.add_argument("--package")
    parser.add_argument("--endpoint")
    args = parser.parse_args(argv)

    with open(args.tools_file, "rb") as handle:
        raw = json.loads(handle.read().decode("utf-8"))
    tools = raw.get("tools") if isinstance(raw, dict) else raw
    if not isinstance(tools, list):
        print("error: expected a tools array or an object with a 'tools' array", file=sys.stderr)
        return 2

    try:
        descriptor, sri, hazard = build_descriptor(
            server_name=args.server_name,
            registry=args.registry,
            tools=tools,
            server_version=args.server_version,
            transport=args.transport,
            package=args.package,
            endpoint=args.endpoint,
        )
    except MtlError as exc:
        print("error: %s" % (exc,), file=sys.stderr)
        return 1

    out = {
        "descriptor": descriptor,
        "toolSetDigestSRI": sri,
        "subject": subject_reference(descriptor),
    }
    if hazard is not None:
        out["hazard"] = {"code": hazard.code, "detail": hazard.detail}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
