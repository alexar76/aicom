"""
Dynamic model routing based on LLM budget consumption.

When daily/monthly spend approaches configured caps, non-critical tasks are
downgraded to cheaper models instead of failing. Critical tasks (security, dev, qa)
retain heavy models until the budget reaches the critical tier.

Integrates with the existing ``LLMUsageGuard`` for spend tracking and
``pricing_estimate`` for provider/model rate lookups.
"""

from __future__ import annotations

import logging
import os

from core.throughput_limits import (
    effective_llm_daily_cost_cap_usd,
    effective_llm_monthly_cost_cap_usd,
)
from llm.usage_guard import get_usage_guard

logger = logging.getLogger(__name__)

# Task types that always get priority for heavy models.
_CRITICAL_TASK_TYPES: frozenset[str] = frozenset({
    "security_scan",
    "code_generation",
    "qa_testing",
    "hardening",
    "arch_design",
})

# Task types that can use light models when budget is tight.
_NON_CRITICAL_TASK_TYPES: frozenset[str] = frozenset({
    "market_research",
    "marketing_content",
    "sales_outreach",
    "evolution_analysis",
    "spec_writing",
    "methodology_review",
    "design_critique",
    "devops_setup",
})

BudgetTier = str  # "normal" | "tight" | "critical"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def is_critical_task(task_type: str | None) -> bool:
    """True for build/security/quality task types that must keep heavy models
    and are eligible for cross-provider escalation. Single source of truth for
    'critical' across cost_guard and the router."""
    return (task_type or "").strip().lower() in _CRITICAL_TASK_TYPES


def cost_guard_enabled() -> bool:
    """True when budget caps are configured and the feature is not explicitly disabled."""
    if os.environ.get("AIFACTORY_COST_GUARD_ENABLED", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return effective_llm_daily_cost_cap_usd() > 0 or effective_llm_monthly_cost_cap_usd() > 0


class CostGuard:
    """Budget-aware model resolver.

    Wraps ``LLMUsageGuard`` snapshots to decide which model tier to use.
    """

    def __init__(self) -> None:
        self._usage_guard = get_usage_guard()

    # ── Tier calculation ──────────────────────────────────────────────────

    def budget_tier(self) -> BudgetTier:
        """Return the current budget tier based on the worst (most consumed) cap."""
        tight_threshold = _env_float("AIFACTORY_COST_GUARD_TIGHT_THRESHOLD", 0.80)
        critical_threshold = _env_float("AIFACTORY_COST_GUARD_CRITICAL_THRESHOLD", 0.95)
        snap = self._usage_guard.snapshot()

        fraction = 0.0
        daily_cap = snap.get("daily_cost_cap_usd", 0.0)
        if daily_cap > 0:
            fraction = max(fraction, snap.get("day_spend_usd", 0.0) / daily_cap)
        monthly_cap = snap.get("monthly_cost_cap_usd", 0.0)
        if monthly_cap > 0:
            fraction = max(fraction, snap.get("month_spend_usd", 0.0) / monthly_cap)

        if fraction >= critical_threshold:
            return "critical"
        if fraction >= tight_threshold:
            return "tight"
        return "normal"

    def is_budget_tight(self) -> bool:
        """True when in tight or critical tier."""
        return self.budget_tier() != "normal"

    # ── Model resolution ──────────────────────────────────────────────────

    def resolve_model(
        self,
        provider_name: str,
        task_type: str,
        requested_model: str | None,
        *,
        available_models: dict[str, str] | None = None,
    ) -> str | None:
        """Return the model to use, potentially downgraded for budget.

        Args:
            provider_name: Provider key (e.g. "deepseek_api").
            task_type: Task type from routing rules.
            requested_model: Model the router would have selected.
            available_models: Mapping of tier → model id from provider config
                              (e.g. {"heavy": "deepseek-chat", "light": "deepseek-chat", "budget": "deepseek-chat"}).
                              If not provided, ``requested_model`` is returned unchanged.

        Returns:
            Model id to use, or None to keep the router's default.
        """
        if not available_models:
            return requested_model

        # Check if any caps are actually active (snapshot, not env).
        snap = self._usage_guard.snapshot()
        if snap.get("daily_cost_cap_usd", 0.0) <= 0 and snap.get("monthly_cost_cap_usd", 0.0) <= 0:
            return requested_model

        tier = self.budget_tier()
        if tier == "normal":
            return requested_model

        norm_task = (task_type or "").strip().lower()

        if tier == "tight":
            if norm_task in _NON_CRITICAL_TASK_TYPES:
                model = available_models.get("light") or available_models.get("budget")
                if model and model != requested_model:
                    logger.info(
                        "CostGuard: downgrading %s from %s to light model %s (tier=tight)",
                        task_type, requested_model, model,
                    )
                return model or requested_model
            if norm_task not in _CRITICAL_TASK_TYPES:
                # Unknown task_type — treat as critical (keep heavy model) but
                # log so the operator knows to classify it explicitly. Avoids
                # silently passing through unclassified tasks under budget pressure.
                logger.debug(
                    "CostGuard: unknown task_type=%r under tight tier — keeping %s (add to _CRITICAL_TASK_TYPES or _NON_CRITICAL_TASK_TYPES)",
                    task_type, requested_model,
                )
            return requested_model

        # tier == "critical" — everything goes to budget
        model = available_models.get("budget") or available_models.get("light") or available_models.get("heavy")
        if model and model != requested_model:
            logger.warning(
                "CostGuard: downgrading %s from %s to budget model %s (tier=critical)",
                task_type, requested_model, model,
            )
        return model or requested_model

    def snapshot(self) -> dict[str, object]:
        """Return combined cost guard state for admin/debugging."""
        usage = self._usage_guard.snapshot()
        return {
            "budget_tier": self.budget_tier(),
            "enabled": cost_guard_enabled(),
            "tight_threshold": _env_float("AIFACTORY_COST_GUARD_TIGHT_THRESHOLD", 0.80),
            "critical_threshold": _env_float("AIFACTORY_COST_GUARD_CRITICAL_THRESHOLD", 0.95),
            "day_spend_usd": usage.get("day_spend_usd", 0.0),
            "month_spend_usd": usage.get("month_spend_usd", 0.0),
            "daily_cost_cap_usd": usage.get("daily_cost_cap_usd", 0.0),
            "monthly_cost_cap_usd": usage.get("monthly_cost_cap_usd", 0.0),
        }


_cost_guard: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    """Return the process-wide CostGuard singleton."""
    global _cost_guard
    if _cost_guard is None:
        _cost_guard = CostGuard()
    return _cost_guard


def reset_cost_guard_for_tests(guard: CostGuard | None = None) -> None:
    """Test helper — replace the process-wide instance."""
    global _cost_guard
    _cost_guard = guard
