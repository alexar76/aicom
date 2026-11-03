"""Where an AI-Market invoke envelope is POSTed for a given peer — one rule.

Two callers need this answer: routed invokes (``peer_routing._peer_invoke_endpoint``) and the
post-quarantine admission assay (``federation_assay``). They answered it differently
until 2026-08-31, and the assay's answer was the wrong one.

A peer that runs the hub implementation advertises ``mcp_endpoint`` pointing at its
**MCP JSON-RPC** gateway (``/ai-market/mcp``). That endpoint does not accept the
``{capability_id, product_id, input}`` envelope: it answers a short JSON-RPC error, or
``Method not found`` inside a ``text/event-stream`` body. Routing learned this and sends
hub peers to their ``/ai-market/v2/invoke`` route; the assay kept reading ``mcp_endpoint``
verbatim, so its sandbox probe of a live hub came back as 117 bytes of JSON-RPC error and
scored ``review``. Every hub that advertises an MCP gateway — which is every hub running
our image, and the thing we tell operators to publish — was therefore structurally
unable to be admitted automatically.

Non-hub peers keep their advertised endpoint: GAIA publishes
``mcp_endpoint: https://iot.modelmarket.dev/ai-market/v2/invoke``, which is an invoke URL
wearing the MCP name, and following it is correct.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

__all__ = ["peer_is_aimarket_hub", "invoke_endpoint_candidates", "invoke_endpoint_for",
           "peer_tool_endpoint"]


def peer_is_aimarket_hub(well_known: Any) -> bool:
    """Does this peer run the hub implementation (rather than a bare capability service)?

    ``hub_version`` is the signal, and it is the only one. A v2 entry in
    ``protocol_versions`` says which protocol the peer *speaks* — SKOPOS speaks v2 and
    serves its invokes at ``/aimarket/invoke``, so reading v2 as "hub" sent both its sandbox
    probe and every routed invoke to a URL that answers 404. Read from what the peer
    publishes about itself, never from its URL or its category.
    """
    if not isinstance(well_known, dict):
        return False
    return bool(str(well_known.get("hub_version") or "").strip())


def invoke_endpoint_candidates(base_url: str, well_known: Any) -> list[str]:
    """Where to POST an invoke, best guess first, then the other one.

    Declarations are how peers disagree; an HTTP status is how they settle it. A caller
    that can afford a second POST (the admission assay) walks this list until something
    answers like an endpoint rather than like a 404 — which is what finally reached SKOPOS.
    Routing takes the first and does not retry.
    """
    base = str(base_url or "").rstrip("/")
    derived = f"{base}/ai-market/v2/invoke"
    advertised = ""
    if isinstance(well_known, dict):
        advertised = str(well_known.get("mcp_endpoint") or "").strip().rstrip("/")
    ordered = [derived, advertised] if peer_is_aimarket_hub(well_known) else [advertised, derived]
    out: list[str] = []
    for url in ordered:
        if url and url not in out:
            out.append(url)
    return out or [derived]


def invoke_endpoint_for(base_url: str, well_known: Any) -> str:
    """The single URL routing uses: the first candidate.

    Always concrete — a peer that advertises no endpoint at all falls back to the v2 invoke
    route it would have if it ran the reference implementation. Routing has a third answer
    (``None`` → the legacy ``/capabilities/{product}/{cap}/invoke`` path) and keeps it
    locally; the rule they share is which peers must ignore ``mcp_endpoint``.
    """
    return invoke_endpoint_candidates(base_url, well_known)[0]


def peer_tool_endpoint(tool: Any, peer_url: str) -> str:
    """The URL a peer sells this manifest tool at, or "" when routing must not use one.

    The spec asks a tool for a name, a description and an input_schema. An x402 seller adds
    ``endpoint`` and ``method`` and answers there, with no AI-Market invoke route at all: both
    outside implementations that knocked on modelmarket.dev in October 2026 are built that way
    (mach402.dev, agent-exec.448c.org). Their invoke candidates answer 404 and their tools carry
    no ``capability_id``, so the assay had nothing to probe and routing nowhere to go.

    Only for that shape: a tool with a ``capability_id`` is a hub-protocol listing and goes
    through the peer's invoke route as before. The method must be POST (or unstated), and the
    endpoint — absolute, or a path on the peer — must sit on exactly the peer's origin: a peer
    names where its OWN tools answer, never someone else's host. Callers still apply their
    SSRF guard; this only decides whether the peer's own manifest may point us there.
    """
    if not isinstance(tool, dict):
        return ""
    if str(tool.get("capability_id") or tool.get("id") or "").strip():
        return ""
    if str(tool.get("method") or "POST").strip().upper() != "POST":
        return ""
    raw = str(tool.get("endpoint") or "").strip()
    if not raw or raw.startswith("//") or any(c in raw for c in "\r\n\t\\ "):
        return ""
    url = urljoin(str(peer_url or "").rstrip("/") + "/", raw) if raw.startswith("/") else raw
    a, b = urlparse(str(peer_url or "")), urlparse(url)
    if b.scheme not in ("http", "https") or b.scheme != a.scheme or b.username or b.password:
        return ""
    if (b.hostname or "").lower() != (a.hostname or "").lower() or not b.hostname:
        return ""
    default = {"https": 443, "http": 80}
    try:
        if (a.port or default[a.scheme]) != (b.port or default[b.scheme]):
            return ""
    except ValueError:
        return ""
    return url.split("#", 1)[0]

