# aimarket-orchestrator

## Value in plain words

Describe a goal in plain language; the hub plans which AI capabilities to call in what order and estimates cost before spending — autopilot for multi-step tasks.

**Простыми словами:** Описываете цель простыми словами; хаб планирует, какие AI вызывать и в каком порядке, и оценивает стоимость до траты — автопилот для многошаговых задач.

Full text: [docs/value.md](docs/value.md)


## Documentation

| Document | Description |
|----------|-------------|
| [User guide](docs/user-guide.md) | Install, configure, verify plugin is loaded |
| [User cases](docs/user-cases.md) | Personas and cross-plugin workflows |
| [SDK integration](docs/sdk-integration.md) | Code examples and hook behavior |

---

**The planner IS a capability. Priced at 1% of total spend.**
External agents send NL tasks. Orchestrator selects the capability chain, negotiates prices, executes, and returns a signed Bill of Materials. You sell the brain, not just the muscles.

## When to Use
- External agents with "empty head" — just send NL task, get result + BOM
- Complex multi-step workflows requiring capability chaining
- Consumer who doesn't know which capabilities exist — orchestrator plans for them
- Monetization: orchestrator earns 1% of every routed dollar in the ecosystem

## Installation
```bash
pip install aimarket-orchestrator
```

## Example
```python
from aimarket_orchestrator.orchestrator_capability import Orchestrator

orch = Orchestrator(orchestration_fee_pct=0.01)
caps = [
    {"capability_id": "translate.multi@v2", "product_id": "p1", "name": "translate",
     "price_per_call_usd": 0.40, "p50_latency_ms": 8100},
    {"capability_id": "legal.review@v1", "product_id": "p2", "name": "legal",
     "price_per_call_usd": 1.20, "p50_latency_ms": 11400},
]

plan = orch.plan("translate contract to French then legal review", budget_usd=3.0,
                 available_capabilities=caps)
print(f"Steps: {len(plan.steps)}, Est: ${plan.estimated_total_usd:.2f}")
print(f"Orchestration fee: ${plan.orchestration_fee_usd:.4f} (1%)")

def mock_invoke(pid, cid, inp):
    return {"success": True, "result": {"output": f"done {cid}"}, "price_usd": 0.40}

result = orch.execute_plan(plan, mock_invoke)
print(result["bill_of_materials"])
print(f"Tasks completed: {orch.stats()['tasks_completed']}")
print(f"Total fees earned: ${orch.stats()['total_fees_earned_usd']:.4f}")
```

## Pricing
Default 1% of total invocation spend. Configurable at init: `Orchestrator(orchestration_fee_pct=0.02)` for 2%.

## License
MIT · Maintained by AI-Factory
