"""
Methodology knowledge store — persistent memory for the Methodology Agent.

Stores three kinds of records under ``data_root/methodology/``:

* ``lessons.jsonl``   — pluggable rules ("learned red flags") that augment
  built-in domain packs. Each lesson has a domain (or '*' for global), a
  trigger expressed as keywords / regex, a severity, advice and provenance.
  Lessons are applied on top of heuristic findings during every review.
* ``cases/<product_id>.json`` — full review history per product (spec +
  implementation reviews + outcome). Used for search ("how did similar
  products fail?") and for ``learn_from_feedback`` to convert recurring
  patterns into lessons.
* ``feedback.jsonl`` — operator feedback (`was_correct=True/False`,
  optional auto-promote into a lesson).

Storage format is plain JSON / JSONL so it is easy to inspect, version,
migrate and back up. There is no DB requirement.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


from core.paths import resolve_data_root
from core.logging_utils import log_suppressed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class MethodologyLesson:
    """A learned methodology rule that augments built-in domain packs.

    Lessons are evaluated by the heuristic engine on top of pack-level red
    flags. They support both keyword and regex matchers and can be scoped to
    a specific domain (``domain_id``) or globally (``domain="*"``). Lessons
    can come from three sources:

    * ``operator`` — manually added by an admin via the UI / API,
    * ``auto`` — auto-promoted from confirmed feedback on a past case,
    * ``import`` — bulk-imported from another deployment.
    """

    #: Stable id (12-char hex when auto-generated).
    id: str
    #: Either an exact ``domain_id`` (e.g. ``helpdesk_support``) or ``"*"`` for global.
    domain: str
    #: ``"high" | "medium" | "low"`` — high-severity lessons block the gate.
    severity: str
    #: Short label shown in admin UI.
    title: str
    #: Operator-facing description of the anti-pattern / rule.
    detail: str
    #: Suggested remediation, surfaced as ``fix_hint`` on the resulting finding.
    fix_hint: str = ""
    #: Lower-cased substrings that fire the lesson when found in the source.
    keywords: list[str] = field(default_factory=list)
    #: Regex patterns evaluated case-insensitively, multiline.
    regex: list[str] = field(default_factory=list)
    #: Stages this lesson applies to: any subset of ``["spec", "implementation"]``.
    applies_to: list[str] = field(default_factory=lambda: ["spec", "implementation"])
    #: Provenance: ``operator`` | ``auto`` | ``import``.
    source: str = "operator"
    #: Reserved for future weighted scoring; currently informational.
    weight: float = 1.0
    #: Allow operators to disable a lesson without deleting it.
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    #: When auto-promoted, the case ids that triggered the promotion.
    related_case_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-friendly dict (used in the JSONL store and admin API)."""
        return {
            "id": self.id,
            "domain": self.domain,
            "severity": self.severity,
            "title": self.title,
            "detail": self.detail,
            "fix_hint": self.fix_hint,
            "keywords": list(self.keywords),
            "regex": list(self.regex),
            "applies_to": list(self.applies_to),
            "source": self.source,
            "weight": float(self.weight),
            "enabled": bool(self.enabled),
            "created_at": float(self.created_at),
            "updated_at": float(self.updated_at),
            "related_case_ids": list(self.related_case_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MethodologyLesson":
        """Build a lesson from a dict (lenient — unknown / missing fields use defaults)."""
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:12]),
            domain=str(data.get("domain") or "*"),
            severity=str(data.get("severity") or "medium").lower(),
            title=str(data.get("title") or ""),
            detail=str(data.get("detail") or ""),
            fix_hint=str(data.get("fix_hint") or ""),
            keywords=[str(k) for k in (data.get("keywords") or []) if k],
            regex=[str(r) for r in (data.get("regex") or []) if r],
            applies_to=[str(a) for a in (data.get("applies_to") or ["spec", "implementation"])],
            source=str(data.get("source") or "operator"),
            weight=float(data.get("weight") or 1.0),
            enabled=bool(data.get("enabled", True)),
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            related_case_ids=[str(c) for c in (data.get("related_case_ids") or [])],
        )

    def matches(self, blob: str, *, stage: str) -> bool:
        """Return ``True`` when this lesson fires for the given source blob.

        ``stage`` is one of ``"spec"`` / ``"implementation"`` and is checked
        against :attr:`applies_to`. Disabled lessons never match.
        """
        if not self.enabled:
            return False
        if self.applies_to and stage not in self.applies_to:
            return False
        text = (blob or "").lower()
        for kw in self.keywords:
            if kw and kw.lower() in text:
                return True
        for pat in self.regex:
            try:
                if re.search(pat, blob or "", re.I | re.M):
                    return True
            except re.error:
                continue
        return False


@dataclass
class MethodologyCase:
    """Persistent record of one methodology review for a product.

    Cases are append-only history rows: each ``review_spec`` /
    ``review_implementation`` invocation that opts into persistence stores
    one case under ``cases/<product_id>.json``. Cases carry the full set of
    findings and the operator feedback (if any) so the agent has memory of
    past reviews and can answer "how did similar products fail?".
    """

    case_id: str
    product_id: str
    #: ``"post_spec"`` or ``"post_implementation"``.
    stage: str
    domain: Optional[str]
    #: 0..100 coverage score from the heuristic engine.
    score: Optional[int]
    passed: bool
    #: Findings emitted by the engine (severity, code, detail, fix_hint).
    findings: list[dict[str, Any]] = field(default_factory=list)
    #: Free-form metadata such as ``category`` and ``delivery_profile``.
    metadata: dict[str, Any] = field(default_factory=dict)
    #: Operator feedback (set later via :meth:`MethodologyKnowledgeStore.record_feedback`).
    feedback: Optional[dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the JSON shape stored in ``cases/<product_id>.json``."""
        return {
            "case_id": self.case_id,
            "product_id": self.product_id,
            "stage": self.stage,
            "domain": self.domain,
            "score": self.score,
            "passed": self.passed,
            "findings": list(self.findings),
            "metadata": dict(self.metadata),
            "feedback": dict(self.feedback) if self.feedback else None,
            "created_at": float(self.created_at),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MethodologyCase":
        """Reverse of :meth:`to_dict`; tolerates missing / unexpected fields."""
        return cls(
            case_id=str(data.get("case_id") or uuid.uuid4().hex[:12]),
            product_id=str(data.get("product_id") or ""),
            stage=str(data.get("stage") or "post_implementation"),
            domain=(data.get("domain") if data.get("domain") is None else str(data.get("domain"))),
            score=(int(data["score"]) if data.get("score") is not None else None),
            passed=bool(data.get("passed", False)),
            findings=list(data.get("findings") or []),
            metadata=dict(data.get("metadata") or {}),
            feedback=dict(data["feedback"]) if isinstance(data.get("feedback"), dict) else None,
            created_at=float(data.get("created_at") or time.time()),
        )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class MethodologyKnowledgeStore:
    """Filesystem-backed knowledge store for the methodologist.

    Storage layout under ``${data_root}/methodology/``::

        lessons.jsonl                   # one MethodologyLesson per line
        feedback.jsonl                  # operator feedback log
        cases/<product_id>.json         # append-only review history per product

    The store is intentionally plain JSON / JSONL: easy to inspect, version,
    migrate and back up; no DB requirement and no schema migrations.
    """

    def __init__(self, data_root: Optional[str | Path] = None) -> None:
        """Create the on-disk layout under :func:`_resolve_data_root` (idempotent)."""
        self.data_root = resolve_data_root(data_root)
        self.base = self.data_root / "methodology"
        self.cases_dir = self.base / "cases"
        self.lessons_path = self.base / "lessons.jsonl"
        self.feedback_path = self.base / "feedback.jsonl"
        self.base.mkdir(parents=True, exist_ok=True)
        self.cases_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- lessons -------------------------------------------------

    def add_lesson(self, lesson: MethodologyLesson) -> MethodologyLesson:
        """Append a lesson to ``lessons.jsonl`` and return it (id auto-generated if missing)."""
        if not lesson.id:
            lesson.id = uuid.uuid4().hex[:12]
        lesson.updated_at = time.time()
        with self.lessons_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(lesson.to_dict(), ensure_ascii=False) + "\n")
        return lesson

    def update_lesson(self, lesson_id: str, **changes: Any) -> Optional[MethodologyLesson]:
        """Edit a lesson in place by id; returns the new value or ``None`` if not found.

        Implementation reads the JSONL, replaces the matching record, and atomically
        rewrites the file via :meth:`_rewrite_lessons`. Suitable for the small
        number of lessons a deployment typically holds.
        """
        lessons = list(self.iter_lessons())
        updated: Optional[MethodologyLesson] = None
        for i, lesson in enumerate(lessons):
            if lesson.id == lesson_id:
                payload = lesson.to_dict()
                payload.update(changes)
                payload["updated_at"] = time.time()
                lessons[i] = MethodologyLesson.from_dict(payload)
                updated = lessons[i]
                break
        if updated is None:
            return None
        self._rewrite_lessons(lessons)
        return updated

    def delete_lesson(self, lesson_id: str) -> bool:
        """Remove a lesson by id; returns ``True`` when something was deleted."""
        lessons = [l for l in self.iter_lessons() if l.id != lesson_id]
        if len(lessons) == len(list(self.iter_lessons())):
            return False
        self._rewrite_lessons(lessons)
        return True

    def iter_lessons(self) -> Iterator[MethodologyLesson]:
        """Yield all lessons from ``lessons.jsonl``; corrupt rows are skipped silently."""
        if not self.lessons_path.is_file():
            return
        with self.lessons_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield MethodologyLesson.from_dict(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

    def list_lessons(
        self,
        *,
        domain: Optional[str] = None,
        enabled_only: bool = False,
        applies_to: Optional[str] = None,
    ) -> list[MethodologyLesson]:
        """Filtered view over all lessons.

        * ``domain``       – ``None`` returns all; otherwise ``domain`` and ``"*"`` (global) match.
        * ``enabled_only`` – drop lessons with ``enabled=False``.
        * ``applies_to``   – ``"spec"`` or ``"implementation"`` – stage filter.
        """
        out: list[MethodologyLesson] = []
        for lesson in self.iter_lessons():
            if enabled_only and not lesson.enabled:
                continue
            if applies_to and applies_to not in lesson.applies_to:
                continue
            if domain and lesson.domain not in (domain, "*"):
                continue
            out.append(lesson)
        return out

    def find_lessons_for(self, blob: str, *, domain: Optional[str], stage: str) -> list[MethodologyLesson]:
        """Return the subset of lessons that fire on the given source blob."""
        return [
            l for l in self.list_lessons(domain=domain, enabled_only=True, applies_to=stage)
            if l.matches(blob, stage=stage)
        ]

    def _rewrite_lessons(self, lessons: Iterable[MethodologyLesson]) -> None:
        """Atomically rewrite ``lessons.jsonl`` (write to ``.tmp`` then ``rename``)."""
        tmp = self.lessons_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fp:
            for lesson in lessons:
                fp.write(json.dumps(lesson.to_dict(), ensure_ascii=False) + "\n")
        tmp.replace(self.lessons_path)

    # ---------------- cases ---------------------------------------------------

    def case_path(self, product_id: str) -> Path:
        """Return the on-disk path for the given product's case history file."""
        return self.cases_dir / f"{product_id}.json"

    def append_case(self, case: MethodologyCase) -> MethodologyCase:
        """Append a review case to ``cases/<product_id>.json`` (creates the file if needed)."""
        path = self.case_path(case.product_id)
        history: list[dict[str, Any]] = []
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                history = list(payload.get("history") or [])
            except (OSError, json.JSONDecodeError):
                history = []
        history.append(case.to_dict())
        payload = {"product_id": case.product_id, "history": history}
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return case

    def get_case_history(self, product_id: str) -> list[MethodologyCase]:
        """Read the chronological case history for one product (empty list if absent)."""
        path = self.case_path(product_id)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [MethodologyCase.from_dict(c) for c in payload.get("history") or []]

    def iter_cases(self) -> Iterator[MethodologyCase]:
        """Iterate over every case across every product (used by full-store search)."""
        for path in sorted(self.cases_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            for raw in payload.get("history") or []:
                if isinstance(raw, dict):
                    yield MethodologyCase.from_dict(raw)

    # ---------------- search / learning --------------------------------------

    def search(
        self,
        query: str,
        *,
        domain: Optional[str] = None,
        kinds: tuple[str, ...] = ("lessons", "cases"),
        limit: int = 25,
    ) -> dict[str, list[dict[str, Any]]]:
        """Substring search across lessons and review cases.

        Returns a dict ``{"lessons": [...], "cases": [...]}`` of matching
        records (already serialised to plain dicts). ``kinds`` lets callers
        restrict the search to one bucket; ``domain`` filters by ``domain_id``.
        """
        q = (query or "").strip().lower()
        results: dict[str, list[dict[str, Any]]] = {"lessons": [], "cases": []}
        if not q:
            return results

        if "lessons" in kinds:
            for lesson in self.list_lessons(domain=domain):
                hay = " ".join(
                    [
                        lesson.title,
                        lesson.detail,
                        lesson.fix_hint,
                        lesson.domain,
                        lesson.severity,
                        " ".join(lesson.keywords),
                        " ".join(lesson.regex),
                    ]
                ).lower()
                if q in hay:
                    results["lessons"].append(lesson.to_dict())
                if len(results["lessons"]) >= limit:
                    break

        if "cases" in kinds:
            for case in self.iter_cases():
                if domain and (case.domain or "") != domain:
                    continue
                hay_parts: list[str] = [
                    case.product_id,
                    case.stage,
                    str(case.domain or ""),
                    str(case.score or ""),
                ]
                for f in case.findings:
                    if isinstance(f, dict):
                        hay_parts.append(str(f.get("code") or ""))
                        hay_parts.append(str(f.get("detail") or ""))
                hay = " ".join(hay_parts).lower()
                if q in hay:
                    results["cases"].append(case.to_dict())
                if len(results["cases"]) >= limit:
                    break

        return results

    # ---------------- feedback / learn-from-feedback -------------------------

    def record_feedback(
        self,
        *,
        case_id: str,
        product_id: str,
        was_correct: bool,
        notes: str = "",
        promote_finding_code: Optional[str] = None,
        actor: str = "operator",
    ) -> dict[str, Any]:
        """
        Persist operator feedback on a case. When ``promote_finding_code`` is
        supplied and the feedback says the gate was correct, the corresponding
        finding is auto-promoted into a learned lesson so the rule fires faster
        on similar future products.
        """
        entry = {
            "id": uuid.uuid4().hex[:12],
            "case_id": case_id,
            "product_id": product_id,
            "was_correct": bool(was_correct),
            "notes": str(notes or "").strip()[:1000],
            "promote_finding_code": str(promote_finding_code or "").strip() or None,
            "actor": str(actor or "operator"),
            "created_at": time.time(),
        }
        with self.feedback_path.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Update the case in-place so admins can see feedback alongside review.
        case_path = self.case_path(product_id)
        if case_path.is_file():
            try:
                payload = json.loads(case_path.read_text(encoding="utf-8"))
                history = payload.get("history") or []
                for case in history:
                    if isinstance(case, dict) and case.get("case_id") == case_id:
                        case["feedback"] = {
                            "was_correct": bool(was_correct),
                            "notes": entry["notes"],
                            "actor": entry["actor"],
                            "created_at": entry["created_at"],
                        }
                        break
                case_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            except (OSError, json.JSONDecodeError) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (web/backend/services/methodology_knowledge.py)", exc_info=_suppressed_exc)

        promoted_lesson: Optional[MethodologyLesson] = None
        if was_correct and entry["promote_finding_code"]:
            promoted_lesson = self._auto_promote_lesson(
                case_id=case_id,
                product_id=product_id,
                finding_code=entry["promote_finding_code"],
                actor=actor,
            )
        entry["promoted_lesson_id"] = promoted_lesson.id if promoted_lesson else None
        return entry

    def _auto_promote_lesson(
        self,
        *,
        case_id: str,
        product_id: str,
        finding_code: str,
        actor: str,
    ) -> Optional[MethodologyLesson]:
        """Convert a confirmed finding into a learned lesson.

        Used by :meth:`record_feedback` when the operator says "this gate was
        right, make it stick". We pull the original finding from the case,
        extract a few keyword candidates from its ``detail`` text, and store a
        new ``source="auto"`` lesson scoped to the same domain and stage.
        """
        case_path = self.case_path(product_id)
        if not case_path.is_file():
            return None
        try:
            payload = json.loads(case_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        target_case: Optional[dict[str, Any]] = None
        for c in payload.get("history") or []:
            if isinstance(c, dict) and c.get("case_id") == case_id:
                target_case = c
                break
        if not target_case:
            return None
        finding: Optional[dict[str, Any]] = None
        for f in target_case.get("findings") or []:
            if isinstance(f, dict) and str(f.get("code")) == finding_code:
                finding = f
                break
        if not finding:
            return None
        domain = str(target_case.get("domain") or "*")
        keywords = []
        for tok in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{3,}", str(finding.get("detail") or ""))[:6]:
            keywords.append(tok.lower())
        lesson = MethodologyLesson(
            id=uuid.uuid4().hex[:12],
            domain=domain,
            severity=str(finding.get("severity") or "medium").lower(),
            title=f"Learned: {finding.get('code', 'methodology_finding')}",
            detail=str(finding.get("detail") or ""),
            fix_hint=str(finding.get("fix_hint") or ""),
            keywords=keywords,
            regex=[],
            applies_to=[str(target_case.get("stage") or "post_implementation").replace("post_", "")],
            source="auto",
            weight=0.8,
            enabled=True,
            related_case_ids=[case_id],
        )
        # Normalise applies_to (post_spec -> spec, post_implementation -> implementation)
        norm = []
        for a in lesson.applies_to:
            if a in ("spec", "post_spec"):
                norm.append("spec")
            elif a in ("implementation", "post_implementation"):
                norm.append("implementation")
            else:
                norm.append(a)
        lesson.applies_to = norm or ["implementation"]
        return self.add_lesson(lesson)
