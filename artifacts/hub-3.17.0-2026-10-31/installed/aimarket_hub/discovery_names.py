"""The protocol's names on the wire, in both spellings.

The Internet-Drafts in ``aimarket-protocol/ietf/`` propose names without a product brand:
the discovery document at ``/.well-known/agent-marketplace`` (RFC 8615) and the request
header ``Agent-Marketplace-Crawler`` (no ``X-`` prefix, RFC 6648). The hub has served
``/.well-known/ai-market.json`` and sent ``X-AIMarket-Crawler`` since 2026-05, and every
peer in the network reads those. Both spellings are therefore served, sent and accepted
side by side; nothing here retires the old ones.

The draft document differs from the legacy one in three members, and this module is the
single place that maps between them:

===================  ==========================  ==========================================
draft name           legacy name                 note
===================  ==========================  ==========================================
``catalogue_url``    ``manifest_url``            same resource
``peers``            ``peers``                   draft: array of discovery-document URIs;
                                                 legacy: array of objects with ``url``
``signature_profile``  (implied)                 always ``ed25519-pipe-2`` here
===================  ==========================  ==========================================

The signed catalogue itself is byte-identical under both names (the canonical string keeps
the pair name ``tools_hash``), so a signature valid for one reader is valid for the other.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

DRAFT_WELL_KNOWN_PATH = "/.well-known/agent-marketplace"
LEGACY_WELL_KNOWN_PATH = "/.well-known/ai-market.json"

DRAFT_CRAWLER_HEADER = "Agent-Marketplace-Crawler"
LEGACY_CRAWLER_HEADER = "X-AIMarket-Crawler"

#: The one signature profile this hub implements (draft §5).
SIGNATURE_PROFILE = "ed25519-pipe-2"

_WELL_KNOWN_MARK = "/.well-known/"


def discovery_base(discovery_url: str) -> str:
    """The hub base a discovery-document URI belongs to, under either spelling."""
    text = str(discovery_url or "").strip()
    if _WELL_KNOWN_MARK in text:
        return text.rsplit(_WELL_KNOWN_MARK, 1)[0].rstrip("/")
    return text.rstrip("/")


def is_draft_document(doc: dict[str, Any]) -> bool:
    """True when a discovery document uses the draft's member names."""
    return isinstance(doc, dict) and isinstance(doc.get("catalogue_url"), str) and not isinstance(
        doc.get("manifest_url"), str
    )


def normalize_discovery_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Return ``doc`` with the legacy members filled in from the draft ones.

    A reader that only knows the legacy shape (the schema validator, the crawler, the
    assay) runs unchanged on the result. Members already present are never overwritten:
    a document that carries both spellings is taken at its word on the legacy one, which
    is what every existing peer reads.

    ``peers`` given as discovery-document URIs become ``{"url", "name",
    "well_known_url"}`` objects, so a peer that lives under the draft path is dialled at
    the draft path and not at a legacy path it may not serve.
    """
    if not isinstance(doc, dict):
        return doc
    out = dict(doc)
    if isinstance(out.get("catalogue_url"), str) and not isinstance(out.get("manifest_url"), str):
        out["manifest_url"] = out["catalogue_url"]
    peers = out.get("peers")
    if isinstance(peers, list) and any(isinstance(p, str) for p in peers):
        converted: list[Any] = []
        for p in peers:
            if isinstance(p, str):
                base = discovery_base(p)
                if not base:
                    continue
                converted.append({"url": base, "name": base, "well_known_url": p.strip()})
            else:
                converted.append(p)
        out["peers"] = converted
    return out


def draft_discovery_document(legacy: dict[str, Any], peer_discovery_urls: list[str]) -> dict[str, Any]:
    """The draft-shaped document for ``/.well-known/agent-marketplace``.

    Built from the legacy document so the two can never disagree about the key, the
    catalogue or the counts. ``peer_discovery_urls`` are the discovery URIs this hub
    actually reads for its admitted peers — a legacy path for a peer that serves only
    that, the draft path once a peer advertises one. A reader following them gets a
    document that exists, which beats a path that 404s.

    ``manifest_url`` rides along as an unknown member for legacy readers that land here;
    the draft says a reader MUST ignore members it does not recognise.
    """
    catalogue_url = str(legacy.get("manifest_url") or "")
    doc: dict[str, Any] = {
        "name": legacy.get("name"),
        "protocol_versions": list(legacy.get("protocol_versions") or []),
        "catalogue_url": catalogue_url,
        "manifest_url": catalogue_url,
        "signer_public_key": legacy.get("signer_public_key"),
        "signature_profile": SIGNATURE_PROFILE,
        "capabilities_count": legacy.get("capabilities_count", 0),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "peers": list(peer_discovery_urls),
        "hub_version": legacy.get("hub_version"),
        "mcp_endpoint": legacy.get("mcp_endpoint"),
        # Where the pre-standard document lives, for a reader that wants the full
        # legacy member set (payment rails, ecosystem, observed hubs).
        "legacy_discovery_url": None,
    }
    hub_url = str(legacy.get("hub_url") or legacy.get("base_url") or "").rstrip("/")
    if not hub_url and catalogue_url and "/ai-market/" in catalogue_url:
        hub_url = catalogue_url.split("/ai-market/", 1)[0]
    doc["legacy_discovery_url"] = f"{hub_url}{LEGACY_WELL_KNOWN_PATH}" if hub_url else None
    return {k: v for k, v in doc.items() if v is not None}
