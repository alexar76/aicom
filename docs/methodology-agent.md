# Methodology Agent

`MethodologyAgent` validates that a generated product follows the accepted process / shape for its domain (CRM, helpdesk, LMS, e-commerce, …). It is a **process gate**, not a visual-design or generic QA agent.

## Why it exists

Generic tests can confirm that a page renders and links work, but they cannot tell whether a "CRM" actually has leads, deals, pipeline stages, ownership and conversion reporting. The methodologist closes that gap.

## Architecture

```
agents/methodologist.py                          ← thin orchestrator-facing agent
web/backend/services/
  domain_methodology/
    base.py                                      ← schema v2 dataclasses
    registry.py                                  ← list / get / select / score packs
    packs/                                       ← one module per domain (crm, helpdesk, ...)
  methodology_review.py                          ← heuristic engine v2
  methodology_knowledge.py                       ← lessons + case history (memory)
web/backend/api/admin/methodology.py             ← admin API surface
```

## Domain packs (schema v2)

A pack is a *declarative methodology profile* for a product domain. Each one
contains:

| Section | Purpose |
|---|---|
| `keywords`, `categories` | Auto-select the right pack from the idea / category. |
| `entities[]` (with `fields[]`) | First-class objects the product must model (e.g. `ticket`, `deal`) and their key attributes. |
| `roles[]` | User personas the product must distinguish (e.g. `agent`, `customer`). |
| `capabilities[]` | Concrete actions the product must support (e.g. `assign ticket`). |
| `lifecycle_states[]` | Named states (`new`, `paid`, `resolved`, …) with `is_initial` / `is_terminal`. |
| `lifecycle_transitions[]` | Allowed `from → to` transitions — checked as a graph, not as flat words. |
| `acceptance_scenarios[]` | Real user journeys with steps and expected outcome (`onboarding`, `core_action`, `recovery`, …). |
| `api_endpoints[]` | API surface an honest implementation should expose (used by post-implementation review). |
| `process_metrics_definitions[]` | Each KPI carries `formula` and `target_direction`. |
| `red_flags[]` | Anti-patterns with `keywords` + optional `regex` + `fix_hint`. |
| `references[]` | Standards / textbooks the methodology is grounded in. |
| `methodology_notes` | Free-form notes for the LLM second opinion. |

### Built-in packs

| `domain_id` | Label | References |
|---|---|---|
| `crm_sales` | CRM / Sales pipeline | HubSpot Academy, Predictable Revenue, Challenger Sale |
| `helpdesk_support` | Helpdesk / IT support | ITIL 4, ISO/IEC 20000-1, HDI |
| `ecommerce` | E-commerce | Stripe / Shopify checkout patterns, OWASP ASVS |
| `lms_education` | LMS / Education | IMS Caliper, SCORM 2004 / xAPI, QM rubric |
| `hr_recruiting` | HR / Recruiting (ATS) | SHRM, OFCCP / EEOC, Greenhouse / Lever patterns |
| `project_management` | Project / Task management | Kanban (Anderson), Scrum Guide 2020 |
| `finance_billing` | Finance / Billing | IFRS / GAAP, PCI DSS, SOX 404 |
| `healthcare_wellness` | Healthcare / Wellness | HIPAA, GDPR Art.9, HL7 FHIR |
| `analytics_bi` | Analytics / BI | dbt metrics layer, OpenMetrics, Looker / Cube |
| `devtools_ops` | DevTools / Ops platform | Google SRE Book, DORA / Accelerate |

Each pack lives in its own module under
`web/backend/services/domain_methodology/packs/` and is auto-registered.

Short owner-facing playbooks (one file per domain where applicable) live under **[domain-guides/README.md](domain-guides/README.md)**.

## Heuristic engine v2

`methodology_review.py` evaluates the product on seven weighted axes:

| Axis | Weight |
|---|---|
| Required entities | 0.22 |
| Required capabilities | 0.22 |
| Lifecycle states | 0.16 |
| Lifecycle transitions (graph) | 0.10 |
| User roles | 0.08 |
| Acceptance scenarios | 0.10 |
| API endpoints (impl only) | 0.12 |

The aggregate produces a `score` in 0..100. The review fails if the score is
below the configured `min_score` **or** any high-severity finding is present.
On top of axes, both pack-level red flags and learned lessons are evaluated as
extra blockers.

The review report is uniform across both stages and now also includes
`lessons_applied` and (when `persist_case=True`) `case_id`.

## Control points

1. **Post-spec gate**

   `PMAgent` calls `review_spec(...)` after producing the specification. High-severity findings become PM retry hints — the spec is corrected before code is generated.

2. **Post-implementation gate**

   `QAAgent` calls `review_implementation(...)` over the generated code. High-severity findings become QA bugs and contribute to `quality_gates.passed`. Marketplace eligibility additionally rejects products with `methodology_review_failed`.

## Rework behaviour

If the implementation fails methodology review:

- QA reports high-severity methodology bugs.
- Marketplace readiness returns `methodology_review_failed`.
- Existing pipeline repair logic moves the product to `BUG_FOUND` / `DEV_FIXING`.

The flag `AIFACTORY_MARKETPLACE_REQUIRE_METHODOLOGY` (default `1`) controls
whether methodology failure blocks marketplace listing.

## Memory: lessons + case history

`MethodologyKnowledgeStore` persists two kinds of records under `${data_root}/methodology/`:

- `lessons.jsonl` — pluggable rules ("learned red flags") that augment built-in
  packs. A lesson has `domain` (or `*` for global), `severity`, `keywords` /
  `regex`, `fix_hint`, `applies_to` (`spec` / `implementation`), `weight` and
  `source` (`operator` / `auto` / `import`).
- `cases/<product_id>.json` — full review history per product (every spec /
  implementation review the methodologist has run).
- `feedback.jsonl` — operator feedback on past reviews.

## Search

The agent and the admin API can search across both lessons and case history:

```python
agent = MethodologyAgent(...)
results = agent.search("no payment step", domain="ecommerce")
# -> { "lessons": [...], "cases": [...] }
```

Or via the admin API:

```
GET /api/admin/methodology/search?q=no%20payment%20step&domain=ecommerce
```

## Learning loop

The methodologist learns in three ways:

1. **Operator-supplied lessons.** An admin adds a lesson via API or UI; from
   that point every review of the relevant domain (or globally with `*`)
   evaluates the lesson on top of the built-in pack.
2. **Auto-promotion via feedback.** When an admin marks a finding as
   "correct, this should always block" and supplies a `promote_finding_code`,
   the methodologist auto-creates a lesson scoped to that domain so similar
   future products fail faster.
3. **Case history.** Every review writes a `MethodologyCase` so the agent has
   memory of past failures / passes for a product and can be queried for
   "how did similar products fail?".

Helpers on the agent:

```python
agent.add_lesson(domain="helpdesk_support", title="No SLA timer",
                 detail="...", severity="high", keywords=["no sla timer"],
                 applies_to=["spec", "implementation"])

agent.learn_from_feedback(case_id=..., product_id=..., was_correct=True,
                          promote_finding_code="domain_capability_missing")

agent.history(product_id="prod-X")
```

## Admin API

```
GET    /api/admin/methodology/domains                    – pack catalog
GET    /api/admin/methodology/domains/{domain_id}        – full pack schema
POST   /api/admin/methodology/domains/match              – auto-match a pack to an idea
POST   /api/admin/methodology/review/spec                – one-shot spec review
POST   /api/admin/methodology/review/implementation/{pid}– one-shot implementation review
GET    /api/admin/methodology/cases/{product_id}         – review history
GET    /api/admin/methodology/lessons                    – list lessons
POST   /api/admin/methodology/lessons                    – add a lesson
PATCH  /api/admin/methodology/lessons/{lesson_id}        – edit / disable / re-enable
DELETE /api/admin/methodology/lessons/{lesson_id}        – delete a lesson
GET    /api/admin/methodology/search?q=...               – search lessons + cases
POST   /api/admin/methodology/feedback                   – operator feedback (auto-promotes lessons)
```

All endpoints require admin authentication.

## Operator visibility

The agent appears as `Methodologist` / `methodologist` in:

- Admin → Agents
- Admin → Live Monitor agent roster
- Admin → Agent Logs filter
- Pipeline task icons / labels
- Corporate discussion agent metadata
- Telegram / corporate chat pipeline labels
