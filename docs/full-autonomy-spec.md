# Full Autonomy — implementation map

**Status:** implemented (MVP rollout phases 1–4)  
**Spec owner:** factory core  

This document tracks the **implemented** Full Autonomy feature. The canonical behavior:

| Mode | Config | Behavior |
|------|--------|----------|
| Supervised (default) | `general.autonomy_mode=supervised` | Unchanged — pipeline parks at `HUMAN_REVIEW_PENDING` |
| Full autonomy | `general.autonomy_mode=full` | AI surrogate (heavy judge) resolves human gates |

## Code map

| Component | Path |
|-----------|------|
| Mode resolution | `core/autonomy_mode.py` |
| Eligibility + verdict schema + audit | `core/surrogate_review.py` |
| Judge LLM agent | `agents/surrogate_reviewer.py` |
| Orchestrator bridge | `orchestrator/autonomy_bridge.py` |
| Outcome memory (L2) + exploration | `core/outcome_memory.py` |
| Discovery prior | `director/discovery_pipeline.py` → `compute_idea_score(outcome_fit)` |
| Learning objective (EV) | `core/learning_objective.py` |
| Distilled playbook (L1) | `core/playbook.py`, retrieval in `agents/base_agent.py` |
| Surrogate calibration (L3) | `core/calibration.py` |
| Process bandit (L4) | `core/process_bandit.py` |
| Factory IQ analytics | `core/factory_iq.py`, `web/backend/api/analytics.py`, page `web/frontend/app/iq/page.tsx` |
| Settings UI | Admin → Settings → **Full autonomy** (next to Factory hold) |
| Tests | `tests/test_autonomy_mode.py`, `tests/test_surrogate_review.py`, `tests/test_outcome_prior.py`, `tests/test_learning_objective.py`, `tests/test_playbook.py`, `tests/test_calibration.py`, `tests/test_process_bandit.py`, `tests/test_factory_iq.py` |

**Effective self-learning is documented in full at [effective-self-learning.md](effective-self-learning.md)** (objective, the four loops, data shapes, env knobs, proof).

## Env knobs

See `.env.example` — `AIFACTORY_AUTONOMY_*`, `AIFACTORY_OUTCOME_*`.

## Rollout status

- [x] Phase 1: `autonomy_mode` + Settings toggle  
- [x] Phase 2: Surrogate at post-DevOps, QA/security exhaust, runtime `ai_review` feedback  
- [x] Phase 3: Director pending auto-resolve (decisions file)  
- [x] Phase 4 MVP: `outcomes.jsonl` + `outcome_prior` in discovery  
- [x] Phase 5: Factory IQ analytics (`/api/analytics/factory-iq`, public mirror, `/iq` page). Grafana panel JSON pending.  
- [x] Phase 6: EV objective + distilled playbook (L1) + exploration (L2) + calibration (L3) + process bandit (L4). LLM distiller refinement and L4 apply-step deferred — see [effective-self-learning.md §10](effective-self-learning.md).  

## Operations

1. Enable in Admin → Settings → **Full autonomy** (or `AIFACTORY_AUTONOMY_MODE=full`).  
2. Emergency stop still wins: `AIFACTORY_FACTORY_ON_HOLD=1`.  
3. Audit trail: `data/autonomy/surrogate_decisions.jsonl`.  
4. Hard gates (benchmark, Critical security, objective demo/smoke) are **never** auto-approved.

See also `docs/pipeline-operations.md` (update when Phase 5 lands).
