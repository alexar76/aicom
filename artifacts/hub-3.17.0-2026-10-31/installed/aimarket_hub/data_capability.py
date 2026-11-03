"""Data-as-Capability (#7) — a manifest builder, not a search engine.

**What this used to be, and why it changed.** The module described a marketplace: "notary
company uploads 50k court decisions → `legal.us-cases.search@v1`, $0.05 per query, 70%
revenue to owner". None of that existed. `query()` returned an f-string built from the
caller's own words with `relevance_score` hard-coded to 0.95; `register()` took
`document_count` and `data_size_bytes` as caller-asserted integers and generated `data_hash`
from `owner_address + time.time()`, so the "SHA-256 of the corpus" was a nonce committing to
nothing; there was no upload endpoint, no index, no route, no table and no payout path;
`platform_fee_pct` was assigned in the constructor and never read again. The whole thing was
imported by nothing but its own tests while the feature matrix marked it "✅ Done".

**What it is now.** The three real pieces it was standing in for all exist:

* the corpus and the search belong to the publisher, behind their own `invoke_url` — the hub
  hosts nothing and never did, and pretending otherwise is what made this a mock;
* listing is `POST /ai-market/v2/supply/register`, self-serve with a credit-account key;
* the 70/30 split is real money now — `AIMARKET_PUBLISHER_SHARE_BPS`, paid into the
  publisher's credit balance on every completed sale (`credits.pay_publisher`).

So what is left here is the one thing that was genuinely useful: turning a description of a
corpus into the manifest those endpoints expect, with the pricing and access policy filled
in consistently. It computes nothing it cannot know and asserts nothing it cannot check.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

#: Default share of each query that goes to the data owner. The hub enforces the split
#: itself from ``AIMARKET_PUBLISHER_SHARE_BPS``; this is only what the manifest advertises.
DEFAULT_OWNER_SHARE_PCT = 0.70

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, fallback: str = "corpus") -> str:
    slug = _SLUG_RE.sub("-", str(text or "").strip().lower()).strip("-")
    return (slug or fallback)[:48]


def corpus_fingerprint(documents: list[str]) -> str:
    """SHA-256 over the documents themselves, in a fixed order.

    A real commitment, unlike the old `data_hash`: two publishers with the same corpus get
    the same fingerprint, and changing one document changes it. Callers that do not want to
    hand their corpus to this process should hash it themselves and pass the digest — what
    must not happen is a random value presented to buyers as a content hash.
    """
    digest = hashlib.sha256()
    for doc in sorted(str(d) for d in documents or []):
        digest.update(hashlib.sha256(doc.encode("utf-8")).digest())
    return digest.hexdigest()


def data_capability_manifest(
    *,
    name: str,
    description: str,
    invoke_url: str,
    query_price_usd: float,
    publisher_id: str = "",
    corpus_hash: str = "",
    document_count: int | None = None,
    tags: list[str] | None = None,
    owner_share_pct: float = DEFAULT_OWNER_SHARE_PCT,
    max_query_length: int = 4000,
) -> dict[str, Any]:
    """Build the `/supply/register` body for a corpus the publisher serves themselves.

    ``document_count`` is optional and echoed as the publisher's own claim rather than as a
    fact this hub verified — the previous version stored the same number as if the hub had
    counted it.
    """
    slug = slugify(name)
    manifest: dict[str, Any] = {
        "product_id": f"data-{slug}",
        "capability_id": f"{slug}.search@v1",
        "name": name,
        "description": description,
        "invoke_url": invoke_url,
        "price_per_call_usd": round(float(query_price_usd), 6),
        "categories": ["data", "search", *(tags or [])],
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": int(max_query_length)},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "snippet": {"type": "string"},
                            "document_id": {"type": "string"},
                            "relevance_score": {"type": "number"},
                        },
                    },
                },
                "total_matches": {"type": "integer"},
            },
            "required": ["results"],
        },
        # Advertised, and separately enforced by the hub on every sale.
        "revenue_share": {
            "owner_share_pct": round(float(owner_share_pct), 4),
            "settled_by": "hub credits (AIMARKET_PUBLISHER_SHARE_BPS)",
        },
    }
    if publisher_id:
        manifest["publisher_id"] = publisher_id
    if corpus_hash:
        manifest["corpus_sha256"] = str(corpus_hash)
    if document_count is not None:
        manifest["claimed_document_count"] = int(document_count)
    return manifest


def expected_owner_earnings(
    query_price_usd: float, queries: int, owner_share_pct: float = DEFAULT_OWNER_SHARE_PCT,
) -> dict[str, float]:
    """What a publisher would earn for N sales at this price — arithmetic, not a promise."""
    gross = round(float(query_price_usd) * max(0, int(queries)), 6)
    owner = round(gross * float(owner_share_pct), 6)
    return {
        "gross_usd": gross,
        "owner_usd": owner,
        "operator_usd": round(gross - owner, 6),
    }
