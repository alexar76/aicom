#!/usr/bin/env python3
"""MTL/1 subject construction — the normative digest computation of PROFILE.md sections 4-5.

DRAFT ON DISK.  Nothing in this directory is sent, published, submitted or posted
anywhere; the user reviews and distributes it themselves.

This module builds the two digests an MCP Trust Label commits to:

  * the **tool-set digest** -- SHA-256 over the RFC 8785 canonical form of the
    normalised tool-definition array (PROFILE.md section 5);
  * the **subject digest** -- SHA-256 over the RFC 8785 canonical form of the
    MCP Server Descriptor (PROFILE.md section 4).

Both use ``awr.canonicalize`` from the AWR/2 reference implementation, unchanged.  That
canonicalizer refuses non-integer JSON numbers (``AWR-CANON-001``, SPEC section 4.3), which
is exactly the behaviour MTL/1 wants: a tool schema carrying a non-integer number is not
digestible under MTL/1 and the label degrades to ``inconclusive`` with ``MTL-NUM-001``
rather than committing to bytes two implementations might disagree about.

Run ``python mtl_subject.py --help`` for the CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

from awr import AwrError, canonical_sri, canonicalize

# ---------------------------------------------------------------------------
# Reason codes local to this profile.  PROFILE.md section 11.
# ---------------------------------------------------------------------------

MTL_SUBJ_001 = "MTL-SUBJ-001"  # tool entry is not an object, or name missing/empty
MTL_SUBJ_002 = "MTL-SUBJ-002"  # tool set is empty
MTL_SUBJ_003 = "MTL-SUBJ-003"  # duplicate tool name
MTL_NUM_001 = "MTL-NUM-001"    # non-integer JSON number in a tool schema: not digestible

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


def canonical_tool_set(tools: Sequence[Any]) -> List[Dict[str, Any]]:
    """The normalised, sorted tool array MTL/1 digests."""
    if not tools:
        raise MtlError(MTL_SUBJ_002, "the tool set is empty; there is nothing to pin")
    entries = [normalise_tool(tool) for tool in tools]

    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        if entry["name"] in seen:
            raise MtlError(
                MTL_SUBJ_003,
                "duplicate tool name %r at positions %d and %d; the digest would be "
                "ambiguous" % (entry["name"], seen[entry["name"]], index),
            )
        seen[entry["name"]] = index

    entries.sort(key=lambda entry: utf16_sort_key(entry["name"]))
    return entries


def tool_set_digest(tools: Sequence[Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """``(sri, canonical_entries)`` for *tools*.

    Raises :class:`MtlError` with ``MTL-NUM-001`` when a schema carries a non-integer JSON
    number, because ``awr.canonicalize`` refuses one (SPEC section 4.3) and MTL/1 does not
    invent a resolution.
    """
    entries = canonical_tool_set(tools)
    try:
        sri = canonical_sri(entries)
    except AwrError as exc:
        if exc.code == "AWR-CANON-001":
            raise MtlError(
                MTL_NUM_001,
                "a tool schema contains a non-integer JSON number, which MTL/1 cannot "
                "digest reproducibly (%s)" % (exc,),
            ) from exc
        raise
    return sri, entries


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
