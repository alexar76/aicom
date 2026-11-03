"""Can this hub actually execute a capability it is offering for sale?

One predicate, used by everything that either accepts a listing or advertises one, so
the three places that need the answer cannot drift apart:

* ``factory_bridge.import_factory_products`` — refuse the row at ingest;
* the ``/ai-market/v2/search`` and manifest paths — never offer it to a buyer;
* ``scripts/cleanup_hub_demo_catalogue.py`` — find the rows already stored.

Why a serving-side check and not just an ingest gate: the ingest gate only protects rows
that arrive *after* it exists. The live hub was found selling twelve capabilities at
$0.15–$1.50 that answered 404, seeded long before any gate, and a name-pattern cleanup
missed every one of them because the names looked respectable (``code.review@v1``,
``legal.review@v1``). Rows also arrive by admin insert, DB restore, and federation import.
The buyer-facing question is "can this run", so that is where the check belongs.

The execution paths this mirrors live in ``api.py`` (the invoke handler), in this order:

1. ``invoke_url``            — an external provider endpoint;
2. ``prompt_template``       — a hub-local static JSON pack, e.g. security-rules.sec-feed;
3. ``AIFACTORY_PUBLIC_URL``  — the factory fallback, deliberately NOT counted (see below).

The factory fallback is excluded on purpose. It is a blind POST to
``{factory}/capabilities/{product_id}/{capability_id}/invoke``; whether anything answers
there is unknowable from a database row, and on the live deployment every one of those
twelve returned ``404 capability not found``. Counting it would make the predicate mean
"might work", which is exactly the assumption that put unsellable rows in the storefront.
A capability that genuinely lives behind the factory should carry its ``invoke_url``.
"""

from __future__ import annotations

from typing import Any


def has_execution_path(
    invoke_url: str | None, prompt_template: str | None = None
) -> bool:
    """True when the hub knows, from the row alone, how to run this capability."""
    if (invoke_url or "").strip():
        return True
    # A static pack is stored as a JSON object in prompt_template and returned verbatim
    # by the invoke handler. Anything else in that column is an LLM prompt, which is not
    # an execution path on its own.
    return (prompt_template or "").strip().startswith("{")


def capability_is_fulfillable(cap: Any) -> bool:
    """``has_execution_path`` for a Capability object or a plain dict row.

    Federated capabilities are always fulfillable from this hub's point of view: the
    peer that published them owns execution, and this hub only routes. Applying the
    local rule to them would silently unlist the whole federation.
    """
    if isinstance(cap, dict):
        if (cap.get("product_id"), cap.get("capability_id"), cap.get("source_hub") or "local") == ("hephaestus", "pipeline.run@v1", "local"):
            return True
        source_hub = str(cap.get("source_hub") or "")
        invoke_url = cap.get("invoke_url")
        prompt_template = cap.get("prompt_template")
    else:
        if (getattr(cap, "product_id", ""), getattr(cap, "capability_id", ""), getattr(cap, "source_hub", "") or "local") == ("hephaestus", "pipeline.run@v1", "local"):
            return True
        source_hub = str(getattr(cap, "source_hub", "") or "")
        invoke_url = getattr(cap, "invoke_url", "")
        prompt_template = getattr(cap, "prompt_template", "")

    if source_hub and source_hub != "local":
        return True
    return has_execution_path(invoke_url, prompt_template)
