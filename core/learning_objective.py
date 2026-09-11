"""Learning objective — realized Expected Value per build.

Single number every learning loop optimizes (spec §8.1):

    EV(build) = (demand_value if shipped else 0)  −  cost

``demand_value`` is a money-proxy from storefront / AIMarket signals; ``cost`` is
the realized LLM spend (repair loops included). Realized EV (not a forecast) is
what the learning curve plots — a rising series is the proof the factory learns.
All weights are env-tunable; defaults are deliberately conservative.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def demand_value(demand: dict[str, Any] | None) -> float:
    """Money-proxy ($) from realized demand signals. 0 when there is no traffic."""
    d = demand or {}

    def _n(key: str) -> float:
        try:
            return max(0.0, float(d.get(key) or 0))
        except (TypeError, ValueError):
            return 0.0

    invokes = _n("aimarket_invokes")
    checkouts = _n("checkout_starts")
    views = _n("views")
    return (
        invokes * _envf("AIFACTORY_EV_INVOKE_VALUE", 0.50)
        + checkouts * _envf("AIFACTORY_EV_CHECKOUT_VALUE", 0.20)
        + views * _envf("AIFACTORY_EV_VIEW_VALUE", 0.002)
    )


def expected_value(
    *,
    shipped: bool,
    cost_usd: float = 0.0,
    repair_rounds: int = 0,
    demand: dict[str, Any] | None = None,
) -> float:
    """Realized EV for one build. Negative when spend outweighs demand."""
    try:
        cost = max(0.0, float(cost_usd or 0.0))
    except (TypeError, ValueError):
        cost = 0.0
    # Repair rounds carry a small opportunity penalty even when cost logging is sparse.
    cost += max(0, int(repair_rounds or 0)) * _envf("AIFACTORY_EV_REPAIR_PENALTY", 0.10)
    value = demand_value(demand) if shipped else 0.0
    return round(value - cost, 4)


def learning_ab_enabled() -> bool:
    """Master switch for live-vs-frozen A/B proof cohorts (spec §8.8)."""
    return _env_truthy("AIFACTORY_LEARNING_FROZEN") or _env_truthy("AIFACTORY_LEARNING_AB")


def frozen_cohort_fraction() -> float:
    """Share of builds assigned to the frozen-control cohort (playbook off)."""
    if not learning_ab_enabled():
        return 0.0
    raw = (os.environ.get("AIFACTORY_LEARNING_FROZEN_FRACTION", "") or "").strip()
    if not raw:
        return 0.5
    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return 0.5


def cohort_is_frozen(product_id: str) -> bool:
    """Stable per-product assignment to frozen vs live cohort."""
    frac = frozen_cohort_fraction()
    if frac <= 0:
        return False
    if frac >= 1:
        return True
    pid = (product_id or "").strip()
    if not pid:
        return False
    bucket = int(hashlib.sha256(pid.encode()).hexdigest()[:8], 16) % 10_000
    return bucket / 10_000.0 < frac


def assign_learning_cohort(product: dict[str, Any]) -> bool:
    """Tag ``learning_frozen`` on a product at creation. No-op when A/B is off."""
    if "learning_frozen" in product:
        return bool(product["learning_frozen"])
    pid = str(product.get("id") or "")
    frozen = cohort_is_frozen(pid) if pid and learning_ab_enabled() else False
    product["learning_frozen"] = frozen
    return frozen


def learning_frozen(product: dict[str, Any] | None = None) -> bool:
    """Whether this build is in the frozen-control cohort (playbook skipped)."""
    if product is not None:
        if "learning_frozen" in product:
            return bool(product["learning_frozen"])
        pid = str(product.get("id") or product.get("product_id") or "")
        if pid:
            return cohort_is_frozen(pid) if learning_ab_enabled() else False
    # No product context: only True when the entire fleet is frozen (fraction=1).
    return learning_ab_enabled() and frozen_cohort_fraction() >= 1.0
