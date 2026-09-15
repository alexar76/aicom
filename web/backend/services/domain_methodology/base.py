"""
Domain methodology data model (schema v2).

A *DomainPack* is a declarative methodology profile for a product domain
(CRM, helpdesk, LMS, e-commerce, …). It is intentionally rich so that the
heuristic engine **and** the LLM second opinion have enough material to
grade process compliance — not visual polish, not generic test pass-rate.

Every pack describes:

* identity / matching       — id, label, keywords, categories;
* domain ontology           — entities (with fields), user roles, capabilities;
* process model             — lifecycle states + allowed transitions, terminal states;
* acceptance bar            — concrete user journeys the product must satisfy;
* API surface (optional)    — endpoints an honest implementation exposes;
* KPIs                      — process metrics with formula and target direction;
* red flags                 — anti-patterns that block the methodology gate;
* reference material        — sources / standards used to ground LLM advice.

All collections default to empty, so older schema-v1 callers that only used
``required_entities`` / ``required_roles`` etc. keep working unchanged via
the back-compat properties at the bottom of :class:`DomainPack`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityField:
    """A required attribute on a first-class domain entity (e.g. ``status`` on ``ticket``)."""

    #: Canonical field name (e.g. ``status``, ``due_date``).
    name: str
    #: Human-readable explanation of what the field carries.
    description: str = ""
    #: Synonyms that should also count as a match in spec / code text.
    aliases: tuple[str, ...] = ()
    #: When ``True`` the field is mandatory and contributes to the score.
    required: bool = True


@dataclass(frozen=True)
class DomainEntity:
    """A first-class object the product must model (ticket, deal, course, …)."""

    #: Canonical entity name (e.g. ``ticket``).
    name: str
    description: str = ""
    #: Required attributes on this entity (used by the spec/impl checks).
    fields: tuple[EntityField, ...] = ()
    #: Synonyms accepted in matching (e.g. ``incident``, ``case`` for ``ticket``).
    aliases: tuple[str, ...] = ()
    #: ``False`` for entities that are nice-to-have rather than required.
    required: bool = True

    def all_aliases(self) -> tuple[str, ...]:
        """Return ``(name,) + aliases`` — convenient for fuzzy matching."""
        return (self.name,) + tuple(self.aliases)


@dataclass(frozen=True)
class DomainRole:
    """A user persona / role the product must distinguish (agent, customer, …)."""

    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    required: bool = True

    def all_aliases(self) -> tuple[str, ...]:
        """Return ``(name,) + aliases`` for matcher use."""
        return (self.name,) + tuple(self.aliases)


@dataclass(frozen=True)
class Capability:
    """A concrete user-facing action the product must support (e.g. ``assign ticket``)."""

    #: Stable id used in findings and reports.
    id: str
    #: Human-readable label that is searched for in spec/code.
    label: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    #: Higher-severity capabilities are required; lower-severity contribute less.
    severity: Literal["high", "medium", "low"] = "high"

    def all_aliases(self) -> tuple[str, ...]:
        """Return ``(label,) + aliases`` — labels are the canonical match key."""
        return (self.label,) + tuple(self.aliases)


@dataclass(frozen=True)
class LifecycleState:
    """A named state in the lifecycle of the main domain object (e.g. ``resolved``)."""

    name: str
    description: str = ""
    aliases: tuple[str, ...] = ()
    #: Marks the entry state(s) of the state machine.
    is_initial: bool = False
    #: Marks terminal states (``closed``, ``won``, ``rolled back``, …).
    is_terminal: bool = False

    def all_aliases(self) -> tuple[str, ...]:
        """Return ``(name,) + aliases`` — used by lifecycle matching."""
        return (self.name,) + tuple(self.aliases)


@dataclass(frozen=True)
class LifecycleTransition:
    """A directed edge between two lifecycle states (``from_state -> to_state``)."""

    from_state: str
    to_state: str
    #: Optional label describing the action that triggers the move.
    label: str = ""
    #: Optional roles / events that may trigger this transition.
    triggered_by: tuple[str, ...] = ()


@dataclass(frozen=True)
class AcceptanceScenario:
    """A real end-to-end user journey the product must satisfy.

    Acceptance scenarios are *behavioural* tests of the methodology — they
    describe what an honest implementation has to let the user do (e.g. a
    sales rep must be able to advance a deal through stages with attribution).
    """

    #: Stable id used in findings.
    id: str
    #: Short human-readable title, also matched against spec / code text.
    title: str
    #: Coarse classification used for analytics and weighting.
    journey_type: Literal[
        "onboarding", "core_action", "edge_case", "recovery", "operational",
        "reporting", "compliance", "general",
    ] = "general"
    #: Ordered steps of the journey (matched fuzzily against the source text).
    steps: tuple[str, ...] = ()
    #: One-line description of what success looks like at the end of the flow.
    expected_outcome: str = ""
    severity: Literal["high", "medium", "low"] = "high"


@dataclass(frozen=True)
class ApiEndpoint:
    """An API endpoint that an honest implementation is expected to expose."""

    #: HTTP verb (``GET``, ``POST``, …); compared case-insensitively.
    method: str
    #: Path template with optional ``{id}``-style placeholders.
    path_pattern: str
    purpose: str = ""
    severity: Literal["high", "medium", "low"] = "medium"


@dataclass(frozen=True)
class ProcessMetric:
    """A process KPI with formula and direction (e.g. ``MTTR — lower is better``)."""

    id: str
    label: str
    #: Closed-form formula expressed in domain terms (used by reports / LLM).
    formula: str = ""
    target_direction: Literal["lower_is_better", "higher_is_better"] = "higher_is_better"
    #: Optional textual target ("<= 24h", "> 60%", …).
    target_value: Optional[str] = None


@dataclass(frozen=True)
class RedFlagPattern:
    """An anti-pattern in spec / code text that blocks the methodology gate."""

    id: str
    severity: Literal["high", "medium", "low"]
    #: Operator-facing description of the anti-pattern.
    description: str
    #: Lowercased substrings that, if found in the source, trigger the flag.
    keywords: tuple[str, ...] = ()
    #: Regex patterns evaluated case-insensitively against the raw source.
    regex: tuple[str, ...] = ()
    #: Suggested remediation; included verbatim in the finding's ``fix_hint``.
    fix_hint: str = ""

    def compiled_regex(self) -> Iterable[re.Pattern]:
        """Lazily compile :attr:`regex` patterns with ``re.I`` for matching."""
        return (re.compile(p, re.I) for p in self.regex)


@dataclass(frozen=True)
class Reference:
    """An external standard / textbook the methodology is grounded in."""

    title: str
    url: str = ""
    note: str = ""


# ---------------------------------------------------------------------------
# Top-level pack
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainPack:
    """Schema-v2 methodology contract for a product domain.

    Instances are immutable and built once at import time inside
    :mod:`web.backend.services.domain_methodology.packs`. The heuristic engine
    inspects the public collections directly; the LLM receives them serialised
    via :meth:`to_payload`.
    """

    domain_id: str
    label: str
    description: str

    # --- matching --------------------------------------------------------
    keywords: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()

    # --- ontology --------------------------------------------------------
    entities: tuple[DomainEntity, ...] = ()
    roles: tuple[DomainRole, ...] = ()
    capabilities: tuple[Capability, ...] = ()

    # --- process model ---------------------------------------------------
    lifecycle_states: tuple[LifecycleState, ...] = ()
    lifecycle_transitions: tuple[LifecycleTransition, ...] = ()
    acceptance_scenarios: tuple[AcceptanceScenario, ...] = ()
    api_endpoints: tuple[ApiEndpoint, ...] = ()
    process_metrics_definitions: tuple[ProcessMetric, ...] = ()

    # --- detection -------------------------------------------------------
    red_flags: tuple[RedFlagPattern, ...] = ()
    references: tuple[Reference, ...] = ()
    methodology_notes: str = ""

    # --- back-compat (schema v1 — derived if not set) --------------------
    _legacy_required_entities: tuple[str, ...] = field(default=(), repr=False)
    _legacy_required_roles: tuple[str, ...] = field(default=(), repr=False)
    _legacy_required_capabilities: tuple[str, ...] = field(default=(), repr=False)
    _legacy_required_lifecycle: tuple[str, ...] = field(default=(), repr=False)
    _legacy_process_metrics: tuple[str, ...] = field(default=(), repr=False)
    _legacy_blocking_red_flags: tuple[str, ...] = field(default=(), repr=False)

    # ------------------------------------------------------------------
    # Backward-compatible properties used by schema-v1 callers / heuristics
    # ------------------------------------------------------------------

    @property
    def required_entities(self) -> tuple[str, ...]:
        """Schema-v1 alias: names of required :class:`DomainEntity` instances."""
        if self._legacy_required_entities:
            return self._legacy_required_entities
        return tuple(e.name for e in self.entities if e.required)

    @property
    def required_roles(self) -> tuple[str, ...]:
        """Schema-v1 alias: names of required :class:`DomainRole` instances."""
        if self._legacy_required_roles:
            return self._legacy_required_roles
        return tuple(r.name for r in self.roles if r.required)

    @property
    def required_capabilities(self) -> tuple[str, ...]:
        """Schema-v1 alias: labels of high-severity :class:`Capability` items."""
        if self._legacy_required_capabilities:
            return self._legacy_required_capabilities
        return tuple(c.label for c in self.capabilities if c.severity == "high")

    @property
    def required_lifecycle(self) -> tuple[str, ...]:
        """Schema-v1 alias: ordered lifecycle state names."""
        if self._legacy_required_lifecycle:
            return self._legacy_required_lifecycle
        return tuple(s.name for s in self.lifecycle_states)

    @property
    def process_metrics(self) -> tuple[str, ...]:
        """Schema-v1 alias: KPI labels (without formulas)."""
        if self._legacy_process_metrics:
            return self._legacy_process_metrics
        return tuple(m.label for m in self.process_metrics_definitions)

    @property
    def blocking_red_flags(self) -> tuple[str, ...]:
        """Schema-v1 alias: descriptions of high-severity red flags."""
        if self._legacy_blocking_red_flags:
            return self._legacy_blocking_red_flags
        return tuple(rf.description for rf in self.red_flags if rf.severity == "high")

    # ------------------------------------------------------------------
    # Lookups used by heuristic engine
    # ------------------------------------------------------------------

    def lifecycle_state_aliases(self) -> dict[str, tuple[str, ...]]:
        """Map ``state name -> (name, *aliases)`` — used by lifecycle scoring."""
        return {s.name: s.all_aliases() for s in self.lifecycle_states}

    def initial_states(self) -> tuple[str, ...]:
        """Names of states marked ``is_initial=True`` (graph entry points)."""
        return tuple(s.name for s in self.lifecycle_states if s.is_initial)

    def terminal_states(self) -> tuple[str, ...]:
        """Names of states marked ``is_terminal=True`` (graph sinks)."""
        return tuple(s.name for s in self.lifecycle_states if s.is_terminal)

    def entity_aliases(self) -> dict[str, tuple[str, ...]]:
        """Map ``entity name -> (name, *aliases)`` for fuzzy entity matching."""
        return {e.name: e.all_aliases() for e in self.entities}

    def capability_aliases(self) -> dict[str, tuple[str, ...]]:
        """Map ``capability label -> (label, *aliases)`` for capability matching."""
        return {c.label: c.all_aliases() for c in self.capabilities}

    def role_aliases(self) -> dict[str, tuple[str, ...]]:
        """Map ``role name -> (name, *aliases)`` for role matching."""
        return {r.name: r.all_aliases() for r in self.roles}

    # ------------------------------------------------------------------
    # Serialization (admin API + LLM prompt)
    # ------------------------------------------------------------------

    def to_payload(self, *, full: bool = False) -> dict:
        """Serialise the pack for the admin API and the LLM prompt.

        ``full=False`` returns the compact schema-v1-shaped summary that older
        callers (catalog endpoints, marketplace_quality logs) consume.
        ``full=True`` returns the rich schema-v2 payload, including lifecycle
        transitions, acceptance scenarios, API contracts and KPI formulas —
        used by ``GET /api/admin/methodology/domains/{id}`` and by the LLM
        second-opinion prompt of :class:`agents.methodologist.MethodologyAgent`.
        """
        base = {
            "schema_version": 2,
            "domain_id": self.domain_id,
            "label": self.label,
            "description": self.description,
            "keywords": list(self.keywords),
            "categories": list(self.categories),
            "required_entities": list(self.required_entities),
            "required_roles": list(self.required_roles),
            "required_capabilities": list(self.required_capabilities),
            "required_lifecycle": list(self.required_lifecycle),
            "process_metrics": list(self.process_metrics),
            "blocking_red_flags": list(self.blocking_red_flags),
        }
        if not full:
            return base
        base.update(
            {
                "entities": [
                    {
                        "name": e.name,
                        "description": e.description,
                        "aliases": list(e.aliases),
                        "required": e.required,
                        "fields": [
                            {
                                "name": f.name,
                                "description": f.description,
                                "aliases": list(f.aliases),
                                "required": f.required,
                            }
                            for f in e.fields
                        ],
                    }
                    for e in self.entities
                ],
                "roles": [
                    {
                        "name": r.name,
                        "description": r.description,
                        "aliases": list(r.aliases),
                        "required": r.required,
                    }
                    for r in self.roles
                ],
                "capabilities": [
                    {
                        "id": c.id,
                        "label": c.label,
                        "description": c.description,
                        "aliases": list(c.aliases),
                        "severity": c.severity,
                    }
                    for c in self.capabilities
                ],
                "lifecycle_states": [
                    {
                        "name": s.name,
                        "description": s.description,
                        "aliases": list(s.aliases),
                        "is_initial": s.is_initial,
                        "is_terminal": s.is_terminal,
                    }
                    for s in self.lifecycle_states
                ],
                "lifecycle_transitions": [
                    {
                        "from_state": t.from_state,
                        "to_state": t.to_state,
                        "label": t.label,
                        "triggered_by": list(t.triggered_by),
                    }
                    for t in self.lifecycle_transitions
                ],
                "acceptance_scenarios": [
                    {
                        "id": a.id,
                        "title": a.title,
                        "journey_type": a.journey_type,
                        "steps": list(a.steps),
                        "expected_outcome": a.expected_outcome,
                        "severity": a.severity,
                    }
                    for a in self.acceptance_scenarios
                ],
                "api_endpoints": [
                    {
                        "method": e.method,
                        "path_pattern": e.path_pattern,
                        "purpose": e.purpose,
                        "severity": e.severity,
                    }
                    for e in self.api_endpoints
                ],
                "process_metrics_definitions": [
                    {
                        "id": m.id,
                        "label": m.label,
                        "formula": m.formula,
                        "target_direction": m.target_direction,
                        "target_value": m.target_value,
                    }
                    for m in self.process_metrics_definitions
                ],
                "red_flags": [
                    {
                        "id": rf.id,
                        "severity": rf.severity,
                        "description": rf.description,
                        "keywords": list(rf.keywords),
                        "regex": list(rf.regex),
                        "fix_hint": rf.fix_hint,
                    }
                    for rf in self.red_flags
                ],
                "references": [
                    {"title": r.title, "url": r.url, "note": r.note}
                    for r in self.references
                ],
                "methodology_notes": self.methodology_notes,
            }
        )
        return base
