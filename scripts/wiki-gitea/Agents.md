# Pipeline agents

> Full roster: [`docs/agents.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/agents.md)

## Canonical list

One Python module per role under [`agents/`](http://5.129.212.122/Superowner/aicom/src/branch/main/agents/). System prompts: [`agents/prompts/`](http://5.129.212.122/Superowner/aicom/src/branch/main/agents/prompts/).

| Agent | Role |
|-------|------|
| Analyst | Idea refinement, constraints |
| PM | Spec / user stories |
| Methodologist | Domain pack gate (conditional) |
| Architect | Stack + structure |
| Design Critic | UX brief compliance (conditional) |
| Developer | Implementation |
| Hardening | Resilience pass (conditional) |
| QA | Tests + repair hints |
| Security | Scans + policy |
| DevOps | Deploy artifacts, packaging |
| Marketing | Copy, positioning |
| Sales | Pricing / GTM surface |
| Evolution Analyst | Post-ship improvements |

**Count agents from disk:** `ls agents/*.py` — do not rely on marketing copy alone.

## Flow config

Order and conditional gates: [`config/pipeline_flow.json`](http://5.129.212.122/Superowner/aicom/src/branch/main/config/pipeline_flow.json)

Runtime also adds: test gate, Playwright E2E, security tooling, storefront deploy step.

## Methodologist & domain packs

10 built-in packs under `web/backend/services/domain_methodology/packs/`.

- Index: [`docs/domain-guides/README.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/domain-guides/README.md)
- Deep dive: [`docs/methodology-agent.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/methodology-agent.md)

## Director (autonomous)

Separate from pipeline agents — schedules discovery, picks ranked ideas, enqueues products. Not listed in **AI Agents** admin roster.

## Capabilities map

[`docs/factory-capabilities.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/factory-capabilities.md)
