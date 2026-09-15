# Effective self-learning

**Status:** implemented (L1–L4 + objective + proof + analytics). Frontend page live at `/iq`.

The factory does not just remember — it **learns, measurably**. It optimizes one number,
distills its own build outcomes into validated rules its agents follow, learns *what* to build
and *how* to run, calibrates its AI gatekeeper, and **proves** the improvement on a live-vs-frozen
learning curve. This document is the canonical reference: architecture, data shapes, code map, env
knobs, API, operations, and what is deferred.

Related: [full-autonomy-spec.md](full-autonomy-spec.md) (the AI surrogate that removes the human
gate — self-learning is what makes a human-free factory create *increasing* value).

---

## 1. Why this exists

Before this, "learning" was `learning_memory.py`: raw per-task rows appended to a flat JSONL and
the *last N* injected into prompts. Accumulation by recency — **no objective, no credit assignment,
no distillation, no validation, no exploration, no proof.** It could not get better. This system
replaces that with a closed optimization loop.

## 2. The objective — EV per build

Everything optimizes one measurable number ([`core/learning_objective.py`](../core/learning_objective.py)):

```
EV(build) = (demand_value if shipped else 0)  −  cost
```

- `demand_value` — money-proxy from realized signals: AIMarket invokes, checkout starts, views
  (weights `AIFACTORY_EV_*`). Zero when there is no traffic — an honest "shipped but nobody came
  is not value yet".
- `cost` — realized LLM spend plus a small per-repair-round penalty.

Realized EV (not a forecast) is what the **learning curve** plots. A rising series is the proof the
factory learns. `EV` is computed once per terminal build and stored on the episode.

## 3. The four loops

| Loop | Learns | Mechanism | Status |
|------|--------|-----------|--------|
| **L1 Tactical** | *How* to build well | Distilled, validated **playbook** → agent prompts | ✅ implemented |
| **L2 Strategic** | *What* to build next | `outcome_prior` + UCB exploration → idea score | ✅ implemented |
| **L3 Calibration** | Whether to trust our **AI gatekeeper** | Surrogate approve-accuracy → tighten threshold | ✅ implemented (opt-in) |
| **L4 Process** | *How to run* (config) | Thompson bandit over config arms per category; applies repair budget | ✅ implemented (opt-in) |

### L1 — distilled, validated playbook ([`core/playbook.py`](../core/playbook.py))

The distiller recomputes rules from `episodes.jsonl` on a cadence
(`distill_if_due`, every `AIFACTORY_PLAYBOOK_DISTILL_EVERY` terminal builds). For each category, the
dominant failure `signal` becomes a candidate **"avoid: …"** rule whose `lift_ev` is the *measured*
EV gap between builds that avoided the defect and builds that hit it. A rule is:

- `active` — support ≥ `MIN_SUPPORT` **and** measured `lift_ev > 0` (avoiding it demonstrably raised
  EV). Only `active` rules are retrieved. **The measurement is the validation** (spec §8.6) — no
  hand-waving.
- `retired` — enough evidence, but the signal did not hurt EV.
- `provisional` — too little evidence yet.

Signals recurring across **≥2 categories** also produce a `scope.category == ""` global rule, so the
playbook still helps when an agent's category is unknown.

**Retrieval** ([`base_agent._generate`](../agents/base_agent.py)) replaces "inject last N raw rows":
agents receive the **top-k active rules whose scope matches** (category + global), ranked by
`lift_ev × confidence`, deduplicated by claim (prefers the specific category rule over its global
twin). Higher signal *and* fewer tokens. Skipped for the frozen-control cohort (§6).

### L2 — strategic prior + exploration ([`core/outcome_memory.py`](../core/outcome_memory.py))

`outcome_fit_score` adds a term to `compute_idea_score` so the factory prefers categories it
**actually ships and that actually convert**. Cold start (< `OUTCOME_MIN_SAMPLES`) stays neutral —
no data, no noise. Past threshold it exploits measured `ship_rate`/`demand_rate` **plus a UCB
exploration bonus** that shrinks as evidence grows, keeping under-sampled categories reachable so the
factory never collapses onto one niche.

### L3 — surrogate calibration ([`core/calibration.py`](../core/calibration.py))

Joins `surrogate_decisions.jsonl` (what the AI gate decided + how confident) with `outcomes.jsonl`
(what happened). When a gate's `approve`s have been historically over-confident (mean confidence ≫
actual accuracy), `calibrated_min_confidence` **raises that gate's approve threshold**. This is the
machine substitute for "the operator learned not to trust that gate." Opt-in via
`AIFACTORY_AUTONOMY_CALIBRATION=1`; consulted inside `SurrogateReviewer.decide`.

### L4 — process bandit ([`core/process_bandit.py`](../core/process_bandit.py))

Learns, per category, which **config arm** (e.g. model tier / repair budget / gate strictness) yields
the best EV. `select_arm` uses Thompson sampling over per-arm EV with an ε-greedy floor;
`update` records reward after each terminal build (wired in `record_terminal_outcome` whenever a
product carries `config_arm`). **Opt-in:** the worker calls `select_process_arm` only when
`AIFACTORY_PROCESS_BANDIT=1`, applies the chosen arm to the run config, and tags the product so the
loop closes. The recommender and reward-recording are done; choosing to *apply* an arm is the single
integration point a deployment turns on.

## 4. Proof — or it isn't learning (spec §8.8)

- **Realized EV metric** — `factory_ev_per_build` (Prometheus histogram, labels `cohort` ∈
  {live, frozen}, `shipped`) plus `factory_builds_total`. Emitted on every terminal build.
- **Frozen-control A/B** — set `AIFACTORY_LEARNING_FROZEN=1` to enable a stable per-product split
  (`AIFACTORY_LEARNING_FROZEN_FRACTION`, default `0.5`): ~half the fleet runs **without** the
  playbook (frozen baseline), half runs with learning on (live). If live EV does not pull ahead of
  frozen over time, learning is off *by definition* — visible on `/iq` as `gap`.
- **Reward-hacking guard** — because EV includes **demand**, the AI surrogate cannot game ship-rate
  by approving junk: junk that ships but never converts lowers EV and demotes the rules/decisions
  that produced it.

## 5. Analytics & the `/iq` dashboard

- **Snapshot** — [`core/factory_iq.py`](../core/factory_iq.py) `factory_iq_snapshot()` is a pure,
  read-only rollup: Factory IQ (0–100), learning curve (live vs frozen + gap), ship-rate,
  cost-per-ship, EV slope, active-rule feed, and calibration error. Whitelisted scalars only.
- **API** — [`web/backend/api/analytics.py`](../web/backend/api/analytics.py):
  `GET /api/analytics/factory-iq` (dashboard) and `GET /api/public/factory-iq`
  (public mirror, gated by `AIFACTORY_PUBLIC_IQ=1`).
- **Page** — [`web/frontend/app/iq/page.tsx`](../web/frontend/app/iq/page.tsx): a live page (polls
  every 15s) showing the IQ climbing, the learning curve with the live-vs-frozen gap, and a feed of
  the playbook rules the factory is forming — *watch it get smarter*. Framer Motion + GlassCard, on
  brand with `/monitor` and `/pulse`.

## 6. Data artifacts (all under `data/`)

| File | Written by | Shape |
|------|-----------|-------|
| `state/episodes.jsonl` | `record_terminal_outcome` | per build: `objective{shipped, ev, cost_usd, repair_rounds, demand}`, `root_cause{stage, gate, signal}`, `learning_frozen` |
| `discovery/outcomes.jsonl` | `record_terminal_outcome` | per build: `category`, `reached`, `ev`, `repair_rounds`, `telemetry`, `surrogate_decisions` |
| `state/playbook.jsonl` | `distill` | per rule: `scope{category,stage}`, `claim`, `support`, `lift_ev`, `confidence`, `win_rate`, `status` |
| `state/bandit.jsonl` | `process_bandit.update` | per build under an arm: `category`, `arm`, `reward` |
| `autonomy/surrogate_decisions.jsonl` | `append_surrogate_audit` | per gate: `point`, `decision`, `confidence`, `rationale`, `product_id` |

## 7. Environment knobs

See [`.env.example`](../.env.example) (section "Effective self-learning"). Summary:

| Knob | Default | Effect |
|------|---------|--------|
| `AIFACTORY_EV_INVOKE_VALUE` / `_CHECKOUT_VALUE` / `_VIEW_VALUE` | 0.50 / 0.20 / 0.002 | demand money-proxy weights |
| `AIFACTORY_EV_REPAIR_PENALTY` | 0.10 | per-repair-round cost penalty |
| `AIFACTORY_PLAYBOOK_TOPK` | 6 | rules injected per agent |
| `AIFACTORY_PLAYBOOK_MIN_SUPPORT` | 3 | episodes needed before a rule can activate |
| `AIFACTORY_PLAYBOOK_DISTILL_EVERY` | 5 | re-distill cadence (terminal builds) |
| `AIFACTORY_PLAYBOOK_EPISODE_WINDOW` | 500 | recency window for distillation |
| `AIFACTORY_LEARNING_EXPLORE_C` | 1.5 | UCB exploration strength (L2) |
| `AIFACTORY_LEARNING_EXPLORE_FRAC` | 0.15 | ε-greedy explore fraction (L4) |
| `AIFACTORY_AUTONOMY_CALIBRATION` | 0 | enable L3 threshold tightening |
| `AIFACTORY_CALIBRATION_MIN_SAMPLES` | 5 | evidence before calibration acts |
| `AIFACTORY_PROCESS_BANDIT` | 0 | enable L4 arm selection |
| `AIFACTORY_PROCESS_BANDIT_ARMS` | balanced,heavy,light | config arms |
| `AIFACTORY_LEARNING_FROZEN` | 0 | enable live-vs-frozen A/B proof |
| `AIFACTORY_LEARNING_FROZEN_FRACTION` | 0.5 | share of builds in frozen control (playbook off) |
| `AIFACTORY_PUBLIC_IQ` | 0 | expose the public `/api/public/factory-iq` mirror |

## 8. Operations

1. The loop runs automatically: every terminal build writes an episode + outcome, the playbook
   re-distills on cadence, agents pick up active rules on their next run.
2. To **prove** learning, set `AIFACTORY_LEARNING_FROZEN=1` (50/50 split by default) and watch
   `gap` on `/iq` or Grafana (`factory_ev_per_build{cohort}`) once terminal builds accumulate.
3. Turn on L3 (`AIFACTORY_AUTONOMY_CALIBRATION=1`) once enough surrogate decisions have outcomes.
4. Turn on L4 (`AIFACTORY_PROCESS_BANDIT=1`) and have the worker apply `select_process_arm` to the
   run config, tagging `config_arm` on the product.

## 9. Tests

- [`tests/test_learning_objective.py`](../tests/test_learning_objective.py) — EV math.
- [`tests/test_playbook.py`](../tests/test_playbook.py) — distill promotes positive-lift rules,
  retires harmless signals, scope-matched retrieval.
- [`tests/test_calibration.py`](../tests/test_calibration.py) — approve-accuracy + threshold raise.
- [`tests/test_process_bandit.py`](../tests/test_process_bandit.py) — update, arm stats, exploit pick.
- [`tests/test_factory_iq.py`](../tests/test_factory_iq.py) — snapshot, learning curve, ship/cost.
- [`tests/test_outcome_prior.py`](../tests/test_outcome_prior.py) — cold-start neutrality + prior.

## 10. Completion status

All four previously-deferred pieces are now implemented:

- **L4 apply step — done.** `process_bandit.assign_build_arm` picks a config arm at product
  creation (`web/backend/main.py:_append_product_to_pipeline`, opt-in
  `AIFACTORY_PROCESS_BANDIT=1`), tags `config_arm`, and applies the arm's repair-budget via
  `quality_settings.max_pipeline_repair_rounds_for_product` (used in `task_executor_agent`). Realized
  EV flows back to that arm in `record_terminal_outcome`. Arms: `light`(3)/`balanced`(default)/`heavy`(10)
  repair rounds — the bandit learns the cost/ship trade-off per category. An explicit
  `AIFACTORY_MAX_QUALITY_LOOPS` hard cap is always respected.
- **LLM distiller refinement — done.** `playbook.refine_playbook_claims` (async) rewrites active rule
  claims into crisp guidance; opt-in `AIFACTORY_PLAYBOOK_LLM_REFINE=1`, scheduled from the Director
  worker. Measurement fields (lift/confidence/status) are never touched; deterministic distillation is
  unchanged.
- **Deeper credit assignment — done.** `outcome_memory._extract_root_cause` derives the responsible
  stage from the task history (last failed task's agent), the failing gate, and records a compact
  per-stage `decisions` trail on each episode for future attribution.
- **Grafana panel JSON — done.** `grafana/dashboards/factory-iq.json` (6 panels: EV live-vs-frozen,
  builds, surrogate decisions/confidence/escalations, ship-vs-fail). The `/iq` page visualizes the
  same data for non-Grafana users.

### Still genuinely future (not blocking)

- Per-decision *counterfactual* attribution (which architecture choice caused the lift) beyond the
  recorded `decisions` trail.
- Applying bandit arms to levers other than repair budget (model tier, gate strictness).
