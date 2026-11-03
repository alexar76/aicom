"""Which of OUR nodes a peer is — answered from the operator's pin, never from the peer.

The monitor kept five hand-written tables mapping hosts and name prefixes to node ids, and
every row was added to fix a real bug: an unmatched peer was drawn as a second violet
planet beside the satellite that already had one, and "a second planet is a lie". The
tables work, and they are also the reason adding one satellite means editing eight files.

The fact those tables encode is not discoverable, and must not be: a peer that could name
its own node id could claim somebody else's. But it is not unknown either — the operator
already wrote it down, in `federation_seeds.json`, next to the Ed25519 key they vouched
for. This module reads that answer back.

Two properties, deliberately kept apart:

* **Identity comes from the URL the operator pinned.** `https://atlas.modelmarket.dev` is
  ATLAS because the operator put that URL in the seed file, not because the peer says
  `name: "ATLAS"` (a stranger can say that) and not because it is `trusted` (federation
  auto-admit grants that to strangers on sandbox evidence — first live pass 2026-08-31).
* **The key decides trust, not identity.** A peer whose advertised key stops matching the
  pin is quarantined by the crawler and stays quarantined. It does NOT lose its node id:
  dropping the id would drop the fold, and the satellite would be re-emitted as a
  discovered stranger next to its own greyed-out node — the duplicate planet again,
  triggered by nothing worse than a key rotation. `identity_key_matches` reports it.

`declared_id` — what the peer publishes as `ecosystem.product` — is stored and served, and
is never consulted here. It is a claim; this is an answer.
"""

from __future__ import annotations

from typing import Any

__all__ = ["canonical_id_for", "identity_for"]


def _pin_keys(peer: Any) -> tuple[str, ...]:
    """The one URL that identifies a peer row: its own ``url``.

    NOT ``well_known_url``. That field is copied verbatim out of an unauthenticated
    announce body with no origin binding to the hub URL, so reading it here let a stranger
    claim any node in the seed file by announcing `hub_url=https://evil.example` with
    `well_known_url=https://atlas.modelmarket.dev/.well-known/ai-market.json` — and the
    forged row survived operator approval, because the desk shows the id this module
    resolved. Nothing is lost by dropping it: `config.seed_node_ids` is double-keyed under
    both the well-known URL and its base, and the crawler stores the base as ``url``.
    """
    url = str(getattr(peer, "url", "") or "").strip().rstrip("/")
    return (url,) if url else ()


def identity_for(peer: Any, config: Any) -> dict[str, Any]:
    """``{"canonical_id": str, "identity_key_matches": bool | None}``.

    ``canonical_id`` is ``""`` for every peer the operator never pinned — which is every
    stranger, and correctly so: a discovered peer is drawn as itself, not folded onto one
    of ours. ``identity_key_matches`` is ``None`` when there is no pin to compare against.
    """
    node_ids = getattr(config, "seed_node_ids", None) or {}
    pubkeys = getattr(config, "seed_pubkeys", None) or {}

    for url in _pin_keys(peer):
        declared = str(node_ids.get(url) or "").strip()
        if not declared:
            continue
        # Whether the key the peer ADVERTISES still matches what this hub pinned for it.
        # Not computable from `public_key`: that column IS the pin — the crawler writes the
        # pinned key there and `record_peer_key_mismatch` deliberately leaves it alone, so
        # comparing it against the seed file compares the pin with itself. It reported
        # `True` for a peer quarantined as a takeover, and `False` for a healthy one whose
        # key an operator had legitimately re-pinned. The crawler already decided this
        # question and wrote the answer in `status`.
        matches: bool | None = None
        if pubkeys.get(url):
            matches = str(getattr(peer, "status", "") or "") != "key_mismatch"
        return {"canonical_id": declared, "identity_key_matches": matches}
    return {"canonical_id": "", "identity_key_matches": None}


def canonical_id_for(peer: Any, config: Any) -> str:
    """Just the id, for callers that do not care why."""
    return str(identity_for(peer, config)["canonical_id"])
