"""
Methodology review engine (v2).

Two checkpoints:

* ``review_spec(spec, pack=...)`` — methodology check on a PM specification.
* ``review_implementation(code_dir, pack=...)`` — methodology check on the
  generated code (post-developer / post-QA).

What changed vs v1:

* Uses the rich domain pack schema (entities + fields, lifecycle states **and**
  transitions, acceptance scenarios, API endpoints, KPIs, red-flag patterns).
* Optional ``MethodologyKnowledgeStore`` injects learned lessons (extra red
  flags) on top of built-in checks.
* Each review can persist a ``MethodologyCase`` so the agent has memory.

Returns a uniform report::

    {
        "stage": "post_spec" | "post_implementation",
        "domain": str | None,
        "domain_label": str,
        "score": int,            # 0..100
        "min_score": int,
        "passed": bool,
        "checks": {
            "entities":       {"present": [...], "missing": [...]},
            "roles":          {...},
            "capabilities":   {...},
            "lifecycle":      {...},
            "lifecycle_transitions": {"present": [...], "missing": [...]},
            "api_endpoints":  {"present": [...], "missing": [...]},  # impl only
            "acceptance":     {"present": [...], "missing": [...]},
            "red_flags":      {"hits": [...]},
        },
        "findings": [
            {"severity": "high|medium|low", "code": "...", "detail": "...", "fix_hint": "..."}
        ],
        "lessons_applied": [ ... lesson ids ... ],
        "case_id": str,         # written when a knowledge store is attached
    }
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

from web.backend.services.domain_methodology.base import (
    AcceptanceScenario,
    ApiEndpoint,
    DomainEntity,
    DomainPack,
    LifecycleState,
    LifecycleTransition,
    RedFlagPattern,
)
from web.backend.services.methodology_knowledge import (
    MethodologyCase,
    MethodologyKnowledgeStore,
    MethodologyLesson,
)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_TEXT_ARTIFACT_SUFFIXES = {
    ".html", ".htm", ".css", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".json", ".yml", ".yaml", ".toml", ".md", ".txt", ".py", ".sql",
}
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist-info"}


def _normalize(text: str) -> str:
    """Lowercase and strip everything except letters, digits, spaces, slashes, dashes, underscores."""
    return re.sub(r"[^a-z0-9 /_-]+", " ", (text or "").lower()).strip()


def _term_aliases(name: str, aliases: Iterable[str] = ()) -> tuple[str, ...]:
    """Return ``(name, *aliases)`` — small helper used when we need a flat tuple."""
    return (name,) + tuple(aliases)


def _term_matches(blob: str, term: str) -> bool:
    """Fuzzy term match: exact, slash/underscore-separated, or first-two-tokens substring."""
    norm = _normalize(term)
    if not norm:
        return False
    if norm in blob:
        return True
    for alt in (norm.replace("/", " "), norm.replace("-", " "), norm.replace("_", " ")):
        if alt in blob:
            return True
    primary = [t for t in norm.split() if len(t) >= 3]
    if not primary:
        return False
    return all(t in blob for t in primary[:2])


def _any_alias_matches(blob: str, aliases: Iterable[str]) -> bool:
    """Return ``True`` when at least one alias passes :func:`_term_matches`."""
    return any(_term_matches(blob, a) for a in aliases if a)


def _spec_inner(spec: Any) -> dict:
    """Unwrap the ``{"specification": {...}}`` envelope produced by some PM outputs."""
    if isinstance(spec, dict) and isinstance(spec.get("specification"), dict):
        return spec["specification"]
    return spec if isinstance(spec, dict) else {}


def _spec_blob(spec: Any) -> str:
    """Flatten a spec dict into a normalised lower-cased blob.

    Pulls only the human-readable fields that carry methodology signal
    (description, features, requirements, user stories) — the rest is noise.
    The result is the input both :func:`_term_matches` and red-flag matchers
    operate on.
    """
    parts: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, list):
            for v in value:
                _add(v)
        elif isinstance(value, dict):
            for v in value.values():
                _add(v)

    inner = _spec_inner(spec)
    for key in (
        "product_name", "description", "category",
        "core_features", "functional_requirements", "non_functional_requirements",
        "user_stories", "personas", "tags", "target_audience", "domain",
    ):
        if key in inner:
            _add(inner[key])
    return _normalize(" \n ".join(parts))


def _iter_code_artifacts(code_dir: Path) -> Iterable[tuple[str, str]]:
    """Yield ``(relative_path, file_text)`` for every text artifact under ``code_dir``.

    Skips git/node_modules/venv directories and binary suffixes; reads files as
    UTF-8 with replacement to avoid choking on stray bytes.
    """
    if not code_dir or not code_dir.is_dir():
        return
    for p in sorted(code_dir.rglob("*")):
        if not p.is_file():
            continue
        if any(part in _SKIP_PARTS for part in p.parts):
            continue
        if p.suffix.lower() not in _TEXT_ARTIFACT_SUFFIXES:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        try:
            rel = p.relative_to(code_dir).as_posix()
        except ValueError:
            rel = p.name
        yield rel, text


def _code_blob(code_dir: Path) -> tuple[str, str]:
    """Return ``(normalized_lower_blob, raw_concat)`` for the code directory.

    The normalised blob feeds keyword/term matching; the raw concatenation
    keeps casing and punctuation so regex-based red-flag and API-shape matching
    works correctly (e.g. preserving ``POST /api/tickets`` literals).
    """
    raw_chunks: list[str] = []
    for _rel, text in _iter_code_artifacts(code_dir) or []:
        raw_chunks.append(text)
    raw = " \n ".join(raw_chunks)
    return _normalize(raw), raw


# ---------------------------------------------------------------------------
# Per-axis evaluation
# ---------------------------------------------------------------------------

_AXIS_WEIGHTS = {
    "entities": 0.22,
    "capabilities": 0.22,
    "lifecycle": 0.16,
    "lifecycle_transitions": 0.10,
    "roles": 0.08,
    "acceptance": 0.10,
    "api": 0.12,  # only really used by implementation reviews
}


def _axis_eval_named(blob: str, items: Iterable[tuple[str, tuple[str, ...]]]) -> tuple[list[str], list[str]]:
    """Evaluate one axis from a list of ``(name, aliases)`` pairs.

    Returns ``(present, missing)`` lists of names — the standard shape that
    every axis on the report uses.
    """
    present: list[str] = []
    missing: list[str] = []
    for name, aliases in items:
        if _any_alias_matches(blob, aliases):
            present.append(name)
        else:
            missing.append(name)
    return present, missing


def _axis_eval_simple(blob: str, terms: Iterable[str]) -> tuple[list[str], list[str]]:
    """Convenience wrapper for axes where each term has no aliases."""
    return _axis_eval_named(blob, [(t, (t,)) for t in terms if t])


def _eval_lifecycle(blob: str, states: tuple[LifecycleState, ...]) -> tuple[list[str], list[str]]:
    """Map a list of :class:`LifecycleState` instances onto the standard axis output."""
    return _axis_eval_named(blob, [(s.name, s.all_aliases()) for s in states])


def _eval_lifecycle_transitions(
    blob: str, transitions: tuple[LifecycleTransition, ...]
) -> tuple[list[str], list[str]]:
    """Score the lifecycle *graph*, not just its nodes.

    A transition is "present" when both endpoints appear in the source AND a
    motion verb (``move``, ``advance``, ``->`` …) is present, or when the
    explicit transition label appears verbatim. This keeps simple state-name
    enumerations from inflating the lifecycle score.
    """
    present: list[str] = []
    missing: list[str] = []
    for t in transitions:
        endpoints_present = _term_matches(blob, t.from_state) and _term_matches(blob, t.to_state)
        label_present = bool(t.label) and _term_matches(blob, t.label)
        verb_present = bool(re.search(r"\b(move|advance|transition|change\s*status|step|progress|->|=>)\b", blob))
        key = f"{t.from_state} -> {t.to_state}"
        if (endpoints_present and verb_present) or label_present:
            present.append(key)
        else:
            missing.append(key)
    return present, missing


def _eval_acceptance(blob: str, scenarios: tuple[AcceptanceScenario, ...]) -> tuple[list[str], list[str]]:
    """Score acceptance scenarios by title match OR step-keyword overlap.

    A scenario is considered covered when its title is present in the source,
    or when at least half of its steps share salient keywords (≥ 5 chars) with
    the source text.
    """
    present: list[str] = []
    missing: list[str] = []
    for s in scenarios:
        title_present = _term_matches(blob, s.title)
        step_hits = 0
        for step in s.steps:
            tokens = [t for t in _normalize(step).split() if len(t) >= 5]
            if tokens and any(t in blob for t in tokens[:2]):
                step_hits += 1
        ratio_ok = bool(s.steps) and step_hits / max(1, len(s.steps)) >= 0.5
        if title_present or ratio_ok:
            present.append(s.id)
        else:
            missing.append(s.id)
    return present, missing


def _eval_api(raw_text: str, endpoints: tuple[ApiEndpoint, ...]) -> tuple[list[str], list[str]]:
    """Detect required API endpoints in raw source text.

    For each endpoint we accept three positive signals:

    * ``METHOD`` followed within ~200 chars by the path pattern,
    * a FastAPI/Flask-style decorator ``@router.get("/path")``,
    * a literal occurrence of the path pattern inside a string / call site.

    Path placeholders such as ``{id}`` are normalised so that real values
    (e.g. ``/api/tickets/42``) also match.
    """
    present: list[str] = []
    missing: list[str] = []
    if not raw_text:
        return present, [f"{e.method} {e.path_pattern}" for e in endpoints]
    for e in endpoints:
        path_re = re.escape(e.path_pattern).replace(r"\{id\}", r"[^\"'\s)]+").replace(r"\{[^}]+\}", r"[^\"'\s)]+")
        # Either "METHOD path" appears (FastAPI / Flask decorators), or the path
        # alone appears in client / docs code.
        method = e.method.upper()
        method_re = re.compile(
            rf'(?:["\'\(\s]){path_re}(?:["\'\)\s])',
            re.I,
        )
        method_with_verb = re.compile(
            rf"\b{method}\b[^\n]{{0,200}}{path_re}",
            re.I,
        )
        decorator_re = re.compile(
            rf'@\w+\.(?:get|post|put|patch|delete)\s*\(\s*["\']{path_re}["\']',
            re.I,
        )
        if method_with_verb.search(raw_text) or decorator_re.search(raw_text) or method_re.search(raw_text):
            present.append(f"{method} {e.path_pattern}")
        else:
            missing.append(f"{method} {e.path_pattern}")
    return present, missing


# ---------------------------------------------------------------------------
# Red flags (built-in pack + learned lessons)
# ---------------------------------------------------------------------------


def _eval_red_flags(
    raw_text: str,
    *,
    pack: Optional[DomainPack],
    lessons: list[MethodologyLesson],
    stage: str,
) -> list[dict[str, Any]]:
    """Evaluate built-in pack red flags and learned lessons against the source.

    Returns a flat list of hit descriptors with ``source="pack"`` or
    ``source="lesson"`` so :func:`_build_findings` can encode them with the
    correct finding code (``red_flag:<id>`` vs ``methodology_learned_red_flag``).
    """
    hits: list[dict[str, Any]] = []
    if pack is not None:
        for rf in pack.red_flags:
            if _red_flag_matches(rf, raw_text):
                hits.append(
                    {
                        "source": "pack",
                        "id": rf.id,
                        "severity": rf.severity,
                        "description": rf.description,
                        "fix_hint": rf.fix_hint,
                    }
                )
    for lesson in lessons:
        if lesson.matches(raw_text, stage=stage):
            hits.append(
                {
                    "source": "lesson",
                    "id": lesson.id,
                    "severity": lesson.severity,
                    "description": lesson.title or lesson.detail,
                    "detail": lesson.detail,
                    "fix_hint": lesson.fix_hint,
                }
            )
    return hits


def _red_flag_matches(rf: RedFlagPattern, raw_text: str) -> bool:
    """Return ``True`` if any of the red flag's keywords (lowercased) or regex matches."""
    if not raw_text:
        return False
    blob_lc = raw_text.lower()
    for kw in rf.keywords:
        if kw and kw.lower() in blob_lc:
            return True
    for pat in rf.compiled_regex():
        if pat.search(raw_text):
            return True
    return False


# ---------------------------------------------------------------------------
# Coverage score
# ---------------------------------------------------------------------------


def _coverage_score(checks: dict[str, dict[str, list[str]]]) -> int:
    """Compute the weighted 0..100 coverage score from per-axis present/missing.

    The weights live in :data:`_AXIS_WEIGHTS`. Axes with zero items are
    excluded from both the numerator and denominator (so missing API contracts
    don't penalise a spec-stage review).
    """
    total_weight = 0.0
    score = 0.0
    for axis, weight in _AXIS_WEIGHTS.items():
        ax = checks.get(axis) or {}
        present = ax.get("present") or []
        missing = ax.get("missing") or []
        total = len(present) + len(missing)
        if total <= 0:
            continue
        score += weight * (len(present) / total)
        total_weight += weight
    if total_weight <= 0:
        return 0
    return int(round((score / total_weight) * 100))


# ---------------------------------------------------------------------------
# Core review function
# ---------------------------------------------------------------------------


def _build_findings(
    *,
    pack: Optional[DomainPack],
    checks: dict[str, dict[str, list[str]]],
    red_flag_hits: list[dict[str, Any]],
    score: int,
    min_score: int,
    stage: str,
) -> tuple[list[dict], bool]:
    """Compose the final ``(findings, passed)`` tuple from per-axis stats and red flags.

    The ``passed`` boolean is ``score >= min_score AND no high-severity findings``.
    A virtual high-severity ``domain_methodology_below_threshold`` finding is
    inserted at the top whenever the score is sub-threshold, so the operator
    sees a single clear reason for the rejection.
    """
    findings: list[dict] = []

    def _emit(axis: str, code: str, label: str, severity: str, threshold: float) -> None:
        ax = checks.get(axis) or {}
        miss = ax.get("missing") or []
        present = ax.get("present") or []
        total = len(miss) + len(present)
        if total <= 0 or not miss:
            return
        ratio = len(miss) / total
        if ratio < threshold and severity != "high":
            return
        if severity == "high" and ratio < 0.25:
            return
        miss_sample = ", ".join(miss[:8])
        findings.append(
            {
                "severity": severity,
                "code": code,
                "detail": f"{label} not covered: {', '.join(miss[:6])}"
                + (" …" if len(miss) > 6 else ""),
                "fix_hint": (
                    f"Add explicit spec text (functional_requirements, user_stories, or description) "
                    f"that names and scopes each missing item for {(pack.label if pack else 'this domain')}: "
                    f"{miss_sample}."
                    + (" …" if len(miss) > 8 else "")
                ),
            }
        )

    _emit("entities", "domain_entity_missing", "Required entities", "high", 0.25)
    _emit("capabilities", "domain_capability_missing", "Required capabilities", "high", 0.25)
    _emit("lifecycle", "domain_lifecycle_missing", "Lifecycle states", "medium", 0.34)
    _emit("lifecycle_transitions", "domain_lifecycle_transition_missing", "Lifecycle transitions", "medium", 0.50)
    _emit("acceptance", "domain_acceptance_scenario_missing", "Acceptance scenarios", "medium", 0.50)
    _emit("api", "domain_api_endpoint_missing", "API endpoints", "high", 0.50)
    _emit("roles", "domain_role_missing", "User roles", "low", 0.34)

    for hit in red_flag_hits:
        sev = str(hit.get("severity") or "medium").lower()
        if sev not in ("high", "medium", "low"):
            sev = "medium"
        if hit.get("source") == "lesson":
            code = "methodology_learned_red_flag"
        else:
            code = f"red_flag:{hit.get('id', 'unknown')}"
        findings.append(
            {
                "severity": sev,
                "code": code,
                "detail": str(hit.get("description") or hit.get("detail") or "").strip()[:600],
                "fix_hint": str(hit.get("fix_hint") or "").strip()[:400],
                "source": hit.get("source"),
                "ref": hit.get("id"),
            }
        )

    if score < min_score:
        findings.insert(
            0,
            {
                "severity": "high",
                "code": "domain_methodology_below_threshold",
                "detail": (
                    f"Domain methodology coverage {score}/100 below minimum {min_score} "
                    f"({pack.label if pack else 'generic'}, stage={stage})."
                ),
                "fix_hint": (
                    "Refine the spec / implementation so the listed entities, capabilities, "
                    "lifecycle and API surfaces for this domain are explicitly present."
                ),
            },
        )

    has_high = any(f.get("severity") == "high" for f in findings)
    passed = score >= min_score and not has_high
    return findings, passed


def _evaluate(
    *,
    pack: Optional[DomainPack],
    blob: str,
    raw_text: str,
    knowledge: Optional[MethodologyKnowledgeStore],
    stage: str,
) -> dict[str, Any]:
    """Run all per-axis evaluators + red flags + lessons and return the raw result.

    Centralised so :func:`review_spec` and :func:`review_implementation` differ
    only in (a) what blob/raw_text they pass and (b) whether they evaluate the
    API axis (impl only). The function does not produce findings or scores by
    itself — it returns the building blocks for :func:`_build_findings` and
    :func:`_coverage_score`.
    """
    checks: dict[str, dict[str, list[str]]] = {}

    if pack is not None:
        ent_p, ent_m = _axis_eval_named(blob, [(e.name, e.all_aliases()) for e in pack.entities if e.required])
        cap_p, cap_m = _axis_eval_named(
            blob,
            [(c.label, c.all_aliases()) for c in pack.capabilities if c.severity == "high"],
        )
        role_p, role_m = _axis_eval_named(
            blob, [(r.name, r.all_aliases()) for r in pack.roles if r.required]
        )
        life_p, life_m = _eval_lifecycle(blob, pack.lifecycle_states)
        trans_p, trans_m = _eval_lifecycle_transitions(blob, pack.lifecycle_transitions)
        accept_p, accept_m = _eval_acceptance(blob, pack.acceptance_scenarios)
        if stage == "post_implementation":
            api_p, api_m = _eval_api(raw_text, pack.api_endpoints)
        else:
            api_p, api_m = ([], [])

        checks = {
            "entities": {"present": ent_p, "missing": ent_m},
            "capabilities": {"present": cap_p, "missing": cap_m},
            "roles": {"present": role_p, "missing": role_m},
            "lifecycle": {"present": life_p, "missing": life_m},
            "lifecycle_transitions": {"present": trans_p, "missing": trans_m},
            "acceptance": {"present": accept_p, "missing": accept_m},
            "api": {"present": api_p, "missing": api_m},
        }
    else:
        ent_p, ent_m = _axis_eval_simple(blob, ("user", "data record", "owner/role", "lifecycle/status"))
        cap_p, cap_m = _axis_eval_simple(blob, ("create", "list/search", "edit", "assign owner", "change status"))
        checks = {
            "entities": {"present": ent_p, "missing": ent_m},
            "capabilities": {"present": cap_p, "missing": cap_m},
            "roles": {"present": [], "missing": []},
            "lifecycle": {"present": [], "missing": []},
            "lifecycle_transitions": {"present": [], "missing": []},
            "acceptance": {"present": [], "missing": []},
            "api": {"present": [], "missing": []},
        }

    lessons_for_stage_kind = "spec" if stage == "post_spec" else "implementation"
    lessons: list[MethodologyLesson] = []
    if knowledge is not None:
        lessons = knowledge.list_lessons(
            domain=(pack.domain_id if pack else None),
            enabled_only=True,
            applies_to=lessons_for_stage_kind,
        )

    red_flag_hits = _eval_red_flags(raw_text, pack=pack, lessons=lessons, stage=lessons_for_stage_kind)

    score = _coverage_score(checks)
    return {
        "checks": checks,
        "score": score,
        "red_flag_hits": red_flag_hits,
        "lessons_applied": [h.get("id") for h in red_flag_hits if h.get("source") == "lesson"],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def review_spec(
    spec: dict,
    *,
    pack: Optional[DomainPack],
    stage: str = "post_spec",
    min_score: int = 60,
    knowledge: Optional[MethodologyKnowledgeStore] = None,
    persist_case: bool = False,
    product_id: Optional[str] = None,
    case_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    blob = _spec_blob(spec)
    raw_text = blob  # spec is already plain text
    base = _evaluate(pack=pack, blob=blob, raw_text=raw_text, knowledge=knowledge, stage="post_spec")
    findings, passed = _build_findings(
        pack=pack,
        checks=base["checks"],
        red_flag_hits=base["red_flag_hits"],
        score=int(base["score"]),
        min_score=min_score,
        stage=stage,
    )
    report = {
        "stage": stage,
        "domain": pack.domain_id if pack else None,
        "domain_label": pack.label if pack else "generic",
        "score": int(base["score"]),
        "min_score": min_score,
        "checks": base["checks"],
        "findings": findings,
        "lessons_applied": base["lessons_applied"],
        "passed": passed,
    }
    if persist_case and knowledge is not None and product_id:
        case = MethodologyCase(
            case_id=uuid.uuid4().hex[:12],
            product_id=product_id,
            stage=stage,
            domain=report["domain"],
            score=report["score"],
            passed=report["passed"],
            findings=report["findings"],
            metadata=case_metadata or {},
        )
        knowledge.append_case(case)
        report["case_id"] = case.case_id
    return report


def review_implementation(
    code_dir: Path,
    *,
    pack: Optional[DomainPack],
    spec: Optional[dict] = None,
    stage: str = "post_implementation",
    min_score: int = 55,
    knowledge: Optional[MethodologyKnowledgeStore] = None,
    persist_case: bool = False,
    product_id: Optional[str] = None,
    case_metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    code_path = Path(code_dir) if code_dir else None
    if code_path is None or not code_path.is_dir():
        return {
            "stage": stage,
            "domain": pack.domain_id if pack else None,
            "domain_label": pack.label if pack else "generic",
            "score": 0,
            "min_score": min_score,
            "checks": {},
            "findings": [
                {
                    "severity": "high",
                    "code": "domain_no_code",
                    "detail": "No generated code to evaluate methodology against.",
                    "fix_hint": "Run developer + QA stages so artifacts exist before the methodology gate.",
                }
            ],
            "lessons_applied": [],
            "passed": False,
        }
    blob, raw_text = _code_blob(code_path)
    base = _evaluate(
        pack=pack, blob=blob, raw_text=raw_text, knowledge=knowledge, stage="post_implementation"
    )
    findings, passed = _build_findings(
        pack=pack,
        checks=base["checks"],
        red_flag_hits=base["red_flag_hits"],
        score=int(base["score"]),
        min_score=min_score,
        stage=stage,
    )
    report = {
        "stage": stage,
        "domain": pack.domain_id if pack else None,
        "domain_label": pack.label if pack else "generic",
        "score": int(base["score"]),
        "min_score": min_score,
        "checks": base["checks"],
        "findings": findings,
        "lessons_applied": base["lessons_applied"],
        "passed": passed,
    }
    if persist_case and knowledge is not None and product_id:
        case = MethodologyCase(
            case_id=uuid.uuid4().hex[:12],
            product_id=product_id,
            stage=stage,
            domain=report["domain"],
            score=report["score"],
            passed=report["passed"],
            findings=report["findings"],
            metadata=case_metadata or {},
        )
        knowledge.append_case(case)
        report["case_id"] = case.case_id
    return report
