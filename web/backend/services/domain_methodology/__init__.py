"""
Domain methodology framework
============================

Public façade for the *pluggable domain packs* that the
:class:`agents.methodologist.MethodologyAgent` uses to grade whether a generated
product actually follows the accepted process / shape for its domain (CRM,
helpdesk, LMS, e-commerce, …).

Each pack is a declarative methodology profile (schema v2) describing:

* matching keywords / categories,
* required domain entities (with fields), user roles, capabilities,
* a lifecycle graph (states + allowed transitions),
* acceptance scenarios (real user journeys),
* expected API surface,
* KPI formulas with target direction,
* anti-pattern red flags (keyword + regex),
* reference standards.

Two control points use this module:

* **post-spec**  — :func:`web.backend.services.methodology_review.review_spec`
  ranks the PM specification against the matched pack;
* **post-impl** — :func:`web.backend.services.methodology_review.review_implementation`
  ranks generated code/templates against the same pack.

Public API
----------

* :func:`list_domain_packs`     – full catalog of built-in packs.
* :func:`get_domain_pack`       – exact lookup by ``domain_id``.
* :func:`select_domain_pack`    – best-match pack for a given idea / spec.
* :func:`score_domain_packs`    – full ranking (debug / search).

The dataclasses re-exported here (`DomainPack`, `LifecycleState`, …) make up
the schema-v2 contract used by the heuristic engine and the admin API.
"""

from web.backend.services.domain_methodology.base import (
    AcceptanceScenario,
    ApiEndpoint,
    Capability,
    DomainEntity,
    DomainPack,
    DomainRole,
    EntityField,
    LifecycleState,
    LifecycleTransition,
    ProcessMetric,
    RedFlagPattern,
    Reference,
)
from web.backend.services.domain_methodology.registry import (
    get_domain_pack,
    list_domain_packs,
    score_domain_packs,
    select_domain_pack,
)

__all__ = [
    "AcceptanceScenario",
    "ApiEndpoint",
    "Capability",
    "DomainEntity",
    "DomainPack",
    "DomainRole",
    "EntityField",
    "LifecycleState",
    "LifecycleTransition",
    "ProcessMetric",
    "RedFlagPattern",
    "Reference",
    "get_domain_pack",
    "list_domain_packs",
    "score_domain_packs",
    "select_domain_pack",
]
