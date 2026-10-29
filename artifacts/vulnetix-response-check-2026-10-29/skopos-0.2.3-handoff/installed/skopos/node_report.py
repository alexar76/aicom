"""The document a monitored host produces, and the rules for believing it.

One shape is carried by all three transports: pushed over HTTPS, printed by
``skopos-node ssh-op`` over a forced command, or (for ``direct-ssh``) assembled
by SKOPOS from raw script output. Validating it in one place means the trust
boundary is one file rather than twenty-five columns.

Two invariants matter more than the rest:

**The document contains no identity.** There is no ``server_name`` field and
adding one is a validation error, not a silently ignored key. Which server a
report belongs to is decided by the credential it arrived under, so a node
cannot write into another host's data even if it lies about everything else.

**The document contains no parsed values.** Only raw log lines. If a node could
supply ``remote_addr`` or ``status`` directly, it could store a harmless-looking
row under the dedup hash of a real attack line, and the real line would then be
dropped as a duplicate forever — durable, invisible log suppression. SKOPOS
re-parses every line itself, exactly as it does for SSH-collected output.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .node_protocol import (
    MAX_LINES_PER_REPORT,
    MAX_PROBE_BYTES,
    MAX_SOURCE_ID_BYTES,
    MAX_SOURCES,
    PROTOCOL_VERSION,
    ProtocolError,
    clean_line,
)

#: Parsers a source may ask for. An unknown value is rejected rather than
#: defaulted, so a typo shows up at once instead of silently changing how a
#: host's traffic is read.
VALID_PARSERS = frozenset({"nginx", "apache", "uvicorn", "auto"})
VALID_KINDS = frozenset({"file", "docker"})

_DOC_KEYS = frozenset(
    {"protocol", "agent_version", "generated_at", "sources", "probe", "knocks", "facts"}
)
_SOURCE_KEYS = frozenset({"id", "kind", "parser", "lines", "truncated"})

#: Facts the agent may report about itself. Everything here is diagnostic and
#: none of it is trusted for a security decision — it exists so the dashboard can
#: say "this host is running an old agent" or "someone put the agent in the
#: docker group", not so SKOPOS can act on the host's own say-so.
_FACT_KEYS = frozenset(
    {
        "hostname",
        "agent_user",
        "groups",
        "probe_age_s",
        "knocks_age_s",
        "privileged",
        "interval_s",
        "python",
        "collect_errors",
    }
)


@dataclass(frozen=True)
class ReportSource:
    id: str
    kind: str
    parser: str
    lines: tuple[str, ...]
    truncated: bool = False


@dataclass(frozen=True)
class NodeReport:
    protocol: int
    agent_version: str
    generated_at: int
    sources: tuple[ReportSource, ...] = ()
    probe: str | None = None
    knocks: str | None = None
    facts: dict = field(default_factory=dict)
    #: Lines dropped during validation. Surfaced so a host quietly emitting
    #: garbage is visible rather than merely quieter than it should be.
    rejected_lines: int = 0

    @property
    def total_lines(self) -> int:
        return sum(len(s.lines) for s in self.sources)


def _require_flat(value, *, label: str, depth: int = 0) -> None:
    """Reject nesting. A flat schema cannot be turned into a parser bomb."""
    if depth > 2:
        raise ProtocolError(f"{label} is nested too deeply")
    if isinstance(value, dict):
        for k, v in value.items():
            if not isinstance(k, str):
                raise ProtocolError(f"{label} has a non-string key")
            _require_flat(v, label=label, depth=depth + 1)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _require_flat(v, label=label, depth=depth + 1)
    elif not isinstance(value, (str, int, float, bool)) and value is not None:
        raise ProtocolError(f"{label} has an unsupported value type")


def _validate_source_id(raw) -> tuple[str, str]:
    """Return (kind, id) for a source, or raise.

    The id ends up in ``collector_status.last_log_paths``, in an index predicate
    and in the LLM's context, so it is validated with the same guards a path
    would get over SSH rather than taken as an opaque label.
    """
    from .shell_safe import validate_docker_name, validate_log_path

    if not isinstance(raw, str) or not raw:
        raise ProtocolError("source id must be a non-empty string")
    try:
        encoded_length = len(raw.encode("utf-8"))
    except UnicodeEncodeError as e:
        # json.loads accepts a lone surrogate escape; encoding it does not.
        raise ProtocolError("source id is not valid text") from e
    if encoded_length > MAX_SOURCE_ID_BYTES:
        raise ProtocolError("source id is too long")
    if raw.startswith("file:"):
        try:
            validate_log_path(raw[len("file:") :])
        except ValueError as e:
            raise ProtocolError(f"invalid file source: {e}") from e
        return "file", raw
    if raw.startswith("docker:"):
        try:
            validate_docker_name(raw[len("docker:") :])
        except ValueError as e:
            raise ProtocolError(f"invalid docker source: {e}") from e
        return "docker", raw
    raise ProtocolError("source id must start with 'file:' or 'docker:'")


def _validate_text(raw, *, label: str, cap: int) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ProtocolError(f"{label} must be a string")
    if "\x00" in raw:
        raise ProtocolError(f"{label} contains a NUL byte")
    encoded = raw.encode("utf-8", errors="ignore")
    if len(encoded) > cap:
        return encoded[:cap].decode("utf-8", errors="ignore")
    return raw


def parse_report(doc) -> NodeReport:
    """Validate an untrusted document into a :class:`NodeReport`, or raise."""
    if not isinstance(doc, dict):
        raise ProtocolError("report must be an object")

    unknown = set(doc) - _DOC_KEYS
    if unknown:
        # Rejecting rather than ignoring is deliberate. "server_name" arriving
        # here means either a version mismatch or an attempt to steer identity,
        # and both deserve a loud failure.
        raise ProtocolError(f"unexpected field(s): {','.join(sorted(unknown))}")

    protocol = doc.get("protocol")
    if protocol != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol version: {protocol!r}")

    generated_at = doc.get("generated_at")
    if not isinstance(generated_at, int) or isinstance(generated_at, bool):
        raise ProtocolError("generated_at must be an integer")

    agent_version = doc.get("agent_version")
    if not isinstance(agent_version, str) or len(agent_version) > 32:
        raise ProtocolError("agent_version must be a short string")

    raw_sources = doc.get("sources") or []
    if not isinstance(raw_sources, list):
        raise ProtocolError("sources must be a list")
    if len(raw_sources) > MAX_SOURCES:
        raise ProtocolError("too many sources")

    sources: list[ReportSource] = []
    seen_ids: set[str] = set()
    total_lines = 0
    rejected = 0

    for item in raw_sources:
        if not isinstance(item, dict):
            raise ProtocolError("each source must be an object")
        extra = set(item) - _SOURCE_KEYS
        if extra:
            raise ProtocolError(f"unexpected source field(s): {','.join(sorted(extra))}")

        kind_from_id, source_id = _validate_source_id(item.get("id"))
        kind = item.get("kind", kind_from_id)
        if kind not in VALID_KINDS or kind != kind_from_id:
            raise ProtocolError("source kind disagrees with its id")
        parser = item.get("parser", "auto")
        if parser not in VALID_PARSERS:
            raise ProtocolError(f"unknown parser: {parser!r}")
        if source_id in seen_ids:
            raise ProtocolError("duplicate source id")
        seen_ids.add(source_id)

        raw_lines = item.get("lines") or []
        if not isinstance(raw_lines, list):
            raise ProtocolError("source lines must be a list")

        lines: list[str] = []
        for ln in raw_lines:
            if total_lines + len(lines) >= MAX_LINES_PER_REPORT:
                raise ProtocolError("too many lines in report")
            cleaned = clean_line(ln)
            if cleaned is None:
                rejected += 1
                continue
            lines.append(cleaned)

        total_lines += len(lines)
        sources.append(
            ReportSource(
                id=source_id,
                kind=kind,
                parser=parser,
                lines=tuple(lines),
                truncated=bool(item.get("truncated", False)),
            )
        )

    facts = doc.get("facts") or {}
    if not isinstance(facts, dict):
        raise ProtocolError("facts must be an object")
    unknown_facts = set(facts) - _FACT_KEYS
    if unknown_facts:
        raise ProtocolError(f"unexpected fact(s): {','.join(sorted(unknown_facts))}")
    _require_flat(facts, label="facts")

    return NodeReport(
        protocol=protocol,
        agent_version=agent_version,
        generated_at=generated_at,
        sources=tuple(sources),
        probe=_validate_text(doc.get("probe"), label="probe", cap=MAX_PROBE_BYTES),
        knocks=_validate_text(doc.get("knocks"), label="knocks", cap=MAX_PROBE_BYTES),
        facts=facts,
        rejected_lines=rejected,
    )


def build_document(
    *,
    agent_version: str,
    generated_at: int,
    sources: list[dict],
    probe: str | None = None,
    knocks: str | None = None,
    facts: dict | None = None,
) -> dict:
    """Assemble a document on the agent side. Mirrors :func:`parse_report`."""
    doc: dict = {
        "protocol": PROTOCOL_VERSION,
        "agent_version": agent_version,
        "generated_at": int(generated_at),
        "sources": sources,
    }
    if probe is not None:
        doc["probe"] = probe
    if knocks is not None:
        doc["knocks"] = knocks
    if facts:
        doc["facts"] = facts
    return doc
