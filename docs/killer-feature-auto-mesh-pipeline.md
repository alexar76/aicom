# AI-Factory and the separate Auto-Mesh service

AI-Factory builds products with its internal PM, architect, developer, QA and other role agents.
Its ordinary pipeline does not automatically replace those roles with marketplace providers.

## Implemented factory integration

The optional [external diagnosis flow](factory-subcontracting.md) adds a concrete purchase path:

1. A high/critical, file-bound QA finding persists through two completed internal repairs.
2. The factory looks for a configured, compatible, credits-eligible service on AIMarket.
3. It reserves a bounded price and invokes the service once.
4. It verifies the billing receipt and the report's source references.
5. Its internal developer receives the advice; normal tests and QA still determine acceptance.

The feature is off by default. It requires an approved provider, source-sharing scope, pinned Hub
keys and a funded account. Unknown payments stay reserved and are not automatically retried.
It does not promise a refund when local report acceptance fails.

Full algorithm, configuration, provider contract, accounting and recovery:
[English](factory-subcontracting.md) · [Русский](factory-subcontracting.ru.md) ·
[Español](factory-subcontracting.es.md) · [Français](factory-subcontracting.fr.md) ·
[中文](factory-subcontracting.zh.md).

## Separate Auto-Mesh service

[`ai-service-mesh/backend/ai_service_mesh/orchestrator.py`](https://github.com/alexar76/ai-service-mesh/blob/main/backend/ai_service_mesh/orchestrator.py)
contains a separate `MeshOrchestrator`: discovery, preflight, invoke and fallback to another
candidate. Its task API is independent of the factory's normal code-generation pipeline.

The older description on this page presented that service as if every factory build discovered,
funded and hired external agents for PM → Architect → Dev → QA. That integration is not implemented.
The bounded diagnosis flow above is the current factory-to-market purchase integration.

## Source map

| Path | Responsibility |
|---|---|
| [config/pipeline_flow.json](../config/pipeline_flow.json) | Internal role sequence |
| [orchestrator/task_executor_agent.py](../orchestrator/task_executor_agent.py) | Developer handoff and QA outcome hooks |
| [orchestrator/procurement.py](../orchestrator/procurement.py) | Optional purchase workflow |
| [core/procurement_store.py](../core/procurement_store.py) | Durable reservations and purchase journal |
| [ai-service-mesh](https://github.com/alexar76/ai-service-mesh/tree/main/) | Separate task orchestration service |

Related: [ecosystem architecture](ecosystem-architecture.md), [ecosystem capabilities](killer-features.md).
