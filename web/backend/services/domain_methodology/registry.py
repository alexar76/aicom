"""
Lookup of domain methodology packs.

This module is the *registry* layer on top of the static built-in packs in
:mod:`web.backend.services.domain_methodology.packs`. It exposes pack lookup
by id, full ranking for diagnostics, and a heuristic auto-selector used by the
PM/QA agents and the admin API.

Public API
----------

* :func:`list_domain_packs`  – full catalog.
* :func:`get_domain_pack`    – exact ``domain_id`` lookup.
* :func:`score_domain_packs` – full ranking (used by ``/methodology/domains/match``).
* :func:`select_domain_pack` – best-match pack for an idea / spec, or ``None``
  when nothing scores above ``min_score`` (the methodologist then falls back
  to generic structural checks).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from web.backend.services.domain_methodology.base import DomainPack
from web.backend.services.domain_methodology.packs import ALL_PACKS


def list_domain_packs() -> list[DomainPack]:
    """Return all built-in packs as a fresh list (safe to mutate by callers)."""
    return list(ALL_PACKS)


def get_domain_pack(domain_id: str) -> Optional[DomainPack]:
    """Return the pack with the given ``domain_id`` (case-insensitive), or ``None``."""
    needle = (domain_id or "").strip().lower()
    if not needle:
        return None
    for pack in ALL_PACKS:
        if pack.domain_id == needle:
            return pack
    return None


def _gather_text(idea: str, category: Optional[str], spec: Optional[dict[str, Any]]) -> str:
    """Concatenate idea + category + relevant spec fields into a lowercased blob.

    The blob is the input that :func:`_score_pack` searches for keyword and
    entity mentions. We pull only the human-readable fields that actually carry
    domain signal (description, features, functional requirements, user stories).
    """
    parts: list[str] = []
    if isinstance(idea, str):
        parts.append(idea)
    if isinstance(category, str):
        parts.append(category)
    if isinstance(spec, dict):
        for key in ("product_name", "description", "category"):
            v = spec.get(key)
            if isinstance(v, str):
                parts.append(v)
        for f in spec.get("core_features") or []:
            if isinstance(f, dict):
                for k in ("name", "description"):
                    v = f.get(k)
                    if isinstance(v, str):
                        parts.append(v)
        for fr in spec.get("functional_requirements") or []:
            if isinstance(fr, dict):
                for k in ("title", "description", "acceptance_criteria"):
                    v = fr.get(k)
                    if isinstance(v, str):
                        parts.append(v)
        for us in spec.get("user_stories") or []:
            if isinstance(us, dict):
                for k in ("story", "acceptance_criteria"):
                    v = us.get(k)
                    if isinstance(v, str):
                        parts.append(v)
    return " \n ".join(parts).lower()


def _score_pack(pack: DomainPack, blob: str, category_lc: str) -> int:
    """Heuristic pack score for a given idea blob.

    Weighting (additive):

    * ``+6`` exact category match,
    * ``+3`` partial category match,
    * ``+3`` per multi-word keyword hit, ``+2`` per single-word keyword hit,
    * ``+1`` per primary-token entity name hit (≥ 4 chars).

    Keywords are the dominant signal; entities are a soft tiebreaker.
    """
    score = 0
    if category_lc and any(category_lc == c for c in pack.categories):
        score += 6
    elif category_lc and any(c and c in category_lc for c in pack.categories):
        score += 3
    for kw in pack.keywords:
        if kw and kw in blob:
            score += 3 if " " in kw else 2
    # Entity / capability mentions are softer hints (only count primary token).
    for ent in pack.entities:
        token = ent.name.split("/")[0].split(" ")[0]
        if len(token) >= 4 and token in blob:
            score += 1
    return score


def score_domain_packs(
    idea: str,
    category: Optional[str] = None,
    spec: Optional[dict[str, Any]] = None,
    *,
    candidates: Optional[Iterable[DomainPack]] = None,
) -> list[tuple[DomainPack, int]]:
    """Return ``(pack, score)`` pairs sorted by descending score.

    Used both for the auto-selector and as a diagnostic endpoint
    (``POST /api/admin/methodology/domains/match``). Pass ``candidates`` to
    restrict the search to a subset of packs (e.g. for unit tests).
    Returns ``[]`` if there is no usable text to score against.
    """
    blob = _gather_text(idea, category, spec)
    if not blob.strip():
        return []
    category_lc = (category or "").strip().lower()
    pool = list(candidates) if candidates is not None else list(ALL_PACKS)
    ranked = [(pack, _score_pack(pack, blob, category_lc)) for pack in pool]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked


def select_domain_pack(
    idea: str,
    category: Optional[str] = None,
    spec: Optional[dict[str, Any]] = None,
    *,
    candidates: Optional[Iterable[DomainPack]] = None,
    min_score: int = 4,
) -> Optional[DomainPack]:
    """Pick the best-fit pack or return ``None`` if nothing is confident enough.

    Returning ``None`` is a deliberate fallback: when no pack scores above
    ``min_score`` the methodologist runs only the generic structural checks
    (entities/capabilities) — better than forcing an irrelevant domain shape.
    """
    ranked = score_domain_packs(idea, category, spec, candidates=candidates)
    if not ranked:
        return None
    best, best_score = ranked[0]
    if best_score < min_score:
        return None
    return best
