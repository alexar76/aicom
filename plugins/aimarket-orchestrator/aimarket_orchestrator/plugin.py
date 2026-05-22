"""aimarket-orchestrator plugin — NL task planner and executor — decomposes tasks into capability chains, 1% fee."""

from aimarket_hub.plugin import HubPlugin
from aimarket_orchestrator.orchestrator_capability import Orchestrator


class OrchestratorPlugin(HubPlugin):
    name = "aimarket-orchestrator"
    version = "2.0.0"
    description = "NL task planner and executor — decomposes tasks into capability chains, 1% fee"
    homepage = "https://github.com/ai-factory/aimarket-orchestrator"
    category = "monetization"

    def __init__(self):
        super().__init__()
        self._orchestrator = Orchestrator(orchestration_fee_pct=0.01)

    def register_routes(self, router):
        
        from pydantic import BaseModel, Field

        class PlanRequest(BaseModel):
            task: str = Field(..., min_length=3, max_length=4000)
            budget_usd: float = Field(3.0, ge=0, le=100_000)

        @router.post("/orchestrator/plan")
        async def plan_task(body: PlanRequest):
            plan = self._orchestrator.plan(body.task, body.budget_usd, [], "optimal")
            return {"task": plan.task, "steps": len(plan.steps),
                    "estimated_total_usd": plan.estimated_total_usd,
                    "orchestration_fee_usd": plan.orchestration_fee_usd}

    def get_manifest_extension(self):
        return {"orchestrator": {"fee_pct": 0.01, "strategy": "optimal"}}
