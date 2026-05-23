"""Orchestrator-as-a-Capability (#10)

The planner (which picks capability chains) IS a capability priced at 1% of spend.
External agent with empty head just sends NL task → orchestrator selects, negotiates,
executes, returns result + BOM.

Sell the brain, not just the muscles. When ecosystem grows, orchestrator becomes
the most profitable capability in the catalog — mandatory for most tasks.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrchestrationPlan:
    """A multi-step plan to fulfill an NL task."""

    task: str
    steps: list[dict[str, Any]]  # Each step: {product_id, capability_id, input, depends_on}
    estimated_total_usd: float
    estimated_total_ms: int
    budget_usd: float
    orchestration_fee_pct: float = 0.01  # 1% of total spend
    strategy: str = "optimal"  # optimal, cheapest, fastest, most_trusted

    @property
    def orchestration_fee_usd(self) -> float:
        return round(self.estimated_total_usd * self.orchestration_fee_pct, 4)


class Orchestrator:
    """AI-powered planner that decomposes NL tasks into capability chains.

    This IS the brain of the marketplace. External agents send NL tasks,
    the orchestrator chooses which capabilities to chain, negotiates prices,
    and returns the result.

    Pricing: 1% of total spend (configurable).
    """

    def __init__(self, orchestration_fee_pct: float = 0.01):
        self.fee_pct = orchestration_fee_pct
        self._plans: list[OrchestrationPlan] = []
        self._total_fees_earned: float = 0.0
        self._tasks_completed: int = 0

    def plan(
        self,
        task: str,
        budget_usd: float,
        available_capabilities: list[dict[str, Any]],
        strategy: str = "optimal",
    ) -> OrchestrationPlan:
        """Decompose NL task into a capability chain plan.

        In production, this uses an LLM to read all capability descriptions
        and select the optimal chain. Here we use a heuristic planner.
        """
        # Heuristic: find capabilities whose name/description matches task keywords
        task_lower = task.lower()
        steps: list[dict[str, Any]] = []

        # Simple keyword-based matching
        keywords_map = {
            "translate": "translate",
            "legal": "legal",
            "review": "review",
            "summarize": "summarize",
            "fraud": "fraud",
            "score": "score",
            "audit": "audit",
            "analyze": "analyze",
            "generate": "generate",
            "search": "search",
        }

        matched = []
        for kw, cap_hint in keywords_map.items():
            if kw in task_lower:
                for cap in available_capabilities:
                    if cap_hint in cap.get("name", "").lower() or cap_hint in cap.get("capability_id", "").lower():
                        if cap not in matched:
                            matched.append(cap)
                            break

        if not matched and available_capabilities:
            # Fallback: pick the cheapest capability
            matched = [min(available_capabilities, key=lambda c: c.get("price_per_call_usd", 999))]

        # Build sequential steps
        prev_id = None
        total_price = 0.0
        total_latency = 0

        for i, cap in enumerate(matched):
            step_id = f"step_{i}"
            step = {
                "id": step_id,
                "product_id": cap.get("product_id", ""),
                "capability_id": cap.get("capability_id", cap.get("name", "")),
                "draft_input": {"text": task if i == 0 else "{output_from_previous}"},
                "depends_on": [prev_id] if prev_id else [],
                "input_from": prev_id,
                "est_price_usd": cap.get("price_per_call_usd", 0.35),
                "est_latency_ms": cap.get("p50_latency_ms", 3000),
            }
            steps.append(step)
            total_price += step["est_price_usd"]
            total_latency += step["est_latency_ms"]
            prev_id = step_id

        plan = OrchestrationPlan(
            task=task,
            steps=steps,
            estimated_total_usd=total_price,
            estimated_total_ms=total_latency,
            budget_usd=budget_usd,
            orchestration_fee_pct=self.fee_pct,
            strategy=strategy,
        )

        self._plans.append(plan)
        return plan

    def execute_plan(
        self,
        plan: OrchestrationPlan,
        invoker,  # Function that invokes a capability: (product_id, cap_id, input) → result
    ) -> dict[str, Any]:
        """Execute a plan step by step, feeding outputs forward."""
        context: dict[str, Any] = {}
        results: list[dict[str, Any]] = []
        total_spent = 0.0
        all_ok = True

        for step in plan.steps:
            inp = dict(step.get("draft_input") or {})
            if context:
                if "output_from_previous" not in inp:
                    inp["output_from_previous"] = context
                for key, val in inp.items():
                    if isinstance(val, str) and "{output_from_previous}" in val:
                        inp[key] = val.replace("{output_from_previous}", json.dumps(context))

            try:
                result = invoker(
                    step["product_id"],
                    step["capability_id"],
                    inp,
                )
                results.append(result)
                total_spent += result.get("price_usd", step["est_price_usd"])
                if result.get("success"):
                    context = result.get("result") or {}
                else:
                    all_ok = False
                    break
            except Exception:
                all_ok = False
                break

        orchestration_fee = round(total_spent * self.fee_pct, 4)
        self._total_fees_earned += orchestration_fee
        self._tasks_completed += 1

        return {
            "task": plan.task,
            "success": all_ok,
            "steps_executed": len(results),
            "total_spend_usd": round(total_spent, 4),
            "orchestration_fee_usd": orchestration_fee,
            "orchestration_fee_pct": self.fee_pct,
            "bill_of_materials": {
                "steps": [
                    {
                        "capability_id": s["capability_id"],
                        "price_usd": r.get("price_usd", s["est_price_usd"]),
                        "success": r.get("success", False),
                    }
                    for s, r in zip(plan.steps, results)
                ],
                "orchestration_fee_usd": orchestration_fee,
                "total_usd": round(total_spent + orchestration_fee, 4),
            },
            "final_result": results[-1].get("result") if results else {},
        }

    def stats(self) -> dict[str, Any]:
        return {
            "total_plans": len(self._plans),
            "tasks_completed": self._tasks_completed,
            "total_fees_earned_usd": round(self._total_fees_earned, 4),
            "fee_pct": self.fee_pct,
            "avg_fee_per_task": round(self._total_fees_earned / max(self._tasks_completed, 1), 4),
        }
