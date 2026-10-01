# AI-Factory: Investor Functional Overview

For the visual version with diagrams and current screenshots, see: `docs/investor-deck.md`.

## 1) What the product does

AI-Factory is an autonomous product studio: it takes a product idea and turns it into a working software output through a managed multi-agent pipeline.

Core outcome:
- faster launch cycles from idea to runnable product;
- standardized quality controls across all generated products;
- centralized monitoring, recovery, and governance for scale.

## 2) End-to-end pipeline

The platform runs a staged production flow:
1. **Analyst** — market and positioning brief.
2. **Product Manager (PM)** — structured specification.
3. **Architect / Designer layer** — technical architecture + UI/UX direction (multi-variant).
4. **Design Critic** — art-direction quality gate (taste-level scoring + iteration requests).
5. **Developer** — code generation aligned with spec and architecture.
6. **Hardening** — focused refactor/tests/security/UX pass before QA.
7. **QA + Security + DevOps + GTM agents** — verification, hardening, packaging, and commercial readiness.

Every stage is persisted and observable, with retry and rework loops when quality gates fail.

## 3) Enterprise-grade governance and quality controls

Recent platform upgrades introduced strict controls that materially improve output quality:

- **Spec quality gates**  
  PM outputs are validated for testability/completeness (acceptance criteria, structure, consistency).

- **Automatic recovery loops**  
  Failed PM/QA states trigger automated re-queue and repair paths without manual intervention.

- **Production mode**  
  Stronger standards for market-ready builds: richer requirements, stricter architecture/design checks, and release-critic gating before completion.

- **Demo and marketplace quality gates**  
  Generated products are filtered for completeness and usability before public listing.

- **Designer/UX anti-template checks**  
  UX baseline checks reject thin template pages (e.g., missing CTA or weak structure).

- **Design novelty policy (anti-clone)**  
  Marketplace eligibility can require minimum design novelty score to prevent repetitive “same-looking” outputs.

- **Security hardening path**  
  Security modules and tests were stabilized (firewall behavior, audit logger reliability, auth/token edge cases).

- **Domain playbooks & discovery packs**  
  For each idea, the system infers a vertical (fintech, education, ecommerce, devtools, general) and injects a curated
  set of domain assumptions, discovery questions, UX patterns and anti-patterns into the PM brief — the equivalent of a
  domain lead sanity-checking requirements before work starts.

- **Design Critic gate (art-direction loop)**  
  After the Architect generates `ui_experience` + design variants, a dedicated Design Critic agent scores the direction
  (originality, clarity, brand-coherence, feasibility, accessibility) and can block progression back to the Architect
  until the visual direction is strong enough for production.

- **Feedback-driven regeneration**  
  User feedback (support chat, structured product feedback, telemetry events) is summarized into a feedback digest that
  is fed back into the PM brief and Hardening pass, so recurring issues and patterns directly shape the next generation.

## 4) Admin and operations capabilities

The Admin panel provides live control and observability:

- real-time pipeline monitor by product/stage/task;
- LLM logs with agent/task attribution;
- product handoff inspection (spec/architecture/developer handoff artifacts);
- manual and automated policy audit workflows;
- category/explore navigation and storefront consistency controls.

Operationally, the system supports:
- state persistence with SQLite sync/migration protections;
- non-destructive migration strategy;
- robust reprocessing after deployment/restart events;
- a release cockpit with executable go/no-go protocol checks.

## 5) Product and UX platform features

- **Multilingual foundation** for admin and support surfaces (EN/RU/ES support path).
- **Improved navigation and discoverability** in Explore/category flows.
- **Sandbox viewing behavior tuned for reliability** (same-tab open to avoid popup blockers).
- **Progressive loading path in pipeline monitor** to improve perceived performance.
- **In-product feedback loop**: public product pages expose lightweight rating + feedback forms and telemetry events,
  with aggregation in admin views and automatic routing to PM/QA/Director flows.

## 6) Why this matters commercially

For investors, the key differentiator is not “one generated app,” but a controllable generation system with:
- repeatable quality policy,
- measurable gate outcomes,
- automatic recovery from failure states,
- and governance suitable for scaling beyond demo-level output.

This turns AI generation from one-off novelty into an operational product engine.

## 7) Current status and near-term execution

Current platform state:
- core pipeline and verification stack are production-oriented;
- quality and governance controls are actively enforced;
- anti-template and anti-clone layers are now part of listing logic;
- operational maturity layer is active (load-smoke p95 checks, release protocol execution, go/no-go cockpit, feedback guardrails).

Near-term execution focus:
1. continue tightening developer + QA standards for “sellable-level” outputs;
2. expand UX heuristics and end-to-end scenario validation;
3. run repeated fresh-idea pipeline benchmarks and publish pass-rate metrics;
4. track per-product performance trend regressions and auto-alert on sustained degradation.

## 8) Distribution and revenue mechanics now implemented

- **Self-serve billing:** Stripe checkout session + webhook-based entitlement upgrades.
- **Plan ladder foundation:** free / maker / studio / enterprise plan model in customer profiles.
- **Referral loop:** per-customer referral code with attributed conversions and revenue reporting.
- **Public trust pages:** benchmark page, launch kit page, and SEO-focused content pages (blog + FAQ + sitemap/robots).
- **Viral embedding:** embeddable "Powered by AI-Factory" badge script for external sites.

See also: `docs/factory-capabilities.md` for the full function map.

---

This document is intended as the investor-facing functional snapshot of the platform and will be updated as the next quality milestones are completed.
