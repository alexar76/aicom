# AI-Factory — Positioning notes

> Snapshot date: 2026-05-10. Pricing and features for hosted products change frequently — always verify on the vendor's own site before quoting.

This document is internal positioning material, not a head-to-head ranking. AI-Factory and hosted AI app builders (Bolt.new, Lovable, v0, Devin, Replit Agent, Cursor, Windsurf, etc.) are different shapes of product and choose different trade-offs. Anyone publishing a "we beat all of them" table should expect (correctly) to be called out for cherry-picking; this file therefore lists what we focus on, where the trade-offs sit, and what is genuinely measurable in our repo.

---

## What hosted builders do well

- Polished cloud editor and onboarding.
- Hosted previews, team accounts, billing, SSO.
- Prebuilt integrations (DBs, auth, deploys) configured for you.
- Continuous product investment by a vendor team — Bolt, Lovable, v0, Devin, Replit Agent, Cursor, Windsurf all ship features we do not have and do not plan to chase.

If those properties matter more than self-hosting, those tools are the right pick. AI-Factory does not try to replace a cloud IDE.

## Where AI-Factory is different

- **Self-hosted, MIT.** You run the stack on your own box; artifacts, state, logs, and the SQLite/Postgres pipeline DB are on disk you control. `LICENSE` is MIT.
- **Your own LLM keys.** No vendor lock-in on the inference layer. `llm/router.py` routes across configured providers; DeepSeek is the default for most installs.
- **Pipeline of role-specialized agents** rather than one chat agent. Source of truth is `agents/` (one Python class per role) and `config/pipeline_flow.json` (`agent_flow` order). Roles today: Analyst, PM, Methodologist, Architect, Design Critic, Developer, Hardening, QA, Security, DevOps, Marketing, Sales, Evolution Analyst. Some are conditional gates (Methodologist, Design Critic, Hardening). Director is a separate meta-worker.
- **Repair loops with bounded budget.** Demo / browser / security / methodology gates can send a product back to `DEV_FIXING`; `AIFACTORY_MAX_QUALITY_LOOPS` caps the number of remediation cycles before `FAILED` (`core/quality_settings.py`).
- **Playwright-based deep crawl in CI/QA.** Implementation is `web/backend/services/browser_preview_e2e.py`. It is a real artifact, not a feature checkbox — but it is also not the same scope as paid hosted E2E platforms; do not market it as "better than" theirs.
- **Storefront with optional on-chain checkout** for shipped products (`web/backend/api/payment.py`).
- **On-disk traceability.** Spec, code, telemetry, LLM call logs (`data/logs/llm_calls.jsonl`) and pipeline state are all readable files; this is the main reason operators pick AI-Factory.

## Trade-offs to be honest about

- Bring-your-own-keys means **bring-your-own bill**. DeepSeek is cheap; `full_software` jobs with many repair rounds can still run into double-digit dollars.
- Setup is **`docker compose up`** plus configuring providers — not zero-ops.
- We do not have a hosted multi-tenant SaaS, a billing dashboard, an in-browser collaborative editor, or vendor support SLAs.
- "Quality gates pass" is a meaningful bar but not equivalent to "production-ready application". Most products in the demo catalog go through several `DEV_FIXING` rounds; some end in `FAILED` after exhausting the loop budget. The README's wall-clock and cost numbers reflect that.
- We do not claim "outperforms every known competitor". Different products, different problems.

## Closest open-source neighbours

There are very few projects in this shape; most public AI coding tools are IDE assistants or single-agent SaaS generators. Examples observed during the snapshot date:

- `zainsaeeed/ai-website-system` — small multi-agent landing generator.
- `dyuhaus/SaaS-Generator` — pipeline-style SaaS generator.

These exist; check their READMEs for current state. AI-Factory differs mainly by scope (full pipeline, QA gates, storefront) rather than by claiming uniqueness.

## How to talk about AI-Factory externally

- Compare on **what is in this repo today**, not on aspirational features.
- Cite paths (`agents/`, `config/pipeline_flow.json`, `web/backend/services/browser_preview_e2e.py`, `core/quality_settings.py`, `LICENSE`) so readers can check.
- Do not quote competitor pricing without re-fetching it on the day of posting.
- Avoid "no one else does X" framing — most hosted vendors do *something* in adjacent space, and the audience knows it.

---

*Internal doc. Not linked from the README hero. Keep it grounded.*
