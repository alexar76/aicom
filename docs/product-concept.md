# Product concept (north star)

This fork of AI-Factory optimizes for **mass-useful, embarrassing-to-send quality**, not “another repo of code.”

## Promise (5 seconds)

**One plain-language brief → a web page you can drop in chat** — with automated checks so obvious stubs and broken previews fail.

The **multi-agent pipeline** (market research → ideas/spec → architecture → code → QA → security → …) remains the **single engine**. There is **no alternate “landing-only” pipeline**: outputs are often **one-page sites**, but the **same stages** run whether work started autonomously or from a buyer brief.

### Designer / UX layer (for investors and buyers)

There is **no extra queued “designer agent”** in the state machine today. Instead, the **Architect** emits a structured **`ui_experience`** object in `architecture.json` (mood, CSS variables, Google Font pairs, motion, signature moment, anti-patterns). The **Developer** implements it for browser deliverables. The public homepage shows **Design** as its own step in the pipeline strip plus a **Designer** callout card so the story is legible to investors: product-quality UI is a first-class contract, not an afterthought.

## Same pipeline — two ways to start it

| Mode | What feeds the pipeline |
|------|-------------------------|
| **Autonomous** | **Marketing / market research** and **idea generation** on your schedule (Director, timers, autonomous pipeline) — as designed; keeps discovering and enqueueing work without a manual phrase. |
| **On-demand** | **The customer’s phrase / brief** (Admin → New Product, API, lead flow). Every downstream agent still runs in order; PM/spec/marketing use **that brief as the source of truth**, not a parallel shortcut stack. |

Landings are a **product shape**, not a **different conveyor**.

## What we guarantee vs not

| We aim to guarantee | We do not guarantee |
|---------------------|---------------------|
| Repeatable pipeline, artifacts on disk, preview | Viral growth or conversion |
| Demo/TZ/browser gates when enabled | Legal correctness of user-written claims |
| Optional crypto checkout where configured | Trademark safety of user content |

## Marketplace

The internal marketplace is an **optional channel** for packaged outputs — not required for the core “one brief → page” story. Many go-to-market paths can skip it at first.

## Monetization (landing SKU)

- **Positioning:** full pipeline + marketplace stay; the **buyer story** is a **one-shot landing page** (HTML/CSS/JS), not enterprise SaaS pricing.
- **Default list/checkout amount:** when marketing and sales artifacts do not set a price, the API uses **~$4.99 USDT** as the storefront default (`DEFAULT_STOREFRONT_PRICE_USDT` in `web/backend/api/products.py`, aligned with `DEFAULT_CHECKOUT_AMOUNT_USDT` in `web/backend/api/payment.py`). Override per product via `sales_config.json` (`pricing.usdt_price` or tier prices) or marketing `monetization_scheme.paid_tiers`.
- **Flow:** describe the page on the **homepage hero** → **Admin → New Product** (prefill via **sessionStorage** or URL `?tab=new-product&idea=…`) → pipeline runs → **Sandbox** preview on the product page → **crypto checkout** → after confirmation, **download ZIP** from **Account** (`/api/customer/orders/{id}/download`).

## Localization

Public marketing strings live in `web/frontend/lib/marketing.ts` (`en` full, `ru` partial). Set `NEXT_PUBLIC_MARKETING_LOCALE=ru` at build/runtime for Russian hero/features intro.

## Forking under a new brand

1. Rename `brandName` and strings in `marketing.ts`.
2. Update `config.yaml` → `general.platform_name`.
3. Refresh `README.md` hero paragraph and deploy URLs.
