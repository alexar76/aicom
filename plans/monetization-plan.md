# AI-Factory v2.1 — monetization plan (English)

Internal strategy outline. **Production domain and ops:** [docs/production-domain.md](../docs/production-domain.md). **Product narrative:** [docs/product-concept.md](../docs/product-concept.md), [docs/marketing.md](../docs/marketing.md).

## Overview

AI-Factory is a self-hosted, multi-agent pipeline (PM → architect → developer → QA → security → DevOps → marketing → sales → evolution) with optional crypto checkout, storefront, and admin controls. Revenue ideas below are placeholders for commercial packaging; constants and live pricing live in code (`web/backend/api/products.py`, `web/backend/api/payment.py`).

## Offerings (sketch)

### SaaS — “AI-Factory Cloud” (hypothetical hosted tier)

| Tier | Indicative $/mo | Notes |
|------|-----------------|-------|
| Starter | $49 | Low concurrency, few active products |
| Professional | $149 | Higher limits, full agent set |
| Business | $499 | Team features, integrations |
| Enterprise | custom | SLA, private cloud, dedicated support |

### Self-hosted license (annual)

- Basic / Pro / Enterprise license tiers (numbers TBD) for orgs that cannot use public cloud.
- **Not implemented, and not implementable as written.** Every component is MIT or Apache-2.0
  with no licence-key check anywhere in the code (`AIFACTORY_LICENSE_KEY` is emitted into
  generated compose files and read by nothing), so a self-hosted "tier" gates nothing. Selling
  one would mean selling support and updates, not access. Stated here because this file ships
  in the public mirror, where a reader could otherwise take it for a description of the product.

### Usage-based

- Per-pipeline or per-agent-run metering for trial or bursty workloads.

### Default landing SKU

- Storefront + checkout may default to a small **USDT** price for a marketing landing when no explicit `sales_config` price is set (see code paths above).

### Marketplace

- Commission on third-party listings; optional featured placement fees.

### Services

- Implementation packages, custom integrations, white-label branding.

## Pricing models

- **Subscription** — predictable MRR.
- **Usage-based** — pay per run for experimentation.
- **Hybrid** — base subscription + overage.

## Go-to-market (summary)

- Hosted upsell on a fully permissive repo — **not** open core: nothing is withheld from the open version, so the hosted tier competes on operation, not on features.
- Content and demos: gallery scripts, `docs/gallery/README.md`.
- Partner channel for agencies / integrators.

## Risks

- LLM cost volatility; need caps and routing controls (`model_providers.yaml`).
- Support load; triage via support bot and Director queue (`docs/pipeline-operations.md` where applicable).

## Next steps

1. Align public pricing copy with whatever is enforced in payment APIs.
2. Instrument usage (pipeline runs, LLM tokens) before selling usage-based tiers.
3. Legal review for crypto checkout and regional restrictions.
