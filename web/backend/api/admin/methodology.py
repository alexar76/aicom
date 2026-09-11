"""
Admin API for the Methodologist Agent.

Endpoints:

* `GET    /api/admin/methodology/domains`                    — pack catalog (compact)
* `GET    /api/admin/methodology/domains/{domain_id}`        — full pack schema
* `POST   /api/admin/methodology/domains/match`              — auto-match a domain pack
* `POST   /api/admin/methodology/review/spec`                — run a one-shot spec review
* `POST   /api/admin/methodology/review/implementation/{pid}`— run a one-shot implementation review
* `GET    /api/admin/methodology/cases/{product_id}`         — review history for a product
* `GET    /api/admin/methodology/lessons`                    — list lessons
* `POST   /api/admin/methodology/lessons`                    — add a lesson
* `PATCH  /api/admin/methodology/lessons/{lesson_id}`        — edit / disable / re-enable a lesson
* `DELETE /api/admin/methodology/lessons/{lesson_id}`        — delete a lesson
* `GET    /api/admin/methodology/search?q=...`               — search lessons + cases
* `POST   /api/admin/methodology/feedback`                   — operator feedback (auto-promotes lessons)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.paths import data_root as default_data_root
from web.backend.core.admin_roles import require_admin_with_rbac
from web.backend.services.domain_methodology import (
    DomainPack,
    get_domain_pack,
    list_domain_packs,
    score_domain_packs,
    select_domain_pack,
)
from web.backend.services.methodology_knowledge import (
    MethodologyKnowledgeStore,
    MethodologyLesson,
)
from web.backend.services.methodology_review import (
    review_implementation,
    review_spec,
)


router = APIRouter(
    prefix="/api/admin/methodology",
    tags=["admin-methodology"],
    dependencies=[Depends(require_admin_with_rbac)],
)


def _store() -> MethodologyKnowledgeStore:
    """Build a fresh :class:`MethodologyKnowledgeStore` rooted at the factory data dir."""
    return MethodologyKnowledgeStore(data_root=str(default_data_root()))


def _resolve_pack(domain_id: str) -> DomainPack:
    """Look up a pack by id or raise ``404`` for the admin API."""
    pack = get_domain_pack(domain_id)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"unknown domain pack: {domain_id}")
    return pack


# --------------------------------------------------------------------- domains


@router.get("/domains")
async def list_domains() -> dict[str, Any]:
    """``GET /api/admin/methodology/domains`` — compact catalog of built-in packs."""
    return {
        "domains": [pack.to_payload(full=False) for pack in list_domain_packs()],
        "count": len(list_domain_packs()),
    }


@router.get("/domains/{domain_id}")
async def get_domain(domain_id: str) -> dict[str, Any]:
    """``GET /api/admin/methodology/domains/{id}`` — full schema-v2 pack payload."""
    pack = _resolve_pack(domain_id)
    return pack.to_payload(full=True)


class DomainMatchRequest(BaseModel):
    """Body for :func:`match_domain` — describes the idea / spec to match against."""

    idea: str = ""
    category: Optional[str] = None
    specification: Optional[dict[str, Any]] = None
    forced_domain_id: Optional[str] = None


@router.post("/domains/match")
async def match_domain(payload: DomainMatchRequest) -> dict[str, Any]:
    """``POST /api/admin/methodology/domains/match`` — auto-pick the best-fit pack.

    Returns ``{ "matched": <compact_pack | null>, "ranking": [{...}] }``. When
    ``forced_domain_id`` is supplied the ranking is omitted and the explicitly
    chosen pack is returned (with ``404`` if the id is unknown).
    """
    if payload.forced_domain_id:
        pack = get_domain_pack(payload.forced_domain_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="forced_domain_id not found")
        ranking = []
    else:
        pack = select_domain_pack(payload.idea or "", category=payload.category, spec=payload.specification)
        ranking = [
            {"domain_id": p.domain_id, "label": p.label, "score": s}
            for p, s in score_domain_packs(payload.idea or "", category=payload.category, spec=payload.specification)
        ]
    return {
        "matched": pack.to_payload(full=False) if pack else None,
        "ranking": ranking,
    }


# --------------------------------------------------------------------- review


class SpecReviewRequest(BaseModel):
    """Body for the ad-hoc post-spec review endpoint.

    ``product_id`` is optional; when supplied (and ``persist_case=True``) the
    review is appended to that product's case history.
    """

    product_id: Optional[str] = None
    idea: str = ""
    category: Optional[str] = None
    specification: dict[str, Any] = Field(default_factory=dict)
    forced_domain_id: Optional[str] = None
    persist_case: bool = True


@router.post("/review/spec")
async def review_spec_endpoint(payload: SpecReviewRequest) -> dict[str, Any]:
    """``POST /api/admin/methodology/review/spec`` — run a one-shot spec review."""
    if payload.forced_domain_id:
        pack = get_domain_pack(payload.forced_domain_id)
    else:
        pack = select_domain_pack(payload.idea, category=payload.category, spec=payload.specification)
    knowledge = _store()
    persist = payload.persist_case and bool(payload.product_id)
    return review_spec(
        payload.specification,
        pack=pack,
        stage="post_spec",
        knowledge=knowledge,
        persist_case=persist,
        product_id=payload.product_id,
        case_metadata={"category": payload.category},
    )


class ImplReviewRequest(BaseModel):
    """Body for the ad-hoc post-implementation review endpoint."""

    idea: str = ""
    category: Optional[str] = None
    specification: Optional[dict[str, Any]] = None
    forced_domain_id: Optional[str] = None
    persist_case: bool = True


@router.post("/review/implementation/{product_id}")
async def review_implementation_endpoint(product_id: str, payload: ImplReviewRequest) -> dict[str, Any]:
    """``POST /api/admin/methodology/review/implementation/{product_id}`` — re-review code on demand."""
    if payload.forced_domain_id:
        pack = get_domain_pack(payload.forced_domain_id)
    else:
        pack = select_domain_pack(payload.idea, category=payload.category, spec=payload.specification)
    knowledge = _store()
    code_dir = Path(default_data_root()) / "code" / product_id
    return review_implementation(
        code_dir,
        pack=pack,
        spec=payload.specification,
        stage="post_implementation",
        knowledge=knowledge,
        persist_case=payload.persist_case,
        product_id=product_id,
        case_metadata={"category": payload.category},
    )


# --------------------------------------------------------------------- cases


@router.get("/cases/{product_id}")
async def get_cases(product_id: str) -> dict[str, Any]:
    """``GET /api/admin/methodology/cases/{product_id}`` — full review history for one product."""
    cases = _store().get_case_history(product_id)
    return {"product_id": product_id, "history": [c.to_dict() for c in cases]}


# --------------------------------------------------------------------- lessons


class LessonCreate(BaseModel):
    """Body for :func:`create_lesson` — fields mirror :class:`MethodologyLesson`."""

    domain: str = "*"
    title: str
    detail: str
    severity: str = "medium"
    keywords: list[str] = Field(default_factory=list)
    regex: list[str] = Field(default_factory=list)
    applies_to: list[str] = Field(default_factory=lambda: ["spec", "implementation"])
    fix_hint: str = ""
    weight: float = 1.0
    enabled: bool = True


class LessonUpdate(BaseModel):
    """Body for :func:`update_lesson` — every field is optional (PATCH semantics)."""

    domain: Optional[str] = None
    title: Optional[str] = None
    detail: Optional[str] = None
    severity: Optional[str] = None
    keywords: Optional[list[str]] = None
    regex: Optional[list[str]] = None
    applies_to: Optional[list[str]] = None
    fix_hint: Optional[str] = None
    weight: Optional[float] = None
    enabled: Optional[bool] = None


@router.get("/lessons")
async def list_lessons(
    domain: Optional[str] = Query(default=None),
    enabled_only: bool = Query(default=False),
    applies_to: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """``GET /api/admin/methodology/lessons`` — list lessons, with optional filters."""
    lessons = _store().list_lessons(domain=domain, enabled_only=enabled_only, applies_to=applies_to)
    return {"lessons": [l.to_dict() for l in lessons], "count": len(lessons)}


@router.post("/lessons")
async def create_lesson(payload: LessonCreate, admin=Depends(require_admin_with_rbac)) -> dict[str, Any]:
    """``POST /api/admin/methodology/lessons`` — add a new operator-supplied lesson."""
    import uuid

    lesson = MethodologyLesson(
        id=uuid.uuid4().hex[:12],
        domain=payload.domain or "*",
        severity=payload.severity or "medium",
        title=payload.title,
        detail=payload.detail,
        fix_hint=payload.fix_hint or "",
        keywords=list(payload.keywords or []),
        regex=list(payload.regex or []),
        applies_to=list(payload.applies_to or ["spec", "implementation"]),
        source="operator",
        weight=float(payload.weight or 1.0),
        enabled=bool(payload.enabled),
    )
    return _store().add_lesson(lesson).to_dict()


@router.patch("/lessons/{lesson_id}")
async def update_lesson(lesson_id: str, payload: LessonUpdate) -> dict[str, Any]:
    """``PATCH /api/admin/methodology/lessons/{id}`` — partial edit of a lesson."""
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    updated = _store().update_lesson(lesson_id, **changes)
    if updated is None:
        raise HTTPException(status_code=404, detail="lesson not found")
    return updated.to_dict()


@router.delete("/lessons/{lesson_id}")
async def delete_lesson(lesson_id: str) -> dict[str, Any]:
    """``DELETE /api/admin/methodology/lessons/{id}`` — remove a lesson by id."""
    ok = _store().delete_lesson(lesson_id)
    if not ok:
        raise HTTPException(status_code=404, detail="lesson not found")
    return {"deleted": lesson_id}


# --------------------------------------------------------------------- search


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Free-text query"),
    domain: Optional[str] = Query(default=None),
    kinds: str = Query(default="lessons,cases"),
    limit: int = Query(default=25, ge=1, le=200),
) -> dict[str, Any]:
    """``GET /api/admin/methodology/search`` — substring search over lessons and cases.

    ``kinds`` is a comma-separated subset of ``lessons,cases``; defaults to both.
    """
    parts = tuple(k.strip() for k in (kinds or "").split(",") if k.strip())
    if not parts:
        parts = ("lessons", "cases")
    return _store().search(q, domain=domain, kinds=parts, limit=limit)


# --------------------------------------------------------------------- feedback


class FeedbackPayload(BaseModel):
    """Body for :func:`feedback` — see :meth:`MethodologyKnowledgeStore.record_feedback`."""

    case_id: str
    product_id: str
    was_correct: bool
    notes: str = ""
    promote_finding_code: Optional[str] = None
    actor: str = "operator"


@router.post("/feedback")
async def feedback(payload: FeedbackPayload) -> dict[str, Any]:
    """``POST /api/admin/methodology/feedback`` — record operator feedback on a case.

    When ``was_correct`` is ``True`` and ``promote_finding_code`` is supplied,
    the matching finding is automatically converted into a lesson scoped to
    that domain so similar future products fail the gate faster.
    """
    return _store().record_feedback(
        case_id=payload.case_id,
        product_id=payload.product_id,
        was_correct=payload.was_correct,
        notes=payload.notes,
        promote_finding_code=payload.promote_finding_code,
        actor=payload.actor,
    )
