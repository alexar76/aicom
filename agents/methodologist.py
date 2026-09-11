"""
Methodologist Agent
===================
Single agent that validates whether a generated product follows the accepted
process / shape for its domain (CRM, helpdesk, LMS, ...).

Two checkpoints, both implemented as utility methods (called inline by PM/QA),
plus a thin :meth:`execute` wrapper so the agent shows up as a first-class
participant in the orchestrator (logs, agent status, escalation, brainstorm).

Beyond the heuristic gate, the agent provides a small **learning loop**:

* :meth:`search`            — search learned lessons + past review cases.
* :meth:`add_lesson`        — operator-supplied rule (red flag).
* :meth:`learn_from_feedback` — turn a confirmed correct/incorrect review into
  an automatic lesson when applicable.
* :meth:`history`           — full review history for a product.

Domain registry: :mod:`web.backend.services.domain_methodology`.
Heuristics:      :mod:`web.backend.services.methodology_review`.
Memory:          :mod:`web.backend.services.methodology_knowledge`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from agents.prompt_utils import prompt_json
from agents.prompts.load_prompt import load_prompt
from core.logging_utils import log_suppressed

from .base_agent import AgentInput, AgentOutput, BaseAgent

logger = logging.getLogger(__name__)
from llm import GenerationConfig, LLMRouter
from llm.factory_defaults import FACTORY_MAX_OUTPUT_TOKENS_HEAVY, FACTORY_TIMEOUT_PM_SPEC_SEC
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

_METHODOLOGIST_SYSTEM = load_prompt("methodologist_system_prompt.md")


class MethodologyAgent(BaseAgent):
    """Methodology gate — invoked at two checkpoints (post-spec, post-implementation)."""

    def __init__(self, llm_router: LLMRouter):
        """Wire the agent to the LLM router; defer knowledge-store creation until first use."""
        super().__init__(
            agent_type="methodologist",
            llm_router=llm_router,
            task_type="methodology_review",
        )
        self._knowledge: MethodologyKnowledgeStore | None = None

    # ------------------------------------------------------------------
    # Knowledge access (lazy)
    # ------------------------------------------------------------------

    def knowledge(self) -> MethodologyKnowledgeStore:
        """Return the lazily-created :class:`MethodologyKnowledgeStore` for this agent."""
        if self._knowledge is None:
            self._knowledge = MethodologyKnowledgeStore(data_root=str(self.data_root))
        return self._knowledge

    # ------------------------------------------------------------------
    # Domain pack selection
    # ------------------------------------------------------------------

    def select_pack_for(
        self,
        idea: str,
        category: str | None,
        spec: dict | None,
        *,
        forced_domain_id: str | None = None,
    ) -> DomainPack | None:
        """Resolve which :class:`DomainPack` applies for this product.

        Honours ``forced_domain_id`` as an explicit override (admin / prompt
        ``domain:=`` directive); otherwise falls back to the best-fit auto
        match from :func:`select_domain_pack`. Returns ``None`` when no pack
        is confident enough — callers must handle that case.
        """
        if forced_domain_id:
            forced = get_domain_pack(forced_domain_id)
            if forced is not None:
                return forced
        return select_domain_pack(idea or "", category=category, spec=spec)

    def list_packs(self) -> list[DomainPack]:
        """Full catalog of built-in packs (proxy for :func:`list_domain_packs`)."""
        return list_domain_packs()

    def rank_packs(
        self,
        idea: str,
        category: str | None,
        spec: dict | None = None,
    ) -> list[tuple[DomainPack, int]]:
        """Diagnostic ranking helper — proxy for :func:`score_domain_packs`."""
        return score_domain_packs(idea or "", category=category, spec=spec)

    # ------------------------------------------------------------------
    # Spec / implementation review entry points
    # ------------------------------------------------------------------

    def review_specification(
        self,
        product_id: str,
        idea: str,
        category: str | None,
        specification: dict,
        *,
        delivery_profile: str | None = None,
        forced_domain_id: str | None = None,
        persist_case: bool = True,
    ) -> dict:
        """Run the post-spec methodology gate for one product.

        Resolves the matching pack, calls
        :func:`web.backend.services.methodology_review.review_spec`, persists
        the report under ``state/<pid>/methodology_spec_review.json`` and (by
        default) appends a :class:`MethodologyCase` to the knowledge store.
        Used inline by :class:`agents.pm.PMAgent`.
        """
        pack = self.select_pack_for(idea, category, specification, forced_domain_id=forced_domain_id)
        report = review_spec(
            specification,
            pack=pack,
            stage="post_spec",
            knowledge=self.knowledge(),
            persist_case=persist_case,
            product_id=product_id,
            case_metadata={"category": category, "delivery_profile": delivery_profile},
        )
        report["delivery_profile"] = delivery_profile
        report["agent"] = self.agent_type
        report["product_id"] = product_id
        report["created_at"] = time.time()
        try:
            self._save_artifact(
                product_id, "state", report, filename="methodology_spec_review.json",
            )
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/methodologist.py)", exc_info=_suppressed_exc)
        return report

    def review_implementation_artifact(
        self,
        product_id: str,
        idea: str,
        category: str | None,
        specification: dict | None,
        code_dir: Path | None = None,
        *,
        delivery_profile: str | None = None,
        forced_domain_id: str | None = None,
        persist_case: bool = True,
    ) -> dict:
        """Run the post-implementation methodology gate over generated code.

        Defaults ``code_dir`` to ``${data_root}/code/<pid>``. Persists the
        resulting report under ``telemetry/<pid>/methodology_implementation.json``
        and, by default, appends a :class:`MethodologyCase`. Used inline by
        :class:`agents.qa.QAAgent`.
        """
        pack = self.select_pack_for(idea, category, specification, forced_domain_id=forced_domain_id)
        path = Path(code_dir) if code_dir else (self.data_root / "code" / product_id)
        report = review_implementation(
            path,
            pack=pack,
            spec=specification,
            stage="post_implementation",
            knowledge=self.knowledge(),
            persist_case=persist_case,
            product_id=product_id,
            case_metadata={"category": category, "delivery_profile": delivery_profile},
        )
        report["delivery_profile"] = delivery_profile
        report["agent"] = self.agent_type
        report["product_id"] = product_id
        report["created_at"] = time.time()
        try:
            tel_dir = self.data_root / "telemetry" / product_id
            tel_dir.mkdir(parents=True, exist_ok=True)
            (tel_dir / "methodology_implementation.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as _suppressed_exc:
            log_suppressed(logger, "non-fatal (agents/methodologist.py)", exc_info=_suppressed_exc)
        return report

    # ------------------------------------------------------------------
    # Search + history (knowledge access)
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        domain: str | None = None,
        kinds: tuple[str, ...] = ("lessons", "cases"),
        limit: int = 25,
    ) -> dict[str, list[dict[str, Any]]]:
        """Search learned lessons and review history (free-text substring match)."""
        return self.knowledge().search(query, domain=domain, kinds=kinds, limit=limit)

    def history(self, product_id: str) -> list[dict[str, Any]]:
        """Return the chronological list of methodology cases for one product."""
        return [c.to_dict() for c in self.knowledge().get_case_history(product_id)]

    # ------------------------------------------------------------------
    # Learning (lessons + feedback loop)
    # ------------------------------------------------------------------

    def add_lesson(
        self,
        *,
        domain: str,
        title: str,
        detail: str,
        severity: str = "medium",
        keywords: list[str] | None = None,
        regex: list[str] | None = None,
        applies_to: list[str] | None = None,
        fix_hint: str = "",
        source: str = "operator",
        weight: float = 1.0,
    ) -> dict[str, Any]:
        """Persist an operator-supplied lesson and return the stored payload."""
        lesson = MethodologyLesson(
            id=uuid.uuid4().hex[:12],
            domain=domain or "*",
            severity=severity or "medium",
            title=title or detail[:80],
            detail=detail or "",
            fix_hint=fix_hint,
            keywords=list(keywords or []),
            regex=list(regex or []),
            applies_to=list(applies_to or ["spec", "implementation"]),
            source=source,
            weight=float(weight or 1.0),
        )
        return self.knowledge().add_lesson(lesson).to_dict()

    def list_lessons(
        self,
        *,
        domain: str | None = None,
        enabled_only: bool = False,
        applies_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return all lessons (optionally filtered) as plain dicts."""
        return [
            lesson.to_dict()
            for lesson in self.knowledge().list_lessons(
                domain=domain, enabled_only=enabled_only, applies_to=applies_to,
            )
        ]

    def update_lesson(self, lesson_id: str, **changes: Any) -> dict[str, Any] | None:
        """Edit a lesson by id; returns the updated payload or ``None`` if not found."""
        lesson = self.knowledge().update_lesson(lesson_id, **changes)
        return lesson.to_dict() if lesson else None

    def delete_lesson(self, lesson_id: str) -> bool:
        """Delete a lesson by id; returns ``True`` when something was removed."""
        return self.knowledge().delete_lesson(lesson_id)

    def learn_from_feedback(
        self,
        *,
        case_id: str,
        product_id: str,
        was_correct: bool,
        notes: str = "",
        promote_finding_code: str | None = None,
        actor: str = "operator",
    ) -> dict[str, Any]:
        """Record operator feedback and (optionally) auto-promote a finding into a lesson.

        See :meth:`MethodologyKnowledgeStore.record_feedback` for the feedback
        log shape and the auto-promotion rule.
        """
        return self.knowledge().record_feedback(
            case_id=case_id,
            product_id=product_id,
            was_correct=was_correct,
            notes=notes,
            promote_finding_code=promote_finding_code,
            actor=actor,
        )

    # ------------------------------------------------------------------
    # Optional LLM second opinion (used by both reviews when available)
    # ------------------------------------------------------------------

    async def llm_second_opinion(
        self,
        agent_input: AgentInput,
        *,
        pack: DomainPack | None,
        heuristic_report: dict,
    ) -> dict:
        """Optional LLM enrichment of the heuristic report.

        Sends the matched pack and the heuristic findings to the configured
        LLM and parses a JSON response with shape::

            {
              "passed": bool,
              "additional_findings": [
                  {"severity": "...", "code": "...", "detail": "...", "fix_hint": "..."}
              ],
              "summary": "..."
            }

        The function never raises — on any failure (timeout, malformed JSON,
        no pack) it returns ``{}`` and the heuristic report stands alone.
        """
        if pack is None:
            return {}
        prompt = (
            f"{_METHODOLOGIST_SYSTEM}\n\n"
            f"Product idea:\n{agent_input.data.get('idea','')}\n\n"
            f"Domain pack (full schema):\n"
            f"{prompt_json(pack.to_payload(full=True), limit=8000)}\n\n"
            f"Heuristic report:\n"
            f"{prompt_json(heuristic_report, limit=6000)}\n"
        )
        try:
            cfg = GenerationConfig(
                temperature=0.15,
                max_tokens=FACTORY_MAX_OUTPUT_TOKENS_HEAVY,
                timeout_sec=FACTORY_TIMEOUT_PM_SPEC_SEC,
                json_mode=True,
            )
            raw = await self._generate(prompt, config=cfg, agent_input=agent_input)
            parsed = self._extract_json(raw) or {}
        except Exception:
            parsed = {}
        if not isinstance(parsed, dict):
            return {}
        extras = parsed.get("additional_findings") or []
        clean: list[dict] = []
        if isinstance(extras, list):
            for f in extras[:8]:
                if not isinstance(f, dict):
                    continue
                code = str(f.get("code") or "domain_methodology_finding")[:80]
                detail = str(f.get("detail") or "").strip()[:600]
                if not detail:
                    continue
                clean.append(
                    {
                        "severity": str(f.get("severity") or "medium").lower(),
                        "code": code,
                        "detail": detail,
                        "fix_hint": str(f.get("fix_hint") or "").strip()[:400],
                    }
                )
        return {
            "summary": str(parsed.get("summary") or "").strip()[:400],
            "additional_findings": clean,
            "llm_passed": bool(parsed.get("passed", True)) if "passed" in parsed else None,
        }

    # ------------------------------------------------------------------
    # Orchestrator entry point — runs an ad-hoc methodology snapshot
    # ------------------------------------------------------------------

    async def execute(self, agent_input: AgentInput) -> AgentOutput:
        """Orchestrator entry point: run an ad-hoc methodology snapshot.

        Dispatches on ``agent_input.data['stage']`` (``post_spec`` /
        ``post_implementation``) and returns an :class:`AgentOutput` whose
        ``data`` carries the full review report, ``passed`` flag, ``case_id``
        and a ``peer_review`` block compatible with the orchestrator's
        existing approve/block plumbing. Errors are caught and converted into
        a failed :class:`AgentOutput`.
        """
        start = time.time()
        pid = agent_input.product_id
        data = agent_input.data or {}

        idea = str(data.get("idea") or "")
        category = data.get("category")
        spec_payload = data.get("specification") or {}
        delivery_profile = data.get("delivery_profile")
        forced_domain_id = data.get("forced_domain_id") or data.get("domain")
        stage = str(data.get("stage") or "post_implementation").lower()

        try:
            if stage == "post_spec":
                report = self.review_specification(
                    pid,
                    idea,
                    category,
                    spec_payload if isinstance(spec_payload, dict) else {},
                    delivery_profile=delivery_profile,
                    forced_domain_id=forced_domain_id,
                )
            else:
                report = self.review_implementation_artifact(
                    pid,
                    idea,
                    category,
                    spec_payload if isinstance(spec_payload, dict) else None,
                    code_dir=self.data_root / "code" / pid,
                    delivery_profile=delivery_profile,
                    forced_domain_id=forced_domain_id,
                )

            passed = bool(report.get("passed"))
            elapsed = time.time() - start
            self._log(
                "INFO",
                f"Methodology {stage} for {pid}: domain={report.get('domain')} "
                f"score={report.get('score')} passed={passed} "
                f"lessons_applied={report.get('lessons_applied')} ({elapsed:.2f}s)",
            )

            findings = [f for f in (report.get("findings") or []) if isinstance(f, dict)]
            high_blockers = [
                str(f.get("detail") or f.get("code") or "").strip()
                for f in findings
                if f.get("severity") == "high" and (f.get("detail") or f.get("code"))
            ]
            notes_parts = [
                "Methodology gate (process / domain shape).",
                f"passed={passed}, score={report.get('score')}/{report.get('min_score')}.",
            ]
            if high_blockers:
                notes_parts.append("High-severity findings (Architect must address in architecture/TZ): " + "; ".join(high_blockers[:8]))

            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=pid,
                agent_type=self.agent_type,
                success=True,
                data={
                    "methodology_review": report,
                    "passed": passed,
                    "domain": report.get("domain"),
                    "score": report.get("score"),
                    "stage": stage,
                    "case_id": report.get("case_id"),
                    # Always approve for pipeline progression: Architect consumes
                    # methodology_spec_review.json + findings as binding remediation input.
                    "peer_review": {
                        "recommended": "approve",
                        "blockers": [],
                        "notes": " ".join(notes_parts),
                    },
                },
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
        except Exception as e:
            elapsed = time.time() - start
            self._log("ERROR", f"Methodology review failed for {pid}: {e}")
            return AgentOutput(
                task_id=agent_input.task_id,
                product_id=pid,
                agent_type=self.agent_type,
                success=False,
                error=str(e),
                timestamp=time.time(),
                metrics={"elapsed_seconds": elapsed},
            )
