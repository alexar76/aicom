"""Stamp every Alien Monitor node with the hub it belongs to.

Operators need this on the detail card — which federation Hub owns / lists / settles
for this surface. Rules:

- A hub node belongs to itself.
- Signal Hunt game → Signal Hunt Hub.
- Use Cases portal → Competing Lab Hub.
- Other competing-galaxy nodes → Competing Lab Hub (default lab edge).
- Discovered hub suns → themselves; their children → their parent hub.
- Discovered services → the listing hub, never made into hubs by affiliation.
- Everything else in the primary galaxy → AIMarket Hub (public edge).

``HUB_URL`` / loopback ``:9083`` is the *API* poll target inside Docker. Operator
links on the card must use the public HTTPS edge (``ALIEN_PUBLIC_HUB_URL``), same
split Competing Lab already has for ``ALIEN_COMPETING_HUB_PUBLIC_URL``.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from competing_lab_layers import competing_hub_url, signal_hunt_url

DEFAULT_PUBLIC_HUB_URL = "https://modelmarket.dev"


def hub_public_url() -> str:
    """Public HTTPS edge for operator links (node cards, hub affiliation).

    The universe map must not hand out the live hub's hostname: a UNI card that
    says ``modelmarket.dev`` is how bubble dollars get read as revenue. When this
    process is ``ALIEN_MODE=universe`` and ``ALIEN_UNI_HUB_URL`` is set, that is
    the edge. LIVE (and anyone without a bubble hub) keeps the live public URL.
    """
    mode = (os.environ.get("ALIEN_MODE") or "").strip().lower()
    if mode == "universe":
        uni = (os.environ.get("ALIEN_UNI_HUB_URL") or "").strip().rstrip("/")
        if uni:
            return uni
    return (
        os.environ.get("ALIEN_PUBLIC_HUB_URL", "").strip()
        or os.environ.get("HUB_PUBLIC_URL", "").strip()
        or os.environ.get("AIMARKET_PUBLIC_HUB_URL", "").strip()
        or DEFAULT_PUBLIC_HUB_URL
    ).rstrip("/")


def _host(url: str | None) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url if "://" in url else f"http://{url}")
        host = (p.hostname or "").lower()
        port = p.port
        if port and port not in (80, 443):
            return f"{host}:{port}"
        return host
    except Exception:
        return str(url).lower().strip()


def _hub_ref(*, hid: str, label: str, url: str | None = None) -> dict[str, str]:
    out = {"id": hid, "label": label}
    if url:
        out["url"] = url
    return out


def apply_hub_affiliation(
    nodes: list[dict[str, Any]],
    *,
    primary_hub_url: str | None = None,
    primary_label: str = "AIMarket Hub",
) -> None:
    """Mutate ``nodes`` in place — set ``hub: {id, label, url?}`` on each.

    ``primary_hub_url`` should be the *public* operator edge. Callers that only
    have the Docker API URL should omit it (defaults to ``hub_public_url()``).
    """
    primary = (primary_hub_url or hub_public_url()).rstrip("/")
    lab = competing_hub_url().rstrip("/")
    hunt = signal_hunt_url().rstrip("/")
    primary_host = _host(primary)
    lab_host = _host(lab)
    hunt_host = _host(hunt)

    primary_hub = _hub_ref(hid="hub", label=primary_label, url=primary)
    lab_hub = _hub_ref(hid="competing_hub", label="Competing Lab Hub", url=lab)
    hunt_hub = _hub_ref(hid="signal_hunt_hub", label="Signal Hunt Hub", url=hunt)

    # Consume the role discovery resolved for the graph, rather than inventing a second
    # definition of "hub" from `discovered`. A provider in a hub's system stays a provider.
    peer_hubs = {
        str(n["id"]): _hub_ref(
            hid=str(n["id"]), label=str(n.get("label") or n["id"]), url=n.get("url"),
        )
        for n in nodes if isinstance(n, dict) and n.get("id")
        and (n.get("role") == "hub" or n.get("group") in ("peer_hub", "pending_hub"))
    }
    parent_hubs = {**peer_hubs, "hub": primary_hub, "competing_hub": lab_hub,
                   "signal_hunt_hub": hunt_hub}

    for node in nodes:
        if not isinstance(node, dict) or not node.get("id"):
            continue
        nid = str(node["id"])
        url = (node.get("url") or "").rstrip("/")
        host = _host(url)

        if nid == "hub":
            node["hub"] = dict(primary_hub)
            # Card link must be the public edge even when the entity was seeded
            # with Docker HUB_URL (127.0.0.1:9083) for layer polls.
            if primary:
                node["url"] = primary
            continue

        if nid == "competing_hub":
            node["hub"] = _hub_ref(
                hid="competing_hub",
                label=str(node.get("label") or "Competing Lab Hub"),
                url=url or lab,
            )
            continue

        if nid == "signal_hunt_hub":
            node["hub"] = _hub_ref(
                hid="signal_hunt_hub",
                label=str(node.get("label") or "Signal Hunt Hub"),
                url=url or hunt,
            )
            continue

        if nid in peer_hubs:
            node["hub"] = dict(peer_hubs[nid])
            continue

        parent = node.get("parent_id")
        if isinstance(parent, str) and parent in parent_hubs:
            node["hub"] = dict(parent_hubs[parent])
            continue

        # Game belongs to Signal Hunt Hub; use portal to Competing Lab Hub.
        if nid == "signal_hunt":
            node["hub"] = dict(hunt_hub)
            continue

        if nid == "use_cases" or node.get("galaxy") == "competing":
            node["hub"] = dict(lab_hub)
            continue

        if host and host == hunt_host:
            node["hub"] = dict(hunt_hub)
            continue
        if host and host == lab_host:
            node["hub"] = dict(lab_hub)
            continue
        if host and primary_host and host == primary_host:
            node["hub"] = dict(primary_hub)
            continue

        node["hub"] = dict(primary_hub)
