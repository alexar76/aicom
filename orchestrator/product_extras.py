"""
Pipeline product fields that are not first-class SQL columns but must survive SQLite round-trips.
"""

from __future__ import annotations

import json
from typing import Any

# Top-level product keys persisted in products.extras JSON (not in dedicated columns).
PRODUCT_EXTRA_KEYS: tuple[str, ...] = (
    "name",
    "delivery_profile",
    "production_mode",
    "quality_repair_round",
    "security_repair_round",
    "critic_repair_round",
    "last_bug_context",
    "failure_reason",
    "peer_reviews",
    "design_review_iterations",
    "qa_peer_review_iterations",
    "policy_audit_eligible",
    "design_review_forced_proceed",
    "qa_review_forced_proceed",
    "qa_repair_extensions",
    "security_repair_extensions",
    "human_review_kind",
    "human_review_reason",
    "surrogate_decisions",
    "surrogate_repair_hint",
    "config_arm",
    "learning_frozen",
    "max_quality_loops_override",
    "owner_email",
    "funnel_lead_source",
    "funnel_referral",
    "operator_locked",
    "operator_locked_at",
    "metis_gate",  # advisory Metis confidence-gate envelope (opt-in; see llm/metis_gate.py)
    # Severity-weighted QA defect total of the last ACCEPTED round, and how many rounds
    # have been thrown away. Both must survive a cycle or the round-regression guard has
    # nothing to compare against and silently degrades to accepting everything.
    "last_qa_defect_score",
    "reverted_round_count",
    # The QA findings that describe the tree currently on disk. A revert restores the
    # code; without this it left the REJECTED round's findings in last_bug_context, so
    # the next round was handed a diagnosis of a tree that no longer existed.
    "last_accepted_bug_context",
    "last_journey_depth",
    "last_demo_quality_score",
    "last_backend_booted",
    "last_preview_crashed",
    "last_critical_pressure",
    "last_reopen_rules_version",
    "last_accepted_defect_identities",
    "last_accepted_tree_fingerprint",
    "last_qa_defect_score_rules",
    "last_round_generated",
    "budget_parked",
    "state_before_budget_park",
    # Fixed-point detection in the round guard. These MUST be here: under the SQLite backend a
    # key absent from this tuple is dropped on save, so the repeat counter would reset every
    # cycle and the breaker that stops a stuck repair loop could never reach its threshold — a
    # guard that silently does nothing, which is the exact failure it was written to end.
    # Sentinel reached 38 reverted rounds before anyone noticed; a reset counter would have made
    # that invisible forever.
    "rejected_tree_fingerprints",
    "pipeline_stuck_reason",
    "pipeline_stuck_at",
    # Consecutive accepted QA-fail rounds that did not lower the defect score. Must survive
    # a cycle or the plateau breaker resets every round and never reaches its threshold —
    # the same silent-guard failure as dropping rejected_tree_fingerprints.
    "qa_non_improvement_streak",
)

# Top-level product keys that already have a home in SQLite (dedicated columns,
# the explicit ``extras`` allow-list above, or the nested ``metadata`` blob) and
# therefore must NOT be duplicated into the generic catch-all column.
#
# ``metadata`` is reconstructed from dedicated SQL columns; ``tasks`` is stored in
# the tasks table; ``workspace_id`` is a column on its own. Internal sync markers
# (leading underscore, e.g. ``_dirty_product_ids``) are also excluded.
_RESERVED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "workspace_id",
        "idea",
        "state",
        "created_at",
        "updated_at",
        "metadata",
        "tasks",
        # dedicated SQL columns surfaced as top-level keys on the product dict
        "spec",
        "architecture",
        "tags",
        "category",
        "monetization_scheme",
        "evolution_history",
        "error",
        "current_task_id",
    }
    | set(PRODUCT_EXTRA_KEYS)
)


def extract_product_extras(product: dict[str, Any]) -> dict[str, Any]:
    """Collect extra fields from a product dict for SQL persistence."""
    out: dict[str, Any] = {}
    for key in PRODUCT_EXTRA_KEYS:
        if key in product and product[key] is not None:
            out[key] = product[key]
    return out


def extract_generic_metadata(product: dict[str, Any]) -> dict[str, Any]:
    """Capture any *unknown* top-level product fields so SQLite never silently drops them.

    Anything that is not a reserved column, not in the ``PRODUCT_EXTRA_KEYS``
    allow-list, and not an internal sync marker is persisted verbatim into the
    ``generic_metadata`` JSON column. This is the forward-compatibility catch-all:
    new product fields survive a SQLite round-trip without a schema migration or a
    code change to the allow-list.
    """
    out: dict[str, Any] = {}
    for key, val in product.items():
        if not isinstance(key, str):
            continue
        if key in _RESERVED_TOP_LEVEL_KEYS or key.startswith("_"):
            continue
        if val is None:
            continue
        out[key] = val
    return out


def merge_generic_metadata(product: dict[str, Any], generic: dict[str, Any] | None) -> dict[str, Any]:
    """Merge persisted generic metadata back onto a product dict (does not clobber set fields)."""
    if not generic:
        return product
    for key, val in generic.items():
        if key in _RESERVED_TOP_LEVEL_KEYS or str(key).startswith("_"):
            continue
        if key not in product or product.get(key) is None:
            product[key] = val
    return product


def merge_product_extras(product: dict[str, Any], extras: dict[str, Any] | None) -> dict[str, Any]:
    """Merge persisted extras back onto a product dict."""
    if not extras:
        return product
    for key, val in extras.items():
        if key not in product or product.get(key) is None:
            product[key] = val
    return product


def extras_to_json(extras: dict[str, Any]) -> str | None:
    if not extras:
        return None
    return json.dumps(extras, ensure_ascii=False)


def extras_from_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
