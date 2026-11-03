"""Buyer-facing catalogue hygiene.

Protocol identifiers stay immutable because they are payment and routing keys.  Display
names and route state are a separate concern: federated manifests in the wild often put a
fully-qualified ``product.capability@v1`` string in ``name``, and an admitted peer can later
go stale while its rows remain in the database.  This module makes both cases explicit
without rewriting the signed identifiers a caller must send back to ``/invoke``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


_VERSION_SUFFIX = re.compile(r"(?:@v[0-9][A-Za-z0-9._-]*)+$", re.IGNORECASE)
_MARKDOWN = re.compile(r"[*_`]+")
_GENERIC_CAPABILITIES = {"run", "invoke", "execute", "summarize", "summary"}


def _without_version(value: str) -> str:
    return _VERSION_SUFFIX.sub("", (value or "").strip())


def catalogue_display_name(capability: Any) -> str:
    """Return a clean UI label while preserving IDs on the underlying object.

    Examples seen in the live federation:

    * ``memory-verify.Verify Memory@v1`` → ``Verify Memory``;
    * ``prod-a1b2.run@v1`` plus ``Execute ... for SignalForge — ...`` →
      ``SignalForge · Run``;
    * ``atlas.fire.weather@v1`` → ``atlas.fire.weather``.
    """
    product_id = str(getattr(capability, "product_id", "") or "").strip()
    capability_id = str(getattr(capability, "capability_id", "") or "").strip()
    raw_name = str(getattr(capability, "name", "") or capability_id).strip()
    name = _without_version(raw_name)

    prefix = f"{product_id}." if product_id else ""
    if prefix and name.casefold().startswith(prefix.casefold()):
        name = name[len(prefix):].strip()
    name = name or _without_version(capability_id) or capability_id

    action = _without_version(capability_id).rsplit(".", 1)[-1].casefold()
    if action in _GENERIC_CAPABILITIES and name.casefold() in _GENERIC_CAPABILITIES:
        description = _MARKDOWN.sub("", str(getattr(capability, "description", "") or ""))
        subject_match = re.search(
            r"\b(?:workflow|content produced)\s+for\s+(.+?)(?:\s+[—–]\s+|\s+\([0-9]+\)\s*$|$)",
            description,
            re.IGNORECASE,
        )
        if subject_match:
            subject = subject_match.group(1).strip(" .:-")[:72]
            if subject:
                verb = "Summarize" if action in {"summarize", "summary"} else "Run"
                return f"{subject} · {verb}"
    return name[:120]


def protocol_tool_name(capability: Any) -> str:
    """Canonical manifest tool name with exactly one product and version suffix."""
    product_id = str(getattr(capability, "product_id", "") or "").strip()
    capability_id = str(getattr(capability, "capability_id", "") or "").strip()
    name = _without_version(str(getattr(capability, "name", "") or capability_id))
    prefix = f"{product_id}." if product_id else ""
    if prefix and name.casefold().startswith(prefix.casefold()):
        name = name[len(prefix):]

    raw_version = str(getattr(capability, "version", "") or "").strip().lstrip("@")
    id_match = re.search(r"@(v[0-9][A-Za-z0-9._-]*)$", capability_id, re.IGNORECASE)
    version = (id_match.group(1) if id_match else raw_version) or "v1"
    base = f"{product_id}.{name}" if product_id else name
    return f"{base}@{version}"


@dataclass(frozen=True)
class RouteFreshness:
    status: str
    age_s: int | None

    @property
    def sellable(self) -> bool:
        return self.status in {"live", "unknown"}


def route_freshness(
    capability: Any,
    peer: Any | None,
    *,
    max_age_s: int,
    now: float | None = None,
) -> RouteFreshness:
    """Classify whether a stored offer still has a route the invoke gate will admit.

    Old databases can have no ``last_crawl``.  Treat that as ``unknown`` for backwards
    compatibility, but fail closed for missing/non-active peers and for a timestamp older
    than the operator's freshness bound.
    """
    source_hub = str(getattr(capability, "source_hub", "") or "local")
    if source_hub == "local":
        return RouteFreshness("live", 0)
    if peer is None or str(getattr(peer, "status", "") or "") != "active":
        return RouteFreshness("unavailable", None)

    stamp = str(getattr(peer, "last_crawl", "") or "").strip()
    if not stamp:
        return RouteFreshness("unknown", None)
    try:
        parsed = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return RouteFreshness("unknown", None)
    age = max(0, int((time.time() if now is None else now) - parsed.timestamp()))
    return RouteFreshness("stale" if age > max(1, int(max_age_s)) else "live", age)
