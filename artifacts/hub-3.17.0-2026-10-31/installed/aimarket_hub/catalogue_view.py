"""What buyer-facing catalogue surfaces read about a capability: whether its route is sellable
now, the fulfillable snapshot, the inputs a caller must supply, and the answer-dependence
bookkeeping on each call. Moved out of api.py, which re-exports every name.
"""

from __future__ import annotations

import logging
from typing import Any

from aimarket_hub.access_policy import capability_is_publicly_offerable
from aimarket_hub.catalog import route_freshness
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from aimarket_hub.fulfillment import capability_is_fulfillable

logger = logging.getLogger(__name__)


# ── What a caller must supply to invoke ────────────────────────
#
# The catalogue carries every provider's `input_schema`, but /search never surfaced
# any of it, so a client had no way to know a capability has required fields. The
# hub's own console then sent one shape — `{"text": <query>}` — to everything, which
# is fine for a free-text oracle and invalid for every capability that needs real
# arguments: on 2026-08-25 production showed `atlas.point.read@v1` refused 8/8 with
# `point_id required`, plus the same refusal on situation.brief / watchbox.check /
# fire.weather / gnss.degradation / ais.public.read. A refusal still spends a free
# trial and (on a paid channel) still settles, so guessing the body is not free.
#
# Only the REQUIRED properties are echoed, and only the fields a form needs: the
# whole schema on every one of up to 100 matches would bloat a browse response for
# data the caller can still fetch from the provider's manifest.
_INPUT_HINT_KEYS = ("type", "description", "enum", "minimum", "maximum", "default")


def _input_requirements(schema: Any) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Required input names + a compact per-field hint, from a capability schema.

    Defensive about the shape: `input_schema` is a peer-controlled blob that the
    crawler stores verbatim, so anything that is not the JSON-Schema object we expect
    yields "no known requirements" rather than an exception on a browse request.
    """
    if not isinstance(schema, dict):
        return [], {}
    props = schema.get("properties")
    props = props if isinstance(props, dict) else {}
    # `required` must be a LIST. A peer that writes it as a bare string would
    # otherwise be iterated character by character — "point_id" became eight
    # single-letter required fields (caught by the peer-blob test below).
    declared = schema.get("required")
    declared = declared if isinstance(declared, (list, tuple)) else []
    required: list[str] = []
    hints: dict[str, dict[str, Any]] = {}
    for name in declared:
        if not isinstance(name, str) or name in hints:
            continue
        # A property listed as required but never described is still required — the
        # caller has to be told about it even with no hint to give.
        spec = props.get(name)
        spec = spec if isinstance(spec, dict) else {}
        required.append(name)
        hints[name] = {
            k: spec[k] for k in _INPUT_HINT_KEYS
            if k in spec and isinstance(spec[k], (str, int, float, bool, list))
        }
    return required, hints


def _observe_answer(db: HubDatabase, source_hub: Any, body: Any, response: Any) -> None:
    """Digests of what was asked and what came back (answer_dependence.py). Bookkeeping: never fails a call."""
    try:
        from aimarket_hub import answer_dependence

        answer_dependence.observe(
            db, (str(source_hub or "local"), body.product_id, body.capability_id), body.input, response,
        )
    except Exception as exc:
        logger.warning("answer observation NOT recorded for %s: %s", getattr(body, "capability_id", "?"), exc)


def _catalogue_route(db: HubDatabase, config: HubConfig, capability: Any):
    """Route state shared by every buyer-facing catalogue surface."""
    source_hub = str(getattr(capability, "source_hub", "") or "local")
    peer = None if source_hub == "local" else db.get_peer(source_hub)
    return route_freshness(
        capability,
        peer,
        max_age_s=config.catalog_max_stale_s,
    )


def _catalogue_snapshot(db: HubDatabase, config: HubConfig, *, limit: int = 1000):
    """Fulfillable, public offers whose route is currently sellable."""
    return [
        capability
        for capability in db.list_capabilities(limit=limit)
        if capability_is_fulfillable(capability)
        and capability_is_publicly_offerable(capability)
        and _catalogue_route(db, config, capability).sellable
    ]
